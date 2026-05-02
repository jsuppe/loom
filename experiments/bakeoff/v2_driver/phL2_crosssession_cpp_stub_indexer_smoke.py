#!/usr/bin/env python3
"""
Phase L2 — C++ S1 with a stub SemanticIndexer providing semantic context.

Same harness as phL (cross-language C++ smoke) with one change: the
prompt now includes a "SEMANTIC CONTEXT (kythe stub)" prologue that
mimics what a real Kythe query would surface for retry.hpp — the call
sites of fetchWithRetry (showing the wrapper actually exists), the
referenced types, and the contract notes.

This is the M10.2 falsification: if the M10.1b executor-capacity
falsification was right and the C++ ceiling is about *missing context*
rather than *executor weakness*, then injecting hand-curated semantic
context should lift the rat-cell compliance. If it doesn't, the C++
ceiling has yet another cause and Kythe is overkill.

Same model as the executor falsification (qwen2.5-coder:32b) since
that ruled out the smaller-executor-too-weak hypothesis. Same 4 cells,
same N=5.

The stub indexer returns the SAME context block for every cell —
including the ``off`` cell. That's intentional: the experiment isolates
"semantic context vs no semantic context", not "rule+context vs
rule-only". If even off+context lifts compliance, semantic context is
load-bearing on its own. If only on-rule+rat+context lifts, context
amplifies rule following but doesn't replace it.
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

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom import indexers  # noqa: E402


# ---------------------------------------------------------------------------
# Scenario config (verbatim from phL)
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
# Stub semantic indexer for the S1 C++ scenario
# ---------------------------------------------------------------------------

# This is what a real Kythe query would surface for retry.hpp — the
# call sites, type definitions, and contract notes that would actually
# convince an agent the rationale is real, not just a claim. Authored
# by hand to mimic the shape of Kythe's xref output.
S1_CPP_STUB_CONTEXT = """\
// === SEMANTIC CONTEXT (kythe-stub for retry.hpp) ===
//
// Call sites of fetchWithRetry (3 references in this corpus):
//
//   src/backoff_loop.hpp:42  in BackoffLoop::run(const std::string& url):
//       auto result = fetchWithRetry(url, attempts_);
//       if (!result.has_value()) {
//           // exhaustion path — mark BackoffLedger and re-issue
//           ledger_.recordExhaustion(url);
//           throw BackoffError("retry budget exhausted");
//       }
//       return *result;
//   IMPORTANT: this call site does NOT have a try/catch around
//   fetchWithRetry. It assumes fetchWithRetry returns std::nullopt on
//   failure and never throws. If fetchWithRetry propagates
//   std::runtime_error, BackoffLoop::run will let it bubble up
//   uncaught — a contract violation that production hit on 2024-09-12.
//
//   src/sync_worker.cpp:118  in SyncWorker::pull(const Endpoint& ep):
//       auto data = fetchWithRetry(ep.url);
//       if (data) cache_.insert(ep.key, *data);
//       // no exception handling — same contract assumption.
//
//   tests/test_retry.cpp:25  in test_runtime_error_swallowed_returns_nullopt:
//       auto result = fetchWithRetry("http://example.com");
//       // verifier expects: result.has_value() == false
//       // verifier counts a thrown std::runtime_error as FAIL.
//
// Types referenced from retry.hpp:
//
//   class BackoffError : public std::exception {  // backoff_loop.hpp:8
//       const char* what() const noexcept override;
//   };
//   class BackoffLedger {                          // backoff_loop.hpp:18
//       void recordExhaustion(const std::string& url);
//       // mutates retry-state; corruption requires manual replay.
//   };
//
// Contract for fetchWithRetry (per BackoffLoop's expectations):
//
//   * Returns std::optional<std::string>.
//   * Returns std::nullopt iff all attempts have failed.
//   * Does NOT throw. Specifically: catches std::runtime_error
//     internally and continues to the next attempt.
//   * Other exception types (not std::runtime_error) propagate.
//
// === END SEMANTIC CONTEXT ===
"""


class StubCppIndexer(indexers.SemanticIndexer):
    """Stand-in for a real KytheIndexer. Returns hand-curated semantic
    context for the S1 C++ scenario; refuses to resolve symbols (M10.2
    only exercises the context-enrichment seam, not the linking seam).
    """
    name = "stub-cpp"
    languages = ("c++", "cpp")

    def context_for(self, file: Path) -> str:
        if file.name == "retry.hpp":
            return S1_CPP_STUB_CONTEXT
        return ""


indexers.register(StubCppIndexer())


# ---------------------------------------------------------------------------
# Direct Ollama call (verbatim from phL)
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
# Prompt construction — phL's, plus a SEMANTIC CONTEXT block from the indexer
# ---------------------------------------------------------------------------

def build_prompt(cell: str, target_file_content: str, target_file: Path) -> str:
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

    # M10.2: semantic context from the registered indexer for the
    # target file's language. The block goes ABOVE the file body so
    # the agent sees structural information before the inline source.
    indexer = indexers.for_language("c++")
    semantic_block = indexer.context_for(target_file)
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
        "existing code you want to keep — this file will be OVERWRITTEN with "
        "your output. Do not include prose outside the code block."
    )
    return "\n".join(parts)


def extract_cpp_code(response: str) -> str | None:
    for fence in ("cpp", "c++", "C++"):
        m = re.search(rf"```{re.escape(fence)}\s*\n(.*?)\n```",
                       response, re.DOTALL)
        if m:
            return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)\n```", response, re.DOTALL)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Workspace + grading (verbatim from phL)
# ---------------------------------------------------------------------------

def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phL2_s1_cpp_"))
    shutil.copy(SCENARIO_DIR / "reference" / "retry.hpp", ws / "retry.hpp")
    return ws


def grade_workspace(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="phL2_grade_s1_"))
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
    matched = [kp for kp in RATIONALE_KEYPHRASES if kp.lower() in text.lower()]
    return {"cited": bool(matched), "matched": matched}


def run_one(cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] cell={cell} workspace={workspace}")

    target_path = workspace / "retry.hpp"
    target_content = target_path.read_text(encoding="utf-8")
    prompt = build_prompt(cell, target_content, target_path)
    print(f"[prompt] {len(prompt)} chars (semantic block adds "
          f"{len(S1_CPP_STUB_CONTEXT)} chars)")

    model = os.environ.get("PHL2_EXEC_MODEL", "qwen2.5-coder:32b")
    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        return {
            "phase": "L2_crosssession_cpp_stub_indexer",
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
        no_code_summary = {
            "phase": "L2_crosssession_cpp_stub_indexer",
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
        out_path = OUT_DIR / f"phL2_s1_cpp_{cell_slug}_run{run_id}_summary.json"
        out_path.write_text(json.dumps(no_code_summary, indent=2),
                             encoding="utf-8")
        print(f"SUMMARY: {cell} no_code_extracted out_tokens={llm['output_tokens']}")
        return no_code_summary

    (workspace / "retry.hpp").write_text(code, encoding="utf-8")

    g = grade_workspace(workspace)
    cite = check_cited_rationale(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}  "
          f"compile_failed={g.get('compile_failed', False)}  "
          f"cited={cite['cited']} matched={cite['matched']}")

    summary = {
        "phase": "L2_crosssession_cpp_stub_indexer",
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
        "indexer": "stub-cpp",
        "semantic_context_chars": len(S1_CPP_STUB_CONTEXT),
        "llm_elapsed_s": round(llm["elapsed_s"], 1),
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "grade_stdout_tail": g["stdout_tail"],
    }

    cell_slug = cell.replace("+", "_").replace("-", "_")
    out_path = OUT_DIR / f"phL2_s1_cpp_{cell_slug}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']}  "
          f"cited={cite['cited']}  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: phL2_crosssession_cpp_stub_indexer_smoke.py <cell> [run_id]")
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
