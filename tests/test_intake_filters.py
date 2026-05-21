"""
Tests for src/loom/intake_filters.py — M14.2.

Table-driven against the real M14.1 audit corpus
(experiments/pilot/intake_audit_labels.json). Each case is the
original triggering message + the classifier kind, with the audit's
y/n/? label as the expected outcome.

Acceptance (per M14.2 plan):
  - precision >=95% on known-good (y-labeled): the screens should NOT
    skip these. Currently 11 y-labeled captures.
  - recall >=80% on known-noise (n-labeled): the screens SHOULD skip
    at least 80% of these. Currently 9 n-labeled captures.

The corpus is small (25), so the tests run as parameterized cases
rather than a stochastic check. As the corpus grows the suite stays
the same shape — just more rows.
"""
from __future__ import annotations

import pytest

from loom.intake_filters import (
    KIND_BYPASS,
    _looks_like_scenario_paste,
    _looks_like_session_scoped,
    _looks_like_speculation,
    _looks_like_tool_docs,
    screen_message,
)


# Corpus drawn from experiments/pilot/intake_audit_labels.json. Each
# row is (req_id, label, kind, message). Messages are the user prompts
# that drove the capture; we re-read them from the rationale field on
# the persisted req where the original message wasn't logged
# (pre-M14.1 records).
AUDIT_CORPUS: list[tuple[str, str, str, str]] = [
    # --- y-labeled (real captures the screen MUST let through) ---
    (
        "REQ-c0e06e44", "y", "requirement",
        "all of our experimental findings, for all tests, must be retained in github",
    ),
    (
        "REQ-0023dae0", "y", "process_rule",
        "Loom doctor's domain whitelist (behavior/ui/data/architecture/terminology) "
        "is requirement-kind only. Findings (kind=finding, domain=experimental) and "
        "process_rules (kind=process_rule, domain=operational) trigger spurious "
        "'Non-standard domains' warnings even though those domains are correct for "
        "non-requirement kinds.",
    ),
    (
        "REQ-0a83d16a", "y", "finding",
        "Empirically observed: Loom doctor's coverage check applies uniformly across "
        "all kinds, counting findings and process-rules as 'requirements missing test "
        "specs.'",
    ),
    (
        "REQ-94590539", "y", "process_rule",
        "If the loom dev hits a substrate issue (something doesn't behave as the doc "
        "says), they should flag back to me and I'll fix on the Driftgraph side. If "
        "they hit a Loom-side issue (their validators don't produce good output, "
        "latency is too high, etc.), that's for them to iterate on.",
    ),
    (
        "REQ-4dfc60c0", "y", "finding",
        "Confusion LOOSE (any pause counts) overstates FP because rule-conflict / "
        "ambiguity pauses count too: TP=50  FP=30  FN=0  TN=20  P=0.625  R=1.0",
    ),
    (
        "REQ-0ecbb866", "y", "methodology",
        "What I'd ask before merging v3 to production: Two things, in priority order: "
        "Cross-model replication. Until v3 holds across at least one frontier model, "
        "treat it as qwen3.5-specific. Counterfactual prompt ablation. Same eval set.",
    ),
    (
        "REQ-3789ccba", "y", "finding",
        "these results are very remarkable. it kind of leads me to believe that "
        "framing your prompts for an llm when you're trying to instruct it or guide "
        "it to do. things is heavily dependent on the model and if you switch or if "
        "you have the model change automatically, this could have the opposite "
        "effect for all of your preconditions that you set in your prompt",
    ),
    (
        "REQ-8f4d0d2a", "y", "finding",
        "Qwen: S1=0, S2=0, S3=100 — that's S1=S2 < S3, not S1<S2<S3. "
        "What's actually shared across vendors is 'S1 is at the bottom, S3 is at "
        "the top.' S2's position is contested.",
    ),
    (
        "REQ-310651fc", "y", "methodology",
        "please kick off n=30",
    ),
    (
        "REQ-aec89441", "y", "hypothesis",
        # The load-bearing FP guard test: speculative opener BUT
        # contains "must be adjusted" claim → should pass screen.
        "I'm wondering if we can build a model for how prompts that are intended "
        "to work the same, must be adjusted across different models to achieve "
        "the same levels of compliance and conformance when switching models?",
    ),
    (
        "REQ-df576710", "y", "methodology",
        "starting to think we have to think less about the actual paper, text and "
        "more about revising our methodology and experimentation cuz as it stands "
        "right now from your results from the analysis, half of everything that we "
        "looked at and investigated and modeled seems to be broken or in a bad state",
    ),
    # --- n-labeled (noise the screen SHOULD catch) ---
    (
        "REQ-8a9f714b", "n", "requirement",
        "please implement the the m11.3",
    ),
    (
        "REQ-e9aa56bc", "n", "process_rule",
        "please note that both loom and drift graph development are under the same "
        "host, so you should be able to see drift graph source code and "
        "documentation locally in the SDR graph database repository",
    ),
    (
        "REQ-4293cb48", "n", "hypothesis",
        "I'm interested to see if we can try development tasks to see how well "
        "this system performs relative to a control",
    ),
    (
        "REQ-b5cdf541", "n", "hypothesis",
        "I'm thinking we may want to create a very large synthetic data set of "
        "many different scenarios of which we want to be able to flag or track so "
        "that we can validate that this works across many different scenarios... "
        "what kind of experiment do you think we can create such that it is more "
        "rigorous in terms of what we're testing",
    ),
    (
        "REQ-b1eca25c", "n", "process_rule",
        "Yes, I would like you to format the response and write it to a file on "
        "the file system and then give me the path to the file on the file system.",
    ),
    (
        "REQ-c17b7a6f", "n", "process_rule",
        "no need to commit this file",
    ),
    (
        "REQ-c0907768", "n", "requirement",
        "Ok I'd like you to continue without the API key and use max for the "
        "rationale arc replication",
    ),
    (
        "REQ-13af719e", "n", "requirement",
        "catch and swallow errors thrown by doFetch on every attempt. Do NOT "
        "propagate errors from this function. Return null when all attempts fail.",
    ),
    (
        "REQ-accfaacc", "n", "requirement",
        "If this event is something the user would act on now, send a "
        "PushNotification. Routine or benign output doesn't need one.",
    ),
]


@pytest.mark.parametrize("req_id,label,kind,message", AUDIT_CORPUS)
def test_screen_matches_audit_label(req_id, label, kind, message):
    """For each audit-labeled capture, the screen verdict should
    match (y → capture, n → skip). Borderline (?) cases are
    excluded — they're allowed to go either way."""
    verdict, reason = screen_message(message, {"kind": kind})
    if label == "y":
        assert verdict == "capture", (
            f"{req_id} ({kind}) should pass screen but was skipped: "
            f"{reason!r}"
        )
    elif label == "n":
        assert verdict == "skip", (
            f"{req_id} ({kind}) should be skipped but passed screen "
            f"(reason field: {reason!r})"
        )


def test_precision_on_known_good_is_100():
    """Recompute precision over the y-labeled corpus to surface a
    single number even if individual parametrized tests pass."""
    good = [c for c in AUDIT_CORPUS if c[1] == "y"]
    passed = sum(
        1 for _, _, kind, msg in good
        if screen_message(msg, {"kind": kind})[0] == "capture"
    )
    precision = passed / len(good)
    assert precision >= 0.95, (
        f"screen rejected {len(good) - passed} of {len(good)} real captures; "
        f"precision={precision:.3f}, target>=0.95"
    )


def test_recall_on_known_noise_at_least_80pct():
    noise = [c for c in AUDIT_CORPUS if c[1] == "n"]
    caught = sum(
        1 for _, _, kind, msg in noise
        if screen_message(msg, {"kind": kind})[0] == "skip"
    )
    recall = caught / len(noise)
    assert recall >= 0.80, (
        f"screen caught only {caught} of {len(noise)} noise captures; "
        f"recall={recall:.3f}, target>=0.80"
    )


# ---------------------------------------------------------------------------
# Detector-level micro-tests (so a regression points at the right
# detector, not just at the orchestrator)
# ---------------------------------------------------------------------------


class TestSessionScoped:
    def test_please_implement(self):
        assert _looks_like_session_scoped("please implement the m11.3", {})[0]

    def test_i_would_like_you_to(self):
        assert _looks_like_session_scoped(
            "Yes, I would like you to format the response", {},
        )[0]

    def test_no_need_to(self):
        assert _looks_like_session_scoped("no need to commit this file", {})[0]

    def test_continue_without(self):
        assert _looks_like_session_scoped(
            "Ok I'd like you to continue without the API key", {},
        )[0]

    def test_please_note_fyi(self):
        assert _looks_like_session_scoped(
            "please note that both projects live on the same host", {},
        )[0]

    def test_legit_requirement_passes(self):
        # No session-scope markers; a real workflow rule.
        assert not _looks_like_session_scoped(
            "all experimental findings must be retained in github", {},
        )[0]


class TestScenarioPaste:
    def test_camelcase_plus_imperative(self):
        # The audit case: 1 camelCase + "must" + "throw" → flagged.
        skip, _ = _looks_like_scenario_paste(
            "catch and swallow errors thrown by doFetch on every attempt. "
            "Do NOT propagate errors from this function.",
            {},
        )
        assert skip

    def test_project_context_inhibits(self):
        # "our doFetch" signals project ownership — pass.
        skip, _ = _looks_like_scenario_paste(
            "our doFetch helper must catch errors", {},
        )
        assert not skip

    def test_no_camelcase_passes(self):
        skip, _ = _looks_like_scenario_paste(
            "all results must be retained", {},
        )
        assert not skip

    def test_camelcase_without_imperative_passes(self):
        # Conversational mention of a function name, no directive
        skip, _ = _looks_like_scenario_paste(
            "we ran benchmarkSuite yesterday and got 12pp", {},
        )
        assert not skip


class TestToolDocs:
    def test_classic_tool_doc_paste(self):
        skip, _ = _looks_like_tool_docs(
            "If this event is something the user would act on now, send a "
            "PushNotification. Routine or benign output doesn't need one.",
            {},
        )
        assert skip

    def test_first_person_inhibits(self):
        # An opinion that mentions a tool name → not tool docs.
        skip, _ = _looks_like_tool_docs(
            "we should call PushNotification when the build breaks", {},
        )
        assert not skip

    def test_long_message_inhibits(self):
        # Length cap — discussion containing a tool name is not docs.
        long_msg = (
            "If we add a new event type, send a PushNotification. " * 10
        )
        skip, _ = _looks_like_tool_docs(long_msg, {})
        assert not skip

    def test_no_tool_name_passes(self):
        skip, _ = _looks_like_tool_docs(
            "If the user clicks submit, send an email", {},
        )
        assert not skip


class TestSpeculation:
    def test_im_interested_to_see_if(self):
        skip, _ = _looks_like_speculation(
            "I'm interested to see if we can try development tasks", {},
        )
        assert skip

    def test_what_kind_of_experiment(self):
        skip, _ = _looks_like_speculation(
            "what kind of experiment do you think we can create", {},
        )
        assert skip

    def test_speculation_with_declarative_claim_passes(self):
        # Critical: REQ-aec89441-shape input. Speculative opener BUT
        # contains "must be adjusted" → real hypothesis, must pass.
        skip, _ = _looks_like_speculation(
            "I'm wondering if we can build a model for how prompts that are "
            "intended to work the same, must be adjusted across different "
            "models",
            {},
        )
        assert not skip

    def test_no_speculation_opener_passes(self):
        skip, _ = _looks_like_speculation(
            "we should retain all experimental findings", {},
        )
        assert not skip


class TestKindBypass:
    def test_finding_bypasses_screen(self):
        # Even with a screen-positive message, kind=finding bypasses.
        verdict, reason = screen_message(
            "please implement m11.3",  # session-scoped pattern
            {"kind": "finding"},
        )
        assert verdict == "capture"
        assert "kind-bypass" in reason

    def test_methodology_bypasses_screen(self):
        verdict, reason = screen_message(
            "no need to commit this file",  # session-scoped pattern
            {"kind": "methodology"},
        )
        assert verdict == "capture"
        assert "kind-bypass" in reason

    def test_requirement_does_not_bypass(self):
        verdict, _ = screen_message(
            "please implement m11.3",
            {"kind": "requirement"},
        )
        assert verdict == "skip"

    def test_hypothesis_does_not_bypass(self):
        verdict, _ = screen_message(
            "I'm interested to see if we can try X",
            {"kind": "hypothesis"},
        )
        assert verdict == "skip"

    def test_kind_bypass_set(self):
        # Pin the bypass set so we notice if it changes silently.
        assert KIND_BYPASS == frozenset({"finding", "methodology"})


class TestOrchestrator:
    def test_empty_message_passes(self):
        # Don't blow up on empty input; let the existing pipeline
        # handle "nothing to classify."
        verdict, _ = screen_message("", {"kind": "requirement"})
        assert verdict == "capture"

    def test_missing_kind_defaults_to_requirement(self):
        # If classification dict has no kind, default to requirement
        # (most restrictive) — fail-closed to noise rather than open.
        verdict, _ = screen_message(
            "please implement m11.3", {},
        )
        assert verdict == "skip"

    def test_reason_includes_detector_name(self):
        # Reason string must let the audit attribute the skip to a
        # specific detector for iteration.
        _, reason = screen_message(
            "no need to commit this file", {"kind": "requirement"},
        )
        assert reason.startswith("session_scoped")
