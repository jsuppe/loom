"""
Tests for MCP resource-URI plumbing.

These exercise the pure helpers (`_parse_resource_uri`, `_KINDS`) without
spinning up the MCP SDK or an async event loop. Full-loop tests belong
behind an optional `mcp` dep and live elsewhere.
"""

import sys
from pathlib import Path

import pytest

# Import the server module by path so we can run these tests without the
# mcp SDK installed. We need to skip import-time errors if mcp is missing.
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

mcp = pytest.importorskip("mcp", reason="mcp SDK required for server module")

sys.path.insert(0, str(REPO_ROOT / "mcp_server"))
import server  # noqa: E402


class TestParseResourceUri:
    def test_requirements_parsed(self):
        assert server._parse_resource_uri("loom://requirements/myproj") == (
            "requirements", "myproj"
        )

    def test_testspec_parsed(self):
        assert server._parse_resource_uri("loom://testspec/p2") == (
            "testspec", "p2"
        )

    def test_drift_parsed(self):
        assert server._parse_resource_uri("loom://drift/p3") == ("drift", "p3")

    def test_non_loom_uri_raises(self):
        with pytest.raises(ValueError, match="Not a loom URI"):
            server._parse_resource_uri("http://example.com")

    def test_missing_project_raises(self):
        with pytest.raises(ValueError, match="Malformed"):
            server._parse_resource_uri("loom://requirements/")

    def test_missing_kind_raises(self):
        # Empty kind → "Malformed" (not "Unknown kind") because the split
        # yields ("", "project"), so first check fires first.
        with pytest.raises(ValueError, match="Malformed"):
            server._parse_resource_uri("loom:///myproj")

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="Unknown resource kind"):
            server._parse_resource_uri("loom://bogus/p")


class TestKinds:
    def test_all_three_kinds_declared(self):
        assert set(server._KINDS.keys()) == {"requirements", "testspec", "drift"}

    def test_requirements_is_markdown(self):
        mime, _ = server._KINDS["requirements"]
        assert mime == "text/markdown"

    def test_drift_is_json(self):
        mime, _ = server._KINDS["drift"]
        assert mime == "application/json"
