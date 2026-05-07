#!/usr/bin/env python3
"""
Lock an eval-set v1: merge an existing dataset (e.g. n=100 from
the original M13.7 run) with the augmentation scenarios produced
by m13_eval_curate.py, write to the m13_v1 location, and
optionally write a manifest with stats.

Usage:
    python m13_eval_lock.py \\
        --base experiments/bakeoff/runs-v3/phM13_4_dataset_n100.json \\
        --augment experiments/bakeoff/runs-v3/m13_v1_augment.json \\
        --out experiments/bakeoff/eval_sets/m13_v1/scenarios.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True,
                   help="Original dataset JSON (e.g. phM13_4_dataset_n100.json)")
    p.add_argument("--augment", required=True,
                   help="Augmentation JSON from m13_eval_curate.py")
    p.add_argument("--out", required=True,
                   help="Where to write the locked scenarios.json")
    args = p.parse_args(argv)

    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    aug = json.loads(Path(args.augment).read_text(encoding="utf-8"))

    base_scen = base.get("scenarios", [])
    aug_scen = aug.get("scenarios", [])
    print(f"base: {len(base_scen)} scenarios")
    print(f"augment: {len(aug_scen)} scenarios")

    # Renumber scenario_ids so they're contiguous from s001
    merged: list[dict] = []
    for i, s in enumerate(base_scen + aug_scen, 1):
        s = dict(s)  # copy so we don't mutate originals
        s["scenario_id"] = f"s{i:04d}"
        merged.append(s)
    print(f"merged: {len(merged)} scenarios (contiguous IDs s0001 ... s{len(merged):04d})")

    # Final cell-count audit
    by_stratum_edit = Counter(
        (s.get("stratum","?"), s.get("edit_type","?")) for s in merged
    )
    print("\nFinal cell distribution (stratum × edit_type):")
    for (stratum, et), n in sorted(by_stratum_edit.items()):
        marker = "✓" if n >= 5 else "⚠ < 5"
        print(f"  {stratum:<28} edit_type={et:<12} n={n:>3}  {marker}")

    by_stratum = Counter(s.get("stratum","?") for s in merged)
    print("\nBy stratum:")
    for k, v in by_stratum.items():
        print(f"  {k:<28} {v}")

    payload = {
        "version": "v1.0",
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "base_dataset": str(args.base),
        "augment_dataset": str(args.augment),
        "n_scenarios": len(merged),
        "scenarios": merged,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nLocked: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
