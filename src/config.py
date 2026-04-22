"""
Loom per-target-project configuration: ``.loom-config.json``.

A Loom config lives at the root of the target repo (the one Loom is
pointed at, not the loom repo itself). It pins settings that otherwise
have to be passed as flags or env vars on every invocation: the project
name for the store, which executor/decomposer model to use, where tests
live, which paths to ignore when copying to scratch, etc.

Precedence (highest first):
    1. Explicit CLI flag
    2. Environment variable
    3. This config file
    4. Built-in default

The config is optional — Loom runs fine without it. ``loom init`` is the
command that writes one.

Design intent:
    - One JSON file, human-editable, no schema validation beyond "is this
      a dict". If a field is missing, fall back to the default. If it's
      the wrong type, the caller gets the raw value and can decide.
    - No automatic config-discovery across parent dirs (yet). The caller
      passes the target_dir explicitly; we look for ``.loom-config.json``
      right there.
    - Writes are atomic (write to tmp, rename) so a crashed init never
      leaves a half-written file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_FILENAME = ".loom-config.json"

# Defaults that apply when a field is absent from the config.
DEFAULTS: dict[str, Any] = {
    "project": None,
    "target_dir": ".",
    "decomposer_model": None,      # None → services._default_decomposer_model()
    "executor_model": "qwen3.5:latest",
    "embedding_model": "nomic-embed-text",
    "test_runner": "pytest",
    "test_dir": "tests",
    "ignore": [
        ".git", "__pycache__", ".venv", "venv", ".pytest_cache",
        "node_modules", ".tox", "dist", "build", ".mypy_cache",
        ".claude", ".worktrees",
    ],
}


def config_path(target_dir: Path | str) -> Path:
    return Path(target_dir) / CONFIG_FILENAME


def load_config(target_dir: Path | str) -> dict[str, Any]:
    """Return the config dict for target_dir.

    If the file is absent or unreadable, returns the defaults dict (a
    fresh copy — safe for the caller to mutate).
    """
    path = config_path(target_dir)
    merged = {**DEFAULTS, "ignore": list(DEFAULTS["ignore"])}
    if not path.exists():
        return merged
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return merged
    if not isinstance(raw, dict):
        return merged
    for k, v in raw.items():
        merged[k] = v
    return merged


def save_config(target_dir: Path | str, config: dict[str, Any]) -> Path:
    """Atomically write config to target_dir/.loom-config.json. Returns path."""
    path = config_path(target_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(config, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def resolve(
    key: str,
    *,
    cli: Any = None,
    env_var: str | None = None,
    config: dict[str, Any] | None = None,
    default: Any = None,
) -> Any:
    """Resolve a single setting by precedence: CLI > env > config > default.

    ``default`` overrides ``DEFAULTS[key]`` if passed explicitly. Any
    None value is treated as "not set" and skipped.
    """
    if cli is not None:
        return cli
    if env_var:
        envv = os.environ.get(env_var)
        if envv:
            return envv
    if config is not None and config.get(key) is not None:
        return config[key]
    if default is not None:
        return default
    return DEFAULTS.get(key)
