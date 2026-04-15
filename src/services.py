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


def conflicts(store: LoomStore, text: str) -> list[dict[str, Any]]:
    """Check whether `text` conflicts with existing requirements.

    `text` is parsed as `domain | value`; if no `|`, defaults to
    `behavior | <text>`.

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
    checks["ollama"] = {"ok": ollama_ok, "models": ollama_models[:5]}

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

    return {
        "project": store.project,
        "healthy": len(issues) == 0,
        "checks": checks,
        "issues": issues,
        "warnings": warnings,
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
            })

    return {
        "file": file_path,
        "lines": lines,
        "linked": True,
        "drift_detected": drift_found,
        "requirements": results,
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

    return {
        "linked": True,
        "impl_id": impl_id,
        "file": file_path,
        "lines": lines or "all",
        "satisfies": satisfies,
        "satisfies_specs": satisfies_specs,
        "warnings": warnings,
    }


VALID_STATUSES = ("pending", "in_progress", "implemented", "verified", "superseded")


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
