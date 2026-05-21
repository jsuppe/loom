"""
M14.1 — Intake-hook precision audit.

Walks ``~/.openclaw/loom/<project>/.intake-log.jsonl`` and presents
every capturing branch (``auto_link``, ``captured_with_rationale``)
for hand-labeling. Persists labels to
``experiments/pilot/intake_audit_labels.json`` so the run is resumable
and the data is durable.

Two modes:

* Default: interactive (y/n/?/s/q) — operator labels each capture.
* ``--non-interactive``: dumps capture metadata to stdout for
  programmatic / agent labeling, no prompts.

Computed output (written next to the labels file):
  intake_audit_summary.md — precision, FP rate, breakdown by branch
                            and by kind, list of FP candidates with
                            rationales for easy review.

Run::

    python experiments/pilot/intake_audit.py --project loom
    python experiments/pilot/intake_audit.py --project loom --non-interactive

Per the M14 design, this is a one-off measurement tool, not a long-
lived CLI. Once the M14.2 detector ships, the audit can be re-run
to measure precision lift.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow this script to run out of the repo without an install.
_HERE = Path(__file__).resolve()
_REPO = _HERE.parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

from loom.store import LoomStore  # noqa: E402


CAPTURING_BRANCHES = {"auto_link", "captured_with_rationale"}
LABELS_PATH = _HERE.parent / "intake_audit_labels.json"
SUMMARY_PATH = _HERE.parent / "intake_audit_summary.md"


def _intake_log_for_project(project: str) -> Path:
    home = Path(os.path.expanduser("~"))
    return home / ".openclaw" / "loom" / project / ".intake-log.jsonl"


def load_captures(log_path: Path, store: LoomStore) -> list[dict]:
    """Return every capturing-branch record with the captured req's
    value/rationale joined in (so the audit shows what the classifier
    actually produced, not just the log metadata)."""
    if not log_path.exists():
        return []
    captures: list[dict] = []
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if rec.get("branch") not in CAPTURING_BRANCHES:
            continue
        req_id = rec.get("captured_req_id")
        if not req_id:
            continue
        req = store.get_requirement(req_id)
        captures.append({
            "req_id": req_id,
            "branch": rec.get("branch"),
            "ts": rec.get("ts"),
            "kind": rec.get("kind", "requirement"),
            "rationale_source": rec.get("rationale_source"),
            "candidates_top_score": rec.get("candidates_top_score"),
            "candidates_count": rec.get("candidates_count"),
            # M14.1 forward-only: only records written AFTER the M14.1
            # _record patch will have this field. Pre-existing records
            # show "(message not logged)" as a marker.
            "message": rec.get("message", "(message not logged)"),
            "message_truncated": rec.get("message_truncated", False),
            # Pulled live from the store at audit time. None when the
            # req has been archived / deleted since capture.
            "value": req.value if req else None,
            "rationale": req.rationale if req else None,
            "status": req.status if req else None,
            "superseded_at": req.superseded_at if req else None,
        })
    return captures


def load_labels() -> dict[str, dict]:
    """Read existing labels (resume support). Schema:

        {req_id: {"label": "y"|"n"|"?", "notes": str, "labeled_at": iso}}
    """
    if not LABELS_PATH.exists():
        return {}
    return json.loads(LABELS_PATH.read_text(encoding="utf-8"))


def save_labels(labels: dict[str, dict]) -> None:
    LABELS_PATH.write_text(
        json.dumps(labels, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _print_capture(i: int, n: int, c: dict) -> None:
    print(f"[{i}/{n}] {c['req_id']} — {c['kind']} (branch={c['branch']})")
    print(f"  status: {c['status']}"
          + (f"  superseded_at: {c['superseded_at']}" if c['superseded_at'] else ""))
    print(f"  value: {c['value']}")
    if c['rationale']:
        rat = c['rationale']
        if len(rat) > 240:
            rat = rat[:240] + "…"
        print(f"  rationale: {rat}")
    print(f"  ts: {c['ts']}, source: {c['rationale_source']}")
    if c['message'] != "(message not logged)":
        msg = c['message']
        if len(msg) > 240:
            msg = msg[:240] + "…"
        print(f"  message: {msg}")


def run_interactive(captures: list[dict], labels: dict[str, dict]) -> dict[str, dict]:
    """y = good capture, n = noise, ? = borderline, s = skip, q = quit+save."""
    from datetime import datetime, timezone
    n = len(captures)
    for i, c in enumerate(captures, 1):
        if c["req_id"] in labels and labels[c["req_id"]].get("label") in ("y", "n", "?"):
            continue
        print("\n" + "=" * 70)
        _print_capture(i, n, c)
        while True:
            choice = input("? [y/n/?/s/q] > ").strip().lower()
            if choice in ("y", "n", "?", "s", "q"):
                break
            print("  enter y, n, ?, s, or q")
        if choice == "q":
            print("Quitting; partial labels saved.")
            break
        if choice == "s":
            continue
        notes = input("  notes (optional, press enter to skip): ").strip()
        labels[c["req_id"]] = {
            "label": choice,
            "notes": notes,
            "labeled_at": datetime.now(timezone.utc).isoformat(),
            "value_at_label": c["value"],
        }
        save_labels(labels)
    return labels


def write_summary(captures: list[dict], labels: dict[str, dict]) -> None:
    from collections import Counter
    by_label = Counter()
    fp_candidates: list[dict] = []
    by_kind_total = Counter()
    by_kind_fp = Counter()
    for c in captures:
        by_kind_total[c["kind"]] += 1
        label = labels.get(c["req_id"], {}).get("label", "(unlabeled)")
        by_label[label] += 1
        if label == "n":
            fp_candidates.append(c)
            by_kind_fp[c["kind"]] += 1

    total = len(captures)
    labeled = sum(by_label[k] for k in ("y", "n", "?"))
    real = by_label["y"]
    noise = by_label["n"]
    borderline = by_label["?"]

    precision_strict = real / (real + noise) if (real + noise) > 0 else float("nan")
    precision_lenient = (real + borderline) / labeled if labeled > 0 else float("nan")

    lines = [
        "# Intake-hook precision audit (M14.1)",
        "",
        f"Run against `{LABELS_PATH.name}`. Generated from",
        f"`{_intake_log_for_project('loom').name}` capturing branches",
        f"(`auto_link` + `captured_with_rationale`).",
        "",
        "## Headline numbers",
        "",
        f"- Total captures: **{total}**",
        f"- Labeled: **{labeled}** ({labeled / total * 100:.1f}% coverage)" if total else "",
        f"- Real (y): **{real}**",
        f"- Noise (n): **{noise}**",
        f"- Borderline (?): **{borderline}**",
        "",
        f"- **Precision (strict, n=noise)**: {precision_strict:.3f} ({real}/{real + noise})",
        f"- **Precision (lenient, ? counted as good)**: {precision_lenient:.3f} ({real + borderline}/{labeled})",
        "",
        "## By kind",
        "",
        "| kind | total | noise | precision |",
        "|---|---|---|---|",
    ]
    for kind in sorted(by_kind_total):
        n_kind = by_kind_total[kind]
        fp_kind = by_kind_fp[kind]
        p = (n_kind - fp_kind) / n_kind if n_kind else float("nan")
        lines.append(f"| {kind} | {n_kind} | {fp_kind} | {p:.3f} |")
    lines.append("")

    if fp_candidates:
        lines.append("## Noise captures (label=n)")
        lines.append("")
        for c in fp_candidates:
            lines.append(f"### {c['req_id']} — {c['kind']}")
            lines.append("")
            lines.append(f"- value: {c['value']}")
            rat = (c['rationale'] or '')[:300]
            lines.append(f"- rationale: {rat}")
            note = labels.get(c["req_id"], {}).get("notes", "")
            if note:
                lines.append(f"- audit note: {note}")
            lines.append("")

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSummary written to {SUMMARY_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="loom")
    ap.add_argument("--non-interactive", action="store_true",
                    help="Dump captures to stdout as JSON; skip prompts")
    ap.add_argument("--summary-only", action="store_true",
                    help="Skip labeling; just regenerate the summary doc "
                         "from the existing labels file")
    args = ap.parse_args()

    log_path = _intake_log_for_project(args.project)
    store = LoomStore(project=args.project)
    captures = load_captures(log_path, store)
    labels = load_labels()

    if args.non_interactive:
        for c in captures:
            print(json.dumps(c, ensure_ascii=False))
        return 0

    print(f"Found {len(captures)} captures in {log_path}")
    print(f"Existing labels: {len(labels)}")
    print(f"Labels file: {LABELS_PATH}")

    if not args.summary_only:
        labels = run_interactive(captures, labels)

    write_summary(captures, labels)
    return 0


if __name__ == "__main__":
    sys.exit(main())
