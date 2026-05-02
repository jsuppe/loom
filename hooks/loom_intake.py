#!/usr/bin/env python3
"""
Loom UserPromptSubmit hook (M11.5 P1 scaffold).

Runs before the agent sees a user message. Classifies the message
as requirement-shape, runs ``loom.intake.process_message`` to get
a branch decision, and injects a system-reminder with the result.

NOT YET REGISTERED in Claude Code's settings.json — that's M11.5
P2. This file ships as the install target so users can wire it up
manually after evaluation.

Protocol (Claude Code UserPromptSubmit hook):
    - stdin: JSON with at least {prompt} and optionally {session_id}.
    - stdout: JSON envelope with hookSpecificOutput.additionalContext
              when the hook has something to inject; empty stdout
              otherwise.
    - exit code 0 on success.

Output JSON shape (mirrors loom_pretool.py)::

    {"continue": true,
     "hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                            "additionalContext": "<reminder>"}}

The hook silently no-ops on:
  * classifier errors (LLM unavailable, parse failure)
  * branch == "noop" (message wasn't requirement-shape)

Environment:
    LOOM_PROJECT             Override project detection.
    LOOM_INTAKE_MODEL        Override classifier model.
    LOOM_INTAKE_DAILY_BUDGET Override daily auto-link cap.
    LOOM_INTAKE_DEBUG        1 to log hook activity to stderr.

Install (manual, P1):
    Add to ``.claude/settings.json``:
      {"hooks": {"UserPromptSubmit": [{"type": "command",
                  "command": "python /abs/path/to/hooks/loom_intake.py"}]}}
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Ensure the package is importable when this script runs from a
# checkout that hasn't been pip-installed.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))


def _log(msg: str) -> None:
    if os.environ.get("LOOM_INTAKE_DEBUG") == "1":
        print(f"[loom-intake] {msg}", file=sys.stderr)


def _resolve_project_name() -> str:
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


def main() -> int:
    t0 = time.perf_counter()
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as e:
        _log(f"bad stdin JSON: {e}")
        return 0

    prompt = event.get("prompt") or event.get("user_message") or ""
    if not prompt.strip():
        _log("empty prompt; no-op")
        return 0

    session_id = event.get("session_id") or "intake-hook"
    msg_id = event.get("message_id") or f"hook:{int(time.time() * 1000)}"
    project = _resolve_project_name()

    # Defer the heavy imports until we know we have something to do.
    try:
        from loom.store import LoomStore
        from loom import intake
    except Exception as e:
        _log(f"import failed: {e}")
        return 0

    daily_budget = int(os.environ.get(
        "LOOM_INTAKE_DAILY_BUDGET",
        str(intake.DEFAULT_DAILY_BUDGET),
    ))

    try:
        store = LoomStore(project)
    except Exception as e:
        _log(f"store open failed: {e}")
        return 0

    try:
        outcome = intake.process_message(
            store, prompt,
            msg_id=msg_id,
            session=session_id,
            daily_budget=daily_budget,
        )
    except Exception as e:
        _log(f"process_message raised: {e}")
        return 0

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    _log(f"branch={outcome['branch']} latency={elapsed_ms}ms")

    if outcome["branch"] == "noop" or not outcome.get("reminder"):
        return 0

    reminder = (
        "<system-reminder source=\"loom-intake\">\n"
        + outcome["reminder"]
        + "\n</system-reminder>"
    )
    response = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": reminder,
        },
    }
    print(json.dumps(response, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
