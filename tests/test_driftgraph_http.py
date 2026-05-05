"""Tests for the Phase 13.5 substrate read API client (M13.5e).

Network calls are mocked via monkeypatching urllib.request.urlopen
so the suite doesn't need a live Driftgraph bot.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from loom import driftgraph_http as dh


class _FakeResp:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _stub_urlopen(monkeypatch, *, body: bytes, status: int = 200,
                  capture: list | None = None):
    def fake(req, timeout=None):
        if capture is not None:
            capture.append({
                "url": req.full_url,
                "method": req.get_method(),
                "headers": dict(req.headers),
                "data": req.data,
            })
        return _FakeResp(body, status)
    monkeypatch.setattr(dh.urllib.request, "urlopen", fake)


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_true_when_health_returns_200(self, monkeypatch):
        _stub_urlopen(monkeypatch, body=b'{"ok":true}')
        assert dh.is_available() is True

    def test_false_when_substrate_down(self, monkeypatch):
        import urllib.error

        def fake(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(dh.urllib.request, "urlopen", fake)
        assert dh.is_available() is False


# ---------------------------------------------------------------------------
# get_claim_status — Bearer auth
# ---------------------------------------------------------------------------


class TestGetClaimStatus:
    def test_sends_bearer_auth(self, monkeypatch):
        captured: list[dict] = []
        _stub_urlopen(
            monkeypatch,
            body=b'{"claim_id":"clm_x","foundation_drifted":false}',
            capture=captured,
        )
        result = dh.get_claim_status("sparkeye", "clm_x", secret="abc")
        assert result["claim_id"] == "clm_x"
        # urllib lowercases header names.
        auth = captured[0]["headers"].get("Authorization")
        assert auth == "Bearer abc"
        assert "/claims/clm_x?project=sparkeye" in captured[0]["url"]

    def test_returns_none_on_missing_secret(self):
        assert dh.get_claim_status("p", "c", secret="") is None

    def test_returns_none_on_missing_args(self):
        assert dh.get_claim_status("", "c", secret="x") is None
        assert dh.get_claim_status("p", "", secret="x") is None

    def test_swallows_404(self, monkeypatch):
        import urllib.error

        def fake(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 404, "Not Found", {}, io.BytesIO(b'{"error":"x"}'),
            )

        monkeypatch.setattr(dh.urllib.request, "urlopen", fake)
        assert dh.get_claim_status("p", "c", secret="x") is None


# ---------------------------------------------------------------------------
# bulk_claim_lookup — HMAC over body
# ---------------------------------------------------------------------------


class TestBulkClaimLookup:
    def test_sends_hmac_and_returns_dict_keyed_by_id(self, monkeypatch):
        captured: list[dict] = []
        _stub_urlopen(
            monkeypatch,
            body=json.dumps({
                "project": "sparkeye",
                "claims": [
                    {"claim_id": "clm_a", "foundation_drifted": False},
                    {"claim_id": "clm_b", "foundation_drifted": True},
                ],
                "missing": ["clm_ghost"],
            }).encode(),
            capture=captured,
        )
        result = dh.bulk_claim_lookup(
            "sparkeye", ["clm_a", "clm_b", "clm_ghost"], secret="abc",
        )
        assert set(result.keys()) == {"clm_a", "clm_b"}
        assert result["clm_b"]["foundation_drifted"] is True
        # HMAC header set
        sig = captured[0]["headers"].get("X-hub-signature-256")
        assert sig is not None and sig.startswith("sha256=")

    def test_skips_null_entries_in_claims_list(self, monkeypatch):
        # Some substrate versions return null entries for missing
        # IDs in the claims[] list. Client must drop them, not crash.
        _stub_urlopen(
            monkeypatch,
            body=json.dumps({
                "project": "p",
                "claims": [
                    {"claim_id": "clm_real", "foundation_drifted": False},
                    None,
                    {"foundation_drifted": True},  # missing claim_id
                ],
            }).encode(),
        )
        result = dh.bulk_claim_lookup("p", ["clm_real"], secret="x")
        assert list(result.keys()) == ["clm_real"]

    def test_returns_none_on_empty_args(self):
        assert dh.bulk_claim_lookup("", ["c"], secret="x") is None
        assert dh.bulk_claim_lookup("p", [], secret="x") is None
        assert dh.bulk_claim_lookup("p", ["c"], secret="") is None

    def test_raises_on_oversize_batch(self):
        # 500 cap is enforced client-side so callers know to batch.
        with pytest.raises(ValueError, match="capped at 500"):
            dh.bulk_claim_lookup(
                "p", [f"clm_{i}" for i in range(501)], secret="x",
            )


# ---------------------------------------------------------------------------
# list_foundation_drifted
# ---------------------------------------------------------------------------


class TestListFoundationDrifted:
    def test_returns_drifted_claims_list(self, monkeypatch):
        _stub_urlopen(
            monkeypatch,
            body=json.dumps({
                "project": "sparkeye",
                "drifted_claims": [
                    {"claim_id": "clm_x", "broken_chain": []},
                ],
                "count": 1,
            }).encode(),
        )
        result = dh.list_foundation_drifted("sparkeye", secret="abc")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["claim_id"] == "clm_x"

    def test_returns_none_on_unexpected_shape(self, monkeypatch):
        _stub_urlopen(monkeypatch, body=b'{"project":"x"}')  # no drifted_claims
        assert dh.list_foundation_drifted("x", secret="abc") is None


# ---------------------------------------------------------------------------
# find_drifted_ancestors_for_req — convenience wrapper
# ---------------------------------------------------------------------------


class TestFindDriftedAncestorsForReq:
    def test_no_signal_when_substrate_down(self, monkeypatch, tmp_path):
        monkeypatch.setattr(dh, "is_available", lambda: False)
        out = dh.find_drifted_ancestors_for_req(tmp_path, "REQ-x")
        assert out["available"] is False
        assert out["drifted"] is False

    def test_returns_drifted_when_substrate_says_so(self, monkeypatch, tmp_path):
        from loom import warrants
        warrants.record_push(
            tmp_path, req_id="REQ-x", validator_id="v", score=1.0,
            project_tag="sparkeye",
            response={"episode_id": "ep", "claim_ids": ["clm_a"]},
            endpoint_url="http://x",
        )
        monkeypatch.setattr(dh, "is_available", lambda: True)
        monkeypatch.setattr(
            dh, "bulk_claim_lookup",
            lambda project, ids, **kw: {
                "clm_a": {
                    "claim_id": "clm_a",
                    "foundation_drifted": True,
                    "n_invalidated_parents": 1,
                    "because_of_targets": ["clm_dead_parent"],
                },
            },
        )
        out = dh.find_drifted_ancestors_for_req(tmp_path, "REQ-x")
        assert out["drifted"] is True
        assert out["available"] is True
        assert out["claim_ids"] == ["clm_a"]
        assert len(out["drifted_ancestors"]) == 1
        assert out["drifted_ancestors"][0]["ancestor"]["ancestor_claim_id"] == "clm_dead_parent"

    def test_handles_drifted_with_no_because_of_targets(self, monkeypatch, tmp_path):
        # foundation_drifted=True but because_of_targets is empty —
        # substrate detected drift via deeper hop than immediate parent.
        # Client surfaces a placeholder so callers know there's drift.
        from loom import warrants
        warrants.record_push(
            tmp_path, req_id="REQ-x", validator_id="v", score=1.0,
            project_tag="sparkeye",
            response={"episode_id": "ep", "claim_ids": ["clm_a"]},
            endpoint_url="http://x",
        )
        monkeypatch.setattr(dh, "is_available", lambda: True)
        monkeypatch.setattr(
            dh, "bulk_claim_lookup",
            lambda project, ids, **kw: {
                "clm_a": {
                    "claim_id": "clm_a",
                    "foundation_drifted": True,
                    "n_invalidated_parents": 2,
                    "because_of_targets": [],  # empty
                },
            },
        )
        out = dh.find_drifted_ancestors_for_req(tmp_path, "REQ-x")
        assert out["drifted"] is True
        assert len(out["drifted_ancestors"]) == 1
        anc = out["drifted_ancestors"][0]["ancestor"]
        assert anc["ancestor_claim_id"] is None  # placeholder
        assert anc.get("_n_invalidated_parents") == 2
