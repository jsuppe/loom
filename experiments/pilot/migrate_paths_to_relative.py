"""
M17.1 — One-off migration to convert absolute Implementation paths
to the new POSIX-relative convention.

Walks every impl in a project's store. For each:
  1. Computes the canonical stored form via ``normalize_file_path``.
  2. If the form differs from what's stored, generates the new
     impl_id, writes a new impl row, and deletes the old one.
  3. Re-uses the existing embedding (avoids re-running Ollama).

Idempotent: a clean store (all paths already in canonical form)
produces zero changes.

Default mode is ``--dry-run``: prints what WOULD change and exits
without touching the store. Add ``--apply`` to commit. Always prints
a summary at the end.

Run::

    python experiments/pilot/migrate_paths_to_relative.py --project loom
    python experiments/pilot/migrate_paths_to_relative.py --project loom --apply

Per the M14 dogfooding pattern, this is a one-off script (not a CLI
command). After running once per project, delete or archive.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running out of the repo without an install.
_HERE = Path(__file__).resolve()
_REPO = _HERE.parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

from loom.paths import normalize_file_path  # noqa: E402
from loom.store import (  # noqa: E402
    Implementation, LoomStore, generate_impl_id,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="loom")
    ap.add_argument("--apply", action="store_true",
                    help="Commit the migration. Default is dry-run.")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    store = LoomStore(project=args.project)

    impls = store.list_implementations()
    print(f"Scanning {len(impls)} implementation row(s) in project={args.project}")
    print()

    changes: list[tuple[Implementation, str]] = []
    for impl in impls:
        # normalize_file_path resolves paths against cwd by default,
        # which here is the loom repo (project root). Pre-existing impls
        # stored absolute Windows paths — those resolve cleanly and
        # become "src/foo.py" form. Impls already in canonical form
        # also no-op through the same code path.
        new_path = normalize_file_path(impl.file)
        if new_path != impl.file:
            changes.append((impl, new_path))

    if not changes:
        print("✓ No changes needed — all impl paths are already canonical.")
        return 0

    print(f"Found {len(changes)} impl(s) with non-canonical paths:")
    print()
    for impl, new_path in changes:
        print(f"  {impl.id}:")
        print(f"    from: {impl.file}")
        print(f"      to: {new_path}")
        print(f"    satisfies: {[s.get('req_id') for s in (impl.satisfies or [])]}")
    print()

    if not args.apply:
        print("Dry-run — no changes written. Add --apply to commit.")
        return 0

    # Commit changes: write the new impl row, then delete the old.
    # We re-use the embedding (cheap) and preserve all metadata. The
    # new impl_id is derived from (new_path, lines) so it's stable
    # across machines.
    print("Applying migration...")
    print()
    migrated = 0
    failed: list[tuple[str, str]] = []
    for impl, new_path in changes:
        try:
            # Pull the existing embedding so we don't recompute.
            existing = store.implementations.get(
                ids=[impl.id], include=["embeddings"],
            )
            if not existing.get("embeddings"):
                failed.append((impl.id, "no embedding found in store"))
                continue
            embedding = existing["embeddings"][0]

            new_impl = Implementation(
                id=generate_impl_id(new_path, impl.lines),
                file=new_path,
                lines=impl.lines,
                content=impl.content,
                content_hash=impl.content_hash,
                timestamp=impl.timestamp,
                satisfies=impl.satisfies,
                satisfies_specs=impl.satisfies_specs,
                satisfies_patterns=impl.satisfies_patterns,
                symbol_ticket=impl.symbol_ticket,
                symbol_signature_hash=impl.symbol_signature_hash,
            )
            # Write new, then delete old. Order matters — if the new
            # write fails halfway, we still have the old row.
            store.add_implementation(new_impl, embedding)
            if new_impl.id != impl.id:
                store.delete_implementation(impl.id)
            migrated += 1
            print(f"  ✓ {impl.id[:8]}... → {new_impl.id[:8]}... ({new_path})")
        except Exception as e:
            failed.append((impl.id, str(e)))
            print(f"  ✗ {impl.id[:8]}... FAILED: {e}")

    print()
    print(f"Migrated: {migrated}/{len(changes)}")
    if failed:
        print(f"Failed: {len(failed)}")
        for impl_id, err in failed:
            print(f"  {impl_id}: {err}")
        return 1

    # Sanity check: re-scan and confirm 0 non-canonical paths remain.
    remaining = sum(
        1 for impl in store.list_implementations()
        if normalize_file_path(impl.file) != impl.file
    )
    if remaining > 0:
        print(f"⚠️  {remaining} impl(s) still non-canonical after migration "
              "(unexpected). Re-run --dry-run to inspect.")
        return 1

    print()
    print("✓ All impl paths now canonical.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
