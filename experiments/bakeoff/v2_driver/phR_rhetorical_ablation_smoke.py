#!/usr/bin/env python3
"""
Phase R — Deep ablation of the RATIONALE constant (Lesson 1 validation).

The Loom prompt-engineering doc claims "rationale is load-bearing"
based on the phQ series, where on-rule (no rationale) compliance
sat at 0% and on-rule+rationale saturated at 100%. But the same
data also showed a length-matched placebo hitting 70-90% — close
enough to rationale that "explanation-shape text" might be doing
most of the work, not the rationale's content.

This phase decomposes the RATIONALE constant into six atomic
rhetorical features and runs leave-one-out ablation:

  A. Codebase locator        ("backoff_loop.js", "BackoffError")
  B. Mechanism               ("intercepts and re-issues", "breaks the wrapper contract")
  C. Incident date           ("2024-09-12")
  D. Cost anchor             ("three hours")
  E. Reframe                 ("actually working as intended")
  F. Dependence assertion    ("load-bearing for the wrapper above us")

For each feature, a variant strips just that feature while keeping
the other five. If a strip drops compliance materially (toward the
30% placebo floor), that feature is necessary. If a strip leaves
compliance at 100%, that feature is non-essential on this scenario.

Conditions chosen to give maximum ablation headroom: phQ6 baseline
(JsIndexer v2, NO test files in workspace, qwen2.5-coder:32b).
phQ7's wider context saturated placebo at 70%, leaving only 30pp
of room. phQ6 leaves 70pp.

Cells (N=10 each, 80 trials total, ~22 min wall):
  - placebo (control)
  - V_full (positive control — same as phQ6 +rat, expected ≈100%)
  - V_no_locator   strips A
  - V_no_mechanism strips B
  - V_no_date      strips C
  - V_no_cost      strips D
  - V_no_reframe   strips E
  - V_no_dependence strips F

Same harness shape as phQ6: ESM scenario, real JsIndexer v2,
no test_retry.js in workspace.
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


# ---------------------------------------------------------------------------
# Scenario config — verbatim from phQ6
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


# ---------------------------------------------------------------------------
# Rationale variants — leave-one-out decomposition
# ---------------------------------------------------------------------------
#
# V_FULL is the original phQ rationale. Each V_NO_* strips one
# rhetorical feature while keeping the others. Lengths are NOT
# controlled across variants; the gap between placebo and full
# rationale (70pp at phQ6) is wide enough that small length-effect
# noise should be detectable.

V_FULL = (
    "The retry wrapper in backoff_loop.js two frames up intercepts "
    "BackoffError and re-issues. Throwing from fetchWithRetry breaks "
    "the wrapper contract — production incident 2024-09-12 lost "
    "three hours while ops chased a propagation bug that was "
    "actually working as intended. The current swallow-and-return-"
    "null behavior is load-bearing for the BackoffError wrapper "
    "above us."
)

# Strip A (codebase locator): replace specific file/class names with
# generic referents. Keeps the rest of the structure intact.
V_NO_LOCATOR = (
    "The retry wrapper two frames up intercepts an error type and "
    "re-issues. Throwing from fetchWithRetry breaks the wrapper "
    "contract — production incident 2024-09-12 lost three hours "
    "while ops chased a propagation bug that was actually working "
    "as intended. The current swallow-and-return-null behavior is "
    "load-bearing for the wrapper above us."
)

# Strip B (mechanism): remove causal/mechanism prose. Keep the
# locator, date, cost, reframe, dependence claim.
V_NO_MECHANISM = (
    "The retry wrapper in backoff_loop.js two frames up handles "
    "errors via BackoffError. Errors from fetchWithRetry are "
    "problematic — production incident 2024-09-12 lost three hours "
    "while ops chased a propagation bug that was actually working "
    "as intended. The current swallow-and-return-null behavior is "
    "load-bearing for the BackoffError wrapper above us."
)

# Strip C (incident date): drop the specific date but keep the
# appeal to history.
V_NO_DATE = (
    "The retry wrapper in backoff_loop.js two frames up intercepts "
    "BackoffError and re-issues. Throwing from fetchWithRetry breaks "
    "the wrapper contract — a past production incident lost three "
    "hours while ops chased a propagation bug that was actually "
    "working as intended. The current swallow-and-return-null "
    "behavior is load-bearing for the BackoffError wrapper above us."
)

# Strip D (cost anchor): remove the "three hours" quantification.
V_NO_COST = (
    "The retry wrapper in backoff_loop.js two frames up intercepts "
    "BackoffError and re-issues. Throwing from fetchWithRetry breaks "
    "the wrapper contract — production incident 2024-09-12 was "
    "caused by ops chasing a propagation bug that was actually "
    "working as intended. The current swallow-and-return-null "
    "behavior is load-bearing for the BackoffError wrapper above us."
)

# Strip E (reframe): drop the "actually working as intended" line
# that anticipates the task framing's "fix the bug" pull.
V_NO_REFRAME = (
    "The retry wrapper in backoff_loop.js two frames up intercepts "
    "BackoffError and re-issues. Throwing from fetchWithRetry breaks "
    "the wrapper contract — production incident 2024-09-12 lost "
    "three hours while ops chased a propagation bug. The current "
    "swallow-and-return-null behavior is load-bearing for the "
    "BackoffError wrapper above us."
)

# Strip F (dependence assertion): drop the explicit "load-bearing"
# language at the end.
V_NO_DEPENDENCE = (
    "The retry wrapper in backoff_loop.js two frames up intercepts "
    "BackoffError and re-issues. Throwing from fetchWithRetry breaks "
    "the wrapper contract — production incident 2024-09-12 lost "
    "three hours while ops chased a propagation bug that was "
    "actually working as intended."
)

# Length-matched placebo (verbatim from phQ harnesses) — control.
PLACEBO_TARGET_LEN = len(V_FULL)
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


# Cell name → rationale text. Special: "placebo" uses PLACEBO.
CELL_RATIONALES = {
    "placebo":         PLACEBO,
    "V_full":          V_FULL,
    "V_no_locator":    V_NO_LOCATOR,
    "V_no_mechanism":  V_NO_MECHANISM,
    "V_no_date":       V_NO_DATE,
    "V_no_cost":       V_NO_COST,
    "V_no_reframe":    V_NO_REFRAME,
    "V_no_dependence": V_NO_DEPENDENCE,
}


# ---------------------------------------------------------------------------
# Ollama call (verbatim from phQ6 — keep_alive + retry on transient 5xx)
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


# ---------------------------------------------------------------------------
# Claude CLI shell-out (cross-model replication path; uses Max plan auth,
# not API key). Returns the same shape as call_ollama() so callers don't
# branch. Triggered when PHR_EXEC_MODEL starts with "claude-" or is one
# of the bare aliases ("haiku", "sonnet", "opus").
# ---------------------------------------------------------------------------

_CLAUDE_SYSTEM_PROMPT = (
    "You are a helpful coding assistant. When the user asks for code, "
    "reply with the requested code in a fenced code block and nothing "
    "outside it."
)


def call_claude(model: str, prompt: str, timeout: int = 600) -> dict:
    # Run from a clean tempdir to avoid inheriting the loom project's
    # CLAUDE.md and tool loadout. Disable tools entirely so the model
    # cannot edit files agentically — we want a pure text completion
    # comparable to call_ollama. Override the system prompt for the
    # same reason.
    clean_cwd = tempfile.mkdtemp(prefix="phR_claude_cwd_")
    args = [
        "claude", "-p", "--no-session-persistence",
        "--output-format", "json", "--model", model,
        "--tools", "",
        "--system-prompt", _CLAUDE_SYSTEM_PROMPT,
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    t0 = time.time()
    try:
        proc = subprocess.run(
            args, input=prompt, cwd=clean_cwd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env=env, timeout=timeout,
            shell=(sys.platform == "win32"),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude CLI timed out after {timeout}s")
    elapsed = time.time() - t0
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude CLI rc={proc.returncode}: {(proc.stderr or '')[-300:]}"
        )
    try:
        d = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"claude CLI non-JSON output: {(proc.stdout or '')[-300:]}"
        )
    usage = d.get("usage", {}) or {}
    in_tokens = (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
    )
    return {
        "response": d.get("result", ""),
        "elapsed_s": elapsed,
        "input_tokens": in_tokens,
        "output_tokens": usage.get("output_tokens", 0),
    }


def _call_model(model: str, prompt: str, timeout: int = 600) -> dict:
    """Dispatch to ollama vs claude CLI based on model name prefix."""
    if model.startswith("claude") or model in ("haiku", "sonnet", "opus"):
        return call_claude(model, prompt, timeout=timeout)
    return call_ollama(model, prompt, timeout=timeout)


def build_prompt(cell: str, retry_js: str, semantic_block: str) -> str:
    parts: list[str] = []
    parts.append(f"# Task: {TASK}\n")
    parts.append("Files to modify: retry.js")
    parts.append("Grading test: tests/test_retry.js")
    parts.append("Size budget: <= 1 file, <= 200 LoC\n")

    parts.append("## Requirements\n")
    parts.append("### REQ-001 [behavior]")
    parts.append(f"Value: {RULE}")
    rationale_text = CELL_RATIONALES[cell]
    parts.append(f"Rationale: {rationale_text}")
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
    """phQ6 conditions: source files only, no test_retry.js. Wider
    headroom for ablation than phQ7's test-included setup."""
    ws = Path(tempfile.mkdtemp(prefix="phR_s1_js_"))
    for src in SCENARIO_DIR.glob("reference/*"):
        shutil.copy(src, ws / src.name)
    return ws


def grade_workspace(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="phR_grade_s1_"))
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

    model = os.environ.get("PHR_EXEC_MODEL", "qwen2.5-coder:32b")
    cell_slug = cell.replace("+", "_").replace("-", "_")
    # Original Qwen baseline files are saved at the bare path for backward
    # compatibility. New cross-model runs (haiku/sonnet/etc.) get the model
    # name embedded in the filename so they coexist without clobbering.
    if model.startswith("qwen2.5-coder"):
        suffix = ""
    else:
        suffix = "_" + model.replace(":", "_").replace("/", "_")
    out_path = OUT_DIR / f"phR_s1_js{suffix}_{cell_slug}_run{run_id}_summary.json"

    try:
        llm = _call_model(model, prompt)
    except Exception as e:
        err = {
            "phase": "R_rhetorical_ablation",
            "cell": cell, "run_id": run_id,
            "passed": 0, "total": 2,
            "error": f"model call failed ({model}): {e}",
            "wall_s": round(time.time() - t0, 1),
        }
        out_path.write_text(json.dumps(err, indent=2), encoding="utf-8")
        print(f"SUMMARY: {cell} ERROR: {e}")
        return err
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} out={llm['output_tokens']}")

    code = extract_js_code(llm["response"])
    if code is None:
        no_code = {
            "phase": "R_rhetorical_ablation",
            "cell": cell, "run_id": run_id,
            "passed": 0, "total": 2, "pass_rate": 0.0,
            "compile_failed": True,
            "no_code_extracted": True,
            "input_tokens": llm["input_tokens"],
            "output_tokens": llm["output_tokens"],
            "model": model,
            "wall_s": round(time.time() - t0, 1),
        }
        out_path.write_text(json.dumps(no_code, indent=2), encoding="utf-8")
        print(f"SUMMARY: {cell} no_code_extracted")
        return no_code

    (workspace / "retry.js").write_text(code, encoding="utf-8")
    g = grade_workspace(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}  compile_failed={g.get('compile_failed', False)}")

    summary = {
        "phase": "R_rhetorical_ablation",
        "cell": cell, "run_id": run_id,
        "passed": g["passed"], "total": g["total"],
        "pass_rate": g["passed"] / g["total"] if g["total"] else 0.0,
        "compile_failed": g.get("compile_failed", False),
        "rationale_chars": len(CELL_RATIONALES[cell]),
        "input_tokens": llm["input_tokens"],
        "output_tokens": llm["output_tokens"],
        "model": model,
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
        print("  phR_rhetorical_ablation_smoke.py sweep [N]")
        print("  phR_rhetorical_ablation_smoke.py <cell> [run_id]")
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
