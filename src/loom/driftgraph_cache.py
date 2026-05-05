"""
Driftgraph state cache (M13.5d) — local mirror fed by webhook events
from the Driftgraph substrate.

The cache is populated from a Driftgraph → Loom webhook the substrate
will fire on every state change (claim_created / claim_invalidated /
supersedes / foundation_drift). The receiver lives in
``hooks/loom_drift_webhook.py``; this module is the read side
+ replay logic that turns the event log into a query-time state
lookup.

Cache file format: append-only JSONL at
``<data_dir>/.driftgraph-cache.jsonl``. Each line is the verbatim
webhook payload as the substrate sent it, plus a ``received_at``
timestamp. We never mutate prior records — the freshness model is
"latest event wins" computed at read time. That keeps the cache
crash-safe and lets `loom warrant cache-replay` rebuild any
derived view without state migration.

State semantics per claim_id:
  invalidated:      claim was explicitly superseded by ANY source
                    (chat utterance, Loom retraction, etc.)
  foundation_drift: at least one BECAUSE_OF ancestor was invalidated
                    AFTER this claim was last reported active
  drifted_ancestors: list of {ancestor_claim_id, detected_at,
                              event_kind} for the most recent drift
                              events affecting this claim

Failure modes are silent. The cache empty + Driftgraph reachable =
fall back to in-process Cypher (Path B). Cache empty + Driftgraph
unreachable = no signal. Either way the agent gets a clean
PreToolUse experience.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


CACHE_FILENAME = ".driftgraph-cache.jsonl"


def cache_path(data_dir: Path) -> Path:
    """Per-project cache file location."""
    return Path(data_dir) / CACHE_FILENAME


def record_event(data_dir: Path, payload: dict) -> None:
    """Append a webhook event to the cache. ``payload`` is the
    verbatim JSON the substrate sent (post-HMAC-verification — that
    happens in hooks/loom_drift_webhook.py before this is called).

    Best-effort; logging failures must not break the receiver's
    request handler. If the disk is full or the data_dir is
    unwritable, the cache simply doesn't grow, and lookups return
    "no signal" (which is the correct degradation)."""
    rec = dict(payload)  # shallow copy so we don't mutate caller's dict
    rec.setdefault("received_at", datetime.now(timezone.utc).isoformat())
    try:
        path = cache_path(data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _read_events(data_dir: Path) -> list[dict]:
    """Return the full event list from the cache, oldest first.
    Returns ``[]`` on missing or corrupt cache (no signal)."""
    path = cache_path(data_dir)
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def has_cache(data_dir: Path) -> bool:
    """True iff the cache file exists AND has at least one record.
    Used by ``services.context()`` to decide whether to read from
    the cache or fall back to the in-process Cypher path."""
    path = cache_path(data_dir)
    if not path.exists():
        return False
    try:
        with path.open("rb") as f:
            return bool(f.read(1))
    except OSError:
        return False


def compute_claim_state(data_dir: Path, claim_id: str) -> dict[str, Any]:
    """Replay the event log to produce the current state of a single
    claim. Returns:

        {
          "claim_id": str,
          "invalidated": bool,           # has been explicitly superseded
          "invalidated_at": str | None,  # event timestamp
          "foundation_drifted": bool,    # any BECAUSE_OF ancestor invalidated
          "drifted_ancestors": [         # one entry per drift event
              {"ancestor_claim_id", "detected_at", "event_kind"}
          ],
        }
    """
    state: dict[str, Any] = {
        "claim_id": claim_id,
        "invalidated": False,
        "invalidated_at": None,
        "foundation_drifted": False,
        "drifted_ancestors": [],
    }
    events = _read_events(data_dir)
    if not events:
        return state

    # Index drifted-ancestor entries by ancestor_claim_id so we can
    # de-dupe (foundation_drift events for the same ancestor that fire
    # repeatedly across detections).
    seen_ancestors: dict[str, dict] = {}

    for ev in events:
        kind = ev.get("event")

        # claim_invalidated: explicit supersede of a specific claim_id
        # (Loom retraction, chat utterance, ingest replacement, …)
        if kind in ("claim_invalidated", "supersedes"):
            target = (
                ev.get("retracted_claim_id")
                or ev.get("invalidated_claim_id")
                or ev.get("claim_id")
            )
            if target == claim_id:
                state["invalidated"] = True
                state["invalidated_at"] = (
                    ev.get("invalidated_at")
                    or ev.get("detected_at")
                    or ev.get("received_at")
                )

        # foundation_drift: a BECAUSE_OF ancestor of one or more
        # dependents was just invalidated. We're claim_id; check if
        # we're in the dependents list.
        elif kind == "foundation_drift":
            for dep in ev.get("dependents") or []:
                if dep.get("claim_id") != claim_id:
                    continue
                ancestor_id = ev.get("retracted_claim_id") or ev.get("ancestor_claim_id")
                if not ancestor_id:
                    continue
                state["foundation_drifted"] = True
                # Latest fire wins per ancestor (overwrite if seen before).
                seen_ancestors[ancestor_id] = {
                    "ancestor_claim_id": ancestor_id,
                    "ancestor_subject": ev.get("retracted_subject"),
                    "ancestor_object": ev.get("retracted_object"),
                    "detected_at": (
                        ev.get("detected_at") or ev.get("received_at")
                    ),
                    "event_kind": kind,
                }

    # Stable order: by detected_at ascending (oldest drift first).
    state["drifted_ancestors"] = sorted(
        seen_ancestors.values(),
        key=lambda a: a.get("detected_at") or "",
    )
    return state


def lookup_drifted_for_req(
    data_dir: Path, req_id: str,
) -> dict[str, Any]:
    """Convenience matching `driftgraph_query.find_drifted_ancestors_
    for_req`'s shape — looks up active claim_ids from the warrants
    log, computes per-claim state from the cache, returns the same
    {drifted, claim_ids, drifted_ancestors, available} dict so
    `services.context()` can swap the implementation without changing
    its consumer."""
    from . import warrants

    out = {
        "drifted": False, "claim_ids": [], "drifted_ancestors": [],
        "available": False,
    }
    if not has_cache(data_dir):
        # No cache yet → fall through to the in-process path. Caller
        # treats available=False as "use the other channel."
        return out
    out["available"] = True

    active = warrants.lookup_active_claims_for_req(data_dir, req_id)
    out["claim_ids"] = active
    if not active:
        return out

    for claim_id in active:
        state = compute_claim_state(data_dir, claim_id)
        if state["foundation_drifted"]:
            for anc in state["drifted_ancestors"]:
                out["drifted_ancestors"].append({
                    "claim_id": claim_id,
                    "ancestor": {
                        "ancestor_claim_id": anc["ancestor_claim_id"],
                        "ancestor_subject": anc.get("ancestor_subject"),
                        "ancestor_object": anc.get("ancestor_object"),
                        "invalidated_at": anc.get("detected_at"),
                        "hops": 1,  # webhook payload doesn't carry hops
                    },
                })
    out["drifted"] = bool(out["drifted_ancestors"])
    return out
