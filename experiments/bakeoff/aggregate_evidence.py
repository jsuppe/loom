#!/usr/bin/env python3
"""
aggregate_evidence.py — produce a single shareable Markdown report
summarizing every Loom bakeoff trial.

Walks `experiments/bakeoff/runs-v2/` and collects per-trial summary
JSON (both flat *.json files and dir/summary.json forms produced
across phases A/B/C/D/E/F/G). Groups by experiment cell, computes
pass rate / median wall / total tokens / total cost, and writes
`EVIDENCE_REPORT.md` alongside the FINDINGS-*.md documents.

Run from the repo root:
    python3 experiments/bakeoff/aggregate_evidence.py
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
RUNS = REPO / "experiments" / "bakeoff" / "runs-v2"
FINDINGS = REPO / "experiments" / "bakeoff"
OUT = REPO / "experiments" / "bakeoff" / "EVIDENCE_REPORT.md"


def extract_phase(name: str) -> tuple[str, str]:
    """Map a filename or dirname to (phase_label, cell_label).

    phase_label is 'A', 'B', 'C/dart-orders', etc.
    cell_label is the within-phase variant (e.g. 'haiku±loom', 'qwen3.5').
    """
    n = name.replace(".json", "").replace("_summary", "")
    # Phase A: phA_<po>_<eng>_<paramstring>_NNN
    if n.startswith("phA_"):
        if "engL" in n: loom = "+L"
        elif "noneL" in n: loom = "-L"
        else: loom = "?"
        # po-eng pair
        if "haiku_sym" in n: cell = f"A/haiku⇆haiku{loom}"
        elif "opus_sym" in n: cell = f"A/opus⇆opus{loom}"
        elif "sonnet_sym" in n: cell = f"A/sonnet⇆sonnet{loom}"
        elif "opuspo_sonneteng" in n: cell = f"A/opus·sonnet{loom}"
        elif "sonnetpo_opuseng" in n: cell = f"A/sonnet·opus{loom}"
        else: cell = f"A/{n[:30]}"
        return "A", cell
    # Phase B trials (state-machine ±Loom across model tiers)
    if n.startswith("phB_opus_sym_retest"):
        return "B", "B/opus⇆opus retest"
    if n.startswith("phB_haiku_sym"):
        loom = "+L" if "engL" in n else ("-L" if "noneL" in n else "?")
        return "B", f"B/haiku⇆haiku{loom}"
    if n.startswith("phB_opus_sym"):
        loom = "+L" if "engL" in n else ("-L" if "noneL" in n else "?")
        return "B", f"B/opus⇆opus{loom}"
    if n.startswith("phB_sonnet_sym"):
        loom = "+L" if "engL" in n else ("-L" if "noneL" in n else "?")
        return "B", f"B/sonnet⇆sonnet{loom}"
    if n.startswith("v2_parity_baseline"): return "B", "B/sonnet baseline"
    if n.startswith("v2_parity_loom"): return "B", "B/sonnet+loom"
    if n.startswith("c3_sonnet_loom"): return "B", "B/c3-sonnet+loom"
    if n.startswith("c4_sonnet_baseline"): return "B", "B/c4-sonnet baseline"
    # Phase C inventories
    if n.startswith("phC_python_inv_runp"): return "C/python-inventory", "py-inv N=5 qwen3.5"
    if n.startswith("phC_python_inv_runsmoke"): return "C/python-inventory", "py-inv smoke"
    if n.startswith("phC_cpp_inv_runv2_") or n.startswith("phC_cpp_inv_runsmoke_v2"): return "C/cpp-inventory", "cpp-inv v2 (split) qwen-coder:32b"
    if n.startswith("phC_cpp_inv_runc"): return "C/cpp-inventory", "cpp-inv v1 (header-only) qwen-coder:32b"
    if n.startswith("phC_cpp_inv_runsmoke"): return "C/cpp-inventory", "cpp-inv smoke"
    if n.startswith("phC_dart_inv_rund"): return "C/dart-inventory", "dart-inv qwen-coder:32b"
    if n.startswith("phC_dart_inv_runsmokeBP"): return "C/dart-inventory", "dart-inv blueprint smoke"
    if n.startswith("phC_dart_inv_runsmoke"): return "C/dart-inventory", "dart-inv smoke"
    if n.startswith("phC_dart_inv_runA"): return "C/dart-inventory", "dart-inv v3/v4 cell A"
    if n.startswith("phC_dart_inv_runB"): return "C/dart-inventory", "dart-inv v3/v4 cell B"
    if n.startswith("phC_dart_inv"): return "C/dart-inventory", "dart-inv"
    if n.startswith("phC_dart_run"):
        return "C/dart-orders", "dart-orders Tier-progression qwen3.5"
    if n.startswith("phC_cpp_run"): return "C/cpp-orders", "cpp-orders qwen-coder:32b"
    # Phase D
    if n.startswith("phD_auto_python_queue"): return "D", "D/python-queue asym"
    if n.startswith("phD_auto"): return "D", "D/state-machine asym"
    if n.startswith("phD_oneshot_run"): return "D", "D/state-machine one-shot"
    if n.startswith("phD_run_"): return "D", "D/state-machine v0 manual"
    if n.startswith("phD_smoke"): return "D", "D/state-machine smoke"
    # Phase E + variants. Each filename is an AGGREGATE; the cell label
    # describes the aggregate's scope. Sub-trial detail is preserved in
    # the expanded results.
    if n.startswith("phE_scale_"):
        return "E.scale", f"E.scale {n.replace('phE_scale_smoke_', '')}"
    if n.startswith("phE_block_"):
        return "E.block", f"E.block {n.replace('phE_block_smoke_', '')}"
    if n.startswith("phE_hook_"):
        return "E", f"E hook {n.replace('phE_hook_smoke_', '')}"
    if n.startswith("phE_"): return "E", n
    # Phase F
    if n.startswith("phF_"): return "F", n
    # Phase G — rationale citation aggregate files
    if n.startswith("phG_rationale_smoke_haiku_s1"): return "G", "G/haiku S1 smoke"
    if n.startswith("phG_rationale_smoke_haiku"): return "G", "G/haiku rationale"
    if n.startswith("phG_rationale_smoke_sonnet"): return "G", "G/sonnet rationale"
    if n.startswith("phG_replay_audit"): return "G", "G/replay audit"
    if n.startswith("phG_haiku_backup"): return "G", "G/haiku backup"
    if n.startswith("phG_"): return "G", n
    # Default
    return "other", n


def load_summary(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_aggregate(d: dict) -> bool:
    """Phase E/G aggregate files have a `results` list of sub-trials.

    Schema: {n, scenarios?, results: [{scenario, hook?, pass, cost_usd, elapsed_s, ...}]}
    """
    return isinstance(d, dict) and isinstance(d.get("results"), list)


def expand_aggregate(d: dict) -> list[dict]:
    """Convert an aggregate result file into individual trial dicts."""
    out = []
    for r in d.get("results", []):
        # Normalize to the per-trial schema the aggregator expects.
        passed = 1 if r.get("pass") else 0
        total = 1 if "pass" in r else 0
        out.append({
            "passed": passed,
            "total": total,
            "wall_s": r.get("elapsed_s", 0),
            "opus_cost_usd": r.get("cost_usd", 0),
            "_aggregate_meta": {
                "scenario": r.get("scenario"),
                "hook": r.get("hook"),
                "model": r.get("model"),
                "verifier_reason": r.get("verifier_reason"),
            },
        })
    return out


def collect() -> dict:
    """Return {phase: {cell: [trial_dicts]}}."""
    bins: dict[str, dict[str, list[dict]]] = {}
    for entry in sorted(RUNS.iterdir()):
        if entry.is_file() and entry.suffix == ".json":
            d = load_summary(entry)
            if not d: continue
            phase, cell = extract_phase(entry.name)
        elif entry.is_dir():
            sj = entry / "summary.json"
            if not sj.exists(): continue
            d = load_summary(sj)
            if not d: continue
            phase, cell = extract_phase(entry.name)
        else:
            continue
        # Aggregate phE/phG result files contain many sub-trials; expand
        # them so the per-cell stats are accurate.
        if is_aggregate(d):
            for sub in expand_aggregate(d):
                bins.setdefault(phase, {}).setdefault(cell, []).append(sub)
        else:
            bins.setdefault(phase, {}).setdefault(cell, []).append(d)
    return bins


def median_safe(xs):
    xs = [x for x in xs if x is not None]
    if not xs: return None
    return statistics.median(xs)


def sum_safe(xs):
    return sum(x for x in xs if x is not None)


def fmt_pass_rate(d: dict) -> tuple[int, int]:
    """Extract passed/total from a trial dict (schema varies)."""
    p = d.get("passed", d.get("final_passed", 0))
    t = d.get("total", d.get("final_total", 0))
    return p, t


def fmt_cost(d: dict) -> float:
    """Extract a comparable cost number."""
    return (
        d.get("opus_cost_usd")
        or d.get("po_cost_usd", 0) + d.get("eng_cost_usd", 0)
        or 0.0
    )


def fmt_wall(d: dict) -> float:
    return (
        d.get("wall_s")
        or d.get("duration_s")
        or 0.0
    )


def fmt_tokens(d: dict) -> int:
    return (
        d.get("total_tokens")
        or (d.get("po_in", 0) + d.get("po_out", 0)
            + d.get("eng_in", 0) + d.get("eng_out", 0))
        or d.get("opus_input_tokens", 0) + d.get("opus_output_tokens", 0)
        or 0
    )


def cell_stats(trials: list[dict]) -> dict:
    n = len(trials)
    if n == 0:
        return {"n": 0}
    passes = [fmt_pass_rate(t) for t in trials]
    pass_rates = [p / t if t > 0 else 0.0 for p, t in passes]
    full_passes = sum(1 for p, t in passes if t > 0 and p == t)
    walls = [fmt_wall(t) for t in trials]
    costs = [fmt_cost(t) for t in trials]
    tokens = [fmt_tokens(t) for t in trials]
    return {
        "n": n,
        "full_pass_count": full_passes,
        "full_pass_rate_pct": round(100 * full_passes / n, 1),
        "median_pass_rate": round(statistics.median(pass_rates), 3),
        "median_wall_s": round(statistics.median(walls), 1),
        "median_cost_usd": round(statistics.median(costs), 4),
        "total_cost_usd": round(sum(costs), 4),
        "total_tokens": sum(tokens),
    }


def render(bins: dict) -> str:
    lines = []
    lines.append("# Loom — Aggregated Experimental Evidence")
    lines.append("")
    lines.append("Auto-generated by `experiments/bakeoff/aggregate_evidence.py`.")
    lines.append("Walks every per-trial summary in `experiments/bakeoff/runs-v2/`")
    lines.append("and groups by phase + experiment cell.")
    lines.append("")

    # Top-line totals
    total_trials = sum(
        len(trials) for cells in bins.values() for trials in cells.values()
    )
    total_cost = sum(
        sum(fmt_cost(t) for t in trials)
        for cells in bins.values() for trials in cells.values()
    )
    total_tokens = sum(
        sum(fmt_tokens(t) for t in trials)
        for cells in bins.values() for trials in cells.values()
    )
    full_passes = sum(
        sum(1 for t in trials
            if fmt_pass_rate(t)[1] > 0 and fmt_pass_rate(t)[0] == fmt_pass_rate(t)[1])
        for cells in bins.values() for trials in cells.values()
    )
    lines.append("## Top-line totals")
    lines.append("")
    lines.append(f"- Total trials recorded: **{total_trials}**")
    lines.append(f"- Trials at 100 % pass: **{full_passes}** "
                 f"({100*full_passes/total_trials:.1f} %)")
    lines.append(f"- Total Opus/PO cost across all trials: **${total_cost:.2f}**")
    lines.append(f"- Total tokens across all trials: **{total_tokens:,}**")
    lines.append("")

    # Per-phase breakdown
    phase_order = [
        "A", "B", "C/dart-orders", "C/cpp-orders",
        "C/python-inventory", "C/dart-inventory", "C/cpp-inventory",
        "D", "E", "E.scale", "E.block", "F", "G", "other",
    ]
    phase_summaries = {p: bins.get(p, {}) for p in phase_order if p in bins}

    for phase, cells in phase_summaries.items():
        if not cells: continue
        lines.append(f"## Phase {phase}")
        lines.append("")
        lines.append("| cell | N | full-pass | median pass | median wall (s) | median cost ($) | total cost ($) |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        # Sort cells by name for stability
        for cell, trials in sorted(cells.items()):
            s = cell_stats(trials)
            if s["n"] == 0: continue
            lines.append(
                f"| {cell} | {s['n']} | {s['full_pass_count']}/{s['n']} "
                f"({s['full_pass_rate_pct']}%) | {s['median_pass_rate']:.3f} | "
                f"{s['median_wall_s']} | {s['median_cost_usd']:.4f} | "
                f"{s['total_cost_usd']:.4f} |"
            )
        # Phase total line
        all_trials = [t for trials in cells.values() for t in trials]
        ps = cell_stats(all_trials)
        lines.append(
            f"| **phase total** | **{ps['n']}** | "
            f"**{ps['full_pass_count']}/{ps['n']} ({ps['full_pass_rate_pct']}%)** "
            f"| | | | **{ps['total_cost_usd']:.2f}** |"
        )
        lines.append("")

    # Per-language fitness map
    lines.append("## Per-language fitness map (synthesized)")
    lines.append("")
    lines.append("Pass rates across all relevant Phase C / D cells, by language and project size.")
    lines.append("")
    lines.append("| language | scale | best pass rate | best executor | sample |")
    lines.append("|---|---|---|---|---|")
    py_d = bins.get("D", {}).get("D/state-machine asym", []) + bins.get("D", {}).get("D/python-queue asym", [])
    py_inv = bins.get("C/python-inventory", {}).get("py-inv N=5 qwen3.5", [])
    cpp_orders = bins.get("C/cpp-orders", {}).get("cpp-orders qwen-coder:32b", [])
    cpp_inv_v1 = bins.get("C/cpp-inventory", {}).get("cpp-inv v1 (header-only) qwen-coder:32b", [])
    cpp_inv_v2 = bins.get("C/cpp-inventory", {}).get("cpp-inv v2 (split) qwen-coder:32b", [])
    dart_orders = bins.get("C/dart-orders", {}).get("dart-orders Tier-progression qwen3.5", [])
    dart_inv = bins.get("C/dart-inventory", {}).get("dart-inv qwen-coder:32b", [])

    def rate(trials):
        if not trials: return None
        full = sum(1 for t in trials if fmt_pass_rate(t)[1] > 0 and fmt_pass_rate(t)[0] == fmt_pass_rate(t)[1])
        return f"{full}/{len(trials)} = {100*full/len(trials):.0f}%"

    for label, scale, trials, exe in [
        ("Python", "single-file (D)", py_d, "qwen3.5:latest"),
        ("Python", "9-file (C/python-inventory)", py_inv, "qwen3.5:latest"),
        ("C++", "single-header (C/cpp-orders)", cpp_orders, "qwen2.5-coder:32b"),
        ("C++", "13-file v2 split (C/cpp-inventory)", cpp_inv_v2, "qwen2.5-coder:32b"),
        ("C++", "9-header v1 (C/cpp-inventory)", cpp_inv_v1, "qwen2.5-coder:32b"),
        ("Dart", "3-file (C/dart-orders Tier-progression)", dart_orders, "qwen3.5:latest"),
        ("Dart", "9-file (C/dart-inventory)", dart_inv, "qwen2.5-coder:32b"),
    ]:
        r = rate(trials) or "(no trials)"
        n = len(trials)
        lines.append(f"| {label} | {scale} | {r} | {exe} | N={n} |")
    lines.append("")
    lines.append("Note: these tables aggregate every trial recorded; some cells")
    lines.append("contain in-flight or smoke trials. See per-phase tables above")
    lines.append("for the full breakdown.")
    lines.append("")

    # Caveats — what some phases actually measure
    lines.append("## How to read these tables (per-phase metric notes)")
    lines.append("")
    lines.append("Several phases measure something other than \"did the test")
    lines.append("suite pass.\" Reading the `full-pass` column literally for")
    lines.append("those phases will mislead.")
    lines.append("")
    lines.append("- **Phase A / B (in-session ±Loom):** TaskQueue and")
    lines.append("  state-machine were *saturated* at every Claude tier. Both")
    lines.append("  cells (with and without Loom) hit 100 %. The phase")
    lines.append("  measures **cost overhead**, not correctness lift. See")
    lines.append("  per-phase `total cost` columns.")
    lines.append("")
    lines.append("- **Phase D (asymmetric pipeline):** Pass-rate matters here")
    lines.append("  AND so does cost ratio vs. the in-session baseline. The")
    lines.append("  ~8× cost claim comes from comparing D's `total cost` to")
    lines.append("  the equivalent Phase B cell's `total cost`. See")
    lines.append("  `FINDINGS-bakeoff-v2-pilot.md` for the breakdown.")
    lines.append("")
    lines.append("- **Phase E (pre-edit hook on/off):** \"pass\" here means")
    lines.append("  *the agent complied with the requirement under the")
    lines.append("  hook setting*. The headline finding (+93pp Sonnet, +60pp")
    lines.append("  Haiku, 0pp Opus) compares the *delta* between hook-on and")
    lines.append("  hook-off cells, not the absolute pass rate.")
    lines.append("")
    lines.append("- **Phase E.scale:** measures hook *latency* under 100 /")
    lines.append("  500-file synthetic projects, not pass rate. The 0/0")
    lines.append("  full-pass count in the table is an artifact of the")
    lines.append("  aggregator; the actual finding is constant-time hook")
    lines.append("  latency around 800 ms.")
    lines.append("")
    lines.append("- **Phase E.block (hard-block on drift):** \"pass=false\" is")
    lines.append("  the *expected* outcome — the hook blocked the edit. The")
    lines.append("  0/30 in the table is the agent failing to bypass the")
    lines.append("  block, which is exactly what we wanted. The mechanism is")
    lines.append("  30/30 reliable; the 0 % \"pass rate\" is a misreading of")
    lines.append("  the field semantics.")
    lines.append("")
    lines.append("- **Phase G (cross-session rationale):** \"pass\" is whether")
    lines.append("  the agent cited the rationale verbatim or paraphrased.")
    lines.append("  The headline finding (100 % Haiku, 93 % Sonnet citation")
    lines.append("  rate) comes from the with-rationale cell only;")
    lines.append("  without-rationale cell stays near 0 %. The aggregate")
    lines.append("  62.8 % across all G cells in this table mixes those.")
    lines.append("")
    lines.append("For detailed per-cell semantics, see the FINDINGS docs")
    lines.append("listed at the bottom.")
    lines.append("")

    # Findings doc cross-reference
    lines.append("## Narrative findings docs")
    lines.append("")
    for f in sorted(FINDINGS.glob("FINDINGS-*.md")):
        lines.append(f"- [{f.name}]({f.name})")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("Regenerate with `python3 experiments/bakeoff/aggregate_evidence.py`.")
    return "\n".join(lines)


def main():
    bins = collect()
    OUT.write_text(render(bins), encoding="utf-8")
    print(f"wrote {OUT}")
    # Quick recap to stdout
    total = sum(len(t) for c in bins.values() for t in c.values())
    print(f"  {total} trials across {sum(len(c) for c in bins.values())} cells")


if __name__ == "__main__":
    main()
