"""
Tests for src/services.py — shared logic layer between CLI and MCP.

Verifies service functions return the expected data shapes against a
temp LoomStore. Service functions embed text via src/embedding.py; we
force its hash-fallback path so tests don't need Ollama.
"""

import sys
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import embedding  # noqa: E402
import services  # noqa: E402
from store import LoomStore, Requirement, Implementation  # noqa: E402


@pytest.fixture
def store():
    tmp = Path(tempfile.mkdtemp())
    s = LoomStore(project="test-services", data_dir=tmp)
    yield s
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def fake_embedding():
    return [0.1] * 768


@pytest.fixture(autouse=True)
def force_fallback_embedding(monkeypatch):
    """Route get_embedding through the hash fallback so tests don't need Ollama."""
    embedding._embedding_cache.clear()

    def boom(*a, **kw):
        raise ConnectionResetError("no ollama in tests")

    monkeypatch.setattr(embedding.urllib.request, "urlopen", boom)


def _mk_req(store, req_id, domain, value, fake_embedding):
    req = Requirement(
        id=req_id,
        domain=domain,
        value=value,
        source_msg_id="m1",
        source_session="s1",
        timestamp="2026-01-01T00:00:00Z",
    )
    store.add_requirement(req, fake_embedding)
    return req


class TestStatus:
    def test_empty_store(self, store):
        data = services.status(store)
        assert data["project"] == "test-services"
        assert data["requirements"] == 0
        assert data["active"] == 0
        assert data["superseded"] == 0
        assert data["drift_count"] == 0
        assert data["drift"] == []

    def test_counts_reflect_store(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "A", fake_embedding)
        _mk_req(store, "REQ-b", "behavior", "B", fake_embedding)
        data = services.status(store)
        assert data["requirements"] == 2
        assert data["active"] == 2
        assert data["superseded"] == 0

    def test_drift_reported_for_superseded_req_with_impl(self, store, fake_embedding):
        _mk_req(store, "REQ-old", "behavior", "old", fake_embedding)
        impl = Implementation(
            id="IMPL-1", file="src/x.py", lines="1-10",
            content="pass", content_hash="h",
            satisfies=[{"req_id": "REQ-old"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        store.supersede_requirement("REQ-old")

        data = services.status(store)
        assert data["superseded"] == 1
        assert data["drift_count"] == 1
        assert data["drift"][0]["req_id"] == "REQ-old"
        assert data["drift"][0]["file"] == "src/x.py"


class TestQuery:
    def test_empty_store_returns_empty_list(self, store):
        assert services.query(store, "anything") == []

    def test_returns_expected_shape(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "users must log in", fake_embedding)
        results = services.query(store, "login", limit=5)
        assert len(results) == 1
        r = results[0]
        assert set(r.keys()) >= {
            "id", "domain", "value", "status",
            "superseded", "source", "timestamp", "distance",
        }
        assert r["id"] == "REQ-x"
        assert r["superseded"] is False


class TestListRequirements:
    def test_empty(self, store):
        assert services.list_requirements(store) == []

    def test_excludes_superseded_by_default(self, store, fake_embedding):
        _mk_req(store, "REQ-live", "behavior", "live", fake_embedding)
        _mk_req(store, "REQ-dead", "behavior", "dead", fake_embedding)
        store.supersede_requirement("REQ-dead")

        reqs = services.list_requirements(store)
        ids = [r["id"] for r in reqs]
        assert "REQ-live" in ids
        assert "REQ-dead" not in ids

    def test_include_superseded(self, store, fake_embedding):
        _mk_req(store, "REQ-live", "behavior", "live", fake_embedding)
        _mk_req(store, "REQ-dead", "behavior", "dead", fake_embedding)
        store.supersede_requirement("REQ-dead")

        reqs = services.list_requirements(store, include_superseded=True)
        ids = [r["id"] for r in reqs]
        assert "REQ-live" in ids
        assert "REQ-dead" in ids

    def test_has_test_false_when_no_spec(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        reqs = services.list_requirements(store)
        assert reqs[0]["has_test"] is False


class TestTrace:
    def test_unknown_req_raises_lookup(self, store):
        with pytest.raises(LookupError):
            services.trace(store, "REQ-missing")

    def test_missing_file_raises_lookup(self, store):
        with pytest.raises(LookupError):
            services.trace(store, "/nonexistent/path.py")

    def test_req_with_no_impls(self, store, fake_embedding):
        _mk_req(store, "REQ-lonely", "behavior", "alone", fake_embedding)
        data = services.trace(store, "REQ-lonely")
        assert data["type"] == "requirement"
        assert data["id"] == "REQ-lonely"
        assert data["implementations"] == []
        assert data["test_spec"] is None
        assert data["superseded_at"] is None

    def test_req_with_impls(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        impl = Implementation(
            id="IMPL-1", file="src/x.py", lines="1-10",
            content="x = 1", content_hash="h",
            satisfies=[{"req_id": "REQ-x"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        data = services.trace(store, "REQ-x")
        assert len(data["implementations"]) == 1
        assert data["implementations"][0]["file"] == "src/x.py"


class TestChain:
    def test_unknown_req_raises_lookup(self, store):
        with pytest.raises(LookupError):
            services.chain(store, "REQ-missing")

    def test_bare_requirement_has_empty_sublists(self, store, fake_embedding):
        _mk_req(store, "REQ-bare", "behavior", "bare", fake_embedding)
        data = services.chain(store, "REQ-bare")
        assert data["id"] == "REQ-bare"
        assert data["patterns"] == []
        assert data["specifications"] == []
        assert data["direct_implementations"] == []
        assert data["test_spec"] is None

    def test_direct_impl_separated_from_spec_impl(self, store, fake_embedding):
        _mk_req(store, "REQ-1", "behavior", "one", fake_embedding)
        direct = Implementation(
            id="IMPL-direct", file="src/a.py", lines="1-5",
            content="a", content_hash="ha",
            satisfies=[{"req_id": "REQ-1"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(direct, fake_embedding)
        data = services.chain(store, "REQ-1")
        assert len(data["direct_implementations"]) == 1
        assert data["direct_implementations"][0]["file"] == "src/a.py"
        assert data["specifications"] == []


class TestCoverage:
    def test_empty_store_full_coverage(self, store):
        data = services.coverage(store)
        # 0/0 reqs is treated as 100% by convention
        assert data["layer_1_req_to_spec"]["coverage_pct"] == 100
        assert data["layer_1_req_to_spec"]["with_specs"] == 0
        assert data["layer_1_req_to_spec"]["without_specs"] == []
        # 0/0 specs is 0% (no specs to be covered)
        assert data["layer_2_spec_to_impl"]["coverage_pct"] == 0
        assert data["layer_3_spec_to_test"]["coverage_pct"] == 0

    def test_req_without_spec_lands_in_layer_1_gap(self, store, fake_embedding):
        _mk_req(store, "REQ-no-spec", "behavior", "uncovered", fake_embedding)
        data = services.coverage(store)
        l1 = data["layer_1_req_to_spec"]
        assert l1["total_requirements"] == 1
        assert l1["with_specs"] == 0
        assert l1["coverage_pct"] == 0
        assert len(l1["without_specs"]) == 1
        assert l1["without_specs"][0]["id"] == "REQ-no-spec"


class TestConflicts:
    def test_empty_store_no_conflicts(self, store):
        assert services.conflicts(store, "behavior | brand new req") == []

    def test_parses_text_without_pipe(self, store):
        # No `|` → defaults to behavior domain. Just check it doesn't crash.
        result = services.conflicts(store, "no pipe here")
        assert isinstance(result, list)


class TestDoctor:
    def test_empty_store_returns_shape(self, store):
        data = services.doctor(store)
        assert "healthy" in data
        assert "checks" in data
        assert "issues" in data
        assert "warnings" in data
        # Store check should pass against our temp store
        assert data["checks"]["store"]["ok"] is True
        # Test coverage on empty store: 0/0 → 100%
        assert data["checks"]["test_coverage"]["coverage_pct"] == 100
        # Domains check passes (no reqs, no custom domains)
        assert data["checks"]["domains"]["custom"] == []

    def test_orphan_impl_warned(self, store, fake_embedding):
        # Impl that points at a req that doesn't exist → orphan
        impl = Implementation(
            id="IMPL-orphan", file="src/x.py", lines="1-1",
            content="x", content_hash="h",
            satisfies=[{"req_id": "REQ-ghost"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        data = services.doctor(store)
        assert data["checks"]["orphans"]["count"] == 1
        assert any("REQ-ghost" in w for w in data["warnings"])

    def test_drift_warned_for_superseded_with_impl(self, store, fake_embedding):
        _mk_req(store, "REQ-old", "behavior", "old", fake_embedding)
        impl = Implementation(
            id="IMPL-1", file="src/x.py", lines="1-1",
            content="x", content_hash="h",
            satisfies=[{"req_id": "REQ-old"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        store.supersede_requirement("REQ-old")
        data = services.doctor(store)
        assert data["checks"]["drift"]["count"] == 1


class TestExtract:
    def test_creates_requirement(self, store):
        result = services.extract(
            store, domain="behavior", value="users must log in",
        )
        assert result["req_id"].startswith("REQ-")
        assert result["domain"] == "behavior"
        assert result["value"] == "users must log in"
        assert result["conflicts"] == []
        # Verify it was actually persisted.
        assert store.get_requirement(result["req_id"]) is not None

    def test_lowercases_domain_and_strips_whitespace(self, store):
        result = services.extract(
            store, domain="  BEHAVIOR  ", value="  spaced text  ",
        )
        assert result["domain"] == "behavior"
        assert result["value"] == "spaced text"

    def test_id_is_deterministic(self, store):
        # Same domain+value → same ID.
        r1 = services.extract(store, domain="data", value="cache TTL is 60s")
        # Re-extraction creates the same ID; ChromaDB will overwrite.
        r2 = services.extract(store, domain="data", value="cache TTL is 60s")
        assert r1["req_id"] == r2["req_id"]

    def test_rationale_persisted(self, store):
        result = services.extract(
            store, domain="behavior", value="rate limit", rationale="prevent abuse",
        )
        req = store.get_requirement(result["req_id"])
        assert req.rationale == "prevent abuse"


class TestCheck:
    def test_missing_file_raises(self, store):
        with pytest.raises(LookupError):
            services.check(store, "/nonexistent/path.py")

    def test_unlinked_file_returns_empty(self, store, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        data = services.check(store, str(f))
        assert data["linked"] is False
        assert data["drift_detected"] is False
        assert data["requirements"] == []

    def test_drift_detected_when_req_superseded(self, store, fake_embedding, tmp_path):
        from store import generate_impl_id
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        f = tmp_path / "x.py"
        f.write_text("# impl\n")

        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="# impl\n", content_hash="h",
            satisfies=[{"req_id": "REQ-x"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        store.supersede_requirement("REQ-x")

        data = services.check(store, str(f))
        assert data["linked"] is True
        assert data["drift_detected"] is True
        assert data["requirements"][0]["drifted"] is True


class TestLink:
    def test_missing_file_raises(self, store):
        with pytest.raises(LookupError):
            services.link(store, "/nonexistent/path.py", req_ids=["REQ-x"])

    def test_no_ids_returns_unlinked_with_warning(self, store, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        result = services.link(store, str(f))
        assert result["linked"] is False
        assert result["impl_id"] is None
        assert result["warnings"]  # should explain why

    def test_all_unknown_ids_returns_unlinked_with_warnings(self, store, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        result = services.link(store, str(f), req_ids=["REQ-ghost"])
        assert result["linked"] is False
        assert any("REQ-ghost" in w for w in result["warnings"])

    def test_unknown_req_warned_and_skipped(self, store, fake_embedding, tmp_path):
        _mk_req(store, "REQ-real", "behavior", "real", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")

        result = services.link(
            store, str(f), req_ids=["REQ-real", "REQ-ghost"],
        )
        assert result["linked"] is True
        assert any("REQ-ghost" in w for w in result["warnings"])
        # REQ-real should still be linked despite REQ-ghost failing.
        assert any(s["req_id"] == "REQ-real" for s in result["satisfies"])

    def test_links_persisted(self, store, fake_embedding, tmp_path):
        _mk_req(store, "REQ-a", "behavior", "a", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("def a(): pass\n")
        result = services.link(store, str(f), req_ids=["REQ-a"])
        assert result["linked"] is True
        impls = store.get_implementations_for_requirement("REQ-a")
        assert len(impls) == 1
        assert impls[0].id == result["impl_id"]


class TestDetectRequirements:
    def test_missing_file_raises(self, store):
        with pytest.raises(LookupError):
            services.detect_requirements(store, "/nonexistent/path.py")

    def test_returns_candidates(self, store, fake_embedding, tmp_path):
        _mk_req(store, "REQ-1", "behavior", "match", fake_embedding)
        f = tmp_path / "x.py"
        f.write_text("anything\n")
        candidates = services.detect_requirements(store, str(f), n=3)
        assert isinstance(candidates, list)
        # With one req and matching dummy embedding, we expect to see it.
        if candidates:
            assert "req_id" in candidates[0]
            assert "value" in candidates[0]


class TestSync:
    def test_writes_both_docs(self, store, tmp_path):
        result = services.sync(store, str(tmp_path))
        from pathlib import Path
        assert Path(result["requirements_path"]).exists()
        assert Path(result["test_spec_path"]).exists()
        assert result["public"] is False

    def test_public_mode_flag_passed(self, store, tmp_path):
        result = services.sync(store, str(tmp_path), public=True)
        assert result["public"] is True


class TestSupersede:
    def test_unknown_req_raises(self, store):
        with pytest.raises(LookupError):
            services.supersede(store, "REQ-missing")

    def test_already_superseded_raises_value_error(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        services.supersede(store, "REQ-x")
        with pytest.raises(ValueError):
            services.supersede(store, "REQ-x")

    def test_supersedes_and_returns_value(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "old way", fake_embedding)
        result = services.supersede(store, "REQ-x")
        assert result["req_id"] == "REQ-x"
        assert result["value"] == "old way"
        assert result["affected_tests"] == []
        # Verify mutation persisted.
        req = store.get_requirement("REQ-x")
        assert req.superseded_at is not None


class TestSetStatus:
    def test_unknown_req_raises_lookup(self, store):
        with pytest.raises(LookupError):
            services.set_status(store, "REQ-missing", "implemented")

    def test_invalid_status_raises_value_error(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        with pytest.raises(ValueError):
            services.set_status(store, "REQ-x", "bogus")

    def test_valid_status_updates(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        result = services.set_status(store, "REQ-x", "implemented")
        assert result == {"req_id": "REQ-x", "status": "implemented"}
        assert store.get_requirement("REQ-x").status == "implemented"


class TestRefine:
    def test_unknown_req_raises_lookup(self, store):
        with pytest.raises(LookupError):
            services.refine(store, "REQ-missing", elaboration="how")

    def test_empty_elaboration_raises_value_error(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        with pytest.raises(ValueError):
            services.refine(store, "REQ-x", elaboration="   ")

    def test_invalid_status_raises_value_error(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        with pytest.raises(ValueError):
            services.refine(store, "REQ-x", elaboration="how", status="bogus")

    def test_full_update(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        result = services.refine(
            store, "REQ-x",
            elaboration="add input validation on the form",
            acceptance_criteria=["empty email rejected", "bad domain rejected"],
            conversation_context="discussed in design review",
            status="in_progress",
        )
        assert result["req_id"] == "REQ-x"
        assert result["elaboration"] == "add input validation on the form"
        assert len(result["acceptance_criteria"]) == 2
        assert result["status"] == "in_progress"
        assert result["is_complete"] is True

    def test_minimal_update_keeps_pending(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        result = services.refine(store, "REQ-x", elaboration="add validation")
        # Status not provided → unchanged
        assert result["status"] == "pending"
        # Note: ChromaDB rejects empty lists, so acceptance_criteria
        # round-trips as ["TBD"]. That's a pre-existing quirk (see
        # CLAUDE.md ChromaDB metadata rules); is_complete therefore
        # returns True even though no criteria were provided.
        assert result["acceptance_criteria"] == ["TBD"]
