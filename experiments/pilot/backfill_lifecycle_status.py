"""
M15.5 — One-off migration to backfill lifecycle status on existing
kind=requirement reqs.

Applies the M15.2 auto-advance rules retroactively:

  * If a pending/rationale_needed req has at least one linked impl →
    bump to ``in_progress`` (trigger: backfill).
  * If a req also has a TestSpec with ``last_verified`` set → bump to
    ``implemented`` (fast-forwards through in_progress as needed).
  * Drift-free-for-N-days promotion to ``verified`` is NOT applied
    here — that requires running ``loom verify-stable --apply`` after
    backfill so the user can review the candidate list first.

Only touches ``kind=requirement``. Other kinds keep their existing
status (per M15 D2).

Dry-run by default. Add ``--apply`` to commit.

Run::

    python experiments/pilot/backfill_lifecycle_status.py --project loom
    python experiments/pilot/backfill_lifecycle_status.py --project loom --apply
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
from loom.testspec import TestSpecStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="loom")
    ap.add_argument("--apply", action="store_true",
                    help="Commit the backfill. Default is dry-run.")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    store = LoomStore(project=args.project)
    spec_store = TestSpecStore(store.data_dir)

    candidates: list[tuple[str, str, str, str]] = []
    # (req_id, current_status, target_status, reason)

    for req in store.list_requirements(include_superseded=False):
        if req.kind != "requirement":
            continue
        if req.status not in ("pending", "rationale_needed"):
            continue
        impls = store.get_implementations_for_requirement(req.id)
        non_evidence = [
            i for i in impls
            if not any(s.get("link_type") == "evidences"
                       for s in (i.satisfies or []))
        ]
        if not non_evidence:
            continue

        spec = spec_store.get_spec(req.id)
        if spec is not None and getattr(spec, "last_verified", None):
            target = "implemented"
            reason = (
                "backfill: M15.5 — test spec verified at "
                f"{spec.last_verified}"
            )
        else:
            target = "in_progress"
            reason = (
                f"backfill: M15.5 — linked to "
                f"{len(non_evidence)} impl(s)"
            )
        candidates.append((req.id, req.status, target, reason))

    print(f"Scanning project={args.project}: "
          f"{len(store.list_requirements(include_superseded=False))} "
          f"active requirement(s) total.")
    print()

    if not candidates:
        print("✓ No backfill needed — every linked pending/rationale_needed "
              "kind=requirement already has its lifecycle advanced.")
        return 0

    print(f"Backfill candidates ({len(candidates)}):")
    print()
    for req_id, current, target, reason in candidates:
        print(f"  {req_id}: {current} → {target}")
        print(f"    {reason}")
    print()

    if not args.apply:
        print("Dry-run — no changes written. Add --apply to commit.")
        return 0

    print("Applying backfill...")
    print()
    applied = 0
    failed: list[tuple[str, str]] = []
    for req_id, current, target, reason in candidates:
        try:
            result = services.set_status(
                store, req_id, target,
                reason=reason, _trigger="backfill",
            )
            path = result.get("path") or []
            applied += 1
            print(f"  ✓ {req_id}: {current} → {target} "
                  f"(traversed {len(path)} hop(s))")
        except Exception as e:
            failed.append((req_id, str(e)))
            print(f"  ✗ {req_id}: FAILED — {e}")

    print()
    print(f"Backfilled: {applied}/{len(candidates)}")
    if failed:
        print(f"Failed: {len(failed)}")
        for rid, err in failed:
            print(f"  {rid}: {err}")
        return 1

    # Quick acceptance check: what fraction of active kind=requirement
    # is still pending?
    active = [
        r for r in store.list_requirements(include_superseded=False)
        if r.kind == "requirement" and r.status != "archived"
    ]
    still_pending = [r for r in active if r.status == "pending"]
    pct = len(still_pending) / len(active) * 100 if active else 0
    print()
    print(f"Post-backfill: {len(still_pending)}/{len(active)} "
          f"active kind=requirement still pending ({pct:.1f}%).")
    if pct <= 30:
        print("✓ Within M15 acceptance threshold (≤30% pending).")
    else:
        print(f"⚠ Exceeds M15 threshold ({pct:.1f}% > 30%). Some "
              "pending reqs lack impl links — consider `loom triage` "
              "or `loom archive` to clean up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
