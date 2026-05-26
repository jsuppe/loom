#!/usr/bin/env python3
"""
M19 — Real-world drift detection precision eval harness.

Implements the design in M19_PREREGISTRATION.md.

Two subcommands:
    freeze     — snapshot the current loom store's 10 linked-file set
                 to linked_files.lock (run once at pre-reg lock time).
    eval       — walk git history per linked file, sample up to 8
                 historical versions, compute hash-compare against the
                 frozen baseline, emit one row per (file, version) pair
                 to m19_classifications.csv for hand-classification.

Output rows include enough context for a human to classify each diff
as TP (semantically meaningful) or FP (cosmetic) per the rubric.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent

sys.path.insert(0, str(_REPO / "src"))

from loom.store import LoomStore  # noqa: E402

LOCK_PATH = _HERE / "linked_files.lock"
CSV_PATH = _HERE / "m19_classifications.csv"
MAX_VERSIONS_PER_FILE = 8
PROJECT = "loom"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd or _REPO,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout


def file_existed_at(commit: str, path: str) -> bool:
    proc = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}:{path}"],
        cwd=_REPO, capture_output=True,
        shell=(sys.platform == "win32"),
    )
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# freeze — snapshot linked-file set + their stored content_hash
# ---------------------------------------------------------------------------


def cmd_freeze(_args) -> int:
    store = LoomStore(PROJECT)
    impls = list(store.list_implementations())

    lock = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "project": PROJECT,
        "git_head": git("rev-parse", "HEAD").strip(),
        "implementations": [],
    }
    for imp in impls:
        lock["implementations"].append({
            "impl_id": imp.id,
            "file": imp.file,
            "lines": imp.lines,
            "content_hash": imp.content_hash,
            "timestamp": imp.timestamp,
            "satisfies": [
                {"req_id": s.get("req_id"), "req_version": s.get("req_version")}
                for s in (imp.satisfies or [])
            ],
        })

    LOCK_PATH.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    print(f"Froze {len(impls)} linked-file entries to {LOCK_PATH}")
    print(f"git HEAD = {lock['git_head'][:12]}")
    return 0


# ---------------------------------------------------------------------------
# eval — walk git history per linked file, emit one CSV row per pair
# ---------------------------------------------------------------------------


def _diff_summary(commit: str, path: str) -> dict:
    """Stat + first-100-lines preview of the diff from commit's PARENT
    to commit for path. Used to give the hand-classifier enough context
    to bin-code without opening a separate editor."""
    try:
        stat = git("diff", "--stat", f"{commit}~1", commit, "--", path).strip()
    except Exception:
        stat = "(no parent diff available)"
    try:
        body = git(
            "diff", "--unified=1", "--no-color",
            f"{commit}~1", commit, "--", path,
        )
    except Exception:
        body = ""
    return {
        "stat": stat,
        "preview": "\n".join(body.splitlines()[:120]),
    }


def cmd_eval(args) -> int:
    if not LOCK_PATH.exists():
        print(f"ERROR: {LOCK_PATH} missing. Run `freeze` first.")
        return 1
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    head = git("rev-parse", "HEAD").strip()
    print(f"Eval at git HEAD {head[:12]} against lock from {lock['frozen_at']}")
    print(f"Lock'd git HEAD = {lock['git_head'][:12]}\n")

    rows = []
    excluded_count = 0
    excluded_reasons: dict[str, int] = {}

    for entry in lock["implementations"]:
        path = entry["file"]
        stored_hash = entry["content_hash"]
        impl_id = entry["impl_id"]
        satisfies = ",".join(s["req_id"] for s in entry["satisfies"])

        print(f"--- {path} (impl={impl_id[:8]}, satisfies={satisfies}) ---")

        try:
            log_lines = git(
                "log", f"--max-count={MAX_VERSIONS_PER_FILE}",
                "--pretty=%H%x09%ci%x09%s", "--", path,
            ).splitlines()
        except RuntimeError as e:
            print(f"  ERROR: {e}")
            continue

        if not log_lines:
            print(f"  (no commit history found)")
            continue

        for line in log_lines:
            try:
                commit_hash, commit_date, subject = line.split("\t", 2)
            except ValueError:
                continue

            if not file_existed_at(commit_hash, path):
                excluded_count += 1
                excluded_reasons["no_file_at_commit"] = (
                    excluded_reasons.get("no_file_at_commit", 0) + 1
                )
                continue

            try:
                content_at_commit = git("show", f"{commit_hash}:{path}")
            except RuntimeError as e:
                excluded_count += 1
                excluded_reasons["git_show_failed"] = (
                    excluded_reasons.get("git_show_failed", 0) + 1
                )
                continue

            historical_hash = sha256_text(content_at_commit)
            drift_fires = historical_hash != stored_hash

            diff = _diff_summary(commit_hash, path)

            row = {
                "file": path,
                "impl_id": impl_id,
                "satisfies": satisfies,
                "commit": commit_hash[:12],
                "commit_date": commit_date,
                "commit_subject": subject,
                "stored_hash": stored_hash[:12],
                "historical_hash": historical_hash[:12],
                "drift_fires": "yes" if drift_fires else "no",
                "diff_stat": diff["stat"],
                "diff_preview": diff["preview"],
                # Hand-classification slot — empty for harness fill
                "bin_code": "",
                "tp_fp_ambig": "",
                "classifier_note": "",
            }
            rows.append(row)
            mark = "DRIFT" if drift_fires else "match"
            print(f"  [{mark:5s}] {commit_hash[:12]} {commit_date[:10]} {subject[:60]}")

    # Emit CSV
    fieldnames = list(rows[0].keys()) if rows else []
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                # CSV doesn't handle multi-line cells well; truncate preview
                row_safe = dict(row)
                row_safe["diff_preview"] = (
                    row_safe["diff_preview"].replace("\n", " ⏎ ")[:1200]
                )
                writer.writerow(row_safe)

    drift_count = sum(1 for r in rows if r["drift_fires"] == "yes")
    match_count = sum(1 for r in rows if r["drift_fires"] == "no")

    print(f"\nWrote {len(rows)} rows to {CSV_PATH}")
    print(f"  drift_fires=yes : {drift_count}")
    print(f"  drift_fires=no  : {match_count}")
    print(f"  excluded        : {excluded_count}  reasons={excluded_reasons}")
    print()
    print(f"Next: hand-classify each drift_fires=yes row in {CSV_PATH.name}")
    print(f"  Set bin_code (M-API / M-Behav / M-Intent / C-White / C-Rename / "
          f"C-Comment / C-Dead / Mixed / Ambig)")
    print(f"  Set tp_fp_ambig (TP / FP / Ambig)")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_freeze = sub.add_parser("freeze")
    p_freeze.set_defaults(fn=cmd_freeze)

    p_eval = sub.add_parser("eval")
    p_eval.set_defaults(fn=cmd_eval)

    args = ap.parse_args()
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
