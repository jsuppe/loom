#!/usr/bin/env python3
"""
AI-classification pass for M19 drift-eval CSV.

The pre-reg specifies a hand-classification step. This is a
*first-pass AI classification* applied per the locked rubric. The
classifications are recorded as `tp_fp_ambig` + `bin_code` columns
plus a `classifier_note` indicating provenance. The user can review
and override.

The pre-reg's Texas-sharpshooter rule forbids changing the rubric
post-hoc; this script applies the rubric as written. If any case is
ambiguous, it is marked `Ambig` and excluded from the precision
denominator.
"""
import csv
from pathlib import Path

_HERE = Path(__file__).resolve().parent
CSV_PATH = _HERE / "m19_classifications.csv"

# Manual classification of each case based on inspecting the commit
# message + diff stat + diff preview. Format: i -> (bin_code, tp_fp,
# rationale).
CLASSIFICATIONS = {
    # phT_rule_precedence_smoke.py @ generalized-harness:
    # adds new R_imperative_pro cell to CELL_CONFIG (verified via git
    # diff). New diagnostic experiment cell — substantive behavior change.
    0: ("M-Behav", "TP", "adds R_imperative_pro cell to CELL_CONFIG"),
    # phT @ port-to-claude-cli: adds new code path for Claude CLI vs
    # Ollama; substantive behavior change.
    1: ("M-Behav", "TP", "ports execution path from Ollama to Claude CLI shell-out"),
    # phT @ initial: 418-line file creation. Inception event; entire
    # current behavior didn't exist at this commit.
    2: ("M-Behav", "TP", "file inception (+418 lines, no prior version)"),
    # phU @ port-to-claude-cli: same as phT case 1.
    3: ("M-Behav", "TP", "ports execution path from Ollama to Claude CLI shell-out"),
    # phU @ initial: 431-line file creation.
    4: ("M-Behav", "TP", "file inception (+431 lines, no prior version)"),
    # FINDINGS-bakeoff-v3-payload-sharpening.md @ initial creation:
    # 229-line findings doc creation. The linked req REQ-c0b0a242 is
    # about the findings content; the file's intent IS the content.
    5: ("M-Intent", "TP", "findings doc inception (+229 lines, no prior version)"),
    # phQ3 @ initial: 437-line file creation.
    6: ("M-Behav", "TP", "file inception (+437 lines, no prior version)"),
    # phQ4 @ initial: 352-line file creation.
    7: ("M-Behav", "TP", "file inception (+352 lines, no prior version)"),
    # phQ7 @ initial: 407-line file creation.
    8: ("M-Behav", "TP", "file inception (+407 lines, no prior version)"),
    # phR @ port-to-claude-cli: same pattern as phT/phU port.
    9: ("M-Behav", "TP", "ports execution path from Ollama to Claude CLI shell-out"),
    # phR @ initial: 456-line file creation.
    10: ("M-Behav", "TP", "file inception (+456 lines, no prior version)"),
    # phS @ port-to-claude-cli: same pattern.
    11: ("M-Behav", "TP", "ports execution path from Ollama to Claude CLI shell-out"),
    # phS @ initial: 360-line file creation.
    12: ("M-Behav", "TP", "file inception (+360 lines, no prior version)"),
    # indexers_js.py @ indexer-doctor: adds health() method on
    # SemanticIndexer subclass — public API addition.
    13: ("M-API", "TP", "adds health() method to JsIndexer (public API)"),
    # indexers_js.py @ v2: filter logic for import refs + adjacent
    # type defs — behavior change in indexing pipeline.
    14: ("M-Behav", "TP", "changes JsIndexer filter logic for refs (behavior)"),
    # indexers_js.py @ initial: 502-line file creation.
    15: ("M-Behav", "TP", "file inception (+502 lines, no prior version)"),
    # warrants_l2_results.json @ initial: 440-line results file
    # creation. Linked req REQ-bdb1e667 is about Phase L2 validator
    # results; file's intent IS the data.
    16: ("M-Intent", "TP", "results JSON inception (+440 lines, no prior version)"),
}


def main() -> int:
    rows = []
    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if len(rows) != len(CLASSIFICATIONS):
        print(f"WARN: {len(rows)} rows in CSV vs {len(CLASSIFICATIONS)} "
              f"classifications — please re-run eval or update classify.py")

    for i, row in enumerate(rows):
        if i not in CLASSIFICATIONS:
            continue
        bin_code, tp_fp, note = CLASSIFICATIONS[i]
        row["bin_code"] = bin_code
        row["tp_fp_ambig"] = tp_fp
        row["classifier_note"] = (
            f"AI-classified by assistant per locked rubric: {note}"
        )

    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    # Summary
    tp = sum(1 for r in rows if r["tp_fp_ambig"] == "TP")
    fp = sum(1 for r in rows if r["tp_fp_ambig"] == "FP")
    amb = sum(1 for r in rows if r["tp_fp_ambig"] == "Ambig")
    denom = tp + fp  # Ambig excluded per pre-reg
    precision = tp / denom if denom else 0.0
    print(f"Classification summary:")
    print(f"  TP   : {tp}")
    print(f"  FP   : {fp}")
    print(f"  Ambig: {amb}  (excluded from precision)")
    print(f"  Precision (TP / (TP+FP)) = {precision*100:.1f}% (n={denom})")

    by_bin = {}
    for r in rows:
        by_bin[r["bin_code"]] = by_bin.get(r["bin_code"], 0) + 1
    print(f"\nBin distribution:")
    for k in sorted(by_bin):
        print(f"  {k:10s}: {by_bin[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
