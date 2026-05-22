"""
Tests for src/loom/services.py M15 lifecycle pieces:
  - _REQ_TRANSITIONS strict graph + _fast_forward_path BFS
  - set_status with kind=requirement validation + multi-hop traversal
  - set_status DeprecationWarning when reason missing on manual calls
  - link auto-advance: pending → in_progress
  - test_verify auto-advance: in_progress → implemented (with fast-forward
    when called on pending/rationale_needed reqs)
  - verified_eligible: window-based drift-free check
  - verify_stable dry-run vs --apply
  - set_status preserves free transitions for non-requirement kinds
"""
from __future__ import annotations

import json
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from loom import embedding, services
from loom.services import (
    _REQ_TRANSITIONS,
    _fast_forward_path,
    _is_transition_legal,
)
from loom.store import LoomStore, Requirement


@pytest.fixture
def store(tmp_path) -> LoomStore:
    return LoomStore("test-lifecycle", data_dir=tmp_path)


@pytest.fixture
def fake_embedding():
    return [0.1] * 768


@pytest.fixture(autouse=True)
def force_fallback_embedding(monkeypatch):
    embedding._embedding_cache.clear()

    def boom(*a, **kw):
        raise ConnectionResetError("no ollama in tests")

    monkeypatch.setattr(embedding.urllib.request, "urlopen", boom)


def _mk_req(store, value, *, status="pending", kind="requirement",
            domain="behavior", rationale="r"):
    """Helper: create via extract so the timestamp + embedding are right,
    then force the status if needed."""
    out = services.extract(
        store, domain=domain, value=value, rationale=rationale,
        kind=kind, status=status if status != "pending" else None,
    )
    return out["req_id"]


# ---------------------------------------------------------------------------
# Transition graph BFS
# ---------------------------------------------------------------------------


class TestFastForwardPath:
    def test_single_hop(self):
        assert _fast_forward_path("pending", "in_progress") == ["in_progress"]

    def test_two_hop(self):
        assert _fast_forward_path("pending", "implemented") == [
            "in_progress", "implemented",
        ]

    def test_three_hop(self):
        # pending → in_progress → implemented → verified
        assert _fast_forward_path("pending", "verified") == [
            "in_progress", "implemented", "verified",
        ]

    def test_backward(self):
        # Regression: verified → ... → pending should work via the
        # backward edges (verified→implemented→in_progress→pending).
        path = _fast_forward_path("verified", "pending")
        assert path == ["implemented", "in_progress", "pending"]

    def test_same_status(self):
        # No-op — no hops needed.
        assert _fast_forward_path("pending", "pending") == []

    def test_unreachable_from_superseded(self):
        # superseded is terminal — nothing reachable from it.
        assert _fast_forward_path("superseded", "pending") == []
        assert _fast_forward_path("superseded", "archived") == []

    def test_archived_recovery(self):
        # archived → pending is a direct legal edge.
        assert _fast_forward_path("archived", "pending") == ["pending"]

    def test_universal_escape(self):
        # any → superseded or archived directly.
        for start in ("pending", "in_progress", "implemented", "verified"):
            assert _fast_forward_path(start, "superseded") == ["superseded"]
            assert _fast_forward_path(start, "archived") == ["archived"]

    def test_unknown_start_state_returns_empty(self):
        # Defensive: stale data with a status not in the graph.
        assert _fast_forward_path("zombie", "pending") == []

    def test_is_transition_legal(self):
        assert _is_transition_legal("pending", "verified")
        assert not _is_transition_legal("superseded", "pending")
        assert _is_transition_legal("pending", "pending")  # no-op


# ---------------------------------------------------------------------------
# set_status — kind=requirement strict graph
# ---------------------------------------------------------------------------


class TestSetStatusRequirementKind:
    def test_single_hop_legal(self, store):
        req_id = _mk_req(store, "x")
        result = services.set_status(
            store, req_id, "in_progress", reason="testing",
        )
        assert result["status"] == "in_progress"
        assert result["path"] == ["in_progress"]
        assert store.get_requirement(req_id).status == "in_progress"

    def test_fast_forward_records_each_hop(self, store):
        req_id = _mk_req(store, "x")
        result = services.set_status(
            store, req_id, "verified", reason="testing",
        )
        assert result["path"] == ["in_progress", "implemented", "verified"]
        # Final state is verified.
        assert store.get_requirement(req_id).status == "verified"
        # Three events were recorded (one per hop).
        events_path = Path(store.data_dir) / ".loom-events.jsonl"
        events = [
            json.loads(l) for l in
            events_path.read_text(encoding="utf-8").splitlines() if l.strip()
        ]
        status_events = [e for e in events if e.get("event") == "status_changed"]
        assert len(status_events) == 3
        assert [e["to_status"] for e in status_events] == [
            "in_progress", "implemented", "verified",
        ]

    def test_unreachable_target_raises(self, store):
        req_id = _mk_req(store, "x")
        services.set_status(store, req_id, "superseded", reason="t")
        # superseded is terminal; can't go back to pending.
        with pytest.raises(ValueError, match="no path"):
            services.set_status(store, req_id, "pending", reason="t")

    def test_regression_path_legal(self, store):
        # verified → pending IS reachable (through implemented → in_progress).
        req_id = _mk_req(store, "x")
        services.set_status(store, req_id, "verified", reason="forward")
        result = services.set_status(
            store, req_id, "pending", reason="regression",
        )
        assert result["path"] == ["implemented", "in_progress", "pending"]

    def test_archive_recovery(self, store):
        # archived → pending is the M2.3 recovery edge.
        req_id = _mk_req(store, "x")
        services.set_status(store, req_id, "archived", reason="cleanup")
        result = services.set_status(
            store, req_id, "pending", reason="recover",
        )
        assert result["status"] == "pending"

    def test_noop_when_already_at_target(self, store):
        req_id = _mk_req(store, "x")
        result = services.set_status(store, req_id, "pending", reason="t")
        assert result["path"] == []
        # No event emitted for a no-op.
        events_path = Path(store.data_dir) / ".loom-events.jsonl"
        if events_path.exists():
            events = [
                json.loads(l) for l in
                events_path.read_text(encoding="utf-8").splitlines() if l.strip()
            ]
            assert not any(e.get("event") == "status_changed" for e in events)


class TestSetStatusOtherKinds:
    """D2: only kind=requirement uses the strict graph. Other kinds
    keep their per-kind enum validation but no transition restrictions."""

    def test_finding_can_skip(self, store):
        # finding: preliminary → confirmed (or any other valid kind value)
        # without a graph traversal.
        req_id = _mk_req(
            store, "f", kind="finding", domain="experimental",
            status="preliminary",
        )
        result = services.set_status(
            store, req_id, "confirmed", reason="evidence in",
        )
        # Direct hop; no graph fast-forward.
        assert result["status"] == "confirmed"
        # Path is just the target (not multi-hop).
        assert result["path"] == ["confirmed"]

    def test_methodology_free_transitions(self, store):
        req_id = _mk_req(
            store, "m", kind="methodology", domain="experimental",
            status="proposed",
        )
        # methodology: proposed → deprecated directly (no in_progress).
        services.set_status(store, req_id, "deprecated", reason="r")
        assert store.get_requirement(req_id).status == "deprecated"


# ---------------------------------------------------------------------------
# Deprecation warning on missing reason
# ---------------------------------------------------------------------------


class TestSetStatusReasonWarning:
    def test_missing_reason_warns(self, store):
        req_id = _mk_req(store, "x")
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            services.set_status(store, req_id, "in_progress")
            # Find our deprecation warning specifically.
            relevant = [
                w for w in ws
                if issubclass(w.category, DeprecationWarning)
                and "reason=" in str(w.message)
            ]
            assert relevant, "expected DeprecationWarning about reason="

    def test_with_reason_no_warning(self, store):
        req_id = _mk_req(store, "x")
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            services.set_status(
                store, req_id, "in_progress", reason="testing",
            )
            relevant = [
                w for w in ws
                if issubclass(w.category, DeprecationWarning)
                and "reason=" in str(w.message)
            ]
            assert not relevant

    def test_auto_trigger_no_warning(self, store):
        # Auto-advance hooks pass _trigger= — that suppresses the warning.
        req_id = _mk_req(store, "x")
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            services.set_status(
                store, req_id, "in_progress", _trigger="link",
            )
            relevant = [
                w for w in ws
                if issubclass(w.category, DeprecationWarning)
                and "reason=" in str(w.message)
            ]
            assert not relevant


# ---------------------------------------------------------------------------
# Auto-advance — link hook
# ---------------------------------------------------------------------------


class TestLinkAutoAdvance:
    def test_first_link_bumps_pending_to_in_progress(
        self, store, fake_embedding, tmp_path, monkeypatch,
    ):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        req_id = _mk_req(store, "x")
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        services.link(store, str(f), req_ids=[req_id])
        assert store.get_requirement(req_id).status == "in_progress"

    def test_link_on_in_progress_is_idempotent(
        self, store, fake_embedding, tmp_path, monkeypatch,
    ):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        req_id = _mk_req(store, "x")
        services.set_status(
            store, req_id, "implemented", reason="manual",
        )
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        services.link(store, str(f), req_ids=[req_id])
        # No downgrade — still implemented.
        assert store.get_requirement(req_id).status == "implemented"

    def test_link_evidences_does_not_advance_finding(
        self, store, fake_embedding, tmp_path, monkeypatch,
    ):
        # M15: auto-advance only fires for kind=requirement. Findings
        # have their own (free) lifecycle; evidences-links don't bump.
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        req_id = _mk_req(
            store, "finding x", kind="finding", domain="experimental",
            status="preliminary",
        )
        f = tmp_path / "f.json"
        f.write_text("{}")
        services.link(store, str(f), req_ids=[req_id])
        # Status unchanged (finding's preliminary status is preserved).
        assert store.get_requirement(req_id).status == "preliminary"


# ---------------------------------------------------------------------------
# Auto-advance — test_verify hook
# ---------------------------------------------------------------------------


class TestVerifyHook:
    def test_verify_bumps_in_progress_to_implemented(self, store):
        from loom.testspec import TestSpec, TestSpecStore

        req_id = _mk_req(store, "x")
        services.set_status(
            store, req_id, "in_progress", reason="manual",
        )
        spec_store = TestSpecStore(store.data_dir)
        spec_store.add_spec(TestSpec(
            req_id=req_id,
            description="test for x",
            steps=["x"], expected="works", automated=False,
        ))
        result = services.test_verify(store, req_id)
        assert result["status_advanced"] is True
        assert store.get_requirement(req_id).status == "implemented"

    def test_verify_fast_forwards_from_pending(self, store):
        from loom.testspec import TestSpec, TestSpecStore

        req_id = _mk_req(store, "x")
        # Status is pending; test_verify should fast-forward through
        # in_progress → implemented.
        spec_store = TestSpecStore(store.data_dir)
        spec_store.add_spec(TestSpec(
            req_id=req_id,
            description="t",
            steps=["x"], expected="w", automated=False,
        ))
        services.test_verify(store, req_id)
        assert store.get_requirement(req_id).status == "implemented"

    def test_verify_does_not_downgrade(self, store):
        from loom.testspec import TestSpec, TestSpecStore

        req_id = _mk_req(store, "x")
        services.set_status(store, req_id, "verified", reason="t")
        spec_store = TestSpecStore(store.data_dir)
        spec_store.add_spec(TestSpec(
            req_id=req_id,
            description="t",
            steps=["x"], expected="w", automated=False,
        ))
        result = services.test_verify(store, req_id)
        assert result["status_advanced"] is False
        assert store.get_requirement(req_id).status == "verified"


# ---------------------------------------------------------------------------
# verify_stable
# ---------------------------------------------------------------------------


class TestVerifyStable:
    def test_eligible_requires_implemented_status(self, store):
        # A pending req is never eligible.
        _mk_req(store, "x")
        result = services.verify_stable(store)
        assert result["eligible"] == []

    def test_eligible_when_no_drift_events(self, store):
        req_id = _mk_req(store, "x")
        services.set_status(
            store, req_id, "implemented", reason="manual",
        )
        result = services.verify_stable(store, days=14)
        assert len(result["eligible"]) == 1
        assert result["eligible"][0]["req_id"] == req_id
        assert result["dry_run"] is True
        assert result["applied"] == 0
        # Still implemented — dry-run doesn't mutate.
        assert store.get_requirement(req_id).status == "implemented"

    def test_apply_promotes_to_verified(self, store):
        req_id = _mk_req(store, "x")
        services.set_status(
            store, req_id, "implemented", reason="manual",
        )
        result = services.verify_stable(store, days=14, apply=True)
        assert result["applied"] == 1
        assert store.get_requirement(req_id).status == "verified"

    def test_recent_drift_blocks_eligibility(self, store):
        req_id = _mk_req(store, "x")
        services.set_status(
            store, req_id, "implemented", reason="manual",
        )
        # Write a fake drift_detected event for this req.
        events_path = Path(store.data_dir) / ".loom-events.jsonl"
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text(
            json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": "drift_detected",
                "req_ids": [req_id],
                "signals": ["content"],
            }) + "\n",
            encoding="utf-8",
        )
        result = services.verify_stable(store, days=14)
        assert result["eligible"] == []

    def test_old_drift_outside_window_does_not_block(self, store):
        req_id = _mk_req(store, "x")
        services.set_status(
            store, req_id, "implemented", reason="manual",
        )
        # Drift event 30 days ago — outside the 14-day window.
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        events_path = Path(store.data_dir) / ".loom-events.jsonl"
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text(
            json.dumps({
                "ts": old_ts,
                "event": "drift_detected",
                "req_ids": [req_id],
                "signals": ["content"],
            }) + "\n",
            encoding="utf-8",
        )
        result = services.verify_stable(store, days=14)
        assert len(result["eligible"]) == 1

    def test_non_requirement_kinds_excluded(self, store):
        req_id = _mk_req(
            store, "f", kind="finding", domain="experimental",
            status="preliminary",
        )
        # Even if we force the status to "implemented" (which isn't
        # valid for findings, but suppose it were), the verify_stable
        # filter excludes by kind.
        result = services.verify_stable(store)
        assert result["eligible"] == []


# ---------------------------------------------------------------------------
# M15.3 — Doctor stale-pending + metrics pending-age
# ---------------------------------------------------------------------------


class TestStalePendingAlarm:
    def test_no_warning_for_recent_pending(self, store):
        # Fresh pending requirement, no warning.
        _mk_req(store, "x")
        result = services.doctor(store)
        assert result["checks"]["stale_pending"]["count"] == 0

    def test_no_warning_for_old_pending_with_impls(
        self, store, fake_embedding, tmp_path, monkeypatch,
    ):
        # Old pending WITH impls is not stale — it's normal in-progress
        # work whose status hasn't been bumped (the auto-advance will
        # catch it on the next link, but until then, no warning).
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        req_id = _mk_req(store, "x")
        # Backdate the req to 60 days ago.
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        store.update_requirement(req_id, {"timestamp": old_ts})
        # Link an impl.
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        services.link(store, str(f), req_ids=[req_id])
        # link() will auto-advance to in_progress, but force back to
        # pending to model "old pending with impls" explicitly.
        store.update_requirement(req_id, {"status": "pending"})
        result = services.doctor(store)
        assert result["checks"]["stale_pending"]["count"] == 0

    def test_warning_fires_for_old_unlinked_pending(self, store):
        req_id = _mk_req(store, "x")
        # Backdate to 45 days ago.
        old_ts = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        store.update_requirement(req_id, {"timestamp": old_ts})
        result = services.doctor(store)
        assert result["checks"]["stale_pending"]["count"] == 1
        assert any("pending >30d" in w for w in result["warnings"])

    def test_only_requirement_kind_counts(self, store):
        # An old, unlinked finding/methodology shouldn't trigger.
        req_id = _mk_req(
            store, "f", kind="finding", domain="experimental",
            status="preliminary",
        )
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        store.update_requirement(req_id, {"timestamp": old_ts})
        result = services.doctor(store)
        assert result["checks"]["stale_pending"]["count"] == 0


class TestPendingAgeMetrics:
    def test_pending_age_includes_p50_p95(self, store):
        _mk_req(store, "a")
        _mk_req(store, "b")
        _mk_req(store, "c")
        m = services.metrics(store)
        assert "requirement" in m["pending_age"]
        block = m["pending_age"]["requirement"]
        assert block["count"] == 3
        assert "p50_days" in block
        assert "p95_days" in block
        assert "count_over_30d" in block

    def test_pending_age_split_by_kind(self, store):
        _mk_req(store, "r")
        _mk_req(store, "f", kind="finding", domain="experimental",
                status="preliminary")
        m = services.metrics(store)
        # Both kinds appear because both default-statuses count as
        # "pending-equivalent" (pending for requirement, preliminary
        # for finding).
        assert "requirement" in m["pending_age"]
        assert "finding" in m["pending_age"]
        assert m["pending_age"]["requirement"]["count"] == 1
        assert m["pending_age"]["finding"]["count"] == 1

    def test_advanced_status_not_counted(self, store):
        # in_progress / implemented / verified are NOT pending-equivalent.
        req_id = _mk_req(store, "x")
        services.set_status(
            store, req_id, "in_progress", reason="moved on",
        )
        m = services.metrics(store)
        # No requirement bucket because the only req is in_progress.
        if "requirement" in m["pending_age"]:
            assert m["pending_age"]["requirement"]["count"] == 0
