"""
Tests for src/loom/paths.py — M17.1.

Pure function tests on tmp_path-isolated directories so no real
git toplevel can interfere with the assertions.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from loom.paths import normalize_file_path, project_root


class TestProjectRoot:
    def test_finds_git_toplevel(self, tmp_path):
        # Set up: tmp_path is the project root, with a subdirectory
        # we'll search from.
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "src" / "loom"
        sub.mkdir(parents=True)
        assert project_root(sub) == tmp_path.resolve()

    def test_falls_back_to_start_when_no_git(self, tmp_path):
        # No .git anywhere along the path — return the start dir.
        sub = tmp_path / "src" / "loom"
        sub.mkdir(parents=True)
        # Edge: we might still find a real .git somewhere above tmp_path
        # (e.g. when tests run from inside the loom repo). The contract
        # is "first .git wins"; the test only asserts that the result
        # is *some* directory in the chain, not necessarily ``sub``.
        root = project_root(sub)
        assert root == sub.resolve() or any(
            (p / ".git").exists()
            for p in [root, *root.parents]
        )

    def test_stops_at_first_git(self, tmp_path):
        # Nested git: inner repo with .git should be the root, not
        # the outer one.
        (tmp_path / ".git").mkdir()
        inner = tmp_path / "submodule"
        inner.mkdir()
        (inner / ".git").mkdir()
        sub = inner / "src"
        sub.mkdir()
        assert project_root(sub) == inner.resolve()


class TestNormalizeFilePath:
    def test_absolute_inside_root_becomes_relative(self, tmp_path):
        (tmp_path / ".git").mkdir()
        f = tmp_path / "src" / "loom" / "store.py"
        f.parent.mkdir(parents=True)
        f.touch()
        result = normalize_file_path(f, root=tmp_path)
        assert result == "src/loom/store.py"

    def test_relative_path_resolved_against_cwd(self, tmp_path, monkeypatch):
        # When user types a relative path, resolve() uses cwd. Make
        # cwd be the project root for the test.
        (tmp_path / ".git").mkdir()
        f = tmp_path / "src" / "a.py"
        f.parent.mkdir()
        f.touch()
        monkeypatch.chdir(tmp_path)
        result = normalize_file_path("src/a.py", root=tmp_path)
        assert result == "src/a.py"

    def test_path_outside_root_kept_absolute(self, tmp_path):
        # File lives outside the project — return absolute POSIX form.
        (tmp_path / ".git").mkdir()
        outside = tmp_path.parent / "other_repo" / "file.py"
        outside.parent.mkdir(exist_ok=True)
        outside.touch()
        result = normalize_file_path(outside, root=tmp_path)
        # POSIX separators, full path.
        assert "/" in result
        assert "\\" not in result
        assert result.endswith("/other_repo/file.py")

    def test_windows_backslashes_normalized(self, tmp_path):
        (tmp_path / ".git").mkdir()
        f = tmp_path / "src" / "a.py"
        f.parent.mkdir()
        f.touch()
        # Even if the caller types backslashes, the stored form is
        # POSIX. This is the cross-platform portability guarantee.
        # Use string with backslashes deliberately:
        backslash_path = str(f).replace("/", "\\")
        result = normalize_file_path(backslash_path, root=tmp_path)
        assert "\\" not in result
        assert result == "src/a.py"

    def test_dot_dot_normalized(self, tmp_path):
        (tmp_path / ".git").mkdir()
        f = tmp_path / "src" / "a.py"
        f.parent.mkdir()
        f.touch()
        # `..` in the input gets resolved away.
        weird = tmp_path / "src" / "sub" / ".." / "a.py"
        result = normalize_file_path(weird, root=tmp_path)
        assert result == "src/a.py"

    def test_already_relative_with_root_explicit(self, tmp_path, monkeypatch):
        # If the file doesn't physically exist but the path is
        # cleanly relative to the given root, we still get a clean
        # relative result (resolve() doesn't require existence).
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        result = normalize_file_path("src/loom/imaginary.py", root=tmp_path)
        assert result == "src/loom/imaginary.py"
