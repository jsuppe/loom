#!/usr/bin/env python3
"""
Phase L2 acceptance evaluation: Toulmin@v1 LLM-driven validator
against (a) the canary set [strict gate] and (b) a 20-rationale
sample from the dogfooded loom store [coverage-band signal].

Acceptance per PR #13 comment 2:
  1. Coverage band: 30–60% pass on the 20-rationale sample
     (bimodal score distribution = good signal; 0.5-clustered = bad)
  2. 0/5 false positives on the canary
     — single false positive = unreliable substrate
  3. (Bonus, optional) Downstream Driftgraph alignment via Cypher

Output:
  experiments/pilot/warrants_l2_results.json — full per-rationale
    results (validator output, score, parts breakdown)
  experiments/pilot/warrants_l2_summary.md — human-readable summary
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
CANARY_PATH = LOOM_DIR / "tests" / "data" / "toulmin_canary_v1.json"
RESULTS_PATH = LOOM_DIR / "experiments" / "pilot" / "warrants_l2_results.json"
SUMMARY_PATH = LOOM_DIR / "experiments" / "pilot" / "warrants_l2_summary.md"

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom import warrants  # noqa: E402
from loom.store import LoomStore  # noqa: E402


def evaluate_canary() -> tuple[list[dict], int]:
    """Run toulmin_v1 on every canary item. Returns
    (per-item results, false-positive count)."""
    items = json.loads(CANARY_PATH.read_text(encoding="utf-8"))
    results = []
    fp = 0
    for item in items:
        t0 = time.perf_counter()
        res = warrants.toulmin_v1(item["rationale"])
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        outcome = {
            "id": item["id"],
            "rationale": item["rationale"],
            "category": item["category"],
            "expected_reject_reason": item["expected_reject_reason"],
            "actual_passes": res.passes,
            "actual_score": res.score,
            "actual_reason": res.reason,
            "actual_parts": res.parts,
            "elapsed_ms": elapsed_ms,
        }
        if res.passes:
            fp += 1
            outcome["FALSE_POSITIVE"] = True
        results.append(outcome)
        verdict = "✗ FALSE POS" if res.passes else "✓ rejected"
        print(f"  {verdict}  {item['id']:<28}  score={res.score:.2f}  ({elapsed_ms}ms)")
    return results, fp


def sample_loom_rationales(n: int = 20) -> list[dict]:
    """Pick up to n loom rationales for the coverage-band check.
    Skips reqs without a rationale (would be trivially failed by
    toulmin_v1; doesn't tell us anything about the validator)."""
    store = LoomStore("loom")
    reqs = store.list_requirements(include_superseded=False)
    # Exclude archived and rationale-less reqs.
    eligible = [
        r for r in reqs
        if r.status != "archived" and (r.rationale or "").strip()
    ]
    # Sample deterministically: sort by id so re-runs are reproducible.
    eligible.sort(key=lambda r: r.id)
    sampled = eligible[:n]
    return [
        {"req_id": r.id, "kind": r.kind, "value": r.value,
         "rationale": r.rationale}
        for r in sampled
    ]


def evaluate_sample(sample: list[dict]) -> list[dict]:
    """Run toulmin_v1 on the sample. Returns per-item outcomes."""
    results = []
    for i, item in enumerate(sample, 1):
        t0 = time.perf_counter()
        res = warrants.toulmin_v1(item["rationale"])
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        out = {
            "req_id": item["req_id"],
            "kind": item["kind"],
            "value": item["value"][:100],
            "rationale_preview": item["rationale"][:120],
            "passes": res.passes,
            "score": res.score,
            "reason": res.reason,
            "parts": res.parts,
            "elapsed_ms": elapsed_ms,
        }
        results.append(out)
        verdict = "✓ PASS" if res.passes else "✗ fail"
        print(f"  [{i:2d}/{len(sample)}]  {verdict}  {item['req_id']}  "
              f"<{item['kind']}>  score={res.score:.2f}  ({elapsed_ms}ms)")
    return results


def score_distribution(results: list[dict]) -> dict:
    """Bin scores into {0.0–0.25, 0.25–0.5, 0.5–0.75, 0.75–1.0}.
    Acceptance criterion 2 wants bimodal — heavy weight at
    0.0–0.25 + 0.75–1.0, light at 0.25–0.75."""
    bins = {"0.00-0.25": 0, "0.25-0.50": 0, "0.50-0.75": 0, "0.75-1.00": 0}
    for r in results:
        s = r["score"]
        if s < 0.25:
            bins["0.00-0.25"] += 1
        elif s < 0.50:
            bins["0.25-0.50"] += 1
        elif s < 0.75:
            bins["0.50-0.75"] += 1
        else:
            bins["0.75-1.00"] += 1
    return bins


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    model = warrants._default_toulmin_v1_model()
    print(f"Toulmin@v1 evaluation — model={model}")
    print(f"  started: {started}")
    print()

    print("=== Cut 1: canary (strict gate; FP must be 0/5) ===")
    canary_results, false_positives = evaluate_canary()
    canary_pass = (false_positives == 0)
    print()
    print(f"Canary FP: {false_positives}/5  → {'PASS' if canary_pass else 'FAIL (acceptance gated)'}")
    print()

    print("=== Cut 2: 20-rationale sample (pass-rate band 30–60%) ===")
    sample = sample_loom_rationales(n=20)
    print(f"  sampled {len(sample)} rationales from the loom store")
    print()
    sample_results = evaluate_sample(sample)
    n = len(sample_results)
    n_pass = sum(1 for r in sample_results if r["passes"])
    pass_rate = (n_pass / n) if n else 0.0
    in_band = 0.30 <= pass_rate <= 0.60
    bins = score_distribution(sample_results)
    # Bimodality heuristic: sum of two outer bins / sum of two inner bins.
    outer = bins["0.00-0.25"] + bins["0.75-1.00"]
    inner = bins["0.25-0.50"] + bins["0.50-0.75"]
    bimodal_ratio = (outer / inner) if inner else float("inf")
    print()
    print(f"Sample pass rate: {n_pass}/{n} = {pass_rate*100:.1f}%  → {'IN BAND' if in_band else 'OUT OF BAND'}")
    print(f"Score distribution: {bins}")
    print(f"Bimodality (outer/inner): {bimodal_ratio:.2f}  (>1.5 = bimodal, ~1.0 = flat, <0.5 = clustered)")
    print()

    finished = datetime.now(timezone.utc).isoformat()
    overall = {
        "started_at": started,
        "finished_at": finished,
        "model": model,
        "canary": {
            "n": len(canary_results),
            "false_positives": false_positives,
            "acceptance_pass": canary_pass,
            "results": canary_results,
        },
        "sample": {
            "n": n,
            "n_pass": n_pass,
            "pass_rate": round(pass_rate, 3),
            "in_band_30_60": in_band,
            "score_bins": bins,
            "bimodality_ratio": round(bimodal_ratio, 2)
                                if bimodal_ratio != float("inf") else None,
            "results": sample_results,
        },
        "acceptance": {
            "cut_1_canary_zero_fp": canary_pass,
            "cut_2_pass_rate_in_band": in_band,
            "overall_pass": canary_pass and in_band,
        },
    }
    RESULTS_PATH.write_text(
        json.dumps(overall, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    # Render a human-readable summary alongside the JSON.
    md = []
    md.append(f"# Toulmin@v1 — Phase L2 evaluation\n")
    md.append(f"**Model:** `{model}`  ")
    md.append(f"**Started:** {started}  ")
    md.append(f"**Finished:** {finished}  \n")
    md.append("## Acceptance summary\n")
    md.append(f"| Cut | Threshold | Result | Verdict |")
    md.append(f"|---|---|---|---|")
    md.append(
        f"| 1 — canary FP | 0/5 false positives | "
        f"{false_positives}/5 | {'PASS' if canary_pass else 'FAIL'} |"
    )
    md.append(
        f"| 2 — sample pass-rate band | 30–60% | "
        f"{n_pass}/{n} = {pass_rate*100:.1f}% | "
        f"{'PASS' if in_band else 'OUT OF BAND'} |"
    )
    md.append(
        f"| score distribution | bimodal preferred | "
        f"outer/inner = {bimodal_ratio:.2f} | "
        f"{'bimodal' if bimodal_ratio > 1.5 else 'mixed' if bimodal_ratio > 0.5 else 'clustered'} |"
    )
    md.append(f"\n**Overall L2 acceptance:** "
              f"{'PASS' if overall['acceptance']['overall_pass'] else 'FAIL'}\n")
    md.append("## Score distribution (sample)\n")
    md.append(f"| Bin | Count |")
    md.append(f"|---|---|")
    for k, v in bins.items():
        md.append(f"| {k} | {v} |")
    md.append("\n## Per-canary outcome\n")
    md.append(f"| ID | category | actual_score | passes | actual_reason |")
    md.append(f"|---|---|---|---|---|")
    for r in canary_results:
        md.append(
            f"| {r['id']} | {r['category']} | {r['actual_score']:.2f} "
            f"| {'**FP**' if r['actual_passes'] else 'rejected'} "
            f"| {r['actual_reason'][:90]} |"
        )
    md.append("\n## Per-sample outcome\n")
    md.append(f"| req_id | kind | score | passes | reason |")
    md.append(f"|---|---|---|---|---|")
    for r in sample_results:
        md.append(
            f"| {r['req_id']} | {r['kind']} | {r['score']:.2f} "
            f"| {'**PASS**' if r['passes'] else 'fail'} "
            f"| {r['reason'][:80]} |"
        )
    SUMMARY_PATH.write_text("\n".join(md), encoding="utf-8")

    print(f"Results: {RESULTS_PATH}")
    print(f"Summary: {SUMMARY_PATH}")
    print()
    overall_pass = overall["acceptance"]["overall_pass"]
    print(f"=== L2 ACCEPTANCE: {'PASS' if overall_pass else 'FAIL'} ===")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
