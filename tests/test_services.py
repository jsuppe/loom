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
