#!/usr/bin/env python3
"""
Phase A batch runner.

Runs 50 bakeoff V2 conditions: capacity gradient within Claude (Haiku,
Sonnet, Opus symmetric) plus Sonnet<->Opus asymmetric, both with and
without Loom on the Engineer.

Skips any run whose summary.json already exists (resumable). Sleeps
briefly between runs to respect Max rate limits.

Writes progress to v2_driver/batch_progress.jsonl — one line per run
with the condensed summary. Launch via:

    nohup python3 batch_runner.py > batch_runner.log 2>&1 &
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
BAKEOFF_DIR = V2_DIR.parent
RUNS_DIR = BAKEOFF_DIR / "runs-v2"
PROGRESS_LOG = V2_DIR / "batch_progress.jsonl"

INTER_RUN_SLEEP_S = 10
MAX_ITERS_PER_RUN = 15


def run_one(
    condition: str,
    run_id: int,
    po_model: str,
    eng_model: str,
    loom_mode: str,
    benchmark: str = "python-queue",
) -> dict:
    """Invoke driver.py once. Returns the summary dict or {'skipped': True}."""
    run_tag = (
        f"{condition}_"
        f"{po_model}po-{eng_model}eng-{loom_mode}L-{benchmark}_"
        f"{run_id:03d}"
    )
    run_dir = RUNS_DIR / run_tag
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        # Already completed — skip.
        try:
            return {"skipped": True, **json.loads(summary_path.read_text(encoding="utf-8"))}
        except Exception:
            # Corrupt summary; re-run.
            pass

    cmd = [
        sys.executable, str(V2_DIR / "driver.py"),
        "--condition", condition,
        "--run-id", str(run_id),
        "--po-model", po_model,
        "--eng-model", eng_model,
        "--loom", loom_mode,
        "--benchmark", benchmark,
        "--max-iters", str(MAX_ITERS_PER_RUN),
    ]
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,  # 30 min hard cap per run
        )
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "condition": condition, "run_id": run_id}

    dur = time.time() - t0
    if summary_path.exists():
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            data["_batch_duration_s"] = round(dur, 1)
            return data
        except Exception as e:
            return {"error": f"summary parse: {e}", "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]}
    return {
        "error": f"no summary produced; rc={result.returncode}",
        "stdout": result.stdout[-500:],
        "stderr": result.stderr[-500:],
        "_batch_duration_s": round(dur, 1),
    }


def log_progress(entry: dict) -> None:
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def main() -> int:
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)

    # The Phase A cell list — (condition_name, po, eng, loom_mode).
    # Each cell gets N=5 runs.
    cells = [
        # Symmetric: capacity gradient
        ("phA_haiku_sym",       "haiku",  "haiku",  "none"),
        ("phA_haiku_sym",       "haiku",  "haiku",  "eng"),
        ("phA_sonnet_sym",      "sonnet", "sonnet", "none"),
        ("phA_sonnet_sym",      "sonnet", "sonnet", "eng"),
        ("phA_opus_sym",        "opus",   "opus",   "none"),
        ("phA_opus_sym",        "opus",   "opus",   "eng"),
        # Asymmetric within Claude
        ("phA_sonnetpo_opuseng", "sonnet", "opus",   "none"),
        ("phA_sonnetpo_opuseng", "sonnet", "opus",   "eng"),
        ("phA_opuspo_sonneteng", "opus",   "sonnet", "none"),
        ("phA_opuspo_sonneteng", "opus",   "sonnet", "eng"),
    ]
    N_PER_CELL = 5

    total = len(cells) * N_PER_CELL
    completed = 0
    errors = 0
    t_start = time.time()

    log_progress({
        "kind": "batch_start",
        "total_runs": total,
        "started_at": t_start,
        "cells": [{"name": c[0], "po": c[1], "eng": c[2], "loom": c[3]} for c in cells],
    })

    for cell_idx, (condition, po, eng, loom) in enumerate(cells):
        for run_id in range(1, N_PER_CELL + 1):
            completed += 1
            print(f"[{completed}/{total}] {condition} po={po} eng={eng} loom={loom} run={run_id}",
                  flush=True)
            summary = run_one(condition, run_id, po, eng, loom)
            status = "ok"
            if summary.get("skipped"):
                status = "skip"
            elif summary.get("error"):
                status = "err"
                errors += 1
            entry = {
                "kind": "run",
                "idx": completed,
                "total": total,
                "condition": condition,
                "po": po, "eng": eng, "loom": loom, "run_id": run_id,
                "status": status,
                "final_pass_rate": summary.get("final_pass_rate"),
                "iterations": summary.get("iterations"),
                "total_tokens": summary.get("total_tokens"),
                "po_cost_usd": summary.get("po_cost_usd"),
                "eng_cost_usd": summary.get("eng_cost_usd"),
                "stop_reason": summary.get("stop_reason"),
                "error": summary.get("error"),
                "batch_duration_s": summary.get("_batch_duration_s"),
            }
            log_progress(entry)
            print(
                f"    -> {status} "
                f"pass={summary.get('final_passed','?')}/{summary.get('final_total','?')} "
                f"iters={summary.get('iterations','?')} "
                f"cost=${(summary.get('po_cost_usd',0) or 0)+(summary.get('eng_cost_usd',0) or 0):.2f} "
                f"dur={summary.get('_batch_duration_s','?')}s",
                flush=True,
            )
            time.sleep(INTER_RUN_SLEEP_S)

    elapsed = time.time() - t_start
    log_progress({
        "kind": "batch_end",
        "completed": completed,
        "errors": errors,
        "elapsed_s": round(elapsed, 1),
    })
    print(f"\n=== DONE in {elapsed/60:.1f} min. errors: {errors}/{total} ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
