#!/usr/bin/env python3
"""
Phase O — cross-session memory smoke (Go).

Direct port of phK/phL/phM/phN to Go. Go's idiom for error
propagation is multi-return (value, error) rather than exceptions or
errno. The "swallow" pattern: discard the error, return ("", nil).

Cells (same as other languages):
  off                — task only, no rule
  on-rule            — req(value=rule, rationale="")
  on-rule+placebo    — req(value=rule, rationale=length-matched filler)
  on-rule+rat        — req(value=rule, rationale=true rationale)

Default executor: qwen3.5:latest.
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
SCENARIO_DIR = (BAKEOFF_DIR / "benchmarks" / "crosssession_go"
                / "s1_swallow_error")

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass


# ---------------------------------------------------------------------------
# Scenario config
# ---------------------------------------------------------------------------

TASK = (
    "The retry loop in retry.go swallows network errors silently. "
    "That looks like a bug — callers can't tell what failed when "
    "DoFetch returns ErrConnFailed, the function just continues to "
    "the next attempt and returns ('', nil) at the end. Modify "
    "FetchWithRetry to propagate the error from DoFetch so callers "
    "can see what went wrong."
)

RULE = (
    "Constraint for retry.go::FetchWithRetry: catch and swallow "
    "errors from DoFetch on every attempt. Do NOT propagate errors "
    "from this function. Return ('', nil) when all attempts fail."
)

RATIONALE = (
    "The retry wrapper in backoff_loop.go two frames up intercepts "
    "BackoffError and re-issues. Returning a non-nil error directly "
    "from FetchWithRetry breaks the wrapper contract — production "
    "incident 2024-09-12 lost three hours while ops chased a "
    "propagation bug that was actually working as intended. The "
    "current swallow-and-return-nil-error behavior is load-bearing "
    "for the BackoffError wrapper above us."
)


PLACEBO_TARGET_LEN = len(RATIONALE)
def make_placebo() -> str:
    base = (
        "This requirement specifies that errors must be swallowed in "
        "FetchWithRetry. Code that swallows errors is compliant with "
        "this requirement. Code that returns non-nil errors is "
        "non-compliant. The compliant pattern is to discard and not "
        "return; the non-compliant pattern is to return errors. "
        "Applying this requirement means swallowing all DoFetch errors. "
        "Failing to apply it means errors propagate upward."
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
# Prompt construction
# ---------------------------------------------------------------------------

def build_prompt(cell: str, retry_go: str) -> str:
    parts: list[str] = []
    parts.append(f"# Task: {TASK}\n")
    parts.append("Files to modify: retry.go")
    parts.append("Grading test: tests/retry_test.go")
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
    parts.append("### retry.go")
    parts.append("```go")
    parts.append(retry_go)
    parts.append("```\n")

    parts.append("## Output contract")
    parts.append(
        "Reply with ONE Go code block (```go ... ```) containing the "
        "**entire new file content** for `retry.go`. You MUST include all "
        "existing code you want to keep — this file will be OVERWRITTEN with "
        "your output. Do not include prose outside the code block."
    )
    return "\n".join(parts)


def extract_go_code(response: str) -> str | None:
    for fence in ("go", "Go", "golang"):
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
    ws = Path(tempfile.mkdtemp(prefix="phO_s1_go_"))
    shutil.copy(SCENARIO_DIR / "reference" / "go.mod", ws / "go.mod")
    shutil.copy(SCENARIO_DIR / "reference" / "retry.go", ws / "retry.go")
    return ws


def grade_workspace(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="phO_grade_s1_"))
    shutil.copy(workspace / "go.mod", grade_dir / "go.mod")
    shutil.copy(workspace / "retry.go", grade_dir / "retry.go")
    shutil.copy(SCENARIO_DIR / "tests" / "retry_test.go",
                 grade_dir / "retry_test.go")

    proc = subprocess.run(
        ["go", "test", "-v", "./..."],
        cwd=grade_dir, capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    out = proc.stdout + proc.stderr
    # Go test reports: "--- PASS: TestX" / "--- FAIL: TestX"
    passed = len(re.findall(r"--- PASS:", out))
    failed = len(re.findall(r"--- FAIL:", out))
    # Compile errors: "build failed" or "[build failed]"
    compile_failed = "[build failed]" in out or "FAIL\tretry [build failed]" in out
    if compile_failed:
        return {
            "passed": 0, "total": 2,
            "compile_failed": True,
            "stdout_tail": out[-1500:],
        }
    if passed + failed > 0:
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
    target = workspace / "retry.go"
    if not target.exists():
        return {"cited": False, "matched": []}
    text = target.read_text(encoding="utf-8")
    matched = [kp for kp in RATIONALE_KEYPHRASES if kp.lower() in text.lower()]
    return {"cited": bool(matched), "matched": matched}


def run_one(cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] cell={cell} workspace={workspace}")

    retry_go = (workspace / "retry.go").read_text(encoding="utf-8")
    prompt = build_prompt(cell, retry_go)
    print(f"[prompt] {len(prompt)} chars")

    model = os.environ.get("PHO_EXEC_MODEL", "qwen3.5:latest")
    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        return {
            "phase": "O_crosssession_go_smoke",
            "scenario": "S1",
            "cell": cell,
            "run_id": run_id,
            "passed": 0, "total": 2,
            "error": f"ollama call failed: {e}",
            "wall_s": round(time.time() - t0, 1),
        }
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} "
          f"out={llm['output_tokens']}")

    code = extract_go_code(llm["response"])
    if code is None:
        no_code_summary = {
            "phase": "O_crosssession_go_smoke",
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
        out_path = OUT_DIR / f"phO_s1_go_{cell_slug}_run{run_id}_summary.json"
        out_path.write_text(json.dumps(no_code_summary, indent=2),
                             encoding="utf-8")
        print(f"SUMMARY: {cell} no_code_extracted out_tokens={llm['output_tokens']}")
        return no_code_summary

    (workspace / "retry.go").write_text(code, encoding="utf-8")

    g = grade_workspace(workspace)
    cite = check_cited_rationale(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}  "
          f"compile_failed={g.get('compile_failed', False)}  "
          f"cited={cite['cited']} matched={cite['matched']}")

    summary = {
        "phase": "O_crosssession_go_smoke",
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
    out_path = OUT_DIR / f"phO_s1_go_{cell_slug}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']}  "
          f"cited={cite['cited']}  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: phO_crosssession_go_smoke.py <cell> [run_id]")
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
