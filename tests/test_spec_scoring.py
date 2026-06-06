"""M26 — grading test for the spec-quality scorer (pre-registered).

This test is the α-mode grading criterion for `loom_exec`. It MUST be
written and committed BEFORE the scorer module exists. Until then,
the import at line ~30 fails and `loom_exec` records a failed grading.

Once `loom_exec` produces `src/loom/spec_scoring.py` (or wires it
through `loom.services`), the import resolves and the seven assertions
below run against the 41-spec calibration set in
`tests/data/spec_scoring_calibration.json`.

The calibration file is the pre-registration artifact:
  * 10 high — hand-authored specs elaborating shipped Loom features
  * 21 mid  — M25-migration specs (concrete identifiers, zero AC)
  * 10 low  — hand-authored antipatterns

Modifying the calibration after lock invalidates the experiment.
See SPEC-85e02906 + REQ-6dec889f for the contract.
"""

from __future__ import annotations

import datetime
import json
import os
import statistics
from pathlib import Path

import pytest

# Import-time failure is intentional: until loom_exec produces the
# scorer, this test cannot be collected and is reported as failed.
from loom.services import score_specification  # noqa: E402
from loom.store import LoomStore, Requirement, Specification  # noqa: E402


CALIBRATION_PATH = (
    Path(__file__).parent / "data" / "spec_scoring_calibration.json"
)


def _load_calibration() -> dict:
    return json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="class")
def calibration() -> dict:
    return _load_calibration()


@pytest.fixture(scope="class")
def populated_store(tmp_path_factory, calibration):
    """Materialize the 41 fixtures into a tmp LoomStore.

    Uses the hash embedding provider so setup is instant — no Ollama
    embedding calls. The scorer's own LLM judge call is unaffected and
    still dispatches to the production model.
    """
    os.environ.setdefault("LOOM_EMBEDDING_PROVIDER", "hash")
    tmpdir = tmp_path_factory.mktemp("calib_store")
    store = LoomStore(project="m26-calib", data_dir=tmpdir)
    now = datetime.datetime.now().isoformat()

    for fx in calibration["specs"]:
        parent_id = f"REQ-{fx['spec_id'].replace('FIXTURE-', 'parent-')}"
        store.add_requirement(Requirement(
            id=parent_id,
            domain="behavior",
            value=fx["parent_req_text"],
            source_msg_id="calib",
            source_session="calib",
            timestamp=now,
        ))
        ac = fx.get("acceptance_criteria") or []
        store.add_specification(Specification(
            id=fx["spec_id"],
            parent_req=parent_id,
            description=fx["description"],
            timestamp=now,
            acceptance_criteria=ac if ac else ["TBD"],
        ))

    return store


@pytest.fixture(scope="class")
def scored(populated_store, calibration):
    """Run the scorer on each fixture once; reuse across all assertions."""
    results = []
    for fx in calibration["specs"]:
        out = score_specification(populated_store, fx["spec_id"])
        results.append({
            "spec_id": fx["spec_id"],
            "band": fx["band"],
            "source": fx["source"],
            "score": out["score"],
            "by_dim": out["by_dim"],
            "latency_ms": out["latency_ms"],
        })
    return results


class TestSpecScoring:
    """The pre-registered grading test. Seven assertions, no escape hatches."""

    def test_shape_returns_expected_dict(self, populated_store, calibration):
        """AC1 — shape contract on a single representative spec."""
        out = score_specification(populated_store, calibration["specs"][0]["spec_id"])
        assert isinstance(out, dict)
        assert isinstance(out["score"], int)
        assert 0 <= out["score"] <= 100
        assert set(out["by_dim"].keys()) == {
            "acceptance_criteria",
            "falsifiability",
            "parent_alignment",
            "concreteness",
        }
        assert all(0 <= v <= 25 for v in out["by_dim"].values())
        assert sum(out["by_dim"].values()) == out["score"]
        assert isinstance(out["judge_model"], str) and out["judge_model"]
        assert isinstance(out["latency_ms"], (int, float))
        assert out["latency_ms"] > 50, (
            f"latency {out['latency_ms']}ms too low — judge probably not called"
        )

    def test_three_band_ordering(self, scored):
        """AC2 — median(high) > median(mid) > median(low) strictly."""
        by_band = {"high": [], "mid": [], "low": []}
        for r in scored:
            by_band[r["band"]].append(r["score"])
        med = {b: statistics.median(vals) for b, vals in by_band.items()}
        assert med["high"] > med["mid"] > med["low"], (
            f"ordering violated: high={med['high']} mid={med['mid']} low={med['low']}"
        )

    def test_high_low_separation(self, scored, calibration):
        """AC3 — median(high) - median(low) >= 50 (load-bearing precision)."""
        high = [r["score"] for r in scored if r["band"] == "high"]
        low = [r["score"] for r in scored if r["band"] == "low"]
        sep = statistics.median(high) - statistics.median(low)
        threshold = calibration["separation_thresholds"]["high_low_min"]
        assert sep >= threshold, (
            f"high-low separation {sep} < {threshold}; "
            f"medians: high={statistics.median(high)} low={statistics.median(low)}"
        )

    def test_high_mid_separation(self, scored, calibration):
        """AC4 — median(high) - median(mid) >= 15."""
        high = [r["score"] for r in scored if r["band"] == "high"]
        mid = [r["score"] for r in scored if r["band"] == "mid"]
        sep = statistics.median(high) - statistics.median(mid)
        threshold = calibration["separation_thresholds"]["high_mid_min"]
        assert sep >= threshold, (
            f"high-mid separation {sep} < {threshold}; "
            f"medians: high={statistics.median(high)} mid={statistics.median(mid)}"
        )

    def test_mid_low_separation(self, scored, calibration):
        """AC5 — median(mid) - median(low) >= 15."""
        mid = [r["score"] for r in scored if r["band"] == "mid"]
        low = [r["score"] for r in scored if r["band"] == "low"]
        sep = statistics.median(mid) - statistics.median(low)
        threshold = calibration["separation_thresholds"]["mid_low_min"]
        assert sep >= threshold, (
            f"mid-low separation {sep} < {threshold}; "
            f"medians: mid={statistics.median(mid)} low={statistics.median(low)}"
        )

    def test_canary_high_no_false_positive(self, scored):
        """AC6 — 0 of 10 high-band specs scores below 60."""
        below = [r for r in scored if r["band"] == "high" and r["score"] < 60]
        assert not below, (
            f"{len(below)} high specs scored <60: "
            f"{[(r['spec_id'], r['score'], r['source']) for r in below]}"
        )

    def test_canary_low_no_false_negative(self, scored):
        """AC7 — 0 of 10 low-band specs scores above 60."""
        above = [r for r in scored if r["band"] == "low" and r["score"] > 60]
        assert not above, (
            f"{len(above)} low specs scored >60: "
            f"{[(r['spec_id'], r['score'], r['source']) for r in above]}"
        )
