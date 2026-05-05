"""Tests for the Driftgraph cache (M13.5d) — both the read-side
event-replay logic and the receiver's HMAC verification."""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from loom import driftgraph_cache as dc


# ---------------------------------------------------------------------------
# Cache file primitives
# ---------------------------------------------------------------------------


class TestRecordEvent:
    def test_creates_jsonl_with_received_at(self, tmp_path):
        dc.record_event(tmp_path, {"event": "claim_invalidated",
                                    "claim_id": "clm_x"})
        path = dc.cache_path(tmp_path)
        assert path.exists()
        line = path.read_text(encoding="utf-8").strip()
        rec = json.loads(line)
        assert rec["event"] == "claim_invalidated"
        assert rec["claim_id"] == "clm_x"
        assert "received_at" in rec  # auto-stamped

    def test_preserves_caller_received_at(self, tmp_path):
        dc.record_event(tmp_path, {
            "event": "foundation_drift",
            "received_at": "2026-05-05T01:00:00+00:00",
        })
        rec = json.loads(dc.cache_path(tmp_path).read_text(encoding="utf-8").strip())
        assert rec["received_at"] == "2026-05-05T01:00:00+00:00"

    def test_record_failure_silent(self, tmp_path):
        # data_dir that can't be created (existing file at the path).
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir")
        # Must not raise — silent failure is the contract.
        dc.record_event(blocker / "subdir",
                        {"event": "claim_invalidated", "claim_id": "x"})


class TestHasCache:
    def test_false_when_missing(self, tmp_path):
        assert dc.has_cache(tmp_path) is False

    def test_false_when_empty_file(self, tmp_path):
        # Touch the file but write nothing — caller should still
        # treat as "no cache yet" (no events have arrived).
        dc.cache_path(tmp_path).touch()
        assert dc.has_cache(tmp_path) is False

    def test_true_after_first_event(self, tmp_path):
        dc.record_event(tmp_path, {"event": "claim_created", "claim_id": "x"})
        assert dc.has_cache(tmp_path) is True


# ---------------------------------------------------------------------------
# Replay logic — compute_claim_state
# ---------------------------------------------------------------------------


class TestComputeClaimState:
    def test_unknown_claim_returns_clean_state(self, tmp_path):
        s = dc.compute_claim_state(tmp_path, "clm_unknown")
        assert s["invalidated"] is False
        assert s["foundation_drifted"] is False
        assert s["drifted_ancestors"] == []

    def test_claim_invalidated_event_marks_state(self, tmp_path):
        dc.record_event(tmp_path, {
            "event": "claim_invalidated",
            "retracted_claim_id": "clm_dead",
            "invalidated_at": "2026-05-05T01:00:00+00:00",
        })
        s = dc.compute_claim_state(tmp_path, "clm_dead")
        assert s["invalidated"] is True
        assert s["invalidated_at"] == "2026-05-05T01:00:00+00:00"

    def test_supersedes_event_marks_state(self, tmp_path):
        # Substrate uses 'supersedes' kind for chat-utterance-driven
        # invalidations; cache should treat it the same as
        # claim_invalidated. (Legacy event name, pre-13.5b.)
        dc.record_event(tmp_path, {
            "event": "supersedes",
            "invalidated_claim_id": "clm_X",
            "by_claim_id": "clm_replacement",
            "detected_at": "2026-05-05T02:00:00+00:00",
        })
        s = dc.compute_claim_state(tmp_path, "clm_X")
        assert s["invalidated"] is True

    def test_claim_superseded_event_phase_13_5b(self, tmp_path):
        # Phase 13.5b webhook event name for chat-driven supersedes.
        dc.record_event(tmp_path, {
            "event": "claim_superseded",
            "superseded_claim_id": "clm_Y",
            "by_claim_id": "clm_new",
            "superseded_at": "2026-05-05T03:00:00+00:00",
            "fired_at": 1730000000,
        })
        s = dc.compute_claim_state(tmp_path, "clm_Y")
        assert s["invalidated"] is True
        assert s["invalidated_at"] == "2026-05-05T03:00:00+00:00"

    def test_foundation_drift_detected_event_phase_13_5b(self, tmp_path):
        # Phase 13.5b uses foundation_drift_detected; cache should
        # treat the same as legacy foundation_drift.
        dc.record_event(tmp_path, {
            "event": "foundation_drift_detected",
            "retracted_claim_id": "clm_dead",
            "retracted_subject": "old finding",
            "dependents": [{"claim_id": "clm_dependent"}],
            "fired_at": 1730000000,
        })
        s = dc.compute_claim_state(tmp_path, "clm_dependent")
        assert s["foundation_drifted"] is True
        assert len(s["drifted_ancestors"]) == 1
        assert s["drifted_ancestors"][0]["ancestor_claim_id"] == "clm_dead"

    def test_foundation_drift_event_records_ancestors(self, tmp_path):
        dc.record_event(tmp_path, {
            "event": "foundation_drift",
            "retracted_claim_id": "clm_dead_parent",
            "retracted_subject": "old finding",
            "dependents": [
                {"claim_id": "clm_child_A"},
                {"claim_id": "clm_child_B"},
            ],
            "detected_at": "2026-05-05T03:00:00+00:00",
        })
        # child_A is foundation-drifted
        s = dc.compute_claim_state(tmp_path, "clm_child_A")
        assert s["foundation_drifted"] is True
        assert len(s["drifted_ancestors"]) == 1
        assert s["drifted_ancestors"][0]["ancestor_claim_id"] == "clm_dead_parent"
        assert s["drifted_ancestors"][0]["ancestor_subject"] == "old finding"
        # And so is child_B
        s2 = dc.compute_claim_state(tmp_path, "clm_child_B")
        assert s2["foundation_drifted"] is True
        # But unrelated claim is not
        s3 = dc.compute_claim_state(tmp_path, "clm_unrelated")
        assert s3["foundation_drifted"] is False

    def test_repeat_drift_event_for_same_ancestor_dedupes(self, tmp_path):
        # Same ancestor reported drifted twice (e.g. retry from
        # substrate). Cache should de-dupe by ancestor_claim_id.
        for i in range(2):
            dc.record_event(tmp_path, {
                "event": "foundation_drift",
                "retracted_claim_id": "clm_parent",
                "dependents": [{"claim_id": "clm_child"}],
                "detected_at": f"2026-05-05T0{i+1}:00:00+00:00",
            })
        s = dc.compute_claim_state(tmp_path, "clm_child")
        assert len(s["drifted_ancestors"]) == 1, "should de-dupe"
        # Latest-event timestamp wins.
        assert s["drifted_ancestors"][0]["detected_at"] == "2026-05-05T02:00:00+00:00"

    def test_corrupt_jsonl_line_skipped(self, tmp_path):
        # Manually write a mix of valid + invalid lines — the reader
        # must skip the bad lines and still surface state from the
        # good ones.
        path = dc.cache_path(tmp_path)
        path.write_text(
            "not json at all\n"
            '{"event": "claim_invalidated", "retracted_claim_id": "clm_x"}\n'
            "{incomplete\n",
            encoding="utf-8",
        )
        s = dc.compute_claim_state(tmp_path, "clm_x")
        assert s["invalidated"] is True


# ---------------------------------------------------------------------------
# lookup_drifted_for_req — convenience wrapper used by services.context
# ---------------------------------------------------------------------------


class TestLookupDriftedForReq:
    def test_no_cache_returns_no_signal(self, tmp_path):
        out = dc.lookup_drifted_for_req(tmp_path, "REQ-x")
        assert out["available"] is False
        assert out["drifted"] is False

    def test_cache_present_no_active_claims_returns_empty(self, tmp_path):
        dc.record_event(tmp_path, {"event": "claim_created", "claim_id": "y"})
        out = dc.lookup_drifted_for_req(tmp_path, "REQ-x")
        # available because cache exists, but no active claims for
        # this req in .warrants-log.jsonl.
        assert out["available"] is True
        assert out["claim_ids"] == []
        assert out["drifted"] is False

    def test_walks_active_claims_and_finds_drift(self, tmp_path):
        # Wire up a warrants log so REQ-x has 2 claims; also a drift
        # event for one of them.
        from loom import warrants
        warrants.record_push(
            tmp_path, req_id="REQ-x", validator_id="v1",
            score=1.0, project_tag="sparkeye",
            response={"episode_id": "ep",
                      "claim_ids": ["clm_a", "clm_b"]},
            endpoint_url="http://x",
        )
        dc.record_event(tmp_path, {
            "event": "foundation_drift",
            "retracted_claim_id": "clm_dead",
            "dependents": [{"claim_id": "clm_a"}],  # only a, not b
            "detected_at": "2026-05-05T04:00:00+00:00",
        })

        out = dc.lookup_drifted_for_req(tmp_path, "REQ-x")
        assert out["available"] is True
        assert out["claim_ids"] == ["clm_a", "clm_b"]
        assert out["drifted"] is True
        assert len(out["drifted_ancestors"]) == 1
        entry = out["drifted_ancestors"][0]
        assert entry["claim_id"] == "clm_a"
        assert entry["ancestor"]["ancestor_claim_id"] == "clm_dead"


# ---------------------------------------------------------------------------
# HMAC verification — receiver-side
# ---------------------------------------------------------------------------


class TestReceiverHMAC:
    """Importing the receiver module shouldn't require a running
    HTTP server — we just exercise the verify_hmac helper. The
    integration of the handler with the HTTPServer surface is
    tested via the L3 substrate-side smoke (live).
    """

    def test_verify_hmac_correct_signature(self):
        from hooks.loom_drift_webhook import _verify_hmac
        secret = "deadbeef" * 8
        body = b'{"event":"claim_invalidated","retracted_claim_id":"x"}'
        sig = "sha256=" + hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256,
        ).hexdigest()
        assert _verify_hmac(secret, body, sig) is True

    def test_verify_hmac_rejects_tampered_body(self):
        from hooks.loom_drift_webhook import _verify_hmac
        secret = "deadbeef" * 8
        sig = "sha256=" + hmac.new(
            secret.encode("utf-8"), b'{"a":1}', hashlib.sha256,
        ).hexdigest()
        assert _verify_hmac(secret, b'{"a":2}', sig) is False

    def test_verify_hmac_rejects_missing_prefix(self):
        from hooks.loom_drift_webhook import _verify_hmac
        secret = "x" * 64
        body = b"{}"
        digest = hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256,
        ).hexdigest()
        # No "sha256=" prefix → invalid.
        assert _verify_hmac(secret, body, digest) is False

    def test_verify_hmac_rejects_empty_secret(self):
        from hooks.loom_drift_webhook import _verify_hmac
        assert _verify_hmac("", b"{}", "sha256=anything") is False
