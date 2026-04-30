"""Tests for src/config.py — .loom-config.json load/save + resolve()."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from loom import config


class TestLoadConfig:
    def test_missing_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = config.load_config(td)
            assert cfg["project"] is None
            assert cfg["executor_model"] == "qwen3.5:latest"
            assert cfg["embedding_model"] == "nomic-embed-text"
            assert ".git" in cfg["ignore"]

    def test_defaults_are_a_fresh_copy(self):
        """Caller mutating returned ignore list must not affect DEFAULTS."""
        with tempfile.TemporaryDirectory() as td:
            cfg = config.load_config(td)
            cfg["ignore"].append("CUSTOM")
            cfg2 = config.load_config(td)
            assert "CUSTOM" not in cfg2["ignore"]

    def test_loads_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".loom-config.json").write_text(
                json.dumps({"project": "myproj", "executor_model": "llama3.1:8b"}),
                encoding="utf-8",
            )
            cfg = config.load_config(td)
            assert cfg["project"] == "myproj"
            assert cfg["executor_model"] == "llama3.1:8b"
            # missing fields filled from DEFAULTS
            assert cfg["embedding_model"] == "nomic-embed-text"

    def test_malformed_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".loom-config.json").write_text(
                "{ not valid json", encoding="utf-8",
            )
            cfg = config.load_config(td)
            assert cfg["project"] is None
            assert cfg["executor_model"] == "qwen3.5:latest"

    def test_nondict_json_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".loom-config.json").write_text(
                json.dumps([1, 2, 3]), encoding="utf-8",
            )
            cfg = config.load_config(td)
            assert cfg["project"] is None


class TestSaveConfig:
    def test_save_writes_pretty_json(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = {"project": "x", "executor_model": "m"}
            path = config.save_config(td, cfg)
            assert path.exists()
            text = path.read_text(encoding="utf-8")
            assert '"project": "x"' in text
            # indent=2 + trailing newline
            assert text.endswith("\n")
            assert "  " in text

    def test_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = {"project": "rt", "custom_field": "value", "ignore": ["a"]}
            config.save_config(td, cfg)
            loaded = config.load_config(td)
            assert loaded["project"] == "rt"
            assert loaded["custom_field"] == "value"
            assert loaded["ignore"] == ["a"]

    def test_save_atomic(self):
        """Write should go via a .tmp file and rename (no partial writes)."""
        with tempfile.TemporaryDirectory() as td:
            config.save_config(td, {"project": "atom"})
            # .tmp should not remain
            assert not (Path(td) / ".loom-config.json.tmp").exists()


class TestResolve:
    def test_cli_wins(self):
        got = config.resolve(
            "project",
            cli="from-cli",
            env_var="LOOM_PROJECT",
            config={"project": "from-config"},
            default="from-default",
        )
        assert got == "from-cli"

    def test_env_when_no_cli(self, monkeypatch):
        monkeypatch.setenv("LOOM_PROJECT", "from-env")
        got = config.resolve(
            "project",
            cli=None,
            env_var="LOOM_PROJECT",
            config={"project": "from-config"},
            default="from-default",
        )
        assert got == "from-env"

    def test_config_when_no_cli_env(self, monkeypatch):
        monkeypatch.delenv("LOOM_PROJECT", raising=False)
        got = config.resolve(
            "project",
            cli=None,
            env_var="LOOM_PROJECT",
            config={"project": "from-config"},
            default="from-default",
        )
        assert got == "from-config"

    def test_default_when_nothing(self, monkeypatch):
        monkeypatch.delenv("LOOM_PROJECT", raising=False)
        got = config.resolve(
            "project",
            cli=None,
            env_var="LOOM_PROJECT",
            config={},
            default="from-default",
        )
        assert got == "from-default"

    def test_defaults_dict_fallback(self):
        # No cli, no env, no config value, no explicit default → DEFAULTS
        got = config.resolve(
            "executor_model",
            cli=None,
            env_var="LOOM_EXECUTOR_MODEL",
            config={},
        )
        assert got == "qwen3.5:latest"

    def test_none_in_config_is_skipped(self):
        """config.get returning None should fall through to default, not be treated as a value."""
        got = config.resolve(
            "decomposer_model",
            cli=None,
            env_var="LOOM_DECOMPOSER_MODEL",
            config={"decomposer_model": None},
            default="fallback",
        )
        assert got == "fallback"
