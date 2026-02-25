"""
Loom Store - Vector database for requirements and implementations.

Uses ChromaDB for embeddings + metadata storage.
"""

import json
import hashlib
from datetime import datetime
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
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Requirement":
        return cls(**d)


@dataclass 
class Implementation:
    """A code chunk linked to requirements."""
    id: str
    file: str
    lines: str  # "42-78"
    content: str
    content_hash: str
    timestamp: str
    satisfies: List[Dict[str, str]]  # [{"req_id": "...", "req_version": "..."}]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Implementation":
        return cls(**d)


class LoomStore:
    """
    Vector store for Loom data.
    
    Collections:
    - requirements: Requirement embeddings + metadata
    - implementations: Code chunk embeddings + metadata
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
        
        self.implementations = self.client.get_or_create_collection(
            name="implementations", 
            metadata={"description": "Code chunks linked to requirements"}
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
    
    # ==================== Implementations ====================
    
    def add_implementation(self, impl: Implementation, embedding: List[float]) -> None:
        """Add or update an implementation."""
        self.implementations.upsert(
            ids=[impl.id],
            embeddings=[embedding],
            metadatas=[{
                **impl.to_dict(),
                "satisfies": json.dumps(impl.satisfies)  # ChromaDB needs string
            }],
            documents=[impl.content]
        )
    
    def get_implementation(self, impl_id: str) -> Optional[Implementation]:
        """Get an implementation by ID."""
        result = self.implementations.get(ids=[impl_id], include=["metadatas"])
        if result["ids"]:
            meta = result["metadatas"][0]
            meta["satisfies"] = json.loads(meta["satisfies"])
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
            meta["satisfies"] = json.loads(meta["satisfies"])
            impls.append({
                "id": results["ids"][0][i],
                "implementation": Implementation.from_dict(meta),
                "distance": results["distances"][0][i] if results["distances"] else None
            })
        return impls
    
    def get_implementations_for_requirement(self, req_id: str) -> List[Implementation]:
        """Get all implementations linked to a requirement."""
        # This requires scanning - ChromaDB doesn't support JSON queries well
        result = self.implementations.get(include=["metadatas"])
        impls = []
        for meta in result["metadatas"]:
            meta["satisfies"] = json.loads(meta["satisfies"])
            impl = Implementation.from_dict(meta)
            if any(s["req_id"] == req_id for s in impl.satisfies):
                impls.append(impl)
        return impls
    
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
