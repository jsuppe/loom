"""
Semantic-indexer registry for ``loom_exec`` and ``loom link --symbol``.

Loom's bundled context (file body + linked-spec text) is enough for
single-file Python work, but the cross-language map (M8.4) showed that
languages where meaning lives in headers, templates, and call-graph
context (C++, Java, Go) need richer signal. This module is the seam
where a real semantic indexer (Kythe, Pyright, rust-analyzer, …) plugs
in to provide that signal.

Scope of M10.1 (this commit): the abstract interface, the registry,
and a no-op default. **No real indexer is shipped here** — adding one
is M10.3+ tracked in ROADMAP.md. The seam is in place so a Kythe or
Pyright implementation can land later without touching call sites.

The indexer is *optional*. The default ``NoOpIndexer`` returns empty
context and refuses to resolve symbols, so Loom keeps working
identically for users without an indexer plugged in.

Architecture mirrors ``runners.py`` — data-only module, no Loom-store
or CLI coupling.

See ROADMAP.md::Milestone 10 for the full design and motivation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class SymbolHit:
    """Resolution of a symbol reference (e.g. ``app::OrderService::commit``)
    to a concrete code location plus the indexer's stable identity for it.

    Fields:
        ticket: indexer-specific stable identity (Kythe ticket URI, LSP
                symbol URI, etc.). Used as the persistent reference on
                Implementation rows so links survive line shifts and
                file moves.
        file: absolute or repo-relative path to the file the symbol
              lives in.
        byte_range: (start, end) byte offsets within the file. May be
                    None for indexers that only resolve to file-level
                    granularity.
        signature_hash: stable hash of the symbol's structural
                        signature at resolve time. Used by the drift
                        check to detect API changes that a content-
                        hash diff would miss (function renamed but
                        bytes match, member added/removed). May be
                        None for indexers that don't compute it.
    """
    ticket: str
    file: Path
    byte_range: Optional[tuple[int, int]] = None
    signature_hash: Optional[str] = None


class SemanticIndexer:
    """Pluggable backend for symbol-level context + linking.

    Subclasses implement one or more of:
      * ``context_for(file)`` — symbol-level context for the executor
        prompt (definitions of referenced symbols, override chains,
        call sites). Plugged into ``loom_exec``'s prompt assembly.
      * ``resolve_symbol(ref)`` — turn a string like
        ``app::OrderService::commit`` into a ``SymbolHit``. Plugged
        into ``loom link --symbol``.
      * ``signature_of(ticket)`` — recompute the structural signature
        for a previously-resolved symbol. Plugged into ``services.check``
        for structural drift detection.

    All three default to no-op behavior so an indexer that only
    supports one phase doesn't have to fake the others.
    """

    name: str = "abstract"
    languages: tuple[str, ...] = ()

    def supports(self, language: str) -> bool:
        return language in self.languages

    def context_for(self, file: Path) -> str:
        """Return symbol-level context for ``file``, or ``""`` when
        nothing useful to add. Default: no signal."""
        return ""

    def resolve_symbol(self, ref: str) -> Optional[SymbolHit]:
        """Resolve a symbol reference to a concrete location + ticket.
        Returns None when the indexer can't or won't resolve."""
        return None

    def signature_of(self, ticket: str) -> Optional[str]:
        """Stable hash of the symbol's structural signature. Returns
        None when the indexer doesn't track signatures or the ticket
        is unknown."""
        return None


class NoOpIndexer(SemanticIndexer):
    """Default. Reports no language support, returns empty context,
    refuses every resolve. Loom users without a real indexer plugged
    in get no behavior change relative to pre-M10.
    """
    name = "noop"
    languages = ()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
#
# A simple list of registered indexers. ``for_language`` walks the list
# and returns the first one that supports the given language. The order
# matters: earlier registrations win on conflict, so a project-specific
# indexer can shadow a default by registering first.

_INDEXERS: list[SemanticIndexer] = []


def register(indexer: SemanticIndexer) -> None:
    """Register a SemanticIndexer for use by ``loom_exec`` and
    ``loom link --symbol``. Idempotent on instance — re-registering the
    same instance is a no-op.
    """
    if indexer not in _INDEXERS:
        _INDEXERS.append(indexer)


def unregister(indexer: SemanticIndexer) -> None:
    """Remove a previously-registered indexer. Mostly useful for tests
    that swap an indexer in and want to clean up afterwards."""
    if indexer in _INDEXERS:
        _INDEXERS.remove(indexer)


def for_language(language: str) -> SemanticIndexer:
    """Return the first registered indexer that supports ``language``.
    Falls back to ``NoOpIndexer`` so callers never have to handle a
    None — they always get a working object that just returns empty
    context / no resolution.
    """
    for indexer in _INDEXERS:
        if indexer.supports(language):
            return indexer
    return _NOOP


def registered() -> list[SemanticIndexer]:
    """Snapshot of the registered indexers, in registration order.
    For ``loom indexer doctor`` and tests."""
    return list(_INDEXERS)


_NOOP = NoOpIndexer()
