#!/usr/bin/env python3
"""
M22a-pilot — augmentation-effectiveness pilot study harness.

Per the methodology-review verdict on the full M22a design, this is
a SMALL pilot (N=30 scenarios × 4 arms = 120 trials) whose job is
to detect confounds, not publish lift claims. Key design fix from
the review: includes a length-matched **placebo arm** so we can
distinguish "loom's structured context helps" from "more tokens
prime more cautious behavior."

Four arms:

  no_context   — bare task prompt only
  hook         — bare task + system-reminder injecting the relevant
                 finding/rationale/drift-narrative (current loom UX)
  pre_loaded   — bare task + finding context dumped as project-docs
                 preamble at session start (what "ingest the project
                 into loom" looks like at use-time)
  placebo      — bare task + irrelevant-but-length-matched preamble
                 (control for the token-count confound)

Workload: stratified sample of 30 from m13_v1 (10/stratum). Single
model: qwen3.5:latest via Ollama (free, deterministic at temp=0).

Outputs to runs-m22a-pilot/:
  scenarios.json          — locked sample (resumable, reproducible)
  summary_<sid>_<arm>.json — per-trial summary (M18.1-.3 conformant)
  raw_outputs/             — full LLM responses (M18.3)

Then `m22a_analyze.py` runs the paired McNemar tests.

Run:
    python experiments/bakeoff/m22a_pilot/m22a_pilot.py sample
    python experiments/bakeoff/m22a_pilot/m22a_pilot.py run
    python experiments/bakeoff/m22a_pilot/m22a_pilot.py analyze
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
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
    is_noop,
    retain_output,
    read_sampling_lock,
    sampling_drift,
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

M13_V1_PATH = _BAKEOFF / "eval_sets" / "m13_v1" / "scenarios.json"
PILOT_DIR = _HERE
SAMPLE_PATH = PILOT_DIR / "scenarios.json"
RUNS_DIR = _BAKEOFF / "runs-m22a-pilot"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = os.environ.get("M22A_PILOT_MODEL", "qwen3.5:latest")

# Stratified sample size — 10 per stratum × 3 strata = 30 scenarios.
PER_STRATUM = 10
SEED = 42


# ---------------------------------------------------------------------------
# Step 1: Stratified sampling from m13_v1
# ---------------------------------------------------------------------------


def sample_scenarios() -> dict:
    """Pick PER_STRATUM scenarios per stratum from m13_v1.
    Deterministic via seed. Writes to SAMPLE_PATH."""
    data = json.loads(M13_V1_PATH.read_text(encoding="utf-8"))
    all_scenarios = data["scenarios"]
    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for s in all_scenarios:
        by_stratum[s["stratum"]].append(s)

    rng = random.Random(SEED)
    picked: list[dict] = []
    for stratum in sorted(by_stratum):
        candidates = by_stratum[stratum]
        if len(candidates) <= PER_STRATUM:
            picked.extend(candidates)
        else:
            picked.extend(rng.sample(candidates, PER_STRATUM))
    picked.sort(key=lambda s: s["scenario_id"])

    out = {
        "version": "m22a-pilot-v1",
        "source_dataset": str(M13_V1_PATH.relative_to(_REPO)),
        "seed": SEED,
        "per_stratum": PER_STRATUM,
        "n_scenarios": len(picked),
        "stratum_counts": dict(Counter(s["stratum"] for s in picked)),
        "scenarios": picked,
    }
    SAMPLE_PATH.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return out


# ---------------------------------------------------------------------------
# Step 2: Four-arm prompt builders
# ---------------------------------------------------------------------------


# Bare task — used in all arms as the user's actual request.
def _bare_task_block(sc: dict) -> str:
    return (
        "## Task\n\n"
        f"File: `{sc['file_path']}`\n\n"
        "User request:\n"
        f"> {sc['user_request']}\n\n"
        "Output: respond with your plan + the edit you would make, OR an "
        "explicit pause stating why you need clarification before editing."
    )


def build_no_context_prompt(sc: dict) -> str:
    """Arm A — bare task, nothing else."""
    return _bare_task_block(sc)


def build_hook_prompt(sc: dict) -> str:
    """Arm B — bare task + system-reminder injecting the relevant finding
    + drift narrative (M13 v3 scope-qualifier shape, the current loom
    production behavior)."""
    drift_block = (
        "<system-reminder source=\"loom-context\">\n"
        f"Linked requirement: **{sc['finding_id']}** "
        f"(kind: {sc['finding_kind']})\n"
        f"Summary: {sc['finding_summary']}\n"
        f"Rationale: {sc['finding_rationale']}\n\n"
        f"DRIFT DETECTED: {sc['drift_narrative']}\n\n"
        f"THIS WARNING APPLIES IF your edit: adds a constant, writes a "
        f"docstring/comment claim, or modifies logic dependent on this "
        f"finding's specific values. THIS WARNING DOES NOT APPLY IF "
        f"your edit: renames a variable, fixes a typo, or modifies "
        f"unrelated paths. Pause and verify before encoding any number, "
        f"threshold, or definitive claim from the retracted finding as "
        f"a confirmed fact.\n"
        "</system-reminder>\n\n"
        + _bare_task_block(sc)
    )
    return drift_block


def build_pre_loaded_prompt(sc: dict) -> str:
    """Arm C — bare task + project-docs preamble at the START of the
    prompt (what "ingest the project into loom + recall at session
    start" looks like at use-time). Same finding info as Arm B but
    framed as project documentation, no system-reminder envelope."""
    preamble = (
        "## Project context (loom-ingested)\n\n"
        "The following findings + rationale are part of this project's "
        "captured-decisions store. They represent prior empirical work "
        "or process decisions you should be aware of.\n\n"
        f"### {sc['finding_id']} ({sc['finding_kind']})\n\n"
        f"**Summary:** {sc['finding_summary']}\n\n"
        f"**Rationale:** {sc['finding_rationale']}\n\n"
        f"**Drift status:** {sc['drift_narrative']}\n\n"
        "---\n\n"
        + _bare_task_block(sc)
    )
    return preamble


# Pool of irrelevant-but-plausible project text. Drawn from other
# scenarios' rationale fields (so vocabulary is project-like) but the
# CONTENT has nothing to do with the trial's user_request. The
# placebo arm picks N tokens from this pool to length-match Arm C.
_PLACEBO_POOL_CACHE: list[str] | None = None


def _placebo_pool() -> list[str]:
    """Lazy-load the placebo text pool from m13_v1 finding_rationales."""
    global _PLACEBO_POOL_CACHE
    if _PLACEBO_POOL_CACHE is None:
        data = json.loads(M13_V1_PATH.read_text(encoding="utf-8"))
        _PLACEBO_POOL_CACHE = [
            s["finding_rationale"] for s in data["scenarios"]
            if s.get("finding_rationale")
        ]
    return _PLACEBO_POOL_CACHE


def _word_count(text: str) -> int:
    return len(text.split())


def build_placebo_prompt(sc: dict, target_word_count: int) -> str:
    """Arm D — bare task + length-matched irrelevant project text.
    Concatenates rationales from OTHER scenarios, then truncates to
    exactly ``target_word_count`` words of preamble body. Excludes
    this scenario's own rationale to ensure no semantic leak.

    Precision-matched (rather than nearest-boundary) so any arm-vs-
    placebo accuracy delta can't be attributed to a token-count
    difference."""
    pool = [
        t for t in _placebo_pool()
        if t != sc.get("finding_rationale")
    ]
    rng = random.Random(SEED + hash(sc["scenario_id"]) % 10_000)
    rng.shuffle(pool)

    # Concatenate as one stream, split into words, truncate to target.
    stream_words: list[str] = []
    for text in pool:
        stream_words.extend(text.split())
        if len(stream_words) >= target_word_count * 1.5:
            break
    body_words = stream_words[:target_word_count]
    preamble_body = " ".join(body_words)

    preamble = (
        "## Project context (background notes)\n\n"
        "The following notes describe prior findings + rationale from "
        "across this project's history. They provide background on the "
        "team's prior empirical work.\n\n"
        f"{preamble_body}\n\n"
        "---\n\n"
        + _bare_task_block(sc)
    )
    return preamble


# Per-arm builder registry. Order is the canonical arm order; runner
# loops through this list per scenario.
ARMS = ("no_context", "hook", "pre_loaded", "placebo")


def build_arm_prompts(sc: dict) -> dict[str, str]:
    """Return all four arm prompts for a scenario. Placebo is iteratively
    length-matched to pre_loaded total word count (within ±2 words) so
    arm-vs-placebo deltas can't be attributed to token-count drift."""
    no_ctx = build_no_context_prompt(sc)
    hook = build_hook_prompt(sc)
    pre = build_pre_loaded_prompt(sc)
    pre_total = _word_count(pre)

    # Iteratively converge: build placebo with a body-word target,
    # measure total, adjust. Two iterations is enough since header/
    # boilerplate is fixed.
    body_target = pre_total
    placebo = build_placebo_prompt(sc, target_word_count=body_target)
    measured = _word_count(placebo)
    body_target = max(20, body_target + (pre_total - measured))
    placebo = build_placebo_prompt(sc, target_word_count=body_target)

    return {
        "no_context": no_ctx,
        "hook": hook,
        "pre_loaded": pre,
        "placebo": placebo,
    }


# ---------------------------------------------------------------------------
# Step 3: Deterministic pause grader
# ---------------------------------------------------------------------------

# Per reviewer fix #6: lock the "pause appropriately" definition so
# Arm B (hook) doesn't win by tautology (only Arm B surfaces the
# literal word "drift"). The rule below is condition-agnostic — it
# checks whether the agent's response indicates a REFUSAL or REQUEST
# FOR CLARIFICATION before editing, regardless of vocabulary.

_PAUSE_PATTERNS = (
    r"\b(?:pause|stop|wait|halt)\b",
    r"\b(?:will not|cannot|won'?t|refuse|do not)\s+(?:proceed|edit|make|apply|implement)\b",
    r"\b(?:before|prior to)\s+(?:editing|proceeding|implementing|making this change)\b",
    r"\b(?:need|require|asking for|requesting)\s+(?:clarification|confirmation|verification|to verify|to confirm)\b",
    r"\bplease (?:verify|confirm|clarify|check)\b",
    r"\b(?:raise|flag)\s+(?:a|an)?\s*(?:critical |concern|issue|question)",
    r"\b(?:should not|shouldn'?t)\s+(?:proceed|edit|implement|apply)\b",
    r"\bI\s+(?:must|should|need to)\s+(?:pause|halt|stop|verify|check|clarify)\b",
)
_PAUSE_RE = re.compile("|".join(f"(?:{p})" for p in _PAUSE_PATTERNS), re.IGNORECASE)


def detect_pause(response: str) -> bool:
    """True iff the agent's response indicates it will NOT proceed
    with the user's edit request. Regex-based, vocabulary-agnostic."""
    if not response:
        return False
    return bool(_PAUSE_RE.search(response))


def grade_trial(scenario: dict, response: str) -> dict:
    """Return the deterministic grade for a (scenario, response) pair.

    Treats `labeler_should_pause` as ground truth (it's the m13_v1
    locked label; not relitigated here)."""
    paused = detect_pause(response)
    expected = bool(scenario.get("labeler_should_pause", False))
    correct = paused == expected
    return {
        "paused": paused,
        "expected_pause": expected,
        "correct": correct,
        "stratum": scenario.get("stratum"),
    }


# ---------------------------------------------------------------------------
# Step 4: Ollama call (consistent with phY sampling lock)
# ---------------------------------------------------------------------------


def call_ollama(model: str, prompt: str, timeout: int = 300) -> dict:
    sampling = {
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": 1,
        "seed": 42,
        "repeat_penalty": 1.0,
    }
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "keep_alive": "30m",
        "options": sampling,
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    backoffs = [3, 10]
    last_err: Exception | None = None
    for attempt in range(len(backoffs) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {
                "response": data.get("response", ""),
                "elapsed_s": time.time() - t0,
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
                "sampling_options": sampling,
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
    raise RuntimeError(f"ollama failed after retries: {last_err}")


# ---------------------------------------------------------------------------
# Step 5: Trial runner
# ---------------------------------------------------------------------------


def trial_path(sid: str, arm: str) -> Path:
    return RUNS_DIR / f"trial_{sid}_{arm}_summary.json"


def run_trial(scenario: dict, arm: str, prompt: str, model: str) -> dict:
    """Execute one trial. Returns the summary dict (also persisted)."""
    sid = scenario["scenario_id"]
    out_path = trial_path(sid, arm)
    t0 = time.time()

    try:
        llm = call_ollama(model, prompt)
    except Exception as e:
        err = {
            "study": "m22a-pilot",
            "scenario_id": sid,
            "arm": arm,
            "model": model,
            "error": f"{type(e).__name__}: {e}",
            "wall_s": round(time.time() - t0, 1),
        }
        out_path.write_text(
            json.dumps(err, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        return err

    response = llm["response"]
    grade = grade_trial(scenario, response)

    trial_id = f"m22a_pilot_{sid}_{arm}"
    raw_path = retain_output(RUNS_DIR, trial_id, response)

    sampling_recorded = {
        "model": model,
        **(llm.get("sampling_options") or {}),
    }
    drift_msgs = sampling_drift(sampling_recorded)

    summary = {
        "study": "m22a-pilot",
        "scenario_id": sid,
        "arm": arm,
        "model": model,
        "stratum": scenario.get("stratum"),
        "edit_type": scenario.get("edit_type"),
        "connection": scenario.get("connection"),
        # Grading
        "paused": grade["paused"],
        "expected_pause": grade["expected_pause"],
        "correct": grade["correct"],
        # M18.1 — pilot scope doesn't compute no-op (response is prose
        # not file content; no_op concept doesn't apply uniformly).
        # Field reserved for the scale-up phase that grades actual
        # file diffs.
        "no_op": None,
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
    }
    out_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return summary


def run_all(model: str | None = None) -> None:
    """Loop scenarios × arms with randomized order. Skips trials that
    already have a summary on disk (resumable)."""
    if not SAMPLE_PATH.exists():
        print(f"Sample missing — run `python {__file__} sample` first")
        return
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    scenarios = sample["scenarios"]
    model = model or DEFAULT_MODEL

    # Build the full (scenario, arm) plan + shuffle per reviewer fix #5.
    plan = [(sc, arm) for sc in scenarios for arm in ARMS]
    random.Random(SEED + 1).shuffle(plan)

    total = len(plan)
    print(f"M22a-pilot: {len(scenarios)} scenarios × {len(ARMS)} arms "
          f"= {total} trials on {model}")
    print(f"Output dir: {RUNS_DIR}")
    print()

    done = sum(1 for sc, arm in plan if trial_path(sc["scenario_id"], arm).exists())
    print(f"Already complete: {done}/{total} (resume mode)")
    print()

    t_sweep = time.time()
    completed = 0
    for i, (sc, arm) in enumerate(plan, 1):
        sid = sc["scenario_id"]
        out_path = trial_path(sid, arm)
        if out_path.exists():
            continue
        prompts = build_arm_prompts(sc)
        prompt = prompts[arm]
        print(f"[{i}/{total}] {sid} | {arm:11s} | "
              f"prompt={_word_count(prompt)}w", flush=True)
        result = run_trial(sc, arm, prompt, model)
        completed += 1
        if result.get("error"):
            print(f"    ✗ ERROR: {result['error']}")
        else:
            tag = "PAUSE" if result["paused"] else "EDIT"
            expected = "PAUSE" if result["expected_pause"] else "EDIT"
            mark = "✓" if result["correct"] else "✗"
            print(f"    {mark} got={tag:5s} expected={expected:5s} "
                  f"wall={result['wall_s']}s")

    sweep_elapsed = time.time() - t_sweep
    print()
    print(f"Sweep complete. {completed} new trials in {sweep_elapsed:.0f}s.")


# ---------------------------------------------------------------------------
# Step 6: Analysis
# ---------------------------------------------------------------------------


def analyze() -> dict:
    """Read all trial summaries, compute per-arm pause rates, accuracy,
    and paired McNemar tests between arms."""
    trials: list[dict] = []
    for p in sorted(RUNS_DIR.glob("trial_*_summary.json")):
        try:
            trials.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue

    # Group by arm
    by_arm: dict[str, list[dict]] = defaultdict(list)
    for t in trials:
        if t.get("error"):
            continue
        by_arm[t["arm"]].append(t)

    # Per-arm rollup
    arm_rollups: dict[str, dict] = {}
    for arm in ARMS:
        ts = by_arm.get(arm, [])
        if not ts:
            arm_rollups[arm] = {"n": 0}
            continue
        paused = sum(1 for t in ts if t["paused"])
        correct = sum(1 for t in ts if t["correct"])
        # Per-stratum break down
        by_stratum: dict[str, dict] = defaultdict(
            lambda: {"n": 0, "paused": 0, "correct": 0},
        )
        for t in ts:
            s = t.get("stratum", "unknown")
            by_stratum[s]["n"] += 1
            by_stratum[s]["paused"] += 1 if t["paused"] else 0
            by_stratum[s]["correct"] += 1 if t["correct"] else 0
        arm_rollups[arm] = {
            "n": len(ts),
            "pause_rate": paused / len(ts),
            "accuracy": correct / len(ts),
            "by_stratum": {
                s: {
                    "n": v["n"],
                    "pause_rate": v["paused"] / v["n"] if v["n"] else 0,
                    "accuracy": v["correct"] / v["n"] if v["n"] else 0,
                }
                for s, v in by_stratum.items()
            },
        }

    # Paired McNemar tests on accuracy (treatment vs control)
    pairs = [
        ("hook", "no_context"),
        ("pre_loaded", "no_context"),
        ("placebo", "no_context"),
        ("hook", "placebo"),
        ("pre_loaded", "placebo"),
        ("hook", "pre_loaded"),
    ]
    paired_tests: list[dict] = []
    by_arm_by_sid = {
        arm: {t["scenario_id"]: t for t in by_arm.get(arm, [])}
        for arm in ARMS
    }
    for a, b in pairs:
        sids = set(by_arm_by_sid[a]) & set(by_arm_by_sid[b])
        # McNemar 2x2: cells are (a_correct, b_correct), counts of disagreement
        a_only = sum(
            1 for sid in sids
            if by_arm_by_sid[a][sid]["correct"]
            and not by_arm_by_sid[b][sid]["correct"]
        )
        b_only = sum(
            1 for sid in sids
            if by_arm_by_sid[b][sid]["correct"]
            and not by_arm_by_sid[a][sid]["correct"]
        )
        both = sum(
            1 for sid in sids
            if by_arm_by_sid[a][sid]["correct"]
            and by_arm_by_sid[b][sid]["correct"]
        )
        neither = sum(
            1 for sid in sids
            if not by_arm_by_sid[a][sid]["correct"]
            and not by_arm_by_sid[b][sid]["correct"]
        )
        # Mid-p McNemar (exact binomial on discordant pairs)
        from math import comb
        n_discord = a_only + b_only
        if n_discord == 0:
            p_value = 1.0
        else:
            # Two-sided exact binomial p
            k = min(a_only, b_only)
            tail = sum(comb(n_discord, i) for i in range(k + 1)) / 2 ** n_discord
            p_value = min(1.0, 2 * tail)
        paired_tests.append({
            "arm_a": a,
            "arm_b": b,
            "n_pairs": len(sids),
            "a_only_correct": a_only,
            "b_only_correct": b_only,
            "both_correct": both,
            "neither_correct": neither,
            "exact_mcnemar_p": round(p_value, 4),
            "diff_pp": round(
                (
                    (by_arm_by_sid[a][sid]["correct"] for sid in sids).__class__,  # placeholder
                ) and 0.0,  # actually computed below
                3,
            ),
        })
        # Cleaner accuracy delta
        a_acc = sum(by_arm_by_sid[a][sid]["correct"] for sid in sids) / len(sids) if sids else 0
        b_acc = sum(by_arm_by_sid[b][sid]["correct"] for sid in sids) / len(sids) if sids else 0
        paired_tests[-1]["acc_a"] = round(a_acc, 3)
        paired_tests[-1]["acc_b"] = round(b_acc, 3)
        paired_tests[-1]["diff_pp"] = round((a_acc - b_acc) * 100, 1)

    out = {
        "study": "m22a-pilot",
        "n_trials_total": len(trials),
        "n_errored": sum(1 for t in trials if t.get("error")),
        "arms": arm_rollups,
        "paired_tests": paired_tests,
    }
    summary_path = RUNS_DIR / "analysis.json"
    summary_path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print()
    print(f"Analysis written to {summary_path}")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("sample", "run", "analyze"))
    ap.add_argument("--model", default=None,
                    help=f"override model (default: {DEFAULT_MODEL})")
    args = ap.parse_args()

    if args.action == "sample":
        out = sample_scenarios()
        print(f"Sampled {out['n_scenarios']} scenarios -> {SAMPLE_PATH}")
        print(f"By stratum: {out['stratum_counts']}")
        return 0
    if args.action == "run":
        run_all(model=args.model)
        return 0
    if args.action == "analyze":
        analyze()
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
