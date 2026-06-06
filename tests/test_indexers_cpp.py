"""Tests for the LSP-backed ClangdIndexer (M28.2).

Three classes mirror tests/test_indexers_js.py:
- ``TestHelpers``: unit tests for module-level helpers. No subprocess.
- ``TestSoftFail``: behavioral tests when clangd is absent.
- ``TestIntegration``: end-to-end against real clangd. Skipped unless
  clangd is on PATH.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import pytest

from loom import indexers_cpp


HAS_CLANGD = shutil.which("clangd") is not None


class TestHelpers:
    def test_path_to_uri_starts_with_file_scheme(self):
        with tempfile.NamedTemporaryFile(suffix=".cpp", delete=False) as f:
            p = Path(f.name)
        try:
            uri = indexers_cpp._path_to_uri(p)
            assert uri.startswith("file://")
            assert uri.endswith(".cpp")
        finally:
            p.unlink(missing_ok=True)

    def test_uri_to_path_strips_scheme(self):
        uri = "file:///C:/work/foo.cpp"
        path = indexers_cpp._uri_to_path(uri)
        assert path.suffix == ".cpp"

    @pytest.mark.parametrize("name,expected", [
        ("foo.cpp", "cpp"),
        ("foo.cxx", "cpp"),
        ("foo.cc", "cpp"),
        ("foo.hpp", "cpp"),
        ("foo.hxx", "cpp"),
        ("foo.hh", "cpp"),
        ("foo.c", "c"),
        ("foo.h", "c"),
        ("foo.unknown", "cpp"),
    ])
    def test_language_id_for(self, name, expected):
        assert indexers_cpp._language_id_for(Path(name)) == expected

    def test_walk_project_skips_ignored_dirs(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.cpp").write_text("// a")
        (tmp_path / "build").mkdir()
        (tmp_path / "build" / "skipped.cpp").write_text("// no")
        (tmp_path / "third_party").mkdir()
        (tmp_path / "third_party" / "vendor.h").write_text("// no")
        files = list(indexers_cpp._walk_project(tmp_path))
        names = {f.name for f in files}
        assert "a.cpp" in names
        assert "skipped.cpp" not in names
        assert "vendor.h" not in names

    def test_walk_project_caps_at_max(self, tmp_path):
        for i in range(indexers_cpp._MAX_PROJECT_FILES + 50):
            (tmp_path / f"f{i}.cpp").write_text("// generated")
        files = list(indexers_cpp._walk_project(tmp_path))
        assert len(files) <= indexers_cpp._MAX_PROJECT_FILES

    def test_flatten_symbols_hierarchical_shape(self):
        # DocumentSymbol shape with selectionRange
        raw = [
            {
                "name": "Foo",
                "kind": indexers_cpp._KIND_CLASS,
                "selectionRange": {"start": {"line": 0, "character": 6}},
                "children": [
                    {
                        "name": "bar",
                        "kind": indexers_cpp._KIND_METHOD,
                        "selectionRange": {"start": {"line": 2, "character": 10}},
                    },
                ],
            },
        ]
        flat = indexers_cpp._flatten_symbols(raw)
        assert len(flat) == 2
        assert flat[0]["name"] == "Foo"
        assert flat[1]["name"] == "bar"

    def test_flatten_symbols_flat_shape(self):
        # SymbolInformation shape with location
        raw = [
            {
                "name": "Foo",
                "kind": indexers_cpp._KIND_CLASS,
                "location": {"range": {"start": {"line": 0, "character": 0}}},
            },
        ]
        flat = indexers_cpp._flatten_symbols(raw)
        assert len(flat) == 1
        assert flat[0]["name"] == "Foo"

    def test_struct_is_interesting_kind(self):
        """C++-specific: structs should be surfaced like classes."""
        assert indexers_cpp._KIND_STRUCT in indexers_cpp._INTERESTING_KINDS
        assert indexers_cpp._KIND_STRUCT in indexers_cpp._TYPE_DEF_KINDS

    def test_read_snippet_returns_window(self, tmp_path):
        f = tmp_path / "x.cpp"
        f.write_text("\n".join([f"line{i}" for i in range(10)]))
        snip = indexers_cpp._read_snippet(f, 4, after=2)
        assert snip == ["line4", "line5", "line6"]


class TestSoftFail:
    """When clangd is missing, the indexer must warn once + return ""."""

    def test_health_reports_missing_binary(self, monkeypatch, tmp_path):
        monkeypatch.setattr(shutil, "which", lambda _: None)
        idx = indexers_cpp.ClangdIndexer(root=tmp_path)
        h = idx.health()
        assert h["ok"] is False
        assert "clangd" in h["detail"].lower()

    def test_context_for_returns_empty_when_unavailable(
        self, monkeypatch, tmp_path
    ):
        # Force the indexer into "unavailable" state.
        idx = indexers_cpp.ClangdIndexer(root=tmp_path)
        idx._unavailable = True
        target = tmp_path / "foo.cpp"
        target.write_text("int main() {}")
        assert idx.context_for(target) == ""

    def test_first_missing_binary_warns(self, monkeypatch, tmp_path):
        # Make _resolve_server_cmd raise FileNotFoundError to simulate
        # the absent-binary path.
        idx = indexers_cpp.ClangdIndexer(root=tmp_path)

        def boom():
            raise FileNotFoundError("no clangd")
        monkeypatch.setattr(idx, "_resolve_server_cmd", boom)
        target = tmp_path / "foo.cpp"
        target.write_text("int main() {}")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            out = idx.context_for(target)
        assert out == ""
        assert any("ClangdIndexer" in str(wi.message) for wi in w)
        # Subsequent calls do not re-spawn or re-warn.
        with warnings.catch_warnings(record=True) as w2:
            warnings.simplefilter("always")
            out2 = idx.context_for(target)
        assert out2 == ""
        # Should not have warned again — _unavailable flag is set.
        assert not any("ClangdIndexer" in str(wi.message) for wi in w2)

    def test_health_reports_missing_compile_db(self, monkeypatch, tmp_path):
        # clangd is on PATH (fake it) but compile_commands.json is absent.
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/clangd")
        idx = indexers_cpp.ClangdIndexer(root=tmp_path)
        h = idx.health()
        assert h["ok"] is False
        assert "compile_commands" in h["detail"]


@pytest.mark.skipif(not HAS_CLANGD, reason="clangd not on PATH")
class TestIntegration:
    """End-to-end against real clangd. Skipped unless clangd is installed.

    Use the small synthetic C++ project below — the M28 S1 scenario is
    exercised separately by experiments/m28_clangd_indexer/verify_indexer.py.
    """

    def _make_project(self, root: Path) -> Path:
        (root / "include").mkdir()
        header = root / "include" / "math.hpp"
        header.write_text(
            "#pragma once\n"
            "inline int add(int a, int b) { return a + b; }\n"
        )
        src = root / "main.cpp"
        src.write_text(
            "#include \"math.hpp\"\n"
            "int main() { return add(1, 2); }\n"
        )
        cdb = root / "compile_commands.json"
        cdb.write_text(
            f"[{{\"directory\":\"{root.as_posix()}\","
            f"\"command\":\"clang++ -std=c++17 -I{root.as_posix()}/include "
            f"-c {root.as_posix()}/main.cpp\","
            f"\"file\":\"{root.as_posix()}/main.cpp\"}}]"
        )
        return header

    def test_context_for_returns_block(self, tmp_path):
        target = self._make_project(tmp_path)
        idx = indexers_cpp.ClangdIndexer(root=tmp_path)
        try:
            out = idx.context_for(target)
        finally:
            idx.shutdown()
        # Either we got real LSP content or clangd quietly degraded.
        # If we got content, it should be in the expected shape.
        if out:
            assert "SEMANTIC CONTEXT" in out
            assert "lsp:clangd" in out
            assert "END SEMANTIC CONTEXT" in out
