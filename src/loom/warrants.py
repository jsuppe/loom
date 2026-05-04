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
from datetime import datetime, timezone
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


# ---------------------------------------------------------------------------
# Toulmin@v1 — LLM-driven shape extraction (Phase L2)
# ---------------------------------------------------------------------------
#
# Acceptance per PR #13 comment 2:
#   1. Coverage band: 30–60% pass on a 20-rationale sample
#   2. 0/5 false positives on the canary set in
#      tests/data/toulmin_canary_v1.json
#   3. (Bonus, optional) Downstream Driftgraph alignment via Cypher
#
# Threshold rationale: <30% suggests the validator is too strict
# (selecting a tiny minority of rationales as "valid Toulmin"); >60%
# suggests it's pattern-matching rather than philosophically
# evaluating. Inside the band, score distribution shape matters more
# than the exact pass rate — bimodal (most claims ~0.9 or ~0.2) is
# good signal that the validator is making meaningful distinctions;
# clustered around 0.5 means it's hedging and not adding lift.

_TOULMIN_V1_PROMPT = """\
You are a Toulmin-shape validator for a software project's
captured rationales. The Toulmin model says a well-formed
argument has six parts:

  CLAIM      — the assertion being made
  DATA       — facts/evidence the claim rests on
  WARRANT    — the connecting principle that lets DATA support CLAIM
  BACKING    — supporting authority for the WARRANT (often implicit)
  QUALIFIER  — the strength of the claim ("usually", "in production")
  REBUTTAL   — conditions under which the claim doesn't hold

For Toulmin@v1 we evaluate whether a rationale exhibits the four
LOAD-BEARING parts: CLAIM (implicit in the linked requirement),
DATA, WARRANT, and either QUALIFIER or REBUTTAL. BACKING is
optional. A rationale passes if it has data + warrant + (qualifier
OR rebuttal). Fewer than that = rationale is asserted, not argued.

NOT passes:
  - Bare assertion ("This is the right call.")
  - Tautology ("X because X.")
  - Restated WHAT-as-WHY ("must validate inputs because inputs must be validated")
  - Placeholder ("TBD", "because we wanted to")
  - Pure vibe ("seems good", "feels cleaner")

ARE passes:
  - "phS measured a 12pp lift at N=10 on the S1 bench [DATA].
     Anti-rationale beats rule because the model treats hedged
     disclaimers as more authoritative [WARRANT]. Effect held
     across both ANTI_SOFT and ANTI_HARD conditions [QUALIFIER]."
  - "Incident I-2024-04 caused $X in remediation cost when the
     retry loop swallowed errors [DATA]. Don't propagate from the
     retry loop unless the caller opts in [WARRANT]. Exception:
     idempotent reads can re-raise [REBUTTAL]."

Output JSON only, exactly this shape:

  {{"passes": true|false,
    "score": 0.0-1.0,
    "parts": {{
      "data": "<verbatim or paraphrased excerpt, or empty>",
      "warrant": "<verbatim or paraphrased excerpt, or empty>",
      "qualifier": "<verbatim or paraphrased excerpt, or empty>",
      "rebuttal": "<verbatim or paraphrased excerpt, or empty>",
      "backing": "<verbatim or paraphrased excerpt, or empty>"
    }},
    "reason": "<one sentence explaining the pass/fail decision>"}}

Score guidance: 1.0 = all 4 load-bearing parts present;
0.75 = data + warrant + (qualifier OR rebuttal); 0.5 = data +
warrant; 0.25 = only one of data/warrant; 0.0 = none. Pass
threshold is 0.75.

Rationale to evaluate:
\"\"\"
{rationale}
\"\"\"
"""


def _default_toulmin_v1_model() -> str:
    """Mirror the M11.5 classifier model selection: Anthropic Haiku
    when ANTHROPIC_API_KEY is set, else qwen3.5:latest via Ollama.
    Override via LOOM_TOULMIN_V1_MODEL."""
    if env := os.environ.get("LOOM_TOULMIN_V1_MODEL"):
        return env
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic:claude-haiku-4-5-20251001"
    return "ollama:qwen3.5:latest"


def _parse_toulmin_v1_output(content: str) -> Optional[dict]:
    """Parse the LLM's JSON response. Tolerates code fences + leading
    prose. Returns None on unparsable / malformed output (caller
    treats as classifier_error → score 0)."""
    text = (content or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    # Walk brace depth to extract the last balanced JSON object.
    depth = 0
    start = -1
    last = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                last = text[start:i + 1]
                start = -1
    if last is None:
        return None
    try:
        obj = json.loads(last)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if "passes" not in obj or "score" not in obj:
        return None
    return obj


def toulmin_v1(rationale: str, *, model: str | None = None,
               timeout: int = 60) -> ValidatorResult:
    """LLM-driven Toulmin shape extraction (Phase L2). Routes to
    Anthropic Haiku or qwen3.5 depending on env, asks for a
    structured (data/warrant/qualifier/rebuttal) breakdown, returns
    a ValidatorResult with the parts dict populated.

    On any LLM/parse failure: returns passes=False, score=0.0 with
    the failure reason in .reason. Acceptance criteria don't
    distinguish "correctly rejected" from "couldn't evaluate" —
    both mean "not pushing this to Driftgraph."
    """
    # Lazy import: services pulls in the full LLM dispatch surface
    # (Anthropic SDK shape, Ollama HTTP, retry logic, …) which
    # warrants.py shouldn't import at module load just to use v0.
    from . import services

    rationale = (rationale or "").strip()
    if not rationale:
        return ValidatorResult(
            validator_id="toulmin@v1", passes=False, score=0.0,
            reason="empty rationale",
        )

    model = model or _default_toulmin_v1_model()
    prompt = _TOULMIN_V1_PROMPT.format(rationale=rationale)
    try:
        resp = services._call_decomposer_llm(model, prompt, timeout=timeout)
    except Exception as e:
        return ValidatorResult(
            validator_id="toulmin@v1", passes=False, score=0.0,
            reason=f"llm_error: {type(e).__name__}: {e}",
        )

    parsed = _parse_toulmin_v1_output(resp.get("content", ""))
    if parsed is None:
        return ValidatorResult(
            validator_id="toulmin@v1", passes=False, score=0.0,
            reason="parse_failed",
            parts={"raw_content": (resp.get("content") or "")[:400]},
        )

    return ValidatorResult(
        validator_id="toulmin@v1",
        passes=bool(parsed.get("passes", False)),
        score=float(parsed.get("score", 0.0)),
        reason=str(parsed.get("reason", "")),
        parts=parsed.get("parts", {}) or {},
    )


# ---------------------------------------------------------------------------
# Warrants log — claim_id tracking (Phase L3a)
# ---------------------------------------------------------------------------
#
# After every successful push_warrant or push_retraction, we append a
# JSONL record so:
#   - `loom warrant retract --req REQ-id` can look up the most recent
#     claim_ids to retract
#   - `loom supersede` can auto-cascade retractions when
#     LOOM_WARRANTS_AUTO_RETRACT=1
#   - future `loom warrant stats` (Phase L4) can roll up push activity
#
# JSONL chosen over a SQLite table for the same reasons as
# .loom-events.jsonl: append-only, no schema migration, callable from
# anywhere without a store object. Lives at <data_dir>/.warrants-log.jsonl.

WARRANTS_LOG_FILENAME = ".warrants-log.jsonl"


def warrants_log_path(data_dir: pathlib.Path) -> pathlib.Path:
    """The per-project warrants log location."""
    return pathlib.Path(data_dir) / WARRANTS_LOG_FILENAME


def record_push(
    data_dir: pathlib.Path, *,
    req_id: str,
    validator_id: str,
    score: float,
    project_tag: str,
    response: dict,
    endpoint_url: str,
) -> None:
    """Append a push record to the warrants log. Best-effort —
    failure to log must never break the warrant push itself."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "warrant_pushed",
        "req_id": req_id,
        "validator_id": validator_id,
        "score": score,
        "project_tag": project_tag,
        "endpoint": endpoint_url,
        "episode_id": response.get("episode_id"),
        "claim_ids": response.get("claim_ids", []),
        "edges_written": response.get("edges_written"),
    }
    try:
        path = warrants_log_path(data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def record_retraction(
    data_dir: pathlib.Path, *,
    claim_id: str,
    project_tag: str,
    reason: str,
    response: dict,
    endpoint_url: str,
    triggered_by_req_id: str | None = None,
) -> None:
    """Append a retraction record. ``triggered_by_req_id`` is set
    when the retraction came from `--req` lookup or the supersede
    cascade — None for manual claim_id retractions."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "warrant_retracted",
        "claim_id": claim_id,
        "project_tag": project_tag,
        "reason": reason,
        "endpoint": endpoint_url,
        "retracted_claim_id": response.get("retracted_claim_id"),
        "supersedes_edges_written": response.get("supersedes_edges_written"),
        "triggered_by_req_id": triggered_by_req_id,
    }
    try:
        path = warrants_log_path(data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def lookup_latest_push_for_req(
    data_dir: pathlib.Path, req_id: str,
) -> Optional[dict]:
    """Return the most recent ``warrant_pushed`` record for
    ``req_id`` (full record, not just claim_ids), or None if
    nothing's been pushed for this req. Lets callers recover the
    `project_tag` that was used at push time so retractions go to
    the correct project namespace (M13.L3c bug fix — without this,
    the supersede cascade would default to the loom project name
    and Driftgraph would reject with HTTP 404 'project unknown')."""
    path = warrants_log_path(data_dir)
    if not path.exists():
        return None
    latest: Optional[dict] = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (rec.get("event") == "warrant_pushed"
                    and rec.get("req_id") == req_id):
                latest = rec
    except OSError:
        return None
    return latest


def lookup_active_claims_for_req(
    data_dir: pathlib.Path, req_id: str,
) -> list[str]:
    """Return claim_ids most recently pushed for ``req_id`` that
    have not been retracted. "Active" means: appears in the most
    recent push record for this req_id, AND no later retraction
    record references it.

    Empty list = no live warrants for this req. Most callers
    (L3b, L3c) treat this as no-op rather than error."""
    path = warrants_log_path(data_dir)
    if not path.exists():
        return []
    pushed: list[str] = []
    retracted: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("event") == "warrant_pushed" and rec.get("req_id") == req_id:
                # Latest push wins — replace, not append.
                pushed = list(rec.get("claim_ids") or [])
            elif rec.get("event") == "warrant_retracted":
                if cid := rec.get("retracted_claim_id"):
                    retracted.add(cid)
                elif cid := rec.get("claim_id"):
                    retracted.add(cid)
    except OSError:
        return []
    return [cid for cid in pushed if cid not in retracted]
