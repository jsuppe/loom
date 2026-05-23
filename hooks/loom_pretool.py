#!/usr/bin/env python3
"""
Loom PreToolUse hook for Claude Code.

Runs before Edit/Write/MultiEdit tool calls, calls `loom context <file>`, and
injects any linked requirements + drift warnings into the agent's context as
additional context. This is the "push, don't pull" ergonomic layer: the agent
learns about linked requirements without having to remember to ask.

Protocol (Claude Code PreToolUse hook):
    - stdin: JSON with at least {tool_name, tool_input}
    - stdout: JSON response (see below) OR nothing
    - stderr: surfaced on non-zero exit

Output JSON (non-blocking; injects context):
    {"continue": true,
     "hookSpecificOutput": {"hookEventName": "PreToolUse",
                            "additionalContext": "..."}}

If LOOM_HOOK_BLOCK_ON_DRIFT=1, drift instead exits 2 with the message on
stderr, forcing the agent to acknowledge. Default is non-blocking.

Environment:
    LOOM_BIN                 Path to the loom CLI (default: `loom` on PATH,
                             falling back to the sibling scripts/loom).
    LOOM_PROJECT             Override project detection.
    LOOM_HOOK_BLOCK_ON_DRIFT 1 to block the tool call on drift (default 0).
    LOOM_HOOK_DEBUG          1 to log hook activity to stderr.
    LOOM_HOOK_LOG            Explicit path for the JSONL activity log
                             (default: ~/.openclaw/loom/<project>/.hook-log.jsonl).
                             Set to empty string to disable logging.

Install by adding to your settings.json (see hooks/README.md for a sample).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

WATCHED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _log(msg: str) -> None:
    if os.environ.get("LOOM_HOOK_DEBUG") == "1":
        print(f"[loom-hook] {msg}", file=sys.stderr)


def _find_loom_bin() -> list[str]:
    """Resolve the loom executable. Prefer explicit env, then PATH, then sibling."""
    if bin_env := os.environ.get("LOOM_BIN"):
        return [bin_env]
    # Sibling: hooks/ is next to scripts/ in the repo layout.
    sibling = Path(__file__).resolve().parent.parent / "scripts" / "loom"
    if sibling.exists():
        return [sys.executable, str(sibling)]
    return ["loom"]


def _extract_file_path(tool_name: str, tool_input: dict) -> str | None:
    """Pull the file path off an Edit/Write/MultiEdit/NotebookEdit input."""
    if tool_name in {"Edit", "Write", "MultiEdit"}:
        return tool_input.get("file_path")
    if tool_name == "NotebookEdit":
        return tool_input.get("notebook_path")
    return None


def _line_range_for_match(file_text: str, needle: str) -> tuple[int, int] | None:
    """Return the 1-indexed (start_line, end_line) of the first occurrence
    of ``needle`` in ``file_text``, or None on miss."""
    if not needle:
        return None
    idx = file_text.find(needle)
    if idx < 0:
        return None
    start_line = file_text.count("\n", 0, idx) + 1
    end_line = start_line + needle.count("\n")
    return (start_line, end_line)


def _extract_edit_range(
    tool_name: str, tool_input: dict, file_path: str,
) -> str | None:
    """M16.2 — for Edit/MultiEdit, compute the line-range of the edit by
    locating ``old_string`` in the file. Returns ``"start-end"`` or
    ``"start"`` for single-line edits, or None when the range can't be
    determined (file missing, old_string not found, or tool not
    supported).

    Tool coverage (per D3): Edit + MultiEdit only. Write defaults to
    whole-file (lines='all' is correct). NotebookEdit cells aren't
    lines. Just-log per D2 — this only writes the range to the hook
    log; never calls `loom link`.

    MultiEdit returns the UNION span (min start across edits to max
    end) so downstream can express the modified region as one range.
    """
    if tool_name not in {"Edit", "MultiEdit"}:
        return None
    try:
        file_text = Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    if tool_name == "Edit":
        old = tool_input.get("old_string") or ""
        span = _line_range_for_match(file_text, old)
        if span is None:
            return None
        s, e = span
        return str(s) if s == e else f"{s}-{e}"

    # MultiEdit — compute union across the edits[] array
    edits = tool_input.get("edits") or []
    if not edits:
        return None
    spans: list[tuple[int, int]] = []
    for edit in edits:
        old = (edit or {}).get("old_string") or ""
        span = _line_range_for_match(file_text, old)
        if span is not None:
            spans.append(span)
    if not spans:
        return None
    union_start = min(s for s, _ in spans)
    union_end = max(e for _, e in spans)
    return str(union_start) if union_start == union_end else f"{union_start}-{union_end}"


def _resolve_project_name() -> str:
    """Mirror scripts/loom `get_project_name` so logging lands in the same dir."""
    if env := os.environ.get("LOOM_PROJECT"):
        return env
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "default"


def _log_path() -> Path | None:
    """Resolve the JSONL log path. Returns None if logging is disabled."""
    override = os.environ.get("LOOM_HOOK_LOG")
    if override is not None:
        if override == "":
            return None
        return Path(override)
    return Path.home() / ".openclaw" / "loom" / _resolve_project_name() / ".hook-log.jsonl"


def _record(entry: dict) -> None:
    """Append one JSONL entry. Silent on failure — never block the hook."""
    path = _log_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except OSError as e:
        _log(f"log write failed: {e}")


def main() -> int:
    t0 = time.perf_counter()
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"

    def _finish(*, tool: str, file: str | None, fired: bool,
                bytes_out: int, reqs: int, specs: int, drift: bool,
                skipped: str | None,
                edit_range: str | None = None) -> None:
        entry = {
            "ts": ts,
            "tool": tool,
            "file": file,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "bytes": bytes_out,
            "reqs": reqs,
            "specs": specs,
            "drift": drift,
            "fired": fired,
            "skipped": skipped,
        }
        # M16.2 — only emit edit_range when we computed one (Edit/MultiEdit
        # only, file readable, old_string locatable). Absent field on
        # older or N/A entries — backward-compatible.
        if edit_range is not None:
            entry["edit_range"] = edit_range
        _record(entry)

    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as e:
        _log(f"bad stdin JSON: {e}")
        _finish(tool="", file=None, fired=False, bytes_out=0,
                reqs=0, specs=0, drift=False, skipped="bad_stdin")
        return 0

    tool_name = event.get("tool_name") or event.get("tool") or ""
    if tool_name not in WATCHED_TOOLS:
        _log(f"skipping tool: {tool_name!r}")
        # Don't log non-watched tools — they're noise that would swamp the log.
        return 0

    tool_input = event.get("tool_input") or event.get("input") or {}
    file_path = _extract_file_path(tool_name, tool_input)
    if not file_path:
        _log(f"no file path in tool_input for {tool_name}")
        _finish(tool=tool_name, file=None, fired=False, bytes_out=0,
                reqs=0, specs=0, drift=False, skipped="no_file_path")
        return 0

    # M16.2 — best-effort line-range extraction for Edit/MultiEdit.
    # Computed once here so every _finish callsite below logs it
    # uniformly. None for Write/NotebookEdit or when old_string isn't
    # locatable. Pure log entry — no auto-link side-effect (D2).
    edit_range = _extract_edit_range(tool_name, tool_input, file_path)

    # `loom context` reads only ChromaDB metadata — no embedding, no Ollama.
    cmd = _find_loom_bin() + ["context", file_path]
    _log(f"running: {' '.join(cmd)}")

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        _log(f"loom invocation failed: {e}")
        _finish(tool=tool_name, file=file_path, fired=False, bytes_out=0,
                reqs=0, specs=0, drift=False, skipped="cli_unavailable",
                edit_range=edit_range)
        return 0

    if proc.returncode == 1:
        _log(f"loom error: {proc.stdout.strip() or proc.stderr.strip()}")
        _finish(tool=tool_name, file=file_path, fired=False, bytes_out=0,
                reqs=0, specs=0, drift=False, skipped="cli_error",
                edit_range=edit_range)
        return 0

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _log(f"could not parse loom output: {proc.stdout[:200]}")
        _finish(tool=tool_name, file=file_path, fired=False, bytes_out=0,
                reqs=0, specs=0, drift=False, skipped="parse_error",
                edit_range=edit_range)
        return 0

    reqs = data.get("requirements", []) or []
    specs = data.get("specifications", []) or []
    drift = bool(data.get("drift_detected"))
    # M13.5b: foundation drift from the Driftgraph substrate. Distinct
    # signal from local supersedes — surfaced separately so the agent
    # knows the upstream evidence moved on the graph side.
    graph_drift = bool(data.get("graph_drift_detected"))
    graph_drift_entries = data.get("graph_drift", []) or []

    if not data.get("linked"):
        _finish(tool=tool_name, file=file_path, fired=False, bytes_out=0,
                reqs=0, specs=0, drift=False, skipped="no_link",
                edit_range=edit_range)
        return 0

    summary = data.get("summary") or ""
    # Build a richer additional-context block. The summary is the headline;
    # the detail lines help the agent reason about which req applies.
    lines: list[str] = [summary] if summary else []
    for r in reqs:
        flag = " [SUPERSEDED]" if r.get("superseded") else ""
        graph_flag = " [GRAPH-DRIFT]" if r.get("graph_drifted") else ""
        lines.append(f"  - {r['id']} [{r['domain']}]{flag}{graph_flag}: {r['value']}")
        if r.get("rationale"):
            lines.append(f"    Rationale: {r['rationale']}")
    for s in specs:
        lines.append(f"  - {s['id']} -> {s['parent_req']}: {s['description']}")

    if graph_drift_entries:
        lines.append("")
        lines.append("Driftgraph foundation-drift — upstream evidence moved on the graph:")
        for g in graph_drift_entries:
            for anc in g["drifted_ancestors"][:3]:
                a = anc.get("ancestor", {})
                subj = (a.get("ancestor_subject") or "")[:60]
                lines.append(f"  - {g['req_id']} → ancestor "
                             f"{a.get('ancestor_claim_id', '?')[:16]}: {subj}")
        # M13.6d — imperative warning patterned on L9 full-kit
        # (rhetorical opener + inline action-verb imperative). On
        # evidence-dependent tasks this lifts pause rate from 33%
        # (M13.6c v1 generic warning) to 100% (M13.6d v2). The
        # warning text is generated in services.context() so the
        # hook stays a pure pass-through.
        warning_text = data.get("graph_drift_warning_text") or ""
        if warning_text:
            lines.append("")
            lines.append(warning_text)

    message = "\n".join(lines)
    bytes_out = len(message.encode("utf-8"))

    # M13.5b: gate blocks on EITHER local drift OR graph drift when
    # LOOM_HOOK_BLOCK_ON_DRIFT=1 is set.
    if (drift or graph_drift) and os.environ.get("LOOM_HOOK_BLOCK_ON_DRIFT") == "1":
        print(message, file=sys.stderr)
        _finish(tool=tool_name, file=file_path, fired=True, bytes_out=bytes_out,
                reqs=len(reqs), specs=len(specs),
                drift=(drift or graph_drift), skipped=None,
                edit_range=edit_range)
        return 2

    response = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": message,
        },
    }
    print(json.dumps(response))
    _finish(tool=tool_name, file=file_path, fired=True, bytes_out=bytes_out,
            reqs=len(reqs), specs=len(specs), drift=drift, skipped=None,
            edit_range=edit_range)
    return 0


if __name__ == "__main__":
    sys.exit(main())
