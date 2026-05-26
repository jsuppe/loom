#!/usr/bin/env python3
"""
M22e-pilot harness — single-file JS/TS confound-elimination study.
Implements the locked design in M22E_PREREGISTRATION.md.

4 arms per scenario:
  no_context     — task + explicit import_block (layout fixed)
  hook_rationale — task + import_block + style-rationale envelope
  hook_fact      — task + import_block + literal signature envelope
  placebo        — task + import_block + length-matched irrelevant text

The import_block is identical across all arms — this operationalizes
the confound-elimination framing (layout is constant, only the
rationale/fact/placebo envelope varies).

4-bin compile/test outcome:
  compile_fail — node --check rejects OR test loader throws on import
  link_fail    — file loads but runtime undefined symbol
  test_fail    — runs but ≥1 sub-test fails (or <N-1 pass)
  test_pass    — ≥N-1 sub-tests pass and rc=0

Compile+link pass rate is the PRIMARY metric (paired McNemar) per
the pre-reg, identical to M22c.

Usage:
    python m22e_pilot.py prepare
    python m22e_pilot.py run --pilot              # N=24 (3 × 4 × 2)
    python m22e_pilot.py run --full               # N=120 (3 × 4 × 10)
    python m22e_pilot.py run --scenarios s_validate --arms hook_rationale --trials 1
    python m22e_pilot.py analyze
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BAKEOFF = _HERE.parent
_REPO = _BAKEOFF.parent.parent
sys.path.insert(0, str(_BAKEOFF))

from _methodology import (  # noqa: E402
    retain_output,
    sampling_drift,
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCENARIOS_PATH = _HERE / "scenarios.json"
RUNS_DIR = _BAKEOFF / "runs-m22e-pilot"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

BENCH_DIR = _BAKEOFF / "benchmarks" / "js-singlefile"
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = os.environ.get("M22E_PILOT_MODEL", "qwen3.5:latest")

ARMS = ("no_context", "hook_rationale", "hook_fact", "placebo")
SEED = 2026


# ---------------------------------------------------------------------------
# Workspace setup — apply per-scenario hide-rules
# ---------------------------------------------------------------------------


def _copy_reference(dest: Path) -> None:
    for src in BENCH_DIR.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(BENCH_DIR)
        if any(part == "node_modules" for part in rel.parts):
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, out)


def setup_workspace(scenario: dict) -> Path:
    """Per-scenario trial workspace with hide-rules applied."""
    ws = Path(tempfile.mkdtemp(prefix=f"m22e_{scenario['scenario_id']}_"))
    _copy_reference(ws)

    for hide_rel in scenario["hide_files"]:
        target = ws / hide_rel
        if target.exists():
            target.unlink()

    return ws


# ---------------------------------------------------------------------------
# Per-arm prompt builders
# ---------------------------------------------------------------------------

# Task-orthogonal project-notes pool (M22e harness fix discovered in
# smoke test): drawing the placebo from OTHER scenarios' rationales
# semantically interferes — e.g. s_retry's "retriable vs terminal"
# framing made the model ramble in comments forever when applied to
# s_validate. Replace with truly task-orthogonal style notes about
# CI/repo/formatting that resemble project-conventions text in shape
# but cannot apply to any of the three target functions. Documented
# in M22E_PREREGISTRATION_AMENDMENTS.md.
_NEUTRAL_PROJECT_NOTES = (
    "Files use 2-space indentation and JSDoc-style comments. "
    "The CI pipeline runs prettier in --check mode and ESLint with the "
    "recommended ruleset; pre-commit hooks lint staged files. "
    "Test coverage thresholds are enforced at 80% line, 70% branch via "
    "c8. The release workflow uses changesets for semver bumps and "
    "publishes to the internal npm registry on tag push. "
    "Dependencies are pinned via package-lock.json and renovate "
    "auto-PRs minor bumps weekly. Engineers run `npm test` locally "
    "before pushing; the repo has a .nvmrc pinned to Node 22 LTS. "
    "The CONTRIBUTING.md asks contributors to open an issue before "
    "large refactors and to keep PRs under 400 lines of diff. "
    "Code review uses CODEOWNERS for module-level approvers; release "
    "branches follow conventional commit messages for changelog "
    "generation. The benchmark suite runs nightly in a separate job."
)


def _placebo_pool(this_scenario_id: str) -> list[str]:
    # Task-orthogonal; identical pool for every scenario so length-
    # matching behaves deterministically regardless of scenario.
    return [_NEUTRAL_PROJECT_NOTES]


def _word_count(text: str) -> int:
    return len(text.split())


def _bare_task_block(scenario: dict) -> str:
    """Task block — IDENTICAL across all 4 arms. Includes the
    layout-explicit import_block (confound-elimination operationalized)."""
    return (
        f"## Task\n\n"
        f"{scenario['user_request']}\n\n"
        f"The file `{scenario['target_file']}` will be loaded by tests that "
        f"import it like this:\n\n"
        f"```js\n{scenario['import_block']}\n```\n\n"
        f"Output: respond with the complete JavaScript source for "
        f"`{scenario['target_file']}` in a single fenced ```js code block, "
        f"no surrounding prose."
    )


def build_no_context_prompt(scenario: dict) -> str:
    return _bare_task_block(scenario)


def build_hook_rationale_prompt(scenario: dict) -> str:
    return (
        "<system-reminder source=\"loom-context\">\n"
        f"Project convention for this file:\n\n"
        f"{scenario['style_rationale']}\n"
        "</system-reminder>\n\n"
        + _bare_task_block(scenario)
    )


def build_hook_fact_prompt(scenario: dict) -> str:
    return (
        "<system-reminder source=\"loom-context\">\n"
        f"Required exports for this file:\n\n"
        f"```\n{scenario['fact_signature']}\n```\n"
        "</system-reminder>\n\n"
        + _bare_task_block(scenario)
    )


def build_placebo_prompt(scenario: dict, target_words: int) -> str:
    pool = _placebo_pool(scenario["scenario_id"])
    rng = random.Random(SEED + hash(scenario["scenario_id"]) % 10_000)
    rng.shuffle(pool)
    stream = " ".join(pool).split()
    body = " ".join(stream[:target_words]) if stream else "no notes"
    return (
        "<system-reminder source=\"project-notes\">\n"
        f"Background notes from other parts of the project:\n\n"
        f"{body}\n"
        "</system-reminder>\n\n"
        + _bare_task_block(scenario)
    )


def build_arm_prompts(scenario: dict) -> dict[str, str]:
    no_ctx = build_no_context_prompt(scenario)
    rationale = build_hook_rationale_prompt(scenario)
    fact = build_hook_fact_prompt(scenario)
    target_words = _word_count(rationale) - _word_count(no_ctx)
    placebo = build_placebo_prompt(scenario, max(20, target_words))
    measured = _word_count(placebo) - _word_count(no_ctx)
    if measured != target_words:
        adjust = target_words + (target_words - measured)
        placebo = build_placebo_prompt(scenario, max(20, adjust))
    return {
        "no_context": no_ctx,
        "hook_rationale": rationale,
        "hook_fact": fact,
        "placebo": placebo,
    }


# ---------------------------------------------------------------------------
# Ollama call (carry-forward from m22c_pilot)
# ---------------------------------------------------------------------------


def call_ollama(model: str, prompt: str, trial_seed: int,
                 timeout: int = 300) -> dict:
    sampling = {
        # Amendment 2 (see M22E_PREREGISTRATION_AMENDMENTS.md):
        # temp=0 + fixed seed makes t1 bit-identical to t2…tN,
        # collapsing the planned N=120 sweep to N=12 unique outcomes
        # and reducing McNemar paired-pairs to 3 per arm-pair (under-
        # powered for any realistic effect size). M22c's temp=0 was
        # an unstated harness convention that didn't matter at 0%
        # floor but is a study-killer at single-file granularity.
        # Modest temperature + per-trial seed restores meaningful N
        # without abandoning reproducibility (each trial is replayable
        # from its seed).
        "temperature": 0.3,
        "top_p": 0.9,
        "top_k": 40,
        "seed": trial_seed,
        "repeat_penalty": 1.0,
        # JS source files are smaller than Dart multi-file output;
        # 4096 tokens is still comfortable headroom.
        "num_predict": 4096,
    }
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "keep_alive": "30m",
        # qwen3.5 reasoning mode otherwise eats num_predict — m22c lesson.
        "think": False,
        "options": sampling,
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {
        "response": data.get("response", ""),
        "elapsed_s": time.time() - t0,
        "input_tokens": data.get("prompt_eval_count", 0),
        "output_tokens": data.get("eval_count", 0),
        "sampling_options": sampling,
    }


# ---------------------------------------------------------------------------
# Code extraction + grading
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"```(?:js|javascript|jsx|node)?\s*\n(.*?)\n```",
    re.DOTALL,
)


def extract_js_code(response: str) -> str | None:
    m = _FENCE_RE.search(response)
    if not m:
        return None
    return m.group(1).strip()


def _parse_node_test_output(stdout: str, stderr: str, returncode: int,
                             expected_sub_tests: int) -> dict:
    """Classify a node --test run into the 4-bin compile/test outcome.

    Node test output uses TAP-ish format with these counters:
      ℹ tests N      → total
      ℹ pass  N      → passed
      ℹ fail  N      → failed
    A SyntaxError / ReferenceError on import surfaces in stderr.
    """
    out = (stdout or "") + "\n" + (stderr or "")

    # Counters
    pass_m = re.search(r"^\s*[ℹi]\s*pass\s+(\d+)", out, re.MULTILINE)
    fail_m = re.search(r"^\s*[ℹi]\s*fail\s+(\d+)", out, re.MULTILINE)
    passed = int(pass_m.group(1)) if pass_m else 0
    failed = int(fail_m.group(1)) if fail_m else 0

    compile_indicators = (
        "SyntaxError",
        "Cannot find module",
        "Unexpected token",
        "Unexpected identifier",
        "ERR_MODULE_NOT_FOUND",
    )
    link_indicators = (
        "is not a function",
        "is not defined",
        "is not a constructor",
        "Cannot read properties of undefined",
        "TypeError: undefined is not",
    )
    has_compile_error = any(ind in out for ind in compile_indicators)
    has_link_error = any(ind in out for ind in link_indicators)

    # Priority: compile errors first (they often prevent tests from
    # registering at all so passed/failed counts can be 0/0).
    if has_compile_error and passed == 0:
        bin_ = "compile_fail"
    elif has_link_error and passed == 0:
        bin_ = "link_fail"
    elif passed >= (expected_sub_tests - 1) and failed == 0 and returncode == 0:
        bin_ = "test_pass"
    elif failed > 0 or returncode != 0:
        bin_ = "test_fail"
    elif passed > 0:
        # Some passed but not enough to count as test_pass
        bin_ = "test_fail"
    else:
        bin_ = "test_fail"

    return {
        "bin": bin_,
        "passed": passed,
        "failed": failed,
        "expected": expected_sub_tests,
        "returncode": returncode,
        "compile_plus_link_pass": bin_ in ("test_fail", "test_pass"),
        "stdout_tail": out[-1500:],
    }


def grade_workspace(ws: Path, scenario: dict) -> dict:
    """Re-add the oracle test file (model never saw it) and run it."""
    test_src = BENCH_DIR / scenario["test_file"]
    test_dest = ws / scenario["test_file"]
    test_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(test_src, test_dest)

    try:
        proc = subprocess.run(
            ["node", "--test", scenario["test_file"]],
            cwd=ws, capture_output=True, timeout=60,
            text=True, encoding="utf-8", errors="replace",
            shell=(sys.platform == "win32"),
        )
    except subprocess.TimeoutExpired as e:
        return {
            "bin": "test_fail",
            "passed": 0, "failed": 0,
            "expected": scenario.get("expected_sub_tests", 0),
            "returncode": -1,
            "compile_plus_link_pass": False,
            "stdout_tail": f"timeout after 60s: {e}",
        }
    except FileNotFoundError as e:
        return {
            "bin": "compile_fail",
            "passed": 0, "failed": 0,
            "expected": scenario.get("expected_sub_tests", 0),
            "returncode": -1,
            "compile_plus_link_pass": False,
            "stdout_tail": f"node not found: {e}",
        }
    return _parse_node_test_output(
        proc.stdout, proc.stderr, proc.returncode,
        scenario.get("expected_sub_tests", 20),
    )


# ---------------------------------------------------------------------------
# Trial runner
# ---------------------------------------------------------------------------


def trial_path(sid: str, arm: str, trial_n: int) -> Path:
    return RUNS_DIR / f"trial_{sid}_{arm}_t{trial_n}_summary.json"


def run_trial(scenario: dict, arm: str, trial_n: int, model: str) -> dict:
    sid = scenario["scenario_id"]
    out_path = trial_path(sid, arm, trial_n)
    t0 = time.time()

    prompts = build_arm_prompts(scenario)
    prompt = prompts[arm]

    # Per-trial seed: deterministic from (scenario, arm, trial_n)
    # so re-runs replay the same outputs, but distinct across trials
    # so within-cell variance is real (Amendment 2).
    trial_seed = (
        abs(hash((sid, arm, trial_n))) % (2**31 - 1)
    )

    try:
        llm = call_ollama(model, prompt, trial_seed=trial_seed)
    except Exception as e:
        err = {
            "study": "m22e-pilot",
            "scenario_id": sid, "arm": arm, "trial_n": trial_n,
            "model": model,
            "error": f"{type(e).__name__}: {e}",
            "wall_s": round(time.time() - t0, 1),
        }
        out_path.write_text(
            json.dumps(err, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        return err

    response = llm["response"]
    code = extract_js_code(response)

    trial_id = f"m22e_{sid}_{arm}_t{trial_n}"
    raw_path = retain_output(RUNS_DIR, trial_id, response)

    ws = setup_workspace(scenario)
    try:
        if code:
            target = ws / scenario["target_file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code, encoding="utf-8")
            grade = grade_workspace(ws, scenario)
        else:
            grade = {
                "bin": "compile_fail",
                "passed": 0, "failed": 0,
                "expected": scenario.get("expected_sub_tests", 0),
                "returncode": -1,
                "compile_plus_link_pass": False,
                "stdout_tail": "no_code_extracted",
            }
    finally:
        shutil.rmtree(ws, ignore_errors=True)

    sampling_recorded = {
        "model": model, **(llm.get("sampling_options") or {}),
    }
    drift_msgs = sampling_drift(sampling_recorded)

    summary = {
        "study": "m22e-pilot",
        "scenario_id": sid,
        "arm": arm,
        "trial_n": trial_n,
        "model": model,
        "outcome_bin": grade["bin"],
        "compile_plus_link_pass": grade["compile_plus_link_pass"],
        "sub_passed": grade["passed"],
        "sub_failed": grade["failed"],
        "sub_expected": grade["expected"],
        "returncode": grade["returncode"],
        "no_code_extracted": code is None,
        "sampling_options": llm.get("sampling_options"),
        "sampling_recorded": sampling_recorded,
        "sampling_drift": drift_msgs,
        "raw_output_path": (
            str(raw_path.relative_to(RUNS_DIR)) if raw_path else None
        ),
        "input_tokens": llm["input_tokens"],
        "output_tokens": llm["output_tokens"],
        "llm_elapsed_s": round(llm["elapsed_s"], 1),
        "wall_s": round(time.time() - t0, 1),
        "grade_stdout_tail": grade["stdout_tail"],
    }
    out_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return summary


def run_all(scenarios_filter: set[str] | None = None,
            arms_filter: set[str] | None = None,
            trials_per_cell: int = 5,
            model: str | None = None) -> None:
    data = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    scenarios = data["scenarios"]
    if scenarios_filter:
        scenarios = [s for s in scenarios if s["scenario_id"] in scenarios_filter]
    arms = list(arms_filter) if arms_filter else list(ARMS)
    model = model or DEFAULT_MODEL

    plan = [
        (sc, arm, n)
        for sc in scenarios
        for arm in arms
        for n in range(1, trials_per_cell + 1)
    ]
    random.Random(SEED + 1).shuffle(plan)

    total = len(plan)
    print(f"M22e-pilot: {len(scenarios)} scenarios × {len(arms)} arms × "
          f"{trials_per_cell} trials = {total} trials on {model}")
    print(f"Output: {RUNS_DIR}\n")

    done = sum(
        1 for sc, arm, n in plan
        if trial_path(sc["scenario_id"], arm, n).exists()
    )
    print(f"Already complete: {done}/{total} (resume mode)\n")

    t_sweep = time.time()
    completed = 0
    for i, (sc, arm, n) in enumerate(plan, 1):
        sid = sc["scenario_id"]
        out_path = trial_path(sid, arm, n)
        if out_path.exists():
            continue
        print(f"[{i}/{total}] {sid:12s} | {arm:15s} | t{n}", flush=True)
        result = run_trial(sc, arm, n, model)
        completed += 1
        if result.get("error"):
            print(f"    ✗ ERROR: {result['error']}")
        else:
            mark = "✓" if result["compile_plus_link_pass"] else "✗"
            print(f"    {mark} bin={result['outcome_bin']:13s} "
                  f"pass={result['sub_passed']}/"
                  f"{result['sub_passed']+result['sub_failed']} "
                  f"wall={result['wall_s']}s")

    print(f"\nSweep complete. {completed} new trials in {time.time()-t_sweep:.0f}s.")


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p_hat = k / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    spread = z * ((p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) ** 0.5) / denom
    return (max(0, center - spread), min(1, center + spread))


def mcnemar_exact(a_only: int, b_only: int) -> float:
    from math import comb
    n = a_only + b_only
    if n == 0:
        return 1.0
    k = min(a_only, b_only)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def analyze() -> None:
    trials = []
    for p in sorted(RUNS_DIR.glob("trial_*_summary.json")):
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
            if not t.get("error"):
                trials.append(t)
        except json.JSONDecodeError:
            continue

    print(f"=== M22e-pilot analysis (n={len(trials)} trials) ===\n")

    by_arm = defaultdict(list)
    for t in trials:
        by_arm[t["arm"]].append(t)

    print(f"{'arm':16s} {'n':4s} {'comp_fail':10s} {'link_fail':10s} {'test_fail':10s} {'test_pass':10s} {'C+L_pass%':10s}")
    for arm in ARMS:
        ts = by_arm.get(arm, [])
        if not ts:
            continue
        counts = Counter(t["outcome_bin"] for t in ts)
        cplus = sum(1 for t in ts if t["compile_plus_link_pass"])
        lo, hi = wilson_ci(cplus, len(ts))
        print(f"{arm:16s} {len(ts):4d} "
              f"{counts.get('compile_fail',0):10d} "
              f"{counts.get('link_fail',0):10d} "
              f"{counts.get('test_fail',0):10d} "
              f"{counts.get('test_pass',0):10d} "
              f"{cplus/len(ts)*100:7.1f}% "
              f"CI[{lo*100:.0f},{hi*100:.0f}]")

    print("\n=== Paired McNemar on compile+link pass (PRIMARY) ===")
    by_arm_pair = {
        arm: {(t["scenario_id"], t["trial_n"]): t["compile_plus_link_pass"]
              for t in by_arm.get(arm, [])}
        for arm in ARMS
    }
    pairs = [
        ("hook_rationale", "placebo"),
        ("hook_rationale", "no_context"),
        ("hook_fact", "placebo"),
        ("hook_fact", "hook_rationale"),
        ("hook_fact", "no_context"),
        ("placebo", "no_context"),
    ]
    for a, b in pairs:
        keys = set(by_arm_pair[a]) & set(by_arm_pair[b])
        a_only = sum(1 for k in keys if by_arm_pair[a][k] and not by_arm_pair[b][k])
        b_only = sum(1 for k in keys if by_arm_pair[b][k] and not by_arm_pair[a][k])
        both = sum(1 for k in keys if by_arm_pair[a][k] and by_arm_pair[b][k])
        neither = sum(1 for k in keys if not by_arm_pair[a][k] and not by_arm_pair[b][k])
        a_rate = (a_only + both) / len(keys) if keys else 0
        b_rate = (b_only + both) / len(keys) if keys else 0
        p = mcnemar_exact(a_only, b_only)
        print(f"  {a:15s} vs {b:15s} | n_pairs={len(keys):3d} | "
              f"{a_rate*100:5.1f}% vs {b_rate*100:5.1f}% | "
              f"Δ={(a_rate-b_rate)*100:+5.1f}pp | "
              f"a={a_only} b={b_only} both={both} neither={neither} | "
              f"p_exact={p:.4f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare")
    p_prep.set_defaults(fn=lambda a: print(
        f"Scenarios: {len(json.loads(SCENARIOS_PATH.read_text(encoding='utf-8'))['scenarios'])}\n"
        f"Arms: {ARMS}\n"
        f"Workspace: temp dirs per trial\n"
        f"Output: {RUNS_DIR}"))

    p_run = sub.add_parser("run")
    p_run.add_argument("--pilot", action="store_true",
                       help="N=24 (3 × 4 × 2)")
    p_run.add_argument("--full", action="store_true",
                       help="N=120 (3 × 4 × 10)")
    p_run.add_argument("--scenarios", nargs="*")
    p_run.add_argument("--arms", nargs="*")
    p_run.add_argument("--trials", type=int, default=None)
    p_run.add_argument("--model", default=None)

    def _run(a):
        trials = a.trials
        if trials is None:
            trials = 2 if a.pilot else (10 if a.full else 1)
        run_all(
            scenarios_filter=set(a.scenarios) if a.scenarios else None,
            arms_filter=set(a.arms) if a.arms else None,
            trials_per_cell=trials, model=a.model,
        )
    p_run.set_defaults(fn=_run)

    p_an = sub.add_parser("analyze")
    p_an.set_defaults(fn=lambda a: analyze())

    args = ap.parse_args()
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
