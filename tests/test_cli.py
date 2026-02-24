"""
Tests for Loom CLI - specifically the link command auto-detect behavior.

Run with: pytest tests/test_cli.py -v
"""

import pytest
import subprocess
import tempfile
import shutil
import os
from pathlib import Path


@pytest.fixture
def temp_project():
    """Create a temporary project with test data."""
    project_name = "test_cli_project"
    data_dir = Path.home() / ".openclaw" / "loom" / project_name
    
    # Clean up any existing test data
    if data_dir.exists():
        shutil.rmtree(data_dir)
    
    yield project_name
    
    # Cleanup after test
    if data_dir.exists():
        shutil.rmtree(data_dir)


@pytest.fixture
def temp_code_file():
    """Create a temporary code file to link."""
    fd, path = tempfile.mkstemp(suffix=".py")
    with os.fdopen(fd, 'w') as f:
        f.write('''
# Dashboard component
def render_dashboard(project):
    """Shows project status, metrics, and blockers."""
    return {
        "status": project.status,
        "metrics": get_metrics(),
        "blockers": get_blockers()
    }
''')
    yield path
    os.unlink(path)


def run_loom(args: list, input_text: str = None) -> tuple:
    """Run loom CLI and return (stdout, stderr, returncode)."""
    cmd = [str(Path.home() / ".openclaw/skills/loom/scripts/loom")] + args
    result = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True
    )
    return result.stdout, result.stderr, result.returncode


class TestLinkAutoDetect:
    """Tests for auto-detection in loom link command."""
    
    def test_link_auto_detects_requirements(self, temp_project, temp_code_file):
        """Link command auto-detects relevant requirements from code."""
        # First, add a requirement
        stdout, stderr, rc = run_loom(
            ["-p", temp_project, "extract"],
            input_text="REQUIREMENT: ui | Dashboard shows project status and metrics"
        )
        assert rc == 0
        assert "REQ-" in stdout
        
        # Now link the code file - should auto-detect
        stdout, stderr, rc = run_loom(
            ["-p", temp_project, "link", temp_code_file]
        )
        
        assert rc == 0
        assert "Detected requirements" in stdout
        assert "Dashboard" in stdout
    
    def test_link_excludes_superseded_from_auto_detect(self, temp_project, temp_code_file):
        """CRITICAL: Link command should NOT suggest superseded requirements."""
        # Add old requirement
        stdout, _, _ = run_loom(
            ["-p", temp_project, "extract"],
            input_text="REQUIREMENT: ui | Dashboard shows status only"
        )
        # Extract the REQ ID
        old_req_id = None
        for line in stdout.split('\n'):
            if "REQ-" in line and "✓" in line:
                old_req_id = line.split("REQ-")[1].split(":")[0].strip()
                break
        
        assert old_req_id is not None, f"Could not extract REQ ID from: {stdout}"
        old_req_id = f"REQ-{old_req_id}"
        
        # Add new requirement (supersedes old)
        stdout, _, _ = run_loom(
            ["-p", temp_project, "extract"],
            input_text="REQUIREMENT: ui | Dashboard shows status and agent metrics"
        )
        new_req_id = None
        for line in stdout.split('\n'):
            if "REQ-" in line and "✓" in line:
                new_req_id = line.split("REQ-")[1].split(":")[0].strip()
                break
        new_req_id = f"REQ-{new_req_id}"
        
        # Supersede the old requirement
        stdout, _, rc = run_loom(["-p", temp_project, "supersede", old_req_id])
        assert rc == 0
        
        # Link should NOT suggest the superseded requirement
        stdout, stderr, rc = run_loom(
            ["-p", temp_project, "link", temp_code_file]
        )
        
        # The old (superseded) requirement should NOT appear in suggestions
        assert old_req_id not in stdout, \
            f"Superseded requirement {old_req_id} should not be suggested. Output:\n{stdout}"
        
        # The new requirement SHOULD appear
        assert new_req_id in stdout or "Dashboard" in stdout, \
            f"New requirement should be suggested. Output:\n{stdout}"


class TestCheckDrift:
    """Tests for drift checking."""
    
    def test_check_shows_drift_for_superseded_link(self, temp_project, temp_code_file):
        """Check command shows drift when linked to superseded requirement."""
        # Add requirement
        stdout, _, _ = run_loom(
            ["-p", temp_project, "extract"],
            input_text="REQUIREMENT: ui | Dashboard shows basic metrics"
        )
        req_id = None
        for line in stdout.split('\n'):
            if "REQ-" in line and "✓" in line:
                req_id = line.split("REQ-")[1].split(":")[0].strip()
                break
        req_id = f"REQ-{req_id}"
        
        # Link code to requirement
        run_loom(["-p", temp_project, "link", temp_code_file, "--req", req_id])
        
        # Supersede the requirement
        run_loom(["-p", temp_project, "supersede", req_id])
        
        # Check should show drift
        stdout, stderr, rc = run_loom(["-p", temp_project, "check", temp_code_file])
        
        assert rc != 0, "Check should fail (non-zero exit) when drift detected"
        assert "DRIFT" in stdout or "superseded" in stdout.lower(), \
            f"Should indicate drift. Output:\n{stdout}"
