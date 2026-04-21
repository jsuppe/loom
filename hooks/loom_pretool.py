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

Install by adding to your settings.json (see hooks/README.md for a sample).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
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


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as e:
        _log(f"bad stdin JSON: {e}")
        return 0  # never block the tool on our own parse error

    tool_name = event.get("tool_name") or event.get("tool") or ""
    if tool_name not in WATCHED_TOOLS:
        _log(f"skipping tool: {tool_name!r}")
        return 0

    tool_input = event.get("tool_input") or event.get("input") or {}
    file_path = _extract_file_path(tool_name, tool_input)
    if not file_path:
        _log(f"no file path in tool_input for {tool_name}")
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
        return 0

    # Exit codes from `loom context`: 0 = clean, 2 = drift, 1 = error.
    if proc.returncode == 1:
        _log(f"loom error: {proc.stdout.strip() or proc.stderr.strip()}")
        return 0

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _log(f"could not parse loom output: {proc.stdout[:200]}")
        return 0

    if not data.get("linked"):
        return 0  # nothing to say

    summary = data.get("summary") or ""
    # Build a richer additional-context block. The summary is the headline;
    # the detail lines help the agent reason about which req applies.
    lines: list[str] = [summary] if summary else []
    for r in data.get("requirements", []):
        flag = " [SUPERSEDED]" if r.get("superseded") else ""
        lines.append(f"  - {r['id']} [{r['domain']}]{flag}: {r['value']}")
    for s in data.get("specifications", []):
        lines.append(f"  - {s['id']} → {s['parent_req']}: {s['description']}")

    message = "\n".join(lines)

    if data.get("drift_detected") and os.environ.get("LOOM_HOOK_BLOCK_ON_DRIFT") == "1":
        print(message, file=sys.stderr)
        return 2  # block and surface the reason

    # Non-blocking context injection.
    response = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": message,
        },
    }
    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    sys.exit(main())
