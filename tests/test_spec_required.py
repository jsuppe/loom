"""Tests for REQ-7df25683 — Requirement→Spec→Implementation enforcement.

The rule: direct Requirement→Implementation links via link_type=satisfies
are forbidden. evidences-type links (typically for kind=finding/hypothesis)
are unaffected — they're a different relationship.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from loom import services
from loom.store import (
    LoomStore,
    Requirement,
    Specification,
)


@pytest.fixture(autouse=True)
def use_hash_embeddings(monkeypatch):
    monkeypatch.setenv("LOOM_EMBEDDING_PROVIDER", "hash")


@pytest.fixture
def isolated_project(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    return tmp_path


@pytest.fixture
def store_with_req(isolated_project):
    """Build a store with one kind=requirement and one kind=finding."""
    from loom.embedding import get_embedding
    store = LoomStore("m25-test")
    r = Requirement(
        id="REQ-r0000001", domain="behavior",
        value="The system must support graceful shutdown.",
        source_msg_id=None, source_session="test",
        timestamp="2026-05-01T00:00:00+00:00",
        kind="requirement",
    )
    store.add_requirement(r, get_embedding(r.value))
    f = Requirement(
        id="REQ-f0000001", domain="evaluation",
        value="The M22e pilot ceiling-saturated.",
        source_msg_id=None, source_session="test",
        timestamp="2026-05-02T00:00:00+00:00",
        kind="finding",
    )
    store.add_requirement(f, get_embedding(f.value))
    return store


@pytest.fixture
def sample_file(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("def bar(): return 1\n", encoding="utf-8")
    return str(f)


class TestEnforcement:
    def test_direct_req_link_to_requirement_kind_rejected(
        self, store_with_req, sample_file,
    ):
        """REQ-7df25683: direct link to kind=requirement raises."""
        with pytest.raises(ValueError, match="REQ-7df25683 forbids"):
            services.link(
                store_with_req, file_path=sample_file,
                req_ids=["REQ-r0000001"],
            )

    def test_evidences_link_to_finding_allowed(
        self, store_with_req, sample_file,
    ):
        """Evidence links to findings are not blocked — different
        relationship from implementation."""
        result = services.link(
            store_with_req, file_path=sample_file,
            req_ids=["REQ-f0000001"],
        )
        assert result["linked"]
        # Auto-resolved to link_type=evidences for finding
        assert any(s["link_type"] == "evidences" for s in result["satisfies"])

    def test_explicit_evidences_link_to_requirement_allowed(
        self, store_with_req, sample_file,
    ):
        """Explicit link_type=evidences is allowed even on
        kind=requirement (the user is overriding intent deliberately)."""
        result = services.link(
            store_with_req, file_path=sample_file,
            req_ids=["REQ-r0000001"], link_type="evidences",
        )
        assert result["linked"]
        # Warning surfaces the unusual choice
        assert any("evidences" in w for w in result["warnings"])

    def test_spec_mediated_link_allowed(self, store_with_req, sample_file):
        """Linking via --spec succeeds and parent_req auto-linked."""
        from loom.embedding import get_embedding
        spec = Specification(
            id="SPEC-abc12345",
            parent_req="REQ-r0000001",
            description="Contract: provides shutdown handler.",
            timestamp="2026-05-03T00:00:00+00:00",
        )
        store_with_req.add_specification(spec, get_embedding(spec.description))

        result = services.link(
            store_with_req, file_path=sample_file,
            spec_ids=["SPEC-abc12345"],
        )
        assert result["linked"]
        assert "SPEC-abc12345" in result["satisfies_specs"]
        # parent_req auto-added to satisfies via spec mediation
        assert any(s["req_id"] == "REQ-r0000001"
                   for s in result["satisfies"])

    def test_combined_req_and_spec_link_allowed(
        self, store_with_req, sample_file,
    ):
        """Passing --req together with --spec is fine — the spec
        mediates the relationship."""
        from loom.embedding import get_embedding
        spec = Specification(
            id="SPEC-abc12345",
            parent_req="REQ-r0000001",
            description="Contract.",
            timestamp="2026-05-03T00:00:00+00:00",
        )
        store_with_req.add_specification(spec, get_embedding(spec.description))

        # User passes the same req explicitly + the spec. Should
        # succeed because the spec_ids check bypasses the rejection.
        result = services.link(
            store_with_req, file_path=sample_file,
            req_ids=["REQ-r0000001"],
            spec_ids=["SPEC-abc12345"],
        )
        assert result["linked"]


class TestDoctorWarning:
    def test_doctor_flags_legacy_direct_links(
        self, store_with_req, sample_file,
    ):
        """Legacy direct links inserted via the raw store API (not
        via services.link) should be surfaced by loom doctor."""
        # Inject a direct link bypassing services.link — simulating a
        # pre-REQ-7df25683 impl that's still in the store.
        from datetime import datetime, timezone
        from loom.store import Implementation, generate_impl_id, generate_content_hash
        from loom.embedding import get_embedding
        content = "def bar(): return 1\n"
        impl = Implementation(
            id=generate_impl_id("src/foo.py", "all"),
            file="src/foo.py", lines="all",
            content=content,
            content_hash=generate_content_hash(content),
            timestamp=datetime.now(timezone.utc).isoformat(),
            satisfies=[{
                "req_id": "REQ-r0000001",
                "req_version": "2026-05-01T00:00:00+00:00",
                "link_type": "satisfies",
            }],
            satisfies_specs=None,
        )
        store_with_req.add_implementation(impl, get_embedding(content))

        result = services.doctor(store_with_req)
        assert result["checks"]["legacy_direct_links"]["count"] == 1
        assert any("REQ-7df25683" in w for w in result["warnings"])

    def test_doctor_ignores_spec_mediated_links(
        self, store_with_req, sample_file,
    ):
        """A spec-mediated link should NOT count as legacy."""
        from loom.embedding import get_embedding
        spec = Specification(
            id="SPEC-medi1234",
            parent_req="REQ-r0000001",
            description="Contract.",
            timestamp="2026-05-03T00:00:00+00:00",
        )
        store_with_req.add_specification(spec, get_embedding(spec.description))
        services.link(
            store_with_req, file_path=sample_file,
            spec_ids=["SPEC-medi1234"],
        )

        result = services.doctor(store_with_req)
        assert result["checks"]["legacy_direct_links"]["count"] == 0

    def test_doctor_ignores_evidence_links(
        self, store_with_req, sample_file,
    ):
        """Evidence links to findings should NOT count as legacy."""
        services.link(
            store_with_req, file_path=sample_file,
            req_ids=["REQ-f0000001"],  # finding → auto evidences
        )
        result = services.doctor(store_with_req)
        assert result["checks"]["legacy_direct_links"]["count"] == 0
