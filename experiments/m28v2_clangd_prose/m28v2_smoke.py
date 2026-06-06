#!/usr/bin/env python3
"""M28v2 — ClangdIndexer + LLM-summarized contract prose.

Near-byte-identical clone of m28_clangd_smoke.py with one structural
addition: a summarizer call at sweep start that generates a
contract-style prose summary of retry.hpp + ClangdIndexer's
structural facts, then appends it to the '## Semantic context' block
for every trial.

The summary is generated ONCE per sweep (file doesn't change between
trials) and cached. The locked summarizer prompt (see
PRE_REGISTRATION.md) is intentionally isolated from the rule and
task -- the H3 STOP gate is the guard against the summarizer
inferring the contract from source-code shape alone.

Pre-registration anchor:
    experiments/m28v2_clangd_prose/PRE_REGISTRATION.md

Locked hypotheses:
    H1 (primary)    rat cell >= 30% (M28 baseline + 30pp)
    H2 (secondary)  input tokens < 2000 per trial (efficiency floor)
    H3 (STOP gate)  off cell <= 20% (prose-leak protection)

Locked harness deltas vs m28_clangd_smoke.py:
    * summarizer call at sweep start (Ollama qwen2.5-coder:32b,
      fallback per user decision -- no ANTHROPIC_API_KEY set)
    * summary cached and reused across all 40 trials
    * appended to the Semantic context block (clangd output
      unchanged underneath)
    * output naming: m28v2_s1_cpp_*

Known pre-reg drift inherited from M28: temperature is NOT set (uses
Ollama defaults). Captured as REQ-ec63fa50.
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
OUT_DIR = BAKEOFF_DIR / "runs-m28v2"
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
# Scenario config -- VERBATIM from phL2/M28
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
# LOCKED SUMMARIZER PROMPT (M28v2 pre-reg artifact; edits require
# supersession audit per the methodology pattern REQ-3896db58)
# ---------------------------------------------------------------------------

SUMMARIZER_PROMPT_TEMPLATE = """\
You are reading a small C/C++ source file plus a structural-facts block extracted by an LSP indexer. Your job is to produce a brief "contract description" -- 4 to 8 sentences -- explaining what the function(s) in the file appear to do, what their callers seem to expect, and what would observably change if the function's behavior were different.

Rules:
- Do not speculate about bugs, fixes, or "should" statements.
- Do not recommend changes.
- Stay descriptive. Refer to the code that exists, the call sites in the structural facts, and the surrounding context.
- Write in plain prose, not bullet points.
- Keep it under 1000 characters.

# Source file
{source_file_content}

# Structural facts (from clangd)
{clangd_context}

# Contract description
"""


# ---------------------------------------------------------------------------
# compile_commands.json substitution (verbatim from M28)
# ---------------------------------------------------------------------------

_CDB_TEMPLATE: Optional[str] = None
_CDB_PATH = SCENARIO_DIR / "compile_commands.json"


def _resolve_compile_db() -> None:
    global _CDB_TEMPLATE
    _CDB_TEMPLATE = _CDB_PATH.read_text(encoding="utf-8")
    resolved = _CDB_TEMPLATE.replace("${SCENARIO_DIR}",
                                      SCENARIO_DIR.as_posix())
    _CDB_PATH.write_text(resolved, encoding="utf-8")


def _restore_compile_db() -> None:
    if _CDB_TEMPLATE is not None:
        _CDB_PATH.write_text(_CDB_TEMPLATE, encoding="utf-8")


_CLANGD_INDEXER: Optional[ClangdIndexer] = None


def _get_indexer() -> ClangdIndexer:
    global _CLANGD_INDEXER
    if _CLANGD_INDEXER is None:
        _CLANGD_INDEXER = ClangdIndexer(root=SCENARIO_DIR)
        indexers.register(_CLANGD_INDEXER)
    return _CLANGD_INDEXER


# ---------------------------------------------------------------------------
# Direct Ollama call (verbatim from M28)
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
# Summarizer (locked prompt, model selection per M11.5 dispatch pattern)
# ---------------------------------------------------------------------------

_CACHED_PROSE: Optional[dict] = None


def _resolve_summarizer_model() -> tuple[str, str]:
    """Return (model_id, provider). M11.5 dispatch pattern: Anthropic
    Haiku if key set; otherwise local qwen2.5-coder:32b with stderr
    warning (M28 F1 -- REQ-cc95b9a1)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ("claude-haiku-4-5", "anthropic")
    print(
        "[m28v2] WARNING: ANTHROPIC_API_KEY not set -- summarizer "
        "falls back to qwen2.5-coder:32b (same model as generator). "
        "This creates a self-reinforcement confound (accepted for "
        "v1 per the M28v2 pre-reg).",
        file=sys.stderr,
    )
    return ("qwen2.5-coder:32b", "ollama")


def _generate_prose_summary(source_file: Path, clangd_context: str) -> dict:
    """Build the summarizer prompt, call the resolved summarizer
    model, return the prose + metadata."""
    source = source_file.read_text(encoding="utf-8")
    prompt = SUMMARIZER_PROMPT_TEMPLATE.format(
        source_file_content=source,
        clangd_context=clangd_context,
    )
    model, provider = _resolve_summarizer_model()
    print(f"[summarizer] model={provider}:{model}  prompt={len(prompt)} chars")
    if provider == "ollama":
        result = call_ollama(model, prompt, timeout=300)
        prose = result["response"].strip()
        meta = {
            "model": f"{provider}:{model}",
            "elapsed_s": round(result["elapsed_s"], 1),
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
        }
    else:
        # Anthropic path -- not active in this run (no key set) but
        # left in place for the Phase 1.5 follow-up that would set
        # ANTHROPIC_API_KEY. We don't import anthropic to avoid the
        # dependency for the qwen-path run.
        raise NotImplementedError(
            "Anthropic summarizer path deferred to Phase 1.5"
        )
    print(f"[summarizer] elapsed={meta['elapsed_s']}s  "
          f"in={meta['input_tokens']}  out={meta['output_tokens']}  "
          f"prose={len(prose)} chars")
    return {"prose": prose, "meta": meta}


def _ensure_prose_cached(target_file: Path) -> dict:
    global _CACHED_PROSE
    if _CACHED_PROSE is not None:
        return _CACHED_PROSE
    indexer = _get_indexer()
    clangd_context = indexer.context_for(target_file)
    if not clangd_context:
        raise RuntimeError(
            "ClangdIndexer returned empty context; cannot summarize."
        )
    summary = _generate_prose_summary(target_file, clangd_context)
    _CACHED_PROSE = {
        "clangd_context": clangd_context,
        "prose": summary["prose"],
        "meta": summary["meta"],
    }
    return _CACHED_PROSE


# ---------------------------------------------------------------------------
# Prompt construction -- M28 layout + appended prose summary
# ---------------------------------------------------------------------------

def build_prompt(cell: str, target_file_content: str,
                 target_file: Path) -> tuple[str, dict]:
    """Returns (prompt_text, semantic_block_info)."""
    cached = _ensure_prose_cached(target_file)
    clangd_context = cached["clangd_context"]
    prose = cached["prose"]

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

    parts.append("## Semantic context\n")
    parts.append("```cpp")
    parts.append(clangd_context.rstrip())
    parts.append("```\n")
    parts.append("**Contract summary (generated):**")
    parts.append(prose)
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
        "existing code you want to keep -- this file will be OVERWRITTEN "
        "with your output. Do not include prose outside the code block."
    )
    info = {
        "clangd_chars": len(clangd_context),
        "prose_chars": len(prose),
        "semantic_block_chars": len(clangd_context) + len(prose),
    }
    return "\n".join(parts), info


def extract_cpp_code(response: str) -> str | None:
    for fence in ("cpp", "c++", "C++"):
        m = re.search(rf"```{re.escape(fence)}\s*\n(.*?)\n```",
                       response, re.DOTALL)
        if m:
            return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)\n```", response, re.DOTALL)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Workspace + grading (verbatim from M28)
# ---------------------------------------------------------------------------

def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="m28v2_s1_cpp_"))
    shutil.copy(SCENARIO_DIR / "reference" / "retry.hpp", ws / "retry.hpp")
    return ws


def grade_workspace(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="m28v2_grade_s1_"))
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
    prompt, info = build_prompt(cell, target_content, target_path)
    print(f"[prompt] {len(prompt)} chars "
          f"(clangd {info['clangd_chars']} + prose {info['prose_chars']})")

    model = os.environ.get("M28V2_EXEC_MODEL", "qwen2.5-coder:32b")
    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        err_summary = {
            "phase": "M28v2_clangd_prose",
            "scenario": "S1",
            "cell": cell,
            "run_id": run_id,
            "passed": 0, "total": 2,
            "error": f"ollama call failed: {e}",
            "wall_s": round(time.time() - t0, 1),
            "intervention": "clangd+prose",
            "clangd_context_chars": info["clangd_chars"],
            "prose_chars": info["prose_chars"],
        }
        cell_slug = cell.replace("+", "_").replace("-", "_")
        out_path = OUT_DIR / f"m28v2_s1_cpp_{cell_slug}_run{run_id}_summary.json"
        out_path.write_text(json.dumps(err_summary, indent=2),
                             encoding="utf-8")
        print(f"SUMMARY: {cell} ERROR: {e}")
        return err_summary
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} "
          f"out={llm['output_tokens']}")

    code = extract_cpp_code(llm["response"])
    if code is None:
        no_code_summary = {
            "phase": "M28v2_clangd_prose",
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
            "intervention": "clangd+prose",
            "clangd_context_chars": info["clangd_chars"],
            "prose_chars": info["prose_chars"],
            "response_tail": llm["response"][-1500:],
            "wall_s": round(time.time() - t0, 1),
        }
        cell_slug = cell.replace("+", "_").replace("-", "_")
        out_path = OUT_DIR / f"m28v2_s1_cpp_{cell_slug}_run{run_id}_summary.json"
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
        "phase": "M28v2_clangd_prose",
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
        "intervention": "clangd+prose",
        "clangd_context_chars": info["clangd_chars"],
        "prose_chars": info["prose_chars"],
        "llm_elapsed_s": round(llm["elapsed_s"], 1),
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "grade_stdout_tail": g["stdout_tail"],
    }

    cell_slug = cell.replace("+", "_").replace("-", "_")
    out_path = OUT_DIR / f"m28v2_s1_cpp_{cell_slug}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']}  "
          f"cited={cite['cited']}  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def run_sweep(cells: list[str], n_per_cell: int) -> dict:
    results = []
    for cell in cells:
        for i in range(1, n_per_cell + 1):
            run_id = str(i)
            print(f"\n===== {cell} run {i}/{n_per_cell} =====")
            summary = run_one(cell, run_id)
            results.append(summary)
    return {"runs": results, "n_per_cell": n_per_cell, "cells": cells}


CELLS = ("off", "on-rule", "on-rule+placebo", "on-rule+rat")


def main(argv: list[str]) -> int:
    _resolve_compile_db()
    try:
        # Cache prose once before any trial runs.
        target = SCENARIO_DIR / "reference" / "retry.hpp"
        cached = _ensure_prose_cached(target)
        print()
        print("=" * 60)
        print(f"PROSE SUMMARY (cached, {len(cached['prose'])} chars):")
        print("=" * 60)
        print(cached["prose"])
        print("=" * 60)
        print()
        # Persist the cached prose so the verdict run records exactly
        # what the model saw.
        prose_log = OUT_DIR / "_cached_prose.json"
        prose_log.write_text(json.dumps(cached, indent=2), encoding="utf-8")
        print(f"prose cache written: {prose_log}")
        print()

        if len(argv) >= 2 and argv[1] == "--sweep":
            n = 10
            for i, a in enumerate(argv[2:]):
                if a == "--n" and i + 1 < len(argv[2:]):
                    n = int(argv[2 + i + 1])
            run_sweep(list(CELLS), n)
            return 0
        if len(argv) < 2:
            print("usage:")
            print("  m28v2_smoke.py <cell> [run_id]   # single trial")
            print("  m28v2_smoke.py --sweep [--n N]   # batch (default N=10)")
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
        if _CLANGD_INDEXER is not None:
            try:
                _CLANGD_INDEXER.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main(sys.argv))
