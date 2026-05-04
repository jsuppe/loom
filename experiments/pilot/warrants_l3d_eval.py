#!/usr/bin/env python3
"""
Phase L3d evaluation: Falsifiability@v1 LLM-driven validator
against (a) the falsifiability canary set and (b) the same
19-rationale sample used in L2.

Acceptance:
  - 0/5 false positives on the canary
  - meaningful signal on the sample — pass rate doesn't have a
    fixed band like Toulmin's 30–60% (Falsifiability is a
    different measurement); we report the rate, the score
    distribution, and the cross-validator agreement matrix
    against L2's Toulmin@v1 results.

Output:
  experiments/pilot/warrants_l3d_results.json
  experiments/pilot/warrants_l3d_summary.md  — including the
    cross-validator agreement matrix (toulmin pass × falsi pass)
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
CANARY_PATH = LOOM_DIR / "tests" / "data" / "falsifiability_canary_v1.json"
L2_RESULTS_PATH = LOOM_DIR / "experiments" / "pilot" / "warrants_l2_results.json"
RESULTS_PATH = LOOM_DIR / "experiments" / "pilot" / "warrants_l3d_results.json"
SUMMARY_PATH = LOOM_DIR / "experiments" / "pilot" / "warrants_l3d_summary.md"

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom import warrants  # noqa: E402
from loom.store import LoomStore  # noqa: E402


def evaluate_canary() -> tuple[list[dict], int]:
    items = json.loads(CANARY_PATH.read_text(encoding="utf-8"))
    results, fp = [], 0
    for item in items:
        t0 = time.perf_counter()
        res = warrants.falsifiability_v1(item["rationale"])
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
    store = LoomStore("loom")
    reqs = store.list_requirements(include_superseded=False)
    eligible = [
        r for r in reqs
        if r.status != "archived" and (r.rationale or "").strip()
    ]
    eligible.sort(key=lambda r: r.id)
    return [
        {"req_id": r.id, "kind": r.kind, "value": r.value,
         "rationale": r.rationale}
        for r in eligible[:n]
    ]


def evaluate_sample(sample: list[dict]) -> list[dict]:
    results = []
    for i, item in enumerate(sample, 1):
        t0 = time.perf_counter()
        res = warrants.falsifiability_v1(item["rationale"])
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


def cross_validator_matrix(toulmin: dict, falsi: list[dict]) -> dict:
    """Build a {(toulmin_pass, falsi_pass): [req_ids]} 2x2 matrix
    to surface which rationales pass which validator. Uses the
    saved L2 results JSON for the toulmin column."""
    by_req_toulmin = {r["req_id"]: r["passes"]
                      for r in toulmin.get("sample", {}).get("results", [])}
    cells: dict[tuple[bool, bool], list[str]] = {
        (True, True): [], (True, False): [],
        (False, True): [], (False, False): [],
    }
    for r in falsi:
        rid = r["req_id"]
        if rid not in by_req_toulmin:
            continue
        cells[(by_req_toulmin[rid], r["passes"])].append(rid)
    return {
        "both_pass": cells[(True, True)],
        "toulmin_only": cells[(True, False)],
        "falsifiability_only": cells[(False, True)],
        "neither": cells[(False, False)],
    }


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    model = warrants._default_falsifiability_v1_model()
    print(f"Falsifiability@v1 evaluation — model={model}")
    print(f"  started: {started}")
    print()

    print("=== Cut 1: canary (FP must be 0/5) ===")
    canary_results, false_positives = evaluate_canary()
    canary_pass = (false_positives == 0)
    print()
    print(f"Canary FP: {false_positives}/5  → {'PASS' if canary_pass else 'FAIL'}")
    print()

    print("=== Cut 2: 19-rationale sample (rate signal + bimodality) ===")
    sample = sample_loom_rationales(n=20)
    sample_results = evaluate_sample(sample)
    n = len(sample_results)
    n_pass = sum(1 for r in sample_results if r["passes"])
    pass_rate = n_pass / n if n else 0.0
    bins = {"0.00-0.25": 0, "0.25-0.50": 0, "0.50-0.75": 0, "0.75-1.00": 0}
    for r in sample_results:
        s = r["score"]
        if s < 0.25:
            bins["0.00-0.25"] += 1
        elif s < 0.50:
            bins["0.25-0.50"] += 1
        elif s < 0.75:
            bins["0.50-0.75"] += 1
        else:
            bins["0.75-1.00"] += 1
    outer = bins["0.00-0.25"] + bins["0.75-1.00"]
    inner = bins["0.25-0.50"] + bins["0.50-0.75"]
    bimodal_ratio = (outer / inner) if inner else float("inf")
    print()
    print(f"Sample pass rate: {n_pass}/{n} = {pass_rate*100:.1f}%")
    print(f"Score distribution: {bins}")
    print(f"Bimodality (outer/inner): {bimodal_ratio:.2f}")
    print()

    # Cross-validator matrix vs L2 Toulmin results
    matrix = None
    if L2_RESULTS_PATH.exists():
        print("=== Cut 3: cross-validator agreement (Toulmin × Falsifiability) ===")
        l2 = json.loads(L2_RESULTS_PATH.read_text(encoding="utf-8"))
        matrix = cross_validator_matrix(l2, sample_results)
        for label, ids in matrix.items():
            print(f"  {label:<24}: {len(ids):2d}  {ids[:5]}{'...' if len(ids) > 5 else ''}")
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
            "score_bins": bins,
            "bimodality_ratio": round(bimodal_ratio, 2)
                                if bimodal_ratio != float("inf") else None,
            "results": sample_results,
        },
        "cross_validator": matrix,
        "acceptance": {
            "cut_1_canary_zero_fp": canary_pass,
            "overall_pass": canary_pass,  # canary is the only hard gate
        },
    }
    RESULTS_PATH.write_text(
        json.dumps(overall, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = []
    md.append(f"# Falsifiability@v1 — Phase L3d evaluation\n")
    md.append(f"**Model:** `{model}`  ")
    md.append(f"**Started:** {started}  ")
    md.append(f"**Finished:** {finished}  \n")
    md.append("## Acceptance summary\n")
    md.append("| Cut | Threshold | Result | Verdict |")
    md.append("|---|---|---|---|")
    md.append(f"| 1 — canary FP | 0/5 false positives | "
              f"{false_positives}/5 | {'PASS' if canary_pass else 'FAIL'} |")
    md.append(f"| 2 — sample pass rate | informational | "
              f"{n_pass}/{n} = {pass_rate*100:.1f}% | n/a |")
    md.append(f"| 2 — bimodality | bimodal preferred | "
              f"outer/inner = {bimodal_ratio:.2f} | "
              f"{'bimodal' if bimodal_ratio > 1.5 else 'mixed' if bimodal_ratio > 0.5 else 'clustered'} |")
    md.append(f"\n**Overall L3d acceptance:** "
              f"{'PASS' if overall['acceptance']['overall_pass'] else 'FAIL'}\n")
    md.append("## Score distribution (sample)\n")
    md.append("| Bin | Count |")
    md.append("|---|---|")
    for k, v in bins.items():
        md.append(f"| {k} | {v} |")
    if matrix:
        md.append("\n## Cross-validator agreement (Toulmin@v1 × Falsifiability@v1)\n")
        md.append("| cell | count | members |")
        md.append("|---|---|---|")
        md.append(f"| both pass | {len(matrix['both_pass'])} | "
                  f"{', '.join(matrix['both_pass']) or '—'} |")
        md.append(f"| toulmin only | {len(matrix['toulmin_only'])} | "
                  f"{', '.join(matrix['toulmin_only']) or '—'} |")
        md.append(f"| falsifiability only | {len(matrix['falsifiability_only'])} | "
                  f"{', '.join(matrix['falsifiability_only']) or '—'} |")
        md.append(f"| neither | {len(matrix['neither'])} | "
                  f"{', '.join(matrix['neither'][:5]) + ('...' if len(matrix['neither']) > 5 else '') or '—'} |")
    md.append("\n## Per-canary outcome\n")
    md.append("| ID | category | actual_score | passes | actual_reason |")
    md.append("|---|---|---|---|---|")
    for r in canary_results:
        md.append(f"| {r['id']} | {r['category']} | {r['actual_score']:.2f} "
                  f"| {'**FP**' if r['actual_passes'] else 'rejected'} "
                  f"| {r['actual_reason'][:90]} |")
    md.append("\n## Per-sample outcome\n")
    md.append("| req_id | kind | score | passes | reason |")
    md.append("|---|---|---|---|---|")
    for r in sample_results:
        md.append(f"| {r['req_id']} | {r['kind']} | {r['score']:.2f} "
                  f"| {'**PASS**' if r['passes'] else 'fail'} "
                  f"| {r['reason'][:80]} |")
    SUMMARY_PATH.write_text("\n".join(md), encoding="utf-8")

    print(f"Results: {RESULTS_PATH}")
    print(f"Summary: {SUMMARY_PATH}")
    print()
    print(f"=== L3d ACCEPTANCE: {'PASS' if overall['acceptance']['overall_pass'] else 'FAIL'} ===")
    return 0 if overall["acceptance"]["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
