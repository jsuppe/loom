#!/usr/bin/env python3
"""
M19v2 — Enrich loom-self's linked-impl count for drift-detection eval.

The M19v1 finding was: loom-self only has 10 linked impls (mostly
stale experiment-driver scripts), so the drift-detection sample
structurally cannot produce FP cases. Pre-reg's predicted precision
of 50-70% landed at 100% because no cosmetic commits made it into
the sample.

This script:
1. Walks src/loom/*.py
2. For each file, calls services.detect_requirements(n=3) to find
   semantically-related requirements via embedding similarity
3. Links the file to matches whose distance is at most a locked
   threshold (cosine sim ≥ 0.55 — conservative; the default
   min-score for `loom related` is 0.66)
4. Prints a transparent report of what got linked and what the
   match distances were
5. Skips files that are already linked (preserves M19v1 baseline)

Output: enrichment_log.txt with one line per (file, req, distance, action).

After running this, re-run m19_harness.py {freeze, eval} to capture
the new baseline and produce a richer sample for hand-classification.

LOCKED PARAMETERS (so reproducible):
* Target glob: src/loom/*.py (no recursion into prompts/, templates/)
* Per-file: top 3 candidate reqs by similarity
* Distance threshold: ≤ 0.45 (i.e. cosine similarity ≥ 0.55)
* Files already linked: skipped (preserves M19v1 comparison if
  user wants to diff)
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO / "src"))

from loom import services  # noqa: E402
from loom.store import LoomStore  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT = "loom"
TARGET_DIR = _REPO / "src" / "loom"
DISTANCE_THRESHOLD = 0.45  # cosine similarity floor 0.55
TOP_N_PER_FILE = 3
LOG_PATH = _HERE / "enrichment_log.txt"


def main() -> int:
    store = LoomStore(PROJECT)

    # Snapshot already-linked files so we skip them.
    already_linked: set[str] = set()
    for imp in store.list_implementations():
        if imp.file:
            already_linked.add(imp.file)

    print(f"Already linked: {len(already_linked)} impls")
    print(f"Target: {TARGET_DIR.relative_to(_REPO)}/*.py "
          f"(distance ≤ {DISTANCE_THRESHOLD})")
    print()

    targets = sorted(
        p for p in TARGET_DIR.glob("*.py")
        if p.is_file() and p.name != "__init__.py"
    )

    log_lines: list[str] = [f"# M19v2 enrichment run\n"]
    log_lines.append(f"# distance_threshold={DISTANCE_THRESHOLD}\n")
    log_lines.append(f"# top_n={TOP_N_PER_FILE}\n\n")

    linked_count = 0
    skipped_count = 0
    for path in targets:
        rel = str(path.relative_to(_REPO)).replace("\\", "/")
        if rel in already_linked:
            print(f"  [skip] {rel} (already linked)")
            log_lines.append(f"SKIP {rel} (already linked)\n")
            skipped_count += 1
            continue

        try:
            matches = services.detect_requirements(
                store, rel, n=TOP_N_PER_FILE,
            )
        except (LookupError, FileNotFoundError) as e:
            print(f"  [err] {rel}: {e}")
            log_lines.append(f"ERR  {rel}: {e}\n")
            continue

        # Filter by distance (lower = better match).
        good = [
            m for m in matches
            if m.get("distance") is not None and m["distance"] <= DISTANCE_THRESHOLD
        ]
        if not good:
            best = matches[0] if matches else None
            best_str = (f"best d={best['distance']:.3f}"
                        if best else "no candidates")
            print(f"  [low ] {rel} ({best_str})")
            log_lines.append(f"LOW  {rel} {best_str}\n")
            continue

        req_ids = [m["req_id"] for m in good]
        try:
            result = services.link(
                store, file_path=rel, req_ids=req_ids,
            )
        except Exception as e:
            print(f"  [err ] {rel}: link failed: {e}")
            log_lines.append(f"ERR  {rel}: link failed: {e}\n")
            continue

        print(f"  [link] {rel} -> {','.join(req_ids)}")
        for m in good:
            log_lines.append(
                f"LINK {rel}  {m['req_id']}  d={m['distance']:.3f}  "
                f"\"{m['value'][:60]}\"\n"
            )
        linked_count += 1

    print()
    print(f"Summary: linked {linked_count}, skipped {skipped_count}, "
          f"target total {len(targets)}")

    LOG_PATH.write_text("".join(log_lines), encoding="utf-8")
    print(f"Log: {LOG_PATH.relative_to(_REPO)}")

    new_total = len(list(store.list_implementations()))
    print(f"\nLinked impls in store: {new_total} (was {len(already_linked)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
