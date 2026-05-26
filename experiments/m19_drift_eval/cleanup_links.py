#!/usr/bin/env python3
"""
Clean up loom-self's auto-linked-impl set.

The M19v2 enrichment auto-linked 20 src/loom/ files via embedding
similarity. Inspecting the resulting links revealed that ~67% of
satisfies edges point at FINDING-kind REQs (research observations
captured during this session that happened to share vocabulary with
the technical code).

Findings should not be link targets for SOURCE CODE implementations.
Findings can legitimately be linked from EVIDENCE files (results
JSON, findings markdown) via link_type=evidences — but the M19v2
enrichment used implementation-style links for everything.

This script:
1. Walks all Implementation rows
2. For each `satisfies` edge whose linked REQ is kind=finding AND
   whose linked file is `src/loom/*`, REMOVE that edge.
3. If an Implementation row's satisfies list becomes empty after
   removal, delete the entire row.
4. Preserves pre-existing legitimate finding-links on evidence
   files (experiments/bakeoff/FINDINGS-*.md, *_results.json).

Output: dry-run report first; pass --apply to commit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

from loom.embedding import get_embedding  # noqa: E402
from loom.store import LoomStore  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="commit the changes; default is dry-run")
    args = ap.parse_args()

    s = LoomStore("loom")
    all_impls = list(s.list_implementations())
    all_reqs = {r.id: r for r in s.list_requirements()}

    # Build the plan: per impl, what gets kept vs removed.
    to_delete: list[str] = []  # impl_ids fully removed
    to_update: list[tuple[str, list[dict]]] = []  # (impl_id, new satisfies)

    for imp in all_impls:
        if not imp.file or not imp.file.startswith("src/loom/"):
            continue  # only touching src/loom/ links
        kept = []
        for s_ref in imp.satisfies:
            rid = s_ref.get("req_id")
            req = all_reqs.get(rid)
            if req and getattr(req, "kind", "requirement") == "finding":
                continue  # drop finding-link from source file
            kept.append(s_ref)
        if not kept:
            to_delete.append(imp.id)
        elif len(kept) != len(imp.satisfies):
            to_update.append((imp.id, kept))

    print(f"Cleanup plan ({'APPLY' if args.apply else 'DRY-RUN'}):")
    print(f"  impl rows to DELETE (all satisfies were finding-links): {len(to_delete)}")
    print(f"  impl rows to UPDATE (trim finding-links, keep req-links): {len(to_update)}")
    print()
    if to_delete:
        print("DELETE:")
        for iid in to_delete:
            imp = next(i for i in all_impls if i.id == iid)
            print(f"  {imp.file}  (was: {','.join(s['req_id'] for s in imp.satisfies)})")
    if to_update:
        print()
        print("UPDATE:")
        for iid, kept in to_update:
            imp = next(i for i in all_impls if i.id == iid)
            before = [s["req_id"] for s in imp.satisfies]
            after = [s["req_id"] for s in kept]
            removed = sorted(set(before) - set(after))
            print(f"  {imp.file}:")
            print(f"    kept:    {','.join(after)}")
            print(f"    removed: {','.join(removed)}")

    if not args.apply:
        print()
        print("Dry-run only. Pass --apply to commit.")
        return 0

    # Apply
    for iid in to_delete:
        s.delete_implementation(iid)
    for iid, kept in to_update:
        # Re-fetch the impl and update its satisfies. The store API
        # doesn't have an update-satisfies-only method, so use
        # add_implementation with the existing id (it should upsert
        # by id) OR delete+re-add.
        imp = next(i for i in all_impls if i.id == iid)
        s.delete_implementation(iid)
        imp.satisfies = kept
        # Re-embed since add_implementation requires it. The embedding
        # function applies its M19v2 4000-char truncation internally,
        # so this works for any file size.
        vec = get_embedding(imp.content or "")
        s.add_implementation(imp, vec)

    new_total = len(list(s.list_implementations()))
    print()
    print(f"Done. Linked impls: {new_total} (was {len(all_impls)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
