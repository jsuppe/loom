"""
Embedding helper for Loom.

Single source of truth for `get_embedding` used by both the CLI
(`scripts/loom`) and the MCP server (`mcp_server/server.py`). Calls
Ollama's `nomic-embed-text` by default and falls back to a deterministic
hash-based pseudo-embedding if Ollama is unreachable.

Keeps a process-local LRU cache keyed by a SHA-256 prefix of the input.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request

_EMBED_DIM = 768
_CACHE_MAX_SIZE = 500
_OLLAMA_URL = "http://localhost:11434/api/embed"

# Simple insertion-ordered LRU; preserved across calls within one process.
_embedding_cache: dict[str, list[float]] = {}


def _cache_key(text: str) -> str:
    """Short content-addressed key for the cache."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _cache_put(key: str, embedding: list[float]) -> None:
    if len(_embedding_cache) >= _CACHE_MAX_SIZE:
        # Evict oldest (insertion-order dict).
        oldest_key = next(iter(_embedding_cache))
        del _embedding_cache[oldest_key]
    _embedding_cache[key] = embedding


def _hash_fallback(text: str) -> list[float]:
    """Deterministic pseudo-embedding. Fine for dev, bad for search quality."""
    h = hashlib.sha256(text.encode()).digest()
    return [(h[i % 32] - 128) / 128.0 for i in range(_EMBED_DIM)]


def get_embedding(
    text: str,
    model: str = "nomic-embed-text",
    max_retries: int = 3,
    use_cache: bool = True,
) -> list[float]:
    """
    Get an embedding vector for `text`.

    Args:
        text: Text to embed.
        model: Ollama model name. Default `nomic-embed-text` (768 dims).
        max_retries: Retries with exponential backoff on transient failures.
        use_cache: If True, consult and populate the process-local LRU.

    Returns a list of `_EMBED_DIM` floats. Always returns a value — falls
    back to a hash-based pseudo-embedding when Ollama is unavailable.
    """
    cache_key = _cache_key(text) if use_cache else None

    if use_cache and cache_key in _embedding_cache:
        return _embedding_cache[cache_key]

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            data = json.dumps({"model": model, "input": text}).encode()
            req = urllib.request.Request(
                _OLLAMA_URL,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                embedding = result["embeddings"][0]
                if use_cache and cache_key is not None:
                    _cache_put(cache_key, embedding)
                return embedding
        except (urllib.error.URLError, TimeoutError, ConnectionResetError) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
                continue
        except KeyError as e:
            # Malformed response — don't retry.
            last_error = e
            break

    print(
        f"⚠️  Ollama unavailable after {max_retries} attempts, "
        f"using fallback embeddings: {last_error}"
    )
    embedding = _hash_fallback(text)
    if use_cache and cache_key is not None:
        _cache_put(cache_key, embedding)
    return embedding
