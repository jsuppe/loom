#!/usr/bin/env python3
"""
Phase M — cross-session memory smoke (C).

Direct port of phK (Python) and phL (C++) to C. Fits between them
on the language-fitness axis: more qwen training data than C++,
simpler syntax, but errno-based error handling is a different idiom
than Python exceptions or C++ try/catch.

The C-idiomatic equivalent of S1 (swallow vs propagate exception):
errno propagation. The reference fetch_with_retry clears errno
before returning (the "swallow"). The contrarian task pushes qwen
to leave errno set so callers can debug.

Cells (same as phK/phL):
  off                — task only, no rule
  on-rule            — req(value=rule, rationale="")
  on-rule+placebo    — req(value=rule, rationale=length-matched filler)
  on-rule+rat        — req(value=rule, rationale=true rationale)

Default executor: qwen3.5:latest (same as phK/phL for clean cross-
language comparison).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"
OUT_DIR = BAKEOFF_DIR / "runs-v2"
SCENARIO_DIR = (BAKEOFF_DIR / "benchmarks" / "crosssession_c"
                / "s1_swallow_errno")

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass


# ---------------------------------------------------------------------------
# Scenario config
# ---------------------------------------------------------------------------

TASK = (
    "The retry loop in retry.c is hiding errors from callers — when "
    "do_fetch fails, the retry function clears errno before "
    "returning, so the caller has no way to know what went wrong. "
    "Modify fetch_with_retry to preserve the first failure's errno "
    "across retry attempts so callers can debug network problems."
)

RULE = (
    "Constraint for retry.c::fetch_with_retry: must clear errno to 0 "
    "before returning, regardless of how many internal do_fetch "
    "attempts failed. Callers must NOT see errno set by internal "
    "failures. The function returns NULL on overall failure with "
    "errno cleared, or a non-NULL pointer on success with errno "
    "cleared."
)

RATIONALE = (
    "The retry wrapper in backoff_loop.c one frame up reads errno "
    "after the call to decide whether to backoff. If we leave errno "
    "set from a transient internal failure, the wrapper backs off "
    "unnecessarily and we lose throughput — production incident "
    "2024-09-12 cost three hours of degraded service while ops "
    "chased an errno-leak that was actually working as intended. "
    "The current clear-errno behavior is load-bearing for the "
    "BackoffError wrapper above us."
)


PLACEBO_TARGET_LEN = len(RATIONALE)
def make_placebo() -> str:
    base = (
        "This requirement specifies that errno must be cleared in "
        "fetch_with_retry. Code that clears errno is compliant with "
        "this requirement. Code that leaves errno set is non-compliant. "
        "The compliant pattern is to clear; the non-compliant pattern "
        "is to leave errno set. Applying this requirement means "
        "clearing errno before return. Failing to apply it means "
        "errno leaks to the caller."
    )
    while len(base) < PLACEBO_TARGET_LEN - 50:
        base += " The compliance pattern is requirement-applies; non-compliance is requirement-does-not-apply."
    return base[:PLACEBO_TARGET_LEN].rstrip() + "."

PLACEBO = make_placebo()


# ---------------------------------------------------------------------------
# Direct Ollama call
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/generate"


def call_ollama(model: str, prompt: str, timeout: int = 600) -> dict:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=body,
                                  headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    elapsed = time.time() - t0
    return {
        "response": data.get("response", ""),
        "elapsed_s": elapsed,
        "input_tokens": data.get("prompt_eval_count", 0),
        "output_tokens": data.get("eval_count", 0),
    }


# ---------------------------------------------------------------------------
# Prompt construction (mirrors task_build_prompt format)
# ---------------------------------------------------------------------------

def build_prompt(cell: str, retry_h: str, retry_c: str) -> str:
    parts: list[str] = []
    parts.append(f"# Task: {TASK}\n")
    parts.append("Files to modify: retry.c")
    parts.append("Grading test: tests/test_retry.c")
    parts.append("Size budget: <= 1 file, <= 200 LoC\n")

    if cell != "off":
        parts.append("## Requirements\n")
        parts.append("### REQ-001 [behavior]")
        parts.append(f"Value: {RULE}")
        if cell == "on-rule+placebo":
            parts.append(f"Rationale: {PLACEBO}")
        elif cell == "on-rule+rat":
            parts.append(f"Rationale: {RATIONALE}")
        parts.append("")

    parts.append("## Source context\n")
    parts.append("### retry.h (header — do not modify)")
    parts.append("```c")
    parts.append(retry_h)
    parts.append("```\n")
    parts.append("### retry.c (modify this)")
    parts.append("```c")
    parts.append(retry_c)
    parts.append("```\n")

    parts.append("## Output contract")
    parts.append(
        "Reply with ONE C code block (```c ... ```) containing the "
        "**entire new file content** for `retry.c`. You MUST include all "
        "existing code you want to keep — this file will be OVERWRITTEN with "
        "your output. Do not include prose outside the code block."
    )
    return "\n".join(parts)


def extract_c_code(response: str) -> str | None:
    for fence in ("c", "C"):
        m = re.search(rf"```{re.escape(fence)}\s*\n(.*?)\n```",
                       response, re.DOTALL)
        if m:
            return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)\n```", response, re.DOTALL)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Workspace + grading
# ---------------------------------------------------------------------------

def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phM_s1_c_"))
    shutil.copy(SCENARIO_DIR / "reference" / "retry.h", ws / "retry.h")
    shutil.copy(SCENARIO_DIR / "reference" / "retry.c", ws / "retry.c")
    return ws


def grade_workspace(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="phM_grade_s1_"))
    shutil.copy(workspace / "retry.h", grade_dir / "retry.h")
    shutil.copy(workspace / "retry.c", grade_dir / "retry.c")
    shutil.copy(SCENARIO_DIR / "tests" / "test_retry.c",
                 grade_dir / "test_retry.c")
    exe = grade_dir / "test_runner.exe"

    compile_proc = subprocess.run(
        ["gcc", "-std=c11", "-I", str(grade_dir),
         str(grade_dir / "retry.c"),
         str(grade_dir / "test_retry.c"),
         "-o", str(exe)],
        capture_output=True, text=True, timeout=60,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    if compile_proc.returncode != 0:
        return {
            "passed": 0, "total": 2,
            "compile_failed": True,
            "stdout_tail": (compile_proc.stdout + compile_proc.stderr)[-1500:],
        }

    run_proc = subprocess.run(
        [str(exe)],
        capture_output=True, text=True, timeout=30,
        encoding="utf-8", errors="replace",
    )
    out = run_proc.stdout + run_proc.stderr
    m = re.search(r"SUMMARY:\s*(\d+)\s*passed,\s*(\d+)\s*failed", out)
    if m:
        passed = int(m.group(1))
        failed = int(m.group(2))
        return {
            "passed": passed, "total": passed + failed,
            "compile_failed": False,
            "stdout_tail": out[-1500:],
        }
    return {
        "passed": 0, "total": 2,
        "compile_failed": False,
        "stdout_tail": out[-1500:],
    }


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------

RATIONALE_KEYPHRASES = ["wrapper", "BackoffError", "incident", "load-bearing"]


def check_cited_rationale(workspace: Path) -> dict:
    target = workspace / "retry.c"
    if not target.exists():
        return {"cited": False, "matched": []}
    text = target.read_text(encoding="utf-8")
    matched = [kp for kp in RATIONALE_KEYPHRASES if kp.lower() in text.lower()]
    return {"cited": bool(matched), "matched": matched}


def run_one(cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] cell={cell} workspace={workspace}")

    retry_h = (workspace / "retry.h").read_text(encoding="utf-8")
    retry_c = (workspace / "retry.c").read_text(encoding="utf-8")
    prompt = build_prompt(cell, retry_h, retry_c)
    print(f"[prompt] {len(prompt)} chars")

    model = os.environ.get("PHM_EXEC_MODEL", "qwen3.5:latest")
    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        return {
            "phase": "M_crosssession_c_smoke",
            "scenario": "S1",
            "cell": cell,
            "run_id": run_id,
            "passed": 0, "total": 2,
            "error": f"ollama call failed: {e}",
            "wall_s": round(time.time() - t0, 1),
        }
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} "
          f"out={llm['output_tokens']}")

    code = extract_c_code(llm["response"])
    if code is None:
        no_code_summary = {
            "phase": "M_crosssession_c_smoke",
            "scenario": "S1",
            "cell": cell,
            "run_id": run_id,
            "passed": 0, "total": 2,
            "pass_rate": 0.0,
            "compile_failed": True,
            "no_code_extracted": True,
            "input_tokens": llm["input_tokens"],
            "output_tokens": llm["output_tokens"],
            "model": model,
            "response_tail": llm["response"][-1500:],
            "wall_s": round(time.time() - t0, 1),
        }
        cell_slug = cell.replace("+", "_").replace("-", "_")
        out_path = OUT_DIR / f"phM_s1_c_{cell_slug}_run{run_id}_summary.json"
        out_path.write_text(json.dumps(no_code_summary, indent=2),
                             encoding="utf-8")
        print(f"SUMMARY: {cell} no_code_extracted out_tokens={llm['output_tokens']}")
        return no_code_summary

    (workspace / "retry.c").write_text(code, encoding="utf-8")

    g = grade_workspace(workspace)
    cite = check_cited_rationale(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}  "
          f"compile_failed={g.get('compile_failed', False)}  "
          f"cited={cite['cited']} matched={cite['matched']}")

    summary = {
        "phase": "M_crosssession_c_smoke",
        "scenario": "S1",
        "cell": cell,
        "run_id": run_id,
        "passed": g["passed"],
        "total": g["total"],
        "pass_rate": g["passed"] / g["total"] if g["total"] else 0.0,
        "compile_failed": g.get("compile_failed", False),
        "cited_rationale": cite["cited"],
        "rationale_keyphrases_matched": cite["matched"],
        "rationale_len": len(RATIONALE) if cell == "on-rule+rat"
                          else (len(PLACEBO) if cell == "on-rule+placebo"
                                else 0),
        "input_tokens": llm["input_tokens"],
        "output_tokens": llm["output_tokens"],
        "model": model,
        "llm_elapsed_s": round(llm["elapsed_s"], 1),
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "grade_stdout_tail": g["stdout_tail"],
    }

    cell_slug = cell.replace("+", "_").replace("-", "_")
    out_path = OUT_DIR / f"phM_s1_c_{cell_slug}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']}  "
          f"cited={cite['cited']}  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: phM_crosssession_c_smoke.py <cell> [run_id]")
        print("  cell ∈ off, on-rule, on-rule+placebo, on-rule+rat")
        return 1
    cell = argv[1]
    run_id = argv[2] if len(argv) > 2 else "smoke"
    if cell not in ("off", "on-rule", "on-rule+placebo", "on-rule+rat"):
        print(f"unknown cell: {cell}", file=sys.stderr)
        return 1
    run_one(cell, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
