"""
M17.2 — One-off migration to auto-generate slugs for every existing
requirement that doesn't have one.

Walks the store; for each req with `slug=None`, generates a
kebab-case slug via ``services.generate_slug`` + uniqueness check;
writes back via the store's underlying update path.

Dry-run by default. Add ``--apply`` to commit.

Run::

    python experiments/pilot/backfill_slugs.py --project loom
    python experiments/pilot/backfill_slugs.py --project loom --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

from loom import services  # noqa: E402
from loom.store import LoomStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="loom")
    ap.add_argument("--apply", action="store_true",
                    help="Commit the backfill. Default is dry-run.")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    store = LoomStore(project=args.project)

    reqs = store.list_requirements(include_superseded=True)
    needs_slug = [r for r in reqs if not getattr(r, "slug", None)]

    print(f"Project={args.project}: {len(reqs)} requirements total, "
          f"{len(needs_slug)} without slugs.\n")

    if not needs_slug:
        print("✓ Every requirement already has a slug. Nothing to backfill.")
        return 0

    # Compute slugs with running uniqueness (track ones we'd assign
    # in this pass so two reqs in the same run don't collide).
    in_use: set[str] = {
        s for s in (getattr(r, "slug", None) for r in reqs) if s
    }
    plan: list[tuple[str, str, str]] = []  # (req_id, value_preview, slug)
    for r in needs_slug:
        base = services.generate_slug(r.value)
        candidate = base
        n = 2
        while candidate in in_use:
            candidate = f"{base}-{n}"
            n += 1
        in_use.add(candidate)
        plan.append((r.id, r.value[:80], candidate))

    print(f"Backfill plan ({len(plan)} entries):\n")
    for rid, value, slug in plan:
        print(f"  {rid}  ->  {slug}")
        print(f"             {value}")
    print()

    if not args.apply:
        print("Dry-run — no changes written. Add --apply to commit.")
        return 0

    print("Applying...")
    applied = 0
    failed: list[tuple[str, str]] = []
    for rid, _, slug in plan:
        try:
            store.update_requirement(rid, {"slug": slug})
            applied += 1
        except Exception as e:
            failed.append((rid, str(e)))

    print(f"\nBackfilled: {applied}/{len(plan)}")
    if failed:
        print(f"Failed: {len(failed)}")
        for rid, err in failed:
            print(f"  {rid}: {err}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
