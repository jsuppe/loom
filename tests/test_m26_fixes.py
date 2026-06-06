"""Regression tests for M26 P-path findings F1 + F5.

F1 (REQ-cc95b9a1): `loom decompose` silently falls back to ollama when
  ANTHROPIC_API_KEY is missing. Fix: one-time stderr warning.

F5 (REQ-25c75b6f): `loom_exec`'s output contract hard-codes the runner's
  Python defaults regardless of target file extension. Fix: shared
  `services.select_fence_and_mode` selects fence + apply_mode per-file.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

from loom import services


# ============================================================
# F1 — silent-fallback warning
# ============================================================


class TestF1FallbackWarning:
    @pytest.fixture(autouse=True)
    def _reset_warned_flag(self):
        """Reset the module-level once-flag so each test starts clean."""
        services._DECOMPOSER_FALLBACK_WARNED = False
        yield
        services._DECOMPOSER_FALLBACK_WARNED = False

    def test_warns_when_key_missing(self, monkeypatch, capsys):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("LOOM_DECOMPOSER_MODEL", raising=False)

        model = services._default_decomposer_model()
        captured = capsys.readouterr()

        assert model == "ollama:qwen2.5-coder:32b"
        assert "ANTHROPIC_API_KEY not set" in captured.err
        assert "asymmetric pipeline" in captured.err.lower() or "single-model" in captured.err.lower()

    def test_no_warning_when_key_present(self, monkeypatch, capsys):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        monkeypatch.delenv("LOOM_DECOMPOSER_MODEL", raising=False)

        model = services._default_decomposer_model()
        captured = capsys.readouterr()

        assert model.startswith("anthropic:")
        assert captured.err == ""

    def test_no_warning_when_explicit_override(self, monkeypatch, capsys):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("LOOM_DECOMPOSER_MODEL", "ollama:custom-model:7b")

        model = services._default_decomposer_model()
        captured = capsys.readouterr()

        assert model == "ollama:custom-model:7b"
        assert captured.err == ""

    def test_warning_fires_only_once_per_process(self, monkeypatch, capsys):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("LOOM_DECOMPOSER_MODEL", raising=False)

        services._default_decomposer_model()
        first = capsys.readouterr().err
        services._default_decomposer_model()
        second = capsys.readouterr().err

        assert "ANTHROPIC_API_KEY" in first
        assert second == ""  # the warning is suppressed on subsequent calls


# ============================================================
# F5 — per-extension fence + apply_mode override
# ============================================================


@pytest.fixture
def python_runner():
    return SimpleNamespace(fence="python", language="python", apply_mode="append")


@pytest.fixture
def dart_runner():
    return SimpleNamespace(fence="dart", language="dart", apply_mode="replace")


class TestF5SelectFenceAndMode:
    @pytest.mark.parametrize("path", [
        "src/loom/cli.py",
        "tests/test_foo.py",
        "scripts/migrate.py",
    ])
    def test_python_files_keep_runner_defaults(self, path, python_runner):
        fence, lang, mode = services.select_fence_and_mode(path, python_runner)
        assert (fence, lang, mode) == ("python", "python", "append")

    def test_dart_files_keep_dart_runner_defaults(self, dart_runner):
        fence, lang, mode = services.select_fence_and_mode("lib/orders.dart", dart_runner)
        assert (fence, lang, mode) == ("dart", "dart", "replace")

    @pytest.mark.parametrize("path,expected", [
        ("src/loom/prompts/spec_score.txt", ("text", "plain-text", "replace")),
        ("docs/README.md", ("markdown", "markdown", "replace")),
        ("tests/data/calibration.json", ("json", "JSON", "replace")),
        ("config/settings.yaml", ("yaml", "YAML", "replace")),
        ("config/settings.yml", ("yaml", "YAML", "replace")),
        ("pyproject.toml", ("toml", "TOML", "replace")),
    ])
    def test_non_code_extensions_override(self, path, expected, python_runner):
        """Non-code files use content-type fences and replace mode regardless of runner."""
        fence, lang, mode = services.select_fence_and_mode(path, python_runner)
        assert (fence, lang, mode) == expected

    def test_case_insensitive_extension_matching(self, python_runner):
        """A .TXT file should be treated as text, same as .txt."""
        fence, _, mode = services.select_fence_and_mode("PROMPT.TXT", python_runner)
        assert fence == "text"
        assert mode == "replace"

    def test_unknown_extension_falls_through_to_runner(self, dart_runner):
        """Unrecognized extension: trust the runner's decision."""
        fence, lang, mode = services.select_fence_and_mode("weird/file.xyz", dart_runner)
        assert (fence, lang, mode) == ("dart", "dart", "replace")
