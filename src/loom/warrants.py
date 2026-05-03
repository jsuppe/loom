"""
Loom → Driftgraph warrants integration (M13 / Phase L1).

Loom owns extraction + philosophical validators (Toulmin v0 heuristic,
Toulmin v1 LLM-driven, …); Driftgraph owns storage + retrieval + drift
mechanics. This module is the boundary: a thin HMAC-authenticated HTTP
client + the on-Loom-side validators that produce the
``{validator_id, validator_score, claim_text, rationale}`` payload
shape Driftgraph's ``/warrants`` endpoint expects.

See ``experiments/philosophical-scaffolds/README.md`` (the section
"Operationalizing the integration: Loom-side build plan") for the
phase plan, acceptance criteria, and the curl smoke-test that proves
the substrate is reachable before any code is written.

Phase L1 (this commit): wire test. Toulmin@v0 is a ~5-line heuristic
that checks rationale shape (length, justification keyword, sentence
completeness). NOT philosophically meaningful — its job is to produce
a payload-shaped result so the contract gets exercised end-to-end.

Phase L2 (next): replace the v0 heuristic with ``toulmin_v1`` —
LLM-driven extraction of (claim, data, warrant, qualifier, rebuttal).
Acceptance: 30–60% coverage on a 20-rationale sample; 0/5 false
positives on the curated canary in ``tests/data/toulmin_canary_v1.json``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import pathlib
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Substrate config
# ---------------------------------------------------------------------------

DEFAULT_ENDPOINT = "http://127.0.0.1:8080/warrants"
DEFAULT_TIMEOUT = 15  # seconds

# Per the Driftgraph dev (PR #13 comment 3): canonical filesystem path.
# Falls back to env var for CI / non-Jon machines; empty = integration
# disabled.
SECRET_PATH = pathlib.Path.home() / ".driftgraph" / "loom-webhook-secret"


def load_secret() -> str:
    """Resolve the HMAC shared secret. Order:
      1. ``$LOOM_WEBHOOK_SECRET`` env var (CI / override)
      2. ``~/.driftgraph/loom-webhook-secret`` canonical file
      3. empty string (treat as "warrants integration disabled")"""
    if env := os.environ.get("LOOM_WEBHOOK_SECRET"):
        return env.strip()
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text(encoding="utf-8").strip()
    return ""


def endpoint() -> str:
    """Resolve the warrants endpoint URL. Override via
    ``$LOOM_WARRANTS_ENDPOINT``; defaults to the same-machine 127.0.0.1
    bot Driftgraph runs in v0 (PR #13 Phase L1 default)."""
    return os.environ.get("LOOM_WARRANTS_ENDPOINT", DEFAULT_ENDPOINT)


# ---------------------------------------------------------------------------
# HTTP client — push_warrant / push_retraction
# ---------------------------------------------------------------------------


class WarrantPushError(RuntimeError):
    """Raised when the substrate rejects a warrant push. Includes the
    HTTP status + response body so callers can decide whether the
    failure is substrate-side (their bug) or Loom-side (our bug)."""

    def __init__(self, status: int, body: str):
        super().__init__(f"Driftgraph rejected warrant push: HTTP {status}: {body}")
        self.status = status
        self.body = body


def push_warrant(payload: dict, *, secret: str | None = None,
                 url: str | None = None,
                 timeout: int = DEFAULT_TIMEOUT) -> dict:
    """POST a validated warrant to the Driftgraph ``/warrants``
    endpoint. Returns the parsed response JSON, typically::

        {"episode_id": "ep_...", "claim_ids": ["clm_...", ...],
         "edges_written": int}

    Required payload keys (Driftgraph contract): ``project``,
    ``validator_id``, ``validator_score``, ``claim_text``, ``rationale``.

    Raises:
        WarrantPushError: substrate returned non-2xx (signature
            mismatch, schema rejection, …).
        urllib.error.URLError: network-level failure (substrate
            unreachable, timeout, …). Phase L4 will add retries; for
            now the caller decides.
        ValueError: secret is empty (integration not configured).
    """
    secret = secret if secret is not None else load_secret()
    if not secret:
        raise ValueError(
            "no LOOM_WEBHOOK_SECRET — set the env var or write the "
            "secret to ~/.driftgraph/loom-webhook-secret"
        )
    url = url or endpoint()
    body = json.dumps(payload).encode("utf-8")
    sig = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256,
    ).hexdigest()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise WarrantPushError(e.code, body_text) from e


def push_retraction(project: str, claim_id: str, reason: str = "",
                    *, secret: str | None = None,
                    url: str | None = None) -> dict:
    """Retract a previously-pushed claim. Driftgraph treats this as a
    SUPERSEDES edge with no replacement; foundation-drift alerts fire
    automatically for downstream BECAUSE_OF dependencies (Phase 9
    behaviour, per PR #13)."""
    return push_warrant({
        "project": project,
        "validator_id": "loom-retraction",
        "validator_score": 0.0,
        "retraction_target_claim_id": claim_id,
        "rationale": reason,
    }, secret=secret, url=url)


# ---------------------------------------------------------------------------
# Toulmin@v0 — heuristic shape check (Phase L1)
# ---------------------------------------------------------------------------


@dataclass
class ValidatorResult:
    """What every validator returns. ``passes`` is the boolean gate;
    ``score`` is the validator's confidence in [0.0, 1.0]; ``reason``
    is human-readable explanation; ``parts`` is optional structured
    breakdown (Toulmin@v1 fills in claim/data/warrant/qualifier/
    rebuttal here)."""
    validator_id: str
    passes: bool
    score: float
    reason: str
    parts: dict[str, Any] = field(default_factory=dict)

    def to_payload(self, *, project: str, claim_text: str,
                   rationale: str) -> dict:
        """Convert to the Driftgraph /warrants payload shape."""
        return {
            "project": project,
            "validator_id": self.validator_id,
            "validator_score": self.score,
            "claim_text": claim_text,
            "rationale": rationale,
            **({"validator_parts": self.parts} if self.parts else {}),
        }


# Heuristic parameters — tuned for "obvious junk doesn't slip through,
# real rationale doesn't get blocked." Calibration target is the M11.5
# pilot rationales + the dogfooded M12 findings (kind=finding entries
# with citations to harness scripts).
_TOULMIN_V0_MIN_LEN = 50
_TOULMIN_V0_JUSTIFY_KEYWORDS = tuple(s.lower() for s in (
    # Justification connectives — at least one signals the rationale
    # is actually trying to explain WHY rather than just restate WHAT.
    # Stored lowercase because the comparison is `kw in rationale.lower()`.
    "because", "given", "since", "due to", "based on",
    "to prevent", "to avoid", "in order to", "so that",
    "measured", "observed", "demonstrated", "shows that",
    "evidence", "phQ", "phS", "phT", "phU", "phR",  # M10 harness refs
    "incident", "outage", "regression",
    "source:",  # the "Source: <path>" prefix loom rationales use
))
# A "complete" sentence ends with terminal punctuation OR (defensive)
# closes a typical rationale tail. Guards against truncated capture.
_TOULMIN_V0_TAIL_RE = re.compile(r'[.!?)\]"\'`>]\s*$')


def toulmin_v0(rationale: str) -> ValidatorResult:
    """Heuristic shape check. Phase L1's job is wire-test, not
    philosophy — this validator just gates on three signals so the
    contract gets exercised with non-trivial filtering:

      1. Length ≥ 50 chars (single-word rationales reject)
      2. Contains at least one justification keyword (signal that
         the rationale is actually explaining rather than restating)
      3. Doesn't end mid-word / mid-sentence (catches truncated capture)

    Score is the fraction of the three checks that pass, mapped to
    {0.0, 0.33, 0.67, 1.0}. Pass if score >= 1.0 (all three).
    Phase L2 replaces this with LLM-driven Toulmin@v1.
    """
    rationale = (rationale or "").strip()
    checks = {
        "length": len(rationale) >= _TOULMIN_V0_MIN_LEN,
        "justification": any(
            kw in rationale.lower() for kw in _TOULMIN_V0_JUSTIFY_KEYWORDS
        ),
        "complete_sentence": bool(_TOULMIN_V0_TAIL_RE.search(rationale)),
    }
    n_pass = sum(checks.values())
    score = round(n_pass / 3.0, 2)
    passes = n_pass == 3
    failed = [k for k, v in checks.items() if not v]
    reason = (
        "all checks pass" if passes
        else f"failed: {', '.join(failed)}"
    )
    return ValidatorResult(
        validator_id="toulmin@v0",
        passes=passes,
        score=score,
        reason=reason,
        parts={"checks": checks},
    )
