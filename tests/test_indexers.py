"""Tests for src/loom/indexers.py — the SemanticIndexer scaffolding (M10.1).

Covers the registry, the NoOp default, and a tiny FakeIndexer that
exercises the abstract surface so the data path is validated end-to-
end without needing a real Kythe install.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loom import indexers
from loom.indexers import (
    NoOpIndexer,
    SemanticIndexer,
    SymbolHit,
    for_language,
    register,
    registered,
    unregister,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Restore the registry to empty after each test so tests can't
    leak indexer registrations into one another."""
    snapshot = list(indexers._INDEXERS)
    indexers._INDEXERS.clear()
    yield
    indexers._INDEXERS.clear()
    indexers._INDEXERS.extend(snapshot)


class TestNoOpIndexer:
    def test_supports_returns_false_for_every_language(self):
        idx = NoOpIndexer()
        for lang in ("python", "c++", "rust", "made_up"):
            assert idx.supports(lang) is False

    def test_context_for_returns_empty_string(self, tmp_path):
        idx = NoOpIndexer()
        f = tmp_path / "x.py"
        f.write_text("pass\n")
        assert idx.context_for(f) == ""

    def test_resolve_symbol_returns_none(self):
        idx = NoOpIndexer()
        assert idx.resolve_symbol("app::Service::method") is None

    def test_signature_of_returns_none(self):
        idx = NoOpIndexer()
        assert idx.signature_of("kythe://corpus?path=foo#sym") is None


class TestRegistry:
    def test_for_language_falls_back_to_noop_when_empty(self):
        idx = for_language("python")
        assert isinstance(idx, NoOpIndexer)

    def test_register_and_resolve(self):
        class FakePy(SemanticIndexer):
            name = "fake-py"
            languages = ("python",)

        py = FakePy()
        register(py)
        assert for_language("python") is py
        # Other languages still fall back to noop.
        assert isinstance(for_language("c++"), NoOpIndexer)

    def test_first_registered_wins_on_conflict(self):
        class FakeA(SemanticIndexer):
            name = "a"
            languages = ("python",)

        class FakeB(SemanticIndexer):
            name = "b"
            languages = ("python",)

        a = FakeA()
        b = FakeB()
        register(a)
        register(b)
        # Earlier registration shadows later one — lets project-level
        # indexers override defaults by registering first.
        assert for_language("python") is a

    def test_register_is_idempotent_on_instance(self):
        class FakePy(SemanticIndexer):
            name = "fake-py"
            languages = ("python",)

        py = FakePy()
        register(py)
        register(py)
        assert registered() == [py]

    def test_unregister_removes_indexer(self):
        class FakePy(SemanticIndexer):
            name = "fake-py"
            languages = ("python",)

        py = FakePy()
        register(py)
        unregister(py)
        assert isinstance(for_language("python"), NoOpIndexer)


class TestSymbolHit:
    def test_minimal_hit(self, tmp_path):
        # Just ticket + file is valid; the optional fields can be omitted.
        hit = SymbolHit(
            ticket="kythe://loom?path=app/x.py#cls",
            file=tmp_path / "x.py",
        )
        assert hit.byte_range is None
        assert hit.signature_hash is None

    def test_full_hit(self, tmp_path):
        hit = SymbolHit(
            ticket="kythe://loom?path=app/x.py#cls",
            file=tmp_path / "x.py",
            byte_range=(100, 250),
            signature_hash="sha:abc",
        )
        assert hit.byte_range == (100, 250)
        assert hit.signature_hash == "sha:abc"


class TestFakeIndexerEndToEnd:
    """End-to-end smoke: a fake indexer plugged into the registry
    answers context_for / resolve_symbol / signature_of, and the
    plumbing returns its values unchanged."""

    def test_full_path(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("# hello\n")

        class FakePy(SemanticIndexer):
            name = "fake-py"
            languages = ("python",)
            def context_for(self, file):
                return f"// fake context for {file.name}"
            def resolve_symbol(self, ref):
                return SymbolHit(
                    ticket=f"fake://{ref}",
                    file=f,
                    byte_range=(0, 7),
                    signature_hash="sig:test",
                )
            def signature_of(self, ticket):
                return "sig:test"

        register(FakePy())
        idx = for_language("python")

        assert idx.context_for(f) == f"// fake context for {f.name}"
        hit = idx.resolve_symbol("app::greet")
        assert hit is not None
        assert hit.ticket == "fake://app::greet"
        assert hit.byte_range == (0, 7)
        assert idx.signature_of(hit.ticket) == "sig:test"
