"""
Loom Store - Vector database for requirements and implementations.

Uses ChromaDB for embeddings + metadata storage.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None


@dataclass
class Requirement:
    """A requirement derived from chat."""
    id: str
    domain: str  # terminology, behavior, ui, data, etc.
    value: str   # The actual requirement text
    source_msg_id: str
    source_session: str
    timestamp: str  # ISO format
    superseded_at: Optional[str] = None
    
    # Enhanced fields for actionable requirements
    elaboration: Optional[str] = None  # Agent-generated expansion of how to satisfy this
    rationale: Optional[str] = None  # Why this requirement exists (decision context)
    status: str = "pending"  # pending, in_progress, implemented, verified, superseded
    acceptance_criteria: Optional[List[str]] = None  # Definition of done
    test_spec_id: Optional[str] = None  # Link to test specification
    conversation_context: Optional[str] = None  # Key conversation excerpts
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Handle None/empty lists - ChromaDB rejects empty lists in metadata
        if not d.get('acceptance_criteria'):
            d['acceptance_criteria'] = ["TBD"]
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Requirement":
        # Handle missing fields for backwards compatibility
        d.setdefault('elaboration', None)
        d.setdefault('rationale', None)
        d.setdefault('status', 'pending')
        d.setdefault('acceptance_criteria', None)
        d.setdefault('test_spec_id', None)
        d.setdefault('conversation_context', None)
        return cls(**d)
    
    def is_complete(self) -> bool:
        """Check if requirement has full refinement."""
        return bool(
            self.elaboration and 
            self.acceptance_criteria and 
            len(self.acceptance_criteria) > 0
        )


@dataclass
class Specification:
    """A detailed specification that describes HOW to implement a requirement."""
    id: str
    parent_req: str  # REQ-xxx that this spec belongs to
    description: str  # Detailed specification text
    timestamp: str  # ISO format
    status: str = "draft"  # draft, approved, implemented, verified, superseded
    acceptance_criteria: Optional[List[str]] = None  # Specific criteria for this spec
    source_doc: Optional[str] = None  # Document path if extracted from docs
    source_conversation: Optional[str] = None  # Session if from conversation
    superseded_at: Optional[str] = None
    superseded_by: Optional[str] = None  # SPEC-xxx
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Handle None/empty lists - ChromaDB rejects empty lists in metadata
        if not d.get('acceptance_criteria'):
            d['acceptance_criteria'] = ["TBD"]
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Specification":
        d.setdefault('status', 'draft')
        d.setdefault('acceptance_criteria', None)
        d.setdefault('source_doc', None)
        d.setdefault('source_conversation', None)
        d.setdefault('superseded_at', None)
        d.setdefault('superseded_by', None)
        return cls(**d)


@dataclass
class Pattern:
    """A shared design pattern or standard that applies to multiple requirements."""
    id: str
    name: str  # Short name, e.g., "JSON API Response Format"
    description: str  # Full pattern description
    timestamp: str
    applies_to: List[str]  # [REQ-xxx, REQ-yyy, ...]
    status: str = "active"  # active, deprecated
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Pattern":
        d.setdefault('status', 'active')
        return cls(**d)


@dataclass 
class Implementation:
    """A code chunk linked to requirements and specifications."""
    id: str
    file: str
    lines: str  # "42-78"
    content: str
    content_hash: str
    timestamp: str
    satisfies: List[Dict[str, str]]  # [{"req_id": "...", "req_version": "..."}]
    satisfies_specs: Optional[List[str]] = None  # [SPEC-xxx, SPEC-yyy]
    satisfies_patterns: Optional[List[str]] = None  # [PAT-xxx]
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get('satisfies_specs') is None:
            d['satisfies_specs'] = []
        if d.get('satisfies_patterns') is None:
            d['satisfies_patterns'] = []
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Implementation":
        d.setdefault('satisfies_specs', None)
        d.setdefault('satisfies_patterns', None)
        return cls(**d)


class LoomStore:
    """
    Vector store for Loom data.
    
    Collections:
    - requirements: Requirement embeddings + metadata
    - specifications: Detailed specs linked to requirements
    - patterns: Shared design patterns across requirements
    - implementations: Code chunks linked to requirements/specs
    - chat_messages: Raw chat message embeddings for context
    """
    
    def __init__(self, project: str, data_dir: Optional[Path] = None):
        if chromadb is None:
            raise ImportError("chromadb is required. Install with: pip install chromadb")
        
        self.project = project
        self.data_dir = data_dir or Path.home() / ".openclaw" / "loom" / project
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB with persistent storage
        self.client = chromadb.PersistentClient(
            path=str(self.data_dir),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collections
        self.requirements = self.client.get_or_create_collection(
            name="requirements",
            metadata={"description": "Extracted requirements from chat"}
        )
        
        self.specifications = self.client.get_or_create_collection(
            name="specifications",
            metadata={"description": "Detailed specifications linked to requirements"}
        )
        
        self.patterns = self.client.get_or_create_collection(
            name="patterns",
            metadata={"description": "Shared design patterns across requirements"}
        )
        
        self.implementations = self.client.get_or_create_collection(
            name="implementations", 
            metadata={"description": "Code chunks linked to requirements and specifications"}
        )
        
        self.chat_messages = self.client.get_or_create_collection(
            name="chat_messages",
            metadata={"description": "Raw chat messages for context"}
        )
    
    # ==================== Requirements ====================
    
    def add_requirement(self, req: Requirement, embedding: List[float]) -> None:
        """Add or update a requirement."""
        self.requirements.upsert(
            ids=[req.id],
            embeddings=[embedding],
            metadatas=[req.to_dict()],
            documents=[req.value]
        )
    
    def get_requirement(self, req_id: str) -> Optional[Requirement]:
        """Get a requirement by ID."""
        result = self.requirements.get(ids=[req_id], include=["metadatas"])
        if result["ids"]:
            return Requirement.from_dict(result["metadatas"][0])
        return None
    
    def get_current_requirement(self, req_id: str) -> Optional[Requirement]:
        """Get the current (non-superseded) version of a requirement."""
        # ChromaDB can't filter on None values, so we get and filter in Python
        result = self.requirements.get(
            ids=[req_id],
            include=["metadatas"]
        )
        if result["ids"]:
            req = Requirement.from_dict(result["metadatas"][0])
            if req.superseded_at is None:
                return req
        return None
    
    def supersede_requirement(self, req_id: str) -> None:
        """Mark a requirement as superseded."""
        req = self.get_requirement(req_id)
        if req and not req.superseded_at:
            from datetime import timezone
            req.superseded_at = datetime.now(timezone.utc).isoformat()
            # Re-embed with updated metadata
            result = self.requirements.get(ids=[req_id], include=["embeddings"])
            if result["embeddings"] is not None and len(result["embeddings"]) > 0:
                self.add_requirement(req, result["embeddings"][0])
    
    def search_requirements(self, query_embedding: List[float], n: int = 5) -> List[Dict]:
        """Search requirements by semantic similarity."""
        results = self.requirements.query(
            query_embeddings=[query_embedding],
            n_results=n,
            include=["metadatas", "documents", "distances"]
        )
        
        return [
            {
                "id": results["ids"][0][i],
                "requirement": Requirement.from_dict(results["metadatas"][0][i]),
                "distance": results["distances"][0][i] if results["distances"] else None
            }
            for i in range(len(results["ids"][0]))
        ]
    
    def list_requirements(self, include_superseded: bool = False) -> List[Requirement]:
        """List all requirements."""
        result = self.requirements.get(include=["metadatas"])
        reqs = [Requirement.from_dict(m) for m in result["metadatas"]]
        if not include_superseded:
            reqs = [r for r in reqs if r.superseded_at is None]
        return reqs
    
    def update_requirement(self, req_id: str, updates: Dict[str, Any]) -> Optional[Requirement]:
        """Update specific fields of a requirement."""
        req = self.get_requirement(req_id)
        if not req:
            return None
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(req, key):
                setattr(req, key, value)
        
        # Re-save with existing embedding
        result = self.requirements.get(ids=[req_id], include=["embeddings"])
        if result["embeddings"] is not None and len(result["embeddings"]) > 0:
            self.add_requirement(req, result["embeddings"][0])
        
        return req
    
    def set_requirement_status(self, req_id: str, status: str) -> bool:
        """Update requirement status (pending, in_progress, implemented, verified, superseded)."""
        valid_statuses = ["pending", "in_progress", "implemented", "verified", "superseded"]
        if status not in valid_statuses:
            return False
        
        req = self.update_requirement(req_id, {"status": status})
        return req is not None
    
    def set_requirement_elaboration(self, req_id: str, elaboration: str, 
                                     acceptance_criteria: Optional[List[str]] = None,
                                     conversation_context: Optional[str] = None) -> bool:
        """Set the elaboration and acceptance criteria for a requirement."""
        updates = {"elaboration": elaboration}
        if acceptance_criteria:
            updates["acceptance_criteria"] = acceptance_criteria
        if conversation_context:
            updates["conversation_context"] = conversation_context
        
        req = self.update_requirement(req_id, updates)
        return req is not None
    
    def link_test_spec(self, req_id: str, test_spec_id: str) -> bool:
        """Link a requirement to its test specification."""
        req = self.update_requirement(req_id, {"test_spec_id": test_spec_id})
        return req is not None
    
    def get_requirements_by_status(self, status: str) -> List[Requirement]:
        """Get all requirements with a specific status."""
        all_reqs = self.list_requirements(include_superseded=(status == "superseded"))
        return [r for r in all_reqs if r.status == status]
    
    def get_incomplete_requirements(self) -> List[Requirement]:
        """Get requirements that need refinement (no elaboration or acceptance criteria)."""
        all_reqs = self.list_requirements()
        return [r for r in all_reqs if not r.is_complete()]
    
    # ==================== Specifications ====================
    
    def add_specification(self, spec: Specification, embedding: List[float]) -> None:
        """Add or update a specification."""
        self.specifications.upsert(
            ids=[spec.id],
            embeddings=[embedding],
            metadatas=[spec.to_dict()],
            documents=[spec.description]
        )
    
    def get_specification(self, spec_id: str) -> Optional[Specification]:
        """Get a specification by ID."""
        result = self.specifications.get(ids=[spec_id], include=["metadatas"])
        if result["ids"]:
            return Specification.from_dict(result["metadatas"][0])
        return None
    
    def list_specifications(self, req_id: Optional[str] = None, include_superseded: bool = False) -> List[Specification]:
        """List specifications, optionally filtered by parent requirement."""
        result = self.specifications.get(include=["metadatas"])
        specs = [Specification.from_dict(m) for m in result["metadatas"]]
        
        if not include_superseded:
            specs = [s for s in specs if s.superseded_at is None]
        
        if req_id:
            specs = [s for s in specs if s.parent_req == req_id]
        
        return specs
    
    def get_specifications_for_requirement(self, req_id: str) -> List[Specification]:
        """Get all specifications for a requirement."""
        return self.list_specifications(req_id=req_id)
    
    def update_specification(self, spec_id: str, updates: Dict[str, Any]) -> Optional[Specification]:
        """Update specific fields of a specification."""
        spec = self.get_specification(spec_id)
        if not spec:
            return None
        
        for key, value in updates.items():
            if hasattr(spec, key):
                setattr(spec, key, value)
        
        result = self.specifications.get(ids=[spec_id], include=["embeddings"])
        if result["embeddings"] is not None and len(result["embeddings"]) > 0:
            self.add_specification(spec, result["embeddings"][0])
        
        return spec
    
    def supersede_specification(self, spec_id: str, new_spec_id: Optional[str] = None) -> bool:
        """Mark a specification as superseded."""
        spec = self.get_specification(spec_id)
        if spec and not spec.superseded_at:
            updates = {"superseded_at": datetime.now(timezone.utc).isoformat()}
            if new_spec_id:
                updates["superseded_by"] = new_spec_id
            self.update_specification(spec_id, updates)
            return True
        return False
    
    def search_specifications(self, query_embedding: List[float], n: int = 5) -> List[Dict]:
        """Search specifications by semantic similarity."""
        results = self.specifications.query(
            query_embeddings=[query_embedding],
            n_results=n,
            include=["metadatas", "documents", "distances"]
        )
        
        return [
            {
                "id": results["ids"][0][i],
                "specification": Specification.from_dict(results["metadatas"][0][i]),
                "distance": results["distances"][0][i] if results["distances"] else None
            }
            for i in range(len(results["ids"][0]))
        ]
    
    # ==================== Patterns ====================
    
    def add_pattern(self, pattern: Pattern, embedding: List[float]) -> None:
        """Add or update a pattern."""
        self.patterns.upsert(
            ids=[pattern.id],
            embeddings=[embedding],
            metadatas=[{
                **pattern.to_dict(),
                "applies_to": json.dumps(pattern.applies_to)
            }],
            documents=[pattern.description]
        )
    
    def get_pattern(self, pattern_id: str) -> Optional[Pattern]:
        """Get a pattern by ID."""
        result = self.patterns.get(ids=[pattern_id], include=["metadatas"])
        if result["ids"]:
            meta = result["metadatas"][0]
            meta["applies_to"] = json.loads(meta["applies_to"])
            return Pattern.from_dict(meta)
        return None
    
    def list_patterns(self, include_deprecated: bool = False) -> List[Pattern]:
        """List all patterns."""
        result = self.patterns.get(include=["metadatas"])
        patterns = []
        for m in result["metadatas"]:
            m["applies_to"] = json.loads(m["applies_to"])
            patterns.append(Pattern.from_dict(m))
        
        if not include_deprecated:
            patterns = [p for p in patterns if p.status == "active"]
        
        return patterns
    
    def get_patterns_for_requirement(self, req_id: str) -> List[Pattern]:
        """Get all patterns that apply to a requirement."""
        all_patterns = self.list_patterns()
        return [p for p in all_patterns if req_id in p.applies_to]
    
    def add_requirement_to_pattern(self, pattern_id: str, req_id: str) -> bool:
        """Add a requirement to a pattern's applies_to list."""
        pattern = self.get_pattern(pattern_id)
        if pattern and req_id not in pattern.applies_to:
            pattern.applies_to.append(req_id)
            result = self.patterns.get(ids=[pattern_id], include=["embeddings"])
            if result["embeddings"] is not None and len(result["embeddings"]) > 0:
                self.add_pattern(pattern, result["embeddings"][0])
            return True
        return False
    
    def search_patterns(self, query_embedding: List[float], n: int = 5) -> List[Dict]:
        """Search patterns by semantic similarity."""
        results = self.patterns.query(
            query_embeddings=[query_embedding],
            n_results=n,
            include=["metadatas", "documents", "distances"]
        )
        
        found = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            meta["applies_to"] = json.loads(meta["applies_to"])
            found.append({
                "id": results["ids"][0][i],
                "pattern": Pattern.from_dict(meta),
                "distance": results["distances"][0][i] if results["distances"] else None
            })
        return found
    
    # ==================== Implementations ====================
    
    def add_implementation(self, impl: Implementation, embedding: List[float]) -> None:
        """Add or update an implementation."""
        meta = impl.to_dict()
        # ChromaDB needs JSON strings for complex types
        meta["satisfies"] = json.dumps(impl.satisfies)
        meta["satisfies_specs"] = json.dumps(impl.satisfies_specs or [])
        meta["satisfies_patterns"] = json.dumps(impl.satisfies_patterns or [])
        
        self.implementations.upsert(
            ids=[impl.id],
            embeddings=[embedding],
            metadatas=[meta],
            documents=[impl.content]
        )
    
    def get_implementation(self, impl_id: str) -> Optional[Implementation]:
        """Get an implementation by ID."""
        result = self.implementations.get(ids=[impl_id], include=["metadatas"])
        if result["ids"]:
            meta = result["metadatas"][0]
            meta["satisfies"] = json.loads(meta.get("satisfies", "[]"))
            meta["satisfies_specs"] = json.loads(meta.get("satisfies_specs", "[]"))
            meta["satisfies_patterns"] = json.loads(meta.get("satisfies_patterns", "[]"))
            return Implementation.from_dict(meta)
        return None
    
    def search_implementations(self, query_embedding: List[float], n: int = 10) -> List[Dict]:
        """Search implementations by semantic similarity."""
        results = self.implementations.query(
            query_embeddings=[query_embedding],
            n_results=n,
            include=["metadatas", "documents", "distances"]
        )
        
        impls = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            meta["satisfies"] = json.loads(meta.get("satisfies", "[]"))
            meta["satisfies_specs"] = json.loads(meta.get("satisfies_specs", "[]"))
            meta["satisfies_patterns"] = json.loads(meta.get("satisfies_patterns", "[]"))
            impls.append({
                "id": results["ids"][0][i],
                "implementation": Implementation.from_dict(meta),
                "distance": results["distances"][0][i] if results["distances"] else None
            })
        return impls
    
    def _parse_impl_meta(self, meta: Dict) -> Implementation:
        """Parse implementation metadata from ChromaDB."""
        meta["satisfies"] = json.loads(meta.get("satisfies", "[]"))
        meta["satisfies_specs"] = json.loads(meta.get("satisfies_specs", "[]"))
        meta["satisfies_patterns"] = json.loads(meta.get("satisfies_patterns", "[]"))
        return Implementation.from_dict(meta)
    
    def get_implementations_for_requirement(self, req_id: str) -> List[Implementation]:
        """Get all implementations linked to a requirement."""
        result = self.implementations.get(include=["metadatas"])
        impls = []
        for meta in result["metadatas"]:
            impl = self._parse_impl_meta(meta)
            if any(s["req_id"] == req_id for s in impl.satisfies):
                impls.append(impl)
        return impls
    
    def get_implementations_for_specification(self, spec_id: str) -> List[Implementation]:
        """Get all implementations linked to a specification."""
        result = self.implementations.get(include=["metadatas"])
        impls = []
        for meta in result["metadatas"]:
            impl = self._parse_impl_meta(meta)
            if spec_id in (impl.satisfies_specs or []):
                impls.append(impl)
        return impls
    
    def get_implementations_for_pattern(self, pattern_id: str) -> List[Implementation]:
        """Get all implementations linked to a pattern."""
        result = self.implementations.get(include=["metadatas"])
        impls = []
        for meta in result["metadatas"]:
            impl = self._parse_impl_meta(meta)
            if pattern_id in (impl.satisfies_patterns or []):
                impls.append(impl)
        return impls
    
    def link_implementation_to_spec(self, impl_id: str, spec_id: str) -> bool:
        """Link an existing implementation to a specification."""
        impl = self.get_implementation(impl_id)
        if impl:
            specs = impl.satisfies_specs or []
            if spec_id not in specs:
                specs.append(spec_id)
                impl.satisfies_specs = specs
                result = self.implementations.get(ids=[impl_id], include=["embeddings"])
                if result["embeddings"] and len(result["embeddings"]) > 0:
                    self.add_implementation(impl, result["embeddings"][0])
                return True
        return False
    
    def link_implementation_to_pattern(self, impl_id: str, pattern_id: str) -> bool:
        """Link an existing implementation to a pattern."""
        impl = self.get_implementation(impl_id)
        if impl:
            patterns = impl.satisfies_patterns or []
            if pattern_id not in patterns:
                patterns.append(pattern_id)
                impl.satisfies_patterns = patterns
                result = self.implementations.get(ids=[impl_id], include=["embeddings"])
                if result["embeddings"] and len(result["embeddings"]) > 0:
                    self.add_implementation(impl, result["embeddings"][0])
                return True
        return False
    
    # ==================== Chat Messages ====================
    
    def add_chat_message(
        self, 
        msg_id: str, 
        content: str, 
        embedding: List[float],
        session: str,
        role: str,
        timestamp: str
    ) -> None:
        """Add a chat message for context retrieval."""
        self.chat_messages.upsert(
            ids=[msg_id],
            embeddings=[embedding],
            metadatas=[{
                "session": session,
                "role": role,
                "timestamp": timestamp
            }],
            documents=[content]
        )
    
    def search_chat(self, query_embedding: List[float], n: int = 10) -> List[Dict]:
        """Search chat history by semantic similarity."""
        results = self.chat_messages.query(
            query_embeddings=[query_embedding],
            n_results=n,
            include=["metadatas", "documents", "distances"]
        )
        
        return [
            {
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] if results["distances"] else None
            }
            for i in range(len(results["ids"][0]))
        ]
    
    # ==================== Utilities ====================
    
    def stats(self) -> Dict[str, int]:
        """Get collection statistics."""
        return {
            "requirements": self.requirements.count(),
            "implementations": self.implementations.count(),
            "chat_messages": self.chat_messages.count()
        }


def generate_impl_id(file: str, lines: str) -> str:
    """Generate a stable ID for an implementation chunk."""
    return hashlib.sha256(f"{file}:{lines}".encode()).hexdigest()[:16]


def generate_content_hash(content: str) -> str:
    """Generate a hash of content for change detection."""
    return hashlib.sha256(content.encode()).hexdigest()
