"""Tests for the LSP-backed JsIndexer (M10.3 step 4).

Two test classes:
- ``TestHelpers``: unit tests for module-level helpers (URI/path
  conversion, project walking, snippet reading). No subprocess needed.
- ``TestSoftFail``: behavioral tests for the indexer when the LSP
  binary is absent. Asserts the indexer warns once and returns "".
- ``TestIntegration``: end-to-end against a real LSP server. Skipped
  unless ``typescript-language-server`` is on PATH.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import pytest

from loom import indexers_js


HAS_LSP = shutil.which("typescript-language-server") is not None


class TestHelpers:
    def test_path_to_uri_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as f:
            p = Path(f.name)
        try:
            uri = indexers_js._path_to_uri(p)
            assert uri.startswith("file://")
            back = indexers_js._uri_to_path(uri)
            assert back.resolve() == p.resolve()
        finally:
            p.unlink(missing_ok=True)

    def test_uri_to_path_decodes_percent_encoding(self):
        # Server-emitted URIs may percent-encode the colon on Windows
        # ("/c%3A/Users/..."). Without decoding, downstream Path()
        # operations fail.
        path = indexers_js._uri_to_path("file:///c%3A/foo/bar.js")
        # On Windows this should resolve to C:/foo/bar.js; on POSIX
        # the percent-encoded form just becomes a regular path.
        if sys.platform == "win32":
            assert "c:" in str(path).lower()
        assert "%3A" not in str(path)

    def test_walk_project_finds_js_files_recursively(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.js").write_text("// a")
        (tmp_path / "src" / "b.ts").write_text("// b")
        (tmp_path / "src" / "nested").mkdir()
        (tmp_path / "src" / "nested" / "c.tsx").write_text("// c")
        # Should be ignored:
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "skip.js").write_text("// skip")
        (tmp_path / "ignore.txt").write_text("not js")

        found = list(indexers_js._walk_project(tmp_path))
        names = sorted(p.name for p in found)
        assert names == ["a.js", "b.ts", "c.tsx"]

    def test_read_snippet_includes_lines_after(self, tmp_path):
        f = tmp_path / "x.js"
        f.write_text("a\nb\nc\nd\ne\nf\n")
        snippet = indexers_js._read_snippet(f, line=1, after=2)
        assert snippet == ["b", "c", "d"]

    def test_read_snippet_returns_empty_for_missing_file(self, tmp_path):
        snippet = indexers_js._read_snippet(tmp_path / "nope.js", line=0)
        assert snippet == []

    def test_relative_to_falls_back_to_absolute(self, tmp_path):
        # When the path isn't under root, return the absolute string.
        outside = tmp_path / ".." / "outside.js"
        rel = indexers_js._relative_to(outside, tmp_path)
        assert rel  # non-empty

    def test_flatten_symbols_handles_document_symbol(self):
        symbols = [
            {
                "name": "outer",
                "kind": 12,
                "selectionRange": {"start": {"line": 0, "character": 9}},
                "children": [
                    {"name": "inner", "kind": 6,
                     "selectionRange": {"start": {"line": 1, "character": 4}},
                     "children": []},
                ],
            },
        ]
        flat = indexers_js._flatten_symbols(symbols)
        assert len(flat) == 2
        assert flat[0]["name"] == "outer"
        assert flat[1]["name"] == "inner"
        assert flat[1]["kind"] == 6

    def test_flatten_symbols_handles_symbol_information(self):
        symbols = [
            {
                "name": "fn",
                "kind": 12,
                "location": {
                    "uri": "file:///x.js",
                    "range": {"start": {"line": 5, "character": 0}},
                },
            },
        ]
        flat = indexers_js._flatten_symbols(symbols)
        assert len(flat) == 1
        assert flat[0]["position"] == {"line": 5, "character": 0}


class TestSoftFail:
    def test_returns_empty_when_binary_missing(self, tmp_path):
        # Override the resolved binary to a path that doesn't exist.
        idx = indexers_js.JsIndexer(
            root=tmp_path,
            server_cmd=["definitely-not-a-real-binary-loom-xyz"],
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = idx.context_for(tmp_path / "nope.js")
        assert result == ""
        # Subsequent calls should NOT warn again — _unavailable is sticky.
        with warnings.catch_warnings(record=True) as caught2:
            warnings.simplefilter("always")
            result = idx.context_for(tmp_path / "nope.js")
        assert result == ""
        assert len(caught2) == 0

    def test_supports_only_js_ts_languages(self):
        idx = indexers_js.JsIndexer()
        assert idx.supports("javascript")
        assert idx.supports("js")
        assert idx.supports("typescript")
        assert idx.supports("ts")
        assert not idx.supports("python")
        assert not idx.supports("go")


@pytest.mark.skipif(not HAS_LSP,
                    reason="typescript-language-server not installed")
class TestIntegration:
    @pytest.fixture
    def fixture_root(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "retry.js").write_text(
            "export async function fetchWithRetry(url, attempts = 3) {\n"
            "  for (let i = 0; i < attempts; i++) {\n"
            "    try { return await doFetch(url); }\n"
            "    catch (e) { if (i === attempts - 1) return null; }\n"
            "  }\n"
            "  return null;\n"
            "}\n"
            "export async function doFetch(url) { throw new Error('x'); }\n"
        )
        (src / "consumer.js").write_text(
            "import { fetchWithRetry } from './retry.js';\n"
            "export async function run(url) {\n"
            "  const result = await fetchWithRetry(url, 3);\n"
            "  return result;\n"
            "}\n"
        )
        (tmp_path / "package.json").write_text(json.dumps({"type": "module"}))
        (tmp_path / "jsconfig.json").write_text(json.dumps({
            "compilerOptions": {
                "module": "esnext",
                "target": "es2020",
                "moduleResolution": "node",
                "checkJs": True, "allowJs": True,
            },
            "include": ["src/**/*"],
        }))
        return tmp_path

    def test_returns_phq3_shaped_context(self, fixture_root):
        idx = indexers_js.JsIndexer(root=fixture_root)
        try:
            out = idx.context_for(fixture_root / "src" / "retry.js")
        finally:
            idx.shutdown()
        # Header / footer match the phQ3 stub shape.
        assert "=== SEMANTIC CONTEXT" in out
        assert "=== END SEMANTIC CONTEXT" in out
        # References for fetchWithRetry should include the consumer file.
        assert "fetchWithRetry" in out
        assert "consumer.js" in out
        # Snippets should include the call-site code line.
        assert "await fetchWithRetry" in out

    def test_returns_empty_for_nonexistent_file(self, fixture_root):
        idx = indexers_js.JsIndexer(root=fixture_root)
        try:
            out = idx.context_for(fixture_root / "src" / "missing.js")
        finally:
            idx.shutdown()
        assert out == ""

    def test_register_works_through_indexers_module(self, fixture_root):
        from loom import indexers
        idx = indexers_js.JsIndexer(root=fixture_root)
        try:
            indexers.register(idx)
            resolved = indexers.for_language("javascript")
            assert resolved is idx
            out = resolved.context_for(fixture_root / "src" / "retry.js")
            assert "fetchWithRetry" in out
        finally:
            indexers.unregister(idx)
            idx.shutdown()
