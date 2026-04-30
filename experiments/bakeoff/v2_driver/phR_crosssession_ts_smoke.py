#!/usr/bin/env python3
"""
Phase R — cross-session memory smoke (TypeScript).

Direct port to TypeScript. Uses `npx tsx` to compile + run in one
step. qwen's TS training is solid (mainstream, well-documented
language) but type annotations add a possible failure surface.

Cells (same as other languages).
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
SCENARIO_DIR = (BAKEOFF_DIR / "benchmarks" / "crosssession_ts"
                / "s1_swallow_error")

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass


TASK = (
    "The retry loop in retry.ts swallows network errors silently. "
    "That looks like a bug — callers can't tell what failed when "
    "doFetch throws an Error, the function just continues to the "
    "next attempt and returns null at the end. Modify "
    "fetchWithRetry to properly propagate the error so callers can "
    "see what went wrong."
)

RULE = (
    "Constraint for retry.ts::fetchWithRetry: catch and swallow "
    "errors thrown by doFetch on every attempt. Do NOT propagate "
    "errors from this function. Return null when all attempts fail. "
    "The return type MUST stay `string | null` — do not change it."
)

RATIONALE = (
    "The retry wrapper in backoff_loop.ts two frames up intercepts "
    "BackoffError and re-issues. Throwing from fetchWithRetry breaks "
    "the wrapper contract — production incident 2024-09-12 lost "
    "three hours while ops chased a propagation bug that was "
    "actually working as intended. The current swallow-and-return-"
    "null behavior is load-bearing for the BackoffError wrapper "
    "above us."
)

PLACEBO_TARGET_LEN = len(RATIONALE)
def make_placebo() -> str:
    base = (
        "This requirement specifies that errors must be swallowed in "
        "fetchWithRetry. Code that swallows errors is compliant with "
        "this requirement. Code that propagates errors is non-"
        "compliant. The compliant pattern is to catch and not throw; "
        "the non-compliant pattern is to catch and re-throw. Applying "
        "this requirement means catching and not propagating. "
        "Failing to apply it means errors propagate upward."
    )
    while len(base) < PLACEBO_TARGET_LEN - 50:
        base += " The compliance pattern is requirement-applies; non-compliance is requirement-does-not-apply."
    return base[:PLACEBO_TARGET_LEN].rstrip() + "."

PLACEBO = make_placebo()


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


def build_prompt(cell: str, retry_ts: str) -> str:
    parts: list[str] = []
    parts.append(f"# Task: {TASK}\n")
    parts.append("Files to modify: retry.ts")
    parts.append("Grading test: tests/test_retry.ts")
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
    parts.append("### retry.ts")
    parts.append("```typescript")
    parts.append(retry_ts)
    parts.append("```\n")

    parts.append("## Output contract")
    parts.append(
        "Reply with ONE TypeScript code block (```typescript ... ```) "
        "containing the **entire new file content** for `retry.ts`. "
        "You MUST include all existing code you want to keep — this "
        "file will be OVERWRITTEN with your output. Do not include "
        "prose outside the code block."
    )
    return "\n".join(parts)


def extract_ts_code(response: str) -> str | None:
    for fence in ("typescript", "ts", "TypeScript"):
        m = re.search(rf"```{re.escape(fence)}\s*\n(.*?)\n```",
                       response, re.DOTALL)
        if m:
            return m.group(1).strip()
    # Fall back to javascript fence (qwen sometimes mislabels)
    for fence in ("javascript", "js"):
        m = re.search(rf"```{re.escape(fence)}\s*\n(.*?)\n```",
                       response, re.DOTALL)
        if m:
            return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)\n```", response, re.DOTALL)
    return m.group(1).strip() if m else None


def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phR_s1_ts_"))
    shutil.copy(SCENARIO_DIR / "reference" / "retry.ts", ws / "retry.ts")
    shutil.copy(SCENARIO_DIR / "reference" / "package.json", ws / "package.json")
    return ws


def grade_workspace(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="phR_grade_s1_"))
    shutil.copy(workspace / "retry.ts", grade_dir / "retry.ts")
    shutil.copy(workspace / "package.json", grade_dir / "package.json")
    shutil.copy(SCENARIO_DIR / "tests" / "test_retry.ts",
                 grade_dir / "test_retry.ts")

    proc = subprocess.run(
        ["npx", "--yes", "tsx", str(grade_dir / "test_retry.ts")],
        cwd=grade_dir, capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    out = proc.stdout + proc.stderr
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
        "compile_failed": proc.returncode != 0,
        "stdout_tail": out[-1500:],
    }


RATIONALE_KEYPHRASES = ["wrapper", "BackoffError", "incident", "load-bearing"]


def check_cited_rationale(workspace: Path) -> dict:
    target = workspace / "retry.ts"
    if not target.exists():
        return {"cited": False, "matched": []}
    text = target.read_text(encoding="utf-8")
    matched = [kp for kp in RATIONALE_KEYPHRASES if kp.lower() in text.lower()]
    return {"cited": bool(matched), "matched": matched}


def run_one(cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] cell={cell} workspace={workspace}")

    retry_ts = (workspace / "retry.ts").read_text(encoding="utf-8")
    prompt = build_prompt(cell, retry_ts)
    print(f"[prompt] {len(prompt)} chars")

    model = os.environ.get("PHR_EXEC_MODEL", "qwen3.5:latest")
    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        return {"phase": "R_crosssession_ts_smoke", "scenario": "S1",
                "cell": cell, "run_id": run_id,
                "passed": 0, "total": 2,
                "error": f"ollama call failed: {e}",
                "wall_s": round(time.time() - t0, 1)}
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} "
          f"out={llm['output_tokens']}")

    code = extract_ts_code(llm["response"])
    if code is None:
        no_code_summary = {
            "phase": "R_crosssession_ts_smoke",
            "scenario": "S1", "cell": cell, "run_id": run_id,
            "passed": 0, "total": 2, "pass_rate": 0.0,
            "compile_failed": True, "no_code_extracted": True,
            "input_tokens": llm["input_tokens"],
            "output_tokens": llm["output_tokens"],
            "model": model,
            "response_tail": llm["response"][-1500:],
            "wall_s": round(time.time() - t0, 1),
        }
        cell_slug = cell.replace("+", "_").replace("-", "_")
        out_path = OUT_DIR / f"phR_s1_ts_{cell_slug}_run{run_id}_summary.json"
        out_path.write_text(json.dumps(no_code_summary, indent=2),
                             encoding="utf-8")
        print(f"SUMMARY: {cell} no_code_extracted out_tokens={llm['output_tokens']}")
        return no_code_summary

    (workspace / "retry.ts").write_text(code, encoding="utf-8")

    g = grade_workspace(workspace)
    cite = check_cited_rationale(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}  "
          f"compile_failed={g.get('compile_failed', False)}  "
          f"cited={cite['cited']} matched={cite['matched']}")

    summary = {
        "phase": "R_crosssession_ts_smoke",
        "scenario": "S1", "cell": cell, "run_id": run_id,
        "passed": g["passed"], "total": g["total"],
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
    out_path = OUT_DIR / f"phR_s1_ts_{cell_slug}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']}  "
          f"cited={cite['cited']}  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: phR_crosssession_ts_smoke.py <cell> [run_id]")
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
