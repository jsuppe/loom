#!/usr/bin/env python3
"""
M19v3 harness — req-relevance precision eval.

Implements the design in M19V3_PREREGISTRATION.md. Adapts the
M19v1 harness shape to read its baseline from tight_links.lock
(hand-curated) rather than the live loom store (which has loose
auto-links from M19v2).

For each (file, req) pair in tight_links.lock:
1. Compute current SHA-256 of the file at HEAD (the baseline)
2. Walk `git log --max-count=10 -- <file>`
3. For each historical commit C: read the file at C, hash-compare
4. Emit one CSV row per (file, version) with linked req's value
   embedded so the classifier has the context it needs

Output: m19v3_classifications.csv with rows ready for AI-classify +
user spot-check.
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

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

LOCK_PATH = _HERE / "tight_links.lock"
CSV_PATH = _HERE / "m19v3_classifications.csv"
MAX_VERSIONS_PER_FILE = 10  # one more than v1/v2 to compensate for fewer files
PROJECT = "loom"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=_REPO,
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


def _diff_summary(commit: str, path: str) -> dict:
    """Stat + first-150-lines preview of the diff from commit's PARENT
    to commit. Used as classifier context."""
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
        "preview": "\n".join(body.splitlines()[:150]),
    }


def cmd_eval(args) -> int:
    if not LOCK_PATH.exists():
        print(f"ERROR: {LOCK_PATH} missing. Lock the link set first.")
        return 1
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    # Resolve req values from the loom store so the classifier sees
    # what each link is "about" without re-querying.
    store = LoomStore(PROJECT)
    req_values: dict[str, str] = {}
    for r in store.list_requirements():
        req_values[r.id] = r.value or ""

    head = git("rev-parse", "HEAD").strip()
    print(f"M19v3 eval at git HEAD {head[:12]}")
    print(f"Lock from {lock['locked_at']} (HEAD was {lock['git_head_at_curation']})")
    print(f"{len(lock['links'])} tight (file, req) pairs locked")
    print()

    rows = []
    excluded_count = 0
    excluded_reasons: dict[str, int] = {}

    for link in lock["links"]:
        path = link["file"]
        rid = link["req_id"]
        confidence = link["confidence"]
        link_type = link.get("link_type", "implementation")
        link_rationale = link["rationale"]
        req_value = req_values.get(rid, "(req not in store)")

        # Compute baseline hash from file at HEAD.
        head_path = _REPO / path
        if not head_path.exists():
            excluded_count += 1
            excluded_reasons["file_missing_at_head"] = (
                excluded_reasons.get("file_missing_at_head", 0) + 1
            )
            print(f"  [skip] {path} (missing at HEAD)")
            continue
        try:
            baseline_text = head_path.read_text(encoding="utf-8", errors="replace")
            baseline_hash = sha256_text(baseline_text)
        except OSError as e:
            excluded_count += 1
            excluded_reasons["read_failed"] = excluded_reasons.get("read_failed", 0) + 1
            print(f"  [skip] {path}: {e}")
            continue

        print(f"--- {path} ({confidence}, {link_type}) -> {rid} ---")

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
            except RuntimeError:
                excluded_count += 1
                excluded_reasons["git_show_failed"] = (
                    excluded_reasons.get("git_show_failed", 0) + 1
                )
                continue

            historical_hash = sha256_text(content_at_commit)
            drift_fires = historical_hash != baseline_hash

            diff = _diff_summary(commit_hash, path)

            row = {
                "file": path,
                "req_id": rid,
                "req_value": req_value,
                "link_confidence": confidence,
                "link_type": link_type,
                "link_rationale": link_rationale,
                "commit": commit_hash[:12],
                "commit_date": commit_date,
                "commit_subject": subject,
                "baseline_hash": baseline_hash[:12],
                "historical_hash": historical_hash[:12],
                "drift_fires": "yes" if drift_fires else "no",
                "diff_stat": diff["stat"],
                "diff_preview": diff["preview"],
                # Classification slots — M19v3.4 fills these
                "ai_bin": "",
                "ai_tp_fp": "",
                "ai_note": "",
                "user_bin": "",
                "user_tp_fp": "",
                "user_note": "",
                "final_bin": "",
                "final_tp_fp": "",
            }
            rows.append(row)
            mark = "DRIFT" if drift_fires else "match"
            print(f"  [{mark:5s}] {commit_hash[:12]} {commit_date[:10]} {subject[:50]}")

    # Emit CSV
    if not rows:
        print("ERROR: no rows generated")
        return 1
    fieldnames = list(rows[0].keys())
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row_safe = dict(row)
            # CSV doesn't handle newlines well — collapse with marker
            row_safe["diff_preview"] = (
                row_safe["diff_preview"].replace("\n", " ⏎ ")[:2000]
            )
            row_safe["req_value"] = row_safe["req_value"].replace("\n", " ")
            writer.writerow(row_safe)

    drift_count = sum(1 for r in rows if r["drift_fires"] == "yes")
    match_count = sum(1 for r in rows if r["drift_fires"] == "no")

    print()
    print(f"Wrote {len(rows)} rows to {CSV_PATH.name}")
    print(f"  drift_fires=yes : {drift_count}")
    print(f"  drift_fires=no  : {match_count}")
    print(f"  excluded        : {excluded_count}  reasons={excluded_reasons}")
    print()
    print(f"Next: AI-classify (M19v3.4) then user 20% spot-check for kappa")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_eval = sub.add_parser("eval")
    p_eval.set_defaults(fn=cmd_eval)
    args = ap.parse_args()
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
