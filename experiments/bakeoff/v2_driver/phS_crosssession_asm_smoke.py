#!/usr/bin/env python3
"""
Phase S — cross-session memory smoke (Assembly / NASM x86-64).

Extreme-low-fluency probe. Tests whether qwen3.5 can produce valid
NASM x86-64 (Windows ABI) at all, and whether structured rule
context shifts behavior when the executor is at the bottom of the
language-fluency spectrum.

The "swallow vs propagate" S1 idiom in asm: fetch_with_retry must
return 0 (the swallow) when all attempts fail. Returning -1 (or any
non-zero) propagates the error.

Cells (same as other languages).
Default executor: qwen3.5:latest.
Build: nasm -f win64 retry.asm -o retry.obj && gcc test.c retry.obj.
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
SCENARIO_DIR = (BAKEOFF_DIR / "benchmarks" / "crosssession_asm"
                / "s1_swallow_error")

NASM = r"C:\Users\jonsu\local\nasm\nasm-2.16.03\nasm.exe"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass


TASK = (
    "The retry loop in retry.asm hides errors silently — when "
    "do_fetch returns -1 (the failure indicator) on every attempt, "
    "fetch_with_retry returns 0 instead of propagating the -1 to "
    "the caller. That looks like a bug. Modify fetch_with_retry to "
    "return -1 (or the last failure code from do_fetch) so callers "
    "can tell when the operation actually failed."
)

RULE = (
    "Constraint for retry.asm::fetch_with_retry: when all "
    "attempts fail, MUST return 0 in rax (the swallow). Do NOT "
    "propagate the -1 from do_fetch. Callers expect 0 on overall "
    "failure, not -1. Preserve the existing swallow-and-return-zero "
    "behavior."
)

RATIONALE = (
    "The retry caller in backoff_loop.asm one frame up checks rax "
    "for non-zero to detect success, and uses a separate side "
    "channel for error propagation. If fetch_with_retry returns -1 "
    "directly, the wrapper interprets that as success and re-issues "
    "indefinitely — production incident 2024-09-12 lost three hours "
    "while the wrapper looped. The current return-zero-on-failure "
    "behavior is load-bearing for the BackoffError wrapper above us."
)


PLACEBO_TARGET_LEN = len(RATIONALE)
def make_placebo() -> str:
    base = (
        "This requirement specifies that fetch_with_retry must "
        "return 0 on overall failure. Code that returns 0 is "
        "compliant with this requirement. Code that returns -1 is "
        "non-compliant. The compliant pattern is to set rax to 0 "
        "before ret; the non-compliant pattern is to leave rax "
        "as -1. Applying this requirement means zeroing rax before "
        "the final ret. Failing to apply it means propagating -1."
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


def build_prompt(cell: str, retry_asm: str) -> str:
    parts: list[str] = []
    parts.append(f"# Task: {TASK}\n")
    parts.append("Files to modify: retry.asm")
    parts.append("Grading test: tests/test_retry.c (links + calls fetch_with_retry)")
    parts.append("Build: nasm -f win64 retry.asm -o retry.obj && gcc test_retry.c retry.obj -o test_runner.exe")
    parts.append("Calling convention: Windows x64 (RCX = first arg, RAX = return)")
    parts.append("Size budget: <= 1 file, <= 100 lines\n")

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
    parts.append("### retry.asm (NASM x86-64 syntax)")
    parts.append("```nasm")
    parts.append(retry_asm)
    parts.append("```\n")

    parts.append("## Output contract")
    parts.append(
        "Reply with ONE NASM x86-64 code block (```nasm ... ```) "
        "containing the **entire new file content** for `retry.asm`. "
        "Use NASM syntax (not GAS / AT&T). Use Windows x64 calling "
        "convention (RCX/RDX/R8/R9 for args, RAX for return, 32-byte "
        "shadow space). Include `bits 64`, `default rel`, the global "
        "symbol declarations, and the section directive. You MUST "
        "include all existing code you want to keep — this file will "
        "be OVERWRITTEN with your output. Do not include prose "
        "outside the code block."
    )
    return "\n".join(parts)


def extract_asm_code(response: str) -> str | None:
    for fence in ("nasm", "asm", "x86", "assembly", "x86_64"):
        m = re.search(rf"```{re.escape(fence)}\s*\n(.*?)\n```",
                       response, re.DOTALL)
        if m:
            return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)\n```", response, re.DOTALL)
    return m.group(1).strip() if m else None


def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phS_s1_asm_"))
    shutil.copy(SCENARIO_DIR / "reference" / "retry.asm", ws / "retry.asm")
    return ws


def grade_workspace(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="phS_grade_s1_"))
    shutil.copy(workspace / "retry.asm", grade_dir / "retry.asm")
    shutil.copy(SCENARIO_DIR / "tests" / "test_retry.c",
                 grade_dir / "test_retry.c")

    nasm_proc = subprocess.run(
        [NASM, "-f", "win64",
         str(grade_dir / "retry.asm"),
         "-o", str(grade_dir / "retry.obj")],
        capture_output=True, text=True, timeout=30,
        encoding="utf-8", errors="replace",
    )
    if nasm_proc.returncode != 0:
        return {
            "passed": 0, "total": 2,
            "compile_failed": True,
            "compile_stage": "nasm",
            "stdout_tail": (nasm_proc.stdout + nasm_proc.stderr)[-1500:],
        }

    gcc_proc = subprocess.run(
        ["gcc", str(grade_dir / "test_retry.c"),
         str(grade_dir / "retry.obj"),
         "-o", str(grade_dir / "test_runner.exe")],
        capture_output=True, text=True, timeout=30,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    if gcc_proc.returncode != 0:
        return {
            "passed": 0, "total": 2,
            "compile_failed": True,
            "compile_stage": "link",
            "stdout_tail": (gcc_proc.stdout + gcc_proc.stderr)[-1500:],
        }

    run_proc = subprocess.run(
        [str(grade_dir / "test_runner.exe")],
        capture_output=True, text=True, timeout=10,
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


RATIONALE_KEYPHRASES = ["wrapper", "BackoffError", "incident", "load-bearing"]


def check_cited_rationale(workspace: Path) -> dict:
    target = workspace / "retry.asm"
    if not target.exists():
        return {"cited": False, "matched": []}
    text = target.read_text(encoding="utf-8")
    matched = [kp for kp in RATIONALE_KEYPHRASES if kp.lower() in text.lower()]
    return {"cited": bool(matched), "matched": matched}


def run_one(cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] cell={cell} workspace={workspace}")

    retry_asm = (workspace / "retry.asm").read_text(encoding="utf-8")
    prompt = build_prompt(cell, retry_asm)
    print(f"[prompt] {len(prompt)} chars")

    model = os.environ.get("PHS_EXEC_MODEL", "qwen3.5:latest")
    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        return {"phase": "S_crosssession_asm_smoke", "scenario": "S1",
                "cell": cell, "run_id": run_id,
                "passed": 0, "total": 2,
                "error": f"ollama call failed: {e}",
                "wall_s": round(time.time() - t0, 1)}
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} "
          f"out={llm['output_tokens']}")

    code = extract_asm_code(llm["response"])
    if code is None:
        no_code_summary = {
            "phase": "S_crosssession_asm_smoke",
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
        out_path = OUT_DIR / f"phS_s1_asm_{cell_slug}_run{run_id}_summary.json"
        out_path.write_text(json.dumps(no_code_summary, indent=2),
                             encoding="utf-8")
        print(f"SUMMARY: {cell} no_code_extracted out_tokens={llm['output_tokens']}")
        return no_code_summary

    (workspace / "retry.asm").write_text(code, encoding="utf-8")

    g = grade_workspace(workspace)
    cite = check_cited_rationale(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}  "
          f"compile_failed={g.get('compile_failed', False)} "
          f"stage={g.get('compile_stage', '')}  "
          f"cited={cite['cited']} matched={cite['matched']}")

    summary = {
        "phase": "S_crosssession_asm_smoke",
        "scenario": "S1", "cell": cell, "run_id": run_id,
        "passed": g["passed"], "total": g["total"],
        "pass_rate": g["passed"] / g["total"] if g["total"] else 0.0,
        "compile_failed": g.get("compile_failed", False),
        "compile_stage": g.get("compile_stage", ""),
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
    out_path = OUT_DIR / f"phS_s1_asm_{cell_slug}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']}  "
          f"cited={cite['cited']}  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: phS_crosssession_asm_smoke.py <cell> [run_id]")
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
