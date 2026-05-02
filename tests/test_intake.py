"""Tests for the M11.5 P1 intake-hook scaffold.

Two test classes:
- ``TestParsersAndHelpers``: pure functions (parse_classifier_output,
  _has_softener, _last_json_object). No store, no LLM.
- ``TestProcessMessage``: branch decision logic with the classifier
  monkey-patched. Drives every branch (noop / propose / auto_link /
  captured_with_rationale / rationale_needed / duplicate) plus the
  guardrails (softener, domain whitelist, daily budget).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from loom import intake, services
from loom.store import Implementation, LoomStore, Requirement, generate_content_hash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path) -> LoomStore:
    return LoomStore("test-intake", data_dir=tmp_path)


@pytest.fixture
def fake_embedding():
    return [0.1] * 768


def _seed_req(store, req_id, value, *, domain="behavior",
              embedding=None, rationale="seed"):
    embedding = embedding or [0.1] * 768
    services.extract(
        store, domain=domain, value=value, rationale=rationale,
    )
    # extract auto-generates the id; the test wants known ids so
    # we just rely on the deterministic hash.


def _stub_classifier(monkeypatch, output: dict | None,
                     latency_ms: int = 100, error: str | None = None):
    """Monkey-patch intake.classify_message so tests don't need
    Ollama or Anthropic running."""
    def fake_classify(message, *, model=None, timeout=60):
        return {
            "output": output, "latency_ms": latency_ms,
            "model": model or "stub", "error": error,
        }
    monkeypatch.setattr(intake, "classify_message", fake_classify)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestParsersAndHelpers:
    def test_parse_clean_positive_json(self):
        text = ('{"is_requirement": true, "domain": "behavior", '
                '"value": "X must Y", "rationale_excerpt": "because Z"}')
        out = intake.parse_classifier_output(text)
        assert out["is_requirement"] is True
        assert out["domain"] == "behavior"

    def test_parse_clean_negative_json(self):
        out = intake.parse_classifier_output('{"is_requirement": false}')
        assert out == {"is_requirement": False}

    def test_parse_with_code_fence(self):
        text = "```json\n{\"is_requirement\": false}\n```"
        out = intake.parse_classifier_output(text)
        assert out == {"is_requirement": False}

    def test_parse_with_leading_prose(self):
        text = ('Here is the analysis:\n\n'
                '{"is_requirement": true, "domain": "data", '
                '"value": "X stores Y", "rationale_excerpt": ""}')
        out = intake.parse_classifier_output(text)
        assert out["is_requirement"] is True
        assert out["domain"] == "data"

    def test_parse_malformed_returns_none(self):
        assert intake.parse_classifier_output("not json at all") is None
        assert intake.parse_classifier_output("") is None
        assert intake.parse_classifier_output("{not_json: ") is None

    def test_parse_missing_required_fields_returns_none(self):
        # Positive but missing domain → None (production callers
        # treat this as "not a requirement").
        text = '{"is_requirement": true, "value": "X must Y"}'
        assert intake.parse_classifier_output(text) is None

    def test_softener_detected(self):
        assert intake._has_softener("Make this faster if possible.")
        assert intake._has_softener("Maybe we should rate-limit X.")
        assert intake._has_softener("Try to avoid throwing.")
        assert intake._has_softener("Would be nice to have logging.")
        assert intake._has_softener("Ideally the API stays stable.")

    def test_softener_not_detected_in_firm_statements(self):
        assert not intake._has_softener("Users must confirm before deleting.")
        assert not intake._has_softener("All endpoints require auth.")
        assert not intake._has_softener("Don't propagate errors.")

    def test_predicted_req_id_matches_extract(self, store):
        # Extract a req and verify the helper's prediction matches
        # what extract actually generated.
        result = services.extract(
            store, domain="behavior", value="some specific req",
            rationale="r",
        )
        predicted = intake._predicted_req_id("behavior", "some specific req")
        assert predicted == result["req_id"]

    def test_predicted_req_id_is_case_and_whitespace_normalized(self):
        # extract() lowercases domain and strips value whitespace;
        # the predictor must match exactly.
        a = intake._predicted_req_id("BEHAVIOR", "  rate limit  ")
        b = intake._predicted_req_id("behavior", "rate limit")
        assert a == b


# ---------------------------------------------------------------------------
# process_message — branch logic
# ---------------------------------------------------------------------------


class TestProcessMessage:
    def test_noop_when_classifier_says_not_requirement(self, store, monkeypatch):
        _stub_classifier(monkeypatch, {"is_requirement": False})
        out = intake.process_message(store, "What does this do?")
        assert out["branch"] == "noop"
        assert out["req_id"] is None
        assert out["reminder"] == ""

    def test_noop_when_classifier_errors(self, store, monkeypatch):
        _stub_classifier(monkeypatch, None, error="LLM unavailable")
        out = intake.process_message(store, "anything")
        assert out["branch"] == "noop"

    def test_noop_when_parse_fails(self, store, monkeypatch):
        _stub_classifier(monkeypatch, None)
        out = intake.process_message(store, "anything")
        assert out["branch"] == "noop"

    def test_rationale_needed_when_no_candidates_and_no_excerpt(self, store, monkeypatch):
        _stub_classifier(monkeypatch, {
            "is_requirement": True, "domain": "behavior",
            "value": "Wholly novel requirement nothing matches",
            "rationale_excerpt": "",
        })
        out = intake.process_message(store, "x")
        assert out["branch"] == "rationale_needed"
        assert out["req_id"] is None
        assert "rationale" in out["reminder"].lower()

    def test_captured_with_rationale_when_no_candidates_but_excerpt(self, store, monkeypatch):
        _stub_classifier(monkeypatch, {
            "is_requirement": True, "domain": "behavior",
            "value": "Some requirement with explained reason",
            "rationale_excerpt": "we had an incident in March.",
        })
        out = intake.process_message(store, "x")
        assert out["branch"] == "captured_with_rationale"
        assert out["req_id"] is not None
        # Persisted with the rationale.
        req = store.get_requirement(out["req_id"])
        assert req.rationale == "we had an incident in March."
        assert req.status == "pending"

    def test_propose_branch_when_score_below_auto_link_threshold(
        self, store, monkeypatch, fake_embedding,
    ):
        # Seed a parent so find_related has something to return,
        # but stub find_related to give a deliberately-mid score.
        services.extract(store, domain="behavior",
                         value="parent decision", rationale="origin")

        _stub_classifier(monkeypatch, {
            "is_requirement": True, "domain": "behavior",
            "value": "child requirement",
            "rationale_excerpt": "",
        })
        # Force find_related_requirements to return a single
        # below-threshold candidate.
        def fake_find(store_, text, *, limit, min_score):
            r = next(iter(store.list_requirements()))
            return [{
                "req_id": r.id, "domain": r.domain, "value": r.value,
                "rationale": r.rationale, "rationale_links": [],
                "score": 0.70,  # ≥0.66 but <0.80
            }]
        monkeypatch.setattr(services, "find_related_requirements", fake_find)

        out = intake.process_message(store, "child requirement")
        assert out["branch"] == "propose"
        assert out["req_id"] is None  # not persisted
        assert len(out["candidates"]) == 1
        assert "0.7" in out["reminder"]

    def test_auto_link_branch_when_score_high(
        self, store, monkeypatch, fake_embedding,
    ):
        parent = services.extract(
            store, domain="behavior",
            value="parent for auto-link", rationale="origin",
        )

        _stub_classifier(monkeypatch, {
            "is_requirement": True, "domain": "behavior",
            "value": "auto-linkable derivative requirement",
            "rationale_excerpt": "",
        })
        def fake_find(store_, text, *, limit, min_score):
            return [{
                "req_id": parent["req_id"], "domain": "behavior",
                "value": "parent for auto-link",
                "rationale": "origin", "rationale_links": [],
                "score": 0.90,  # above AUTO_LINK_THRESHOLD
            }]
        monkeypatch.setattr(services, "find_related_requirements", fake_find)

        out = intake.process_message(store, "x")
        assert out["branch"] == "auto_link"
        assert out["req_id"] is not None
        assert out["rationale_links"] == [parent["req_id"]]
        # Verify persisted with linkage.
        req = store.get_requirement(out["req_id"])
        assert req.rationale_links == [parent["req_id"]]
        assert req.status == "pending"

    def test_softener_downgrades_auto_link_to_propose(
        self, store, monkeypatch,
    ):
        services.extract(
            store, domain="behavior", value="parent", rationale="origin",
        )

        _stub_classifier(monkeypatch, {
            "is_requirement": True, "domain": "behavior",
            "value": "Make this faster if possible",  # softener
            "rationale_excerpt": "",
        })
        def fake_find(store_, text, *, limit, min_score):
            r = next(iter(store.list_requirements()))
            return [{
                "req_id": r.id, "domain": r.domain, "value": r.value,
                "rationale": r.rationale, "rationale_links": [],
                "score": 0.95,  # would normally trigger auto-link
            }]
        monkeypatch.setattr(services, "find_related_requirements", fake_find)

        out = intake.process_message(store, "x")
        assert out["branch"] == "propose"
        assert out["softener_triggered"] is True
        assert out["req_id"] is None

    def test_domain_whitelist_blocks_auto_link(self, store, monkeypatch):
        services.extract(
            store, domain="ui", value="parent ui", rationale="origin",
        )

        _stub_classifier(monkeypatch, {
            "is_requirement": True, "domain": "ui",  # NOT in whitelist
            "value": "ui requirement",
            "rationale_excerpt": "",
        })
        def fake_find(store_, text, *, limit, min_score):
            r = next(iter(store.list_requirements()))
            return [{
                "req_id": r.id, "domain": "ui", "value": r.value,
                "rationale": r.rationale, "rationale_links": [],
                "score": 0.95,
            }]
        monkeypatch.setattr(services, "find_related_requirements", fake_find)

        out = intake.process_message(store, "x")
        assert out["branch"] == "propose"
        assert out["domain_whitelist_blocked"] is True

    def test_daily_budget_exhaustion_downgrades_to_propose(
        self, store, monkeypatch,
    ):
        parent = services.extract(
            store, domain="behavior", value="parent", rationale="origin",
        )
        # Pre-populate the intake log with auto-link entries that
        # exhaust the budget for today.
        log_path = intake._intake_log_path(store)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).isoformat()
        with log_path.open("w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({
                    "ts": today, "branch": "auto_link",
                }) + "\n")

        _stub_classifier(monkeypatch, {
            "is_requirement": True, "domain": "behavior",
            "value": "another req",
            "rationale_excerpt": "",
        })
        def fake_find(store_, text, *, limit, min_score):
            return [{
                "req_id": parent["req_id"], "domain": "behavior",
                "value": "parent", "rationale": "origin",
                "rationale_links": [],
                "score": 0.95,
            }]
        monkeypatch.setattr(services, "find_related_requirements", fake_find)

        # daily_budget=2 → 3 prior auto-links exceed it.
        out = intake.process_message(store, "x", daily_budget=2)
        assert out["branch"] == "propose"
        assert out["budget_exceeded"] is True

    def test_duplicate_branch_when_id_collides_with_top_candidate(
        self, store, monkeypatch,
    ):
        # Seed an existing requirement, then "intake" the same value
        # again. The deterministic id will match and we should hit
        # the duplicate branch.
        existing = services.extract(
            store, domain="behavior",
            value="exact-duplicate value text",
            rationale="origin",
        )

        _stub_classifier(monkeypatch, {
            "is_requirement": True, "domain": "behavior",
            "value": "exact-duplicate value text",  # same id
            "rationale_excerpt": "",
        })
        def fake_find(store_, text, *, limit, min_score):
            return [{
                "req_id": existing["req_id"], "domain": "behavior",
                "value": "exact-duplicate value text",
                "rationale": "origin", "rationale_links": [],
                "score": 1.0,
            }]
        monkeypatch.setattr(services, "find_related_requirements", fake_find)

        out = intake.process_message(store, "x")
        assert out["branch"] == "duplicate"
        assert out["req_id"] == existing["req_id"]
        assert "duplicate" in out["reminder"].lower()

    def test_log_records_branch_and_latency(self, store, monkeypatch):
        _stub_classifier(monkeypatch, {"is_requirement": False}, latency_ms=42)
        intake.process_message(store, "What does X do?")
        log_path = intake._intake_log_path(store)
        assert log_path.exists()
        lines = [
            json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        assert lines
        last = lines[-1]
        assert last["branch"] == "noop"
        assert last["classifier_latency_ms"] == 42
