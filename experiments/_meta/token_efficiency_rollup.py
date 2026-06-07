"""M30 — token-efficiency rollup across all bake-off experiments.

Walks ``experiments/bakeoff/runs-*/`` and per-experiment dirs for
trial summary JSONs, computes per-(experiment, cell) statistics:

* trials N
* mean input tokens, mean output tokens
* pass rate + Wilson 95% CI
* tokens-per-pass (efficiency ratio)

Then emits a Markdown table suitable for ``docs/EFFECTIVENESS.md``'s
"Token efficiency frontier" section, plus a JSON dump for downstream
analysis.

Why this exists
---------------
Up through M28, every bake-off trial has captured input_tokens +
output_tokens + pass/total in its summary JSON. We just never rolled
them up cross-experiment. M28's clean refutation (no quality lift,
+150-200 input tokens) is the case study for why this matters: an
intervention can cost tokens without paying back.

Usage::

    python3 experiments/_meta/token_efficiency_rollup.py
    python3 experiments/_meta/token_efficiency_rollup.py --json    # JSON output
    python3 experiments/_meta/token_efficiency_rollup.py --md      # Markdown
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]


# Experiments worth surfacing in the rollup. Each entry maps a glob
# under experiments/ to a human-friendly intervention label. Order
# matters — the table renders in this order so the reader sees the
# methodology evolution chronologically.
SOURCES: list[dict[str, Any]] = [
    {
        "label": "phL — baseline (qwen3.5, no indexer)",
        "glob": "bakeoff/runs-v2/phL_s1_cpp_*_summary.json",
        "language": "C++",
        "model_filter": "qwen3.5:latest",
    },
    {
        "label": "M10.1b — executor capacity (qwen2.5-coder:32b, no indexer)",
        "glob": "bakeoff/runs-v2/phL_s1_cpp_*_summary.json",
        "language": "C++",
        "model_filter": "qwen2.5-coder:32b",
    },
    {
        "label": "M10.2 — hand-curated stub (qwen2.5-coder:32b)",
        "glob": "bakeoff/runs-v2/phL2_*_summary.json",
        "language": "C++",
        "model_filter": "qwen2.5-coder:32b",
    },
    {
        "label": "M28 — ClangdIndexer Phase 1 (qwen2.5-coder:32b)",
        "glob": "bakeoff/runs-m28/m28_*_summary.json",
        "language": "C++",
        "model_filter": "qwen2.5-coder:32b",
    },
    {
        "label": "M29 — style constraint alone (qwen2.5-coder:32b)",
        "glob": "bakeoff/runs-m29/m29_*_summary.json",
        "language": "C++",
        "model_filter": "qwen2.5-coder:32b",
    },
    {
        "label": "M28v2 — clangd + LLM-summarized prose (qwen2.5-coder:32b)",
        "glob": "bakeoff/runs-m28v2/m28v2_*_summary.json",
        "language": "C++",
        "model_filter": "qwen2.5-coder:32b",
    },
]


# Which cells we care about. Cells outside this set get aggregated as
# "other" so cross-experiment tables stay aligned even when an
# experiment introduced a custom cell name.
CANONICAL_CELLS = ("off", "on-rule", "on-rule+placebo", "on-rule+rat")


def wilson_ci(passes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI on a binary proportion."""
    if trials == 0:
        return (0.0, 0.0)
    p = passes / trials
    denom = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(
        p * (1 - p) / trials + z * z / (4 * trials * trials)
    ) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def collect_trials(source: dict[str, Any]) -> dict[str, list[dict]]:
    """Read every trial summary matching ``source['glob']`` and bucket
    by cell. ``model_filter`` (if set) restricts to trials whose
    ``model`` field matches exactly. Cells outside CANONICAL_CELLS
    land in ``other``.
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    glob = source["glob"]
    model_filter = source.get("model_filter")
    files = list((REPO / "experiments").glob(glob))
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if model_filter and data.get("model") != model_filter:
            continue
        cell = data.get("cell", "<no-cell>")
        bucket = cell if cell in CANONICAL_CELLS else "other"
        buckets[bucket].append(data)
    return dict(buckets)


def summarize(trials: list[dict]) -> dict[str, Any]:
    """Aggregate a list of trials into a row."""
    n = len(trials)
    if n == 0:
        return {"n": 0}
    # A trial is "passing" iff passed == total > 0. Compile failures
    # count as 0/total. no_code_extracted likewise.
    passes = sum(
        1 for t in trials
        if t.get("passed", 0) == t.get("total", 0) and t.get("total", 0) > 0
    )
    rate = passes / n
    lo, hi = wilson_ci(passes, n)
    mean_in = sum(t.get("input_tokens", 0) for t in trials) / n
    mean_out = sum(t.get("output_tokens", 0) for t in trials) / n
    return {
        "n": n,
        "passes": passes,
        "pass_rate": rate,
        "ci_lo": lo,
        "ci_hi": hi,
        "mean_input_tokens": mean_in,
        "mean_output_tokens": mean_out,
        "mean_total_tokens": mean_in + mean_out,
        # Tokens-per-pass: undefined when pass_rate == 0; we report
        # mean total tokens × n / passes, or None if no passes.
        "tokens_per_pass": (
            (mean_in + mean_out) * n / passes if passes > 0 else None
        ),
    }


def render_markdown(rollup: list[dict[str, Any]]) -> str:
    """Render the rollup as a Markdown table per source."""
    lines: list[str] = []
    lines.append("# Token-Efficiency Frontier")
    lines.append("")
    lines.append(
        "Generated by `experiments/_meta/token_efficiency_rollup.py`. "
        "One table per intervention shipped or falsified. Pass rate is "
        "binary per trial (both sub-tests pass); Wilson 95% CI shown. "
        "`tokens/pass` is the efficiency ratio — lower is more "
        "token-efficient. `--` means no passes recorded "
        "(ratio undefined)."
    )
    lines.append("")
    for entry in rollup:
        lines.append(f"## {entry['label']}")
        lines.append("")
        if entry.get("language"):
            lines.append(f"_Language: {entry['language']}_")
            lines.append("")
        cells = entry["cells"]
        if not cells:
            lines.append("*No trials found.*")
            lines.append("")
            continue
        lines.append(
            "| cell | n | passes | rate | 95% CI | mean in-tok | "
            "mean out-tok | tokens/pass |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for cell in CANONICAL_CELLS + ("other",):
            row = cells.get(cell)
            if not row or row["n"] == 0:
                continue
            tpp = row["tokens_per_pass"]
            tpp_str = f"{tpp:,.0f}" if tpp is not None else "--"
            lines.append(
                f"| {cell} | {row['n']} | {row['passes']} | "
                f"{row['pass_rate']*100:.0f}% | "
                f"[{row['ci_lo']*100:.0f}%, {row['ci_hi']*100:.0f}%] | "
                f"{row['mean_input_tokens']:,.0f} | "
                f"{row['mean_output_tokens']:,.0f} | "
                f"{tpp_str} |"
            )
        lines.append("")
    return "\n".join(lines)


def build_rollup() -> list[dict[str, Any]]:
    rollup: list[dict[str, Any]] = []
    for source in SOURCES:
        buckets = collect_trials(source)
        cells = {cell: summarize(trials) for cell, trials in buckets.items()}
        rollup.append({
            "label": source["label"],
            "language": source.get("language"),
            "glob": source["glob"],
            "cells": cells,
        })
    return rollup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of Markdown")
    ap.add_argument("--md", action="store_true",
                    help="(default) Emit Markdown")
    args = ap.parse_args()

    rollup = build_rollup()

    if args.json:
        print(json.dumps(rollup, indent=2))
    else:
        print(render_markdown(rollup))
    return 0


if __name__ == "__main__":
    sys.exit(main())
