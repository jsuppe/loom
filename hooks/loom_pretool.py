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
                skipped: str | None) -> None:
        _record({
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
        })

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
                reqs=0, specs=0, drift=False, skipped="cli_unavailable")
        return 0

    if proc.returncode == 1:
        _log(f"loom error: {proc.stdout.strip() or proc.stderr.strip()}")
        _finish(tool=tool_name, file=file_path, fired=False, bytes_out=0,
                reqs=0, specs=0, drift=False, skipped="cli_error")
        return 0

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _log(f"could not parse loom output: {proc.stdout[:200]}")
        _finish(tool=tool_name, file=file_path, fired=False, bytes_out=0,
                reqs=0, specs=0, drift=False, skipped="parse_error")
        return 0

    reqs = data.get("requirements", []) or []
    specs = data.get("specifications", []) or []
    drift = bool(data.get("drift_detected"))

    if not data.get("linked"):
        _finish(tool=tool_name, file=file_path, fired=False, bytes_out=0,
                reqs=0, specs=0, drift=False, skipped="no_link")
        return 0

    summary = data.get("summary") or ""
    # Build a richer additional-context block. The summary is the headline;
    # the detail lines help the agent reason about which req applies.
    lines: list[str] = [summary] if summary else []
    for r in reqs:
        flag = " [SUPERSEDED]" if r.get("superseded") else ""
        lines.append(f"  - {r['id']} [{r['domain']}]{flag}: {r['value']}")
        if r.get("rationale"):
            lines.append(f"    Rationale: {r['rationale']}")
    for s in specs:
        lines.append(f"  - {s['id']} -> {s['parent_req']}: {s['description']}")

    message = "\n".join(lines)
    bytes_out = len(message.encode("utf-8"))

    if drift and os.environ.get("LOOM_HOOK_BLOCK_ON_DRIFT") == "1":
        print(message, file=sys.stderr)
        _finish(tool=tool_name, file=file_path, fired=True, bytes_out=bytes_out,
                reqs=len(reqs), specs=len(specs), drift=True, skipped=None)
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
            reqs=len(reqs), specs=len(specs), drift=drift, skipped=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
