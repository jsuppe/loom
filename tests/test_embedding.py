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


# ---------------------------------------------------------------------------
# Provider dispatch (M3.1)
# ---------------------------------------------------------------------------

class TestResolveProvider:
    def test_explicit_arg_wins(self, monkeypatch):
        monkeypatch.setenv("LOOM_EMBEDDING_PROVIDER", "openai")
        assert emb.resolve_provider(explicit="hash") == "hash"

    def test_env_var_overrides_default(self, monkeypatch):
        monkeypatch.delenv("LOOM_EMBEDDING_PROVIDER", raising=False)
        assert emb.resolve_provider() == "ollama"
        monkeypatch.setenv("LOOM_EMBEDDING_PROVIDER", "OPENAI")
        # case-insensitive
        assert emb.resolve_provider() == "openai"

    def test_config_file_used_when_env_absent(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LOOM_EMBEDDING_PROVIDER", raising=False)
        (tmp_path / ".loom-config.json").write_text(
            '{"embedding_provider": "hash"}', encoding="utf-8")
        assert emb.resolve_provider(target_dir=tmp_path) == "hash"

    def test_default_is_ollama(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LOOM_EMBEDDING_PROVIDER", raising=False)
        # No config file in tmp_path.
        assert emb.resolve_provider(target_dir=tmp_path) == "ollama"


class TestHashProvider:
    def test_hash_provider_is_deterministic_and_dim_768_default(self):
        v1 = emb.get_embedding("foo", provider="hash", use_cache=False)
        v2 = emb.get_embedding("foo", provider="hash", use_cache=False)
        assert v1 == v2
        assert len(v1) == 768

    def test_hash_provider_dim_override_via_model_spec(self):
        v = emb.get_embedding("foo", provider="hash", model="hash:1536",
                              use_cache=False)
        assert len(v) == 1536

    def test_hash_provider_does_not_print_warning(self, capsys):
        # Unlike the ollama-fallback path, explicit hash provider is silent.
        emb.get_embedding("foo", provider="hash", use_cache=False)
        out = capsys.readouterr().out
        assert "fallback" not in out


class TestOpenAIProvider:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            emb.get_embedding("foo", provider="openai",
                              max_retries=1, use_cache=False)

    def test_openai_call_succeeds_when_mocked(self, monkeypatch):
        """Mock urlopen so we don't need a real OpenAI account."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")

        captured: dict = {}

        class FakeResp:
            def read(self):
                return b'{"data": [{"embedding": [0.1, 0.2, 0.3]}]}'
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(req, *a, **kw):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            return FakeResp()

        monkeypatch.setattr(emb.urllib.request, "urlopen", fake_urlopen)
        v = emb.get_embedding("hello", provider="openai", max_retries=1,
                              use_cache=False)
        assert v == [0.1, 0.2, 0.3]
        assert captured["url"] == emb._OPENAI_URL
        assert captured["headers"]["Authorization"] == "Bearer sk-test-fake"


class TestProviderCacheIsolation:
    def test_same_text_different_providers_dont_collide(self, monkeypatch):
        # Force ollama to fall back to hash so we get a deterministic vector
        # without needing Ollama; explicitly request hash for the second call.
        def boom(*a, **kw):
            raise ConnectionResetError("no ollama")
        monkeypatch.setattr(emb.urllib.request, "urlopen", boom)

        # Pre-populate cache deliberately for ollama+nomic-embed-text.
        ollama_key = emb._cache_key("ollama", "nomic-embed-text", "shared")
        emb._embedding_cache[ollama_key] = [9.0] * 768

        # Asking for the same text via the hash provider must NOT return
        # the ollama-cached vector — different cache key.
        hash_vec = emb.get_embedding("shared", provider="hash")
        assert hash_vec != [9.0] * 768
        # And the ollama entry is still there (hash put under its own key).
        assert emb._embedding_cache[ollama_key] == [9.0] * 768
