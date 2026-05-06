"""
Driftgraph HTTP read API client (M13.5e — Phase 13.5 substrate
contract).

Three routes the substrate exposes alongside the existing
POST /warrants:

  GET  /claims/<claim_id>?project=<name>     [Bearer auth]
       → claim status row including foundation_drifted bool
  POST /claims/lookup                         [HMAC-over-body]
       body {project, claim_ids: [...]} (capped at 500)
       → {claim_id → status_row}
  GET  /projects/<name>/foundation-drift      [Bearer auth]
       ?limit=<n>
       → {project, drifted_claims: [{claim_id, broken_chain, ...}], count}

This client is the cold-start path: when the cache is empty (no
webhook events have fired yet) `services.context()` can fall back
to one of these calls instead of the in-process Cypher (Path B).
Once webhook events start arriving, the cache becomes the runtime
and these calls fade out of the hot path.

All public functions degrade to None / [] / no-signal on any
failure (substrate down, auth failure, network, parse). The
consumer treats absence of data as "no signal", same as the
cache-miss case.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional


DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_TIMEOUT = 5  # seconds — read calls are on the agent's hot path


def base_url() -> str:
    """The Driftgraph HTTP base. Override via
    ``$LOOM_DRIFTGRAPH_BASE_URL``; defaults to the same-machine bot
    Loom already pushes to (we strip the /warrants suffix Loom uses
    for outbound and treat the host:port as the base)."""
    return os.environ.get("LOOM_DRIFTGRAPH_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _bearer_get(path: str, *, secret: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[dict]:
    """GET with Bearer auth. Returns parsed JSON or None on any
    failure. Caller treats None as "no signal."""
    url = f"{base_url()}{path}"
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {secret}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, OSError, TimeoutError):
        return None


def _hmac_post(path: str, body_obj: dict, *, secret: str,
               timeout: int = DEFAULT_TIMEOUT) -> Optional[dict]:
    """POST with HMAC-over-body. Returns parsed JSON or None on
    any failure."""
    url = f"{base_url()}{path}"
    body = json.dumps(body_obj).encode("utf-8")
    sig = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256,
    ).hexdigest()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, OSError, TimeoutError):
        return None


# ---------------------------------------------------------------------------
# Public API — mirrors driftgraph_query/_cache shapes so callers can swap
# ---------------------------------------------------------------------------


def get_claim_status(project: str, claim_id: str,
                     *, secret: str | None = None) -> Optional[dict]:
    """GET /claims/<claim_id>?project=<name>. Returns the
    `_shape_claim_row` dict (per substrate's Phase 13.5 contract):
    {claim_id, kind, valid, invalidated_at, observed_at, confidence,
     validator_id, validator_score, subject, predicate, object,
     source_episode_id, source, supersedes_chain[],
     because_of_targets[], foundation_drifted: bool,
     n_invalidated_parents: int}. None on any failure.
    """
    from . import warrants
    secret = secret if secret is not None else warrants.load_secret()
    if not secret or not project or not claim_id:
        return None
    # urllib doesn't auto-quote; the substrate matches on the raw
    # path. Keep the input simple — claim_ids are alphanumeric
    # `clm_<hex>` so no quoting needed. Project is similarly plain.
    return _bearer_get(
        f"/claims/{claim_id}?project={project}", secret=secret,
    )


def bulk_claim_lookup(project: str, claim_ids: list[str],
                      *, secret: str | None = None) -> Optional[dict]:
    """POST /claims/lookup. Returns ``{claim_id → status_row}`` for
    every claim_id that exists in the project's database. Missing
    claim_ids simply don't appear in the result. None on any failure.

    The substrate caps the request at 500 claim_ids; this client
    does NOT split — callers with >500 IDs should batch
    themselves.
    """
    from . import warrants
    secret = secret if secret is not None else warrants.load_secret()
    if not secret or not project or not claim_ids:
        return None
    if len(claim_ids) > 500:
        # Don't silently truncate; the caller should know.
        raise ValueError(
            f"bulk_claim_lookup capped at 500 claim_ids per request "
            f"(received {len(claim_ids)}); batch on the caller side."
        )
    resp = _hmac_post(
        "/claims/lookup",
        {"project": project, "claim_ids": claim_ids},
        secret=secret,
    )
    if resp is None:
        return None
    # The substrate's actual Phase 13.5 response shape is
    # {project, claims: [{claim_id, ...}, ...], missing: [...]}.
    # Convert to the {claim_id → row} form callers want.
    if isinstance(resp.get("claims"), list):
        return {c["claim_id"]: c for c in resp["claims"]
                if isinstance(c, dict) and c.get("claim_id")}
    # Forward-compat: also accept flat-dict and {found: dict} shapes.
    if isinstance(resp.get("found"), dict):
        return resp["found"]
    return resp


def list_foundation_drifted(project: str, *, limit: int = 50,
                            secret: str | None = None) -> Optional[list[dict]]:
    """GET /projects/<project>/foundation-drift?limit=<n>. Returns a
    list of {claim_id, broken_chain, ...} dicts for every claim in
    the project currently flagged as foundation-drifted. Used for
    cold-start cache seeding. None on any failure.
    """
    from . import warrants
    secret = secret if secret is not None else warrants.load_secret()
    if not secret or not project:
        return None
    resp = _bearer_get(
        f"/projects/{project}/foundation-drift?limit={limit}",
        secret=secret,
    )
    if resp is None:
        return None
    if isinstance(resp.get("drifted_claims"), list):
        return resp["drifted_claims"]
    return None


def is_available() -> bool:
    """Probe the substrate's /health to confirm the read API is
    reachable. Cheap: no auth, single GET. Returns False on any
    transport failure."""
    url = f"{base_url()}/health"
    try:
        with urllib.request.urlopen(url, timeout=DEFAULT_TIMEOUT) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError,
            OSError, TimeoutError):
        return False


# ---------------------------------------------------------------------------
# Convenience wrapper matching driftgraph_query / driftgraph_cache shape
# ---------------------------------------------------------------------------


def find_drifted_ancestors_for_req(
    data_dir, req_id: str,
) -> dict:
    """Same shape as driftgraph_query.find_drifted_ancestors_for_req
    and driftgraph_cache.lookup_drifted_for_req — looks up the active
    claim_ids for ``req_id`` from the warrants log, then bulk-queries
    the substrate for their status, and returns:

        {drifted, claim_ids, drifted_ancestors, available}

    The ``available`` flag is True only when the substrate /health
    answered 200 — callers fall back to other channels when False.
    """
    from . import warrants
    out = {"drifted": False, "claim_ids": [],
           "drifted_ancestors": [], "available": False}
    if not is_available():
        return out
    out["available"] = True

    active = warrants.lookup_active_claims_for_req(data_dir, req_id)
    out["claim_ids"] = active
    if not active:
        return out

    latest = warrants.lookup_latest_push_for_req(data_dir, req_id)
    project = (latest or {}).get("project_tag") or ""
    if not project:
        return out

    status_by_id = bulk_claim_lookup(project, active) or {}

    # Two-pass: first collect every unique ancestor_id across all
    # foundation-drifted children, then ONE follow-up bulk-lookup
    # to fetch the ancestors' subject/object/invalidated_at. That's
    # 2 HTTP calls regardless of how many child claims we have,
    # vs the naïve N-call-per-ancestor approach.
    ancestor_ids: set[str] = set()
    for claim_id in active:
        info = status_by_id.get(claim_id)
        if not info or not info.get("foundation_drifted"):
            continue
        for anc_id in info.get("because_of_targets") or []:
            if anc_id:
                ancestor_ids.add(anc_id)
    ancestor_status = (
        bulk_claim_lookup(project, list(ancestor_ids))
        if ancestor_ids else {}
    ) or {}

    # Dedupe by ancestor_claim_id within this single-req call —
    # the same ancestor invalidates the req's grounding regardless
    # of how many of the req's child claims point at it. Without
    # this, 3 children sharing a parent produce 3 identical lines
    # in the agent's reminder. Track which child surfaced the
    # ancestor first so the consumer can still reach back into
    # the substrate per-claim if needed.
    seen_ancestors: set[str] = set()
    saw_deep_drift = False
    for claim_id in active:
        info = status_by_id.get(claim_id)
        if not info or not info.get("foundation_drifted"):
            continue
        bo_targets = info.get("because_of_targets") or []
        for anc_id in bo_targets:
            if not anc_id or anc_id in seen_ancestors:
                continue
            seen_ancestors.add(anc_id)
            anc = ancestor_status.get(anc_id) or {}
            out["drifted_ancestors"].append({
                "claim_id": claim_id,
                "ancestor": {
                    "ancestor_claim_id": anc_id,
                    "ancestor_subject": anc.get("subject"),
                    "ancestor_object": anc.get("object"),
                    "ancestor_predicate": anc.get("predicate"),
                    "invalidated_at": anc.get("invalidated_at"),
                    "hops": 1,
                },
            })
        # foundation_drifted=True but because_of_targets is empty
        # — substrate detected drift via a deeper hop than the
        # immediate parent. Emit one placeholder for the whole
        # req, not one per child.
        if not bo_targets and not saw_deep_drift:
            saw_deep_drift = True
            out["drifted_ancestors"].append({
                "claim_id": claim_id,
                "ancestor": {
                    "ancestor_claim_id": None,
                    "ancestor_subject": None,
                    "ancestor_object": None,
                    "invalidated_at": None,
                    "hops": None,
                    "_n_invalidated_parents": info.get("n_invalidated_parents"),
                },
            })
    out["drifted"] = bool(out["drifted_ancestors"])
    return out
