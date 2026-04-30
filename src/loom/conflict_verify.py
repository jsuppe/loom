"""
LLM-based verifier for Loom conflict detection.

Given a proposed new requirement and an existing one, ask a local LLM
via Ollama whether they conflict. Used by services.conflicts() when the
caller opts in via verify=True.

Model selection (benchmarked in benchmarks/conflicts_verified.py):
    qwen3.5:latest  — 100% precision, 87.5% recall, 0% FP on a synthetic
                      28-candidate dataset. Ties the 32B ceiling.
    llama3.1:8b     — 93/87.5/8.3 at ~2x lower latency.
    gemma4:e4b      — 100/75/0, smaller disk footprint.

Override via LOOM_VERIFY_MODEL env var.

Returns (conflict?, raw_response) — callers can distinguish "model said
NO" from "model error" by inspecting whether raw_response starts with
'<error:'.
"""
from __future__ import annotations

import json
import os
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("LOOM_VERIFY_MODEL", "qwen3.5:latest")
TIMEOUT_S = 60   # leave headroom for cold-start on larger models


SYSTEM_PROMPT = """\
You are reviewing two software requirements to decide whether a human
should review them together before accepting the new one.

Answer YES if the requirements:
- Give different values for the same rule (different numbers, thresholds,
  durations, limits) — a contradiction.
- Directly oppose each other (one allows what the other forbids; one
  requires what the other removes) — a contradiction.
- State the same rule in different words with the same effect — a
  duplicate restatement worth catching.

Answer NO if the requirements:
- Cover different aspects of the same topic (e.g. one talks about
  session expiry, the other about cookie security flags).
- Add an additional constraint without contradicting any existing rule.
- Share vocabulary or domain but describe different behavior.
- Are unrelated.

Answer with exactly one word: YES or NO. No explanation.
"""


def _build_user_prompt(candidate: str, existing: str) -> str:
    return (
        f"Proposed new requirement:\n{candidate}\n\n"
        f"Existing requirement:\n{existing}\n\n"
        f"Do these conflict?"
    )


def verify(
    candidate: str,
    existing: str,
    model: str | None = None,
) -> tuple[bool, str]:
    """Return (conflict?, raw_response).

    On connection or parse failure, returns (False, '<error: ...>') so
    the caller can decide whether to drop the pair or surface the error.
    """
    model = model or DEFAULT_MODEL
    try:
        payload = json.dumps({
            "model": model,
            "stream": False,
            # No-op on non-thinking models; disables reasoning preamble
            # on thinking models (gemma4, qwen3.5) so the yes/no lands
            # in the `content` field.
            "think": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(candidate, existing)},
            ],
            "options": {"temperature": 0.0, "num_predict": 32},
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode())
    except Exception as e:
        return False, f"<error: {e}>"

    content = body.get("message", {}).get("content", "").strip()
    low = content.lower()
    yes_idx = low.find("yes")
    no_idx = low.find("no")
    if yes_idx == -1 and no_idx == -1:
        return False, content
    if yes_idx == -1:
        return False, content
    if no_idx == -1:
        return True, content
    return (yes_idx < no_idx), content
