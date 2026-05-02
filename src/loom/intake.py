"""
Intake hook core logic — M11.5 P1 (scaffold).

Classifies a user chat message as requirement-shape or not, runs
``services.find_related_requirements`` against the store when
positive, and routes to one of four branches:

  * ``auto_link`` — top-1 candidate's score ≥ AUTO_LINK_THRESHOLD
                    AND no softener language detected. Persists with
                    ``rationale_links=[top_candidate_id]`` (and
                    optionally top-2 if their score is also high).
  * ``propose`` — candidates exist but below auto-link threshold,
                  OR softener language detected. Returns the
                  candidates for the agent / user to confirm. Does
                  NOT persist.
  * ``captured_with_rationale`` — no candidates found, but the
                                  classifier extracted a verbatim
                                  rationale from the message.
                                  Persists with prose rationale.
  * ``rationale_needed`` — no candidates, no rationale excerpt.
                           Returns a system-reminder asking the
                           agent to ask the user. Does NOT persist.
  * ``noop`` — message is not requirement-shape; nothing to do.

This module is the testable core. Two thin wrappers expose it:

  * ``cli.cmd_intake`` — manual invocation via ``loom intake "..."``.
  * ``hooks/loom_intake.py`` — Claude Code ``UserPromptSubmit``
    hook (unregistered in P1; registration is the M11.5 P2 step).

Spec: ``docs/DESIGN-rationale-linkage.md`` Part 2 — M11.5.
P0 pilot: ``experiments/pilot/FINDINGS-intake-classifier-pilot.md``.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loom import services
from loom.store import LoomStore


# ---------------------------------------------------------------------------
# Calibrated thresholds (M11.5 P0 + design doc)
# ---------------------------------------------------------------------------

# Top-1 candidate score above which we auto-link without asking the
# user. Below this and above services.RATIONALE_LINK_MIN_SCORE (0.66),
# we propose. 0.80 was the spec's recommendation; not separately
# calibrated by P0 because it's about user experience confidence
# more than retrieval correctness.
AUTO_LINK_THRESHOLD = 0.80

# Top-2 inclusion threshold — if both top candidates clear this,
# include both as auto-links (the design doc's "structured citation
# chain" idea). Slightly below AUTO_LINK_THRESHOLD because the
# top-2 mainly serves as supporting context, not the load-bearing
# parent.
AUTO_LINK_TOP2_THRESHOLD = 0.78

# Domains where auto-capture is allowed. Out-of-list domains
# (including the model inventing `security`, observed in P0) get
# routed to the propose branch — user picks/corrects.
AUTO_CAPTURE_DOMAINS = ("behavior", "data", "architecture")

# Daily auto-capture budget. After this many auto-link branches in
# a project's intake log, downgrade to propose for the rest of the
# day. Prevents runaway capture from a noisy session.
DEFAULT_DAILY_BUDGET = int(os.environ.get("LOOM_INTAKE_DAILY_BUDGET", "30"))


# ---------------------------------------------------------------------------
# Softener-detection guardrail (added from M11.5 P0 findings)
# ---------------------------------------------------------------------------
#
# The single false positive in the P0 pilot was "Make this faster
# if possible." — a hedged optimization request, not a real rule.
# When the classified value contains hedging language, downgrade
# auto-capture to propose so the user gets a chance to reject before
# persistence.

_SOFTENERS = (
    r"\bif possible\b",
    r"\bif (?:we|you|i) can\b",
    r"\btry to\b",
    r"\bwould be (?:nice|good)\b",
    r"\bmaybe\b",
    r"\bperhaps\b",
    r"\bconsider(?:ing)?\b",
    r"\bideally\b",
    r"\bsomeday\b",
    r"\bnice to have\b",
)
_SOFTENER_RE = re.compile(
    r"|".join(f"(?:{p})" for p in _SOFTENERS), re.IGNORECASE,
)


def _has_softener(text: str) -> bool:
    return bool(_SOFTENER_RE.search(text or ""))


# ---------------------------------------------------------------------------
# Classifier prompt (verbatim from M11.5 spec)
# ---------------------------------------------------------------------------

CLASSIFIER_PROMPT = """\
You are a requirement-detection classifier for a software project.
The user just sent a message in a chat about the project. Decide
whether the message contains a SOFTWARE REQUIREMENT — a statement
about how the system MUST or SHOULD behave, look, or be structured.

NOT requirements:
  - Questions ("can you...", "what does...", "how do I...")
  - Code edits or fixes ("fix the bug", "make this work")
  - Style preferences without behavior implications ("use 4 spaces")
  - Commentary on the agent's work ("looks good", "try again")

ARE requirements:
  - "X must do Y when Z"
  - "We should rate-limit endpoint X"
  - "Users need to see Y before deleting"
  - "Don't ever propagate errors from the retry loop"

Output JSON only, exactly one of:

  {{"is_requirement": false}}

  {{"is_requirement": true,
    "domain": "behavior" | "ui" | "data" | "architecture" | "terminology",
    "value": "<one-sentence requirement statement>",
    "rationale_excerpt": "<verbatim sentence from the message that explains WHY, or empty string if not present>"}}

User message:
\"\"\"
{user_message}
\"\"\"
"""


def _default_classifier_model() -> str:
    """Mirror the decomposer-model selection logic. Anthropic Haiku
    when ``ANTHROPIC_API_KEY`` is set (better classification, similar
    latency), else qwen3.5:latest (validated in M11.5 P0)."""
    if env := os.environ.get("LOOM_INTAKE_MODEL"):
        return env
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic:claude-haiku-4-5-20251001"
    return "ollama:qwen3.5:latest"


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


def _last_json_object(text: str) -> Any:
    """Walk brace-depth, return the last balanced JSON object, or
    None on miss."""
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
        return json.loads(last)
    except json.JSONDecodeError:
        return None


def parse_classifier_output(content: str) -> Optional[dict]:
    """Parse the classifier's JSON. Tolerates leading/trailing prose
    and triple-backtick json fences. Returns None when the output
    truly can't be parsed — production callers treat that as 'not a
    requirement' (silent no-op) per the M11.5 spec."""
    text = (content or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    obj = _last_json_object(text)
    if not isinstance(obj, dict):
        return None
    if not obj.get("is_requirement"):
        return {"is_requirement": False}
    if not obj.get("domain") or not obj.get("value"):
        return None
    return obj


def classify_message(
    message: str,
    *,
    model: Optional[str] = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Run the classifier prompt over ``message``. Returns
    ``{output, latency_ms, error}`` where ``output`` is the parsed
    dict (or None on parse failure / classifier error)."""
    model = model or _default_classifier_model()
    prompt = CLASSIFIER_PROMPT.format(user_message=message)
    t0 = time.time()
    try:
        resp = services._call_decomposer_llm(model, prompt, timeout=timeout)
    except Exception as e:
        return {
            "output": None,
            "latency_ms": int((time.time() - t0) * 1000),
            "model": model,
            "error": f"{type(e).__name__}: {e}",
        }
    return {
        "output": parse_classifier_output(resp.get("content", "")),
        "latency_ms": int((time.time() - t0) * 1000),
        "model": model,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Daily budget bookkeeping
# ---------------------------------------------------------------------------


def _intake_log_path(store: LoomStore) -> Path:
    return Path(store.data_dir) / ".intake-log.jsonl"


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _today_auto_link_count(store: LoomStore) -> int:
    """Count of ``auto_link`` branches recorded in today's section
    of the intake log. Used by the daily-budget cap."""
    log = _intake_log_path(store)
    if not log.exists():
        return 0
    today = _today_iso()
    count = 0
    try:
        for line in log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("ts", "")
            if not ts.startswith(today):
                continue
            if rec.get("branch") == "auto_link":
                count += 1
    except OSError:
        return 0
    return count


def _record(store: LoomStore, rec: dict) -> None:
    """Append a JSON record to the intake log. Best-effort; logging
    must never break the intake path."""
    rec.setdefault("ts", datetime.now(timezone.utc).isoformat())
    try:
        log = _intake_log_path(store)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Branch decisions
# ---------------------------------------------------------------------------


def _predicted_req_id(domain: str, value: str) -> str:
    """Mirror the deterministic ID hash from ``services.extract`` so
    we can detect duplicate-of-existing before calling extract."""
    import hashlib as _h
    return f"REQ-{_h.sha256(f'{domain.strip().lower()}:{value.strip()}'.encode()).hexdigest()[:8]}"


def _format_reminder(branch: str, payload: dict) -> str:
    """Build the system-reminder text for a branch outcome. Kept
    under 500 chars per spec to fit cleanly in agent context."""
    if branch == "duplicate":
        return (
            f"Loom recognized this as a duplicate of "
            f"{payload['req_id']} (already in the store). No new "
            f"requirement captured. If the wording should be "
            f"updated, use `loom refine {payload['req_id']}`."
        )
    if branch == "auto_link":
        links = ", ".join(payload["rationale_links"])
        return (
            f"Loom captured this as {payload['req_id']} derived from "
            f"{links}. If that's wrong, archive with "
            f"`loom set-status {payload['req_id']} archived` and "
            f"re-extract."
        )
    if branch == "captured_with_rationale":
        return (
            f"Loom captured this as {payload['req_id']} with the "
            f"rationale you supplied. No related prior decisions "
            f"found above the score threshold."
        )
    if branch == "propose":
        lines = [
            f"  - {c['req_id']}: {c['value'][:80]} (score {c['score']})"
            for c in payload["candidates"]
        ]
        return (
            f"Loom thinks this might be a requirement. Possible "
            f"linkages:\n" + "\n".join(lines) + "\n"
            f"If one applies, run `loom extract --derives-from "
            f"REQ-X --rationale \"...\"`. If none, ask the user "
            f"why this is needed and capture the rationale."
        )
    if branch == "rationale_needed":
        return (
            f"Loom detected a requirement but found no rationale "
            f"or related prior decisions. Before editing, ask the "
            f"user *why* this is needed — what's the constraint, "
            f"deadline, or incident this addresses? Then run "
            f"`loom extract --rationale \"...\"`."
        )
    return ""


def process_message(
    store: LoomStore,
    message: str,
    *,
    model: Optional[str] = None,
    msg_id: str = "intake",
    session: str = "intake-hook",
    daily_budget: int = DEFAULT_DAILY_BUDGET,
) -> dict[str, Any]:
    """Run the full intake pipeline. Returns a structured outcome
    dict suitable for both CLI display and the Claude Code hook
    JSON envelope.

    Outcome shape::

        {
            "branch": "auto_link" | "propose" | "captured_with_rationale"
                      | "rationale_needed" | "noop",
            "reminder": str,           # text to inject as system-reminder
            "req_id": str | None,      # set when branch persisted a req
            "candidates": list[dict],  # set on propose / auto_link
            "classification": dict | None,
            "softener_triggered": bool,
            "budget_exceeded": bool,
            "domain_whitelist_blocked": bool,
            "classifier_latency_ms": int,
        }
    """
    cls = classify_message(message, model=model)
    classification = cls["output"]
    cls_latency = cls["latency_ms"]

    # Default outcome — overridden below per branch.
    outcome: dict[str, Any] = {
        "branch": "noop",
        "reminder": "",
        "req_id": None,
        "candidates": [],
        "classification": classification,
        "softener_triggered": False,
        "budget_exceeded": False,
        "domain_whitelist_blocked": False,
        "classifier_latency_ms": cls_latency,
    }

    # Not requirement-shaped, parse failure, or classifier error.
    if cls["error"]:
        _record(store, {
            "branch": "noop", "reason": "classifier_error",
            "error": cls["error"], "classifier_latency_ms": cls_latency,
        })
        return outcome
    if classification is None:
        _record(store, {
            "branch": "noop", "reason": "parse_failed",
            "classifier_latency_ms": cls_latency,
        })
        return outcome
    if not classification.get("is_requirement"):
        _record(store, {
            "branch": "noop", "reason": "not_requirement",
            "classifier_latency_ms": cls_latency,
        })
        return outcome

    # Guardrails before deciding the branch.
    softener = _has_softener(classification["value"])
    domain = classification.get("domain", "")
    domain_blocked = domain not in AUTO_CAPTURE_DOMAINS
    budget_used = _today_auto_link_count(store)
    budget_exceeded = budget_used >= daily_budget
    outcome["softener_triggered"] = softener
    outcome["domain_whitelist_blocked"] = domain_blocked
    outcome["budget_exceeded"] = budget_exceeded

    # Search for candidates. Failures here are non-fatal — fall
    # through to no-candidates handling.
    try:
        candidates = services.find_related_requirements(
            store, classification["value"],
            limit=services.RATIONALE_LINK_TOP_N,
            min_score=services.RATIONALE_LINK_MIN_SCORE,
        )
    except Exception as e:
        _record(store, {
            "branch": "noop", "reason": "find_related_failed",
            "error": str(e),
        })
        candidates = []
    outcome["candidates"] = candidates

    # ---- Duplicate-of-existing detection ----
    # If the classifier's value text would deterministically hash to
    # the same req_id as the top candidate, this is a literal
    # duplicate — the store already has this exact requirement. No
    # new capture, no link to itself.
    predicted_id = _predicted_req_id(
        classification.get("domain", ""), classification["value"],
    )
    if candidates and candidates[0]["req_id"] == predicted_id:
        outcome["branch"] = "duplicate"
        outcome["req_id"] = predicted_id
        outcome["reminder"] = _format_reminder(
            "duplicate", {"req_id": predicted_id},
        )
        _record(store, {
            "branch": "duplicate",
            "captured_req_id": predicted_id,
            "classifier_latency_ms": cls_latency,
            "candidates_top_score": candidates[0]["score"],
            "candidates_count": len(candidates),
        })
        return outcome

    # ---- Branch selection ----
    auto_link_eligible = (
        candidates
        and candidates[0]["score"] >= AUTO_LINK_THRESHOLD
        and not softener
        and not domain_blocked
        and not budget_exceeded
    )

    if auto_link_eligible:
        link_ids = [candidates[0]["req_id"]]
        if (
            len(candidates) >= 2
            and candidates[1]["score"] >= AUTO_LINK_TOP2_THRESHOLD
        ):
            link_ids.append(candidates[1]["req_id"])
        try:
            result = services.extract(
                store,
                domain=domain,
                value=classification["value"],
                rationale=classification.get("rationale_excerpt") or None,
                rationale_links=link_ids,
                msg_id=msg_id,
                session=session,
            )
        except ValueError as e:
            # Extract validation rejected — fall back to propose so
            # the user can fix.
            outcome["branch"] = "propose"
            payload = {"candidates": candidates}
            outcome["reminder"] = (
                f"Loom thought this should auto-link but extract "
                f"rejected it: {e}. Candidates:\n"
                + _format_reminder("propose", payload).split("\n", 1)[1]
            )
            _record(store, {
                "branch": "propose", "reason": "extract_rejected",
                "error": str(e),
                "classifier_latency_ms": cls_latency,
                "candidates_top_score": candidates[0]["score"]
                                          if candidates else None,
                "candidates_count": len(candidates),
            })
            return outcome

        outcome["branch"] = "auto_link"
        outcome["req_id"] = result["req_id"]
        outcome["rationale_links"] = link_ids
        outcome["reminder"] = _format_reminder("auto_link", {
            "req_id": result["req_id"],
            "rationale_links": link_ids,
        })
        _record(store, {
            "branch": "auto_link",
            "captured_req_id": result["req_id"],
            "rationale_links": link_ids,
            "classifier_latency_ms": cls_latency,
            "candidates_top_score": candidates[0]["score"],
            "candidates_count": len(candidates),
            "rationale_source": "linked"
                                + ("+prose"
                                   if classification.get("rationale_excerpt")
                                   else ""),
        })
        return outcome

    if candidates:
        outcome["branch"] = "propose"
        outcome["reminder"] = _format_reminder("propose", {"candidates": candidates})
        _record(store, {
            "branch": "propose",
            "classifier_latency_ms": cls_latency,
            "candidates_top_score": candidates[0]["score"],
            "candidates_count": len(candidates),
            "softener_triggered": softener,
            "domain_whitelist_blocked": domain_blocked,
            "budget_exceeded": budget_exceeded,
        })
        return outcome

    # No candidates — branch on whether the classifier surfaced
    # a verbatim rationale.
    if classification.get("rationale_excerpt"):
        try:
            result = services.extract(
                store,
                domain=domain,
                value=classification["value"],
                rationale=classification["rationale_excerpt"],
                msg_id=msg_id,
                session=session,
            )
        except ValueError as e:
            outcome["branch"] = "noop"
            outcome["reminder"] = (
                f"Loom detected a requirement but extract rejected "
                f"it: {e}"
            )
            _record(store, {
                "branch": "noop", "reason": "extract_rejected",
                "error": str(e),
            })
            return outcome
        outcome["branch"] = "captured_with_rationale"
        outcome["req_id"] = result["req_id"]
        outcome["reminder"] = _format_reminder(
            "captured_with_rationale", {"req_id": result["req_id"]},
        )
        _record(store, {
            "branch": "captured_with_rationale",
            "captured_req_id": result["req_id"],
            "classifier_latency_ms": cls_latency,
            "candidates_top_score": None,
            "candidates_count": 0,
            "rationale_source": "prose",
        })
        return outcome

    outcome["branch"] = "rationale_needed"
    outcome["reminder"] = _format_reminder("rationale_needed", {})
    _record(store, {
        "branch": "rationale_needed",
        "classifier_latency_ms": cls_latency,
        "candidates_top_score": None,
        "candidates_count": 0,
        "rationale_source": "needed",
    })
    return outcome
