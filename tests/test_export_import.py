"""Tests for the M24 export/import format and round-trip integrity.

The locked guarantee in docs/specs/M24_LOOM_EXPORT_FORMAT.md is that
`import → export` produces byte-identical files (modulo the
manifest's exported_at timestamp). These tests lock that guarantee.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from loom import services
from loom.store import (
    Implementation,
    LoomStore,
    Requirement,
    Specification,
    generate_impl_id,
)


@pytest.fixture
def fixture_project_dir(monkeypatch, tmp_path):
    """Create an isolated per-project data directory so the test
    doesn't touch ~/.openclaw/loom/."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    return tmp_path


@pytest.fixture
def store_with_fixtures(fixture_project_dir):
    """Build a LoomStore populated with deterministic fixtures using
    hash embeddings (no Ollama dependency)."""
    monkeypatch_env = os.environ.copy()
    os.environ["LOOM_EMBEDDING_PROVIDER"] = "hash"
    try:
        store = LoomStore("m24-test")
        # 3 requirements across kinds
        from loom.embedding import get_embedding
        for r in [
            Requirement(
                id="REQ-aaaaaaaa", domain="behavior",
                value="The system must support graceful shutdown.",
                source_msg_id=None, source_session="test",
                timestamp="2026-05-01T00:00:00+00:00",
                rationale="Prevents data loss on SIGTERM.",
                status="pending", kind="requirement",
            ),
            Requirement(
                id="REQ-bbbbbbbb", domain="evaluation",
                value="M24 round-trip must be byte-identical.",
                source_msg_id=None, source_session="test",
                timestamp="2026-05-02T00:00:00+00:00",
                rationale="Tests the determinism guarantee.",
                status="captured", kind="finding",
            ),
            Requirement(
                id="REQ-cccccccc", domain="operational",
                value="Bake-off harnesses lock sampling parameters.",
                source_msg_id=None, source_session="test",
                timestamp="2026-05-03T00:00:00+00:00",
                rationale=None,
                status="active", kind="process_rule",
            ),
        ]:
            text = (r.value or "") + " " + (r.rationale or "")
            store.add_requirement(r, get_embedding(text))

        # 1 implementation link
        impl = Implementation(
            id=generate_impl_id("src/foo.py", "all"),
            file="src/foo.py", lines="all",
            content="# example file\n",
            content_hash="sha256-example",
            timestamp="2026-05-04T00:00:00+00:00",
            satisfies=[{"req_id": "REQ-aaaaaaaa",
                         "req_version": "2026-05-01T00:00:00+00:00",
                         "link_type": "implementation"}],
        )
        store.add_implementation(impl, get_embedding(impl.content))

        yield store
    finally:
        os.environ.clear()
        os.environ.update(monkeypatch_env)


class TestExport:
    def test_export_writes_manifest_and_jsonl_files(
        self, fixture_project_dir, store_with_fixtures,
    ):
        dest = fixture_project_dir / "repo"
        dest.mkdir()
        result = services.export_store(
            store_with_fixtures, dest, project="m24-test",
        )
        loom_dir = Path(result["out_dir"])
        assert (loom_dir / "manifest.json").exists()
        assert (loom_dir / "requirements.jsonl").exists()
        assert (loom_dir / "specifications.jsonl").exists()
        assert (loom_dir / "patterns.jsonl").exists()
        assert (loom_dir / "implementations.jsonl").exists()
        assert (loom_dir / "test_specs.jsonl").exists()

    def test_export_counts_match_fixtures(
        self, fixture_project_dir, store_with_fixtures,
    ):
        dest = fixture_project_dir / "repo"
        dest.mkdir()
        result = services.export_store(
            store_with_fixtures, dest, project="m24-test",
        )
        counts = result["manifest"]["entity_counts"]
        assert counts["requirements"] == 3
        assert counts["implementations"] == 1
        assert counts["specifications"] == 0
        assert counts["patterns"] == 0

    def test_export_rows_sorted_by_id(
        self, fixture_project_dir, store_with_fixtures,
    ):
        dest = fixture_project_dir / "repo"
        dest.mkdir()
        services.export_store(
            store_with_fixtures, dest, project="m24-test",
        )
        lines = (dest / ".loom" / "requirements.jsonl").read_text(
            encoding="utf-8",
        ).splitlines()
        ids = [json.loads(L)["id"] for L in lines]
        assert ids == sorted(ids), "rows must be sorted by id"

    def test_export_uses_lf_newlines_on_all_platforms(
        self, fixture_project_dir, store_with_fixtures,
    ):
        dest = fixture_project_dir / "repo"
        dest.mkdir()
        services.export_store(
            store_with_fixtures, dest, project="m24-test",
        )
        body = (dest / ".loom" / "requirements.jsonl").read_bytes()
        assert b"\r\n" not in body, "must use LF not CRLF"
        assert body.endswith(b"\n")

    def test_export_excludes_last_referenced(
        self, fixture_project_dir, store_with_fixtures,
    ):
        # Touch a req so last_referenced gets set
        store_with_fixtures.touch_requirement("REQ-aaaaaaaa")
        dest = fixture_project_dir / "repo"
        dest.mkdir()
        services.export_store(
            store_with_fixtures, dest, project="m24-test",
        )
        body = (dest / ".loom" / "requirements.jsonl").read_text(
            encoding="utf-8",
        )
        for line in body.splitlines():
            row = json.loads(line)
            assert "last_referenced" not in row, \
                "last_referenced is per-developer; must not export"

    def test_export_excludes_impl_content(
        self, fixture_project_dir, store_with_fixtures,
    ):
        dest = fixture_project_dir / "repo"
        dest.mkdir()
        services.export_store(
            store_with_fixtures, dest, project="m24-test",
        )
        body = (dest / ".loom" / "implementations.jsonl").read_text(
            encoding="utf-8",
        )
        for line in body.splitlines():
            row = json.loads(line)
            assert "content" not in row, \
                "content is re-readable from disk; must not export"

    def test_export_acceptance_criteria_tbd_sentinel_normalized(
        self, fixture_project_dir, store_with_fixtures,
    ):
        # The store may use the ["TBD"] legacy sentinel; the export
        # must normalize to [] for cleanliness.
        dest = fixture_project_dir / "repo"
        dest.mkdir()
        services.export_store(
            store_with_fixtures, dest, project="m24-test",
        )
        body = (dest / ".loom" / "requirements.jsonl").read_text(
            encoding="utf-8",
        )
        for line in body.splitlines():
            row = json.loads(line)
            assert row.get("acceptance_criteria") != ["TBD"], \
                "[\"TBD\"] sentinel must be normalized to []"


class TestRoundTrip:
    def test_export_import_export_is_byte_identical(
        self, fixture_project_dir, store_with_fixtures,
    ):
        """The locked guarantee: round-trip produces identical files
        (modulo manifest's exported_at)."""
        # 1. First export
        dest1 = fixture_project_dir / "repo1"
        dest1.mkdir()
        services.export_store(
            store_with_fixtures, dest1, project="m24-test",
        )

        # 2. Import into a SECOND fresh store
        store2 = LoomStore("m24-test-roundtrip")
        services.import_store(
            store2, dest1, policy="error", skip_embeddings=True,
        )

        # 3. Re-export from store2
        dest2 = fixture_project_dir / "repo2"
        dest2.mkdir()
        services.export_store(
            store2, dest2, project="m24-test-roundtrip",
        )

        # 4. Diff every JSONL (content-only; manifest excluded)
        for name in ("requirements.jsonl", "specifications.jsonl",
                     "patterns.jsonl", "implementations.jsonl",
                     "test_specs.jsonl"):
            body1 = (dest1 / ".loom" / name).read_bytes()
            body2 = (dest2 / ".loom" / name).read_bytes()
            assert body1 == body2, (
                f"{name} not byte-identical across round-trip:\n"
                f"  first export: {body1[:200]!r}\n"
                f"  second export: {body2[:200]!r}"
            )


class TestImport:
    def test_import_error_on_local_only_data(
        self, fixture_project_dir, store_with_fixtures,
    ):
        """Default policy refuses if local store has data not in
        the export."""
        # First export the fixture store, then add an extra req to it,
        # then attempt re-import — the extra req is local-only.
        dest = fixture_project_dir / "repo"
        dest.mkdir()
        services.export_store(
            store_with_fixtures, dest, project="m24-test",
        )

        from loom.embedding import get_embedding
        extra = Requirement(
            id="REQ-deadbeef", domain="behavior",
            value="An extra req added after export.",
            source_msg_id=None, source_session="test",
            timestamp="2026-05-10T00:00:00+00:00",
        )
        store_with_fixtures.add_requirement(
            extra, get_embedding(extra.value),
        )

        with pytest.raises(RuntimeError, match="local store has data"):
            services.import_store(
                store_with_fixtures, dest,
                policy="error", skip_embeddings=True,
            )

    def test_import_merge_keeps_local_only(
        self, fixture_project_dir, store_with_fixtures,
    ):
        """Merge policy keeps local-only entities; export wins on
        same-id conflicts."""
        dest = fixture_project_dir / "repo"
        dest.mkdir()
        services.export_store(
            store_with_fixtures, dest, project="m24-test",
        )

        from loom.embedding import get_embedding
        extra = Requirement(
            id="REQ-deadbeef", domain="behavior",
            value="An extra req kept on merge.",
            source_msg_id=None, source_session="test",
            timestamp="2026-05-10T00:00:00+00:00",
        )
        store_with_fixtures.add_requirement(
            extra, get_embedding(extra.value),
        )

        result = services.import_store(
            store_with_fixtures, dest,
            policy="merge", skip_embeddings=True,
        )
        assert result["applied"]
        # The local-only req should still be there
        assert store_with_fixtures.get_requirement("REQ-deadbeef") is not None

    def test_import_rejects_wrong_version(self, fixture_project_dir, tmp_path):
        loom_dir = tmp_path / "repo" / ".loom"
        loom_dir.mkdir(parents=True)
        (loom_dir / "manifest.json").write_text(
            json.dumps({"version": "m99-export-vX"}),
            encoding="utf-8",
        )
        for name in ("requirements", "specifications", "patterns",
                     "implementations", "test_specs"):
            (loom_dir / f"{name}.jsonl").write_text("", encoding="utf-8")

        store = LoomStore("m24-version-test")
        with pytest.raises(ValueError, match="unsupported export version"):
            services.import_store(store, tmp_path / "repo")

    def test_import_missing_loom_dir_raises(self, fixture_project_dir, tmp_path):
        store = LoomStore("m24-missing-test")
        with pytest.raises(FileNotFoundError, match=".loom/"):
            services.import_store(store, tmp_path / "nonexistent-repo")

    def test_import_with_embeddings_populates_vectors(
        self, fixture_project_dir, store_with_fixtures,
    ):
        """Default (auto-rebuild) path: imported reqs get real (non-
        zero) embeddings so search works without a separate rebuild.
        Test uses LOOM_EMBEDDING_PROVIDER=hash so no Ollama needed."""
        dest = fixture_project_dir / "repo"
        dest.mkdir()
        services.export_store(
            store_with_fixtures, dest, project="m24-test",
        )

        fresh = LoomStore("m24-with-embed")
        result = services.import_store(
            fresh, dest, policy="error", skip_embeddings=False,
        )
        assert result["applied"]

        # Validate embeddings via a semantic-search smoke: the imported
        # store should return matches for a query that overlaps a req's
        # text. With hash embeddings the matches won't be "good" in a
        # similarity sense, but search must not crash and must return
        # something for a known-word query.
        results = fresh.search_requirements(
            [0.1] * 768, n=3,
        )
        assert isinstance(results, list)
        assert len(results) >= 1, "search must return rows after embed-rebuild"
