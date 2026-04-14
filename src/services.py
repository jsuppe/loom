"""
Loom services — shared logic between the CLI and MCP server.

Each function here returns plain Python data structures (dicts, lists of
dicts) that are JSON-serializable. Rendering (emojis, tables, colors) and
exit codes stay in the CLI — this module is pure data.

Why this exists:
    The CLI (scripts/loom) and the MCP server (mcp_server/server.py) both
    need to `loom status`, `loom query`, `loom list`, etc. Without a shared
    layer, one side has to re-parse the other's output or reimplement the
    logic. This module is the single source of truth.

Design rules:
    - No `print()`, no `sys.exit()`, no argparse `args` objects.
    - Never raise for "empty result" — return `[]` or a dict with zero
      counts. Reserve exceptions for actual errors (missing store, bad
      input the caller couldn't have prevented).
    - Accept a `LoomStore` the caller already built, so tests can pass a
      temp-dir store without filesystem side effects.
    - Return shapes are stable: they're part of the MCP tool contract.

This module grows as `cmd_*` functions get refactored. See ROADMAP.md
milestone 4.2 and mcp_server/README.md for the full plan.
"""
from __future__ import annotations

from typing import Any

from store import LoomStore


def status(store: LoomStore) -> dict[str, Any]:
    """Project status: counts, drift items.

    Drift item shape:
        {file, lines, req_id, req_value, superseded_at}
    """
    stats = store.stats()
    all_reqs = store.list_requirements(include_superseded=True)
    superseded = [r for r in all_reqs if r.superseded_at]
    active = [r for r in all_reqs if not r.superseded_at]

    drift: list[dict[str, Any]] = []
    for req in superseded:
        for impl in store.get_implementations_for_requirement(req.id):
            drift.append({
                "file": impl.file,
                "lines": impl.lines,
                "req_id": req.id,
                "req_value": req.value,
                "superseded_at": req.superseded_at,
            })

    return {
        "project": store.project,
        "requirements": stats["requirements"],
        "active": len(active),
        "superseded": len(superseded),
        "implementations": stats["implementations"],
        "chat_messages": stats["chat_messages"],
        "drift_count": len(drift),
        "drift": drift,
    }


def query(store: LoomStore, text: str, limit: int = 5) -> list[dict[str, Any]]:
    """Semantic search over requirements.

    Result shape:
        {id, domain, value, status, superseded, source, timestamp, distance}

    The embedding is computed here rather than passed in because every
    real caller embeds the same text. Tests that want deterministic
    results should monkeypatch `embedding.urllib.request.urlopen` to force
    the hash-fallback path.
    """
    from embedding import get_embedding
    vec = get_embedding(text)
    results = store.search_requirements(vec, n=limit)
    return [
        {
            "id": r["requirement"].id,
            "domain": r["requirement"].domain,
            "value": r["requirement"].value,
            "status": r["requirement"].status,
            "superseded": r["requirement"].superseded_at is not None,
            "source": r["requirement"].source_session,
            "timestamp": r["requirement"].timestamp,
            "distance": r.get("distance"),
        }
        for r in results
    ]


def list_requirements(
    store: LoomStore, include_superseded: bool = False
) -> list[dict[str, Any]]:
    """List requirements with their spec/test-spec state.

    Result shape matches what `loom list --json` emits today. Includes
    `has_test` (bool) derived from the JSON test-spec store.
    """
    from testspec import TestSpecStore
    spec_store = TestSpecStore(store.data_dir)

    reqs = store.list_requirements(include_superseded=include_superseded)
    out: list[dict[str, Any]] = []
    for req in reqs:
        spec = spec_store.get_spec(req.id)
        out.append({
            "id": req.id,
            "domain": req.domain,
            "text": req.value,
            "status": req.status,
            "elaboration": req.elaboration,
            "rationale": req.rationale,
            "acceptance_criteria": req.acceptance_criteria or [],
            "test_spec_id": req.test_spec_id,
            "conversation_context": req.conversation_context,
            "is_complete": req.is_complete(),
            "has_test": spec is not None,
            "superseded": req.superseded_at is not None,
        })
    return out


def trace(store: LoomStore, target: str) -> dict[str, Any]:
    """Bidirectional traceability.

    `target` is either a REQ-id (returns linked files + test spec) or a
    file path (returns requirements linked to that file).

    Raises:
        LookupError: target not found (unknown req-id or missing file).

    Result shapes:
        - requirement: {type, id, domain, value, status, superseded_at,
                        implementations: [{file, lines}],
                        test_spec: {description, verified} | None}
        - file: {type, file, requirements: [{id, domain, value, status,
                                             superseded} | {id, orphan: True}]}
    """
    from pathlib import Path
    from testspec import TestSpecStore
    import json as _json

    if target.lower().startswith("req-"):
        req = store.get_requirement(target)
        if req is None:
            raise LookupError(f"Requirement {target} not found")

        impls = store.get_implementations_for_requirement(target)
        spec_store = TestSpecStore(store.data_dir)
        spec = spec_store.get_spec(target)

        return {
            "type": "requirement",
            "id": target,
            "domain": req.domain,
            "value": req.value,
            "status": req.status,
            "superseded_at": req.superseded_at,
            "implementations": [
                {"file": impl.file, "lines": impl.lines} for impl in impls
            ],
            "test_spec": (
                {"description": spec.description,
                 "verified": spec.last_verified is not None}
                if spec else None
            ),
        }

    # File-path branch. Resolve to absolute so we match regardless of how
    # the caller spelled the path, matching cmd_trace's original behavior.
    filepath = Path(target).resolve()
    if not filepath.exists():
        raise LookupError(f"File not found: {target}")

    result = store.implementations.get(include=["metadatas"])
    file_impls = []
    for meta in result.get("metadatas", []):
        impl_path = meta.get("file", "")
        if impl_path and Path(impl_path).resolve() == filepath:
            meta = dict(meta)  # don't mutate the stored metadata
            meta["satisfies"] = _json.loads(meta.get("satisfies", "[]"))
            file_impls.append(meta)

    all_reqs: set[str] = set()
    for meta in file_impls:
        for sat in meta.get("satisfies", []):
            if rid := sat.get("req_id"):
                all_reqs.add(rid)

    req_list: list[dict[str, Any]] = []
    for rid in sorted(all_reqs):
        r = store.get_requirement(rid)
        if r:
            req_list.append({
                "id": rid,
                "domain": r.domain,
                "value": r.value,
                "status": r.status,
                "superseded": r.superseded_at is not None,
            })
        else:
            req_list.append({"id": rid, "orphan": True})

    return {
        "type": "file",
        "file": target,
        "requirements": req_list,
    }


def chain(store: LoomStore, req_id: str) -> dict[str, Any]:
    """Full traceability chain for a requirement: req → patterns → specs
    → implementations → test.

    Raises:
        LookupError: req_id not found.

    Result shape:
        {id, domain, value, status, elaboration, rationale,
         patterns: [{id, name}],
         specifications: [{id, description, status, implementations: [{file, lines}]}],
         direct_implementations: [{file, lines}],  # impls with no spec link
         test_spec: {description, verified} | None}
    """
    from testspec import TestSpecStore

    req = store.get_requirement(req_id)
    if req is None:
        raise LookupError(f"Requirement {req_id} not found")

    patterns = store.get_patterns_for_requirement(req_id)
    specs = store.get_specifications_for_requirement(req_id)
    impls = store.get_implementations_for_requirement(req_id)
    direct_impls = [i for i in impls if not i.satisfies_specs]

    spec_store = TestSpecStore(store.data_dir)
    test = spec_store.get_spec(req_id)

    spec_data = []
    for spec in specs:
        spec_impls = store.get_implementations_for_specification(spec.id)
        spec_data.append({
            "id": spec.id,
            "description": spec.description,
            "status": spec.status,
            "implementations": [
                {"file": si.file, "lines": si.lines} for si in spec_impls
            ],
        })

    return {
        "id": req_id,
        "domain": req.domain,
        "value": req.value,
        "status": req.status,
        "elaboration": req.elaboration,
        "rationale": req.rationale,
        "patterns": [{"id": p.id, "name": p.name} for p in patterns],
        "specifications": spec_data,
        "direct_implementations": [
            {"file": i.file, "lines": i.lines} for i in direct_impls
        ],
        "test_spec": (
            {"description": test.description,
             "verified": test.last_verified is not None}
            if test else None
        ),
    }
