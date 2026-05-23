"""
Tests for experiments/bakeoff/_methodology.py — M18 helpers.

Imports from a path outside src/ since _methodology lives under
experiments/ (research infra, not the loom package).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add the bake-off dir to the import path.
_BAKEOFF = Path(__file__).parent.parent / "experiments" / "bakeoff"
sys.path.insert(0, str(_BAKEOFF))

import _methodology as M  # noqa: E402


# ---------------------------------------------------------------------------
# No-op detection
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_whitespace_only_diff_collapses(self):
        a = "  def x():\n      pass  \n"
        b = "def x():\npass"
        assert M.normalize_for_noop_comparison(a) == M.normalize_for_noop_comparison(b)

    def test_blank_lines_stripped(self):
        a = "x = 1\n\n\ny = 2\n"
        b = "x = 1\ny = 2"
        assert M.normalize_for_noop_comparison(a) == M.normalize_for_noop_comparison(b)

    def test_empty_string_is_empty(self):
        assert M.normalize_for_noop_comparison("") == ""

    def test_real_difference_preserved(self):
        a = "x = 1"
        b = "x = 2"
        assert M.normalize_for_noop_comparison(a) != M.normalize_for_noop_comparison(b)


class TestIsNoop:
    def test_byte_equal_outputs_are_noop(self):
        ref = "def f(): pass\n"
        assert M.is_noop(ref, ref)

    def test_whitespace_different_outputs_are_noop(self):
        ref = "def f(): pass\n"
        out = "  def f(): pass\n\n"
        assert M.is_noop(out, ref)

    def test_genuine_change_not_noop(self):
        ref = "def f(): pass\n"
        out = "def f(): return 42\n"
        assert not M.is_noop(out, ref)

    def test_empty_reference_returns_false(self):
        assert not M.is_noop("x = 1", "")

    def test_empty_output_returns_false(self):
        assert not M.is_noop("", "x = 1")


class TestComputeCellNoopRate:
    def test_empty_returns_zero(self):
        assert M.compute_cell_noop_rate([]) == 0.0

    def test_no_noops(self):
        trials = [
            {"no_op": False}, {"no_op": False}, {"no_op": False},
        ]
        assert M.compute_cell_noop_rate(trials) == 0.0

    def test_all_noops(self):
        trials = [{"no_op": True}, {"no_op": True}]
        assert M.compute_cell_noop_rate(trials) == 1.0

    def test_mixed(self):
        # 2 of 5 → 0.4
        trials = [
            {"no_op": True}, {"no_op": False}, {"no_op": True},
            {"no_op": False}, {"no_op": False},
        ]
        assert M.compute_cell_noop_rate(trials) == 0.4

    def test_missing_field_treated_as_not_noop(self):
        # Back-compat: pre-M18 summaries didn't have no_op.
        trials = [{"passed": 1}, {"no_op": True}]
        # 1 of 2 → 0.5
        assert M.compute_cell_noop_rate(trials) == 0.5


class TestCellExcludedFromCompliance:
    def test_below_threshold_included(self):
        excluded, reason = M.cell_excluded_from_compliance(0.1, threshold=0.2)
        assert excluded is False
        assert reason == ""

    def test_above_threshold_excluded(self):
        excluded, reason = M.cell_excluded_from_compliance(0.5, threshold=0.2)
        assert excluded is True
        assert "50%" in reason

    def test_at_threshold_included(self):
        # Strict-> comparison: exactly at threshold passes.
        excluded, _ = M.cell_excluded_from_compliance(0.2, threshold=0.2)
        assert excluded is False

    def test_default_threshold_from_env(self, monkeypatch):
        # Default constant honors LOOM_NOOP_THRESHOLD.
        # Need to reload to pick up the env var.
        import importlib
        monkeypatch.setenv("LOOM_NOOP_THRESHOLD", "0.5")
        import _methodology as fresh
        importlib.reload(fresh)
        assert fresh.DEFAULT_NOOP_EXCLUSION_THRESHOLD == 0.5


class TestCellSummaryWithNoopFlags:
    def test_typical_compliant_cell(self):
        trials = [
            {"passed": 2, "total": 2, "no_op": False},
            {"passed": 2, "total": 2, "no_op": False},
            {"passed": 1, "total": 2, "no_op": False},
        ]
        result = M.cell_summary_with_noop_flags(trials)
        assert result["n_trials"] == 3
        assert result["passed"] == 5
        assert result["total_attempts"] == 6
        assert result["compliance_rate"] == pytest.approx(5 / 6)
        assert result["noop_rate"] == 0.0
        assert result["noop_excluded"] is False
        assert result["compliance_rate_reportable"] == pytest.approx(5 / 6)

    def test_noop_heavy_cell_excluded(self):
        # 3 of 4 are no-ops → 75% > 20% threshold.
        trials = [
            {"passed": 2, "total": 2, "no_op": True},
            {"passed": 2, "total": 2, "no_op": True},
            {"passed": 2, "total": 2, "no_op": True},
            {"passed": 1, "total": 2, "no_op": False},
        ]
        result = M.cell_summary_with_noop_flags(trials)
        assert result["noop_rate"] == 0.75
        assert result["noop_excluded"] is True
        assert "75%" in result["noop_exclusion_reason"]
        assert result["compliance_rate_reportable"] is None
        # Raw compliance still reported — just not flagged as
        # reportable.
        assert result["compliance_rate"] > 0


# ---------------------------------------------------------------------------
# Sampling lockfile
# ---------------------------------------------------------------------------


class TestReadSamplingLock:
    def test_missing_file_returns_empty(self, monkeypatch, tmp_path):
        # Point the module's LOCKFILE_PATH at a non-existent file.
        monkeypatch.setattr(M, "LOCKFILE_PATH", tmp_path / "ghost.lock")
        assert M.read_sampling_lock() == {}

    def test_malformed_returns_empty(self, monkeypatch, tmp_path):
        bad = tmp_path / "bad.lock"
        bad.write_text("not json", encoding="utf-8")
        monkeypatch.setattr(M, "LOCKFILE_PATH", bad)
        assert M.read_sampling_lock() == {}

    def test_valid_returns_dict(self, monkeypatch, tmp_path):
        good = tmp_path / "good.lock"
        good.write_text(json.dumps({"defaults": {"temperature": 0}}),
                        encoding="utf-8")
        monkeypatch.setattr(M, "LOCKFILE_PATH", good)
        assert M.read_sampling_lock() == {"defaults": {"temperature": 0}}


class TestSamplingDrift:
    def test_no_lock_no_drift(self):
        assert M.sampling_drift({"temperature": 0.8}, locked={}) == []

    def test_match_no_drift(self):
        locked = {"defaults": {"temperature": 0, "top_p": 1}}
        recorded = {"model": "x", "temperature": 0, "top_p": 1}
        assert M.sampling_drift(recorded, locked=locked) == []

    def test_drift_on_one_key(self):
        locked = {"defaults": {"temperature": 0}}
        recorded = {"temperature": 0.8}
        msgs = M.sampling_drift(recorded, locked=locked)
        assert len(msgs) == 1
        assert "temperature" in msgs[0]
        assert "0.8" in msgs[0]
        assert "0" in msgs[0]

    def test_per_model_overlay_wins(self):
        locked = {
            "defaults": {"temperature": 0},
            "by_model": {"qwen3.5:latest": {"temperature": 0.5}},
        }
        # qwen3.5 expects 0.5; recorded 0.5 → no drift even though
        # defaults says 0.
        recorded = {"model": "qwen3.5:latest", "temperature": 0.5}
        assert M.sampling_drift(recorded, locked=locked) == []

    def test_missing_key_in_recorded_skipped(self):
        # If the harness didn't record a key, we can't claim drift.
        locked = {"defaults": {"temperature": 0, "top_p": 1}}
        recorded = {"temperature": 0}  # top_p missing
        assert M.sampling_drift(recorded, locked=locked) == []


# ---------------------------------------------------------------------------
# Output retention
# ---------------------------------------------------------------------------


class TestRetainOutput:
    def test_writes_to_raw_outputs_dir(self, tmp_path):
        path = M.retain_output(tmp_path, "trial001", "hello world")
        assert path is not None
        assert path.exists()
        assert path.parent == tmp_path / "raw_outputs"
        assert path.read_text(encoding="utf-8") == "hello world"

    def test_overwrites_existing(self, tmp_path):
        M.retain_output(tmp_path, "t", "first")
        path = M.retain_output(tmp_path, "t", "second")
        assert path.read_text(encoding="utf-8") == "second"

    def test_unsafe_trial_id_sanitized(self, tmp_path):
        # Forward slashes, backslashes, etc. all replaced.
        path = M.retain_output(tmp_path, "phY/S1::cell run #1", "x")
        assert path is not None
        # No path separators in the filename portion.
        assert "/" not in path.name
        assert "\\" not in path.name

    def test_env_opt_out(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOOM_NO_RAW_OUTPUT", "1")
        path = M.retain_output(tmp_path, "t", "x")
        assert path is None
        # No file written.
        assert not (tmp_path / "raw_outputs").exists()

    def test_empty_output_still_writes(self, tmp_path):
        # An empty response is a real datapoint (model returned
        # nothing), worth retaining.
        path = M.retain_output(tmp_path, "t", "")
        assert path is not None
        assert path.read_text(encoding="utf-8") == ""
