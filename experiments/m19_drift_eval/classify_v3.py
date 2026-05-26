#!/usr/bin/env python3
"""
AI-classification pass for M19v3 req-relevance precision study.

For each drift event in m19v3_classifications.csv, apply the locked
rubric (R-Direct / R-Indirect / R-Unrelated / Cosmetic / Ambig) by
hand-reading the diff vs the linked req's value. Classifications are
recorded with per-case rationale in the `ai_note` column for user
spot-check.

Per pre-reg M19v3.4: AI first-pass; user 20% spot-check for kappa;
if kappa < 0.5 the user's classifications become the only data.

Small N=16 drift events make heuristic classification noisier than
per-case judgment. This file just records the per-case decisions
plus rationale; the heuristics are in the reasoning, not in code.
"""
import csv
from pathlib import Path

_HERE = Path(__file__).resolve().parent
CSV_PATH = _HERE / "m19v3_classifications.csv"


# Keyed by (file, commit[:12]) since some files have multiple commits.
# Each entry: (bin_code, tp_fp, one-line-rationale).
CLASSIFICATIONS = {
    # ============================================================
    # REQ-2a621c40: JsIndexer (and similar LSP-backed indexers) MUST
    # be pointed at the project root including test files.
    # ============================================================
    ("src/loom/indexers_js.py", "b19ddb5eb2e9"): (
        "R-Indirect", "TP",
        "JsIndexer v2 filter logic — adjacent change to the same "
        "indexer the req constrains; maintainer of REQ-2a621c40 "
        "should know about JsIndexer behavioral changes",
    ),
    ("src/loom/indexers_js.py", "5d094d13c1c2"): (
        "R-Direct", "TP",
        "File inception of JsIndexer — the req IS about this class",
    ),
    ("src/loom/indexers.py", "adf6d32d4946"): (
        "R-Indirect", "TP",
        "SemanticIndexer registry inception — defines the interface "
        "JsIndexer implements; adjacent infra for the req's mandate",
    ),

    # ============================================================
    # REQ-ec36bd89: Loom requirements MUST include rationale (prose
    # or rationale_links). Bare-rule reqs without rationale rejected.
    # ============================================================
    ("src/loom/intake.py", "d806558dcd71"): (
        "R-Indirect", "TP",
        "Kind-aware classifier in intake — routes captures correctly "
        "but the req is about RATIONALE requirement; same intake "
        "flow, different concern",
    ),
    ("src/loom/intake.py", "4eb2f684bcc0"): (
        "R-Direct", "TP",
        "Intake hook scaffold inception — the hook IS what enforces "
        "the rationale-required rule at capture time",
    ),

    # ============================================================
    # REQ-aaa595ca: Loom executor selection MUST consider spec
    # contrarian-shape, not just language.
    # ============================================================
    ("src/loom/exec_cli.py", "39673f8302c4"): (
        "R-Unrelated", "FP",
        "Massive packaging restructure (convert to proper Python "
        "package) — moves file into src/loom/; unrelated to "
        "executor-selection logic the req constrains",
    ),

    # ============================================================
    # REQ-6c353203: The system must use a push-based webhook
    # architecture for foundation drift events.
    # ============================================================
    ("src/loom/driftgraph_http.py", "6a3be06d3dee"): (
        "R-Indirect", "TP",
        "L4 partial + HTTP read API — driftgraph_http carries both "
        "directions of the channel; push surface is part of file's "
        "concern even when this commit emphasizes read",
    ),
    ("src/loom/driftgraph_cache.py", "e6e84168a202"): (
        "R-Direct", "TP",
        "Push-based cache + webhook receiver inception — exactly "
        "the architecture the req mandates",
    ),

    # ============================================================
    # REQ-27023c4b: The system must maintain a log to enable
    # tracking back on previous information or decisions.
    # ============================================================
    ("src/loom/store.py", "9bd1c4c41dca"): (
        "R-Unrelated", "FP",
        "Unlink/supersession workflow — different concern from "
        "log/tracking-back. Touches store but unrelated to req",
    ),
    ("src/loom/store.py", "7f25ecd05977"): (
        "R-Indirect", "TP",
        "Per-kind lifecycle states — extends the log's state model; "
        "maintainer of the log-tracking req should know about state "
        "machine expansions",
    ),
    ("src/loom/store.py", "1303a3060b7a"): (
        "R-Indirect", "TP",
        "Adds Requirement.kind field — extends the log's data model; "
        "directly affects what's tracked",
    ),
    ("src/loom/store.py", "b80cdf41da0f"): (
        "R-Unrelated", "FP",
        "is_complete() method + audit-rationale — methods on "
        "Requirement; tangential to log/tracking semantics",
    ),
    ("src/loom/store.py", "ac42e381ff4a"): (
        "R-Indirect", "TP",
        "Linkage data model + queries — extends the log structure "
        "and read paths; directly part of tracking-back capability",
    ),
    ("src/loom/store.py", "504702230d24"): (
        "R-Unrelated", "FP",
        "Small (6L) addition for indexer-doctor support — touches "
        "store but is plumbing for the indexer health command, not "
        "the log-tracking concern",
    ),
    ("src/loom/store.py", "adf6d32d4946"): (
        "R-Indirect", "TP",
        "9L for indexer metadata fields (symbol_ticket etc.) — "
        "extends the log's stored fields; adjacent to tracking",
    ),
    ("src/loom/store.py", "39673f8302c4"): (
        "R-Unrelated", "FP",
        "Massive packaging restructure — file moved into src/loom/; "
        "1113L diff is mostly path/import changes, not about log "
        "semantics",
    ),
}


def main() -> int:
    rows = []
    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    bins = {}
    tp_fp = {"TP": 0, "FP": 0, "Ambig": 0, "no_drift": 0}

    for row in rows:
        if row["drift_fires"] != "yes":
            tp_fp["no_drift"] += 1
            row["ai_bin"] = "(no drift)"
            row["ai_tp_fp"] = "(no drift)"
            row["ai_note"] = "hash matches baseline"
            row["final_bin"] = "(no drift)"
            row["final_tp_fp"] = "(no drift)"
            continue
        key = (row["file"], row["commit"])
        if key not in CLASSIFICATIONS:
            row["ai_bin"] = "Ambig"
            row["ai_tp_fp"] = "Ambig"
            row["ai_note"] = "no classification recorded"
            row["final_bin"] = "Ambig"
            row["final_tp_fp"] = "Ambig"
            tp_fp["Ambig"] += 1
            continue
        bin_code, tp_fp_label, rationale = CLASSIFICATIONS[key]
        row["ai_bin"] = bin_code
        row["ai_tp_fp"] = tp_fp_label
        row["ai_note"] = (
            f"AI-classified per locked rubric: {rationale}"
        )
        # Pre-fill final_bin with AI; user spot-check may override.
        row["final_bin"] = bin_code
        row["final_tp_fp"] = tp_fp_label
        tp_fp[tp_fp_label] = tp_fp.get(tp_fp_label, 0) + 1
        bins[bin_code] = bins.get(bin_code, 0) + 1

    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    denom = tp_fp["TP"] + tp_fp["FP"]
    precision = tp_fp["TP"] / denom if denom else 0.0

    print(f"M19v3 AI classification ({len(rows)} rows; {tp_fp['no_drift']} TN):")
    print(f"  TP:    {tp_fp['TP']}  (R-Direct + R-Indirect)")
    print(f"  FP:    {tp_fp['FP']}  (R-Unrelated + Cosmetic)")
    print(f"  Ambig: {tp_fp['Ambig']}  (excluded from precision)")
    print(f"  Precision (TP / (TP+FP)) = {precision*100:.1f}%  n={denom}")
    print()
    print("Bin distribution:")
    for k in sorted(bins):
        print(f"  {k:12s}: {bins[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
