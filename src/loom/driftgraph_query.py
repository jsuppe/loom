"""
Loom ← Driftgraph inbound channel (M13.5 — Architecture B, in-process imports).

Every public function in this module degrades to "no signal" on any
failure (Driftgraph repo missing, Neo4j unreachable, project unknown,
schema mismatch). The PreToolUse hook fires before every Edit/Write
— this code MUST NOT throw or block the agent's edit loop.

Architecture B (in-process import) was picked over Path A (Loom rolls
its own Cypher) and Path C (substrate adds HTTP read API) for v0
because:
  - zero substrate work needed (we already have Driftgraph code on disk)
  - reuses Driftgraph's tested Cypher (foundation-drift logic stays
    in chains.py, where the bot already exercises it)
  - cleanly upgradeable to Path C — swap _ensure_modules() for an
    HTTP client; everything else stays the same

Trade-off: Loom now imports from a sibling repo via sys.path hack.
If Driftgraph schema or chains.py signatures change, the import
breaks; ``is_available()`` returns False and the inbound channel
silently degrades. That's the right failure mode — the agent gets
the M11.5/M12-era context as if M13.5 didn't exist.

The Driftgraph repo is discovered via (in order):
  1. ``$LOOM_DRIFTGRAPH_PATH`` env var
  2. ``~/Downloads/grag``                   (current Jon-machine path)
  3. ``~/dev/grag``
  4. ``~/dev/sdr-graph-memory``             (older pre-rename name)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Driftgraph repo discovery
# ---------------------------------------------------------------------------

_DEFAULT_DRIFTGRAPH_PATHS = [
    Path.home() / "Downloads" / "grag",
    Path.home() / "dev" / "grag",
    Path.home() / "dev" / "sdr-graph-memory",
]


def _resolve_driftgraph_root() -> Optional[Path]:
    """Find the Driftgraph repo root, or None if it's not on disk."""
    env = os.environ.get("LOOM_DRIFTGRAPH_PATH")
    if env:
        p = Path(env).expanduser()
        if (p / "product" / "discord_demo" / "chains.py").exists():
            return p
    for p in _DEFAULT_DRIFTGRAPH_PATHS:
        if (p / "product" / "discord_demo" / "chains.py").exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Lazy module import — cached after first attempt
# ---------------------------------------------------------------------------

_modules_loaded = False
_chains_mod: Any = None
_schema_mod: Any = None


def _ensure_modules() -> bool:
    """Try to import Driftgraph's chains + schema modules. Returns
    True on success, False on any failure. Result is cached so
    repeated calls are cheap."""
    global _modules_loaded, _chains_mod, _schema_mod
    if _modules_loaded:
        return _chains_mod is not None
    _modules_loaded = True
    root = _resolve_driftgraph_root()
    if root is None:
        return False
    sdr_bench = root / "sdr-benchmark"
    discord_demo = root / "product" / "discord_demo"
    # Insert at front so our intended modules win over any same-name
    # modules elsewhere on PATH. Don't mutate sys.path if already there.
    for p in (str(sdr_bench), str(discord_demo)):
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        from experiments.v03 import schema as schema_mod  # type: ignore
        import chains as chains_mod  # type: ignore
    except Exception:
        # Could be missing neo4j driver, missing schema module,
        # broken sibling import — all collapse to "no signal".
        return False
    _schema_mod = schema_mod
    _chains_mod = chains_mod
    return True


# ---------------------------------------------------------------------------
# _SimpleIngestor — the .session() shape chains.py expects
# ---------------------------------------------------------------------------


class _SimpleIngestor:
    """Mirrors the ``.session()`` context-manager shape Driftgraph's
    chains.find_foundation_drift expects from its ``ingestor`` arg.
    Holds the database name so per-project routing is implicit."""

    def __init__(self, driver, database: str):
        self._driver = driver
        self._database = database

    def session(self, **kwargs):
        return self._driver.session(database=self._database, **kwargs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_available() -> bool:
    """True iff Driftgraph code AND a reachable Neo4j instance are
    both present. Cached after the first connection check via
    _modules_loaded; the Neo4j ping itself is NOT cached (we want
    is_available() to flip to False if the Neo4j process dies
    mid-session)."""
    if not _ensure_modules():
        return False
    try:
        driver = _schema_mod.connect()
        try:
            driver.verify_connectivity()
            return True
        finally:
            driver.close()
    except Exception:
        return False


# Cypher: walk BACKWARDS from a starting Claim through BECAUSE_OF
# edges. Any ancestor with `invalidated_at IS NOT NULL` means the
# starting Claim's grounding includes a now-superseded foundation.
# Limit to 5 hops — beyond that the dependency is too indirect to
# surface meaningfully in a system-reminder.
_FIND_DRIFTED_ANCESTORS = """
MATCH (start:Claim {claim_id: $claim_id})
OPTIONAL MATCH path = (start)-[:BECAUSE_OF*1..5]->(ancestor:Claim)
WHERE ancestor.invalidated_at IS NOT NULL
RETURN ancestor.claim_id AS ancestor_claim_id,
       ancestor.subject_text AS ancestor_subject,
       ancestor.predicate_text AS ancestor_predicate,
       ancestor.object_text AS ancestor_object,
       ancestor.invalidated_at AS invalidated_at,
       length(path) AS hops
ORDER BY hops ASC
LIMIT 10
"""


def find_drifted_ancestors_for_claim(
    project: str, claim_id: str,
) -> list[dict]:
    """Return ancestors of ``claim_id`` (via BECAUSE_OF edges, up to
    5 hops) that have been superseded. Empty list = claim's grounding
    is still intact, OR Driftgraph wasn't reachable, OR claim doesn't
    exist in this project's DB.

    Each row: {ancestor_claim_id, ancestor_subject, ancestor_predicate,
    ancestor_object, invalidated_at, hops}.
    """
    if not _ensure_modules() or not project or not claim_id:
        return []
    try:
        driver = _schema_mod.connect()
        try:
            with driver.session(database=project) as s:
                rows = s.run(
                    _FIND_DRIFTED_ANCESTORS, claim_id=claim_id,
                ).data()
            return [r for r in rows if r.get("ancestor_claim_id")]
        finally:
            driver.close()
    except Exception:
        return []


def find_drifted_ancestors_for_req(
    data_dir: Path, req_id: str,
) -> dict:
    """Convenience: looks up the active Driftgraph claim_ids for
    ``req_id`` from the warrants log, then queries each for
    drifted ancestors. Returns:

        {
          "drifted": bool,                    # any ancestor superseded?
          "claim_ids": [...],                 # claim_ids checked
          "drifted_ancestors": [              # one entry per (claim, ancestor)
              {"claim_id": str, "ancestor": dict}
          ],
          "available": bool,                  # was Driftgraph reachable?
        }

    Empty / "no signal" shape: drifted=False, claim_ids=[],
    drifted_ancestors=[], available=False (or True if reachable
    but the req simply has no claims). Callers should treat
    drifted=False as "no concern from this channel" regardless
    of why.
    """
    from . import warrants

    out = {
        "drifted": False, "claim_ids": [], "drifted_ancestors": [],
        "available": False,
    }
    if not is_available():
        return out
    out["available"] = True

    active = warrants.lookup_active_claims_for_req(data_dir, req_id)
    out["claim_ids"] = active
    if not active:
        return out

    # Each claim is in the project the warrant was pushed under.
    # Pull project_tag from the latest push record.
    latest = warrants.lookup_latest_push_for_req(data_dir, req_id)
    project = (latest or {}).get("project_tag") or ""
    if not project:
        return out

    for claim_id in active:
        for anc in find_drifted_ancestors_for_claim(project, claim_id):
            out["drifted_ancestors"].append({
                "claim_id": claim_id,
                "ancestor": anc,
            })
    out["drifted"] = bool(out["drifted_ancestors"])
    return out
