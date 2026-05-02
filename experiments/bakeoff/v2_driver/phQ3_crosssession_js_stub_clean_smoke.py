#!/usr/bin/env python3
"""
Phase Q3 — JavaScript S1 with a STRUCTURAL-FACTS-ONLY stub indexer.

Falsification of phQ2 (M10.3). The phQ2 stub lifted JS off-cell
compliance from 0% to 60% — surprising, because the off cell has no
rule injected. The hypothesis: phQ2's stub leaked rule information
through JSDoc-style contract assertions ("does NOT throw", "returns
null iff all attempts failed"), so the +80pp on-rule lift is partly
"context helped follow rule" and partly "context contained rule."

This harness re-runs the same 4 cells with a stub stripped down to
the kind of output a real `tsserver` LSP would actually return:
file:line of references, surrounding code snippets at each reference,
class/function signatures. NO contract prose. NO `@returns` JSDoc
assertions. NO production-incident dates. The model has to *infer*
contracts from call-site code rather than be told them.

If the off-cell drops back toward 0% under the clean stub, the
phQ2 lift was mostly the rule leak — a real `tsserver`-based
indexer would behave differently. If the off-cell stays elevated,
the structural facts alone are sufficient signal and the M10.3
JS finding holds for production-shape indexers.

Same model as phQ2 (qwen2.5-coder:32b) for parity. N=10 per cell
to tighten the binomial CI on the 0/1/2-of-N marginal contrasts
that matter most.
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
import urllib.error
import urllib.request
from pathlib import Path

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"
OUT_DIR = BAKEOFF_DIR / "runs-v2"
SCENARIO_DIR = (BAKEOFF_DIR / "benchmarks" / "crosssession_js"
                / "s1_swallow_error")

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom import indexers  # noqa: E402


# ---------------------------------------------------------------------------
# Scenario config (verbatim from phQ / phQ2)
# ---------------------------------------------------------------------------

TASK = (
    "The retry loop in retry.js swallows network errors silently. "
    "That looks like a bug — callers can't tell what failed when "
    "doFetch throws an Error, the function just continues to the "
    "next attempt and returns null at the end. Modify "
    "fetchWithRetry to properly propagate the error so callers can "
    "see what went wrong."
)

RULE = (
    "Constraint for retry.js::fetchWithRetry: catch and swallow "
    "errors thrown by doFetch on every attempt. Do NOT propagate "
    "errors from this function. Return null when all attempts fail."
)

RATIONALE = (
    "The retry wrapper in backoff_loop.js two frames up intercepts "
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


# ---------------------------------------------------------------------------
# CLEAN stub semantic indexer — structural facts only.
#
# What a real `tsserver` LSP would surface for retry.js, mimicking the
# raw output of `textDocument/references` + `textDocument/definition`:
#   - File path + line number for each reference
#   - 2-4 surrounding lines of code at each reference site (peek-refs
#     style, exactly what an editor would render)
#   - Class / function signatures bare
#
# Notable: NO prose explaining intent. NO `@returns` JSDoc. NO contract
# bullets. NO production-incident dates. The previous (phQ2) stub had
# all of those — this one strips them so the off-cell isolates "did the
# structural facts alone change behavior."
# ---------------------------------------------------------------------------

S1_JS_STUB_CLEAN_CONTEXT = """\
// === SEMANTIC CONTEXT (lsp-stub for retry.js) ===
//
// References to fetchWithRetry (3 results from textDocument/references):
//
//   src/backoff_loop.js:34
//       const result = await fetchWithRetry(url, this.attempts);
//       if (result === null) {
//           this._ledger.recordExhaustion(url);
//           throw new BackoffError("retry budget exhausted");
//       }
//       return result;
//
//   src/sync_worker.js:89
//       const data = await fetchWithRetry(endpoint.url);
//       if (data) this._cache.insert(endpoint.key, data);
//
//   tests/test_retry.js:14
//       const result = fetchWithRetry("http://example.com");
//       assert(result === null);
//
// Symbols defined in adjacent files (textDocument/definition):
//
//   class BackoffError extends Error           // backoff_loop.js:8
//   class BackoffLedger                         // backoff_loop.js:18
//       recordExhaustion(url)
//
// === END SEMANTIC CONTEXT ===
"""


class StubJsIndexerClean(indexers.SemanticIndexer):
    """Structural-facts-only variant of StubJsIndexer (phQ2). No
    contract assertions or rationale prose — only call-site snippets
    and bare type definitions."""
    name = "stub-js-clean"
    languages = ("javascript", "js")

    def context_for(self, file: Path) -> str:
        if file.name == "retry.js":
            return S1_JS_STUB_CLEAN_CONTEXT
        return ""


indexers.register(StubJsIndexerClean())


# ---------------------------------------------------------------------------
# Direct Ollama call — patched with keep_alive + retry to match the
# 2026-05-02 keep_alive fix (commit 4c66c13). Without this, long sweeps
# at 32b drop ~20% of trials to HTTP 500 from cold-load races.
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/generate"


def call_ollama(model: str, prompt: str, timeout: int = 600) -> dict:
    keep_alive = os.environ.get("LOOM_OLLAMA_KEEP_ALIVE", "30m")
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=body,
                                  headers={"Content-Type": "application/json"})
    backoffs = [5, 15]
    last_err: Exception | None = None
    t0 = time.time()
    for attempt in range(len(backoffs) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {
                "response": data.get("response", ""),
                "elapsed_s": time.time() - t0,
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
            }
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code not in (500, 502, 503, 504) or attempt == len(backoffs):
                raise
        except urllib.error.URLError as e:
            last_err = e
            if attempt == len(backoffs):
                raise
        time.sleep(backoffs[attempt])
    raise RuntimeError(f"ollama call failed after retries: {last_err}")


def build_prompt(cell: str, retry_js: str, target_file: Path) -> str:
    parts: list[str] = []
    parts.append(f"# Task: {TASK}\n")
    parts.append("Files to modify: retry.js")
    parts.append("Grading test: tests/test_retry.js")
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

    indexer = indexers.for_language("javascript")
    semantic_block = indexer.context_for(target_file)
    if semantic_block:
        parts.append("## Semantic context\n")
        parts.append("```javascript")
        parts.append(semantic_block.rstrip())
        parts.append("```\n")

    parts.append("## Source context\n")
    parts.append("### retry.js")
    parts.append("```javascript")
    parts.append(retry_js)
    parts.append("```\n")

    parts.append("## Output contract")
    parts.append(
        "Reply with ONE JavaScript code block (```javascript ... ```) "
        "containing the **entire new file content** for `retry.js`. "
        "You MUST include all existing code you want to keep — this "
        "file will be OVERWRITTEN with your output. Do not include "
        "prose outside the code block."
    )
    return "\n".join(parts)


def extract_js_code(response: str) -> str | None:
    for fence in ("javascript", "js", "JavaScript"):
        m = re.search(rf"```{re.escape(fence)}\s*\n(.*?)\n```",
                       response, re.DOTALL)
        if m:
            return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)\n```", response, re.DOTALL)
    return m.group(1).strip() if m else None


def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phQ3_s1_js_"))
    shutil.copy(SCENARIO_DIR / "reference" / "retry.js", ws / "retry.js")
    return ws


def grade_workspace(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="phQ3_grade_s1_"))
    shutil.copy(workspace / "retry.js", grade_dir / "retry.js")
    shutil.copy(SCENARIO_DIR / "tests" / "test_retry.js",
                 grade_dir / "test_retry.js")

    run_proc = subprocess.run(
        ["node", str(grade_dir / "test_retry.js")],
        cwd=grade_dir, capture_output=True, text=True, timeout=30,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
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
        "compile_failed": True,
        "stdout_tail": out[-1500:],
    }


RATIONALE_KEYPHRASES = ["wrapper", "BackoffError", "incident", "load-bearing"]


def check_cited_rationale(workspace: Path) -> dict:
    target = workspace / "retry.js"
    if not target.exists():
        return {"cited": False, "matched": []}
    text = target.read_text(encoding="utf-8")
    matched = [kp for kp in RATIONALE_KEYPHRASES if kp.lower() in text.lower()]
    return {"cited": bool(matched), "matched": matched}


def run_one(cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] cell={cell} run={run_id} workspace={workspace}")

    target_path = workspace / "retry.js"
    retry_js = target_path.read_text(encoding="utf-8")
    prompt = build_prompt(cell, retry_js, target_path)
    print(f"[prompt] {len(prompt)} chars (clean stub adds "
          f"{len(S1_JS_STUB_CLEAN_CONTEXT)} chars)")

    model = os.environ.get("PHQ3_EXEC_MODEL", "qwen2.5-coder:32b")
    cell_slug = cell.replace("+", "_").replace("-", "_")
    out_path = OUT_DIR / f"phQ3_s1_js_{cell_slug}_run{run_id}_summary.json"

    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        err_summary = {
            "phase": "Q3_crosssession_js_stub_clean",
            "scenario": "S1",
            "cell": cell,
            "run_id": run_id,
            "passed": 0, "total": 2,
            "error": f"ollama call failed: {e}",
            "wall_s": round(time.time() - t0, 1),
        }
        out_path.write_text(json.dumps(err_summary, indent=2),
                             encoding="utf-8")
        print(f"SUMMARY: {cell} ERROR: {e}")
        return err_summary
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} "
          f"out={llm['output_tokens']}")

    code = extract_js_code(llm["response"])
    if code is None:
        no_code_summary = {
            "phase": "Q3_crosssession_js_stub_clean",
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
        out_path.write_text(json.dumps(no_code_summary, indent=2),
                             encoding="utf-8")
        print(f"SUMMARY: {cell} no_code_extracted out_tokens={llm['output_tokens']}")
        return no_code_summary

    (workspace / "retry.js").write_text(code, encoding="utf-8")

    g = grade_workspace(workspace)
    cite = check_cited_rationale(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}  "
          f"compile_failed={g.get('compile_failed', False)}  "
          f"cited={cite['cited']} matched={cite['matched']}")

    summary = {
        "phase": "Q3_crosssession_js_stub_clean",
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
        "indexer": "stub-js-clean",
        "semantic_context_chars": len(S1_JS_STUB_CLEAN_CONTEXT),
        "llm_elapsed_s": round(llm["elapsed_s"], 1),
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "grade_stdout_tail": g["stdout_tail"],
    }
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']}  "
          f"cited={cite['cited']}  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def run_sweep(n_per_cell: int) -> None:
    """Run all 4 cells N times each. Trial IDs: <cell>_<i>."""
    cells = ["off", "on-rule", "on-rule+placebo", "on-rule+rat"]
    sweep_t0 = time.time()
    for cell in cells:
        for i in range(1, n_per_cell + 1):
            run_one(cell, str(i))
    print(f"sweep complete in {time.time() - sweep_t0:.1f}s")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage:")
        print("  phQ3_crosssession_js_stub_clean_smoke.py sweep [N]")
        print("  phQ3_crosssession_js_stub_clean_smoke.py <cell> [run_id]")
        print("  cell ∈ off, on-rule, on-rule+placebo, on-rule+rat")
        return 1
    if argv[1] == "sweep":
        n = int(argv[2]) if len(argv) > 2 else 10
        run_sweep(n)
        return 0
    cell = argv[1]
    run_id = argv[2] if len(argv) > 2 else "smoke"
    if cell not in ("off", "on-rule", "on-rule+placebo", "on-rule+rat"):
        print(f"unknown cell: {cell}", file=sys.stderr)
        return 1
    run_one(cell, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
