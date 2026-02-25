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

from store import LoomStore, Requirement, Implementation, generate_impl_id


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
