"""
LLM-driven query expansion for the retrieval benchmark.

Given a user query (often short or jargon-heavy), generate N paraphrases
via Ollama's chat API. Intent: give the embedding model more chances to
match, especially on short queries like "BNPL support" where a single
phrasing lacks enough lexical signal.

This is a benchmark helper, not production code — it's synchronous,
blocks on Ollama, and prints diagnostics on failure. A real integration
would batch, cache, and gracefully degrade.
"""
from __future__ import annotations

import json
import os
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EXPANSION_MODEL = os.environ.get("LOOM_BENCH_MODEL", "llama3.1:8b")
TIMEOUT_S = 15


SYSTEM_PROMPT = """\
You rewrite search queries for a requirements database.

Given a user's query, produce 2 alternative phrasings that preserve the
same intent but use different vocabulary.

Rules:
  - If the query uses jargon or acronyms (e.g. "PCI", "BNPL", "GDPR"),
    expand them into plain English in at least one alternative.
  - If the query is terse (e.g. "Return window"), rewrite at least one
    as a full natural-language question.
  - Do NOT introduce new constraints or assumptions.
  - Output exactly 2 lines, one alternative per line.
  - No numbering, no bullets, no commentary, no quotes.
"""


def expand(query: str) -> list[str]:
    """Return the original query plus up to 2 paraphrases.

    On any failure (timeout, bad JSON, model returning nothing parseable)
    falls back to returning just [query] so the benchmark degrades to
    the baseline rather than crashing.
    """
    try:
        payload = json.dumps({
            "model": EXPANSION_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            "options": {"temperature": 0.3},
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [expand] failed for {query!r}: {e}")
        return [query]

    content = body.get("message", {}).get("content", "").strip()
    if not content:
        return [query]

    # Parse one non-empty line per paraphrase. Strip leading "1.", "- ",
    # and quotes if the model disobeyed the formatting rule.
    paraphrases: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip common disallowed prefixes.
        for prefix in ("1.", "2.", "3.", "-", "*", "•"):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
        line = line.strip("\"'`")
        if line and line.lower() != query.lower():
            paraphrases.append(line)

    # Keep at most 2 paraphrases; prepend the original.
    return [query] + paraphrases[:2]
