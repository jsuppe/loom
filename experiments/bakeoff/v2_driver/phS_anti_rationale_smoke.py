#!/usr/bin/env python3
"""
Phase S — Anti-rationale ablation (Lesson 1 vs Lesson 3 disambiguator).

The phR ablation showed the *reframe* is the single load-bearing
rhetorical feature within the original rationale. But phR didn't
test content POLARITY — every variant supported the rule, just
with different rhetorical features stripped.

phS tests whether content polarity matters: replace the rationale
with text that argues AGAINST the rule. Three variants vary in
how directly they oppose:

  - ANTI_SOFT:        gentle dissent ("this may run counter to best practice")
  - ANTI_HARD:        direct contradiction ("propagate, not swallow")
  - ANTI_AMBIVALENT:  explicit uncertainty ("we have no clear reason")

If anti-rationale drops compliance below the placebo floor (30%
in phR conditions), content polarity matters — bad rationale is
worse than no rationale.

If anti-rationale stays near placebo, the model treats explanation-
shape text without parsing polarity — Lesson 3 (placebo carries
shape, not content) generalizes.

If ANTI_HARD specifically drops near 0% (model sides with rationale
over rule), the model treats rationale as authoritative when it
conflicts with the rule.

Same harness conditions as phR: phQ6 baseline (JsIndexer v2, no
test files in workspace, qwen2.5-coder:32b).

Cells (N=10 each, 40 trials total, ~12-15 min wall):
  - V_full (positive control — pro-rule rationale, ≈100%)
  - ANTI_SOFT
  - ANTI_HARD
  - ANTI_AMBIVALENT
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
                / "s1_swallow_error_esm")

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom import indexers  # noqa: E402
from loom.indexers_js import JsIndexer  # noqa: E402


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


# ---------------------------------------------------------------------------
# Rationale variants — content polarity ablation
# ---------------------------------------------------------------------------

V_FULL = (
    "The retry wrapper in backoff_loop.js two frames up intercepts "
    "BackoffError and re-issues. Throwing from fetchWithRetry breaks "
    "the wrapper contract — production incident 2024-09-12 lost "
    "three hours while ops chased a propagation bug that was "
    "actually working as intended. The current swallow-and-return-"
    "null behavior is load-bearing for the BackoffError wrapper "
    "above us."
)

# Soft anti: hedged dissent. Doesn't directly say "ignore the rule"
# but introduces doubt that the rule is well-founded.
ANTI_SOFT = (
    "Note: catching errors silently can hide real failures and is "
    "generally discouraged in modern JavaScript codebases. The "
    "swallow pattern in this requirement may run counter to current "
    "best practice — consider whether the rule reflects an outdated "
    "constraint that should be revisited rather than enforced."
)

# Hard anti: direct contradiction. The rationale literally argues
# for the opposite of what the rule says.
ANTI_HARD = (
    "This rule contradicts modern best practice. Errors should be "
    "propagated so callers can decide how to handle them — the "
    "swallow-and-return-null pattern is a legacy anti-pattern that "
    "obscures real failures. We are migrating away from this "
    "behavior; new code should propagate errors, not swallow them."
)

# Ambivalent: explicit "we don't know why this is here." Tests
# whether merely flagging uncertainty is treated like anti-rationale
# or like neutral.
ANTI_AMBIVALENT = (
    "We have no clear reason for this rule yet. It's a placeholder "
    "while we decide whether to keep the swallow pattern or switch "
    "to propagation. Either choice may be correct depending on the "
    "broader codebase, which has not been audited. Treat the rule "
    "as provisional until we know more."
)


CELL_RATIONALES = {
    "V_full":          V_FULL,
    "ANTI_SOFT":       ANTI_SOFT,
    "ANTI_HARD":       ANTI_HARD,
    "ANTI_AMBIVALENT": ANTI_AMBIVALENT,
}


# ---------------------------------------------------------------------------
# Ollama call (verbatim from phR — keep_alive + retry on transient 5xx)
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/generate"


def call_ollama(model: str, prompt: str, timeout: int = 600) -> dict:
    keep_alive = os.environ.get("LOOM_OLLAMA_KEEP_ALIVE", "30m")
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
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


def build_prompt(cell: str, retry_js: str, semantic_block: str) -> str:
    parts: list[str] = []
    parts.append(f"# Task: {TASK}\n")
    parts.append("Files to modify: retry.js")
    parts.append("Grading test: tests/test_retry.js")
    parts.append("Size budget: <= 1 file, <= 200 LoC\n")

    parts.append("## Requirements\n")
    parts.append("### REQ-001 [behavior]")
    parts.append(f"Value: {RULE}")
    parts.append(f"Rationale: {CELL_RATIONALES[cell]}")
    parts.append("")

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
    ws = Path(tempfile.mkdtemp(prefix="phS_s1_js_"))
    for src in SCENARIO_DIR.glob("reference/*"):
        shutil.copy(src, ws / src.name)
    return ws


def grade_workspace(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="phS_grade_s1_"))
    shutil.copy(workspace / "retry.js", grade_dir / "retry.js")
    shutil.copy(SCENARIO_DIR / "tests" / "test_retry.js",
                grade_dir / "test_retry.js")
    shutil.copy(SCENARIO_DIR / "reference" / "package.json",
                grade_dir / "package.json")
    run_proc = subprocess.run(
        ["node", str(grade_dir / "test_retry.js")],
        cwd=grade_dir, capture_output=True, text=True, timeout=30,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    out = run_proc.stdout + run_proc.stderr
    m = re.search(r"SUMMARY:\s*(\d+)\s*passed,\s*(\d+)\s*failed", out)
    if m:
        passed = int(m.group(1)); failed = int(m.group(2))
        return {
            "passed": passed, "total": passed + failed,
            "compile_failed": False, "stdout_tail": out[-1500:],
        }
    return {"passed": 0, "total": 2, "compile_failed": True,
            "stdout_tail": out[-1500:]}


def get_semantic_context(workspace: Path) -> str:
    for prev in list(indexers.registered()):
        indexers.unregister(prev)
    idx = JsIndexer(root=workspace)
    indexers.register(idx)
    try:
        block = idx.context_for(workspace / "retry.js")
    finally:
        indexers.unregister(idx)
        idx.shutdown()
    return block


def run_one(cell: str, run_id: str) -> dict:
    if cell not in CELL_RATIONALES:
        raise ValueError(f"unknown cell: {cell}")
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] cell={cell} run={run_id}")
    target_path = workspace / "retry.js"
    retry_js = target_path.read_text(encoding="utf-8")
    semantic_block = get_semantic_context(workspace)
    prompt = build_prompt(cell, retry_js, semantic_block)
    print(f"[prompt] {len(prompt)} chars  rationale={len(CELL_RATIONALES[cell])} chars")

    model = os.environ.get("PHS_EXEC_MODEL", "qwen2.5-coder:32b")
    cell_slug = cell.replace("+", "_").replace("-", "_")
    out_path = OUT_DIR / f"phS_s1_js_{cell_slug}_run{run_id}_summary.json"

    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        err = {"phase": "S_anti_rationale", "cell": cell, "run_id": run_id,
               "passed": 0, "total": 2,
               "error": f"ollama call failed: {e}",
               "wall_s": round(time.time() - t0, 1)}
        out_path.write_text(json.dumps(err, indent=2), encoding="utf-8")
        print(f"SUMMARY: {cell} ERROR: {e}")
        return err
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} out={llm['output_tokens']}")

    code = extract_js_code(llm["response"])
    if code is None:
        no_code = {"phase": "S_anti_rationale", "cell": cell, "run_id": run_id,
                   "passed": 0, "total": 2, "pass_rate": 0.0,
                   "compile_failed": True, "no_code_extracted": True,
                   "input_tokens": llm["input_tokens"],
                   "output_tokens": llm["output_tokens"], "model": model,
                   "wall_s": round(time.time() - t0, 1)}
        out_path.write_text(json.dumps(no_code, indent=2), encoding="utf-8")
        print(f"SUMMARY: {cell} no_code_extracted")
        return no_code

    (workspace / "retry.js").write_text(code, encoding="utf-8")
    g = grade_workspace(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}")
    summary = {
        "phase": "S_anti_rationale", "cell": cell, "run_id": run_id,
        "passed": g["passed"], "total": g["total"],
        "pass_rate": g["passed"] / g["total"] if g["total"] else 0.0,
        "compile_failed": g.get("compile_failed", False),
        "rationale_chars": len(CELL_RATIONALES[cell]),
        "input_tokens": llm["input_tokens"],
        "output_tokens": llm["output_tokens"], "model": model,
        "indexer": "ts-lsp-v2",
        "llm_elapsed_s": round(llm["elapsed_s"], 1),
        "wall_s": round(time.time() - t0, 1),
        "grade_stdout_tail": g["stdout_tail"],
    }
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']} wall={summary['wall_s']}s")
    return summary


def run_sweep(n_per_cell: int) -> None:
    cells = list(CELL_RATIONALES.keys())
    sweep_t0 = time.time()
    for cell in cells:
        for i in range(1, n_per_cell + 1):
            run_one(cell, str(i))
    print(f"sweep complete in {time.time() - sweep_t0:.1f}s")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage:")
        print("  phS_anti_rationale_smoke.py sweep [N]")
        print("  phS_anti_rationale_smoke.py <cell> [run_id]")
        print(f"  cells: {', '.join(CELL_RATIONALES.keys())}")
        return 1
    if argv[1] == "sweep":
        n = int(argv[2]) if len(argv) > 2 else 10
        run_sweep(n)
        return 0
    cell = argv[1]
    run_id = argv[2] if len(argv) > 2 else "smoke"
    if cell not in CELL_RATIONALES:
        print(f"unknown cell: {cell}", file=sys.stderr)
        return 1
    run_one(cell, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
