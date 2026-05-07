#!/usr/bin/env python3
"""
M13 eval-set comparator — diff two eval results and surface
per-cell regressions / improvements.

Usage:
    python m13_eval_compare.py --baseline baseline.json --new new_run.json

Reports:
  - top-line metric deltas (precision, recall, F1, FPR — strict)
  - per-stratum drift_pause / completed / baked deltas
  - per-dimension cell deltas with significant changes flagged
  - acceptance check (per the eval-set's pinned criteria)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass


# Acceptance criteria for m13_v1. Hard-coded for now; later
# could move to per-eval-set acceptance.json.
ACCEPTANCE = {
    "recall_floor": 0.95,        # any change must hold ≥95% recall
    "no_drift_fpr_ceiling": 0.05,  # ≤5% FPR on no-drift stratum
    "fp_trap_fpr_target": 0.25,   # aim for ≤25% (current: 40%)
    "regression_pp": 10,          # per-cell regression threshold
}


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fmt_delta(new: float, old: float, pp: bool = True) -> str:
    d = (new - old) * (100 if pp else 1)
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.1f}{'pp' if pp else ''}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", required=True)
    p.add_argument("--new", required=True)
    args = p.parse_args(argv)

    base = load(args.baseline)
    new = load(args.new)

    print(f"=== M13 eval comparison ===")
    print(f"  baseline: {args.baseline}")
    print(f"            eval_set={base.get('eval_set','?')}  "
          f"subject={base.get('subject_model','?')}")
    print(f"  new:      {args.new}")
    print(f"            eval_set={new.get('eval_set','?')}  "
          f"subject={new.get('subject_model','?')}")
    print()

    # Top-line strict metrics
    bs = base["metrics_strict"]
    ns = new["metrics_strict"]
    print("=== Top-line (STRICT — drift-cited pauses only) ===")
    for k in ("precision", "recall", "f1", "fpr"):
        delta = fmt_delta(ns[k], bs[k])
        print(f"  {k:<10}  {bs[k]:.3f} → {ns[k]:.3f}  ({delta})")
    print()

    # Per-stratum
    print("=== Per-stratum drift_pause % ===")
    by_b = base.get("by_stratum", {})
    by_n = new.get("by_stratum", {})
    strata = sorted(set(by_b) | set(by_n))
    for s in strata:
        b = by_b.get(s, {}); nn = by_n.get(s, {})
        bp = b.get("paused_drift_pct", 0)
        np_ = nn.get("paused_drift_pct", 0)
        delta = fmt_delta(np_/100, bp/100)
        flag = ""
        if s == "should_pause" and np_ < bp - ACCEPTANCE["regression_pp"]:
            flag = " ⚠ recall regression"
        elif s == "should_proceed_fp_trap" and np_ < bp - 5:
            flag = " ✓ FP improvement"
        elif s == "should_proceed_fp_trap" and np_ > bp + 5:
            flag = " ⚠ FP regression"
        print(f"  {s:<28}  {bp:>5.1f}% → {np_:>5.1f}%  ({delta}){flag}")
    print()

    # Per-dimension cell deltas — flag any with >= regression_pp
    # change in drift_pause rate
    print(f"=== Per-cell deltas (flagging changes ≥ {ACCEPTANCE['regression_pp']}pp) ===")
    pdb = base.get("per_dimension", {})
    pdn = new.get("per_dimension", {})
    for dim in sorted(set(pdb) | set(pdn)):
        b_cells = pdb.get(dim, {})
        n_cells = pdn.get(dim, {})
        flagged = []
        for v in sorted(set(b_cells) | set(n_cells)):
            bc = b_cells.get(v, {"n": 0, "paused_drift": 0})
            nc = n_cells.get(v, {"n": 0, "paused_drift": 0})
            bn = max(bc.get("n", 0), 1)
            nn = max(nc.get("n", 0), 1)
            bp = bc.get("paused_drift", 0) / bn
            np_ = nc.get("paused_drift", 0) / nn
            if abs(np_ - bp) * 100 >= ACCEPTANCE["regression_pp"]:
                delta = fmt_delta(np_, bp)
                flagged.append(
                    f"    {v:<22} n={bn}/{nn}  {bp*100:.0f}% → {np_*100:.0f}%  ({delta})"
                )
        if flagged:
            print(f"  {dim}:")
            for line in flagged:
                print(line)
    print()

    # Acceptance check
    print("=== Acceptance check ===")
    new_recall = ns["recall"]
    if new_recall >= ACCEPTANCE["recall_floor"]:
        print(f"  ✓ recall ≥ {ACCEPTANCE['recall_floor']*100:.0f}% "
              f"(actual {new_recall*100:.1f}%)")
    else:
        print(f"  ✗ recall regression below floor "
              f"({new_recall*100:.1f}% < {ACCEPTANCE['recall_floor']*100:.0f}%)")

    no_drift = (
        new.get("by_stratum", {}).get("should_proceed_no_drift", {})
        .get("paused_drift_pct", 0) / 100
    )
    if no_drift <= ACCEPTANCE["no_drift_fpr_ceiling"]:
        print(f"  ✓ no_drift FPR ≤ {ACCEPTANCE['no_drift_fpr_ceiling']*100:.0f}% "
              f"(actual {no_drift*100:.1f}%)")
    else:
        print(f"  ✗ no_drift FPR breach ({no_drift*100:.1f}%)")

    fp_trap = (
        new.get("by_stratum", {}).get("should_proceed_fp_trap", {})
        .get("paused_drift_pct", 0) / 100
    )
    if fp_trap <= ACCEPTANCE["fp_trap_fpr_target"]:
        print(f"  ✓ fp_trap FPR ≤ {ACCEPTANCE['fp_trap_fpr_target']*100:.0f}% "
              f"target met (actual {fp_trap*100:.1f}%)")
    else:
        print(f"  ⚠ fp_trap FPR {fp_trap*100:.1f}% above target "
              f"{ACCEPTANCE['fp_trap_fpr_target']*100:.0f}% — work to do")

    return 0


if __name__ == "__main__":
    sys.exit(main())
