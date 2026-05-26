"""Tests for the LSP-backed PyIndexer (M16.3).

Same shape as ``test_indexers_js.py``:

- ``TestHelpers``: unit tests for module-level helpers (URI/path
  conversion, project walking, snippet reading, import detection).
  No subprocess needed.
- ``TestSoftFail``: behavioral tests for the indexer when pylsp is
  not importable. Asserts the indexer warns once and returns "".
- ``TestIntegration``: end-to-end against a real pylsp. Skipped
  unless ``python-lsp-server`` is importable.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import warnings
from pathlib import Path

import pytest

from loom import indexers_py


HAS_PYLSP = importlib.util.find_spec("pylsp") is not None


class TestHelpers:
    def test_path_to_uri_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            p = Path(f.name)
        try:
            uri = indexers_py._path_to_uri(p)
            assert uri.startswith("file://")
            back = indexers_py._uri_to_path(uri)
            assert back.resolve() == p.resolve()
        finally:
            p.unlink(missing_ok=True)

    def test_uri_to_path_decodes_percent_encoding(self):
        path = indexers_py._uri_to_path("file:///c%3A/foo/bar.py")
        if sys.platform == "win32":
            assert "c:" in str(path).lower()
        assert "%3A" not in str(path)

    def test_walk_project_finds_py_files_recursively(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("pass")
        (tmp_path / "src" / "b.pyi").write_text("def f() -> int: ...")
        (tmp_path / "src" / "nested").mkdir()
        (tmp_path / "src" / "nested" / "c.py").write_text("pass")
        # Should be ignored:
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "skip.py").write_text("pass")
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "lib_skip.py").write_text("pass")
        (tmp_path / "ignore.txt").write_text("not py")

        found = list(indexers_py._walk_project(tmp_path))
        names = sorted(p.name for p in found)
        assert names == ["a.py", "b.pyi", "c.py"]

    def test_walk_project_ignores_node_modules_too(self, tmp_path):
        # Some Python projects ship a JS frontend; node_modules should
        # be skipped even though we're walking Python sources.
        (tmp_path / "a.py").write_text("pass")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg.py").write_text("pass")
        found = list(indexers_py._walk_project(tmp_path))
        names = sorted(p.name for p in found)
        assert names == ["a.py"]

    def test_read_snippet_includes_lines_after(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("a\nb\nc\nd\ne\nf\n")
        snippet = indexers_py._read_snippet(f, line=1, after=2)
        assert snippet == ["b", "c", "d"]

    def test_read_snippet_returns_empty_for_missing_file(self, tmp_path):
        snippet = indexers_py._read_snippet(tmp_path / "nope.py", line=0)
        assert snippet == []

    def test_relative_to_falls_back_to_absolute(self, tmp_path):
        outside = tmp_path / ".." / "outside.py"
        rel = indexers_py._relative_to(outside, tmp_path)
        assert rel

    def test_flatten_symbols_handles_document_symbol(self):
        symbols = [
            {
                "name": "outer",
                "kind": 12,
                "selectionRange": {"start": {"line": 0, "character": 4}},
                "children": [
                    {"name": "inner", "kind": 6,
                     "selectionRange": {"start": {"line": 1, "character": 8}},
                     "children": []},
                ],
            },
        ]
        flat = indexers_py._flatten_symbols(symbols)
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
                    "uri": "file:///x.py",
                    "range": {"start": {"line": 5, "character": 0}},
                },
            },
        ]
        flat = indexers_py._flatten_symbols(symbols)
        assert len(flat) == 1
        assert flat[0]["position"] == {"line": 5, "character": 0}

    # ----------------------------------------------------------------
    # Python-specific import detection
    # ----------------------------------------------------------------

    def test_is_import_ref_detects_plain_import(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text(
            "import foo\n"
            "def bar():\n"
            "    return foo.run()\n"
        )
        assert indexers_py._is_import_ref(f, 0) is True
        assert indexers_py._is_import_ref(f, 1) is False
        assert indexers_py._is_import_ref(f, 2) is False

    def test_is_import_ref_detects_import_as(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("import foo as bar\nbar.run()\n")
        assert indexers_py._is_import_ref(f, 0) is True
        assert indexers_py._is_import_ref(f, 1) is False

    def test_is_import_ref_detects_import_list(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("import foo, bar, baz\nfoo.run()\n")
        assert indexers_py._is_import_ref(f, 0) is True

    def test_is_import_ref_detects_from_import(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text(
            "from foo import bar\n"
            "def use(): return bar()\n"
        )
        assert indexers_py._is_import_ref(f, 0) is True
        assert indexers_py._is_import_ref(f, 1) is False

    def test_is_import_ref_detects_relative_from_import(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("from .foo import bar\n")
        assert indexers_py._is_import_ref(f, 0) is True

    def test_is_import_ref_detects_relative_dot_import(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("from . import foo\n")
        assert indexers_py._is_import_ref(f, 0) is True

    def test_is_import_ref_detects_parenthesized_from_import(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("from foo import (\n    bar,\n    baz,\n)\nbar()\n")
        # First line is the "from foo import (" — matches.
        assert indexers_py._is_import_ref(f, 0) is True
        # Continuation lines inside () are NOT matched by the regex,
        # which is fine — pylsp won't return refs for those lines
        # because they're the import target names not call sites.
        assert indexers_py._is_import_ref(f, 4) is False

    def test_is_import_ref_does_not_match_non_import_lines(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text(
            "def import_foo():\n"  # not an import despite the word
            "    return 1\n"
            "x = importlib.import_module('foo')\n"  # not a top-level import
        )
        assert indexers_py._is_import_ref(f, 0) is False
        assert indexers_py._is_import_ref(f, 2) is False

    def test_is_import_ref_returns_false_for_missing_file(self, tmp_path):
        assert indexers_py._is_import_ref(tmp_path / "nope.py", 0) is False

    def test_read_signature_line_strips_trailing_colon(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("class Foo(Bar):\n    def x(self):\n        pass\n")
        assert indexers_py._read_signature_line(f, 0) == "class Foo(Bar)"

    def test_read_signature_line_handles_function_def(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("def fetch(url: str, retries: int = 3) -> Result:\n    pass\n")
        assert (
            indexers_py._read_signature_line(f, 0)
            == "def fetch(url: str, retries: int = 3) -> Result"
        )

    def test_read_signature_line_handles_blank_first_line(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("\n\nclass Foo: pass\n")
        # First non-empty line within 3-line window
        assert indexers_py._read_signature_line(f, 0) == "class Foo: pass"


class TestSoftFail:
    def test_returns_empty_when_module_missing(self, tmp_path):
        idx = indexers_py.PyIndexer(
            root=tmp_path,
            server_cmd=["definitely-not-a-real-binary-loom-xyz"],
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = idx.context_for(tmp_path / "nope.py")
        assert result == ""
        # Subsequent calls should NOT warn again — _unavailable is sticky.
        with warnings.catch_warnings(record=True) as caught2:
            warnings.simplefilter("always")
            result = idx.context_for(tmp_path / "nope.py")
        assert result == ""
        assert len(caught2) == 0

    def test_supports_only_python_languages(self):
        idx = indexers_py.PyIndexer()
        assert idx.supports("python")
        assert idx.supports("py")
        assert not idx.supports("javascript")
        assert not idx.supports("typescript")
        assert not idx.supports("go")


class TestHealth:
    def test_health_with_override_reports_ok(self, tmp_path):
        idx = indexers_py.PyIndexer(
            root=tmp_path,
            server_cmd=["fake-binary", "--stdio"],
        )
        h = idx.health()
        assert h["ok"] is True
        assert "fake-binary" in h["detail"]

    @pytest.mark.skipif(HAS_PYLSP, reason="pylsp IS importable in this env")
    def test_health_reports_not_ok_when_module_missing(self):
        idx = indexers_py.PyIndexer()
        h = idx.health()
        assert h["ok"] is False
        assert "python-lsp-server" in h["detail"]

    @pytest.mark.skipif(not HAS_PYLSP, reason="pylsp not importable")
    def test_health_reports_ok_when_module_present(self):
        idx = indexers_py.PyIndexer()
        h = idx.health()
        assert h["ok"] is True
        assert "pylsp" in h["detail"]


@pytest.mark.skipif(not HAS_PYLSP, reason="python-lsp-server not importable")
class TestIntegration:
    @pytest.fixture
    def fixture_root(self, tmp_path):
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "retry.py").write_text(
            "def fetch_with_retry(url, attempts=3):\n"
            "    for i in range(attempts):\n"
            "        try:\n"
            "            return do_fetch(url)\n"
            "        except Exception:\n"
            "            if i == attempts - 1:\n"
            "                return None\n"
            "    return None\n"
            "\n"
            "def do_fetch(url):\n"
            "    raise NotImplementedError\n"
        )
        (src / "consumer.py").write_text(
            "from .retry import fetch_with_retry\n"
            "\n"
            "def run(url):\n"
            "    result = fetch_with_retry(url, attempts=3)\n"
            "    if result is None:\n"
            "        return 'failed'\n"
            "    return result\n"
        )
        return tmp_path, src

    def test_context_for_returns_lsp_block(self, fixture_root):
        root, src = fixture_root
        idx = indexers_py.PyIndexer(root=root)
        try:
            ctx = idx.context_for(src / "retry.py")
            # The header line is the canary that the LSP path actually
            # produced output (vs the soft-fail empty-string path).
            assert "SEMANTIC CONTEXT" in ctx, (
                f"expected LSP context block, got: {ctx[:200]!r}"
            )
            # Should reference the consumer call site.
            assert "consumer.py" in ctx or "fetch_with_retry" in ctx
        finally:
            idx.shutdown()

    def test_context_for_filters_import_lines(self, fixture_root):
        root, src = fixture_root
        idx = indexers_py.PyIndexer(root=root)
        try:
            ctx = idx.context_for(src / "retry.py")
            # The consumer's `from .retry import fetch_with_retry` is
            # an import reference; it should NOT appear as a ref site.
            # We can detect this via the line number — if the import
            # line was kept, the output would contain ":1" pointing
            # at consumer.py line 1.
            assert "consumer.py:1\n" not in ctx, (
                "import-line ref leaked into output"
            )
        finally:
            idx.shutdown()

    def test_context_for_missing_file_returns_empty(self, fixture_root):
        root, _ = fixture_root
        idx = indexers_py.PyIndexer(root=root)
        try:
            ctx = idx.context_for(root / "does_not_exist.py")
            assert ctx == ""
        finally:
            idx.shutdown()
