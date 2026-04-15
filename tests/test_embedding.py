"""
Tests for src/embedding.py — the shared embedding helper.

These tests don't require Ollama; we exercise the hash-fallback path and
the cache by monkeypatching the network call.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import embedding as emb  # noqa: E402


@pytest.fixture(autouse=True)
def clear_cache():
    """Isolate tests from each other's cache state."""
    emb._embedding_cache.clear()
    yield
    emb._embedding_cache.clear()


def _force_fallback(monkeypatch):
    """Make `urlopen` raise so get_embedding takes the hash path fast."""
    def boom(*a, **kw):
        raise ConnectionResetError("no ollama in tests")
    monkeypatch.setattr(emb.urllib.request, "urlopen", boom)


def test_hash_fallback_is_deterministic_and_correct_dim(monkeypatch, capsys):
    _force_fallback(monkeypatch)
    v1 = emb.get_embedding("hello world", max_retries=1)
    v2 = emb.get_embedding("hello world", max_retries=1, use_cache=False)
    assert len(v1) == 768
    assert v1 == v2
    # Fallback warning goes to stdout; don't care about exact wording.
    assert "fallback" in capsys.readouterr().out


def test_different_text_produces_different_embedding(monkeypatch):
    _force_fallback(monkeypatch)
    a = emb.get_embedding("apple", max_retries=1, use_cache=False)
    b = emb.get_embedding("banana", max_retries=1, use_cache=False)
    assert a != b


def test_cache_returns_same_object(monkeypatch):
    _force_fallback(monkeypatch)
    first = emb.get_embedding("cached text", max_retries=1)
    # Monkeypatch urlopen to something that would return a different vector
    # if actually called — if the cache works we never call it.
    def fail(*a, **kw):
        raise AssertionError("cache miss: urlopen should not be called")
    monkeypatch.setattr(emb.urllib.request, "urlopen", fail)
    second = emb.get_embedding("cached text", max_retries=1)
    assert first == second


def test_cache_eviction_bounded():
    # Directly exercise _cache_put to avoid the network/fallback path.
    original_max = emb._CACHE_MAX_SIZE
    try:
        # Temporarily shrink so we don't have to insert 500 items.
        emb._CACHE_MAX_SIZE = 3
        for i in range(5):
            emb._cache_put(f"k{i}", [float(i)])
        assert len(emb._embedding_cache) == 3
        # Oldest two evicted; newest three remain.
        assert "k0" not in emb._embedding_cache
        assert "k1" not in emb._embedding_cache
        assert "k4" in emb._embedding_cache
    finally:
        emb._CACHE_MAX_SIZE = original_max
