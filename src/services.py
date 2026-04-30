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

from pathlib import Path
from typing import Any

from store import LoomStore

EVENTS_FILENAME = ".loom-events.jsonl"


def _record_event(store: LoomStore, event_type: str, **fields: Any) -> None:
    """Append a typed event to the per-project event log (M5.1).

    The log lives at ``<store.data_dir>/.loom-events.jsonl`` (one JSON
    object per line, append-only). ``services.metrics`` and
    ``services.health_score`` consume it. Failures are swallowed —
    instrumentation must never break a real operation.
    """
    from datetime import datetime, timezone
    import json as _json

    entry: dict[str, Any] = {
        "event": event_type,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    entry.update(fields)
    try:
        path = store.data_dir / EVENTS_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(entry) + "\n")
    except OSError:
        pass


def status(store: LoomStore) -> dict[str, Any]:
    """Project status: counts, drift items.

    Drift item shape:
        {file, lines, req_id, req_value, superseded_at}
    """
    import json as _json

    stats = store.stats()
    all_reqs = store.list_requirements(include_superseded=True)
    superseded = [r for r in all_reqs if r.superseded_at]
    active = [r for r in all_reqs if not r.superseded_at]

    # Single metadata scan + local index instead of calling
    # get_implementations_for_requirement (which re-scans) once per
    # superseded req — the old shape was O(superseded * all_impls).
    impls_by_req: dict[str, list[dict]] = {}
    all_impls = store.implementations.get(include=["metadatas"])
    for meta in all_impls.get("metadatas", []):
        for sat in _json.loads(meta.get("satisfies", "[]")):
            rid = sat.get("req_id")
            if rid:
                impls_by_req.setdefault(rid, []).append(meta)

    drift: list[dict[str, Any]] = []
    for req in superseded:
        for meta in impls_by_req.get(req.id, []):
            drift.append({
                "file": meta.get("file", ""),
                "lines": meta.get("lines", "all"),
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


def query(
    store: LoomStore,
    text: str,
    limit: int = 5,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """Semantic search over requirements.

    Result shape:
        {id, domain, value, status, superseded, source, timestamp, distance}

    Archived requirements (M2.3) are filtered out by default. Pass
    `include_archived=True` to include them.

    The embedding is computed here rather than passed in because every
    real caller embeds the same text. Tests that want deterministic
    results should monkeypatch `embedding.urllib.request.urlopen` to force
    the hash-fallback path.
    """
    from embedding import get_embedding
    vec = get_embedding(text)
    # Over-fetch when we plan to filter so a small `limit` doesn't return
    # fewer results than expected when all top-k hits are archived.
    n_fetch = limit if include_archived else max(limit * 3, 15)
    results = store.search_requirements(vec, n=n_fetch)
    if not include_archived:
        results = [r for r in results if r["requirement"].status != "archived"]
    results = results[:limit]
    # M2.1: a successful semantic hit counts as "the agent looked at this
    # requirement," so stamp last_referenced. Touching only the returned
    # set (not the whole store) keeps `loom stale` honest — un-hit reqs
    # stay cold, which is the signal we want.
    for r in results:
        store.touch_requirement(r["requirement"].id)
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
    store: LoomStore,
    include_superseded: bool = False,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """List requirements with their spec/test-spec state.

    Result shape matches what `loom list --json` emits today. Includes
    `has_test` (bool) derived from the JSON test-spec store.

    Archived requirements (M2.3) are excluded by default — pass
    `include_archived=True` to surface them. Superseded requirements
    follow the same opt-in pattern via `include_superseded`.
    """
    from testspec import TestSpecStore
    spec_store = TestSpecStore(store.data_dir)

    reqs = store.list_requirements(include_superseded=include_superseded)
    out: list[dict[str, Any]] = []
    for req in reqs:
        if not include_archived and req.status == "archived":
            continue
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
            "last_referenced": req.last_referenced,
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
        store.touch_requirement(target)  # M2.1

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

    # Same O(matches) treatment as services.context — use Chroma's `where`
    # filter on `file` instead of scanning every impl. See that function
    # for the trade-off around relative-stored paths.
    resolved_str = str(filepath)
    metadatas = store.implementations.get(
        where={"file": resolved_str}, include=["metadatas"],
    ).get("metadatas", [])
    if not metadatas and resolved_str != target:
        metadatas = store.implementations.get(
            where={"file": target}, include=["metadatas"],
        ).get("metadatas", [])

    file_impls = []
    for meta in metadatas:
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
            store.touch_requirement(rid)  # M2.1
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
    store.touch_requirement(req_id)  # M2.1

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


def coverage(store: LoomStore) -> dict[str, Any]:
    """Three-layer coverage analysis: req→spec, spec→impl, spec→test.

    Result shape:
        {
          project: str,
          layer_1_req_to_spec: {
            total_requirements, coverage_pct, with_specs, without_specs: [entry]
          },
          layer_2_spec_to_impl: {total_specs, coverage_pct, with_impls, without_impls: [entry]},
          layer_3_spec_to_test: {total_specs, coverage_pct, with_tests, without_tests: [entry]},
        }

    Without_specs entry: {id, domain, value, status, spec_ids, direct_implementations}.
    Without_impls / without_tests entry: {id, parent_req, description, status,
                                         implementation_files, test_ids}.

    Scan-based "likely match" suggestions are NOT returned here — they
    depend on cwd and the filesystem, which the CLI handles in its
    own _scan_project_for_specs helper. MCP can layer that on later.
    """
    from testspec import TestSpecStore

    reqs = store.list_requirements(include_superseded=False)
    spec_store = TestSpecStore(store.data_dir)
    all_specs = store.list_specifications()

    reqs_without_specs: list[dict[str, Any]] = []
    reqs_with_specs: list[dict[str, Any]] = []
    for req in reqs:
        specs = store.get_specifications_for_requirement(req.id)
        entry = {
            "id": req.id,
            "domain": req.domain,
            "value": req.value,
            "status": req.status,
            "spec_ids": [s.id for s in specs],
            "direct_implementations": [
                {"file": i.file, "lines": i.lines}
                for i in store.get_implementations_for_requirement(req.id)
                if not (i.satisfies_specs or [])
            ],
        }
        (reqs_with_specs if specs else reqs_without_specs).append(entry)

    specs_with_impls: list[dict[str, Any]] = []
    specs_without_impls: list[dict[str, Any]] = []
    specs_with_tests: list[dict[str, Any]] = []
    specs_without_tests: list[dict[str, Any]] = []

    for spec in all_specs:
        if spec.superseded_at:
            continue
        impls = store.get_implementations_for_specification(spec.id)
        tests = spec_store.get_specs_for_spec_id(spec.id)

        spec_entry = {
            "id": spec.id,
            "parent_req": spec.parent_req,
            "description": spec.description[:80],
            "status": spec.status,
            "implementation_files": [i.file for i in impls],
            "test_ids": [t.req_id for t in tests],
        }
        (specs_with_impls if impls else specs_without_impls).append(spec_entry)
        (specs_with_tests if tests else specs_without_tests).append(spec_entry)

    total_reqs = len(reqs)
    active_specs = [s for s in all_specs if not s.superseded_at]
    total_specs = len(active_specs)

    spec_cov_pct = (len(reqs_with_specs) / total_reqs * 100) if total_reqs else 100
    impl_cov_pct = (len(specs_with_impls) / total_specs * 100) if total_specs else 0
    test_cov_pct = (len(specs_with_tests) / total_specs * 100) if total_specs else 0

    return {
        "project": store.project,
        "layer_1_req_to_spec": {
            "total_requirements": total_reqs,
            "coverage_pct": round(spec_cov_pct, 1),
            "with_specs": len(reqs_with_specs),
            "without_specs": reqs_without_specs,
        },
        "layer_2_spec_to_impl": {
            "total_specs": total_specs,
            "coverage_pct": round(impl_cov_pct, 1),
            "with_impls": len(specs_with_impls),
            "without_impls": specs_without_impls,
        },
        "layer_3_spec_to_test": {
            "total_specs": total_specs,
            "coverage_pct": round(test_cov_pct, 1),
            "with_tests": len(specs_with_tests),
            "without_tests": specs_without_tests,
        },
    }


def conflicts(
    store: LoomStore,
    text: str,
    *,
    verify: bool = False,
    verify_model: str | None = None,
    pool_top_n: int = 7,
    verify_fn=None,
) -> list[dict[str, Any]]:
    """Check whether `text` conflicts with existing requirements.

    `text` is parsed as `domain | value`; if no `|`, defaults to
    `behavior | <text>`.

    When `verify=False` (default, backward-compatible): uses the
    similarity-based heuristic in docs.check_conflicts.

    When `verify=True`: builds a broader candidate pool (top-N semantic
    neighbors plus same-domain keyword-overlap hits) and runs each
    through a local LLM verifier (see src/conflict_verify.py). This
    trades ~1s of latency per check for substantially higher precision
    and the ability to catch logic-only contradictions the similarity
    heuristic misses (e.g. "guests are not permitted" vs "guests may
    check out"). Benchmark: benchmarks/conflicts_verified.py.

    `verify_fn` is an injection seam for tests — pass a stub matching
    the src.conflict_verify.verify signature: (candidate, existing,
    model) -> (bool, str). Raises RuntimeError if the verifier errors
    on any pool member (so the caller doesn't silently drop results).

    Result is a list of conflict entries; empty list means no conflicts.
    Each entry: {existing_id, existing_domain, existing_value, reason,
                 similarity? (float), overlap? (list[str])}.
    """
    from datetime import datetime, timezone
    from docs import check_conflicts
    from store import Requirement
    from embedding import get_embedding

    if "|" in text:
        domain, value = text.split("|", 1)
        domain = domain.strip().lower()
        value = value.strip()
    else:
        domain, value = "behavior", text.strip()

    temp_req = Requirement(
        id="TEMP",
        domain=domain,
        value=value,
        source_msg_id="conflict-check",
        source_session="cli",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    if not verify:
        # Baseline: similarity + keyword heuristic only.
        out: list[dict[str, Any]] = []
        for c in check_conflicts(store, temp_req, get_embedding_fn=get_embedding):
            existing = c["existing"]
            entry = {
                "existing_id": existing.id,
                "existing_domain": existing.domain,
                "existing_value": existing.value,
                "reason": c["reason"],
            }
            if "similarity" in c:
                entry["similarity"] = c["similarity"]
            if "overlap" in c:
                entry["overlap"] = list(c["overlap"])
            out.append(entry)
        return out

    # ------- Verified path -------
    # Pool: unfiltered top-N semantic + same-domain keyword-overlap hits.
    # We want recall here; precision comes from the LLM verifier.
    if verify_fn is None:
        from conflict_verify import verify as verify_fn  # type: ignore

    new_embedding = get_embedding(value)
    similar = store.search_requirements(new_embedding, n=pool_top_n)
    pool: dict[str, dict[str, Any]] = {}  # req_id -> {req, similarity?}
    for match in similar:
        existing = match["requirement"]
        if existing.id == "TEMP" or existing.superseded_at:
            continue
        distance = match.get("distance", 1.0)
        similarity = max(0.0, 1.0 - (distance / 2.0))
        pool[existing.id] = {"req": existing, "similarity": similarity}

    # Keyword-overlap hits (same domain, >=3 non-stopword words in common).
    stopwords = {"the", "a", "an", "is", "are", "should", "be", "to",
                 "for", "with", "and", "or"}
    new_words = set(value.lower().split()) - stopwords
    for existing in store.list_requirements(include_superseded=False):
        if existing.id in pool or existing.domain != domain:
            continue
        overlap_words = new_words & (set(existing.value.lower().split()) - stopwords)
        if len(overlap_words) >= 3:
            pool[existing.id] = {"req": existing, "overlap": overlap_words}

    # Verify each pool member with the LLM.
    out = []
    for rid, entry in sorted(pool.items()):
        existing = entry["req"]
        is_conflict, raw = verify_fn(value, existing.value, verify_model)
        if raw.startswith("<error:"):
            raise RuntimeError(f"Verifier failed on {rid}: {raw}")
        if not is_conflict:
            continue
        result: dict[str, Any] = {
            "existing_id": existing.id,
            "existing_domain": existing.domain,
            "existing_value": existing.value,
            "reason": f"LLM-verified (model={verify_model or 'default'})",
        }
        if "similarity" in entry:
            result["similarity"] = entry["similarity"]
        if "overlap" in entry:
            result["overlap"] = list(entry["overlap"])
        out.append(result)
    return out


def doctor(store: LoomStore) -> dict[str, Any]:
    """Run health checks: Ollama, store, orphans, drift, test coverage, domains.

    Result shape:
        {project, healthy: bool, checks: {...}, issues: [str], warnings: [str]}

    `healthy` is True iff `issues` is empty. The store check is fatal —
    if it raises, we short-circuit and return immediately.
    """
    import urllib.request
    import json as _json
    from testspec import TestSpecStore

    checks: dict[str, Any] = {}
    issues: list[str] = []
    warnings: list[str] = []

    # 1. Ollama
    ollama_ok = False
    ollama_models: list[str] = []
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/tags",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = _json.loads(resp.read().decode())
            ollama_models = [m["name"] for m in result.get("models", [])]
            if any(m.startswith("nomic-embed-text") for m in ollama_models):
                ollama_ok = True
            else:
                warnings.append("nomic-embed-text model not found")
    except Exception as e:
        issues.append(f"Ollama not reachable: {e}")
    # Return the full list (FINDINGS-wild F3 — the previous [:5] slice
    # hid 9+ available models on multi-model setups). CLI can truncate
    # for display if it wants; JSON/MCP consumers want everything.
    checks["ollama"] = {"ok": ollama_ok, "models": ollama_models}

    # 2. Store (fatal if it fails)
    try:
        stats = store.stats()
        checks["store"] = {"ok": True, **stats}
    except Exception as e:
        issues.append(f"Store error: {e}")
        checks["store"] = {"ok": False, "error": str(e)}
        return {
            "project": store.project,
            "healthy": False,
            "checks": checks,
            "issues": issues,
            "warnings": warnings,
        }

    # 3. Orphan implementations
    all_impls = store.implementations.get(include=["metadatas"])
    orphan_count = 0
    for meta in all_impls.get("metadatas", []):
        for sat in _json.loads(meta.get("satisfies", "[]")):
            if store.get_requirement(sat["req_id"]) is None:
                orphan_count += 1
                warnings.append(
                    f"Impl {meta['id'][:8]}... links to missing {sat['req_id']}"
                )
    checks["orphans"] = {"count": orphan_count}

    # 4. Drift (impls linked to superseded reqs)
    superseded_reqs = [
        r for r in store.list_requirements(include_superseded=True) if r.superseded_at
    ]
    drift_count = sum(
        len(store.get_implementations_for_requirement(sr.id)) for sr in superseded_reqs
    )
    checks["drift"] = {"count": drift_count}
    if drift_count > 0:
        warnings.append(
            f"{drift_count} implementation(s) linked to superseded requirements"
        )

    # 5. Test spec coverage
    try:
        spec_store = TestSpecStore(store.data_dir)
        specs = {s.req_id: s for s in spec_store.list_specs()}
        active_reqs = store.list_requirements(include_superseded=False)
        missing_specs = [r for r in active_reqs if r.id not in specs]
        coverage_pct = (
            ((len(active_reqs) - len(missing_specs)) / len(active_reqs) * 100)
            if active_reqs else 100
        )
        checks["test_coverage"] = {
            "total": len(active_reqs),
            "covered": len(active_reqs) - len(missing_specs),
            "missing": len(missing_specs),
            "missing_ids": [r.id for r in missing_specs[:5]],
            "coverage_pct": round(coverage_pct, 1),
        }
    except Exception as e:
        checks["test_coverage"] = {"error": str(e)}

    # 6. Domain consistency
    valid_domains = {"terminology", "behavior", "ui", "data", "architecture"}
    custom_domains: set[str] = set()
    for r in store.list_requirements(include_superseded=True):
        if r.domain not in valid_domains:
            custom_domains.add(r.domain)
    if custom_domains:
        warnings.append(f"Non-standard domains: {', '.join(custom_domains)}")
    checks["domains"] = {"custom": sorted(custom_domains)}

    # Duplicate-spec check: any requirement with >1 non-superseded spec.
    # Agents generating specs after edit-confusion have been observed
    # to produce duplicates (the sparkeye case: two specs under the
    # same req pointing at different path conventions). Surface it here
    # so existing stores in this state are visible without waiting for
    # the sibling check at spec_add time to catch the NEXT duplicate.
    duplicate_specs: list[dict[str, Any]] = []
    for req in store.list_requirements(include_superseded=False):
        sibs = store.list_specifications(req_id=req.id, include_superseded=False)
        if len(sibs) > 1:
            duplicate_specs.append({
                "req_id": req.id,
                "count": len(sibs),
                "spec_ids": [s.id for s in sibs],
            })
    if duplicate_specs:
        for entry in duplicate_specs:
            warnings.append(
                f"Requirement {entry['req_id']} has {entry['count']} "
                f"non-superseded specs: {', '.join(entry['spec_ids'])} — "
                f"supersede the outdated one(s) or pick a canonical path"
            )
    checks["duplicate_specs"] = {
        "count": len(duplicate_specs),
        "items": duplicate_specs,
    }

    return {
        "project": store.project,
        "healthy": len(issues) == 0,
        "checks": checks,
        "issues": issues,
        "warnings": warnings,
    }


def _check_runner_deps(target_dir: Path, runner_name: str) -> dict[str, Any]:
    """Detect whether the configured test runner's dependencies are declared.

    Returns::

        {"ok": bool, "where": str | None, "runner": str, "warning": str | None}

    We only READ. Never install anything — that's intrusive and out of
    scope for init.
    """
    td = target_dir

    # Python — pytest in requirements.txt / pyproject / nested.
    if runner_name == "pytest":
        for candidate in (
            td / "requirements.txt",
            td / "requirements-dev.txt",
            td / "dev-requirements.txt",
            td / "pyproject.toml",
            td / "setup.py",
            td / "setup.cfg",
        ):
            if candidate.exists():
                try:
                    if "pytest" in candidate.read_text(encoding="utf-8"):
                        return {"ok": True, "where": candidate.name,
                                "runner": runner_name, "warning": None}
                except OSError:
                    continue
        for sub in ("src/backend", "backend", "api", "server"):
            candidate = td / sub / "requirements.txt"
            if candidate.exists():
                try:
                    if "pytest" in candidate.read_text(encoding="utf-8"):
                        return {
                            "ok": True,
                            "where": str(candidate.relative_to(td)).replace("\\", "/"),
                            "runner": runner_name, "warning": None,
                        }
                except OSError:
                    pass
        return {
            "ok": False, "where": None, "runner": runner_name,
            "warning": "pytest not declared in requirements.txt / pyproject.toml — "
                       "loom_exec grades with pytest, add it before running tasks",
        }

    # Dart / Flutter — pubspec.yaml must declare `test` (Dart) or
    # `flutter_test` (Flutter) dev_dependency.
    if runner_name in ("dart_test", "flutter_test"):
        pubspec = td / "pubspec.yaml"
        if not pubspec.exists():
            return {
                "ok": False, "where": None, "runner": runner_name,
                "warning": f"{runner_name} configured but no pubspec.yaml found",
            }
        try:
            text = pubspec.read_text(encoding="utf-8")
        except OSError:
            text = ""
        needed = "flutter_test" if runner_name == "flutter_test" else "test:"
        if needed in text:
            return {"ok": True, "where": "pubspec.yaml",
                    "runner": runner_name, "warning": None}
        return {
            "ok": False, "where": None, "runner": runner_name,
            "warning": f"pubspec.yaml does not declare {needed!r} — "
                       f"loom_exec grades with {runner_name}",
        }

    # Vitest — package.json devDependencies.
    if runner_name == "vitest":
        pkg = td / "package.json"
        if not pkg.exists():
            return {
                "ok": False, "where": None, "runner": runner_name,
                "warning": "vitest configured but no package.json found",
            }
        try:
            text = pkg.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if "vitest" in text:
            return {"ok": True, "where": "package.json",
                    "runner": runner_name, "warning": None}
        return {
            "ok": False, "where": None, "runner": runner_name,
            "warning": "vitest not in package.json devDependencies — "
                       "loom_exec grades with vitest",
        }

    # Unknown runner — just pass through; loom_exec will fall back to pytest.
    return {
        "ok": True, "where": None, "runner": runner_name,
        "warning": None,
    }


def init(
    *,
    target_dir: Path | str,
    project: str,
    force: bool = False,
    ollama_url: str = "http://localhost:11434",
    template: str | None = None,
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Onboard an existing target repo: write .loom-config.json + health check.

    If ``template`` is given, also scaffold files from that template into
    ``target_dir`` before the health-check runs. Files already present
    in the target are skipped (never overwritten) unless ``force=True``.

    Pure function — does not touch the Loom store (caller's responsibility
    if they want to create one). Target-side side effects: writes the
    config file, creates ``tests/`` if missing, and (when ``template`` is
    set) writes template files.

    Result shape::

        {
          "config_path": str,
          "project": str,
          "target_dir": str,
          "config": {...},              # the dict that was written
          "created_config": bool,
          "created_tests_dir": bool,
          "template":       str | None, # the template applied, if any
          "template_files": {"written": [...], "skipped": [...]},  # None if no template
          "checks": {...},
          "warnings": [str],
          "next_steps": [str],
        }

    Raises:
        NotADirectoryError: target_dir doesn't exist.
        FileExistsError: .loom-config.json already exists and force=False.
        LookupError: template name doesn't exist.
        ValueError: template declares variables not provided and without defaults.
    """
    import urllib.request
    import urllib.error
    import json as _json
    import config as _config

    td = Path(target_dir).expanduser().resolve()
    if not td.is_dir():
        raise NotADirectoryError(f"target_dir does not exist: {td}")

    cfg_path = _config.config_path(td)
    if cfg_path.exists() and not force:
        raise FileExistsError(
            f"{cfg_path} already exists (pass force=True to overwrite)"
        )

    # Template rendering, if requested. Runs BEFORE config write so the
    # user sees a coherent "empty dir → scaffold → config" ordering in
    # any output logs.
    template_result: dict[str, Any] | None = None
    template_config_overrides: dict[str, Any] = {}
    if template:
        import templates as _templates
        tmpl = _templates.load_template(template)
        provided = dict(variables or {})
        missing = _templates.required_variables(tmpl, provided)
        if missing:
            names = ", ".join(v.name for v in missing)
            raise ValueError(
                f"template {template!r} requires variables without defaults: {names}"
            )
        template_result = _templates.render_template(
            tmpl, td, provided, overwrite=force,
        )
        template_config_overrides = dict(tmpl.config_overrides)

    # Build the config dict. Start from defaults, override the project name,
    # then apply any template-declared config overrides (e.g. a Flutter
    # template pinning test_runner=flutter_test + test_dir=test).
    cfg: dict[str, Any] = {**_config.DEFAULTS, "ignore": list(_config.DEFAULTS["ignore"])}
    cfg["project"] = project
    for k, v in template_config_overrides.items():
        cfg[k] = v

    _config.save_config(td, cfg)

    # -- Health checks (non-fatal; fill the result and let caller decide) --
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    ollama_models: list[str] = []
    ollama_ok = False
    ollama_err: str | None = None
    try:
        req = urllib.request.Request(
            f"{ollama_url}/api/tags",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = _json.loads(resp.read().decode())
            ollama_models = [m["name"] for m in body.get("models", [])]
            ollama_ok = True
    except Exception as e:
        ollama_err = str(e)
    checks["ollama"] = {"ok": ollama_ok, "error": ollama_err}

    def _has_model(name: str) -> bool:
        # nomic-embed-text:latest matches "nomic-embed-text"
        return any(m == name or m.startswith(name + ":") for m in ollama_models)

    checks["embedding_model"] = {
        "ok": _has_model(cfg["embedding_model"]),
        "name": cfg["embedding_model"],
    }
    if ollama_ok and not checks["embedding_model"]["ok"]:
        warnings.append(
            f"embedding model {cfg['embedding_model']!r} not pulled — "
            f"run `ollama pull {cfg['embedding_model']}`"
        )

    checks["executor_model"] = {
        "ok": _has_model(cfg["executor_model"]),
        "name": cfg["executor_model"],
    }
    if ollama_ok and not checks["executor_model"]["ok"]:
        warnings.append(
            f"executor model {cfg['executor_model']!r} not pulled — "
            f"run `ollama pull {cfg['executor_model']}`"
        )

    # Runner-appropriate dep check. pytest in Python repos; dart/flutter
    # tooling in Dart repos; vitest in package.json for TS repos. We don't
    # install anything — just report.
    runner_name = cfg.get("test_runner") or "pytest"
    checks["test_runner_deps"] = _check_runner_deps(td, runner_name)
    if not checks["test_runner_deps"]["ok"]:
        warnings.append(checks["test_runner_deps"]["warning"])

    # tests/ dir
    tests_dir = td / cfg["test_dir"]
    existed = tests_dir.exists()
    if not existed:
        tests_dir.mkdir(parents=True)
    checks["tests_dir"] = {
        "ok": True,
        "path": str(tests_dir.relative_to(td)),
        "existed": existed,
    }

    next_steps = [
        "loom extract  — capture the first requirement",
        "loom spec <REQ-id>  — elaborate it into a specification",
        "loom decompose <SPEC-id> --apply  — turn the spec into atomic tasks",
        "loom_exec --next  — execute the next ready task",
    ]

    return {
        "config_path": str(cfg_path),
        "project": project,
        "target_dir": str(td),
        "config": cfg,
        "created_config": True,
        "created_tests_dir": not existed,
        "template": template,
        "template_files": template_result,
        "checks": checks,
        "warnings": warnings,
        "next_steps": next_steps,
    }


def extract(
    store: LoomStore,
    *,
    domain: str,
    value: str,
    msg_id: str = "manual",
    session: str = "cli",
    rationale: str | None = None,
) -> dict[str, Any]:
    """Add a single requirement.

    Returns {req_id, domain, value, conflicts}. Conflicts is a list of
    conflict entries (same shape as `services.conflicts`); empty if none.
    The requirement is added to the store regardless of conflicts —
    callers (CLI, MCP) decide how to surface them.

    Note: callers that want to parse `REQUIREMENT: domain | text` syntax
    should do that themselves; this function takes structured fields.
    """
    from datetime import datetime, timezone
    import hashlib as _hashlib
    from store import Requirement
    from embedding import get_embedding

    domain = domain.strip().lower()
    value = value.strip()
    timestamp = datetime.now(timezone.utc).isoformat()
    req_id = f"REQ-{_hashlib.sha256(f'{domain}:{value}'.encode()).hexdigest()[:8]}"

    req = Requirement(
        id=req_id,
        domain=domain,
        value=value,
        source_msg_id=msg_id,
        source_session=session,
        timestamp=timestamp,
        rationale=rationale,
    )

    # Conflict check is best-effort. Done before adding so the conflict
    # list reflects pre-existing reqs, not this one.
    try:
        from docs import check_conflicts
        raw_conflicts = check_conflicts(store, req, get_embedding_fn=get_embedding)
    except Exception:
        raw_conflicts = []

    conflicts_out: list[dict[str, Any]] = []
    for c in raw_conflicts:
        existing = c["existing"]
        entry = {
            "existing_id": existing.id,
            "existing_domain": existing.domain,
            "existing_value": existing.value,
            "reason": c["reason"],
        }
        if "similarity" in c:
            entry["similarity"] = c["similarity"]
        if "overlap" in c:
            entry["overlap"] = list(c["overlap"])
        conflicts_out.append(entry)

    embedding = get_embedding(value)
    store.add_requirement(req, embedding)

    # M5.1: log the extraction + any conflicts caught at extract time
    # so `loom metrics` can report "conflicts caught before commit".
    _record_event(
        store, "requirement_extracted",
        req_id=req_id, domain=domain,
        has_rationale=bool(rationale),
    )
    for c in conflicts_out:
        _record_event(
            store, "conflict_found",
            req_id=req_id, existing_id=c["existing_id"],
            reason=c.get("reason"),
        )

    return {
        "req_id": req_id,
        "domain": domain,
        "value": value,
        "conflicts": conflicts_out,
    }


def _read_file_content(file_path: str, lines: str | None = None) -> str:
    """Read file (optionally a line range like '42-78'). Raises LookupError."""
    from pathlib import Path
    p = Path(file_path)
    if not p.exists():
        raise LookupError(f"File not found: {file_path}")
    content = p.read_text()
    if lines:
        start, end = (int(x) for x in lines.split("-"))
        content = "\n".join(content.split("\n")[start - 1:end])
    return content


def check(
    store: LoomStore, file_path: str, lines: str | None = None
) -> dict[str, Any]:
    """Check a file (or line range) for drift against linked requirements.

    Returns:
        {file, lines, linked: bool, drift_detected: bool,
         requirements: [{req_id, value, domain, status, drifted, superseded_at}]}

    `linked` is False if no Implementation exists for this file/range; in
    that case `requirements` is `[]` and `drift_detected` is False.

    Raises:
        LookupError: file not found.
    """
    from store import generate_impl_id

    # Resolve early so a missing file fails fast (without a stray read).
    if not __import__("pathlib").Path(file_path).exists():
        raise LookupError(f"File not found: {file_path}")

    impl_id = generate_impl_id(file_path, lines or "all")
    impl = store.get_implementation(impl_id)

    if not impl:
        return {
            "file": file_path,
            "lines": lines,
            "linked": False,
            "drift_detected": False,
            "requirements": [],
        }

    drift_found = False
    results: list[dict[str, Any]] = []
    for sat in impl.satisfies:
        req = store.get_requirement(sat["req_id"])
        if req:
            store.touch_requirement(sat["req_id"])  # M2.1
            drifted = req.superseded_at is not None
            if drifted:
                drift_found = True
            results.append({
                "req_id": sat["req_id"],
                "value": req.value,
                "domain": req.domain,
                "status": req.status,
                "drifted": drifted,
                "superseded_at": req.superseded_at,
                "rationale": req.rationale,
            })

    # M5.1: every linked check is a drift signal — emit either a
    # drift_detected event (with the offending req_ids) or a clean
    # signal so metrics can compute the drift ratio over a window.
    if drift_found:
        _record_event(
            store, "drift_detected",
            file=file_path, lines=lines,
            req_ids=[r["req_id"] for r in results if r["drifted"]],
        )
    else:
        _record_event(
            store, "check_clean",
            file=file_path, lines=lines,
        )

    return {
        "file": file_path,
        "lines": lines,
        "linked": True,
        "drift_detected": drift_found,
        "requirements": results,
    }


def context(store: LoomStore, file_path: str) -> dict[str, Any]:
    """File-scoped briefing for pre-edit agent hooks.

    Aggregates every requirement, specification, and drift signal linked
    to any implementation at `file_path`. Unlike `check()` — which keys
    on an exact (file, line-range) match — this surfaces all links that
    touch the file, because a PreToolUse hook usually doesn't know which
    range an earlier `link` call used.

    Result shape:
        {file, linked, drift_detected,
         requirements: [{id, domain, value, status, superseded,
                         superseded_at, rationale, lines}],
         specifications: [{id, description, status, parent_req, lines}],
         summary: str}

    `summary` is a one-line message suitable for direct injection as a
    system-reminder. Empty when `linked=False`.

    Raises:
        LookupError: file not found.
    """
    from pathlib import Path
    import json as _json

    filepath = Path(file_path).resolve()
    if not filepath.exists():
        raise LookupError(f"File not found: {file_path}")

    # Query by exact string match on both the resolved absolute path and
    # the caller's original spelling. Impls stored with relative paths
    # whose resolved form happens to match `filepath` won't be found —
    # that's an accepted trade to keep this O(matches) instead of O(N).
    # Callers that need bulletproof path matching should store absolute
    # paths at link time (spec_link already does; link should too).
    resolved_str = str(filepath)
    metadatas = store.implementations.get(
        where={"file": resolved_str}, include=["metadatas"],
    ).get("metadatas", [])
    if not metadatas and resolved_str != file_path:
        metadatas = store.implementations.get(
            where={"file": file_path}, include=["metadatas"],
        ).get("metadatas", [])

    req_entries: dict[str, dict[str, Any]] = {}
    spec_entries: dict[str, dict[str, Any]] = {}

    for meta in metadatas:
        lines = meta.get("lines", "all")

        for sat in _json.loads(meta.get("satisfies", "[]")):
            rid = sat.get("req_id")
            if not rid or rid in req_entries:
                continue
            req = store.get_requirement(rid)
            if not req:
                continue
            req_entries[rid] = {
                "id": rid,
                "domain": req.domain,
                "value": req.value,
                "status": req.status,
                "superseded": req.superseded_at is not None,
                "superseded_at": req.superseded_at,
                "rationale": req.rationale,
                "lines": lines,
            }

        for sid in _json.loads(meta.get("satisfies_specs", "[]")):
            if sid in spec_entries:
                continue
            spec = store.get_specification(sid)
            if not spec:
                continue
            spec_entries[sid] = {
                "id": sid,
                "description": spec.description,
                "status": spec.status,
                "parent_req": spec.parent_req,
                "lines": lines,
            }

    reqs = sorted(req_entries.values(), key=lambda r: r["id"])
    specs = sorted(spec_entries.values(), key=lambda s: s["id"])
    drift = [r for r in reqs if r["superseded"]]
    linked = bool(reqs or specs)

    if not linked:
        summary = ""
    else:
        parts: list[str] = []
        if reqs:
            parts.append(f"{len(reqs)} req(s)")
        if specs:
            parts.append(f"{len(specs)} spec(s)")
        summary = f"Loom: {file_path} linked to {', '.join(parts)}"
        if drift:
            summary += " — DRIFT on " + ", ".join(d["id"] for d in drift[:3])
            if len(drift) > 3:
                summary += f" (+{len(drift) - 3} more)"

    return {
        "file": file_path,
        "linked": linked,
        "drift_detected": bool(drift),
        "requirements": reqs,
        "specifications": specs,
        "summary": summary,
    }


def cost(
    store: LoomStore,
    *,
    tail: int | None = None,
    log_path: "Any" = None,
) -> dict[str, Any]:
    """Aggregate PreToolUse hook activity from the JSONL log.

    The hook (hooks/loom_pretool.py) appends one line per fire to
    `<store.data_dir>/.hook-log.jsonl`. This reads that log and returns
    stats the user can compare against the effectiveness side of the
    equation: latency percentiles, total bytes/tokens injected, and the
    fraction of fires that produced no context (pure overhead).

    Args:
        store: LoomStore whose data_dir hosts the log.
        tail: if set, only consider the last N entries (after filtering
            to well-formed lines). Useful for "last session only".
        log_path: explicit override for the log location (Path or str).
            Overrides the default `store.data_dir / .hook-log.jsonl`.
            Mostly for tests and cross-project rollups.

    Returns:
        {
          "log_path": str,
          "exists": bool,
          "fires": int,                 # watched-tool invocations recorded
          "injections": int,            # fires where additionalContext was sent
          "empty_fires": int,           # fires that logged but fired=False
          "overhead_pct": float,        # empty_fires / fires * 100
          "drift_events": int,
          "latency_ms": {"p50", "p95", "p99", "max"},
          "bytes": {"avg", "total"},
          "tokens_est": {"avg", "total"},   # bytes / 4 (rough llama/claude estimate)
          "by_tool": {tool_name: count},
          "skipped": {reason: count},   # reasons fires produced no injection
        }

    A missing log file returns `exists: False` with zero-valued stats.
    """
    import json as _json
    from pathlib import Path

    path = Path(log_path) if log_path is not None else store.data_dir / ".hook-log.jsonl"

    empty = {
        "log_path": str(path),
        "exists": False,
        "fires": 0,
        "injections": 0,
        "empty_fires": 0,
        "overhead_pct": 0.0,
        "drift_events": 0,
        "latency_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0},
        "bytes": {"avg": 0.0, "total": 0},
        "tokens_est": {"avg": 0.0, "total": 0},
        "by_tool": {},
        "skipped": {},
    }
    if not path.exists():
        return empty

    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(_json.loads(line))
            except _json.JSONDecodeError:
                continue
    if tail is not None and tail > 0:
        entries = entries[-tail:]
    if not entries:
        out = dict(empty)
        out["exists"] = True
        return out

    fires = len(entries)
    injections = sum(1 for e in entries if e.get("fired"))
    empty_fires = fires - injections
    drift_events = sum(1 for e in entries if e.get("drift"))

    import math
    latencies = sorted(float(e.get("latency_ms", 0.0)) for e in entries)

    def _pct(p: float) -> float:
        if not latencies:
            return 0.0
        # Nearest-rank percentile: the smallest value at or above the cutoff.
        idx = max(0, min(len(latencies) - 1, math.ceil(p * len(latencies)) - 1))
        return round(latencies[idx], 2)

    total_bytes = sum(int(e.get("bytes", 0)) for e in entries)
    avg_bytes = total_bytes / fires if fires else 0.0

    by_tool: dict[str, int] = {}
    skipped: dict[str, int] = {}
    for e in entries:
        tool = e.get("tool") or ""
        if tool:
            by_tool[tool] = by_tool.get(tool, 0) + 1
        reason = e.get("skipped")
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1

    return {
        "log_path": str(path),
        "exists": True,
        "fires": fires,
        "injections": injections,
        "empty_fires": empty_fires,
        "overhead_pct": round(empty_fires / fires * 100.0, 1) if fires else 0.0,
        "drift_events": drift_events,
        "latency_ms": {
            "p50": _pct(0.50),
            "p95": _pct(0.95),
            "p99": _pct(0.99),
            "max": round(latencies[-1], 2) if latencies else 0.0,
        },
        "bytes": {"avg": round(avg_bytes, 1), "total": total_bytes},
        "tokens_est": {
            "avg": round(avg_bytes / 4.0, 1),
            "total": total_bytes // 4,
        },
        "by_tool": by_tool,
        "skipped": skipped,
    }


def _read_events(store: LoomStore, *, since_days: int | None = None) -> list[dict[str, Any]]:
    """Read the project's append-only event log, optionally clipped to a
    trailing N-day window. Used by metrics() and health_score()."""
    import json as _json
    from datetime import datetime, timedelta, timezone

    path = store.data_dir / EVENTS_FILENAME
    if not path.exists():
        return []
    cutoff: datetime | None = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            if cutoff is not None:
                ts_str = e.get("ts", "")
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if ts < cutoff:
                    continue
            out.append(e)
    return out


def metrics(
    store: LoomStore,
    *,
    since_days: int | None = None,
) -> dict[str, Any]:
    """Aggregate effectiveness metrics for the project (M5.2).

    Reads the event log (extract / link / check / conflict events) and
    cross-references against the live store to surface coverage,
    activity, and freshness in one snapshot. Use ``since_days`` to clip
    the activity / drift / conflict windows to a trailing slice
    (typical: 30, 60, or 90).

    Returned shape (all integer counts unless noted):

        {
          "since_days": int | None,
          "requirements": {total, active, archived, superseded},
          "coverage": {
              "with_impls": int, "with_impls_pct": float,
              "with_test_specs": int, "with_test_specs_pct": float,
          },
          "drift": {"events": int, "files_affected": int, "clean_checks": int,
                    "drift_ratio_pct": float},
          "conflicts": {"caught": int},
          "activity": {"extracted": int, "linked": int},
          "staleness": {"never": int, "over_30d": int, "over_60d": int,
                        "over_90d": int},
        }
    """
    from datetime import datetime, timezone
    from testspec import TestSpecStore

    events = _read_events(store, since_days=since_days)

    # ----- requirements + coverage from store state (not windowed) -----
    all_reqs = store.list_requirements(include_superseded=True)
    superseded = [r for r in all_reqs if r.superseded_at]
    archived = [r for r in all_reqs if r.status == "archived"
                and r.superseded_at is None]
    active = [r for r in all_reqs
              if r.superseded_at is None and r.status != "archived"]

    spec_store = TestSpecStore(store.data_dir)
    with_impls = 0
    with_test_specs = 0
    for req in active:
        if store.get_implementations_for_requirement(req.id):
            with_impls += 1
        if spec_store.get_spec(req.id):
            with_test_specs += 1
    n_active = len(active)

    def _pct(num: int, den: int) -> float:
        return round(100.0 * num / den, 1) if den else 0.0

    # ----- drift / conflicts / activity from events (windowed) -----
    drift_events = [e for e in events if e.get("event") == "drift_detected"]
    files_affected: set[str] = set()
    for e in drift_events:
        if f := e.get("file"):
            files_affected.add(f)
    clean_checks = sum(1 for e in events if e.get("event") == "check_clean")
    total_checks = len(drift_events) + clean_checks

    conflicts_caught = sum(1 for e in events if e.get("event") == "conflict_found")
    extracted = sum(1 for e in events if e.get("event") == "requirement_extracted")
    linked = sum(1 for e in events if e.get("event") == "implementation_linked")

    # ----- staleness from last_referenced (not windowed; current state) -----
    now = datetime.now(timezone.utc)
    never = over30 = over60 = over90 = 0
    for req in active:
        if req.last_referenced is None:
            never += 1
            continue
        try:
            ts = datetime.fromisoformat(req.last_referenced.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            never += 1
            continue
        days = (now - ts).days
        if days > 90:
            over90 += 1
        elif days > 60:
            over60 += 1
        elif days > 30:
            over30 += 1

    return {
        "since_days": since_days,
        "requirements": {
            "total": len(all_reqs),
            "active": n_active,
            "archived": len(archived),
            "superseded": len(superseded),
        },
        "coverage": {
            "with_impls": with_impls,
            "with_impls_pct": _pct(with_impls, n_active),
            "with_test_specs": with_test_specs,
            "with_test_specs_pct": _pct(with_test_specs, n_active),
        },
        "drift": {
            "events": len(drift_events),
            "files_affected": len(files_affected),
            "clean_checks": clean_checks,
            # Drift ratio is over actual checks, not over total events.
            "drift_ratio_pct": _pct(len(drift_events), total_checks),
        },
        "conflicts": {"caught": conflicts_caught},
        "activity": {"extracted": extracted, "linked": linked},
        "staleness": {
            "never": never,
            "over_30d": over30,
            "over_60d": over60,
            "over_90d": over90,
        },
    }


def health_score(store: LoomStore) -> dict[str, Any]:
    """Compute a single 0-100 health score plus its components (M5.3).

    Equal-weighted average of four signals over the active requirement
    set:
        impl_coverage     — fraction of active reqs with linked code
        test_coverage     — fraction of active reqs with a test spec
        freshness         — fraction of active reqs referenced in the
                            last 90 days (never-referenced counts as
                            cold)
        non_drift         — fraction of recent (90-day window) checks
                            that found no drift; 100 if no checks
                            recorded yet (no signal = no degradation)

    Empty store: returns score=0 with all components zero. Useful for
    CI gates: ``loom health-score --json | jq .score`` returns an int.
    """
    from datetime import datetime, timezone

    all_reqs = store.list_requirements(include_superseded=True)
    active = [r for r in all_reqs
              if r.superseded_at is None and r.status != "archived"]
    n_active = len(active)
    if n_active == 0:
        return {
            "score": 0,
            "components": {
                "impl_coverage": 0.0,
                "test_coverage": 0.0,
                "freshness": 0.0,
                "non_drift": 100.0,
            },
            "active_requirements": 0,
        }

    from testspec import TestSpecStore
    spec_store = TestSpecStore(store.data_dir)

    with_impls = sum(
        1 for r in active if store.get_implementations_for_requirement(r.id)
    )
    with_tests = sum(1 for r in active if spec_store.get_spec(r.id))

    now = datetime.now(timezone.utc)
    fresh = 0
    for r in active:
        if not r.last_referenced:
            continue
        try:
            ts = datetime.fromisoformat(r.last_referenced.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if (now - ts).days <= 90:
            fresh += 1

    events = _read_events(store, since_days=90)
    drift = sum(1 for e in events if e.get("event") == "drift_detected")
    clean = sum(1 for e in events if e.get("event") == "check_clean")
    total_checks = drift + clean
    # No checks in window = no signal; treat as 100 so a fresh project
    # isn't penalized for not having run `loom check` yet.
    non_drift_pct = 100.0 if total_checks == 0 else (
        100.0 * clean / total_checks
    )

    impl_pct = 100.0 * with_impls / n_active
    test_pct = 100.0 * with_tests / n_active
    fresh_pct = 100.0 * fresh / n_active

    score = round((impl_pct + test_pct + fresh_pct + non_drift_pct) / 4.0)

    return {
        "score": int(score),
        "components": {
            "impl_coverage": round(impl_pct, 1),
            "test_coverage": round(test_pct, 1),
            "freshness": round(fresh_pct, 1),
            "non_drift": round(non_drift_pct, 1),
        },
        "active_requirements": n_active,
    }


def detect_requirements(
    store: LoomStore, file_path: str, lines: str | None = None, n: int = 3
) -> list[dict[str, Any]]:
    """Semantic search to suggest req_ids that match a file's content.

    Excludes superseded requirements. Returns up to `n` matches as
    [{req_id, value, distance}]. Raises LookupError if file missing.
    """
    from embedding import get_embedding
    content = _read_file_content(file_path, lines)
    vec = get_embedding(content)
    results = store.search_requirements(vec, n=n)
    return [
        {
            "req_id": r["id"],
            "value": r["requirement"].value,
            "distance": r.get("distance"),
        }
        for r in results
        if r["requirement"].superseded_at is None
    ]


def link(
    store: LoomStore,
    file_path: str,
    *,
    lines: str | None = None,
    req_ids: list[str] | tuple[str, ...] = (),
    spec_ids: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Link a file (or line range) to requirements and/or specifications.

    Both `req_ids` and `spec_ids` are taken as-given — if you want
    auto-detection, call `detect_requirements` first and pass the IDs in.

    For each spec linked, the spec's parent requirement is also linked
    (preserving the dual-index pattern that lets `loom trace REQ-id`
    keep working). This is intentional; see KNOWN_ISSUES.md M2.

    Linking a requirement that has active specs is allowed but flagged
    in `warnings` (the CLI's "consider linking to a spec instead" UX).

    Returns:
        {linked: bool, impl_id, file, lines,
         satisfies: [{req_id}], satisfies_specs: [str], warnings: [str]}

    `linked` is False if all provided ids were invalid (or none were
    provided). In that case `impl_id` is `None`, `satisfies` and
    `satisfies_specs` are `[]`, and `warnings` carries diagnostics.

    Raises:
        LookupError: file not found.
    """
    from datetime import datetime, timezone
    from store import Implementation, generate_impl_id, generate_content_hash
    from embedding import get_embedding

    content = _read_file_content(file_path, lines)
    impl_id = generate_impl_id(file_path, lines or "all")
    content_hash = generate_content_hash(content)

    satisfies: list[dict[str, str]] = []
    satisfies_specs: list[str] = []
    warnings: list[str] = []

    # Resolve specs first so we can auto-link parent reqs.
    for sid in spec_ids:
        spec = store.get_specification(sid)
        if not spec:
            warnings.append(f"spec {sid} not found")
            continue
        satisfies_specs.append(sid)
        if not any(s["req_id"] == spec.parent_req for s in satisfies):
            parent = store.get_requirement(spec.parent_req)
            if parent:
                satisfies.append({
                    "req_id": spec.parent_req,
                    "req_version": parent.timestamp,
                })

    # Resolve direct req links.
    for rid in req_ids:
        req = store.get_requirement(rid)
        if not req:
            warnings.append(f"requirement {rid} not found")
            continue

        # Lint: warn if user is linking direct when active specs exist
        # AND no spec was explicitly given.
        if not spec_ids:
            existing_specs = store.get_specifications_for_requirement(rid)
            active = [s for s in existing_specs if not s.superseded_at]
            if active:
                spec_list = ", ".join(f"{s.id} ({s.description[:40]})" for s in active)
                warnings.append(
                    f"{rid} has {len(active)} active spec(s); "
                    f"prefer --spec: {spec_list}"
                )

        if not any(s["req_id"] == rid for s in satisfies):
            satisfies.append({"req_id": rid, "req_version": req.timestamp})

    if not satisfies and not satisfies_specs:
        if not warnings:
            warnings.append("no requirement or spec ids provided")
        return {
            "linked": False,
            "impl_id": None,
            "file": file_path,
            "lines": lines or "all",
            "satisfies": [],
            "satisfies_specs": [],
            "warnings": warnings,
        }

    impl = Implementation(
        id=impl_id,
        file=file_path,
        lines=lines or "all",
        content=content,
        content_hash=content_hash,
        timestamp=datetime.now(timezone.utc).isoformat(),
        satisfies=satisfies,
        satisfies_specs=satisfies_specs or None,
    )
    embedding = get_embedding(content)
    store.add_implementation(impl, embedding)

    # M2.1: linking the file is a meaningful "use" of every linked req.
    for s in satisfies:
        store.touch_requirement(s["req_id"])

    # M5.1: log per-link so `loom metrics` can report linking activity
    # over time. One event per (file, req) pair so the rate matches
    # what the user did.
    for s in satisfies:
        _record_event(
            store, "implementation_linked",
            file=file_path, lines=lines or "all",
            req_id=s["req_id"], impl_id=impl_id,
        )

    return {
        "linked": True,
        "impl_id": impl_id,
        "file": file_path,
        "lines": lines or "all",
        "satisfies": satisfies,
        "satisfies_specs": satisfies_specs,
        "warnings": warnings,
    }


VALID_STATUSES = (
    "pending", "in_progress", "implemented", "verified",
    "superseded", "archived",
)


def sync(
    store: LoomStore,
    output_dir: str,
    public: bool = False,
) -> dict[str, Any]:
    """Regenerate REQUIREMENTS.md and TEST_SPEC.md.

    Returns:
        {requirements_path, test_spec_path, public, private_excluded}

    `public=True` filters out IDs listed in PRIVATE.md (and any test
    specs marked private). `private_excluded` is the count of req IDs
    that were filtered out, even when `public=False` (informational).
    """
    from pathlib import Path
    from docs import generate_requirements_doc, generate_test_spec_doc
    from testspec import TestSpecStore

    out = Path(output_dir)
    spec_store = TestSpecStore(store.data_dir)
    specs = {s.req_id: s for s in spec_store.list_specs()}

    private_ids = spec_store.get_private_ids()
    for spec in specs.values():
        if spec.private:
            private_ids.add(spec.req_id)

    req_path = generate_requirements_doc(store, out, private_ids, public)
    test_path = generate_test_spec_doc(store, out, specs, private_ids, public)

    return {
        "requirements_path": str(req_path),
        "test_spec_path": str(test_path),
        "public": public,
        "private_excluded": len(private_ids),
    }


def supersede(store: LoomStore, req_id: str) -> dict[str, Any]:
    """Mark a requirement as superseded.

    Returns:
        {req_id, value, affected_tests: [test_id]}

    Raises:
        LookupError: req_id not found.
        ValueError: requirement is already superseded.
    """
    from docs import analyze_test_impact
    from testspec import TestSpecStore

    req = store.get_requirement(req_id)
    if req is None:
        raise LookupError(f"Requirement {req_id} not found")
    if req.superseded_at:
        raise ValueError(f"Already superseded at {req.superseded_at}")

    store.supersede_requirement(req_id)

    spec_store = TestSpecStore(store.data_dir)
    specs = {s.req_id: s for s in spec_store.list_specs()}
    affected = list(analyze_test_impact(store, req, specs))

    return {
        "req_id": req_id,
        "value": req.value,
        "affected_tests": affected,
    }


def set_status(store: LoomStore, req_id: str, status: str) -> dict[str, Any]:
    """Set a requirement's implementation status.

    Returns: {req_id, status}.

    Raises:
        ValueError: status not in VALID_STATUSES.
        LookupError: req_id not found.
    """
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status: {status}. Valid: {', '.join(VALID_STATUSES)}"
        )
    if not store.set_requirement_status(req_id, status):
        raise LookupError(f"Requirement {req_id} not found")
    return {"req_id": req_id, "status": status}


def archive(store: LoomStore, req_id: str) -> dict[str, Any]:
    """Mark a requirement as archived (M2.3).

    Distinct from supersede: archived means "no longer relevant"
    (deprecated feature, abandoned plan). Excluded from `list`,
    `query`, and `conflicts` by default. Recoverable via
    `set_status(req_id, 'pending')`.

    Returns: {req_id, status: 'archived'}.

    Raises:
        LookupError: req_id not found.
    """
    if not store.archive_requirement(req_id):
        raise LookupError(f"Requirement {req_id} not found")
    return {"req_id": req_id, "status": "archived"}


def stale(
    store: LoomStore,
    *,
    older_than_days: int | None = None,
    unlinked_only: bool = False,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """List requirements ranked by staleness (M2.2).

    Sort key: `last_referenced` ascending (oldest first; never-touched
    requirements rank coldest, sorted by their original `timestamp`).
    Superseded requirements are always excluded — they're already a
    closed decision. Archived requirements are excluded by default
    (`include_archived=True` to surface them).

    Filters:
        older_than_days — only requirements whose last_referenced is
                          older than this many days, OR which were
                          never referenced and whose creation is older
                          than this. None disables the filter.
        unlinked_only — only requirements with zero linked
                        Implementation rows.

    Result shape (per requirement):
        {id, domain, value, status, last_referenced, timestamp,
         days_since_referenced, linked_files: int}
    """
    from datetime import datetime, timedelta, timezone

    cutoff: datetime | None = None
    if older_than_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    out: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for req in store.list_requirements(include_superseded=False):
        if not include_archived and req.status == "archived":
            continue

        # Compute the "age" used for both sorting and the filter. Prefer
        # last_referenced; fall back to creation timestamp for never-touched
        # requirements (they're the coldest of all by definition).
        ts_str = req.last_referenced or req.timestamp
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if cutoff is not None and ts > cutoff:
            continue

        impls = store.get_implementations_for_requirement(req.id)
        if unlinked_only and impls:
            continue

        delta = now - ts
        out.append({
            "id": req.id,
            "domain": req.domain,
            "value": req.value,
            "status": req.status,
            "last_referenced": req.last_referenced,
            "timestamp": req.timestamp,
            "days_since_referenced": delta.days,
            "linked_files": len(impls),
        })

    out.sort(key=lambda r: r["last_referenced"] or r["timestamp"])
    return out


def refine(
    store: LoomStore,
    req_id: str,
    *,
    elaboration: str,
    acceptance_criteria: list[str] | None = None,
    conversation_context: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Elaborate a requirement.

    `elaboration` is required (the "how to satisfy"). The other fields
    are optional updates.

    Returns:
        {req_id, elaboration, acceptance_criteria, status,
         conversation_context, is_complete}

    Raises:
        LookupError: req_id not found.
        ValueError: elaboration is empty/whitespace, or status invalid.
    """
    if not elaboration or not elaboration.strip():
        raise ValueError("elaboration is required")
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status: {status}. Valid: {', '.join(VALID_STATUSES)}"
        )

    if store.get_requirement(req_id) is None:
        raise LookupError(f"Requirement {req_id} not found")

    updates: dict[str, Any] = {"elaboration": elaboration.strip()}
    if acceptance_criteria:
        updates["acceptance_criteria"] = acceptance_criteria
    if conversation_context:
        updates["conversation_context"] = conversation_context
    if status:
        updates["status"] = status

    updated = store.update_requirement(req_id, updates)
    if updated is None:
        # update_requirement returned None despite get_requirement
        # finding it — treat as a transient store failure rather than
        # a logical "not found" so the caller knows to retry.
        raise RuntimeError(f"Failed to update {req_id}")

    return {
        "req_id": req_id,
        "elaboration": updated.elaboration,
        "acceptance_criteria": updated.acceptance_criteria or [],
        "conversation_context": updated.conversation_context,
        "status": updated.status,
        "is_complete": updated.is_complete(),
    }


# ==================== Specifications ====================

def _generate_spec_id() -> str:
    import uuid
    return f"SPEC-{uuid.uuid4().hex[:8]}"


class DuplicateSpecError(ValueError):
    """Raised when spec_add finds a non-superseded sibling spec and !force.

    Carries the existing sibling specs on ``siblings`` so the CLI can
    show them to the user.
    """
    def __init__(self, message: str, siblings: list[dict[str, Any]]):
        super().__init__(message)
        self.siblings = siblings


def spec_add(
    store: LoomStore,
    req_id: str,
    description: str,
    *,
    acceptance_criteria: list[str] | None = None,
    status: str = "draft",
    source_doc: str | None = None,
    test_file: str = "",
    target_dir: Path | str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Add a specification under a parent requirement.

    Refuses to create a second non-superseded spec under the same
    requirement. Agents generating specs after an edit-confusion have
    been observed to produce duplicates (e.g. SPEC-A at `app/lib/x.dart`
    plus SPEC-B at `lib/x.dart` for one req on a Flutter repo). Silent
    duplicates break decomposition downstream: each spec generates its
    own task queue, and tasks under the wrong-path spec can never reach
    green. We raise ``DuplicateSpecError`` with the existing siblings
    instead; callers can pass ``force=True`` to bypass with a warning.

    If ``test_file`` is provided in pytest "path::Class" form and
    ``target_dir`` is given, writes a failing-placeholder skeleton at
    that path inside target_dir (unless the file already exists). This
    gives downstream `loom_exec` a real grading target before
    decomposition runs (FINDINGS-wild F10).

    Returns:
        {spec_id, parent_req, description, status, acceptance_criteria,
         test_file, test_skeleton_written: bool | None,
         siblings_bypassed: list[{id, description}] | []}

        ``test_skeleton_written`` is:
            - None if no test_file was passed or no target_dir given
            - True if a skeleton was written
            - False if the file already existed (respected — not overwritten)

        ``siblings_bypassed`` is populated only when ``force=True`` was
        used to override an existing spec; empty otherwise.

    Raises:
        LookupError: parent requirement not found.
        DuplicateSpecError: non-superseded sibling exists and force=False.
        ValueError: description is empty, or test_file is malformed.
    """
    from datetime import datetime, timezone
    from store import Specification
    from embedding import get_embedding

    description = (description or "").strip()
    if not description:
        raise ValueError("description is required")
    if store.get_requirement(req_id) is None:
        raise LookupError(f"Requirement {req_id} not found")

    test_file = (test_file or "").strip()
    if test_file and "::" not in test_file:
        raise ValueError(
            f"test_file must be in pytest 'path::Class' form, got {test_file!r}"
        )

    # Sibling-spec check: any non-superseded spec under the same req is
    # a blocker unless the caller explicitly passed force=True.
    sibling_specs = store.list_specifications(req_id=req_id, include_superseded=False)
    siblings_as_dicts = [
        {"id": s.id, "description": s.description, "status": s.status,
         "timestamp": s.timestamp, "test_file": getattr(s, "test_file", "")}
        for s in sibling_specs
    ]
    if sibling_specs and not force:
        ids = ", ".join(s.id for s in sibling_specs)
        raise DuplicateSpecError(
            f"requirement {req_id} already has non-superseded spec(s): {ids} "
            f"(pass force=True to create another, or supersede first)",
            siblings=siblings_as_dicts,
        )

    spec_id = _generate_spec_id()
    spec = Specification(
        id=spec_id,
        parent_req=req_id,
        description=description,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=status,
        acceptance_criteria=acceptance_criteria or None,
        source_doc=source_doc,
        test_file=test_file,
    )

    store.add_specification(spec, get_embedding(description))

    skeleton_written: bool | None = None
    if test_file and target_dir is not None:
        # Read the target's test_runner so the skeleton matches.
        import config as _config
        cfg = _config.load_config(target_dir)
        skeleton_written = _write_test_skeleton(
            Path(target_dir), test_file, spec_id,
            runner_name=cfg.get("test_runner"),
        )

    return {
        "spec_id": spec_id,
        "parent_req": req_id,
        "description": description,
        "status": status,
        "acceptance_criteria": acceptance_criteria or [],
        "test_file": test_file,
        "test_skeleton_written": skeleton_written,
        "siblings_bypassed": siblings_as_dicts if force else [],
    }


def _write_test_skeleton(
    target_dir: Path,
    test_target: str,
    spec_id: str,
    runner_name: str | None = None,
) -> bool:
    """Write a failing-placeholder test skeleton for the target runner.

    Returns True if the file was created, False if it already existed.
    Never overwrites — idempotent.

    ``test_target`` is the "path::Name" form; the path is resolved relative
    to ``target_dir``. The skeleton content depends on ``runner_name``
    (pytest, flutter_test, dart_test, vitest) — each emits a placeholder
    that fails on purpose so an empty skeleton can never mistakenly pass.
    """
    path_part, _, name_part = test_target.partition("::")
    dest = target_dir / path_part
    if dest.exists():
        return False

    import runners as _runners
    runner = _runners.get_runner(runner_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(runner.skeleton(name_part or "Grading"), encoding="utf-8")
    return True


def spec_list(
    store: LoomStore,
    req_id: str | None = None,
    include_superseded: bool = False,
) -> list[dict[str, Any]]:
    """List specifications (optionally filtered by parent req).

    Returns a list of:
        {id, parent_req, description, status, superseded_at,
         acceptance_criteria, source_doc, implementation_count}
    """
    if req_id:
        specs = store.get_specifications_for_requirement(req_id)
    else:
        specs = store.list_specifications(include_superseded=include_superseded)
    out: list[dict[str, Any]] = []
    for s in specs:
        impls = store.get_implementations_for_specification(s.id)
        out.append({
            "id": s.id,
            "parent_req": s.parent_req,
            "description": s.description,
            "status": s.status,
            "superseded_at": s.superseded_at,
            "acceptance_criteria": s.acceptance_criteria or [],
            "source_doc": s.source_doc,
            "implementation_count": len(impls),
        })
    return out


def spec_link(
    store: LoomStore,
    spec_id: str,
    file_path: str,
    lines: str | None = None,
) -> dict[str, Any]:
    """Link code to a specification.

    If an Implementation already exists at this (file, lines), it's linked
    to the spec via `link_implementation_to_spec`. Otherwise a new
    Implementation is created.

    Returns:
        {impl_id, spec_id, parent_req, file, lines, reused: bool,
         already_linked: bool}

    Raises:
        LookupError: spec or file not found.
    """
    from pathlib import Path
    from datetime import datetime, timezone
    from store import Implementation, generate_impl_id, generate_content_hash
    from embedding import get_embedding

    spec = store.get_specification(spec_id)
    if spec is None:
        raise LookupError(f"Specification {spec_id} not found")

    filepath = Path(file_path).resolve()
    if not filepath.exists():
        raise LookupError(f"File not found: {file_path}")

    content = filepath.read_text()
    lines_str = lines or f"1-{len(content.splitlines())}"
    if lines:
        start, end = (int(x) for x in lines.split("-"))
        content = "\n".join(content.splitlines()[start - 1:end])

    impl_id = generate_impl_id(str(filepath), lines_str)
    existing = store.get_implementation(impl_id)

    if existing:
        already_linked = not store.link_implementation_to_spec(impl_id, spec_id)
        return {
            "impl_id": impl_id,
            "spec_id": spec_id,
            "parent_req": spec.parent_req,
            "file": str(filepath),
            "lines": lines_str,
            "reused": True,
            "already_linked": already_linked,
        }

    impl = Implementation(
        id=impl_id,
        file=str(filepath),
        lines=lines_str,
        content=content,
        content_hash=generate_content_hash(content),
        timestamp=datetime.now(timezone.utc).isoformat(),
        satisfies=[{"req_id": spec.parent_req, "req_version": "current"}],
        satisfies_specs=[spec_id],
    )
    store.add_implementation(impl, get_embedding(content))

    return {
        "impl_id": impl_id,
        "spec_id": spec_id,
        "parent_req": spec.parent_req,
        "file": str(filepath),
        "lines": lines_str,
        "reused": False,
        "already_linked": False,
    }


# ==================== Patterns ====================

def _generate_pattern_id() -> str:
    import uuid
    return f"PAT-{uuid.uuid4().hex[:8]}"


def pattern_add(
    store: LoomStore,
    name: str,
    description: str,
    applies_to: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Add a shared design pattern.

    Returns:
        {pattern_id, name, description, applies_to, missing_reqs}

    `missing_reqs` lists any req_ids from `applies_to` that don't exist
    (pattern is still created with them in its applies_to list — that
    matches the pre-existing CLI behavior).

    Raises:
        ValueError: name or description empty.
    """
    from datetime import datetime, timezone
    from store import Pattern
    from embedding import get_embedding

    name = (name or "").strip()
    description = (description or "").strip()
    if not name:
        raise ValueError("name is required")
    if not description:
        raise ValueError("description is required")

    missing_reqs = [
        rid for rid in applies_to if store.get_requirement(rid) is None
    ]

    pattern_id = _generate_pattern_id()
    pattern = Pattern(
        id=pattern_id,
        name=name,
        description=description,
        timestamp=datetime.now(timezone.utc).isoformat(),
        applies_to=list(applies_to),
    )
    store.add_pattern(pattern, get_embedding(f"{name}: {description}"))

    return {
        "pattern_id": pattern_id,
        "name": name,
        "description": description,
        "applies_to": list(applies_to),
        "missing_reqs": missing_reqs,
    }


def pattern_list(
    store: LoomStore, include_deprecated: bool = False
) -> list[dict[str, Any]]:
    """List patterns.

    Returns a list of:
        {id, name, description, status, applies_to, implementation_count}
    """
    patterns = store.list_patterns(include_deprecated=include_deprecated)
    out: list[dict[str, Any]] = []
    for p in patterns:
        impls = store.get_implementations_for_pattern(p.id)
        out.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "status": p.status,
            "applies_to": list(p.applies_to) if p.applies_to else [],
            "implementation_count": len(impls),
        })
    return out


def pattern_apply(
    store: LoomStore, pattern_id: str, req_ids: list[str] | tuple[str, ...]
) -> dict[str, Any]:
    """Attach a pattern to additional requirements.

    Returns:
        {pattern_id, added: [req_id], skipped: [req_id]}

    `skipped` covers both "already attached" and "req not found" — the
    underlying `add_requirement_to_pattern` returns False for both and
    doesn't distinguish. Matches pre-existing CLI behavior.

    Raises:
        LookupError: pattern not found.
    """
    if store.get_pattern(pattern_id) is None:
        raise LookupError(f"Pattern {pattern_id} not found")

    added: list[str] = []
    skipped: list[str] = []
    for rid in req_ids:
        if store.add_requirement_to_pattern(pattern_id, rid):
            added.append(rid)
        else:
            skipped.append(rid)
    return {"pattern_id": pattern_id, "added": added, "skipped": skipped}


# ==================== Test specs ====================

def test_add(
    store: LoomStore,
    req_id: str,
    *,
    description: str | None = None,
    steps: list[str] | tuple[str, ...] = (),
    expected: str | None = None,
    automated: bool = False,
    test_file: str | None = None,
    private: bool = False,
) -> dict[str, Any]:
    """Add or update a TestSpec for a requirement.

    Fields default to the existing TestSpec's values if one exists and the
    corresponding arg is None/empty. That matches cmd_test_add's
    merge-with-existing semantics.

    Returns the full TestSpec as a dict.

    Raises:
        LookupError: req_id not found.
        ValueError: no description provided and no existing spec to
                    inherit from.
    """
    from testspec import TestSpec, TestSpecStore

    if store.get_requirement(req_id) is None:
        raise LookupError(f"Requirement {req_id} not found")

    spec_store = TestSpecStore(store.data_dir)
    existing = spec_store.get_spec(req_id)

    final_description = description if description else (
        existing.description if existing else ""
    )
    if not final_description:
        raise ValueError("description is required for new test specs")

    spec = TestSpec(
        req_id=req_id,
        description=final_description,
        steps=list(steps) if steps else (existing.steps if existing else []),
        expected=expected if expected is not None else (
            existing.expected if existing else ""
        ),
        automated=automated if automated else (
            existing.automated if existing else False
        ),
        test_file=test_file if test_file is not None else (
            existing.test_file if existing else None
        ),
        private=private if private else (existing.private if existing else False),
    )
    spec_store.add_spec(spec)
    return spec.to_dict()


def test_verify(store: LoomStore, req_id: str) -> dict[str, Any]:
    """Mark a test as verified. Returns {req_id, last_verified}.

    Raises:
        LookupError: no test spec for this req.
    """
    from testspec import TestSpecStore

    spec_store = TestSpecStore(store.data_dir)
    if not spec_store.mark_verified(req_id):
        raise LookupError(f"No test spec found for {req_id}")
    spec = spec_store.get_spec(req_id)
    return {"req_id": req_id, "last_verified": spec.last_verified}


def test_list(
    store: LoomStore, include_private: bool = True
) -> list[dict[str, Any]]:
    """List test specs as dicts."""
    from testspec import TestSpecStore
    spec_store = TestSpecStore(store.data_dir)
    return [s.to_dict() for s in spec_store.list_specs(include_private=include_private)]


def test_generate(store: LoomStore, force: bool = False) -> dict[str, Any]:
    """Auto-generate TestSpecs from requirements' acceptance criteria.

    Skips:
        - Requirements with no acceptance_criteria (counted in no_criteria).
        - Requirements that already have a TestSpec, unless force=True.

    Returns:
        {generated: [req_id], skipped: [req_id], no_criteria: [req_id]}
    """
    from testspec import TestSpec, TestSpecStore

    spec_store = TestSpecStore(store.data_dir)
    generated: list[str] = []
    skipped: list[str] = []
    no_criteria: list[str] = []

    for req in store.list_requirements():
        ac = req.acceptance_criteria or []
        # Treat the ChromaDB placeholder as "no real criteria".
        real_criteria = [c for c in ac if c and c != "TBD"]
        if not real_criteria:
            no_criteria.append(req.id)
            continue
        if spec_store.get_spec(req.id) is not None and not force:
            skipped.append(req.id)
            continue

        steps = [f"Verify: {c}" for c in real_criteria]
        desc = (
            f"Test for: {req.value[:100]}..."
            if len(req.value) > 100
            else f"Test for: {req.value}"
        )
        spec = TestSpec(
            req_id=req.id,
            description=desc,
            steps=steps,
            expected="All acceptance criteria pass",
            automated=False,
            test_file=None,
            private=False,
        )
        spec_store.add_spec(spec)
        store.link_test_spec(req.id, f"TEST-{req.id}")
        generated.append(req.id)

    return {
        "generated": generated,
        "skipped": skipped,
        "no_criteria": no_criteria,
    }


# ==================== Misc ====================

def incomplete(store: LoomStore) -> list[dict[str, Any]]:
    """List requirements that are missing elaboration or acceptance criteria.

    Returns a list of:
        {id, domain, value, missing: [str]}
    """
    out: list[dict[str, Any]] = []
    for req in store.get_incomplete_requirements():
        missing: list[str] = []
        if not req.elaboration:
            missing.append("elaboration")
        # ["TBD"] placeholder also counts as missing.
        real_crit = [c for c in (req.acceptance_criteria or []) if c and c != "TBD"]
        if not real_crit:
            missing.append("acceptance criteria")
        out.append({
            "id": req.id,
            "domain": req.domain,
            "value": req.value,
            "missing": missing,
        })
    return out


def gaps(store: LoomStore, types: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    """Surface outstanding gaps in a Loom project.

    Each returned dict has the uniform shape:
        {
          "type": str,             # one of: missing_criteria, missing_elaboration, orphan_impl
          "entity_id": str,        # REQ-xxx or IMPL-xxx
          "description": str,      # short human-readable
          "blocks": list[str],     # entity_ids this gap blocks (may be empty list)
          "suggested_action": str  # a single runnable command, e.g., "loom refine REQ-abc"
        }

    Gap types implemented:
    - missing_criteria: active requirement with empty acceptance_criteria
    - missing_elaboration: active requirement with empty elaboration
    - orphan_impl: implementation whose every satisfies[*].req_id either
      doesn't exist or is superseded

    Sort by priority (higher first), ties by entity_id ascending:
        priority 3: missing_criteria
        priority 5: missing_elaboration
        priority 6: orphan_impl

    Args:
        store: LoomStore instance
        types: if provided, only return gaps whose type is in the list
        limit: if provided, cap the returned list at limit entries (after sorting)

    Returns:
        list of gap dicts, sorted by priority and entity_id
    """
    gaps_list: list[dict[str, Any]] = []

    # Detect missing_criteria and missing_elaboration (only from non-superseded reqs)
    for req in store.list_requirements(include_superseded=False):
        # Check for missing_criteria
        real_crit = [c for c in (req.acceptance_criteria or []) if c and c != "TBD"]
        if not real_crit:
            gaps_list.append({
                "type": "missing_criteria",
                "entity_id": req.id,
                "description": f"Requirement {req.id} has no acceptance criteria",
                "blocks": [],
                "suggested_action": f"loom refine {req.id}",
                "_priority": 3,  # for sorting
            })

        # Check for missing_elaboration
        if not req.elaboration:
            gaps_list.append({
                "type": "missing_elaboration",
                "entity_id": req.id,
                "description": f"Requirement {req.id} has no elaboration",
                "blocks": [],
                "suggested_action": f"loom refine {req.id}",
                "_priority": 5,  # for sorting
            })

    # Detect orphan_impl
    result = store.implementations.get(include=["metadatas"])
    for meta in result.get("metadatas", []):
        impl_id = meta.get("id")
        if not impl_id:
            continue

        # Parse satisfies list
        import json as _json
        satisfies = _json.loads(meta.get("satisfies", "[]"))
        req_ids = [s.get("req_id") for s in satisfies if s.get("req_id")]

        # Check if this impl is orphan: every req_id is either missing or superseded
        is_orphan = True
        if req_ids:
            for req_id in req_ids:
                req = store.get_requirement(req_id)
                # If requirement exists and is NOT superseded, impl is not orphan
                if req and not req.superseded_at:
                    is_orphan = False
                    break
        else:
            # No satisfies entries means it's orphan-like
            is_orphan = True

        if is_orphan:
            file_str = meta.get("file", "unknown")
            lines_str = meta.get("lines", "?")
            gaps_list.append({
                "type": "orphan_impl",
                "entity_id": impl_id,
                "description": f"Implementation {impl_id} ({file_str}:{lines_str}) is orphaned",
                "blocks": [],
                "suggested_action": f"loom trace {file_str}",
                "_priority": 6,  # for sorting
            })

    # Filter by types if provided
    if types is not None:
        gaps_list = [g for g in gaps_list if g["type"] in types]

    # Sort by priority (ascending = higher priority first) then entity_id (ascending)
    gaps_list.sort(key=lambda g: (g["_priority"], g["entity_id"]))

    # Remove the internal _priority field
    for gap in gaps_list:
        del gap["_priority"]

    # Apply limit if provided
    if limit is not None:
        gaps_list = gaps_list[:limit]

    return gaps_list


def gaps(store: LoomStore, types: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    """Surface outstanding gaps in a Loom project.

    Each returned dict has the uniform shape:
        {
          "type": str,             # one of: missing_criteria, missing_elaboration, orphan_impl
          "entity_id": str,        # REQ-xxx or IMPL-xxx
          "description": str,      # short human-readable
          "blocks": list[str],     # entity_ids this gap blocks (may be empty list)
          "suggested_action": str  # a single runnable command, e.g., "loom refine REQ-abc"
        }

    Gap types implemented:
    - missing_criteria: active requirement with empty acceptance_criteria
    - missing_elaboration: active requirement with empty elaboration
    - orphan_impl: implementation whose every satisfies[*].req_id either
      doesn't exist or is superseded

    Sort by priority (higher first), ties by entity_id ascending:
        priority 3: missing_criteria
        priority 5: missing_elaboration
        priority 6: orphan_impl

    Args:
        store: LoomStore instance
        types: if provided, only return gaps whose type is in the list
        limit: if provided, cap the returned list at limit entries (after sorting)

    Returns:
        list of gap dicts, sorted by priority and entity_id
    """
    import json as _json
    from datetime import datetime, timezone

    gaps_list: list[dict[str, Any]] = []

    # Detect missing_criteria and missing_elaboration (only from non-superseded reqs)
    for req in store.list_requirements(include_superseded=False):
        # Check for missing_criteria
        real_crit = [c for c in (req.acceptance_criteria or []) if c and c != "TBD"]
        if not real_crit:
            gaps_list.append({
                "type": "missing_criteria",
                "entity_id": req.id,
                "description": f"Requirement {req.id} has no acceptance criteria",
                "blocks": [],
                "suggested_action": f"loom refine {req.id}",
                "_priority": 3,  # for sorting
            })

        # Check for missing_elaboration
        if not req.elaboration:
            gaps_list.append({
                "type": "missing_elaboration",
                "entity_id": req.id,
                "description": f"Requirement {req.id} has no elaboration",
                "blocks": [],
                "suggested_action": f"loom refine {req.id}",
                "_priority": 5,  # for sorting
            })

    # Detect orphan_impl
    result = store.implementations.get(include=["metadatas"])
    for meta in result.get("metadatas", []):
        impl_id = meta.get("id")
        if not impl_id:
            continue

        # Parse satisfies list
        satisfies = _json.loads(meta.get("satisfies", "[]"))
        req_ids = [s.get("req_id") for s in satisfies if s.get("req_id")]

        # Check if this impl is orphan: every req_id is either missing or superseded
        is_orphan = True
        if req_ids:
            for req_id in req_ids:
                req = store.get_requirement(req_id)
                # If requirement exists and is NOT superseded, impl is not orphan
                if req and not req.superseded_at:
                    is_orphan = False
                    break
        else:
            # No satisfies entries means it's orphan-like
            is_orphan = True

        if is_orphan:
            file_str = meta.get("file", "unknown")
            lines_str = meta.get("lines", "?")
            gaps_list.append({
                "type": "orphan_impl",
                "entity_id": impl_id,
                "description": f"Implementation {impl_id} ({file_str}:{lines_str}) is orphaned",
                "blocks": [],
                "suggested_action": f"loom trace {file_str}",
                "_priority": 6,  # for sorting
            })

    # Filter by types if provided
    if types is not None:
        gaps_list = [g for g in gaps_list if g["type"] in types]

    # Sort by priority (ascending = higher priority first) then entity_id (ascending)
    gaps_list.sort(key=lambda g: (g["_priority"], g["entity_id"]))

    # Remove the internal _priority field
    for gap in gaps_list:
        del gap["_priority"]

    # Apply limit if provided
    if limit is not None:
        gaps_list = gaps_list[:limit]

    return gaps_list


def gaps(store: LoomStore, types: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    """Surface outstanding gaps in a Loom project.

    Each returned dict has the uniform shape:
        {
          "type": str,             # one of: missing_criteria, missing_elaboration, orphan_impl, drift
          "entity_id": str,        # REQ-xxx or IMPL-xxx
          "description": str,      # short human-readable
          "blocks": list[str],     # entity_ids this gap blocks (may be empty list)
          "suggested_action": str  # a single runnable command, e.g., "loom refine REQ-abc"
        }

    Gap types implemented:
    - missing_criteria: active requirement with empty acceptance_criteria
    - missing_elaboration: active requirement with empty elaboration
    - orphan_impl: implementation whose every satisfies[*].req_id either
      doesn't exist or is superseded
    - drift: a superseded requirement that still has at least one linked
      implementation. The implementation may also point at live reqs
      (it need NOT be an orphan_impl); what matters is that the
      superseded req's id appears in some Implementation's `satisfies`
      list.

    Sort by priority (higher first), ties by entity_id ascending:
        priority 2: drift
        priority 3: missing_criteria
        priority 5: missing_elaboration
        priority 6: orphan_impl

    Args:
        store: LoomStore instance
        types: if provided, only return gaps whose type is in the list
        limit: if provided, cap the returned list at limit entries (after sorting)

    Returns:
        list of gap dicts, sorted by priority and entity_id
    """
    import json as _json
    from datetime import datetime, timezone

    gaps_list: list[dict[str, Any]] = []

    # Detect missing_criteria and missing_elaboration (only from non-superseded reqs)
    for req in store.list_requirements(include_superseded=False):
        # Check for missing_criteria
        real_crit = [c for c in (req.acceptance_criteria or []) if c and c != "TBD"]
        if not real_crit:
            gaps_list.append({
                "type": "missing_criteria",
                "entity_id": req.id,
                "description": f"Requirement {req.id} has no acceptance criteria",
                "blocks": [],
                "suggested_action": f"loom refine {req.id}",
                "_priority": 3,  # for sorting
            })

        # Check for missing_elaboration
        if not req.elaboration:
            gaps_list.append({
                "type": "missing_elaboration",
                "entity_id": req.id,
                "description": f"Requirement {req.id} has no elaboration",
                "blocks": [],
                "suggested_action": f"loom refine {req.id}",
                "_priority": 5,  # for sorting
            })

    # Detect orphan_impl
    result = store.implementations.get(include=["metadatas"])
    for meta in result.get("metadatas", []):
        impl_id = meta.get("id")
        if not impl_id:
            continue

        # Parse satisfies list
        satisfies = _json.loads(meta.get("satisfies", "[]"))
        req_ids = [s.get("req_id") for s in satisfies if s.get("req_id")]

        # Check if this impl is orphan: every req_id is either missing or superseded
        is_orphan = True
        if req_ids:
            for req_id in req_ids:
                req = store.get_requirement(req_id)
                # If requirement exists and is NOT superseded, impl is not orphan
                if req and not req.superseded_at:
                    is_orphan = False
                    break
        else:
            # No satisfies entries means it's orphan-like
            is_orphan = True

        if is_orphan:
            file_str = meta.get("file", "unknown")
            lines_str = meta.get("lines", "?")
            gaps_list.append({
                "type": "orphan_impl",
                "entity_id": impl_id,
                "description": f"Implementation {impl_id} ({file_str}:{lines_str}) is orphaned",
                "blocks": [],
                "suggested_action": f"loom trace {file_str}",
                "_priority": 6,  # for sorting
            })

    # Detect drift: superseded requirements that still have linked implementations
    all_reqs = store.list_requirements(include_superseded=True)
    superseded_reqs = [r for r in all_reqs if r.superseded_at]
    
    # Build a map of superseded req_id -> list of impl_ids that link to it
    drift_map: dict[str, list[str]] = {}
    for req in superseded_reqs:
        impls = store.get_implementations_for_requirement(req.id)
        if impls:
            drift_map[req.id] = [i.id for i in impls]

    # Emit exactly ONE drift gap per superseded req (dedupe by req.id)
    for req in superseded_reqs:
        if req.id in drift_map:
            impl_ids = drift_map[req.id]
            gaps_list.append({
                "type": "drift",
                "entity_id": req.id,
                "description": f"REQ-{req.id} is superseded but still has linked implementations",
                "blocks": impl_ids,
                "suggested_action": f"loom link --req {req.id}",
                "_priority": 2,  # for sorting
            })

    # Filter by types if provided
    if types is not None:
        gaps_list = [g for g in gaps_list if g["type"] in types]

    # Sort by priority (ascending = higher priority first) then entity_id (ascending)
    gaps_list.sort(key=lambda g: (g["_priority"], g["entity_id"]))

    # Remove the internal _priority field
    for gap in gaps_list:
        del gap["_priority"]

    # Apply limit if provided
    if limit is not None:
        gaps_list = gaps_list[:limit]

    return gaps_list


# ==================== Tasks ====================
#
# An atomic, executor-ready unit of work. See src/store.py::Task for the
# schema. Tasks flow through: pending -> claimed -> complete | rejected.
# Rejected tasks with escalate=True become escalated (for operator review).


def task_add(
    store: LoomStore,
    *,
    parent_spec: str,
    title: str,
    files_to_modify: list[str],
    test_to_write: str,
    context_reqs: list[str] | None = None,
    context_specs: list[str] | None = None,
    context_patterns: list[str] | None = None,
    context_sidecars: list[str] | None = None,
    context_files: list[str] | None = None,
    size_budget_files: int = 2,
    size_budget_loc: int = 80,
    depends_on: list[str] | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Create a new Task.

    Args:
        parent_spec: SPEC-xxx this task satisfies. Must exist in the store.
        title: one-line human description.
        files_to_modify: files the executor may edit.
        test_to_write: grading test target, e.g. 'tests/test_x.py::TestY'.
        context_*: pointer lists for on-demand bundle assembly.
        size_budget_*: atomicity bounds the executor checks.
        depends_on: other TASK-xxx that must complete first (DAG).

    Returns: task dict shape (see task_get).

    Raises:
        LookupError: parent_spec does not exist.
        ValueError: title or files_to_modify empty, or depends_on references
                    a task that doesn't exist.
    """
    from datetime import datetime, timezone
    from store import Task, generate_task_id
    from embedding import get_embedding

    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    if not files_to_modify:
        raise ValueError("files_to_modify must be non-empty")
    if store.get_specification(parent_spec) is None:
        raise LookupError(f"Specification {parent_spec} not found")
    if depends_on:
        for dep in depends_on:
            if store.get_task(dep) is None:
                raise ValueError(f"depends_on references unknown task: {dep}")

    task_id = generate_task_id(parent_spec, title)
    task = Task(
        id=task_id,
        parent_spec=parent_spec,
        title=title,
        timestamp=datetime.now(timezone.utc).isoformat(),
        files_to_modify=list(files_to_modify),
        test_to_write=test_to_write,
        context_reqs=list(context_reqs) if context_reqs else None,
        context_specs=list(context_specs) if context_specs else None,
        context_patterns=list(context_patterns) if context_patterns else None,
        context_sidecars=list(context_sidecars) if context_sidecars else None,
        context_files=list(context_files) if context_files else None,
        size_budget_files=size_budget_files,
        size_budget_loc=size_budget_loc,
        depends_on=list(depends_on) if depends_on else None,
        created_by=created_by,
    )
    store.add_task(task, get_embedding(f"{title}\n{parent_spec}"))
    return _task_to_dict(task)


def _task_to_dict(task) -> dict[str, Any]:
    """Stable JSON-serializable shape for a Task."""
    return {
        "id": task.id,
        "parent_spec": task.parent_spec,
        "title": task.title,
        "timestamp": task.timestamp,
        "files_to_modify": task.files_to_modify,
        "test_to_write": task.test_to_write,
        "context_reqs": task.context_reqs or [],
        "context_specs": task.context_specs or [],
        "context_patterns": task.context_patterns or [],
        "context_sidecars": task.context_sidecars or [],
        "context_files": task.context_files or [],
        "size_budget": {
            "files": task.size_budget_files,
            "loc": task.size_budget_loc,
        },
        "depends_on": task.depends_on or [],
        "status": task.status,
        "claimed_by": task.claimed_by,
        "claimed_at": task.claimed_at,
        "completed_at": task.completed_at,
        "rejection_reason": task.rejection_reason,
        "escalation_count": task.escalation_count,
        "created_by": task.created_by,
        "updated_at": task.updated_at,
    }


def task_list(
    store: LoomStore,
    *,
    status: str | None = None,
    parent_spec: str | None = None,
    claimed_by: str | None = None,
    ready_only: bool = False,
) -> list[dict[str, Any]]:
    """List tasks. Filters stack.

    ready_only: only pending tasks whose depends_on are all complete.
    """
    if ready_only:
        tasks = store.list_ready_tasks()
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        if parent_spec is not None:
            tasks = [t for t in tasks if t.parent_spec == parent_spec]
        if claimed_by is not None:
            tasks = [t for t in tasks if t.claimed_by == claimed_by]
    else:
        tasks = store.list_tasks(status=status, parent_spec=parent_spec, claimed_by=claimed_by)
    return [_task_to_dict(t) for t in tasks]


def task_get(store: LoomStore, task_id: str) -> dict[str, Any]:
    """Get a task's full data. Raises LookupError if not found."""
    task = store.get_task(task_id)
    if task is None:
        raise LookupError(f"Task {task_id} not found")
    return _task_to_dict(task)


def task_claim(store: LoomStore, task_id: str, claimed_by: str) -> dict[str, Any]:
    """Transition pending -> claimed. Stamps claimed_at and claimed_by.

    Raises:
        LookupError: task not found.
        ValueError: task is not in 'pending' status.
    """
    from datetime import datetime, timezone

    task = store.get_task(task_id)
    if task is None:
        raise LookupError(f"Task {task_id} not found")
    if task.status != "pending":
        raise ValueError(
            f"Task {task_id} cannot be claimed from status={task.status} (must be pending)"
        )
    now = datetime.now(timezone.utc).isoformat()
    store.update_task(task_id, {
        "status": "claimed",
        "claimed_by": claimed_by,
        "claimed_at": now,
    })
    return _task_to_dict(store.get_task(task_id))


def task_release(store: LoomStore, task_id: str) -> dict[str, Any]:
    """Transition claimed -> pending (executor gave up cleanly).

    Clears claimed_by/claimed_at. Does NOT count as an escalation.
    """
    task = store.get_task(task_id)
    if task is None:
        raise LookupError(f"Task {task_id} not found")
    if task.status != "claimed":
        raise ValueError(
            f"Task {task_id} cannot be released from status={task.status} (must be claimed)"
        )
    store.update_task(task_id, {
        "status": "pending",
        "claimed_by": None,
        "claimed_at": None,
    })
    return _task_to_dict(store.get_task(task_id))


def task_complete(
    store: LoomStore,
    task_id: str,
    impl_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Transition claimed -> complete. Stamps completed_at.

    impl_ids are returned in the result for audit but not stored on the task
    (implementations link to specs independently).
    """
    from datetime import datetime, timezone

    task = store.get_task(task_id)
    if task is None:
        raise LookupError(f"Task {task_id} not found")
    if task.status != "claimed":
        raise ValueError(
            f"Task {task_id} cannot be completed from status={task.status} (must be claimed)"
        )
    store.update_task(task_id, {
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    result = _task_to_dict(store.get_task(task_id))
    result["linked_impls"] = list(impl_ids) if impl_ids else []
    return result


def task_reject(
    store: LoomStore,
    task_id: str,
    reason: str,
    *,
    escalate: bool = False,
) -> dict[str, Any]:
    """Transition claimed -> rejected (or escalated).

    escalate=True sets status=escalated and increments escalation_count.
    Use this when the failure needs human / larger-model attention.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("reason is required")
    task = store.get_task(task_id)
    if task is None:
        raise LookupError(f"Task {task_id} not found")
    if task.status != "claimed":
        raise ValueError(
            f"Task {task_id} cannot be rejected from status={task.status} (must be claimed)"
        )
    updates: dict[str, Any] = {"rejection_reason": reason}
    if escalate:
        updates["status"] = "escalated"
        updates["escalation_count"] = task.escalation_count + 1
    else:
        updates["status"] = "rejected"
    store.update_task(task_id, updates)
    return _task_to_dict(store.get_task(task_id))


def task_build_prompt(
    store: LoomStore,
    task_id: str,
    target_dir: Path | str | None = None,
    runner: "Any | None" = None,
) -> str:
    """Assemble the executor prompt on demand from current store state.

    Mirrors the enhanced-condition bundle used by benchmarks/ollama_gaps*.py:
      - task scope (title, files, grading test, size budget)
      - linked requirements (value + rationale + elaboration + criteria)
      - linked specifications (description + criteria)
      - linked patterns (name + description)
      - sidecar file contents (inlined)
      - context files (inlined in full)
      - output contract + stop tokens

    Sidecar and context-file paths are resolved relative to ``target_dir``
    if given; otherwise they fall back to absolute paths or paths relative
    to the current working directory.

    If ``runner`` (a ``runners.Runner``) is passed, the output contract is
    tailored to that runner's language + apply_mode — Python append-mode
    says "don't repeat unchanged code"; Dart/TS replace-mode says "reply
    with the entire new file content" since redefining classes isn't
    valid. When ``runner`` is None, falls back to the Python-append prompt
    (legacy behavior).

    Raises LookupError if the task is missing. Referenced reqs/specs/patterns
    that don't exist are silently skipped (graceful degradation).
    """
    from pathlib import Path as _Path

    # Default to pytest/Python if no runner provided (legacy callers).
    if runner is None:
        import runners as _runners
        runner = _runners.get_runner("pytest")

    td = _Path(target_dir) if target_dir is not None else None

    def _resolve(path_str: str) -> _Path:
        p = _Path(path_str)
        if p.is_absolute() or td is None:
            return p
        return td / p

    task = store.get_task(task_id)
    if task is None:
        raise LookupError(f"Task {task_id} not found")

    parts: list[str] = []
    parts.append(f"# Task {task.id}: {task.title}\n")
    parts.append(f"Parent specification: {task.parent_spec}")
    parts.append(f"Files to modify: {', '.join(task.files_to_modify)}")
    parts.append(f"Grading test: {task.test_to_write}")
    parts.append(
        f"Size budget: <= {task.size_budget_files} files, "
        f"<= {task.size_budget_loc} LoC\n"
    )

    if task.context_reqs:
        parts.append("## Requirements\n")
        for rid in task.context_reqs:
            req = store.get_requirement(rid)
            if req is None:
                continue
            parts.append(f"### {req.id} [{req.domain}]")
            parts.append(f"Value: {req.value}")
            if req.rationale:
                parts.append(f"Rationale: {req.rationale}")
            if req.elaboration:
                parts.append(f"Elaboration: {req.elaboration}")
            ac = req.acceptance_criteria or []
            if ac and ac != ["TBD"]:
                parts.append("Acceptance criteria:")
                for c in ac:
                    parts.append(f"  - {c}")
            parts.append("")

    if task.context_specs:
        parts.append("## Specifications\n")
        for sid in task.context_specs:
            spec = store.get_specification(sid)
            if spec is None:
                continue
            parts.append(f"### {spec.id} (parent: {spec.parent_req}, status: {spec.status})")
            parts.append(spec.description)
            ac = spec.acceptance_criteria or []
            if ac and ac != ["TBD"]:
                parts.append("Criteria:")
                for c in ac:
                    parts.append(f"  - {c}")
            parts.append("")

    if task.context_patterns:
        parts.append("## Patterns\n")
        for pid in task.context_patterns:
            pat = store.get_pattern(pid)
            if pat is None:
                continue
            parts.append(f"### {pat.id} -- {pat.name}")
            parts.append(pat.description)
            parts.append("")

    if task.context_sidecars:
        parts.append("## Sidecar notes\n")
        for path_str in task.context_sidecars:
            p = _resolve(path_str)
            if not p.exists():
                continue
            parts.append(f"### {path_str}")
            parts.append(p.read_text(encoding="utf-8"))
            parts.append("")

    if task.context_files:
        parts.append("## Source context\n")
        for path_str in task.context_files:
            p = _resolve(path_str)
            if not p.exists():
                continue
            parts.append(f"### {path_str}")
            parts.append("```")
            parts.append(p.read_text(encoding="utf-8"))
            parts.append("```")
            parts.append("")

    # Output contract depends on apply_mode. Append-mode (Python) is small
    # diffs; replace-mode (Dart/TS) is whole-file, must repeat unchanged code.
    if runner.apply_mode == "replace":
        first_file = task.files_to_modify[0] if task.files_to_modify else "<target>"
        contract = (
            f"## Output contract\n"
            f"Reply with ONE {runner.language} code block "
            f"(```{runner.fence} ... ```) containing the **entire new file "
            f"content** for `{first_file}`. You MUST include all existing "
            f"code you want to keep — this file will be OVERWRITTEN with "
            f"your output. Do not include prose outside the code block.\n\n"
            f"If the task is too large or mixes concerns, reply with "
            f"`TASK_REJECT: <reason>` and stop.\n"
            f"If you need information not provided, reply with "
            f"`NEED_CONTEXT: <what>` and stop.\n"
            f"When complete, begin your final message (after the code block) "
            f"with `DONE: <one-line summary>`."
        )
    else:
        contract = (
            f"## Output contract\n"
            f"Reply with ONE {runner.language} code block "
            f"(```{runner.fence} ... ```) containing your changes. The model "
            f"output is APPENDED to the end of the target file, so redefine "
            f"functions/methods as needed (last definition wins). Do not "
            f"include unchanged code from the files above. Do not include "
            f"prose outside the code block.\n\n"
            f"If the task is too large or mixes concerns, reply with "
            f"`TASK_REJECT: <reason>` and stop.\n"
            f"If you need information not provided, reply with "
            f"`NEED_CONTEXT: <what>` and stop.\n"
            f"When complete, begin your final message (after the code block) "
            f"with `DONE: <one-line summary>`."
        )
    parts.append(contract)

    return "\n".join(parts)


# ==================== Decomposer ====================
#
# Turns a specification + its Loom context into a proposed Task list.
# Opus-class models are the default for the reasoning; a 32B local model
# (qwen2.5-coder:32b) is the fallback ceiling.
#
# Model selection:
#   - LOOM_DECOMPOSER_MODEL env var overrides everything.
#     Format: "anthropic:<model>" or "ollama:<model>".
#   - Else if ANTHROPIC_API_KEY is set: "anthropic:claude-opus-4-7".
#   - Else: "ollama:qwen2.5-coder:32b".
#
# The command-level --model flag overrides the env default.


def _default_decomposer_model() -> str:
    import os
    override = os.environ.get("LOOM_DECOMPOSER_MODEL")
    if override:
        return override
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic:claude-opus-4-7"
    return "ollama:qwen2.5-coder:32b"


def _call_decomposer_llm(model: str, prompt: str, timeout: int = 900) -> dict:
    """Dispatch to Ollama or Anthropic based on the model prefix.

    Returns {content, elapsed_s, input_tokens, output_tokens}. Raises
    RuntimeError on transport failure.
    """
    import json as _json
    import os as _os
    import time as _time
    import urllib.request as _urlreq

    if ":" not in model:
        raise ValueError(
            f"model {model!r} must be 'anthropic:<name>' or 'ollama:<name>'"
        )
    provider, name = model.split(":", 1)
    t0 = _time.perf_counter()

    if provider == "ollama":
        url = _os.environ.get("OLLAMA_URL", "http://localhost:11434")
        payload = _json.dumps({
            "model": name,
            "stream": False,
            "think": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.0, "num_predict": 8000},
        }).encode()
        req = _urlreq.Request(
            f"{url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with _urlreq.urlopen(req, timeout=timeout) as resp:
                body = _json.loads(resp.read().decode())
        except Exception as e:
            raise RuntimeError(f"Ollama call failed: {e}") from e
        msg = body.get("message", {}) or {}
        return {
            "content": msg.get("content", ""),
            "elapsed_s": round(_time.perf_counter() - t0, 2),
            "input_tokens": body.get("prompt_eval_count", 0),
            "output_tokens": body.get("eval_count", 0),
        }

    if provider == "anthropic":
        api_key = _os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY env var required for anthropic provider")
        payload = _json.dumps({
            "model": name,
            "max_tokens": 8000,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = _urlreq.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            with _urlreq.urlopen(req, timeout=timeout) as resp:
                body = _json.loads(resp.read().decode())
        except Exception as e:
            raise RuntimeError(f"Anthropic call failed: {e}") from e
        content_blocks = body.get("content", []) or []
        text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
        usage = body.get("usage", {}) or {}
        return {
            "content": "\n".join(text_parts),
            "elapsed_s": round(_time.perf_counter() - t0, 2),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }

    raise ValueError(f"unknown provider: {provider!r}")


def _build_decompose_prompt(spec, parent_req, patterns: list) -> str:
    """Assemble the decomposer user message from the spec + related context."""
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parent.parent
    template_path = repo_root / "prompts" / "decompose.md"
    try:
        system = template_path.read_text(encoding="utf-8")
    except OSError:
        system = "You are a decomposer. Output YAML tasks or SPEC_TOO_BIG:/NEED_CONTEXT:."

    parts: list[str] = []
    parts.append(system)
    parts.append("\n---\n")
    parts.append("## Input specification to decompose\n")
    parts.append(f"### {spec.id} (parent: {spec.parent_req})")
    parts.append(spec.description)
    ac = spec.acceptance_criteria or []
    if ac and ac != ["TBD"]:
        parts.append("Acceptance criteria:")
        for c in ac:
            parts.append(f"  - {c}")
    if getattr(spec, "test_file", ""):
        parts.append("")
        parts.append(
            f"**Grading target for every feature task on this spec: "
            f"`{spec.test_file}`** — use this exact string as "
            f"`test_to_write`. The file already exists on disk as a "
            f"failing-placeholder skeleton; do not propose a different "
            f"path or create a separate test task."
        )
    parts.append("")

    if parent_req is not None:
        parts.append("## Parent requirement\n")
        parts.append(f"### {parent_req.id} [{parent_req.domain}]")
        parts.append(f"Value: {parent_req.value}")
        if parent_req.rationale:
            parts.append(f"Rationale: {parent_req.rationale}")
        if parent_req.elaboration:
            parts.append(f"Elaboration: {parent_req.elaboration}")
        rac = parent_req.acceptance_criteria or []
        if rac and rac != ["TBD"]:
            parts.append("Acceptance criteria:")
            for c in rac:
                parts.append(f"  - {c}")
        parts.append("")

    if patterns:
        parts.append("## Applicable patterns\n")
        for p in patterns:
            parts.append(f"### {p.id} -- {p.name}")
            parts.append(p.description)
            parts.append("")

    parts.append("\nNow produce the task decomposition per the rules above.\n")
    return "\n".join(parts)


def _parse_decompose_response(content: str) -> tuple[str, Any]:
    """Classify + parse a decomposer response.

    Returns:
        ("spec_too_big", reason)
        ("need_context", what)
        ("tasks", list_of_dicts)
        ("no_yaml", raw_content_preview)
        ("yaml_error", error_message)
    """
    import re as _re
    import yaml as _yaml

    content = content or ""
    stop_re = _re.compile(r"^(SPEC_TOO_BIG|NEED_CONTEXT)\s*:\s*(.*)$", _re.MULTILINE)
    stop = stop_re.search(content)
    if stop:
        kind = stop.group(1).lower()
        reason = stop.group(2).strip()
        if kind == "spec_too_big":
            return ("spec_too_big", reason)
        return ("need_context", reason)

    yaml_re = _re.compile(r"```yaml\s*\n(.*?)\n```", _re.DOTALL)
    m = yaml_re.search(content)
    if not m:
        return ("no_yaml", content[:400])
    yaml_text = m.group(1)
    try:
        data = _yaml.safe_load(yaml_text)
    except Exception as e:
        return ("yaml_error", f"{e}\n---raw---\n{yaml_text[:400]}")
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        return ("yaml_error", f"expected top-level 'tasks' list; got {type(data).__name__}")
    return ("tasks", data["tasks"])


def _validate_task_proposals(
    proposals: list[dict],
    parent_spec: str,
    default_budget_files: int = 2,
    default_budget_loc: int = 80,
    target_dir: Path | str | None = None,
    spec_test_file: str = "",
) -> tuple[list[dict], list[str]]:
    """Shape-check + atomicity-check proposals. Returns (normalized, warnings).

    If ``target_dir`` is given, any entry in ``files_to_modify`` that
    exists on disk relative to target_dir and is not already in
    ``context_files`` is auto-added — a small-model executor has no tool
    access and will hallucinate without the file it is modifying
    (FINDINGS-wild F7/F8).

    If ``spec_test_file`` is non-empty (the parent spec declared a
    grading target via `loom spec --test`), any task whose
    ``test_to_write`` differs is force-normalized back to the spec's
    value with a warning. Closes FINDINGS-wild F10 even when the LLM
    disregards the prompt instruction.
    """
    normalized: list[dict] = []
    warnings: list[str] = []
    titles_seen: set[str] = set()
    td = Path(target_dir) if target_dir is not None else None

    for idx, raw in enumerate(proposals):
        if not isinstance(raw, dict):
            warnings.append(f"task #{idx}: not a dict, skipped")
            continue
        title = (raw.get("title") or "").strip()
        if not title:
            warnings.append(f"task #{idx}: missing title, skipped")
            continue
        if title in titles_seen:
            warnings.append(f"task #{idx}: duplicate title {title!r}, skipped")
            continue
        titles_seen.add(title)
        files = raw.get("files_to_modify") or []
        if not isinstance(files, list) or not files:
            warnings.append(f"task {title!r}: files_to_modify empty, skipped")
            continue
        test = (raw.get("test_to_write") or "").strip()
        if not test:
            warnings.append(f"task {title!r}: test_to_write missing, skipped")
            continue
        # If the parent spec declared a grading target, every task on
        # it uses that — override whatever the LLM produced.
        if spec_test_file and test != spec_test_file:
            warnings.append(
                f"task {title!r}: test_to_write {test!r} replaced with "
                f"spec test_file {spec_test_file!r}"
            )
            test = spec_test_file

        budget_files = int(raw.get("size_budget_files", default_budget_files))
        budget_loc = int(raw.get("size_budget_loc", default_budget_loc))
        if len(files) > budget_files:
            warnings.append(
                f"task {title!r}: touches {len(files)} files, exceeds budget {budget_files}"
            )

        context_files = list(raw.get("context_files") or [])
        if td is not None:
            # Auto-augment: any file_to_modify that exists in the target dir
            # and isn't already in context_files should be added, so the
            # executor sees the current source.
            for fm in files:
                if fm in context_files:
                    continue
                if (td / fm).exists():
                    context_files.append(fm)
                    warnings.append(
                        f"task {title!r}: auto-added {fm} to context_files"
                    )

        normalized.append({
            "title": title,
            "parent_spec": parent_spec,
            "files_to_modify": list(files),
            "test_to_write": test,
            "context_reqs": raw.get("context_reqs") or [],
            "context_specs": raw.get("context_specs") or [],
            "context_patterns": raw.get("context_patterns") or [],
            "context_sidecars": raw.get("context_sidecars") or [],
            "context_files": context_files,
            "size_budget_files": budget_files,
            "size_budget_loc": budget_loc,
            "depends_on_titles": list(raw.get("depends_on") or []),
        })

    def _coerce(d: Any) -> str:
        # qwen occasionally emits depends_on entries as dicts ({title: "..."})
        # or other shapes instead of plain strings. Coerce to a comparable
        # string before normalization.
        if isinstance(d, str):
            return d
        if isinstance(d, dict):
            for k in ("title", "name", "ref"):
                if k in d and isinstance(d[k], str):
                    return d[k]
            return ""
        return str(d)

    def _norm(s: Any) -> str:
        # Collapse all whitespace and lowercase, so YAML pipe-style line
        # breaks and trailing spaces don't break equality. Lowercased
        # because qwen sometimes reflows capitalization across line
        # joins ("File path" vs "file path").
        return " ".join(_coerce(s).split()).lower()

    # Match each depends_on ref against earlier titles in three escalating
    # tiers — generators routinely truncate the dep string to the first
    # line of a multi-line title or summarize it, so strict equality
    # would silently lose chain edges (the symptom phV2 hit at 0% across
    # cells). Tiers stop on first hit:
    #   1. exact (whitespace-normalized)
    #   2. dep is a prefix of a unique earlier title
    #   3. dep is a substring of a unique earlier title
    # If multiple earlier titles match at a tier, we fall through —
    # ambiguity is worse than a missing edge. The tier's chosen
    # canonical title is what we record, so apply_decomposition can
    # resolve to the right earlier task ID.
    for i, t in enumerate(normalized):
        earlier = normalized[:i]
        earlier_norm = [(_norm(n["title"]), n["title"]) for n in earlier]
        resolved: list[str] = []
        bad: list[str] = []
        for d in t["depends_on_titles"]:
            dn = _norm(d)
            # Tier 1: exact match
            exact = [c for n, c in earlier_norm if n == dn]
            if len(exact) == 1:
                resolved.append(exact[0])
                continue
            # Tier 2: prefix (LLM truncated to opening sentence)
            prefix = [c for n, c in earlier_norm if n.startswith(dn) or dn.startswith(n)]
            if len(prefix) == 1:
                resolved.append(prefix[0])
                continue
            # Tier 3: substring (LLM picked a distinctive middle phrase)
            sub = [c for n, c in earlier_norm if dn in n or n in dn]
            if len(sub) == 1:
                resolved.append(sub[0])
                continue
            bad.append(d)
        if bad:
            warnings.append(
                f"task {t['title']!r}: depends_on refs {bad} not found earlier"
            )
        t["depends_on_titles"] = resolved

    return normalized, warnings


def decompose(
    store: LoomStore,
    spec_id: str,
    *,
    model: str | None = None,
    target_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Propose a Task decomposition for a Specification. Does NOT persist.

    If ``target_dir`` is provided, the validator auto-augments each task's
    ``context_files`` with any entry from ``files_to_modify`` that exists
    on disk there. Otherwise context augmentation is skipped.

    Returns:
        {spec_id, model, outcome, tasks, warnings, reason, elapsed_s,
         input_tokens, output_tokens, raw_response}

        outcome is one of: tasks | spec_too_big | need_context | no_yaml | yaml_error

    Raises:
        LookupError: spec_id not found.
        RuntimeError: LLM transport failure.
        ValueError: bad model spec.
    """
    spec = store.get_specification(spec_id)
    if spec is None:
        raise LookupError(f"Specification {spec_id} not found")
    parent_req = store.get_requirement(spec.parent_req) if spec.parent_req else None
    patterns = store.get_patterns_for_requirement(spec.parent_req) if spec.parent_req else []

    model = model or _default_decomposer_model()
    prompt = _build_decompose_prompt(spec, parent_req, patterns)
    llm = _call_decomposer_llm(model, prompt)

    outcome, payload = _parse_decompose_response(llm["content"])
    base = {
        "spec_id": spec_id,
        "model": model,
        "outcome": outcome,
        "tasks": [],
        "warnings": [],
        "reason": None,
        "elapsed_s": llm["elapsed_s"],
        "input_tokens": llm["input_tokens"],
        "output_tokens": llm["output_tokens"],
        "raw_response": llm["content"],
    }

    if outcome == "tasks":
        normalized, warnings = _validate_task_proposals(
            payload,
            parent_spec=spec_id,
            target_dir=target_dir,
            spec_test_file=getattr(spec, "test_file", "") or "",
        )
        base["tasks"] = normalized
        base["warnings"] = warnings
    elif outcome in ("spec_too_big", "need_context"):
        base["reason"] = payload
    else:
        base["reason"] = payload if isinstance(payload, str) else str(payload)

    return base


def apply_decomposition(
    store: LoomStore,
    proposals: list[dict],
    *,
    created_by: str = "decomposer",
) -> dict[str, Any]:
    """Persist accepted task proposals to the store.

    Maps each proposal's depends_on_titles to task IDs by creating earlier
    tasks first.
    """
    created_by_title: dict[str, str] = {}
    created: list[dict] = []
    skipped: list[dict] = []

    for p in proposals:
        title = p["title"]
        dep_titles = p.get("depends_on_titles") or []
        dep_ids = [created_by_title[d] for d in dep_titles if d in created_by_title]
        try:
            result = task_add(
                store,
                parent_spec=p["parent_spec"],
                title=title,
                files_to_modify=p["files_to_modify"],
                test_to_write=p["test_to_write"],
                context_reqs=p.get("context_reqs") or None,
                context_specs=p.get("context_specs") or None,
                context_patterns=p.get("context_patterns") or None,
                context_sidecars=p.get("context_sidecars") or None,
                context_files=p.get("context_files") or None,
                size_budget_files=p.get("size_budget_files", 2),
                size_budget_loc=p.get("size_budget_loc", 80),
                depends_on=dep_ids or None,
                created_by=created_by,
            )
        except (LookupError, ValueError) as e:
            skipped.append({"title": title, "error": str(e)})
            continue
        created_by_title[title] = result["id"]
        created.append(result)

    return {"created": created, "skipped": skipped}
