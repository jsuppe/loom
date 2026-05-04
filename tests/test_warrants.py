"""Tests for the Loom → Driftgraph warrants integration (M13 / Phase L1).

Two test classes:

  * TestToulminV0  — heuristic shape validator (pure function, no I/O)
  * TestPushHTTP   — push_warrant / push_retraction (network mocked
                     via monkeypatching urllib.request.urlopen)

The L2 canary regression test (must reject 5 obviously-bad rationales)
lives in TestToulminV1Canary at the bottom and is gated on the
existence of the canary dataset; ships when L2's toulmin_v1 lands.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
from pathlib import Path

import pytest

from loom import warrants


# ---------------------------------------------------------------------------
# Toulmin@v0 heuristic
# ---------------------------------------------------------------------------


class TestToulminV0:
    def test_passes_real_loom_rationale(self):
        # The kind=finding rationales captured in the dogfooded loom
        # store are the calibration target — Toulmin@v0 must accept
        # them, otherwise the wire test gates on a tautology.
        r = warrants.toulmin_v0(
            "Source: experiments/bakeoff/v2_driver/phQ3_*, phQ4_* harnesses + "
            "FINDINGS-bakeoff-v2-pythonfirst-smoke.md. Bare cell N≥10 per "
            "condition; rationale cell N≥10 per condition. Reproduced across "
            "phQ3/4/5/7 (different rule shapes)."
        )
        assert r.passes is True
        assert r.score == 1.0
        assert r.validator_id == "toulmin@v0"

    def test_rejects_too_short(self):
        r = warrants.toulmin_v0("because")
        assert r.passes is False
        assert "length" in r.reason

    def test_rejects_no_justification_keyword(self):
        # Long enough, ends cleanly, but doesn't *justify* anything —
        # just restates a fact. Toulmin@v0 should catch this.
        r = warrants.toulmin_v0(
            "The system handles requests and returns responses to clients."
        )
        assert r.passes is False
        assert "justification" in r.reason

    def test_rejects_truncated_mid_sentence(self):
        r = warrants.toulmin_v0(
            "Because of the recent incident we need to add validation to the"
        )
        assert r.passes is False
        assert "complete_sentence" in r.reason

    def test_score_partial_when_some_checks_pass(self):
        # 2 of 3: long + has keyword, but truncated → 2/3 = 0.67.
        r = warrants.toulmin_v0(
            "We measured this in phS and observed a 12pp lift but the"
        )
        assert r.passes is False
        assert r.score == round(2/3, 2)

    def test_handles_none_rationale(self):
        r = warrants.toulmin_v0(None)  # type: ignore[arg-type]
        assert r.passes is False
        assert r.score == 0.0

    def test_handles_empty_string(self):
        r = warrants.toulmin_v0("")
        assert r.passes is False
        assert r.score == 0.0

    def test_to_payload_shape(self):
        r = warrants.toulmin_v0(
            "Because of incident I-2025-04 we measured 95% drop on edge nodes."
        )
        assert r.passes
        payload = r.to_payload(
            project="sparkeye", claim_text="X must Y",
            rationale="Because of incident I-2025-04 we measured 95% drop on edge nodes.",
        )
        # Required Driftgraph contract fields.
        assert payload["project"] == "sparkeye"
        assert payload["validator_id"] == "toulmin@v0"
        assert payload["validator_score"] == 1.0
        assert payload["claim_text"] == "X must Y"
        assert "rationale" in payload
        assert "validator_parts" in payload  # checks dict survives

    def test_keyword_match_is_case_insensitive(self):
        # "phQ" in keywords; "phQ3" in rationale → must match even
        # though the K/R cases differ (regression for the bug found
        # during initial L1 dogfooding — the keyword tuple was
        # lowercased after the fact).
        r = warrants.toulmin_v0(
            "Reproduced in phQ3 and phQ4 across all conditions evaluated."
        )
        # Even without "because", it has phQ as a justification marker.
        assert r.parts["checks"]["justification"] is True


# ---------------------------------------------------------------------------
# HTTP client — network mocked
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 201):
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _stub_urlopen(monkeypatch, *, response_body: bytes,
                  response_status: int = 201,
                  capture: list | None = None):
    """Replace urllib.request.urlopen with a fake that returns a
    pre-canned response and (optionally) appends the request to
    a list for inspection."""
    def fake(req, timeout=None):
        if capture is not None:
            capture.append({
                "url": req.full_url,
                "data": req.data,
                "headers": dict(req.headers),
                "method": req.get_method(),
            })
        return _FakeResponse(response_body, status=response_status)
    monkeypatch.setattr(warrants.urllib.request, "urlopen", fake)


class TestPushWarrant:
    def test_signs_with_hmac_sha256(self, monkeypatch):
        captured: list[dict] = []
        _stub_urlopen(monkeypatch,
                      response_body=b'{"episode_id": "ep_test", "claim_ids": []}',
                      capture=captured)
        secret = "deadbeef" * 8  # 64 chars
        payload = {
            "project": "p", "validator_id": "v", "validator_score": 1.0,
            "claim_text": "c", "rationale": "r",
        }
        warrants.push_warrant(payload, secret=secret, url="http://x/warrants")
        assert len(captured) == 1
        body = captured[0]["data"]
        sig_header = captured[0]["headers"].get("X-hub-signature-256")  # urllib lowercases
        assert sig_header is not None
        expected = "sha256=" + hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256,
        ).hexdigest()
        assert sig_header == expected

    def test_returns_parsed_response(self, monkeypatch):
        _stub_urlopen(
            monkeypatch,
            response_body=b'{"episode_id": "ep_abc", "claim_ids": ["clm_1"]}',
        )
        result = warrants.push_warrant(
            {"project": "p", "validator_id": "v", "validator_score": 0.5,
             "claim_text": "c", "rationale": "r"},
            secret="s", url="http://x/warrants",
        )
        assert result == {"episode_id": "ep_abc", "claim_ids": ["clm_1"]}

    def test_raises_on_4xx(self, monkeypatch):
        # Simulate a 400 by raising HTTPError from urlopen.
        import urllib.error

        class _Err(urllib.error.HTTPError):
            def read(self_inner):
                return b'{"error": "invalid signature"}'

        def fake(req, timeout=None):
            raise _Err(req.full_url, 400, "Bad Request", {}, io.BytesIO())

        monkeypatch.setattr(warrants.urllib.request, "urlopen", fake)
        with pytest.raises(warrants.WarrantPushError) as exc:
            warrants.push_warrant(
                {"project": "p", "validator_id": "v", "validator_score": 0.5,
                 "claim_text": "c", "rationale": "r"},
                secret="s", url="http://x/warrants",
            )
        assert exc.value.status == 400
        assert "invalid signature" in exc.value.body

    def test_raises_when_secret_missing(self, monkeypatch):
        # Both env var and canonical file must be absent / empty.
        monkeypatch.delenv("LOOM_WEBHOOK_SECRET", raising=False)
        monkeypatch.setattr(
            warrants, "SECRET_PATH",
            Path("/nonexistent-l1-test-path/secret"),
        )
        with pytest.raises(ValueError, match="LOOM_WEBHOOK_SECRET"):
            warrants.push_warrant({"project": "p"}, secret=None)

    def test_push_retraction_uses_loom_retraction_validator_id(self, monkeypatch):
        captured: list[dict] = []
        _stub_urlopen(
            monkeypatch,
            response_body=b'{"retracted_claim_id": "clm_x", "supersedes_edges_written": 1}',
            response_status=200, capture=captured,
        )
        warrants.push_retraction(
            project="sparkeye", claim_id="clm_x",
            reason="duplicate of clm_y",
            secret="s", url="http://x/warrants",
        )
        sent = json.loads(captured[0]["data"])
        assert sent["validator_id"] == "loom-retraction"
        assert sent["validator_score"] == 0.0
        assert sent["retraction_target_claim_id"] == "clm_x"
        assert sent["rationale"] == "duplicate of clm_y"


# ---------------------------------------------------------------------------
# Secret loader
# ---------------------------------------------------------------------------


class TestLoadSecret:
    def test_env_var_takes_precedence(self, monkeypatch, tmp_path):
        secret_file = tmp_path / "loom-webhook-secret"
        secret_file.write_text("file-secret")
        monkeypatch.setattr(warrants, "SECRET_PATH", secret_file)
        monkeypatch.setenv("LOOM_WEBHOOK_SECRET", "env-secret")
        assert warrants.load_secret() == "env-secret"

    def test_falls_back_to_file(self, monkeypatch, tmp_path):
        secret_file = tmp_path / "loom-webhook-secret"
        secret_file.write_text("file-secret\n")  # trailing newline → stripped
        monkeypatch.setattr(warrants, "SECRET_PATH", secret_file)
        monkeypatch.delenv("LOOM_WEBHOOK_SECRET", raising=False)
        assert warrants.load_secret() == "file-secret"

    def test_returns_empty_when_neither_set(self, monkeypatch, tmp_path):
        monkeypatch.setattr(warrants, "SECRET_PATH", tmp_path / "missing")
        monkeypatch.delenv("LOOM_WEBHOOK_SECRET", raising=False)
        assert warrants.load_secret() == ""

    def test_empty_string_is_disabled_marker(self, monkeypatch):
        monkeypatch.setenv("LOOM_WEBHOOK_SECRET", "")
        # Explicit empty env var should still trigger the file-fallback;
        # only if BOTH are empty is it "disabled."
        monkeypatch.setattr(
            warrants, "SECRET_PATH",
            Path("/nonexistent-l1-test-path/secret"),
        )
        assert warrants.load_secret() == ""


# ---------------------------------------------------------------------------
# Phase L2 canary regression — gated on toulmin_v1 existing
# ---------------------------------------------------------------------------


class TestWarrantsLog:
    """L3a — claim_id tracking via .warrants-log.jsonl sidecar."""

    def test_record_push_writes_jsonl(self, tmp_path):
        warrants.record_push(
            tmp_path,
            req_id="REQ-x", validator_id="toulmin@v1",
            score=0.75, project_tag="sparkeye",
            response={"episode_id": "ep_1",
                      "claim_ids": ["clm_a", "clm_b"],
                      "edges_written": 0},
            endpoint_url="http://x/warrants",
        )
        log = tmp_path / warrants.WARRANTS_LOG_FILENAME
        assert log.exists()
        rec = json.loads(log.read_text(encoding="utf-8").strip())
        assert rec["event"] == "warrant_pushed"
        assert rec["req_id"] == "REQ-x"
        assert rec["validator_id"] == "toulmin@v1"
        assert rec["score"] == 0.75
        assert rec["claim_ids"] == ["clm_a", "clm_b"]
        assert rec["episode_id"] == "ep_1"

    def test_record_retraction_writes_jsonl(self, tmp_path):
        warrants.record_retraction(
            tmp_path,
            claim_id="clm_a", project_tag="sparkeye",
            reason="superseded by R2",
            response={"retracted_claim_id": "clm_a",
                      "supersedes_edges_written": 1},
            endpoint_url="http://x/warrants",
            triggered_by_req_id="REQ-x",
        )
        log = tmp_path / warrants.WARRANTS_LOG_FILENAME
        rec = json.loads(log.read_text(encoding="utf-8").strip())
        assert rec["event"] == "warrant_retracted"
        assert rec["claim_id"] == "clm_a"
        assert rec["retracted_claim_id"] == "clm_a"
        assert rec["triggered_by_req_id"] == "REQ-x"

    def test_lookup_returns_latest_push_minus_retracted(self, tmp_path):
        # Two pushes for the same REQ; second is "current". Then
        # retract one of the second-push's claim_ids. Lookup should
        # return only the surviving claim from push #2.
        warrants.record_push(
            tmp_path, req_id="REQ-x", validator_id="v1", score=0.8,
            project_tag="p",
            response={"episode_id": "ep1", "claim_ids": ["clm_old1", "clm_old2"]},
            endpoint_url="http://x",
        )
        warrants.record_push(
            tmp_path, req_id="REQ-x", validator_id="v1", score=0.9,
            project_tag="p",
            response={"episode_id": "ep2", "claim_ids": ["clm_new1", "clm_new2"]},
            endpoint_url="http://x",
        )
        warrants.record_retraction(
            tmp_path, claim_id="clm_new1", project_tag="p", reason="",
            response={"retracted_claim_id": "clm_new1",
                      "supersedes_edges_written": 1},
            endpoint_url="http://x",
        )
        active = warrants.lookup_active_claims_for_req(tmp_path, "REQ-x")
        # Latest push wins → clm_new1, clm_new2. Then clm_new1 retracted
        # → only clm_new2 remains.
        assert active == ["clm_new2"]

    def test_lookup_unknown_req_returns_empty(self, tmp_path):
        assert warrants.lookup_active_claims_for_req(tmp_path, "REQ-ghost") == []

    def test_lookup_no_log_file_returns_empty(self, tmp_path):
        # No log = no pushes = no active claims. Must not raise.
        assert warrants.lookup_active_claims_for_req(tmp_path / "missing", "REQ-x") == []

    def test_lookup_latest_push_returns_most_recent_record(self, tmp_path):
        # Two pushes for the same REQ with different project_tags;
        # the latest must win — including its project_tag (M13.L3c
        # bug fix; earlier attempt would lose this and HTTP 404 on
        # the cascade).
        warrants.record_push(
            tmp_path, req_id="REQ-x", validator_id="v1", score=0.8,
            project_tag="old-project",
            response={"episode_id": "ep1", "claim_ids": ["clm_1"]},
            endpoint_url="http://x",
        )
        warrants.record_push(
            tmp_path, req_id="REQ-x", validator_id="v1", score=0.9,
            project_tag="new-project",
            response={"episode_id": "ep2", "claim_ids": ["clm_2"]},
            endpoint_url="http://x",
        )
        latest = warrants.lookup_latest_push_for_req(tmp_path, "REQ-x")
        assert latest is not None
        assert latest["project_tag"] == "new-project"
        assert latest["claim_ids"] == ["clm_2"]
        assert latest["episode_id"] == "ep2"

    def test_lookup_latest_push_returns_none_when_no_pushes(self, tmp_path):
        # Empty log → None (caller treats as "no warrants for this req").
        assert warrants.lookup_latest_push_for_req(tmp_path, "REQ-x") is None
        # Missing log file → None (no crash).
        assert warrants.lookup_latest_push_for_req(
            tmp_path / "missing", "REQ-x",
        ) is None

    def test_record_push_failure_is_silent(self, tmp_path, monkeypatch):
        # If the disk is full / unwritable, we must not crash the
        # push pipeline. Simulate by pointing data_dir at a path we
        # can't create (a file masquerading as a directory).
        bad = tmp_path / "blocker"
        bad.write_text("not a dir")
        # No exception should propagate.
        warrants.record_push(
            bad / "subdir", req_id="REQ-x", validator_id="v1", score=1.0,
            project_tag="p",
            response={"episode_id": "ep", "claim_ids": []},
            endpoint_url="http://x",
        )


class TestFalsifiabilityV1Canary:
    """Phase L3d acceptance: the LLM-driven Falsifiability@v1
    validator must reject all 5 of the curated unfalsifiable
    rationales in ``tests/data/falsifiability_canary_v1.json``.
    Same 0/5 false-positive bar as Toulmin@v1.

    Skipped until ``warrants.falsifiability_v1`` ships in L3d."""

    @pytest.fixture
    def canary_path(self):
        return Path(__file__).parent / "data" / "falsifiability_canary_v1.json"

    def test_canary_dataset_exists(self, canary_path):
        assert canary_path.exists(), (
            "Falsifiability canary dataset missing — Phase L3d "
            "requires tests/data/falsifiability_canary_v1.json with "
            "≥5 unfalsifiable rationales the validator must reject."
        )

    def test_falsifiability_v1_rejects_all_canary_rationales(self, canary_path):
        if not hasattr(warrants, "falsifiability_v1"):
            pytest.skip("falsifiability_v1 ships in Phase L3d")
        if not canary_path.exists():
            pytest.skip("falsifiability canary dataset not yet committed")
        items = json.loads(canary_path.read_text(encoding="utf-8"))
        false_positives = []
        for item in items:
            r = warrants.falsifiability_v1(item["rationale"])
            if r.passes:
                false_positives.append({
                    "id": item["id"],
                    "rationale": item["rationale"],
                    "expected_reject_reason": item.get("expected_reject_reason"),
                    "validator_score": r.score,
                })
        assert false_positives == [], (
            f"Falsifiability@v1 false-positive on "
            f"{len(false_positives)} canary rationale(s); see "
            f"TestFalsifiabilityV1Canary"
        )


class TestToulminV1Canary:
    """Phase L2 acceptance: the LLM-driven Toulmin@v1 validator must
    reject all 5 of the curated bad rationales in
    ``tests/data/toulmin_canary_v1.json``. A single false positive =
    unreliable substrate.

    Skipped until ``warrants.toulmin_v1`` ships in Phase L2."""

    @pytest.fixture
    def canary_path(self):
        return Path(__file__).parent / "data" / "toulmin_canary_v1.json"

    def test_canary_dataset_exists(self, canary_path):
        assert canary_path.exists(), (
            "Canary dataset missing — Phase L2 acceptance requires "
            "tests/data/toulmin_canary_v1.json with ≥5 obviously-bad "
            "rationales the validator must reject."
        )

    def test_toulmin_v1_rejects_all_canary_rationales(self, canary_path):
        if not hasattr(warrants, "toulmin_v1"):
            pytest.skip("toulmin_v1 ships in Phase L2")
        if not canary_path.exists():
            pytest.skip("canary dataset not yet committed")
        items = json.loads(canary_path.read_text(encoding="utf-8"))
        false_positives = []
        for item in items:
            r = warrants.toulmin_v1(item["rationale"])
            if r.passes:
                false_positives.append({
                    "rationale": item["rationale"],
                    "expected_reject_reason": item.get("expected_reject_reason"),
                    "validator_score": r.score,
                })
        assert false_positives == [], (
            f"Toulmin@v1 false-positive on {len(false_positives)} canary "
            f"rationale(s); see TestToulminV1Canary"
        )
