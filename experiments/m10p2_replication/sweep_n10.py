#!/usr/bin/env python3
"""M10.2 replication at N=10 — thin sweep wrapper.

Invokes the locked phL2 baseline harness (unmodified) once per
(cell, run_id) for run_id in 1..10 across all 4 cells.

Output lands in experiments/bakeoff/runs-m10p2-n10/ — separate from
the original M10.2 N=5 evidence at runs-v2/phL2_* so both can be
compared in the verdict.

Pre-registration anchor:
    experiments/m10p2_replication/PRE_REGISTRATION.md

Locked hypotheses:
    H1 (primary, two-sided)  rat cell in [30%, 70%] -> real signal;
                              <=10% -> noise; 10-29% or 71-100% -> inconclusive
    H2 (sanity check)         off <=30%, on-rule <=50%, placebo >=30%
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

LOOM_DIR = Path(__file__).resolve().parents[2]
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"
HARNESS = (BAKEOFF_DIR / "v2_driver" /
           "phL2_crosssession_cpp_stub_indexer_smoke.py")
PHL2_OUT_DIR = BAKEOFF_DIR / "runs-v2"
M10P2_OUT_DIR = BAKEOFF_DIR / "runs-m10p2-n10"
M10P2_OUT_DIR.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

CELLS = ("off", "on-rule", "on-rule+placebo", "on-rule+rat")


def move_output(cell: str, run_id_arg: str, replication_label: str) -> None:
    """phL2 writes to runs-v2/. Move the result into our replication
    dir so the original N=5 evidence stays untouched.

    `run_id_arg` is what we passed to phL2 (a namespaced "n10_1", not
    a bare "1") so it can't collide with the original M10.2 files
    named with bare integers 1-5.
    """
    cell_slug = cell.replace("+", "_").replace("-", "_")
    src = PHL2_OUT_DIR / f"phL2_s1_cpp_{cell_slug}_run{run_id_arg}_summary.json"
    if not src.exists():
        print(f"WARN: expected output not found at {src}", file=sys.stderr)
        return
    dst = M10P2_OUT_DIR / f"m10p2_n10_s1_cpp_{cell_slug}_run{run_id_arg}_summary.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    data["replication_phase"] = replication_label
    data["original_run_id"] = run_id_arg
    dst.write_text(json.dumps(data, indent=2), encoding="utf-8")
    src.unlink()


def run_one(cell: str, trial_index: int) -> None:
    """Namespace the run_id to prevent collisions with the original
    M10.2 outputs at runs-v2/phL2_s1_cpp_*_run{1..5}_summary.json."""
    t0 = time.time()
    run_id_arg = f"n10_{trial_index}"
    print(f"\n===== {cell} run n10_{trial_index} =====")
    result = subprocess.run(
        [sys.executable, str(HARNESS), cell, run_id_arg],
        capture_output=False,
        text=True,
        cwd=str(LOOM_DIR),
    )
    if result.returncode != 0:
        print(f"WARN: phL2 returned {result.returncode}", file=sys.stderr)
    move_output(cell, run_id_arg, "M10.2 N=10 (sweep_n10.py)")
    print(f"[wrap] cell={cell} run=n10_{trial_index} wall={time.time() - t0:.1f}s")


def main(argv: list[str]) -> int:
    n = 10
    if "--n" in argv:
        i = argv.index("--n")
        if i + 1 < len(argv):
            n = int(argv[i + 1])

    print(f"M10.2 replication sweep: {len(CELLS)} cells x {n} trials = {len(CELLS) * n} total")
    print(f"Output: {M10P2_OUT_DIR}")

    for cell in CELLS:
        for i in range(1, n + 1):
            run_one(cell, i)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
