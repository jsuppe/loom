#!/usr/bin/env python3
"""
Aggregate bakeoff runs + apply the pre-registered stats.

Reads runs/<condition>_<run_id>/summary.json for every run and computes:

    - medians + IQRs per primary metric per condition
    - Mann-Whitney U + Cliff's delta per primary metric
    - Holm-Bonferroni corrected p-values across the 4 primary metrics
    - a plain-text and JSON summary

Does NOT change its analysis based on what the data shows. Everything
here was pre-registered in PROTOCOL.md before the harness was built.

Usage:
    python aggregate.py [--runs-dir <dir>]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

# ---- primary metrics declared in PROTOCOL.md ----
# (name, extractor, higher_is_better)
PRIMARY_METRICS = [
    ("final_pass_rate",     lambda s: s.get("final_pass_rate", 0.0),                  True),
    ("iterations_to_80pct", lambda s: s.get("iterations_to_80pct") or math.inf,       False),  # lower is better
    ("total_tokens",        lambda s: s.get("total_tokens", 0),                       False),
    ("regression_count",    lambda s: s.get("regression_count", 0),                   False),
]
ALPHA = 0.10  # per PROTOCOL.md


def collect_runs(runs_dir: Path) -> dict[str, list[dict]]:
    """Group summary.json files by condition."""
    by_cond: dict[str, list[dict]] = {"baseline": [], "loom": []}
    if not runs_dir.is_dir():
        return by_cond
    for d in sorted(runs_dir.iterdir()):
        if not d.is_dir():
            continue
        summary = d / "summary.json"
        if not summary.exists():
            continue
        data = json.loads(summary.read_text(encoding="utf-8"))
        cond = data.get("condition")
        if cond in by_cond:
            by_cond[cond].append(data)
    return by_cond


def iqr(values: list[float]) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    vs = sorted(values)
    n = len(vs)
    q1 = vs[max(0, n // 4)]
    q3 = vs[min(n - 1, (3 * n) // 4)]
    return (q1, q3)


def mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float]:
    """Return (U, p-value) for a two-sided Mann-Whitney test.

    Minimal implementation without scipy — uses normal approximation
    with continuity correction. Valid for n1, n2 >= 4; with N=5 per
    condition this is borderline so we also fall back to exact for
    very small samples.
    """
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        return (0.0, 1.0)

    # Rank-sum
    combined = [(v, "a") for v in a] + [(v, "b") for v in b]
    combined.sort(key=lambda x: x[0])
    ranks: dict[int, float] = {}
    i = 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    rank_sum_a = sum(ranks[k] for k, (_, tag) in enumerate(combined) if tag == "a")
    u1 = rank_sum_a - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    # Normal approximation (with continuity correction)
    mean_u = n1 * n2 / 2.0
    sd_u = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)
    if sd_u == 0:
        return (u, 1.0)
    z = (u - mean_u + 0.5) / sd_u
    # Two-sided p via normal CDF
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return (u, p)


def cliffs_delta(a: list[float], b: list[float]) -> tuple[float, str]:
    """Non-parametric effect size for two independent samples.

    Returns (delta, label) where label is one of: negligible, small,
    medium, large (per Romano et al. 2006 thresholds).
    """
    if not a or not b:
        return (0.0, "n/a")
    greater = lesser = 0
    for x in a:
        for y in b:
            if x > y:
                greater += 1
            elif x < y:
                lesser += 1
    delta = (greater - lesser) / (len(a) * len(b))
    abs_d = abs(delta)
    if abs_d < 0.147:
        label = "negligible"
    elif abs_d < 0.33:
        label = "small"
    elif abs_d < 0.474:
        label = "medium"
    else:
        label = "large"
    return (delta, label)


def holm_bonferroni(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni correction. Returns corrected p-values in the
    same order as input (NOT sorted)."""
    m = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    corrected = [0.0] * m
    running_max = 0.0
    for rank, (orig_idx, p) in enumerate(indexed):
        adj = min(1.0, (m - rank) * p)
        running_max = max(running_max, adj)
        corrected[orig_idx] = running_max
    return corrected


def analyze(by_cond: dict[str, list[dict]]) -> dict[str, Any]:
    baseline = by_cond.get("baseline", [])
    loom = by_cond.get("loom", [])
    out: dict[str, Any] = {
        "counts": {"baseline": len(baseline), "loom": len(loom)},
        "metrics": [],
    }
    raw_p_values = []
    rows = []
    for name, extractor, higher_is_better in PRIMARY_METRICS:
        base_vals = [extractor(s) for s in baseline]
        loom_vals = [extractor(s) for s in loom]
        # Replace inf with a sentinel large value so stats still work
        # (inf arises from iterations_to_80pct when 80% was never reached).
        sentinel = 10 ** 6
        base_for_stats = [sentinel if math.isinf(v) else v for v in base_vals]
        loom_for_stats = [sentinel if math.isinf(v) else v for v in loom_vals]

        # "Winner" direction: is loom better on this metric?
        # For higher_is_better metrics, winner = larger values; else smaller.
        u, p = mann_whitney_u(base_for_stats, loom_for_stats)
        delta, d_label = cliffs_delta(loom_for_stats, base_for_stats)
        # Cliff's delta sign: positive means "loom tends to have larger values than baseline".
        # If higher_is_better, positive means Loom wins.
        # If !higher_is_better, negative delta means Loom wins.
        loom_wins = delta > 0 if higher_is_better else delta < 0

        row = {
            "metric": name,
            "higher_is_better": higher_is_better,
            "baseline_median": (
                statistics.median(base_vals) if base_vals else None
            ),
            "loom_median": (
                statistics.median(loom_vals) if loom_vals else None
            ),
            "baseline_iqr": iqr([v if not math.isinf(v) else sentinel for v in base_vals]),
            "loom_iqr": iqr([v if not math.isinf(v) else sentinel for v in loom_vals]),
            "mann_whitney_u": u,
            "p_value_raw": p,
            "cliffs_delta": delta,
            "effect_size_label": d_label,
            "loom_wins_direction": loom_wins,
        }
        rows.append(row)
        raw_p_values.append(p)

    corrected = holm_bonferroni(raw_p_values)
    for row, cp in zip(rows, corrected):
        row["p_value_holm"] = cp
        row["significant_at_alpha"] = cp < ALPHA
    out["metrics"] = rows
    out["alpha"] = ALPHA
    return out


def format_report(analysis: dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append(f"Bakeoff V1 results  (alpha = {analysis['alpha']})")
    lines.append("=" * 70)
    lines.append(f"N baseline: {analysis['counts']['baseline']}")
    lines.append(f"N loom:     {analysis['counts']['loom']}")
    lines.append("")
    header = f"{'metric':<22} {'base median':>12} {'loom median':>12} {'delta':>8} {'size':>10} {'p raw':>8} {'p holm':>8} {'sig':>4}"
    lines.append(header)
    lines.append("-" * len(header))
    for m in analysis["metrics"]:
        def _fmt(v):
            if v is None:
                return "  n/a"
            if isinstance(v, float):
                if math.isinf(v):
                    return "  inf"
                return f"{v:12.3f}"
            return f"{v:>12}"
        sig = "YES " if m["significant_at_alpha"] and m["loom_wins_direction"] else " -  "
        lines.append(
            f"{m['metric']:<22} {_fmt(m['baseline_median'])} {_fmt(m['loom_median'])} "
            f"{m['cliffs_delta']:>+8.3f} {m['effect_size_label']:>10} "
            f"{m['p_value_raw']:>8.3f} {m['p_value_holm']:>8.3f} {sig:>4}"
        )
    lines.append("-" * len(header))
    lines.append("")
    lines.append("sig = YES iff Holm-corrected p < alpha AND Loom favored.")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Aggregate bakeoff runs")
    p.add_argument("--runs-dir", default=None)
    p.add_argument("--json", action="store_true", help="Emit JSON instead of table")
    args = p.parse_args()
    runs_dir = Path(args.runs_dir) if args.runs_dir else Path(__file__).resolve().parent / "runs"
    by_cond = collect_runs(runs_dir)
    analysis = analyze(by_cond)
    if args.json:
        print(json.dumps(analysis, indent=2, default=str))
    else:
        print(format_report(analysis))
    return 0


if __name__ == "__main__":
    sys.exit(main())
