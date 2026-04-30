"""
Embedding helper for Loom.

Single source of truth for `get_embedding` used by both the CLI
(`scripts/loom`) and the MCP server (`mcp_server/server.py`).

Providers:
    ollama  — Local Ollama at http://localhost:11434/api/embed.
              Default model: nomic-embed-text (768 dims). Default
              provider when none is configured.
    openai  — OpenAI's REST API at api.openai.com/v1/embeddings.
              Default model: text-embedding-3-small (1536 dims).
              Requires OPENAI_API_KEY in the environment.
    hash    — Deterministic SHA-256-derived pseudo-embedding. Useful
              for tests, offline dev, or when you want a stable
              "search-disabled" mode. Default 768 dims; configurable
              via the model arg ("hash:1536" → 1536 dims).

Selection precedence (highest first):
    1. explicit `provider=` arg to get_embedding()
    2. LOOM_EMBEDDING_PROVIDER env var
    3. embedding_provider in .loom-config.json (when target_dir given)
    4. "ollama"

The cache is keyed by (provider, model, text-sha) so providers don't
collide. Falling back to hash on Ollama outage stays the existing
behavior — but the warning explicitly names the provider that
failed.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

_CACHE_MAX_SIZE = 500

_OLLAMA_URL = "http://localhost:11434/api/embed"
_OLLAMA_DEFAULT_MODEL = "nomic-embed-text"
_OLLAMA_DEFAULT_DIM = 768

_OPENAI_URL = "https://api.openai.com/v1/embeddings"
_OPENAI_DEFAULT_MODEL = "text-embedding-3-small"
_OPENAI_MODEL_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

_HASH_DEFAULT_DIM = 768

# Insertion-ordered LRU; preserved across calls within one process.
_embedding_cache: dict[str, list[float]] = {}


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------

def resolve_provider(
    *,
    explicit: str | None = None,
    target_dir: Path | str | None = None,
) -> str:
    """Pick the embedding provider by precedence.

    Order: explicit arg → LOOM_EMBEDDING_PROVIDER env → config file → "ollama".
    """
    if explicit:
        return explicit.lower()
    env = os.environ.get("LOOM_EMBEDDING_PROVIDER")
    if env:
        return env.lower()
    if target_dir is not None:
        cfg_path = Path(target_dir) / ".loom-config.json"
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                p = cfg.get("embedding_provider")
                if p:
                    return str(p).lower()
            except (json.JSONDecodeError, OSError):
                pass
    return "ollama"


def default_model_for(provider: str) -> str:
    if provider == "ollama":
        return _OLLAMA_DEFAULT_MODEL
    if provider == "openai":
        return _OPENAI_DEFAULT_MODEL
    if provider == "hash":
        return f"hash:{_HASH_DEFAULT_DIM}"
    raise ValueError(f"unknown embedding provider: {provider!r}")


def expected_dim(provider: str, model: str) -> int:
    """Best-effort declared dimension for (provider, model). Used to
    pre-validate a config; the store also records the actual dim of the
    first write."""
    if provider == "ollama":
        # Ollama models vary; nomic-embed-text is 768. Caller can override
        # by passing the actual recorded dim from the store on subsequent
        # writes.
        return _OLLAMA_DEFAULT_DIM
    if provider == "openai":
        return _OPENAI_MODEL_DIMS.get(model, 1536)
    if provider == "hash":
        # `hash:1536` → 1536; `hash` → default
        if ":" in model:
            try:
                return int(model.split(":", 1)[1])
            except ValueError:
                return _HASH_DEFAULT_DIM
        return _HASH_DEFAULT_DIM
    raise ValueError(f"unknown embedding provider: {provider!r}")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_key(provider: str, model: str, text: str) -> str:
    """Content-addressed key including provider+model so two providers
    can't collide on the same text."""
    h = hashlib.sha256(f"{provider}:{model}:{text}".encode()).hexdigest()
    return h[:24]


def _cache_put(key: str, embedding: list[float]) -> None:
    if len(_embedding_cache) >= _CACHE_MAX_SIZE:
        oldest_key = next(iter(_embedding_cache))
        del _embedding_cache[oldest_key]
    _embedding_cache[key] = embedding


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _hash_embedding(text: str, dim: int = _HASH_DEFAULT_DIM) -> list[float]:
    """Deterministic pseudo-embedding from SHA-256.

    Fine for tests and offline use; useless for semantic search since two
    near-identical strings hash to wildly different vectors.
    """
    h = hashlib.sha256(text.encode()).digest()
    return [(h[i % 32] - 128) / 128.0 for i in range(dim)]


def _ollama_embed(text: str, model: str, max_retries: int) -> list[float]:
    """Call Ollama. Raises on failure after retries (caller decides
    whether to fall back to hash)."""
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
                return result["embeddings"][0]
        except (urllib.error.URLError, TimeoutError, ConnectionResetError) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
        except KeyError as e:
            last_error = e
            break
    raise RuntimeError(f"ollama unreachable: {last_error}")


def _openai_embed(text: str, model: str, max_retries: int) -> list[float]:
    """Call OpenAI's embeddings endpoint via urllib (no SDK dependency).

    Reads OPENAI_API_KEY from the environment. Raises if it's missing
    or if the call fails after retries.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set — required for embedding_provider=openai. "
            "Either export the key or switch provider via LOOM_EMBEDDING_PROVIDER."
        )

    payload = json.dumps({"model": model, "input": text}).encode()
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                _OPENAI_URL,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                return result["data"][0]["embedding"]
        except (urllib.error.URLError, TimeoutError, ConnectionResetError) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
        except (KeyError, IndexError) as e:
            last_error = e
            break
    raise RuntimeError(f"openai embeddings unreachable: {last_error}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_embedding(
    text: str,
    model: str | None = None,
    max_retries: int = 3,
    use_cache: bool = True,
    *,
    provider: str | None = None,
    target_dir: Path | str | None = None,
) -> list[float]:
    """Get an embedding vector for `text`.

    Args:
        text: Text to embed.
        model: Model name. None → provider's default model.
        max_retries: Retries with exponential backoff on transient failures.
        use_cache: If True, consult and populate the process-local LRU.
        provider: Explicit provider ("ollama", "openai", "hash"). When
                  None, resolves via env / config / default-ollama.
        target_dir: Optional path used to load `.loom-config.json` for
                    provider resolution. Most callers can leave this None.

    Returns a list of floats sized to the provider/model's dimension.
    Always returns a value — for the default `ollama` provider, an outage
    falls back to the deterministic hash embedding (with a printed
    warning). Other providers raise on failure rather than silently
    degrading search quality.
    """
    chosen_provider = resolve_provider(explicit=provider, target_dir=target_dir)
    chosen_model = model or default_model_for(chosen_provider)

    cache_key = _cache_key(chosen_provider, chosen_model, text) if use_cache else None
    if use_cache and cache_key in _embedding_cache:
        return _embedding_cache[cache_key]

    embedding: list[float]
    if chosen_provider == "hash":
        dim = expected_dim("hash", chosen_model)
        embedding = _hash_embedding(text, dim=dim)
    elif chosen_provider == "openai":
        embedding = _openai_embed(text, chosen_model, max_retries)
    elif chosen_provider == "ollama":
        try:
            embedding = _ollama_embed(text, chosen_model, max_retries)
        except RuntimeError as e:
            # Back-compat: ollama outage → hash fallback with a warning.
            # Other providers don't fall back silently because that would
            # hide misconfiguration (an OpenAI 401 should surface, not
            # quietly produce useless vectors).
            print(f"⚠️  {e}, using hash fallback embeddings")
            embedding = _hash_embedding(text, dim=_OLLAMA_DEFAULT_DIM)
    else:
        raise ValueError(f"unknown embedding provider: {chosen_provider!r}")

    if use_cache and cache_key is not None:
        _cache_put(cache_key, embedding)
    return embedding
