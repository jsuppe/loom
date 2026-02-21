"""
Loom Test Specification Management

Manages test specifications linked to requirements.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field


@dataclass
class TestSpec:
    """Test specification for a requirement."""
    req_id: str
    description: str
    steps: List[str] = field(default_factory=list)
    expected: str = ""
    automated: bool = False
    test_file: Optional[str] = None
    last_verified: Optional[str] = None
    private: bool = False
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict) -> "TestSpec":
        return cls(**d)


class TestSpecStore:
    """Manages test specifications for a project."""
    
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.specs_file = project_dir / ".loom-specs.json"
        self.private_file = project_dir / "PRIVATE.md"
        self._specs: Dict[str, TestSpec] = {}
        self._private_ids: set = set()
        self._load()
    
    def _load(self):
        """Load specs and private list."""
        if self.specs_file.exists():
            data = json.loads(self.specs_file.read_text())
            for req_id, spec_data in data.items():
                self._specs[req_id] = TestSpec.from_dict(spec_data)
        
        if self.private_file.exists():
            self._load_private()
    
    def _load_private(self):
        """Load private requirement IDs from PRIVATE.md."""
        content = self.private_file.read_text()
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('- REQ-') or line.startswith('* REQ-'):
                req_id = line.split()[1].rstrip(':,')
                self._private_ids.add(req_id)
            elif line.startswith('REQ-'):
                req_id = line.split()[0].rstrip(':,')
                self._private_ids.add(req_id)
    
    def _save(self):
        """Save specs to file."""
        data = {req_id: spec.to_dict() for req_id, spec in self._specs.items()}
        self.specs_file.write_text(json.dumps(data, indent=2))
    
    def add_spec(self, spec: TestSpec) -> None:
        """Add or update a test specification."""
        self._specs[spec.req_id] = spec
        self._save()
    
    def get_spec(self, req_id: str) -> Optional[TestSpec]:
        """Get test spec for a requirement."""
        return self._specs.get(req_id)
    
    def list_specs(self, include_private: bool = True) -> List[TestSpec]:
        """List all test specs."""
        specs = list(self._specs.values())
        if not include_private:
            specs = [s for s in specs if s.req_id not in self._private_ids and not s.private]
        return specs
    
    def is_private(self, req_id: str) -> bool:
        """Check if a requirement is marked private."""
        if req_id in self._private_ids:
            return True
        spec = self._specs.get(req_id)
        return spec.private if spec else False
    
    def mark_verified(self, req_id: str) -> bool:
        """Mark a test as verified now."""
        if req_id in self._specs:
            self._specs[req_id].last_verified = datetime.now(timezone.utc).isoformat()
            self._save()
            return True
        return False
    
    def get_private_ids(self) -> set:
        """Get all private requirement IDs."""
        return self._private_ids.copy()


def create_private_template(project_dir: Path) -> Path:
    """Create a PRIVATE.md template."""
    path = project_dir / "PRIVATE.md"
    if not path.exists():
        content = """# Private Requirements

Requirements listed here will be excluded from public documentation.

## How to Use

List requirement IDs that should remain private:

- REQ-xxxxxxxx — Description of why it's private
- REQ-yyyyyyyy — Internal implementation detail

## Patterns (future)

You can also use patterns:
- All requirements from session "internal-*"
- All requirements in domain "security"

---

## Private Requirements

<!-- Add your private requirement IDs below -->

"""
        path.write_text(content)
    return path
