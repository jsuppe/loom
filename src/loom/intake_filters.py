"""
Intake screening filters — M14.2.

Layer between ``intake.classify_message`` and ``intake.process_message``'s
persistence branches. The classifier's ``is_requirement`` gate catches
the obvious "not a knowledge artifact" cases; the screens here catch
the harder failures the M14.1 audit surfaced:

* **session_scoped** — one-time instructions framed as rules
  ("please implement m11.3", "no need to commit this file")
* **scenario_paste** — pasted spec or harness content where the
  imperative is about a non-project function ("fetchWithRetry must
  catch and swallow errors thrown by doFetch")
* **tool_docs** — third-person tool documentation that reads as an
  instruction but is actually API description ("If this event ...,
  send a PushNotification. Routine output doesn't need one.")
* **speculation** — first-person brainstorm without a declarative
  claim ("I'm interested to see if we can try X")

The screens are deliberately *high-precision, modest-recall* — false
positives (rejecting a real capture) are worse than false negatives
(letting a noise capture through and relying on triage). Per the
M14.1 audit, ``finding`` and ``methodology`` kinds had 100%
classifier precision, so they bypass the screen entirely.

Design intent and audit baseline: REQ-6298a209.
"""
from __future__ import annotations

import re
from typing import Any


# Kinds the M14.1 audit found to be 100% precise on the dogfooded
# store. Captures for these kinds bypass screening entirely.
KIND_BYPASS = frozenset({"finding", "methodology"})


# ---------------------------------------------------------------------------
# Detector: session_scoped
# ---------------------------------------------------------------------------
#
# Catches one-time / file-specific / FYI instructions that should not
# be promoted to project-wide rules. Patterns derive from the 5 audit
# noise captures of this shape:
#   - "please implement the m11.3" (REQ-8a9f714b)
#   - "Yes, I would like you to format the response..." (REQ-b1eca25c)
#   - "no need to commit this file" (REQ-c17b7a6f)
#   - "Ok I'd like you to continue without the API key..." (REQ-c0907768)
#   - "please note that both loom and drift graph development are..." (REQ-e9aa56bc)

_SESSION_SCOPED_PATTERNS = (
    # Conversational openers followed by an instruction to the agent
    r"\b(?:please|ok|okay|yes,?)\s+(?:i'?d like|i would like|i need|i want)\b",
    # Direct first-person instructions to the agent
    r"\bi(?:'d| would)? like (?:you to|us to)\b",
    # Bare "please <verb>" — the canonical "do this now" shape.
    # Whitelisted verbs only to avoid catching e.g. "please note that..."
    # (which has its own pattern below) or "please consider X" (which
    # isn't necessarily session-scoped).
    r"\bplease\s+(?:implement|fix|update|change|add|remove|delete|"
    r"run|stop|do|make|build|create|write|finish|complete|continue)\b",
    # FYI / heads-up framings (env facts, situational context)
    r"\bplease note\b",
    r"\b(?:just|fyi)[, ]+(?:so you know|to (?:let|tell) you)\b",
    # Session/task scope markers
    r"\b(?:for|in) this (?:run|session|task|call|conversation)\b",
    r"\b(?:just|only) (?:this (?:once|time)|for now)\b",
    r"\b(?:no need to|don'?t (?:bother|worry about)|skip(?:ping)?)\b",
    # "Continue [doing X without Y]" — session-state pivot
    r"\b(?:continue|keep going|proceed) (?:without|with(?:out)?|using)\b",
)
_SESSION_SCOPED_RE = re.compile(
    "|".join(f"(?:{p})" for p in _SESSION_SCOPED_PATTERNS),
    re.IGNORECASE,
)


def _looks_like_session_scoped(
    message: str, classification: dict[str, Any],
) -> tuple[bool, str]:
    m = _SESSION_SCOPED_RE.search(message or "")
    if m:
        return (True, f"session-scoped phrase: {m.group(0)!r}")
    return (False, "")


# ---------------------------------------------------------------------------
# Detector: scenario_paste
# ---------------------------------------------------------------------------
#
# Catches harness-spec or example-code paste that the classifier
# captured as a project requirement. Audit case: REQ-13af719e
# ("catch and swallow errors thrown by doFetch on every attempt").
#
# Signal: imperative verb (must / do not / return) appearing alongside
# a camelCase identifier that isn't surrounded by project-context
# words ("our", "the X function in src/...", "this project's").

_CAMEL_RE = re.compile(r"\b[a-z][a-z]*[A-Z][A-Za-z]*\b")
_IMPERATIVE_NEAR_CAMEL_RE = re.compile(
    r"\b(?:must|should|do not|don'?t|return|throw|catch)\b",
    re.IGNORECASE,
)
_PROJECT_CONTEXT_RE = re.compile(
    r"\bour\b|\bthis project\b|\bsrc/[a-z_/]+\b|\bthe [a-z]+ helper\b",
    re.IGNORECASE,
)


def _looks_like_scenario_paste(
    message: str, classification: dict[str, Any],
) -> tuple[bool, str]:
    if not message:
        return (False, "")
    # ≥1 camelCase identifier (function names like doFetch,
    # fetchWithRetry, PushToken). Project context inhibits — a real
    # requirement is more likely to mention "our doFetch" or
    # "src/network.py".
    camels = _CAMEL_RE.findall(message)
    if not camels:
        return (False, "")
    if _PROJECT_CONTEXT_RE.search(message):
        return (False, "")
    # Imperative directive alongside the camelCase signals pasted spec.
    if _IMPERATIVE_NEAR_CAMEL_RE.search(message):
        return (
            True,
            f"camelCase identifier(s) {sorted(set(camels))[:3]} + "
            f"imperative directive, no project context",
        )
    return (False, "")


# ---------------------------------------------------------------------------
# Detector: tool_docs
# ---------------------------------------------------------------------------
#
# Catches pasted tool / API documentation. Audit case: REQ-accfaacc
# (PushNotification docs).
#
# Signal: short message (tool docs are pithy), conditional structure
# ("If X, send/call/show Y"), CamelCase tool name, no first-person
# framing at all.

_FIRST_PERSON_RE = re.compile(
    r"\b(?:i|we|our|my|us|let'?s)\b",
    re.IGNORECASE,
)
_TOOL_NAME_RE = re.compile(
    r"\b[A-Z][a-z]+(?:[A-Z][a-z]+){1,}\b",  # CamelCase ≥2 segments
)
_TOOL_INSTRUCTION_RE = re.compile(
    r"\bif\b.*?\b(?:send|call|show|trigger|emit|notify)\b",
    re.IGNORECASE | re.DOTALL,
)


def _looks_like_tool_docs(
    message: str, classification: dict[str, Any],
) -> tuple[bool, str]:
    if not message:
        return (False, "")
    # Tool-docs are typically pithy. Longer messages are usually
    # discussion/argument — even when they include a tool name, the
    # surrounding prose makes it a real decision capture.
    if len(message) > 350:
        return (False, "")
    if _FIRST_PERSON_RE.search(message):
        return (False, "")
    tool_names = _TOOL_NAME_RE.findall(message)
    if not tool_names:
        return (False, "")
    if _TOOL_INSTRUCTION_RE.search(message):
        return (
            True,
            f"third-person tool-doc framing referencing {tool_names[0]!r}",
        )
    return (False, "")


# ---------------------------------------------------------------------------
# Detector: speculation
# ---------------------------------------------------------------------------
#
# Catches first-person brainstorm framed as hypothesis/requirement
# WITHOUT a declarative claim that would make it falsifiable. Audit
# cases: REQ-4293cb48, REQ-b5cdf541.
#
# Critical FP guard: a real hypothesis like REQ-aec89441 ("I'm
# wondering if we can build a model for how prompts ... MUST BE
# ADJUSTED across different models") opens speculatively but contains
# a declarative MUST-claim. We require BOTH a speculative opener AND
# the absence of a clear declarative claim to fire.

_SPECULATION_OPENER_RE = re.compile(
    r"\bi(?:'m| am) (?:interested|wondering|thinking|curious)\b"
    r"|\b(?:what if|what kind of|what sort of) (?:we|you|i)?\b"
    r"|\b(?:may|might) want to\b"
    r"|\b(?:do you think|what do you think)\b"
    r"|\bjust (?:thinking|brainstorming|wondering)\b"
    r"|\bnot sure (?:if|whether)\b",
    re.IGNORECASE,
)
# A "declarative claim" is the signal a real hypothesis/requirement
# carries even when wrapped in speculative phrasing. If any of these
# show up, treat the message as legitimate — speculative wrapping
# doesn't invalidate a real claim.
_DECLARATIVE_CLAIM_RE = re.compile(
    r"\b(?:must|must not|should|shall|is required|are required|"
    r"will be|cannot|won'?t)\b",
    re.IGNORECASE,
)


def _looks_like_speculation(
    message: str, classification: dict[str, Any],
) -> tuple[bool, str]:
    if not message:
        return (False, "")
    opener = _SPECULATION_OPENER_RE.search(message)
    if not opener:
        return (False, "")
    if _DECLARATIVE_CLAIM_RE.search(message):
        return (False, "")  # speculative framing + real claim ≠ noise
    return (
        True,
        f"speculation opener {opener.group(0)!r} without declarative claim",
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

DETECTORS = (
    ("session_scoped", _looks_like_session_scoped),
    ("scenario_paste", _looks_like_scenario_paste),
    ("tool_docs", _looks_like_tool_docs),
    ("speculation", _looks_like_speculation),
)


def screen_message(
    message: str,
    classification: dict[str, Any],
) -> tuple[str, str]:
    """Decide whether the classifier's positive verdict should
    proceed to capture or be redirected to noop.

    Returns ``("capture", "")`` to let the existing intake pipeline
    run, or ``("skip", reason)`` to short-circuit before
    ``services.extract`` is called. The reason string is the
    detector name + a short explanation; intake logs it so the
    M14.1 audit can be re-run to measure detector hit rate.

    Skips screening entirely for ``kind in {finding, methodology}``,
    which the M14.1 audit found to be 100% precise — the screens
    would only add false-positive risk on these kinds.
    """
    kind = (classification or {}).get("kind", "requirement")
    if kind in KIND_BYPASS:
        return ("capture", f"kind-bypass:{kind}")

    for name, fn in DETECTORS:
        skip, reason = fn(message, classification or {})
        if skip:
            return ("skip", f"{name}: {reason}")
    return ("capture", "")
