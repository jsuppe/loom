"""
Tests for hooks/loom_pretool.py — the PreToolUse hook.

Exercises the JSONL logging path: what fields are written, what's skipped,
and that a non-watched tool never logs. Uses subprocess to run the hook
as Claude Code would, with LOOM_HOOK_LOG redirected to a tempfile.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
HOOK = REPO_ROOT / "hooks" / "loom_pretool.py"
LOOM_BIN = REPO_ROOT / "scripts" / "loom"


def _run_hook(event: dict, log_path: Path, project: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["LOOM_HOOK_LOG"] = str(log_path)
    env["LOOM_PROJECT"] = project
    # Force the sibling-fallback path so the hook uses the repo's scripts/loom
    # instead of anything on PATH.
    env.pop("LOOM_BIN", None)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        env=env,
        timeout=15,
    )


def _read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def tmp_log(tmp_path):
    return tmp_path / "hook.jsonl"


@pytest.fixture
def project_name():
    return f"test-hook-{uuid.uuid4().hex[:8]}"


def test_non_watched_tool_is_not_logged(tmp_log, project_name):
    res = _run_hook(
        {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}},
        tmp_log, project_name,
    )
    assert res.returncode == 0
    assert _read_log(tmp_log) == []


def test_missing_file_path_logs_skip_reason(tmp_log, project_name):
    res = _run_hook(
        {"tool_name": "Edit", "tool_input": {}},
        tmp_log, project_name,
    )
    assert res.returncode == 0
    entries = _read_log(tmp_log)
    assert len(entries) == 1
    e = entries[0]
    assert e["tool"] == "Edit"
    assert e["fired"] is False
    assert e["skipped"] == "no_file_path"
    assert e["bytes"] == 0
    assert "latency_ms" in e and e["latency_ms"] >= 0


def test_nonexistent_file_logs_cli_error(tmp_log, project_name):
    # `loom context` raises LookupError for missing files -> exit 1 -> skipped=cli_error
    bogus = "/definitely/does/not/exist/ever/xyz.py"
    res = _run_hook(
        {"tool_name": "Edit", "tool_input": {"file_path": bogus}},
        tmp_log, project_name,
    )
    assert res.returncode == 0
    entries = _read_log(tmp_log)
    assert len(entries) == 1
    assert entries[0]["skipped"] == "cli_error"
    assert entries[0]["file"] == bogus
    assert entries[0]["fired"] is False


def test_existing_unlinked_file_logs_no_link(tmp_log, project_name, tmp_path):
    f = tmp_path / "lone.py"
    f.write_text("x = 1\n")
    res = _run_hook(
        {"tool_name": "Edit", "tool_input": {"file_path": str(f)}},
        tmp_log, project_name,
    )
    assert res.returncode == 0
    entries = _read_log(tmp_log)
    assert len(entries) == 1
    e = entries[0]
    assert e["skipped"] == "no_link"
    assert e["fired"] is False
    assert e["reqs"] == 0 and e["specs"] == 0
    # Hook should not emit additionalContext when nothing is linked.
    assert res.stdout.strip() == ""
