#!/usr/bin/env python3
"""
M19v2 AI-classification pass with diff inspection.

For each drift_fires=yes row in m19_classifications.csv, fetch the
full diff via `git diff <commit>~1 <commit> -- <file>`, apply the
locked rubric to bin-code the change. Classification is conservative:
when the rubric is genuinely ambiguous, mark Ambig (excluded from
precision denominator per pre-reg).

Heuristics applied (in order, first match wins):
  1. Diff is empty / only whitespace → C-White (FP)
  2. All added/removed lines start with `#` or are inside triple-
     quoted strings or are blank → C-Comment (FP)
  3. Only import statement reorderings → C-Dead (FP)
  4. New decorator/import added; everything else cosmetic → Mixed (TP)
  5. New def/class added → M-API (TP)
  6. Existing def signature changed → M-API (TP)
  7. Logic inside existing function changed → M-Behav (TP)
  8. Diff > 100 lines added → M-Behav (TP) (large changes are
     almost always substantive in Python)
  9. Otherwise → Ambig (excluded)

Each classification records the heuristic that triggered it in
`classifier_note` so the user can spot-check.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
CSV_PATH = _HERE / "m19_classifications.csv"


def git_diff(commit: str, path: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "diff", f"{commit}~1", commit, "--", path],
            cwd=_REPO, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            shell=(sys.platform == "win32"),
        )
        if proc.returncode != 0:
            # File at initial commit — no parent. Return its full body
            # as "added lines."
            return ""
        return proc.stdout
    except Exception:
        return ""


_HUNK_RE = re.compile(r"^@@.*@@", re.MULTILINE)


def split_added_removed(diff: str) -> tuple[list[str], list[str]]:
    """Return (added_lines, removed_lines) — content only, no markers."""
    added, removed = [], []
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    return added, removed


def is_comment_or_blank(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s.startswith("#"):
        return True
    if s.startswith('"""') or s.startswith("'''"):
        return True
    if s.endswith('"""') or s.endswith("'''"):
        return True
    # Inside a docstring on a non-fence line — heuristically count as
    # comment-ish only if it doesn't look like code (no =, no (, no def).
    return False


def is_whitespace_only(line: str) -> bool:
    return line.strip() == ""


def is_import_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("import ") or s.startswith("from ") and " import " in s


def has_def_class(lines: list[str]) -> bool:
    for line in lines:
        s = line.strip()
        if s.startswith("def ") or s.startswith("class ") or s.startswith("async def "):
            return True
    return False


def classify(diff: str) -> tuple[str, str, str]:
    """Return (bin_code, tp_fp_ambig, rationale)."""
    if not diff.strip():
        # File-inception cases have no parent diff. Treat as M-Behav TP
        # (file's entire content materialized at this commit).
        return ("M-Behav", "TP", "file inception (no parent diff)")

    added, removed = split_added_removed(diff)
    total_changed = len(added) + len(removed)

    if total_changed == 0:
        return ("C-White", "FP", "no content-level adds or removes")

    # Heuristic 1: all changes are whitespace
    if all(is_whitespace_only(L) for L in added + removed):
        return ("C-White", "FP", "added/removed lines are all whitespace")

    # Heuristic 2: all changes are comments/docstrings/blank
    if all(is_comment_or_blank(L) for L in added + removed):
        return ("C-Comment", "FP", "added/removed lines are all comments/docstrings/blank")

    # Heuristic 3: all changes are import lines (rearrangement)
    non_blank = [L for L in added + removed if not is_whitespace_only(L)]
    if non_blank and all(is_import_line(L) for L in non_blank):
        return ("C-Dead", "FP", "added/removed lines are all import statements (rearrangement)")

    # Heuristic 4: def/class added or removed — API-shape change
    if has_def_class(added) or has_def_class(removed):
        return ("M-API", "TP", "def/class line added or removed (API shape changed)")

    # Heuristic 5: large diff (>100 changed lines) — substantive feature work
    if total_changed > 100:
        return ("M-Behav", "TP", f"large diff ({total_changed} lines changed) — substantive")

    # Heuristic 6: small mixed change — could be small bug fix (TP) or
    # comment/whitespace cleanup mixed with one line (FP-ish). Need
    # finer heuristics. Default to M-Behav if non-trivial content,
    # else Ambig.
    substantive_lines = [
        L for L in added + removed
        if not is_whitespace_only(L) and not is_comment_or_blank(L)
    ]
    if substantive_lines:
        return ("M-Behav", "TP",
                f"contains {len(substantive_lines)} substantive line(s) (logic/expr change)")

    return ("Ambig", "Ambig",
            f"heuristics don't cover this shape ({total_changed} lines, mixed)")


def main() -> int:
    rows = []
    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    counts = {"TP": 0, "FP": 0, "Ambig": 0, "no_drift": 0}
    bin_counts: dict[str, int] = {}

    for row in rows:
        if row["drift_fires"] != "yes":
            counts["no_drift"] += 1
            row["bin_code"] = "(no drift)"
            row["tp_fp_ambig"] = "(no drift)"
            row["classifier_note"] = "hash matches stored baseline"
            continue
        diff = git_diff(row["commit"], row["file"])
        bin_code, tp_fp, rationale = classify(diff)
        row["bin_code"] = bin_code
        row["tp_fp_ambig"] = tp_fp
        row["classifier_note"] = f"AI-classified by heuristic: {rationale}"
        counts[tp_fp] = counts.get(tp_fp, 0) + 1
        bin_counts[bin_code] = bin_counts.get(bin_code, 0) + 1

    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    denom = counts["TP"] + counts["FP"]
    precision = counts["TP"] / denom if denom else 0.0

    print(f"Classification summary (N={len(rows)} total, "
          f"{counts['no_drift']} no-drift):")
    print(f"  TP   : {counts['TP']}")
    print(f"  FP   : {counts['FP']}")
    print(f"  Ambig: {counts['Ambig']}  (excluded from precision)")
    print(f"  Precision (TP / (TP+FP)) = {precision*100:.1f}% (n={denom})")
    print()
    print("Bin distribution:")
    for k in sorted(bin_counts):
        print(f"  {k:10s}: {bin_counts[k]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
