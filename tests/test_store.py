"""
Tests for Loom Store - requirements and implementations.

Run with: pytest tests/test_store.py -v
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loom.store import LoomStore, Requirement, Implementation, generate_impl_id, Task, generate_task_id


@pytest.fixture
def temp_store():
    """Create a temporary store for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    store = LoomStore(project="test", data_dir=temp_dir)
    yield store
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_embedding():
    """A simple embedding vector for testing."""
    return [0.1] * 768  # Match nomic-embed-text dimensions (768d)


class TestRequirements:
    """Tests for requirement operations."""
    
    def test_add_and_get_requirement(self, temp_store, sample_embedding):
        """Can add and retrieve a requirement."""
        req = Requirement(
            id="REQ-001",
            domain="behavior",
            value="Users can create projects",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        temp_store.add_requirement(req, sample_embedding)
        retrieved = temp_store.get_requirement("REQ-001")
        
        assert retrieved is not None
        assert retrieved.id == "REQ-001"
        assert retrieved.value == "Users can create projects"
        assert retrieved.domain == "behavior"
    
    def test_list_requirements_excludes_superseded_by_default(self, temp_store, sample_embedding):
        """list_requirements excludes superseded by default."""
        # Add two requirements
        req1 = Requirement(
            id="REQ-001",
            domain="behavior",
            value="Dashboard shows status",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        req2 = Requirement(
            id="REQ-002",
            domain="behavior",
            value="Dashboard shows status and agents",
            source_msg_id="msg-2",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        temp_store.add_requirement(req1, sample_embedding)
        temp_store.add_requirement(req2, sample_embedding)
        
        # Supersede the first one
        temp_store.supersede_requirement("REQ-001")
        
        # List should only show non-superseded
        reqs = temp_store.list_requirements(include_superseded=False)
        assert len(reqs) == 1
        assert reqs[0].id == "REQ-002"
        
        # With flag, should show both
        all_reqs = temp_store.list_requirements(include_superseded=True)
        assert len(all_reqs) == 2
    
    def test_supersede_requirement(self, temp_store, sample_embedding):
        """Can supersede a requirement."""
        req = Requirement(
            id="REQ-001",
            domain="behavior",
            value="Original requirement",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        temp_store.add_requirement(req, sample_embedding)
        temp_store.supersede_requirement("REQ-001")

        updated = temp_store.get_requirement("REQ-001")
        assert updated.superseded_at is not None


class TestIsCompleteGate:
    """M11.4 Phase A — gated rationale requirement on is_complete()."""

    def _refined_req(self, *, rationale=None, rationale_links=None):
        from loom.store import Requirement
        return Requirement(
            id="REQ-x", domain="behavior", value="x",
            source_msg_id="m", source_session="s",
            timestamp="2026-01-01T00:00:00Z",
            elaboration="Detailed implementation note",
            acceptance_criteria=["Step 1", "Step 2"],
            rationale=rationale,
            rationale_links=rationale_links,
        )

    def test_default_passes_without_rationale(self, monkeypatch):
        """Default behavior (env flag absent): elaboration +
        acceptance criteria are sufficient. Existing callers must
        not flip when M11.4 lands."""
        monkeypatch.delenv("LOOM_REQUIRE_RATIONALE_FOR_COMPLETE", raising=False)
        req = self._refined_req(rationale=None, rationale_links=None)
        assert req.is_complete() is True

    def test_default_fails_without_elaboration(self, monkeypatch):
        from loom.store import Requirement
        monkeypatch.delenv("LOOM_REQUIRE_RATIONALE_FOR_COMPLETE", raising=False)
        req = Requirement(
            id="REQ-x", domain="behavior", value="x",
            source_msg_id="m", source_session="s",
            timestamp="2026-01-01T00:00:00Z",
            acceptance_criteria=["a"],
        )
        assert req.is_complete() is False

    def test_flag_off_string_zero_treated_as_off(self, monkeypatch):
        # Only the literal "1" enables the strict check; everything
        # else (including "0", "false", empty) keeps default behavior.
        monkeypatch.setenv("LOOM_REQUIRE_RATIONALE_FOR_COMPLETE", "0")
        req = self._refined_req(rationale=None, rationale_links=None)
        assert req.is_complete() is True

    def test_flag_on_fails_without_rationale_or_links(self, monkeypatch):
        monkeypatch.setenv("LOOM_REQUIRE_RATIONALE_FOR_COMPLETE", "1")
        req = self._refined_req(rationale=None, rationale_links=None)
        assert req.is_complete() is False

    def test_flag_on_passes_with_prose_rationale(self, monkeypatch):
        monkeypatch.setenv("LOOM_REQUIRE_RATIONALE_FOR_COMPLETE", "1")
        req = self._refined_req(rationale="why we did this")
        assert req.is_complete() is True

    def test_flag_on_passes_with_rationale_links(self, monkeypatch):
        monkeypatch.setenv("LOOM_REQUIRE_RATIONALE_FOR_COMPLETE", "1")
        req = self._refined_req(rationale_links=["REQ-parent"])
        assert req.is_complete() is True

    def test_flag_on_still_fails_basic_when_unrefined(self, monkeypatch):
        from loom.store import Requirement
        monkeypatch.setenv("LOOM_REQUIRE_RATIONALE_FOR_COMPLETE", "1")
        req = Requirement(
            id="REQ-x", domain="behavior", value="x",
            source_msg_id="m", source_session="s",
            timestamp="2026-01-01T00:00:00Z",
            rationale="have it",  # has rationale but no elaboration
        )
        assert req.is_complete() is False


class TestSearchRequirements:
    """Tests for requirement search - the auto-detect feature."""
    
    def test_search_returns_similar_requirements(self, temp_store, sample_embedding):
        """Search finds semantically similar requirements."""
        req = Requirement(
            id="REQ-001",
            domain="ui",
            value="Dashboard displays project metrics",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        temp_store.add_requirement(req, sample_embedding)
        
        results = temp_store.search_requirements(sample_embedding, n=5)
        
        assert len(results) == 1
        assert results[0]["id"] == "REQ-001"
    
    def test_search_currently_includes_superseded(self, temp_store, sample_embedding):
        """CURRENT BEHAVIOR: search_requirements includes superseded requirements."""
        req = Requirement(
            id="REQ-001",
            domain="ui",
            value="Old dashboard spec",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        temp_store.add_requirement(req, sample_embedding)
        temp_store.supersede_requirement("REQ-001")
        
        results = temp_store.search_requirements(sample_embedding, n=5)
        
        # Currently returns superseded - this is the behavior we want to change
        assert len(results) == 1
        assert results[0]["requirement"].superseded_at is not None


class TestSearchRequirementsFiltered:
    """Tests for the NEW behavior: filtering superseded from search."""
    
    def test_search_active_excludes_superseded(self, temp_store, sample_embedding):
        """NEW BEHAVIOR: search_requirements_active excludes superseded."""
        # Add two requirements with same embedding (for test simplicity)
        req1 = Requirement(
            id="REQ-001",
            domain="ui",
            value="Old dashboard spec",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        req2 = Requirement(
            id="REQ-002",
            domain="ui",
            value="New dashboard spec with agents",
            source_msg_id="msg-2",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        temp_store.add_requirement(req1, sample_embedding)
        temp_store.add_requirement(req2, sample_embedding)
        temp_store.supersede_requirement("REQ-001")
        
        # This is the new method we need to implement
        # For now, we can filter after search
        results = temp_store.search_requirements(sample_embedding, n=5)
        active_results = [r for r in results if r["requirement"].superseded_at is None]
        
        assert len(active_results) == 1
        assert active_results[0]["id"] == "REQ-002"


class TestImplementations:
    """Tests for implementation linking."""
    
    def test_add_and_get_implementation(self, temp_store, sample_embedding):
        """Can add and retrieve an implementation."""
        impl = Implementation(
            id="IMPL-001",
            file="src/dashboard.py",
            lines="1-50",
            content="def render_dashboard(): pass",
            content_hash="abc123",
            timestamp=datetime.now(timezone.utc).isoformat(),
            satisfies=[{"req_id": "REQ-001", "req_version": "v1"}]
        )
        
        temp_store.add_implementation(impl, sample_embedding)
        retrieved = temp_store.get_implementation("IMPL-001")
        
        assert retrieved is not None
        assert retrieved.file == "src/dashboard.py"
        assert len(retrieved.satisfies) == 1
    
    def test_get_implementations_for_requirement(self, temp_store, sample_embedding):
        """Can find implementations linked to a requirement."""
        impl = Implementation(
            id="IMPL-001",
            file="src/dashboard.py",
            lines="1-50",
            content="def render_dashboard(): pass",
            content_hash="abc123",
            timestamp=datetime.now(timezone.utc).isoformat(),
            satisfies=[{"req_id": "REQ-001", "req_version": "v1"}]
        )
        
        temp_store.add_implementation(impl, sample_embedding)
        impls = temp_store.get_implementations_for_requirement("REQ-001")
        
        assert len(impls) == 1
        assert impls[0].id == "IMPL-001"


class TestDriftDetection:
    """Tests for drift detection when requirements change."""
    
    def test_detect_drift_when_linked_req_superseded(self, temp_store, sample_embedding):
        """Drift is detected when a linked requirement is superseded."""
        # Add requirement
        req = Requirement(
            id="REQ-001",
            domain="ui",
            value="Dashboard shows status",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        temp_store.add_requirement(req, sample_embedding)
        
        # Link implementation to it
        impl = Implementation(
            id="IMPL-001",
            file="src/dashboard.py",
            lines="1-50",
            content="def render_dashboard(): pass",
            content_hash="abc123",
            timestamp=datetime.now(timezone.utc).isoformat(),
            satisfies=[{"req_id": "REQ-001", "req_version": "v1"}]
        )
        temp_store.add_implementation(impl, sample_embedding)
        
        # Supersede the requirement
        temp_store.supersede_requirement("REQ-001")
        
        # Check for drift
        impl = temp_store.get_implementation("IMPL-001")
        linked_req = temp_store.get_requirement(impl.satisfies[0]["req_id"])
        
        # Drift = linked to superseded requirement
        assert linked_req.superseded_at is not None


class TestDocGeneration:
    """Tests for REQUIREMENTS.md and TEST_SPEC.md generation with implementation links."""

    def test_requirements_doc_shows_implementation_links(self, temp_store, sample_embedding):
        """Generated REQUIREMENTS.md includes linked implementation files."""
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from loom.docs import generate_requirements_doc

        req = Requirement(
            id="REQ-001",
            domain="behavior",
            value="Users can create projects",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        temp_store.add_requirement(req, sample_embedding)

        impl = Implementation(
            id="IMPL-001",
            file="src/projects.py",
            lines="10-25",
            content="def create_project(): pass",
            content_hash="abc123",
            timestamp=datetime.now(timezone.utc).isoformat(),
            satisfies=[{"req_id": "REQ-001", "req_version": "v1"}]
        )
        temp_store.add_implementation(impl, sample_embedding)

        with tempfile.TemporaryDirectory() as out_dir:
            path = generate_requirements_doc(temp_store, Path(out_dir))
            content = path.read_text(encoding="utf-8")

            assert "`src/projects.py` (lines 10-25)" in content
            assert "**Status:** pending" in content

    def test_requirements_doc_shows_none_when_no_implementations(self, temp_store, sample_embedding):
        """Requirements with no linked code show 'None yet'."""
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from loom.docs import generate_requirements_doc

        req = Requirement(
            id="REQ-002",
            domain="ui",
            value="Dashboard is mobile-friendly",
            source_msg_id="msg-2",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        temp_store.add_requirement(req, sample_embedding)

        with tempfile.TemporaryDirectory() as out_dir:
            path = generate_requirements_doc(temp_store, Path(out_dir))
            content = path.read_text(encoding="utf-8")

            assert "*None yet*" in content

    def test_requirements_doc_has_traceability_matrix(self, temp_store, sample_embedding):
        """Generated REQUIREMENTS.md includes a traceability matrix table."""
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from loom.docs import generate_requirements_doc

        req = Requirement(
            id="REQ-001",
            domain="behavior",
            value="Users can create projects",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        temp_store.add_requirement(req, sample_embedding)

        impl = Implementation(
            id="IMPL-001",
            file="src/projects.py",
            lines="10-25",
            content="def create_project(): pass",
            content_hash="abc123",
            timestamp=datetime.now(timezone.utc).isoformat(),
            satisfies=[{"req_id": "REQ-001", "req_version": "v1"}]
        )
        temp_store.add_implementation(impl, sample_embedding)

        with tempfile.TemporaryDirectory() as out_dir:
            path = generate_requirements_doc(temp_store, Path(out_dir))
            content = path.read_text(encoding="utf-8")

            assert "## Traceability Matrix" in content
            assert "| Requirement | Domain | Specs | Files | Test Spec |" in content
            assert "| REQ-001 | behavior | — | `src/projects.py` | — |" in content

    def test_test_spec_doc_shows_covered_code(self, temp_store, sample_embedding):
        """Generated TEST_SPEC.md shows linked code under test specs."""
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from loom.docs import generate_test_spec_doc
        from loom.testspec import TestSpec

        req = Requirement(
            id="REQ-001",
            domain="behavior",
            value="Users can create projects",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        temp_store.add_requirement(req, sample_embedding)

        impl = Implementation(
            id="IMPL-001",
            file="src/projects.py",
            lines="10-25",
            content="def create_project(): pass",
            content_hash="abc123",
            timestamp=datetime.now(timezone.utc).isoformat(),
            satisfies=[{"req_id": "REQ-001", "req_version": "v1"}]
        )
        temp_store.add_implementation(impl, sample_embedding)

        specs = {
            "REQ-001": TestSpec(
                req_id="REQ-001",
                description="Verify project creation",
                steps=["Click create", "Enter name"],
                expected="Project appears in list"
            )
        }

        with tempfile.TemporaryDirectory() as out_dir:
            path = generate_test_spec_doc(temp_store, Path(out_dir), specs=specs)
            content = path.read_text(encoding="utf-8")

            assert "**Covered code:**" in content
            assert "`src/projects.py` (lines 10-25)" in content

    def test_test_spec_doc_shows_uncovered_code(self, temp_store, sample_embedding):
        """TEST_SPEC.md shows 'Uncovered code' for impls without test specs."""
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from loom.docs import generate_test_spec_doc

        req = Requirement(
            id="REQ-001",
            domain="behavior",
            value="Users can create projects",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        temp_store.add_requirement(req, sample_embedding)

        impl = Implementation(
            id="IMPL-001",
            file="src/projects.py",
            lines="10-25",
            content="def create_project(): pass",
            content_hash="abc123",
            timestamp=datetime.now(timezone.utc).isoformat(),
            satisfies=[{"req_id": "REQ-001", "req_version": "v1"}]
        )
        temp_store.add_implementation(impl, sample_embedding)

        with tempfile.TemporaryDirectory() as out_dir:
            path = generate_test_spec_doc(temp_store, Path(out_dir), specs={})
            content = path.read_text(encoding="utf-8")

            assert "**Uncovered code:**" in content
            assert "`src/projects.py` (lines 10-25)" in content

    def test_requirements_doc_shows_spec_tier(self, temp_store, sample_embedding):
        """REQUIREMENTS.md shows specs under each requirement, with impls nested under specs."""
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from loom.docs import generate_requirements_doc
        from loom.store import Specification

        req = Requirement(
            id="REQ-001",
            domain="behavior",
            value="Users can create projects",
            source_msg_id="msg-1",
            source_session="test-session",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        temp_store.add_requirement(req, sample_embedding)

        spec = Specification(
            id="SPEC-001",
            parent_req="REQ-001",
            description="Project creation endpoint accepts POST /projects with name field",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="approved"
        )
        temp_store.add_specification(spec, sample_embedding)

        impl = Implementation(
            id="IMPL-001",
            file="src/projects.py",
            lines="10-25",
            content="def create_project(name): pass",
            content_hash="abc123",
            timestamp=datetime.now(timezone.utc).isoformat(),
            satisfies=[{"req_id": "REQ-001", "req_version": "v1"}],
            satisfies_specs=["SPEC-001"]
        )
        temp_store.add_implementation(impl, sample_embedding)

        with tempfile.TemporaryDirectory() as out_dir:
            path = generate_requirements_doc(temp_store, Path(out_dir))
            content = path.read_text(encoding="utf-8")

            assert "**Specifications (1):**" in content
            assert "`SPEC-001`" in content
            assert "`src/projects.py` (lines 10-25)" in content
            # Traceability matrix shows spec ID
            assert "| REQ-001 | behavior | `SPEC-001` | `src/projects.py` | — |" in content

    # M11.2 — rationale linkage rendering

    def test_requirements_doc_renders_builds_on_section(self, temp_store, sample_embedding):
        """When a requirement has rationale_links, REQUIREMENTS.md
        should include a 'Builds on:' subsection (M11.2)."""
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from loom.docs import generate_requirements_doc

        # Anchor with rationale.
        anchor = Requirement(
            id="REQ-anchor", domain="behavior",
            value="Rate-limit on every payment-path endpoint",
            source_msg_id="m", source_session="s",
            timestamp=datetime.now(timezone.utc).isoformat(),
            rationale="incident 2024-09-12 — abuse via rapid retries",
        )
        temp_store.add_requirement(anchor, sample_embedding)

        # Derived req that links to the anchor.
        derived = Requirement(
            id="REQ-derived", domain="behavior",
            value="Rate-limit refunds at 10/min",
            source_msg_id="m", source_session="s",
            timestamp=datetime.now(timezone.utc).isoformat(),
            rationale_links=["REQ-anchor"],
        )
        temp_store.add_requirement(derived, sample_embedding)

        with tempfile.TemporaryDirectory() as out_dir:
            content = generate_requirements_doc(
                temp_store, Path(out_dir),
            ).read_text(encoding="utf-8")

        assert "**Builds on:**" in content
        assert "`REQ-anchor`" in content
        assert "Rate-limit on every payment-path endpoint" in content
        assert "incident 2024-09-12" in content

    def test_requirements_doc_marks_rationale_needed_in_heading(self, temp_store, sample_embedding):
        """Reqs with status=rationale_needed get a visible heading
        marker so the debt is hard to miss in scans (M11.2)."""
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from loom.docs import generate_requirements_doc

        req = Requirement(
            id="REQ-debt", domain="behavior",
            value="Some captured-but-unjustified requirement",
            source_msg_id="m", source_session="s",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="rationale_needed",
        )
        temp_store.add_requirement(req, sample_embedding)

        with tempfile.TemporaryDirectory() as out_dir:
            content = generate_requirements_doc(
                temp_store, Path(out_dir),
            ).read_text(encoding="utf-8")
        assert "REQ-debt   ⚠ rationale_needed" in content

    def test_requirements_doc_renders_remediation_prompt(self, temp_store, sample_embedding):
        """rationale_needed reqs without rationale or links get a
        remediation prompt explaining how to clear the debt (M11.2)."""
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from loom.docs import generate_requirements_doc

        req = Requirement(
            id="REQ-debt2", domain="behavior",
            value="Unjustified",
            source_msg_id="m", source_session="s",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="rationale_needed",
        )
        temp_store.add_requirement(req, sample_embedding)
        with tempfile.TemporaryDirectory() as out_dir:
            content = generate_requirements_doc(
                temp_store, Path(out_dir),
            ).read_text(encoding="utf-8")
        assert "Rationale needed" in content
        assert "loom set-status REQ-debt2 pending" in content

    def test_traceability_matrix_adds_derives_column_when_links_exist(
        self, temp_store, sample_embedding,
    ):
        """The matrix gains a 'Derives from' column when at least
        one req has rationale_links (M11.2)."""
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from loom.docs import generate_requirements_doc

        anchor = Requirement(
            id="REQ-A", domain="behavior", value="anchor",
            source_msg_id="m", source_session="s",
            timestamp=datetime.now(timezone.utc).isoformat(),
            rationale="origin",
        )
        derived = Requirement(
            id="REQ-B", domain="behavior", value="derived",
            source_msg_id="m", source_session="s",
            timestamp=datetime.now(timezone.utc).isoformat(),
            rationale_links=["REQ-A"],
        )
        temp_store.add_requirement(anchor, sample_embedding)
        temp_store.add_requirement(derived, sample_embedding)
        with tempfile.TemporaryDirectory() as out_dir:
            content = generate_requirements_doc(
                temp_store, Path(out_dir),
            ).read_text(encoding="utf-8")
        # Header gains the column.
        assert "| Requirement | Domain | Derives from | Specs | Files | Test Spec |" in content
        # Derived row shows the link.
        assert "| REQ-B | behavior | `REQ-A` |" in content
        # Anchor row shows em-dash for empty.
        assert "| REQ-A | behavior | — |" in content

    def test_traceability_matrix_omits_derives_column_when_no_links(
        self, temp_store, sample_embedding,
    ):
        """When no reqs have links, the matrix keeps the original
        5-column shape (M11.2)."""
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from loom.docs import generate_requirements_doc

        req = Requirement(
            id="REQ-plain", domain="behavior", value="plain req",
            source_msg_id="m", source_session="s",
            timestamp=datetime.now(timezone.utc).isoformat(),
            rationale="r",
        )
        temp_store.add_requirement(req, sample_embedding)
        with tempfile.TemporaryDirectory() as out_dir:
            content = generate_requirements_doc(
                temp_store, Path(out_dir),
            ).read_text(encoding="utf-8")
        assert "| Requirement | Domain | Specs | Files | Test Spec |" in content
        assert "Derives from" not in content


class TestSpecificationTestFile:
    def test_defaults_to_empty_string(self):
        from loom.store import Specification
        spec = Specification(
            id="SPEC-x", parent_req="REQ-x",
            description="d", timestamp="2026-01-01T00:00:00Z",
        )
        assert spec.test_file == ""

    def test_roundtrip_through_dict(self):
        from loom.store import Specification
        spec = Specification(
            id="SPEC-y", parent_req="REQ-y",
            description="d", timestamp="2026-01-01T00:00:00Z",
            test_file="tests/test_foo.py::TestFoo",
        )
        round_tripped = Specification.from_dict(spec.to_dict())
        assert round_tripped.test_file == "tests/test_foo.py::TestFoo"

    def test_backward_compat_missing_field(self):
        """Old stores with no test_file key still load."""
        from loom.store import Specification
        d = {
            "id": "SPEC-old", "parent_req": "REQ-old",
            "description": "d", "timestamp": "2026-01-01T00:00:00Z",
            "status": "draft", "acceptance_criteria": None,
            "source_doc": None, "source_conversation": None,
            "superseded_at": None, "superseded_by": None,
            # no test_file
        }
        spec = Specification.from_dict(d)
        assert spec.test_file == ""


class TestTaskDataclass:
    def test_generate_task_id_is_stable(self):
        a = generate_task_id("SPEC-x", "add helper")
        b = generate_task_id("SPEC-x", "add helper")
        assert a == b
        assert a.startswith("TASK-")

    def test_generate_task_id_differs_per_title(self):
        a = generate_task_id("SPEC-x", "add helper")
        b = generate_task_id("SPEC-x", "remove helper")
        assert a != b

    def test_to_from_dict_roundtrip(self):
        t = Task(
            id="TASK-abc", parent_spec="SPEC-x", title="t", timestamp="2026-01-01T00:00:00Z",
            files_to_modify=["src/a.py"], test_to_write="tests/t.py::T",
            context_reqs=["REQ-a"], depends_on=["TASK-prev"],
        )
        d = t.to_dict()
        t2 = Task.from_dict(d)
        assert t2.id == t.id
        assert t2.context_reqs == ["REQ-a"]
        assert t2.depends_on == ["TASK-prev"]

    def test_empty_lists_become_sentinel(self):
        t = Task(
            id="TASK-x", parent_spec="SPEC-x", title="t", timestamp="2026-01-01T00:00:00Z",
            files_to_modify=["src/a.py"], test_to_write="t::T",
        )
        d = t.to_dict()
        # Empty optional lists substituted with ["TBD"] for ChromaDB.
        assert d["context_reqs"] == ["TBD"]
        # Round-trip normalizes back to None.
        assert Task.from_dict(d).context_reqs is None

    def test_is_ready_no_deps(self):
        t = Task(
            id="TASK-x", parent_spec="SPEC-x", title="t", timestamp="2026-01-01T00:00:00Z",
            files_to_modify=["src/a.py"], test_to_write="t::T",
        )
        assert t.is_ready(set()) is True

    def test_is_ready_with_deps(self):
        t = Task(
            id="TASK-x", parent_spec="SPEC-x", title="t", timestamp="2026-01-01T00:00:00Z",
            files_to_modify=["src/a.py"], test_to_write="t::T",
            depends_on=["TASK-a", "TASK-b"],
        )
        assert t.is_ready(set()) is False
        assert t.is_ready({"TASK-a"}) is False
        assert t.is_ready({"TASK-a", "TASK-b"}) is True


class TestTaskStoreMethods:
    def test_add_and_get_task(self, temp_store, sample_embedding):
        t = Task(
            id="TASK-1", parent_spec="SPEC-x", title="add", timestamp="2026-01-01T00:00:00Z",
            files_to_modify=["src/a.py"], test_to_write="t::T",
        )
        temp_store.add_task(t, sample_embedding)
        got = temp_store.get_task("TASK-1")
        assert got is not None
        assert got.id == "TASK-1"

    def test_get_missing_task(self, temp_store):
        assert temp_store.get_task("TASK-404") is None

    def test_list_tasks_filters(self, temp_store, sample_embedding):
        for i, status in enumerate(["pending", "pending", "claimed", "complete"]):
            t = Task(
                id=f"TASK-{i}", parent_spec="SPEC-x", title=f"t{i}",
                timestamp="2026-01-01T00:00:00Z",
                files_to_modify=["src/a.py"], test_to_write="t::T",
                status=status,
            )
            temp_store.add_task(t, sample_embedding)
        assert len(temp_store.list_tasks()) == 4
        assert len(temp_store.list_tasks(status="pending")) == 2
        assert len(temp_store.list_tasks(status="complete")) == 1

    def test_list_ready_tasks_respects_deps(self, temp_store, sample_embedding):
        t1 = Task(id="TASK-1", parent_spec="SPEC-x", title="t1",
                  timestamp="2026-01-01T00:00:00Z",
                  files_to_modify=["src/a.py"], test_to_write="t::T")
        t2 = Task(id="TASK-2", parent_spec="SPEC-x", title="t2",
                  timestamp="2026-01-01T00:00:00Z",
                  files_to_modify=["src/a.py"], test_to_write="t::T",
                  depends_on=["TASK-1"])
        temp_store.add_task(t1, sample_embedding)
        temp_store.add_task(t2, sample_embedding)

        ready = temp_store.list_ready_tasks()
        assert [t.id for t in ready] == ["TASK-1"]

        temp_store.set_task_status("TASK-1", "complete")
        ready = temp_store.list_ready_tasks()
        assert [t.id for t in ready] == ["TASK-2"]

    def test_update_task_stamps_updated_at(self, temp_store, sample_embedding):
        t = Task(id="TASK-1", parent_spec="SPEC-x", title="t",
                 timestamp="2026-01-01T00:00:00Z",
                 files_to_modify=["src/a.py"], test_to_write="t::T")
        temp_store.add_task(t, sample_embedding)
        assert temp_store.get_task("TASK-1").updated_at is None
        temp_store.update_task("TASK-1", {"status": "claimed"})
        assert temp_store.get_task("TASK-1").updated_at is not None

    def test_set_task_status_rejects_invalid(self, temp_store, sample_embedding):
        t = Task(id="TASK-1", parent_spec="SPEC-x", title="t",
                 timestamp="2026-01-01T00:00:00Z",
                 files_to_modify=["src/a.py"], test_to_write="t::T")
        temp_store.add_task(t, sample_embedding)
        assert temp_store.set_task_status("TASK-1", "bogus") is False
        assert temp_store.set_task_status("TASK-1", "claimed") is True

    def test_stats_includes_tasks(self, temp_store, sample_embedding):
        stats = temp_store.stats()
        assert "tasks" in stats
        assert stats["tasks"] == 0
        t = Task(id="TASK-1", parent_spec="SPEC-x", title="t",
                 timestamp="2026-01-01T00:00:00Z",
                 files_to_modify=["src/a.py"], test_to_write="t::T")
        temp_store.add_task(t, sample_embedding)
        assert temp_store.stats()["tasks"] == 1


class TestImplementationSymbolFields:
    """M10.1 — Implementation gains optional symbol_ticket +
    symbol_signature_hash fields. Both default None for back-compat
    with stores that predate M10."""

    def test_default_to_none(self, temp_store, sample_embedding):
        impl = Implementation(
            id="IMPL-noop", file="src/x.py", lines="all",
            content="pass\n", content_hash="h",
            satisfies=[{"req_id": "REQ-x"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        assert impl.symbol_ticket is None
        assert impl.symbol_signature_hash is None

    def test_round_trip_with_symbol_fields(self, temp_store, sample_embedding):
        impl = Implementation(
            id="IMPL-sym", file="src/x.py", lines="42-78",
            content="pass\n", content_hash="h",
            satisfies=[{"req_id": "REQ-x"}],
            timestamp="2026-01-01T00:00:00Z",
            symbol_ticket="kythe://loom?path=src/x.py#Service.commit",
            symbol_signature_hash="sig:abc123",
        )
        temp_store.add_implementation(impl, sample_embedding)
        roundtrip = temp_store.get_implementation("IMPL-sym")
        assert roundtrip is not None
        assert roundtrip.symbol_ticket == "kythe://loom?path=src/x.py#Service.commit"
        assert roundtrip.symbol_signature_hash == "sig:abc123"

    def test_legacy_dict_loads_with_setdefault(self):
        # Simulate a dict from an older store (pre-M10) that lacks the
        # two new fields entirely.
        legacy = {
            "id": "IMPL-old", "file": "src/x.py", "lines": "all",
            "content": "pass\n", "content_hash": "h",
            "satisfies": [{"req_id": "REQ-x"}],
            "timestamp": "2026-01-01T00:00:00Z",
        }
        impl = Implementation.from_dict(legacy)
        assert impl.symbol_ticket is None
        assert impl.symbol_signature_hash is None


class TestEmbeddingDimensionPin:
    """M3.2 — store pins its embedding_dim on first write and rejects
    mismatched vectors thereafter (e.g. provider switched ollama→openai
    without re-embedding)."""

    def test_dim_pinned_on_first_write(self, temp_store, sample_embedding):
        # Empty store; meta key absent until first write.
        assert temp_store._get_meta("embedding_dim") is None
        req = Requirement(
            id="REQ-1", domain="behavior", value="x",
            source_msg_id="m", source_session="s",
            timestamp="2026-01-01T00:00:00Z",
        )
        temp_store.add_requirement(req, sample_embedding)
        assert temp_store._get_meta("embedding_dim") == "768"

    def test_mismatched_dim_raises(self, temp_store, sample_embedding):
        from loom.store import EmbeddingDimensionMismatch
        req = Requirement(
            id="REQ-1", domain="behavior", value="x",
            source_msg_id="m", source_session="s",
            timestamp="2026-01-01T00:00:00Z",
        )
        temp_store.add_requirement(req, sample_embedding)
        # Now try to write a 1536-dim vector (e.g. switched to openai).
        big = [0.1] * 1536
        req2 = Requirement(
            id="REQ-2", domain="behavior", value="y",
            source_msg_id="m", source_session="s",
            timestamp="2026-01-01T00:00:00Z",
        )
        with pytest.raises(EmbeddingDimensionMismatch, match="1536"):
            temp_store.add_requirement(req2, big)

    def test_legacy_store_backfills_dim_on_open(self, sample_embedding):
        """A store created before _loom_meta existed must learn its dim
        from existing data on the next open."""
        from loom.store import LoomStore
        temp_dir = Path(tempfile.mkdtemp())
        try:
            store = LoomStore(project="legacy", data_dir=temp_dir)
            req = Requirement(
                id="REQ-1", domain="behavior", value="x",
                source_msg_id="m", source_session="s",
                timestamp="2026-01-01T00:00:00Z",
            )
            store.add_requirement(req, sample_embedding)
            # Simulate a legacy store: drop the meta entry, close, reopen.
            store.conn.execute("DELETE FROM _loom_meta")
            store.conn.commit()
            store.conn.close()

            reopened = LoomStore(project="legacy", data_dir=temp_dir)
            # Back-filled from the existing 768-dim row.
            assert reopened._get_meta("embedding_dim") == "768"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_each_collection_routes_through_check(self, temp_store, sample_embedding):
        """All six collections share the same dim check — flipping any
        of them with a wrong-sized vector must raise."""
        from loom.store import EmbeddingDimensionMismatch, Specification, Pattern, Implementation
        req = Requirement(
            id="REQ-1", domain="behavior", value="x",
            source_msg_id="m", source_session="s",
            timestamp="2026-01-01T00:00:00Z",
        )
        temp_store.add_requirement(req, sample_embedding)  # pins to 768
        bad = [0.1] * 100

        spec = Specification(id="SPEC-1", parent_req="REQ-1", description="d",
                              timestamp="2026-01-01T00:00:00Z")
        with pytest.raises(EmbeddingDimensionMismatch):
            temp_store.add_specification(spec, bad)

        pat = Pattern(id="PAT-1", name="p", description="d",
                       applies_to=["REQ-1"],
                       timestamp="2026-01-01T00:00:00Z")
        with pytest.raises(EmbeddingDimensionMismatch):
            temp_store.add_pattern(pat, bad)

        impl = Implementation(
            id=generate_impl_id("a.py", "all"),
            file="a.py", lines="all",
            content="x", content_hash="h",
            satisfies=[{"req_id": "REQ-1"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        with pytest.raises(EmbeddingDimensionMismatch):
            temp_store.add_implementation(impl, bad)
