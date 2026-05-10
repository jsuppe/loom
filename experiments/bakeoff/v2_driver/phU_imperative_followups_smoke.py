#!/usr/bin/env python3
"""
Phase U — Three follow-ups on phT's R_imperative finding.

phT showed R_imperative (absolute imperative rule wording) restored
compliance from 0% to 100% against ANTI_SOFT — but with three
caveats the findings doc flagged:

  (a) R_imperative was 50% longer than baseline (277 vs 181 chars).
      Some of the lift could be a length-effect, not specifically
      imperative-effect.
  (b) Only tested against ANTI_SOFT. ANTI_HARD scored 15% in phS;
      does R_imperative still pull it to 100%?
  (c) Untested whether R_imperative + meta_preamble interact
      (additive, neutral, or interfering).

phU addresses all three:

Cells (N=10 each, 50 trials, ~15 min wall):

  R_baseline_check          standard rule + ANTI_SOFT (sanity, expect 0%)
  R_imperative_phrase       baseline + "STRICT REQUIREMENT:" prefix only — tests prefix alone
  R_imperative_minimal      baseline with "MUST NOT under any circumstances" inline — tests middle alone
  R_imperative_vs_anti_hard R_imperative (full) + ANTI_HARD — tests cross-anti generalization
  R_imperative_plus_meta    R_imperative (full) + meta preamble + ANTI_SOFT — tests combo

Interpretive map:
  - If R_imperative_phrase ≈ 100% but R_imperative_minimal ≈ 0% →
    the prefix carries the lift (rhetorical framing matters).
  - If R_imperative_minimal ≈ 100% but R_imperative_phrase ≈ 0% →
    the inline "MUST NOT under any circumstances" carries the
    lift (imperative weight on the action verb matters).
  - If both score high → either approach works; imperative weight
    is the lever wherever it lives in the rule.
  - If both score low → R_imperative's lift was a length effect,
    not an imperative-language effect. Lesson 9 needs revision.

  - If R_imperative_vs_anti_hard ≈ 100% → recipe generalizes
    across anti-rationale strength.
  - If R_imperative_vs_anti_hard ≈ baseline (15% in phS) → recipe
    only works on weak anti, not on direct contradiction.

  - If R_imperative_plus_meta ≈ 100% → R_imperative dominates,
    meta neutral or independent.
  - If R_imperative_plus_meta < 100% → meta-preamble actively
    interferes with imperative weight.
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


# ---------------------------------------------------------------------------
# Rule variants — same lengths-and-content matrix as phT, plus two new
# length-controlled imperative variants.
# ---------------------------------------------------------------------------

# 181 chars — same as phT's baseline.
RULE_STANDARD = (
    "Constraint for retry.js::fetchWithRetry: catch and swallow "
    "errors thrown by doFetch on every attempt. Do NOT propagate "
    "errors from this function. Return null when all attempts fail."
)

# 277 chars — same as phT's R_imperative (full kit: prefix +
# inline MUST NOT + closing override claim).
RULE_IMPERATIVE_FULL = (
    "ABSOLUTE REQUIREMENT — NON-NEGOTIABLE: catch and swallow "
    "errors thrown by doFetch on every attempt. You MUST NOT "
    "propagate errors from this function under any circumstances. "
    "Return null when all attempts fail. This is a STRICT "
    "requirement that overrides general best practices."
)

# 209 chars — baseline + "STRICT REQUIREMENT:" prefix only. Tests
# whether the rhetorical opener alone carries the lift.
RULE_IMPERATIVE_PHRASE = (
    "STRICT REQUIREMENT — NON-NEGOTIABLE: Constraint for "
    "retry.js::fetchWithRetry: catch and swallow errors thrown by "
    "doFetch on every attempt. Do NOT propagate errors from this "
    "function. Return null when all attempts fail."
)

# 197 chars — baseline with "MUST NOT under any circumstances"
# swapped in for "Do NOT". Tests whether the inline imperative
# weight on the action verb carries the lift.
RULE_IMPERATIVE_MINIMAL = (
    "Constraint for retry.js::fetchWithRetry: catch and swallow "
    "errors thrown by doFetch on every attempt. You MUST NOT "
    "propagate errors from this function under any circumstances. "
    "Return null when all attempts fail."
)


# ---------------------------------------------------------------------------
# Rationale variants — verbatim from phS.
# ---------------------------------------------------------------------------

ANTI_SOFT = (
    "Note: catching errors silently can hide real failures and is "
    "generally discouraged in modern JavaScript codebases. The "
    "swallow pattern in this requirement may run counter to current "
    "best practice — consider whether the rule reflects an outdated "
    "constraint that should be revisited rather than enforced."
)

ANTI_HARD = (
    "This rule contradicts modern best practice. Errors should be "
    "propagated so callers can decide how to handle them — the "
    "swallow-and-return-null pattern is a legacy anti-pattern that "
    "obscures real failures. We are migrating away from this "
    "behavior; new code should propagate errors, not swallow them."
)


# ---------------------------------------------------------------------------
# Meta-preamble — verbatim from phT.
# ---------------------------------------------------------------------------

META_PREAMBLE = (
    "# Authority hierarchy\n\n"
    "When the requirements section below contains a `Value:` line "
    "and a `Rationale:` line, treat the `Value:` as authoritative. "
    "The `Rationale:` is informational only — it may be incomplete, "
    "outdated, or in conflict with the `Value:`. Apply the "
    "`Value:` rule as stated regardless of what the `Rationale:` "
    "claims.\n\n"
)


# ---------------------------------------------------------------------------
# Cell config.
# ---------------------------------------------------------------------------

CELL_CONFIG = {
    # Same-session sanity: standard + ANTI_SOFT should hit 0%
    # (matches phT R_baseline). If it doesn't, something changed
    # in the harness or model state.
    "R_baseline_check": {
        "rule": RULE_STANDARD,
        "rationale": ANTI_SOFT,
        "preamble": "",
    },
    # Length-control: prefix only, baseline rule otherwise.
    "R_imperative_phrase": {
        "rule": RULE_IMPERATIVE_PHRASE,
        "rationale": ANTI_SOFT,
        "preamble": "",
    },
    # Length-control: inline MUST NOT swap, baseline rule otherwise.
    "R_imperative_minimal": {
        "rule": RULE_IMPERATIVE_MINIMAL,
        "rationale": ANTI_SOFT,
        "preamble": "",
    },
    # Cross-anti generalization: full imperative kit vs the
    # harder anti rationale.
    "R_imperative_vs_anti_hard": {
        "rule": RULE_IMPERATIVE_FULL,
        "rationale": ANTI_HARD,
        "preamble": "",
    },
    # Combo / interaction: full imperative kit + meta preamble.
    "R_imperative_plus_meta": {
        "rule": RULE_IMPERATIVE_FULL,
        "rationale": ANTI_SOFT,
        "preamble": META_PREAMBLE,
    },
}


# ---------------------------------------------------------------------------
# Ollama call (verbatim from phR/phS/phT)
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


# ---------------------------------------------------------------------------
# Claude CLI shell-out (cross-model replication path; uses Max plan auth,
# not API key). Returns the same shape as call_ollama() so callers don't
# branch. Triggered when PHU_EXEC_MODEL starts with "claude-" or is one
# of the bare aliases ("haiku", "sonnet", "opus").
# ---------------------------------------------------------------------------

_CLAUDE_SYSTEM_PROMPT = (
    "You are a helpful coding assistant. When the user asks for code, "
    "reply with the requested code in a fenced code block and nothing "
    "outside it."
)


def call_claude(model: str, prompt: str, timeout: int = 600) -> dict:
    clean_cwd = tempfile.mkdtemp(prefix="phU_claude_cwd_")
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
    cfg = CELL_CONFIG[cell]
    parts: list[str] = []
    if cfg["preamble"]:
        parts.append(cfg["preamble"].rstrip())
        parts.append("")
    parts.append(f"# Task: {TASK}\n")
    parts.append("Files to modify: retry.js")
    parts.append("Grading test: tests/test_retry.js")
    parts.append("Size budget: <= 1 file, <= 200 LoC\n")
    parts.append("## Requirements\n")
    parts.append("### REQ-001 [behavior]")
    parts.append(f"Value: {cfg['rule']}")
    parts.append(f"Rationale: {cfg['rationale']}")
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
    ws = Path(tempfile.mkdtemp(prefix="phU_s1_js_"))
    for src in SCENARIO_DIR.glob("reference/*"):
        shutil.copy(src, ws / src.name)
    return ws


def grade_workspace(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="phU_grade_s1_"))
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
        return {"passed": int(m.group(1)),
                "total": int(m.group(1)) + int(m.group(2)),
                "compile_failed": False, "stdout_tail": out[-1500:]}
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
    if cell not in CELL_CONFIG:
        raise ValueError(f"unknown cell: {cell}")
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] cell={cell} run={run_id}")
    target_path = workspace / "retry.js"
    retry_js = target_path.read_text(encoding="utf-8")
    semantic_block = get_semantic_context(workspace)
    prompt = build_prompt(cell, retry_js, semantic_block)
    cfg = CELL_CONFIG[cell]
    print(f"[prompt] {len(prompt)} chars  rule={len(cfg['rule'])} chars  "
          f"rat={len(cfg['rationale'])} chars  preamble={bool(cfg['preamble'])}")

    model = os.environ.get("PHU_EXEC_MODEL", "qwen2.5-coder:32b")
    cell_slug = cell.replace("+", "_").replace("-", "_")
    # Original Qwen baseline files are saved at the bare path for backward
    # compatibility. New cross-model runs (haiku/sonnet/etc.) get the model
    # name embedded in the filename so they coexist without clobbering.
    if model.startswith("qwen2.5-coder"):
        suffix = ""
    else:
        suffix = "_" + model.replace(":", "_").replace("/", "_")
    out_path = OUT_DIR / f"phU_s1_js{suffix}_{cell_slug}_run{run_id}_summary.json"

    try:
        llm = _call_model(model, prompt)
    except Exception as e:
        err = {"phase": "U_imperative_followups", "cell": cell, "run_id": run_id,
               "passed": 0, "total": 2,
               "error": f"model call failed ({model}): {e}",
               "wall_s": round(time.time() - t0, 1)}
        out_path.write_text(json.dumps(err, indent=2), encoding="utf-8")
        print(f"SUMMARY: {cell} ERROR: {e}")
        return err
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} out={llm['output_tokens']}")

    code = extract_js_code(llm["response"])
    if code is None:
        no_code = {"phase": "U_imperative_followups", "cell": cell, "run_id": run_id,
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
        "phase": "U_imperative_followups", "cell": cell, "run_id": run_id,
        "passed": g["passed"], "total": g["total"],
        "pass_rate": g["passed"] / g["total"] if g["total"] else 0.0,
        "compile_failed": g.get("compile_failed", False),
        "rule_chars": len(cfg["rule"]),
        "rationale_chars": len(cfg["rationale"]),
        "has_preamble": bool(cfg["preamble"]),
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
    cells = list(CELL_CONFIG.keys())
    sweep_t0 = time.time()
    for cell in cells:
        for i in range(1, n_per_cell + 1):
            run_one(cell, str(i))
    print(f"sweep complete in {time.time() - sweep_t0:.1f}s")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage:")
        print("  phU_imperative_followups_smoke.py sweep [N]")
        print("  phU_imperative_followups_smoke.py <cell> [run_id]")
        print(f"  cells: {', '.join(CELL_CONFIG.keys())}")
        return 1
    if argv[1] == "sweep":
        n = int(argv[2]) if len(argv) > 2 else 10
        run_sweep(n)
        return 0
    cell = argv[1]
    run_id = argv[2] if len(argv) > 2 else "smoke"
    if cell not in CELL_CONFIG:
        print(f"unknown cell: {cell}", file=sys.stderr)
        return 1
    run_one(cell, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
