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


# ---------------------------------------------------------------------------
# M16.2 — edit-range auto-capture (Edit/MultiEdit)
# ---------------------------------------------------------------------------


def test_edit_with_locatable_old_string_logs_range(
    tmp_log, project_name, tmp_path,
):
    # File has a multi-line block; old_string spans lines 2-3.
    f = tmp_path / "code.py"
    f.write_text(
        "line one\n"
        "def foo():\n"
        "    return 42\n"
        "line four\n",
        encoding="utf-8",
    )
    res = _run_hook(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(f),
                "old_string": "def foo():\n    return 42",
                "new_string": "def foo():\n    return 99",
            },
        },
        tmp_log, project_name,
    )
    assert res.returncode == 0
    entries = _read_log(tmp_log)
    assert len(entries) == 1
    # Edit range covers lines 2-3 of the original file.
    assert entries[0].get("edit_range") == "2-3"


def test_edit_with_single_line_old_string_logs_single_line(
    tmp_log, project_name, tmp_path,
):
    f = tmp_path / "code.py"
    f.write_text("a\nb\nc\n", encoding="utf-8")
    res = _run_hook(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(f),
                "old_string": "b",
                "new_string": "B",
            },
        },
        tmp_log, project_name,
    )
    assert res.returncode == 0
    e = _read_log(tmp_log)[0]
    # Single-line range renders without "-".
    assert e.get("edit_range") == "2"


def test_edit_with_unfindable_old_string_omits_edit_range(
    tmp_log, project_name, tmp_path,
):
    f = tmp_path / "code.py"
    f.write_text("a\nb\nc\n", encoding="utf-8")
    res = _run_hook(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(f),
                "old_string": "zzz_never_in_file",
                "new_string": "Z",
            },
        },
        tmp_log, project_name,
    )
    assert res.returncode == 0
    e = _read_log(tmp_log)[0]
    # Range absent when not locatable (no false "1-1" or "all").
    assert "edit_range" not in e


def test_multiedit_logs_union_span(tmp_log, project_name, tmp_path):
    # Two edits — one at line 2, one at line 5. Union span is 2-5.
    f = tmp_path / "code.py"
    f.write_text(
        "line1\nfoo\nline3\nline4\nbar\nline6\n", encoding="utf-8",
    )
    res = _run_hook(
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(f),
                "edits": [
                    {"old_string": "foo", "new_string": "FOO"},
                    {"old_string": "bar", "new_string": "BAR"},
                ],
            },
        },
        tmp_log, project_name,
    )
    assert res.returncode == 0
    e = _read_log(tmp_log)[0]
    assert e.get("edit_range") == "2-5"


def test_write_tool_does_not_log_edit_range(
    tmp_log, project_name, tmp_path,
):
    # Write is whole-file; no edit_range expected.
    f = tmp_path / "code.py"
    f.write_text("x = 1\n", encoding="utf-8")
    res = _run_hook(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(f),
                "content": "x = 2\n",
            },
        },
        tmp_log, project_name,
    )
    assert res.returncode == 0
    e = _read_log(tmp_log)[0]
    assert "edit_range" not in e
