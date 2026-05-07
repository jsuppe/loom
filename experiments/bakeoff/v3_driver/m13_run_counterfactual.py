#!/usr/bin/env python3
"""
M13.7e — counterfactual prompt ablation. Runs the m13_v1 eval
under each of 7 warning variants and produces a comparison
table.

Variants:
  no_signal   — drift NOT surfaced at all (the dev's
                "without any drift signal" baseline; measures
                whether M13 existing matters)
  no_warning  — drift surfaced (GRAPH-DRIFT flag + foundation-
                drift section) but no warning TEXT
  bare_rule   — "Drift detected on REQ-X" — fact only, no
                imperative
  conditional — "if your edit touches X, verify"
  descriptive — "this could touch a finding in flux"
  ask_back    — "does your edit reference X? If so, verify"
  v2          — production v2 (M13.6d, the L9 imperative)
  v3          — production v3 (M13.7d, scope-qualifier; current
                pinned baseline)

The interesting comparisons:
  v3 vs no_signal     — what does M13 buy?
  v3 vs bare_rule     — does the L9 imperative + scope text
                        actually beat just surfacing the drift?
  v3 vs conditional   — is "if/then" simpler form competitive?
  v3 vs ask_back      — is conversational framing competitive?

Total cost: ~7 conditions × 170 scenarios × 2 LLM calls each
≈ 2.4k calls, ~2-3 hours on qwen3.5/temp=0.

The runner reuses the locked m13_v1 dataset for all conditions,
so apples-to-apples comparison is automatic.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")


VARIANTS = [
    "no_signal",
    "no_warning",
    "bare_rule",
    "conditional",
    "descriptive",
    "ask_back",
    "v2",
    "v3",
]


def main() -> int:
    started_overall = time.perf_counter()
    print(f"=== M13.7e counterfactual prompt ablation ===")
    print(f"  variants: {len(VARIANTS)}")
    print(f"  est total: ~2-3 hours on qwen3.5/temp=0")
    print()

    runner = LOOM_DIR / "experiments" / "bakeoff" / "v3_driver" / "m13_eval_runner.py"
    out_dir = LOOM_DIR / "experiments" / "bakeoff" / "runs-v3"

    results: list[tuple[str, Path, float]] = []
    for i, variant in enumerate(VARIANTS, 1):
        t0 = time.perf_counter()
        print(f"[{i}/{len(VARIANTS)}] running variant={variant} "
              f"(started {datetime.now(timezone.utc).isoformat()})")
        env = os.environ.copy()
        env["LOOM_M13_WARNING_VERSION"] = variant
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [
            sys.executable, str(runner),
            "--eval-set", "m13_v1",
            "--model", "ollama:qwen3.5:latest",
            "--tag", f"counterfactual-{variant}",
        ]
        proc = subprocess.run(cmd, env=env, cwd=LOOM_DIR,
                              capture_output=True, text=True,
                              encoding="utf-8")
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            print(f"  ✗ failed (exit {proc.returncode})")
            print(f"    stderr: {(proc.stderr or '')[-500:]}")
            continue
        # Resolve output file path that the runner saved.
        # Runner default tag pattern: eval_<eval_id>_<model_safe>_<tag>.json
        result_path = (
            out_dir
            / f"eval_m13_v1_ollama_qwen3.5_latest_counterfactual-{variant}.json"
        )
        if result_path.exists():
            results.append((variant, result_path, elapsed))
            print(f"  ✓ {elapsed:.1f}s  → {result_path.name}")
        else:
            print(f"  ⚠ runner exited 0 but result not found at {result_path}")

    total_elapsed = time.perf_counter() - started_overall
    print()
    print(f"=== Total elapsed: {total_elapsed/60:.1f} min ===")
    print()
    print("Result files (for compare):")
    for variant, path, _ in results:
        print(f"  {variant:<14} {path}")
    print()
    print("Next: run m13_eval_compare.py against the v3 baseline for each.")
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
