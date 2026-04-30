#!/usr/bin/env python3
"""
Phase L — cross-session memory smoke (C++).

Direct port of phK to C++. Tests whether the rule-vs-rationale flatness
observed in Python (phK) holds when qwen is operating in a less-friendly
language. Same scenario shape, same 4-cell harness, same N=5.

Differs from phK in two ways:
  1. Bypasses loom_exec — calls Ollama directly with a prompt that
     mirrors task_build_prompt's format. The reason: loom_exec doesn't
     have a C++ runner, and the experiment doesn't actually need
     loom_exec — the question is "does qwen produce code that satisfies
     the constraint when given a stored rule." We can construct that
     prompt directly without the dispatch infrastructure.
  2. Compiles + runs the test executable to grade (g++ + ./exe).

Cells (same as phK):
  off                — task only, no rule
  on-rule            — req(value=rule, rationale="")
  on-rule+placebo    — req(value=rule, rationale=length-matched filler)
  on-rule+rat        — req(value=rule, rationale=true rationale)

Default executor: qwen3.5:latest. Same as phK for clean Python<->C++
comparison (NOT qwen2.5-coder:32b, even though it would do better on
C++ syntax — we want the same model under same conditions).
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
SCENARIO_DIR = (BAKEOFF_DIR / "benchmarks" / "crosssession_cpp"
                / "s1_swallow_runtime_error")

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass


# ---------------------------------------------------------------------------
# Scenario config — fixed text, mirrors phK S1
# ---------------------------------------------------------------------------

TASK = (
    "The retry loop in retry.hpp swallows network errors silently. "
    "That looks like a bug — callers can't tell what failed when "
    "doFetch throws std::runtime_error, the function just continues "
    "to the next attempt. Modify fetchWithRetry to properly propagate "
    "std::runtime_error so callers can see what went wrong."
)

RULE = (
    "Constraint for retry.hpp::fetchWithRetry: catch and swallow "
    "std::runtime_error on every attempt. Do NOT propagate "
    "std::runtime_error from this function. Return std::nullopt "
    "when all attempts fail."
)

RATIONALE = (
    "The retry wrapper in backoff_loop.hpp two frames up intercepts "
    "BackoffError and re-issues. Throwing std::runtime_error "
    "directly from fetchWithRetry breaks the wrapper contract — "
    "production incident 2024-09-12 lost three hours while ops "
    "chased a propagation bug that was actually working as "
    "intended. The current swallow-and-return-nullopt behavior is "
    "load-bearing for the BackoffError wrapper above us."
)

# Length-matched placebo (verbosely restates the rule, no new info)
PLACEBO_TARGET_LEN = len(RATIONALE)
def make_placebo() -> str:
    base = (
        "This requirement specifies that std::runtime_error must be "
        "swallowed in fetchWithRetry. Code that swallows is compliant "
        "with this requirement. Code that propagates std::runtime_error "
        "is non-compliant. The compliant pattern is to catch and not "
        "throw; the non-compliant pattern is to catch and re-throw. "
        "Applying this requirement means catching and not propagating. "
        "Failing to apply it means std::runtime_error propagates upward."
    )
    while len(base) < PLACEBO_TARGET_LEN - 50:
        base += " The compliance pattern is requirement-applies; non-compliance is requirement-does-not-apply."
    return base[:PLACEBO_TARGET_LEN].rstrip() + "."

PLACEBO = make_placebo()


# ---------------------------------------------------------------------------
# Direct Ollama call (no loom_exec)
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/generate"


def call_ollama(model: str, prompt: str, timeout: int = 600) -> dict:
    """POST to Ollama's /api/generate. Returns {response, ...}."""
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
# Prompt construction — mirrors task_build_prompt's format
# ---------------------------------------------------------------------------

def build_prompt(cell: str, target_file_content: str) -> str:
    """Construct the executor prompt mirroring task_build_prompt's format.

    For ``off`` cell: just task title + file context, no req section.
    For other cells: include a ``## Requirements`` section with
    ``Value: <rule>`` and (if non-empty) ``Rationale: <text>``.
    """
    parts: list[str] = []
    parts.append(f"# Task: {TASK}\n")
    parts.append("Files to modify: retry.hpp")
    parts.append("Grading test: tests/test_retry.cpp")
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
    parts.append("### retry.hpp")
    parts.append("```cpp")
    parts.append(target_file_content)
    parts.append("```\n")

    parts.append("## Output contract")
    parts.append(
        "Reply with ONE C++ code block (```cpp ... ```) containing the "
        "**entire new file content** for `retry.hpp`. You MUST include all "
        "existing code you want to keep — this file will be OVERWRITTEN with "
        "your output. Do not include prose outside the code block."
    )
    return "\n".join(parts)


def extract_cpp_code(response: str) -> str | None:
    """Extract the first ```cpp ... ``` block (or ```c++ ... ```)."""
    for fence in ("cpp", "c++", "C++"):
        m = re.search(rf"```{re.escape(fence)}\s*\n(.*?)\n```",
                       response, re.DOTALL)
        if m:
            return m.group(1).strip()
    # Fall back: any fenced block.
    m = re.search(r"```\s*\n(.*?)\n```", response, re.DOTALL)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Workspace + grading
# ---------------------------------------------------------------------------

def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phL_s1_cpp_"))
    shutil.copy(SCENARIO_DIR / "reference" / "retry.hpp", ws / "retry.hpp")
    return ws


def grade_workspace(workspace: Path) -> dict:
    """Compile retry.hpp + the hidden test, run the binary, parse output."""
    grade_dir = Path(tempfile.mkdtemp(prefix="phL_grade_s1_"))
    shutil.copy(workspace / "retry.hpp", grade_dir / "retry.hpp")
    shutil.copy(SCENARIO_DIR / "tests" / "test_retry.cpp",
                 grade_dir / "test_retry.cpp")
    exe = grade_dir / "test_runner.exe"

    compile_proc = subprocess.run(
        ["g++", "-std=c++17", "-I", str(grade_dir),
         str(grade_dir / "test_retry.cpp"), "-o", str(exe)],
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
    # Couldn't parse — treat as failure
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
    target = workspace / "retry.hpp"
    if not target.exists():
        return {"cited": False, "matched": []}
    text = target.read_text(encoding="utf-8")
    matched = [kp for kp in RATIONALE_KEYPHRASES if kp.lower() in text.lower()]
    return {"cited": bool(matched), "matched": matched}


def run_one(cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] cell={cell} workspace={workspace}")

    target_content = (workspace / "retry.hpp").read_text(encoding="utf-8")
    prompt = build_prompt(cell, target_content)
    print(f"[prompt] {len(prompt)} chars")

    model = os.environ.get("PHL_EXEC_MODEL", "qwen3.5:latest")
    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        return {
            "phase": "L_crosssession_cpp_smoke",
            "scenario": "S1",
            "cell": cell,
            "run_id": run_id,
            "passed": 0, "total": 2,
            "error": f"ollama call failed: {e}",
            "wall_s": round(time.time() - t0, 1),
        }
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} "
          f"out={llm['output_tokens']}")

    code = extract_cpp_code(llm["response"])
    if code is None:
        # qwen produced no recognizable code — treat as fail.
        # Write the summary file so the trial isn't silently lost.
        no_code_summary = {
            "phase": "L_crosssession_cpp_smoke",
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
        out_path = OUT_DIR / f"phL_s1_cpp_{cell_slug}_run{run_id}_summary.json"
        out_path.write_text(json.dumps(no_code_summary, indent=2),
                             encoding="utf-8")
        print(f"SUMMARY: {cell} no_code_extracted out_tokens={llm['output_tokens']}")
        return no_code_summary

    # Write qwen's output back to retry.hpp
    (workspace / "retry.hpp").write_text(code, encoding="utf-8")

    g = grade_workspace(workspace)
    cite = check_cited_rationale(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}  "
          f"compile_failed={g.get('compile_failed', False)}  "
          f"cited={cite['cited']} matched={cite['matched']}")

    summary = {
        "phase": "L_crosssession_cpp_smoke",
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
    out_path = OUT_DIR / f"phL_s1_cpp_{cell_slug}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']}  "
          f"cited={cite['cited']}  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: phL_crosssession_cpp_smoke.py <cell> [run_id]")
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
