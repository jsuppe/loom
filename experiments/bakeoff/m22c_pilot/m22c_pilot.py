#!/usr/bin/env python3
"""
M22c-pilot harness — single-benchmark Dart augmentation-effectiveness
study. Implements the locked design in M22C_PREREGISTRATION.md.

4 arms per scenario:
  no_context     — bare task + workspace (hide rules applied)
  hook_rationale — bare task + style-rationale (leak-score 0)
  hook_fact      — bare task + literal signature contract (upper-bound)
  placebo        — bare task + length-matched irrelevant project text

Grading is 4-bin compile/test (compile_fail / link_fail / test_fail /
test_pass) per the pre-reg. Compile+link pass rate is the PRIMARY
metric for F-hook-rationale falsifier.

Usage:
    python m22c_pilot.py prepare                  # locked plan, dry-run shape
    python m22c_pilot.py run --pilot              # N=24 pilot (2 trials/cell)
    python m22c_pilot.py run --full               # N=60 full sweep (5 trials/cell)
    python m22c_pilot.py run --scenarios s_customer --arms hook_rationale --trials 1
    python m22c_pilot.py analyze
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
RUNS_DIR = _BAKEOFF / "runs-m22c-pilot"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

BENCH_DIR = (
    _BAKEOFF / "benchmarks" / "dart-inventory" / "ground_truth" / "reference"
)
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = os.environ.get("M22C_PILOT_MODEL", "qwen3.5:latest")

ARMS = ("no_context", "hook_rationale", "hook_fact", "placebo")
SEED = 2026


# ---------------------------------------------------------------------------
# Workspace setup — apply per-scenario hide-rules
# ---------------------------------------------------------------------------


def _copy_reference(dest: Path) -> None:
    """Copy the reference Dart project into ``dest``, excluding
    build artifacts."""
    for src in BENCH_DIR.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(BENCH_DIR)
        # Skip build artifacts; we run `dart pub get` once at the end
        # if needed.
        if any(part == ".dart_tool" for part in rel.parts):
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, out)


def setup_workspace(scenario: dict) -> Path:
    """Build a per-scenario trial workspace per the locked hide-rules.

    Returns the workspace path. Caller is responsible for cleanup."""
    ws = Path(tempfile.mkdtemp(prefix=f"m22c_{scenario['scenario_id']}_"))
    _copy_reference(ws)

    # Remove hide_files
    for hide_rel in scenario["hide_files"]:
        target = ws / hide_rel
        if target.exists():
            target.unlink()

    # Strip specific lines from strip_from_files
    for rel, lines_to_drop in scenario.get("strip_from_files", {}).items():
        path = ws / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for needle in lines_to_drop:
            # Drop the line containing the needle (whole line including
            # trailing newline so we don't leave a blank gap).
            new_lines = []
            for line in text.splitlines(keepends=True):
                if needle in line:
                    continue
                new_lines.append(line)
            text = "".join(new_lines)
        path.write_text(text, encoding="utf-8")

    return ws


# ---------------------------------------------------------------------------
# Per-arm prompt builders
# ---------------------------------------------------------------------------

_PLACEBO_POOL_CACHE: list[str] | None = None


def _placebo_pool(this_scenario_id: str) -> list[str]:
    """Style-rationales from OTHER scenarios — used as length-matched
    irrelevant text. Per-scenario exclusion prevents accidental
    semantic overlap."""
    global _PLACEBO_POOL_CACHE
    if _PLACEBO_POOL_CACHE is None:
        data = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
        _PLACEBO_POOL_CACHE = [
            (s["scenario_id"], s["style_rationale"])
            for s in data["scenarios"]
        ]
    return [r for sid, r in _PLACEBO_POOL_CACHE if sid != this_scenario_id]


def _word_count(text: str) -> int:
    return len(text.split())


def _bare_task_block(scenario: dict) -> str:
    """The minimum task block, identical across arms."""
    return (
        f"## Task\n\n"
        f"{scenario['user_request']}\n\n"
        f"Output: respond with the complete Dart source for "
        f"`{scenario['target_file']}` in a single fenced code block, "
        f"no surrounding prose."
    )


def build_no_context_prompt(scenario: dict) -> str:
    return _bare_task_block(scenario)


def build_hook_rationale_prompt(scenario: dict) -> str:
    """Style-rationale (leak-score 0) via system-reminder envelope."""
    return (
        "<system-reminder source=\"loom-context\">\n"
        f"Project convention for this file:\n\n"
        f"{scenario['style_rationale']}\n"
        "</system-reminder>\n\n"
        + _bare_task_block(scenario)
    )


def build_hook_fact_prompt(scenario: dict) -> str:
    """Literal signature contract — the answer-in-prompt upper bound."""
    return (
        "<system-reminder source=\"loom-context\">\n"
        f"Required method signatures for this file:\n\n"
        f"```\n{scenario['fact_signature']}\n```\n"
        "</system-reminder>\n\n"
        + _bare_task_block(scenario)
    )


def build_placebo_prompt(scenario: dict, target_words: int) -> str:
    """Length-matched irrelevant text drawn from other scenarios."""
    pool = _placebo_pool(scenario["scenario_id"])
    rng = random.Random(SEED + hash(scenario["scenario_id"]) % 10_000)
    rng.shuffle(pool)

    # Concatenate, then truncate to target word count
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
    """All four arm prompts. Placebo length-matched to hook_rationale's
    preamble word count."""
    no_ctx = build_no_context_prompt(scenario)
    rationale = build_hook_rationale_prompt(scenario)
    fact = build_hook_fact_prompt(scenario)
    rationale_preamble_words = _word_count(rationale) - _word_count(no_ctx)
    placebo = build_placebo_prompt(scenario, max(20, rationale_preamble_words))
    # Iterate once to converge length-match
    measured = _word_count(placebo)
    adjust = rationale_preamble_words + (rationale_preamble_words - (measured - _word_count(no_ctx)))
    placebo = build_placebo_prompt(scenario, max(20, adjust))
    return {
        "no_context": no_ctx,
        "hook_rationale": rationale,
        "hook_fact": fact,
        "placebo": placebo,
    }


# ---------------------------------------------------------------------------
# Ollama call
# ---------------------------------------------------------------------------


def call_ollama(model: str, prompt: str, timeout: int = 300) -> dict:
    sampling = {
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": 1,
        "seed": 42,
        "repeat_penalty": 1.0,
        # M22c — cap output so runaway generations don't game the
        # grader (M22a F3 lesson: empty-response on hitting the
        # context window). Dart service files are ~80 LoC = ~1500
        # tokens; 4096 gives 2.5x headroom for verbose comments.
        "num_predict": 4096,
    }
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "keep_alive": "30m",
        # qwen3.5 defaults to reasoning mode; disable so the output
        # tokens land in `response` instead of internal `thinking`
        # (otherwise num_predict is consumed by reasoning and the
        # answer never materializes — M22c smoke-test finding).
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
# Code extraction + grading (4-bin compile/test outcome)
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:dart)?\s*\n(.*?)\n```", re.DOTALL)


def extract_dart_code(response: str) -> str | None:
    m = _FENCE_RE.search(response)
    if not m:
        return None
    return m.group(1).strip()


def _parse_dart_test_output(stdout: str, stderr: str, returncode: int) -> dict:
    """Classify a dart-test run into the 4-bin compile/test outcome.

    Heuristics:
    * compile_fail — analyzer/compiler error keywords in stderr
    * link_fail    — runtime undefined symbol / NoSuchMethodError
    * test_fail    — tests ran but ≥1 failed
    * test_pass    — all passed
    """
    out = (stdout or "") + "\n" + (stderr or "")
    # Count passed/failed from dart test output
    passed_m = re.search(r"\+(\d+)", out)
    failed_m = re.search(r"-(\d+)", out)
    passed = int(passed_m.group(1)) if passed_m else 0
    failed = int(failed_m.group(1)) if failed_m else 0

    # Compile errors
    compile_indicators = (
        "Error: ", "Compilation failed", "error • ",
        "Try changing the type", "Undefined name",
    )
    has_compile_error = any(ind in out for ind in compile_indicators)
    # Link / runtime undefined symbol
    link_indicators = (
        "NoSuchMethodError", "Class 'Null' has no instance method",
        "isn't defined", "is not defined for the class",
    )
    has_link_error = any(ind in out for ind in link_indicators)

    # Priority: compile errors first (Dart's "isn't a type" / "Undefined
    # name" can produce a spurious failed-test count from the loader; we
    # don't want that masquerading as link/test failure).
    if has_compile_error and passed == 0:
        bin_ = "compile_fail"
    elif has_link_error and passed == 0:
        bin_ = "link_fail"
    elif passed > 0 and failed == 0 and returncode == 0:
        bin_ = "test_pass"
    elif failed > 0 or returncode != 0:
        bin_ = "test_fail"
    else:
        bin_ = "test_fail"  # default for ambiguous

    return {
        "bin": bin_,
        "passed": passed,
        "failed": failed,
        "returncode": returncode,
        "compile_plus_link_pass": bin_ in ("test_fail", "test_pass"),
        "stdout_tail": out[-1500:],
    }


def grade_workspace(ws: Path, scenario: dict) -> dict:
    """Run `dart test test/shop_test.dart` in the workspace.

    Returns the 4-bin classification + sub-test counts. The
    `shop_test.dart` file was hidden during workspace setup but we
    bring it back ONLY for grading (the model never saw it)."""
    # Re-add the test file from the reference for grading
    test_src = BENCH_DIR / "test" / "shop_test.dart"
    test_dest = ws / "test" / "shop_test.dart"
    test_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(test_src, test_dest)

    # Need pub get for the first run in a fresh workspace
    try:
        subprocess.run(
            ["dart", "pub", "get"], cwd=ws, capture_output=True,
            timeout=60, text=True, encoding="utf-8", errors="replace",
            shell=(sys.platform == "win32"),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {
            "bin": "compile_fail",
            "passed": 0, "failed": 0, "returncode": -1,
            "compile_plus_link_pass": False,
            "stdout_tail": f"pub get failed: {e}",
        }

    try:
        proc = subprocess.run(
            ["dart", "test", "test/shop_test.dart"],
            cwd=ws, capture_output=True, timeout=120,
            text=True, encoding="utf-8", errors="replace",
            shell=(sys.platform == "win32"),
        )
    except subprocess.TimeoutExpired as e:
        return {
            "bin": "test_fail",
            "passed": 0, "failed": 0, "returncode": -1,
            "compile_plus_link_pass": False,
            "stdout_tail": f"timeout after 120s: {e}",
        }
    return _parse_dart_test_output(
        proc.stdout, proc.stderr, proc.returncode,
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

    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        err = {
            "study": "m22c-pilot",
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
    code = extract_dart_code(response)

    # Retain raw output (M18.3)
    trial_id = f"m22c_{sid}_{arm}_t{trial_n}"
    raw_path = retain_output(RUNS_DIR, trial_id, response)

    # Grade — set up workspace, write the model's code to target file,
    # run dart test
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
                "passed": 0, "failed": 0, "returncode": -1,
                "compile_plus_link_pass": False,
                "stdout_tail": "no_code_extracted",
            }
    finally:
        shutil.rmtree(ws, ignore_errors=True)

    sampling_recorded = {
        "model": model,
        **(llm.get("sampling_options") or {}),
    }
    drift_msgs = sampling_drift(sampling_recorded)

    summary = {
        "study": "m22c-pilot",
        "scenario_id": sid,
        "arm": arm,
        "trial_n": trial_n,
        "model": model,
        # Grading
        "outcome_bin": grade["bin"],
        "compile_plus_link_pass": grade["compile_plus_link_pass"],
        "sub_passed": grade["passed"],
        "sub_failed": grade["failed"],
        "returncode": grade["returncode"],
        "no_code_extracted": code is None,
        # M18.2
        "sampling_options": llm.get("sampling_options"),
        "sampling_recorded": sampling_recorded,
        "sampling_drift": drift_msgs,
        # M18.3
        "raw_output_path": (
            str(raw_path.relative_to(RUNS_DIR)) if raw_path else None
        ),
        # Volumetrics
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
    print(f"M22c-pilot: {len(scenarios)} scenarios × {len(arms)} arms × "
          f"{trials_per_cell} trials = {total} trials on {model}")
    print(f"Output: {RUNS_DIR}")
    print()

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
                  f"pass={result['sub_passed']}/{result['sub_passed']+result['sub_failed']} "
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

    print(f"=== M22c-pilot analysis (n={len(trials)} trials) ===\n")

    # Per-arm bin distribution
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

    # Paired McNemar on compile+link pass rate (PRIMARY)
    print("\n=== Paired McNemar on compile+link pass (PRIMARY) ===")
    by_arm_pair = {
        arm: {(t["scenario_id"], t["trial_n"]): t["compile_plus_link_pass"]
              for t in by_arm.get(arm, [])}
        for arm in ARMS
    }
    pairs = [
        ("hook_rationale", "placebo"),       # F-hook-rationale PRIMARY
        ("hook_rationale", "no_context"),
        ("hook_fact", "placebo"),            # upper-bound descriptive
        ("hook_fact", "hook_rationale"),
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
                       help="N=24 (3 scenarios × 4 arms × 2 trials)")
    p_run.add_argument("--full", action="store_true",
                       help="N=60 (3 scenarios × 4 arms × 5 trials)")
    p_run.add_argument("--scenarios", nargs="*",
                       help="filter scenarios (default: all)")
    p_run.add_argument("--arms", nargs="*",
                       help="filter arms (default: all 4)")
    p_run.add_argument("--trials", type=int, default=None,
                       help="trials per (scenario,arm) cell")
    p_run.add_argument("--model", default=None)

    def _run(a):
        trials = a.trials
        if trials is None:
            trials = 2 if a.pilot else (5 if a.full else 1)
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
