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

# Per-test deferred imports for `score_specification` so the smoke tests
# that don't need the scorer (file existence, CLI registration) can
# collect + run even before loom_exec produces it.
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
    from loom.services import score_specification
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
        from loom.services import score_specification
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


# ====================================================================
# Per-task smoke tests (M26 F6 workaround — REQ-75d6f16c)
#
# Each TestSmoke* class is the grading target for one of the 5 atomic
# tasks in the decomp. Minimal deliverables per task so loom_exec
# doesn't waste attempts on tasks that can't pass TestSpecScoring
# until the full implementation lands.
#
#   Task 1 (prompt file)     → TestSmokePromptFile
#   Task 2 (function sig)    → TestSmokeSignatureImportable
#   Task 3 (core logic)      → TestSpecScoring  (the full grading above)
#   Task 4 (CLI command)     → TestSmokeCliSpecScore
#   Task 5 (in-band integ)   → TestSmokeInBandScoring
# ====================================================================


class TestSmokePromptFile:
    """Task 1 — judge prompt file exists with required template vars."""

    PROMPT_PATH = (
        Path(__file__).resolve().parents[1]
        / "src" / "loom" / "prompts" / "spec_score.txt"
    )

    def test_prompt_file_exists(self):
        assert self.PROMPT_PATH.exists(), (
            f"Expected prompt at {self.PROMPT_PATH}"
        )

    def test_prompt_includes_template_variables(self):
        prompt = self.PROMPT_PATH.read_text(encoding="utf-8")
        for var in ("parent_req", "description", "criteria"):
            assert ("{{" + var + "}}") in prompt or ("{" + var + "}") in prompt, (
                f"prompt missing template variable: {var}"
            )

    def test_prompt_mentions_scoring_dimensions(self):
        prompt = self.PROMPT_PATH.read_text(encoding="utf-8").lower()
        for dim in (
            "acceptance_criteria",
            "falsifiability",
            "parent_alignment",
            "concreteness",
        ):
            assert dim in prompt, f"prompt missing dimension: {dim}"


class TestSmokeSignatureImportable:
    """Task 2 — services.score_specification importable + correct signature.
    Implementation may be a stub at this stage."""

    def test_importable(self):
        from loom.services import score_specification  # noqa: F401

    def test_is_callable(self):
        from loom.services import score_specification
        assert callable(score_specification)

    def test_accepts_expected_args(self):
        """Signature: score_specification(store, spec_id, judge_model=None)."""
        import inspect
        from loom.services import score_specification
        sig = inspect.signature(score_specification)
        params = list(sig.parameters)
        assert params[:2] == ["store", "spec_id"], (
            f"expected (store, spec_id, ...), got {params}"
        )
        assert "judge_model" in sig.parameters, "missing judge_model kwarg"


class TestSmokeCliSpecScore:
    """Task 4 — `loom spec-score <SPEC-id>` CLI subcommand registered."""

    def test_subcommand_registered(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "scripts/loom", "spec-score", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=Path(__file__).resolve().parents[1],
        )
        assert result.returncode == 0, (
            f"`loom spec-score --help` failed: {result.stderr}"
        )
        assert "spec" in result.stdout.lower(), (
            f"--help output doesn't mention spec: {result.stdout[:200]}"
        )

    def test_subcommand_supports_json(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "scripts/loom", "spec-score", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=Path(__file__).resolve().parents[1],
        )
        assert "--json" in result.stdout, (
            f"--json flag not in --help: {result.stdout[:300]}"
        )


class TestSmokeInBandScoring:
    """Task 5 — `loom spec` create scores in-band when
    LOOM_SPEC_SCORE_ON_CREATE=1. Stubs services.score_specification so the
    test exercises only the integration glue, not the LLM judge."""

    def test_score_function_called_during_create(
        self, tmp_path_factory, monkeypatch
    ):
        from loom import services
        from loom.store import LoomStore, Requirement

        tmpdir = tmp_path_factory.mktemp("inband_store")
        store = LoomStore(project="m26-inband", data_dir=tmpdir)
        store.add_requirement(Requirement(
            id="REQ-parent-inband",
            domain="behavior",
            value="Parent requirement for in-band scoring smoke.",
            source_msg_id="test",
            source_session="test",
            timestamp="2026-01-01T00:00:00",
        ))

        calls: list[str] = []

        def fake_score(store_, spec_id, **kw):
            calls.append(spec_id)
            return {
                "score": 30,
                "by_dim": {
                    "acceptance_criteria": 5,
                    "falsifiability": 5,
                    "parent_alignment": 10,
                    "concreteness": 10,
                },
                "judge_model": "stub",
                "latency_ms": 10,
                "reasoning": "stub",
            }

        monkeypatch.setattr(services, "score_specification", fake_score)
        monkeypatch.setenv("LOOM_SPEC_SCORE_ON_CREATE", "1")

        services.spec_add(
            store,
            parent_req="REQ-parent-inband",
            description="A vague spec with no acceptance criteria.",
            criteria=[],
        )

        assert len(calls) == 1, (
            f"expected score_specification called once, got {len(calls)}"
        )

    def test_no_score_call_when_flag_unset(
        self, tmp_path_factory, monkeypatch
    ):
        from loom import services
        from loom.store import LoomStore, Requirement

        tmpdir = tmp_path_factory.mktemp("inband_store_off")
        store = LoomStore(project="m26-inband-off", data_dir=tmpdir)
        store.add_requirement(Requirement(
            id="REQ-parent-inband-off",
            domain="behavior",
            value="Parent requirement for in-band scoring smoke (off).",
            source_msg_id="test",
            source_session="test",
            timestamp="2026-01-01T00:00:00",
        ))

        calls: list[str] = []
        monkeypatch.setattr(
            services, "score_specification",
            lambda *a, **kw: (calls.append(a), {"score": 0})[1],
        )
        monkeypatch.delenv("LOOM_SPEC_SCORE_ON_CREATE", raising=False)

        services.spec_add(
            store,
            parent_req="REQ-parent-inband-off",
            description="A spec without in-band scoring.",
            criteria=["criterion 1"],
        )

        assert calls == [], (
            f"score_specification called when flag unset: {calls}"
        )
