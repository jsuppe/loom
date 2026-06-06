#!/usr/bin/env python3
"""M28 — C++ S1 with ClangdIndexer providing real LSP semantic context.

Near-byte-identical clone of
``experiments/bakeoff/v2_driver/phL2_crosssession_cpp_stub_indexer_smoke.py``.
The ONLY structural deviation is the indexer swap:

   StubCppIndexer(returns hand-curated literal) -> ClangdIndexer(real LSP)

plus the runtime substitution of ``${SCENARIO_DIR}`` in
``compile_commands.json`` (since clangd can't expand placeholders).

Pre-registration anchor:
    experiments/m28_clangd_indexer/PRE_REGISTRATION.md

Locked hypotheses:
    H1 (primary)    rat cell pass rate 30-50% (vs M10.2 stub's 40%)
    H2 (secondary)  placebo cell pass rate >= 40%
    H3 (STOP gate)  off cell pass rate <= 20% (over-firing trip)

Locked harness deltas vs phL2:
    * indexer: ClangdIndexer(root=SCENARIO_DIR)
    * compile_commands.json: substituted at run start, restored at end
    * output naming: m28_s1_cpp_* (separate from M10.2's phL2_s1_cpp_*)
    * N: 10 per cell (vs 5 in M10.2) -- tighter Wilson 95% CIs

KNOWN PRE-REG DRIFT (captured as REQ-ec63fa50 in the loom store):
    The pre-reg PRE_REGISTRATION.md locks Temperature=0.0. The phL2
    baseline doesn't set a temperature -- it uses Ollama's default
    (~0.7-0.8). M10.2's within-cell variance (1/5, 2/5, 3/5)
    confirms non-zero effective temp was in play. To stay
    apples-to-apples with the locked M10.2 baseline, M28 also does
    not set temperature. The drift is documented + acknowledged
    rather than silently corrected.
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
from typing import Optional

LOOM_DIR = Path(__file__).resolve().parents[2]
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"
SCENARIO_DIR = (BAKEOFF_DIR / "benchmarks" / "crosssession_cpp"
                / "s1_swallow_runtime_error")
OUT_DIR = BAKEOFF_DIR / "runs-m28"
OUT_DIR.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom import indexers  # noqa: E402
from loom.indexers_cpp import ClangdIndexer  # noqa: E402


# ---------------------------------------------------------------------------
# Scenario config -- VERBATIM from phL2 (must not drift)
# ---------------------------------------------------------------------------

TASK = (
    "The retry loop in retry.hpp swallows network errors silently. "
    "That looks like a bug -- callers can't tell what failed when "
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
    "directly from fetchWithRetry breaks the wrapper contract -- "
    "production incident 2024-09-12 lost three hours while ops "
    "chased a propagation bug that was actually working as "
    "intended. The current swallow-and-return-nullopt behavior is "
    "load-bearing for the BackoffError wrapper above us."
)

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
        base += (" The compliance pattern is requirement-applies; "
                 "non-compliance is requirement-does-not-apply.")
    return base[:PLACEBO_TARGET_LEN].rstrip() + "."


PLACEBO = make_placebo()


# ---------------------------------------------------------------------------
# ClangdIndexer registration + compile_commands.json substitution
# ---------------------------------------------------------------------------

_CDB_TEMPLATE: Optional[str] = None
_CDB_PATH = SCENARIO_DIR / "compile_commands.json"


def _resolve_compile_db() -> None:
    """Substitute ${SCENARIO_DIR} placeholders so clangd can consume."""
    global _CDB_TEMPLATE
    _CDB_TEMPLATE = _CDB_PATH.read_text(encoding="utf-8")
    resolved = _CDB_TEMPLATE.replace("${SCENARIO_DIR}",
                                      SCENARIO_DIR.as_posix())
    _CDB_PATH.write_text(resolved, encoding="utf-8")


def _restore_compile_db() -> None:
    """Re-write the templated form so the committed file stays portable."""
    if _CDB_TEMPLATE is not None:
        _CDB_PATH.write_text(_CDB_TEMPLATE, encoding="utf-8")


# Register the indexer once. ClangdIndexer is keyed on c++/cpp.
_CLANGD_INDEXER: Optional[ClangdIndexer] = None


def _get_indexer() -> ClangdIndexer:
    global _CLANGD_INDEXER
    if _CLANGD_INDEXER is None:
        _CLANGD_INDEXER = ClangdIndexer(root=SCENARIO_DIR)
        indexers.register(_CLANGD_INDEXER)
    return _CLANGD_INDEXER


# ---------------------------------------------------------------------------
# Direct Ollama call (verbatim from phL2 -- no temp, no seed, see module
# docstring's known pre-reg drift note)
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/generate"


def call_ollama(model: str, prompt: str, timeout: int = 600) -> dict:
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")
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
# Prompt construction -- verbatim from phL2, only indexer is swapped
# ---------------------------------------------------------------------------

def build_prompt(cell: str, target_file_content: str,
                 target_file: Path) -> tuple[str, int]:
    """Returns (prompt_text, semantic_block_chars)."""
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

    indexer = _get_indexer()
    semantic_block = indexer.context_for(target_file)
    semantic_chars = len(semantic_block)
    if semantic_block:
        parts.append("## Semantic context\n")
        parts.append("```cpp")
        parts.append(semantic_block.rstrip())
        parts.append("```\n")

    parts.append("## Source context\n")
    parts.append("### retry.hpp")
    parts.append("```cpp")
    parts.append(target_file_content)
    parts.append("```\n")

    parts.append("## Output contract")
    parts.append(
        "Reply with ONE C++ code block (```cpp ... ```) containing the "
        "**entire new file content** for `retry.hpp`. You MUST include all "
        "existing code you want to keep -- this file will be OVERWRITTEN "
        "with your output. Do not include prose outside the code block."
    )
    return "\n".join(parts), semantic_chars


def extract_cpp_code(response: str) -> str | None:
    for fence in ("cpp", "c++", "C++"):
        m = re.search(rf"```{re.escape(fence)}\s*\n(.*?)\n```",
                       response, re.DOTALL)
        if m:
            return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)\n```", response, re.DOTALL)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Workspace + grading -- verbatim from phL2
# ---------------------------------------------------------------------------

def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="m28_s1_cpp_"))
    shutil.copy(SCENARIO_DIR / "reference" / "retry.hpp", ws / "retry.hpp")
    return ws


def grade_workspace(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="m28_grade_s1_"))
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
    return {
        "passed": 0, "total": 2,
        "compile_failed": False,
        "stdout_tail": out[-1500:],
    }


RATIONALE_KEYPHRASES = ["wrapper", "BackoffError", "incident", "load-bearing"]


def check_cited_rationale(workspace: Path) -> dict:
    target = workspace / "retry.hpp"
    if not target.exists():
        return {"cited": False, "matched": []}
    text = target.read_text(encoding="utf-8")
    matched = [kp for kp in RATIONALE_KEYPHRASES
               if kp.lower() in text.lower()]
    return {"cited": bool(matched), "matched": matched}


# ---------------------------------------------------------------------------
# Run wrapper
# ---------------------------------------------------------------------------

def run_one(cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] cell={cell} workspace={workspace}")

    target_path = workspace / "retry.hpp"
    target_content = target_path.read_text(encoding="utf-8")
    prompt, semantic_chars = build_prompt(cell, target_content, target_path)
    print(f"[prompt] {len(prompt)} chars (semantic block adds "
          f"{semantic_chars} chars)")

    model = os.environ.get("M28_EXEC_MODEL", "qwen2.5-coder:32b")
    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        err_summary = {
            "phase": "M28_clangd_indexer",
            "scenario": "S1",
            "cell": cell,
            "run_id": run_id,
            "passed": 0, "total": 2,
            "error": f"ollama call failed: {e}",
            "wall_s": round(time.time() - t0, 1),
            "indexer": "clangd",
            "semantic_context_chars": semantic_chars,
        }
        cell_slug = cell.replace("+", "_").replace("-", "_")
        out_path = OUT_DIR / f"m28_s1_cpp_{cell_slug}_run{run_id}_summary.json"
        out_path.write_text(json.dumps(err_summary, indent=2),
                             encoding="utf-8")
        print(f"SUMMARY: {cell} ERROR: {e}")
        return err_summary
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} "
          f"out={llm['output_tokens']}")

    code = extract_cpp_code(llm["response"])
    if code is None:
        no_code_summary = {
            "phase": "M28_clangd_indexer",
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
            "indexer": "clangd",
            "semantic_context_chars": semantic_chars,
            "response_tail": llm["response"][-1500:],
            "wall_s": round(time.time() - t0, 1),
        }
        cell_slug = cell.replace("+", "_").replace("-", "_")
        out_path = OUT_DIR / f"m28_s1_cpp_{cell_slug}_run{run_id}_summary.json"
        out_path.write_text(json.dumps(no_code_summary, indent=2),
                             encoding="utf-8")
        print(f"SUMMARY: {cell} no_code_extracted "
              f"out_tokens={llm['output_tokens']}")
        return no_code_summary

    (workspace / "retry.hpp").write_text(code, encoding="utf-8")

    g = grade_workspace(workspace)
    cite = check_cited_rationale(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}  "
          f"compile_failed={g.get('compile_failed', False)}  "
          f"cited={cite['cited']} matched={cite['matched']}")

    summary = {
        "phase": "M28_clangd_indexer",
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
        "indexer": "clangd",
        "semantic_context_chars": semantic_chars,
        "llm_elapsed_s": round(llm["elapsed_s"], 1),
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "grade_stdout_tail": g["stdout_tail"],
    }

    cell_slug = cell.replace("+", "_").replace("-", "_")
    out_path = OUT_DIR / f"m28_s1_cpp_{cell_slug}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']}  "
          f"cited={cite['cited']}  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def run_sweep(cells: list[str], n_per_cell: int) -> dict:
    """Drive the pre-registered N=10 per cell sweep."""
    results = []
    for cell in cells:
        for i in range(1, n_per_cell + 1):
            run_id = str(i)
            print(f"\n===== {cell} run {i}/{n_per_cell} =====")
            summary = run_one(cell, run_id)
            results.append(summary)
    return {"runs": results, "n_per_cell": n_per_cell, "cells": cells}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

CELLS = ("off", "on-rule", "on-rule+placebo", "on-rule+rat")


def main(argv: list[str]) -> int:
    _resolve_compile_db()
    try:
        if len(argv) >= 2 and argv[1] == "--sweep":
            n = 10
            for i, a in enumerate(argv[2:]):
                if a == "--n" and i + 1 < len(argv[2:]):
                    n = int(argv[2 + i + 1])
            run_sweep(list(CELLS), n)
            return 0
        if len(argv) < 2:
            print("usage:")
            print("  m28_clangd_smoke.py <cell> [run_id]   # single trial")
            print("  m28_clangd_smoke.py --sweep [--n N]   # batch (default N=10)")
            print(f"  cells: {', '.join(CELLS)}")
            return 1
        cell = argv[1]
        run_id = argv[2] if len(argv) > 2 else "smoke"
        if cell not in CELLS:
            print(f"unknown cell: {cell}", file=sys.stderr)
            return 1
        run_one(cell, run_id)
        return 0
    finally:
        _restore_compile_db()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
