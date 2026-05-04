"""Tests for the Loom ← Driftgraph inbound channel (M13.5).

The module's design is "fail to no signal on every error path" —
that's what these tests exercise. We avoid spinning up a real Neo4j
in CI by monkeypatching the connect() helper + the imported chains
module. The one path that does need a live substrate (smoke test
against a running bot) lives in `experiments/pilot/` instead.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from loom import driftgraph_query as dq


# ---------------------------------------------------------------------------
# Repo discovery
# ---------------------------------------------------------------------------


class TestRepoDiscovery:
    def test_env_override_wins(self, tmp_path, monkeypatch):
        # Build a fake Driftgraph repo layout — enough to satisfy the
        # discovery probe (chains.py file at the right path).
        fake = tmp_path / "fake-driftgraph"
        (fake / "product" / "discord_demo").mkdir(parents=True)
        (fake / "product" / "discord_demo" / "chains.py").write_text("# stub")
        monkeypatch.setenv("LOOM_DRIFTGRAPH_PATH", str(fake))
        assert dq._resolve_driftgraph_root() == fake

    def test_env_override_invalid_path_falls_through(self, tmp_path, monkeypatch):
        # Env var set but path doesn't have chains.py → ignored;
        # falls through to defaults.
        monkeypatch.setenv("LOOM_DRIFTGRAPH_PATH", str(tmp_path / "nope"))
        # Also force defaults to miss so we get None.
        monkeypatch.setattr(dq, "_DEFAULT_DRIFTGRAPH_PATHS", [])
        assert dq._resolve_driftgraph_root() is None

    def test_default_paths_searched_in_order(self, tmp_path, monkeypatch):
        # Two candidate dirs; only the second is real.
        first = tmp_path / "first"
        second = tmp_path / "second"
        (second / "product" / "discord_demo").mkdir(parents=True)
        (second / "product" / "discord_demo" / "chains.py").write_text("# stub")
        monkeypatch.delenv("LOOM_DRIFTGRAPH_PATH", raising=False)
        monkeypatch.setattr(dq, "_DEFAULT_DRIFTGRAPH_PATHS", [first, second])
        assert dq._resolve_driftgraph_root() == second


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_returns_false_when_repo_missing(self, monkeypatch):
        # Force discovery to fail.
        monkeypatch.setattr(dq, "_modules_loaded", True)
        monkeypatch.setattr(dq, "_chains_mod", None)
        monkeypatch.setattr(dq, "_schema_mod", None)
        assert dq.is_available() is False

    def test_returns_false_when_neo4j_unreachable(self, monkeypatch):
        # Modules loaded but connect() raises.
        monkeypatch.setattr(dq, "_modules_loaded", True)
        monkeypatch.setattr(dq, "_chains_mod", MagicMock())
        schema = MagicMock()
        schema.connect.side_effect = ConnectionError("Neo4j down")
        monkeypatch.setattr(dq, "_schema_mod", schema)
        assert dq.is_available() is False

    def test_returns_true_when_both_present_and_reachable(self, monkeypatch):
        monkeypatch.setattr(dq, "_modules_loaded", True)
        monkeypatch.setattr(dq, "_chains_mod", MagicMock())
        schema = MagicMock()
        driver = MagicMock()
        driver.verify_connectivity.return_value = None
        schema.connect.return_value = driver
        monkeypatch.setattr(dq, "_schema_mod", schema)
        assert dq.is_available() is True
        # connect was called and the driver was closed cleanly.
        driver.close.assert_called_once()


# ---------------------------------------------------------------------------
# find_drifted_ancestors_for_claim
# ---------------------------------------------------------------------------


def _stub_modules_with_session(monkeypatch, *, session_data: list[dict] | None = None,
                               raises: Exception | None = None):
    """Wire up a fake driver/session that returns ``session_data`` rows
    when run() is called, OR raises ``raises`` if set."""
    monkeypatch.setattr(dq, "_modules_loaded", True)
    monkeypatch.setattr(dq, "_chains_mod", MagicMock())
    schema = MagicMock()
    driver = MagicMock()
    if raises:
        driver.session.side_effect = raises
    else:
        sess = MagicMock()
        result = MagicMock()
        result.data.return_value = session_data or []
        sess.run.return_value = result
        sess.__enter__ = lambda self_: sess
        sess.__exit__ = lambda self_, *a: False
        driver.session.return_value = sess
    schema.connect.return_value = driver
    monkeypatch.setattr(dq, "_schema_mod", schema)
    return driver


class TestFindDriftedAncestorsForClaim:
    def test_returns_empty_when_module_unavailable(self, monkeypatch):
        monkeypatch.setattr(dq, "_modules_loaded", True)
        monkeypatch.setattr(dq, "_chains_mod", None)
        monkeypatch.setattr(dq, "_schema_mod", None)
        assert dq.find_drifted_ancestors_for_claim("p", "clm_x") == []

    def test_returns_empty_for_empty_args(self, monkeypatch):
        _stub_modules_with_session(monkeypatch, session_data=[])
        assert dq.find_drifted_ancestors_for_claim("", "clm_x") == []
        assert dq.find_drifted_ancestors_for_claim("p", "") == []

    def test_returns_empty_when_no_drifted_ancestors(self, monkeypatch):
        # Cypher returned a row but with NULL ancestor (the OPTIONAL
        # MATCH found no drifted parent). Our filter should drop it.
        _stub_modules_with_session(monkeypatch, session_data=[
            {"ancestor_claim_id": None,
             "ancestor_subject": None,
             "ancestor_predicate": None,
             "ancestor_object": None,
             "invalidated_at": None,
             "hops": None},
        ])
        assert dq.find_drifted_ancestors_for_claim("p", "clm_x") == []

    def test_returns_drifted_ancestor_rows(self, monkeypatch):
        _stub_modules_with_session(monkeypatch, session_data=[
            {"ancestor_claim_id": "clm_dead",
             "ancestor_subject": "old finding",
             "ancestor_predicate": "states",
             "ancestor_object": "X",
             "invalidated_at": 1730000000,
             "hops": 1},
        ])
        result = dq.find_drifted_ancestors_for_claim("p", "clm_live")
        assert len(result) == 1
        assert result[0]["ancestor_claim_id"] == "clm_dead"
        assert result[0]["hops"] == 1

    def test_swallows_neo4j_errors(self, monkeypatch):
        # Driver raised mid-session — must not bubble up.
        _stub_modules_with_session(
            monkeypatch, raises=RuntimeError("Neo4j connection lost"),
        )
        assert dq.find_drifted_ancestors_for_claim("p", "clm_x") == []


# ---------------------------------------------------------------------------
# find_drifted_ancestors_for_req — the convenience wrapper
# ---------------------------------------------------------------------------


class TestFindDriftedAncestorsForReq:
    def test_no_signal_when_unavailable(self, monkeypatch, tmp_path):
        monkeypatch.setattr(dq, "is_available", lambda: False)
        out = dq.find_drifted_ancestors_for_req(tmp_path, "REQ-x")
        assert out == {
            "drifted": False, "claim_ids": [],
            "drifted_ancestors": [], "available": False,
        }

    def test_no_active_claims_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(dq, "is_available", lambda: True)
        # warrants log doesn't exist for this tmp_path → no claims.
        out = dq.find_drifted_ancestors_for_req(tmp_path, "REQ-x")
        assert out["available"] is True
        assert out["claim_ids"] == []
        assert out["drifted"] is False

    def test_walks_active_claims_when_available(self, monkeypatch, tmp_path):
        # Seed a warrants log with one push for REQ-x.
        from loom import warrants
        warrants.record_push(
            tmp_path, req_id="REQ-x", validator_id="v1",
            score=1.0, project_tag="sparkeye",
            response={"episode_id": "ep", "claim_ids": ["clm_a", "clm_b"]},
            endpoint_url="http://x",
        )
        monkeypatch.setattr(dq, "is_available", lambda: True)
        # Stub the per-claim query so we know what it's called with.
        calls: list[tuple[str, str]] = []
        def fake_per_claim(project, claim_id):
            calls.append((project, claim_id))
            # Mark clm_a as drifted, clm_b as clean.
            if claim_id == "clm_a":
                return [{"ancestor_claim_id": "clm_dead", "hops": 1,
                         "ancestor_subject": "x", "invalidated_at": 1}]
            return []
        monkeypatch.setattr(
            dq, "find_drifted_ancestors_for_claim", fake_per_claim,
        )

        out = dq.find_drifted_ancestors_for_req(tmp_path, "REQ-x")
        assert out["available"] is True
        assert out["claim_ids"] == ["clm_a", "clm_b"]
        assert calls == [("sparkeye", "clm_a"), ("sparkeye", "clm_b")]
        assert out["drifted"] is True
        assert len(out["drifted_ancestors"]) == 1
        assert out["drifted_ancestors"][0]["claim_id"] == "clm_a"

    def test_no_project_tag_in_log_returns_empty(self, monkeypatch, tmp_path):
        # Push log exists but project_tag was missing somehow.
        # Should degrade silently — no Neo4j call attempted.
        from loom import warrants
        warrants.record_push(
            tmp_path, req_id="REQ-x", validator_id="v1",
            score=1.0, project_tag="",  # empty tag
            response={"episode_id": "ep", "claim_ids": ["clm_a"]},
            endpoint_url="http://x",
        )
        monkeypatch.setattr(dq, "is_available", lambda: True)
        called = []
        monkeypatch.setattr(
            dq, "find_drifted_ancestors_for_claim",
            lambda p, c: called.append((p, c)) or [],
        )
        out = dq.find_drifted_ancestors_for_req(tmp_path, "REQ-x")
        assert out["drifted"] is False
        # No Neo4j call attempted because project_tag is empty.
        assert called == []
