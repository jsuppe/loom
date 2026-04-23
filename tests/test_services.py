"""
Tests for src/services.py — shared logic layer between CLI and MCP.

Verifies service functions return the expected data shapes against a
temp LoomStore. Service functions embed text via src/embedding.py; we
force its hash-fallback path so tests don't need Ollama.
"""

import sys
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import embedding  # noqa: E402
import services  # noqa: E402
from store import LoomStore, Requirement, Implementation  # noqa: E402


@pytest.fixture
def store():
    tmp = Path(tempfile.mkdtemp())
    s = LoomStore(project="test-services", data_dir=tmp)
    yield s
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def fake_embedding():
    return [0.1] * 768


@pytest.fixture(autouse=True)
def force_fallback_embedding(monkeypatch):
    """Route get_embedding through the hash fallback so tests don't need Ollama."""
    embedding._embedding_cache.clear()

    def boom(*a, **kw):
        raise ConnectionResetError("no ollama in tests")

    monkeypatch.setattr(embedding.urllib.request, "urlopen", boom)


def _mk_req(store, req_id, domain, value, fake_embedding):
    req = Requirement(
        id=req_id,
        domain=domain,
        value=value,
        source_msg_id="m1",
        source_session="s1",
        timestamp="2026-01-01T00:00:00Z",
    )
    store.add_requirement(req, fake_embedding)
    return req


class TestStatus:
    def test_empty_store(self, store):
        data = services.status(store)
        assert data["project"] == "test-services"
        assert data["requirements"] == 0
        assert data["active"] == 0
        assert data["superseded"] == 0
        assert data["drift_count"] == 0
        assert data["drift"] == []

    def test_counts_reflect_store(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "A", fake_embedding)
        _mk_req(store, "REQ-b", "behavior", "B", fake_embedding)
        data = services.status(store)
        assert data["requirements"] == 2
        assert data["active"] == 2
        assert data["superseded"] == 0

    def test_drift_reported_for_superseded_req_with_impl(self, store, fake_embedding):
        _mk_req(store, "REQ-old", "behavior", "old", fake_embedding)
        impl = Implementation(
            id="IMPL-1", file="src/x.py", lines="1-10",
            content="pass", content_hash="h",
            satisfies=[{"req_id": "REQ-old"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        store.supersede_requirement("REQ-old")

        data = services.status(store)
        assert data["superseded"] == 1
        assert data["drift_count"] == 1
        assert data["drift"][0]["req_id"] == "REQ-old"
        assert data["drift"][0]["file"] == "src/x.py"


class TestQuery:
    def test_empty_store_returns_empty_list(self, store):
        assert services.query(store, "anything") == []

    def test_returns_expected_shape(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "users must log in", fake_embedding)
        results = services.query(store, "login", limit=5)
        assert len(results) == 1
        r = results[0]
        assert set(r.keys()) >= {
            "id", "domain", "value", "status",
            "superseded", "source", "timestamp", "distance",
        }
        assert r["id"] == "REQ-x"
        assert r["superseded"] is False


class TestListRequirements:
    def test_empty(self, store):
        assert services.list_requirements(store) == []

    def test_excludes_superseded_by_default(self, store, fake_embedding):
        _mk_req(store, "REQ-live", "behavior", "live", fake_embedding)
        _mk_req(store, "REQ-dead", "behavior", "dead", fake_embedding)
        store.supersede_requirement("REQ-dead")

        reqs = services.list_requirements(store)
        ids = [r["id"] for r in reqs]
        assert "REQ-live" in ids
        assert "REQ-dead" not in ids

    def test_include_superseded(self, store, fake_embedding):
        _mk_req(store, "REQ-live", "behavior", "live", fake_embedding)
        _mk_req(store, "REQ-dead", "behavior", "dead", fake_embedding)
        store.supersede_requirement("REQ-dead")

        reqs = services.list_requirements(store, include_superseded=True)
        ids = [r["id"] for r in reqs]
        assert "REQ-live" in ids
        assert "REQ-dead" in ids

    def test_has_test_false_when_no_spec(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        reqs = services.list_requirements(store)
        assert reqs[0]["has_test"] is False


class TestTrace:
    def test_unknown_req_raises_lookup(self, store):
        with pytest.raises(LookupError):
            services.trace(store, "REQ-missing")

    def test_missing_file_raises_lookup(self, store):
        with pytest.raises(LookupError):
            services.trace(store, "/nonexistent/path.py")

    def test_req_with_no_impls(self, store, fake_embedding):
        _mk_req(store, "REQ-lonely", "behavior", "alone", fake_embedding)
        data = services.trace(store, "REQ-lonely")
        assert data["type"] == "requirement"
        assert data["id"] == "REQ-lonely"
        assert data["implementations"] == []
        assert data["test_spec"] is None
        assert data["superseded_at"] is None

    def test_req_with_impls(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        impl = Implementation(
            id="IMPL-1", file="src/x.py", lines="1-10",
            content="x = 1", content_hash="h",
            satisfies=[{"req_id": "REQ-x"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        data = services.trace(store, "REQ-x")
        assert len(data["implementations"]) == 1
        assert data["implementations"][0]["file"] == "src/x.py"


class TestChain:
    def test_unknown_req_raises_lookup(self, store):
        with pytest.raises(LookupError):
            services.chain(store, "REQ-missing")

    def test_bare_requirement_has_empty_sublists(self, store, fake_embedding):
        _mk_req(store, "REQ-bare", "behavior", "bare", fake_embedding)
        data = services.chain(store, "REQ-bare")
        assert data["id"] == "REQ-bare"
        assert data["patterns"] == []
        assert data["specifications"] == []
        assert data["direct_implementations"] == []
        assert data["test_spec"] is None

    def test_direct_impl_separated_from_spec_impl(self, store, fake_embedding):
        _mk_req(store, "REQ-1", "behavior", "one", fake_embedding)
        direct = Implementation(
            id="IMPL-direct", file="src/a.py", lines="1-5",
            content="a", content_hash="ha",
            satisfies=[{"req_id": "REQ-1"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(direct, fake_embedding)
        data = services.chain(store, "REQ-1")
        assert len(data["direct_implementations"]) == 1
        assert data["direct_implementations"][0]["file"] == "src/a.py"
        assert data["specifications"] == []


class TestCoverage:
    def test_empty_store_full_coverage(self, store):
        data = services.coverage(store)
        # 0/0 reqs is treated as 100% by convention
        assert data["layer_1_req_to_spec"]["coverage_pct"] == 100
        assert data["layer_1_req_to_spec"]["with_specs"] == 0
        assert data["layer_1_req_to_spec"]["without_specs"] == []
        # 0/0 specs is 0% (no specs to be covered)
        assert data["layer_2_spec_to_impl"]["coverage_pct"] == 0
        assert data["layer_3_spec_to_test"]["coverage_pct"] == 0

    def test_req_without_spec_lands_in_layer_1_gap(self, store, fake_embedding):
        _mk_req(store, "REQ-no-spec", "behavior", "uncovered", fake_embedding)
        data = services.coverage(store)
        l1 = data["layer_1_req_to_spec"]
        assert l1["total_requirements"] == 1
        assert l1["with_specs"] == 0
        assert l1["coverage_pct"] == 0
        assert len(l1["without_specs"]) == 1
        assert l1["without_specs"][0]["id"] == "REQ-no-spec"


class TestConflicts:
    def test_empty_store_no_conflicts(self, store):
        assert services.conflicts(store, "behavior | brand new req") == []

    def test_parses_text_without_pipe(self, store):
        # No `|` → defaults to behavior domain. Just check it doesn't crash.
        result = services.conflicts(store, "no pipe here")
        assert isinstance(result, list)

    def test_verify_confirms_via_stub(self, store, fake_embedding):
        """verify=True + stub verify_fn that flags only REQ-a should return just it."""
        _mk_req(store, "REQ-a", "behavior", "sessions last 30 days", fake_embedding)
        _mk_req(store, "REQ-b", "behavior", "sessions last forever", fake_embedding)

        seen_pairs: list[tuple[str, str]] = []

        def stub(candidate: str, existing: str, model):
            seen_pairs.append((candidate, existing))
            # Stub: only flag the 30-days req as a conflict.
            return ("30 days" in existing, "YES" if "30 days" in existing else "NO")

        result = services.conflicts(
            store, "behavior | sessions last 60 days",
            verify=True, verify_fn=stub,
        )
        ids = [r["existing_id"] for r in result]
        assert "REQ-a" in ids
        assert "REQ-b" not in ids
        # Verifier should have been invoked at least once per candidate in the pool.
        assert len(seen_pairs) >= 1
        # LLM-verified reason surfaces in the result.
        assert all("LLM-verified" in r["reason"] for r in result)

    def test_verify_returns_empty_when_stub_rejects_all(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "something", fake_embedding)
        stub = lambda c, e, m: (False, "NO")  # noqa: E731
        result = services.conflicts(
            store, "behavior | unrelated candidate",
            verify=True, verify_fn=stub,
        )
        assert result == []

    def test_verify_raises_on_verifier_error(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "rule A", fake_embedding)
        # Stub that simulates Ollama connection failure via the <error:...>
        # sentinel that src/conflict_verify.py emits.
        stub = lambda c, e, m: (False, "<error: connection refused>")  # noqa: E731
        import pytest
        with pytest.raises(RuntimeError, match="connection refused"):
            services.conflicts(
                store, "behavior | some candidate",
                verify=True, verify_fn=stub,
            )


class TestInit:
    def test_creates_config_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = services.init(target_dir=td, project="myproj")
            cfg_path = Path(td) / ".loom-config.json"
            assert cfg_path.exists()
            assert result["config_path"] == str(cfg_path)
            assert result["project"] == "myproj"
            assert result["created_config"] is True
            # Config has the project pinned
            import json as _json
            cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
            assert cfg["project"] == "myproj"
            assert cfg["executor_model"] == "qwen3.5:latest"

    def test_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            services.init(target_dir=td, project="p1")
            with pytest.raises(FileExistsError):
                services.init(target_dir=td, project="p2")

    def test_force_overwrites(self):
        with tempfile.TemporaryDirectory() as td:
            services.init(target_dir=td, project="p1")
            result = services.init(target_dir=td, project="p2", force=True)
            assert result["project"] == "p2"
            import json as _json
            cfg = _json.loads(
                (Path(td) / ".loom-config.json").read_text(encoding="utf-8")
            )
            assert cfg["project"] == "p2"

    def test_missing_target_dir_raises(self):
        with pytest.raises(NotADirectoryError):
            services.init(target_dir="/definitely/does/not/exist", project="x")

    def test_creates_tests_dir(self):
        with tempfile.TemporaryDirectory() as td:
            result = services.init(target_dir=td, project="p")
            assert (Path(td) / "tests").is_dir()
            assert result["created_tests_dir"] is True

    def test_existing_tests_dir_not_recreated(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "tests").mkdir()
            result = services.init(target_dir=td, project="p")
            assert result["created_tests_dir"] is False

    def test_health_checks_reported(self):
        # Ollama is mocked-out by the autouse fixture → ollama.ok = False
        # but result structure should still be populated.
        with tempfile.TemporaryDirectory() as td:
            result = services.init(target_dir=td, project="p")
            ch = result["checks"]
            assert ch["ollama"]["ok"] is False
            assert ch["embedding_model"]["name"] == "nomic-embed-text"
            assert ch["executor_model"]["name"] == "qwen3.5:latest"
            assert ch["tests_dir"]["ok"] is True

    def test_pytest_detected_in_requirements_txt(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "requirements.txt").write_text(
                "fastapi>=0.1\npytest>=7\n", encoding="utf-8",
            )
            result = services.init(target_dir=td, project="p")
            assert result["checks"]["pytest"]["ok"] is True
            assert result["checks"]["pytest"]["where"] == "requirements.txt"

    def test_pytest_detected_in_nested_requirements(self):
        with tempfile.TemporaryDirectory() as td:
            backend = Path(td) / "src" / "backend"
            backend.mkdir(parents=True)
            (backend / "requirements.txt").write_text(
                "fastapi\npytest-asyncio\n", encoding="utf-8",
            )
            result = services.init(target_dir=td, project="p")
            assert result["checks"]["pytest"]["ok"] is True
            # Forward-slash path regardless of platform
            assert "backend" in result["checks"]["pytest"]["where"]

    def test_pytest_missing_warns(self):
        with tempfile.TemporaryDirectory() as td:
            result = services.init(target_dir=td, project="p")
            assert result["checks"]["pytest"]["ok"] is False
            assert any("pytest" in w for w in result["warnings"])

    def test_next_steps_present(self):
        with tempfile.TemporaryDirectory() as td:
            result = services.init(target_dir=td, project="p")
            assert isinstance(result["next_steps"], list)
            assert len(result["next_steps"]) >= 3

    def test_with_template_scaffolds_files(self):
        """init --template applies the shipped python-minimal template."""
        with tempfile.TemporaryDirectory() as td:
            result = services.init(
                target_dir=td, project="demo",
                template="python-minimal",
                variables={"app_name": "demoapp", "description": "t",
                           "author": "a", "python_version": "3.10"},
            )
            assert result["template"] == "python-minimal"
            assert result["template_files"] is not None
            assert len(result["template_files"]["written"]) > 0
            # Config is also written
            assert (Path(td) / ".loom-config.json").exists()
            # Package directory gets the substituted name
            assert (Path(td) / "src" / "demoapp" / "__init__.py").exists()

    def test_with_unknown_template_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with pytest.raises(LookupError):
                services.init(
                    target_dir=td, project="p",
                    template="not-a-real-template",
                )

    def test_template_missing_vars_raises(self, monkeypatch):
        """Missing variables without defaults should surface as ValueError."""
        with tempfile.TemporaryDirectory() as user_root, \
             tempfile.TemporaryDirectory() as target:
            user_path = Path(user_root)
            (user_path / "needs-var").mkdir()
            (user_path / "needs-var" / "manifest.yaml").write_text(
                "name: needs-var\nvariables:\n  - {name: mandatory}\n",
                encoding="utf-8",
            )
            (user_path / "needs-var" / "files").mkdir()
            (user_path / "needs-var" / "files" / "x.txt").write_text(
                "{{ mandatory }}", encoding="utf-8",
            )
            import templates as _tpl
            monkeypatch.setattr(_tpl, "user_templates_dir", lambda: user_path)
            with pytest.raises(ValueError):
                services.init(
                    target_dir=target, project="p",
                    template="needs-var", variables={},
                )


class TestDoctor:
    def test_empty_store_returns_shape(self, store):
        data = services.doctor(store)
        assert "healthy" in data
        assert "checks" in data
        assert "issues" in data
        assert "warnings" in data
        # Store check should pass against our temp store
        assert data["checks"]["store"]["ok"] is True
        # Test coverage on empty store: 0/0 → 100%
        assert data["checks"]["test_coverage"]["coverage_pct"] == 100
        # Domains check passes (no reqs, no custom domains)
        assert data["checks"]["domains"]["custom"] == []

    def test_orphan_impl_warned(self, store, fake_embedding):
        # Impl that points at a req that doesn't exist → orphan
        impl = Implementation(
            id="IMPL-orphan", file="src/x.py", lines="1-1",
            content="x", content_hash="h",
            satisfies=[{"req_id": "REQ-ghost"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        data = services.doctor(store)
        assert data["checks"]["orphans"]["count"] == 1
        assert any("REQ-ghost" in w for w in data["warnings"])

    def test_ollama_models_not_truncated(self, store, monkeypatch):
        """FINDINGS-wild F3: the old [:5] slice hid models on multi-model setups."""
        import services as _services
        import json as _json

        class _Resp:
            def __init__(self, body): self._body = body
            def read(self): return self._body
            def __enter__(self): return self
            def __exit__(self, *a): return False

        # 14 fake models — same count we hit on the real dev box
        fake_models = {"models": [{"name": f"model-{i}:latest"} for i in range(14)]}
        payload = _json.dumps(fake_models).encode()

        def fake_urlopen(req, timeout=5):
            return _Resp(payload)

        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda req, timeout=5: _Resp(payload),
        )
        # nomic-embed-text is absent from the fake list → warning fires but
        # the models list should still contain everything.
        data = _services.doctor(store)
        assert len(data["checks"]["ollama"]["models"]) == 14
        assert data["checks"]["ollama"]["models"][13] == "model-13:latest"

    def test_drift_warned_for_superseded_with_impl(self, store, fake_embedding):
        _mk_req(store, "REQ-old", "behavior", "old", fake_embedding)
        impl = Implementation(
            id="IMPL-1", file="src/x.py", lines="1-1",
            content="x", content_hash="h",
            satisfies=[{"req_id": "REQ-old"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        store.supersede_requirement("REQ-old")
        data = services.doctor(store)
        assert data["checks"]["drift"]["count"] == 1


class TestExtract:
    def test_creates_requirement(self, store):
        result = services.extract(
            store, domain="behavior", value="users must log in",
        )
        assert result["req_id"].startswith("REQ-")
        assert result["domain"] == "behavior"
        assert result["value"] == "users must log in"
        assert result["conflicts"] == []
        # Verify it was actually persisted.
        assert store.get_requirement(result["req_id"]) is not None

    def test_lowercases_domain_and_strips_whitespace(self, store):
        result = services.extract(
            store, domain="  BEHAVIOR  ", value="  spaced text  ",
        )
        assert result["domain"] == "behavior"
        assert result["value"] == "spaced text"

    def test_id_is_deterministic(self, store):
        # Same domain+value → same ID.
        r1 = services.extract(store, domain="data", value="cache TTL is 60s")
        # Re-extraction creates the same ID; ChromaDB will overwrite.
        r2 = services.extract(store, domain="data", value="cache TTL is 60s")
        assert r1["req_id"] == r2["req_id"]

    def test_rationale_persisted(self, store):
        result = services.extract(
            store, domain="behavior", value="rate limit", rationale="prevent abuse",
        )
        req = store.get_requirement(result["req_id"])
        assert req.rationale == "prevent abuse"


class TestCheck:
    def test_missing_file_raises(self, store):
        with pytest.raises(LookupError):
            services.check(store, "/nonexistent/path.py")

    def test_unlinked_file_returns_empty(self, store, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        data = services.check(store, str(f))
        assert data["linked"] is False
        assert data["drift_detected"] is False
        assert data["requirements"] == []

    def test_drift_detected_when_req_superseded(self, store, fake_embedding, tmp_path):
        from store import generate_impl_id
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        f = tmp_path / "x.py"
        f.write_text("# impl\n")

        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="# impl\n", content_hash="h",
            satisfies=[{"req_id": "REQ-x"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        store.supersede_requirement("REQ-x")

        data = services.check(store, str(f))
        assert data["linked"] is True
        assert data["drift_detected"] is True
        assert data["requirements"][0]["drifted"] is True


class TestLink:
    def test_missing_file_raises(self, store):
        with pytest.raises(LookupError):
            services.link(store, "/nonexistent/path.py", req_ids=["REQ-x"])

    def test_no_ids_returns_unlinked_with_warning(self, store, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        result = services.link(store, str(f))
        assert result["linked"] is False
        assert result["impl_id"] is None
        assert result["warnings"]  # should explain why

    def test_all_unknown_ids_returns_unlinked_with_warnings(self, store, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        result = services.link(store, str(f), req_ids=["REQ-ghost"])
        assert result["linked"] is False
        assert any("REQ-ghost" in w for w in result["warnings"])

    def test_unknown_req_warned_and_skipped(self, store, fake_embedding, tmp_path):
        _mk_req(store, "REQ-real", "behavior", "real", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")

        result = services.link(
            store, str(f), req_ids=["REQ-real", "REQ-ghost"],
        )
        assert result["linked"] is True
        assert any("REQ-ghost" in w for w in result["warnings"])
        # REQ-real should still be linked despite REQ-ghost failing.
        assert any(s["req_id"] == "REQ-real" for s in result["satisfies"])

    def test_links_persisted(self, store, fake_embedding, tmp_path):
        _mk_req(store, "REQ-a", "behavior", "a", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("def a(): pass\n")
        result = services.link(store, str(f), req_ids=["REQ-a"])
        assert result["linked"] is True
        impls = store.get_implementations_for_requirement("REQ-a")
        assert len(impls) == 1
        assert impls[0].id == result["impl_id"]


class TestDetectRequirements:
    def test_missing_file_raises(self, store):
        with pytest.raises(LookupError):
            services.detect_requirements(store, "/nonexistent/path.py")

    def test_returns_candidates(self, store, fake_embedding, tmp_path):
        _mk_req(store, "REQ-1", "behavior", "match", fake_embedding)
        f = tmp_path / "x.py"
        f.write_text("anything\n")
        candidates = services.detect_requirements(store, str(f), n=3)
        assert isinstance(candidates, list)
        # With one req and matching dummy embedding, we expect to see it.
        if candidates:
            assert "req_id" in candidates[0]
            assert "value" in candidates[0]


class TestSync:
    def test_writes_both_docs(self, store, tmp_path):
        result = services.sync(store, str(tmp_path))
        from pathlib import Path
        assert Path(result["requirements_path"]).exists()
        assert Path(result["test_spec_path"]).exists()
        assert result["public"] is False

    def test_public_mode_flag_passed(self, store, tmp_path):
        result = services.sync(store, str(tmp_path), public=True)
        assert result["public"] is True


class TestSupersede:
    def test_unknown_req_raises(self, store):
        with pytest.raises(LookupError):
            services.supersede(store, "REQ-missing")

    def test_already_superseded_raises_value_error(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        services.supersede(store, "REQ-x")
        with pytest.raises(ValueError):
            services.supersede(store, "REQ-x")

    def test_supersedes_and_returns_value(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "old way", fake_embedding)
        result = services.supersede(store, "REQ-x")
        assert result["req_id"] == "REQ-x"
        assert result["value"] == "old way"
        assert result["affected_tests"] == []
        # Verify mutation persisted.
        req = store.get_requirement("REQ-x")
        assert req.superseded_at is not None


class TestSetStatus:
    def test_unknown_req_raises_lookup(self, store):
        with pytest.raises(LookupError):
            services.set_status(store, "REQ-missing", "implemented")

    def test_invalid_status_raises_value_error(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        with pytest.raises(ValueError):
            services.set_status(store, "REQ-x", "bogus")

    def test_valid_status_updates(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        result = services.set_status(store, "REQ-x", "implemented")
        assert result == {"req_id": "REQ-x", "status": "implemented"}
        assert store.get_requirement("REQ-x").status == "implemented"


class TestRefine:
    def test_unknown_req_raises_lookup(self, store):
        with pytest.raises(LookupError):
            services.refine(store, "REQ-missing", elaboration="how")

    def test_empty_elaboration_raises_value_error(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        with pytest.raises(ValueError):
            services.refine(store, "REQ-x", elaboration="   ")

    def test_invalid_status_raises_value_error(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        with pytest.raises(ValueError):
            services.refine(store, "REQ-x", elaboration="how", status="bogus")

    def test_full_update(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        result = services.refine(
            store, "REQ-x",
            elaboration="add input validation on the form",
            acceptance_criteria=["empty email rejected", "bad domain rejected"],
            conversation_context="discussed in design review",
            status="in_progress",
        )
        assert result["req_id"] == "REQ-x"
        assert result["elaboration"] == "add input validation on the form"
        assert len(result["acceptance_criteria"]) == 2
        assert result["status"] == "in_progress"
        assert result["is_complete"] is True

    def test_minimal_update_keeps_pending(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        result = services.refine(store, "REQ-x", elaboration="add validation")
        # Status not provided → unchanged
        assert result["status"] == "pending"
        # Note: ChromaDB rejects empty lists, so acceptance_criteria
        # round-trips as ["TBD"]. That's a pre-existing quirk (see
        # CLAUDE.md ChromaDB metadata rules); is_complete therefore
        # returns True even though no criteria were provided.
        assert result["acceptance_criteria"] == ["TBD"]


class TestSpecAdd:
    def test_creates_spec(self, store, fake_embedding):
        _mk_req(store, "REQ-p", "behavior", "parent", fake_embedding)
        result = services.spec_add(
            store, "REQ-p", "use pydantic for validation",
            acceptance_criteria=["rejects bad email"],
        )
        assert result["spec_id"].startswith("SPEC-")
        assert result["parent_req"] == "REQ-p"
        assert result["acceptance_criteria"] == ["rejects bad email"]
        assert store.get_specification(result["spec_id"]) is not None

    def test_unknown_parent_raises(self, store):
        with pytest.raises(LookupError):
            services.spec_add(store, "REQ-missing", "spec text")

    def test_empty_description_raises(self, store, fake_embedding):
        _mk_req(store, "REQ-p", "behavior", "p", fake_embedding)
        with pytest.raises(ValueError):
            services.spec_add(store, "REQ-p", "   ")

    def test_test_file_stored_and_skeleton_written(self, store, fake_embedding):
        _mk_req(store, "REQ-t", "behavior", "parent", fake_embedding)
        with tempfile.TemporaryDirectory() as td:
            result = services.spec_add(
                store, "REQ-t", "add route",
                test_file="tests/test_route.py::TestRoute",
                target_dir=td,
            )
            assert result["test_file"] == "tests/test_route.py::TestRoute"
            assert result["test_skeleton_written"] is True
            skeleton = Path(td) / "tests" / "test_route.py"
            assert skeleton.exists()
            content = skeleton.read_text(encoding="utf-8")
            # Placeholder intentionally fails so an empty skeleton never
            # passes.
            assert "class TestRoute" in content
            assert "pytest.fail" in content
            # Store roundtrip preserves the field
            assert store.get_specification(result["spec_id"]).test_file == \
                "tests/test_route.py::TestRoute"

    def test_test_file_not_overwritten_when_exists(self, store, fake_embedding):
        _mk_req(store, "REQ-t", "behavior", "parent", fake_embedding)
        with tempfile.TemporaryDirectory() as td:
            existing = Path(td) / "tests" / "test_route.py"
            existing.parent.mkdir(parents=True)
            existing.write_text("# real tests here", encoding="utf-8")
            result = services.spec_add(
                store, "REQ-t", "d",
                test_file="tests/test_route.py::TestRoute",
                target_dir=td,
            )
            assert result["test_skeleton_written"] is False
            # Existing content preserved
            assert existing.read_text(encoding="utf-8") == "# real tests here"

    def test_test_file_without_target_dir_stores_but_no_skeleton(self, store, fake_embedding):
        _mk_req(store, "REQ-t", "behavior", "parent", fake_embedding)
        result = services.spec_add(
            store, "REQ-t", "d",
            test_file="tests/test_route.py::TestRoute",
            target_dir=None,
        )
        assert result["test_file"] == "tests/test_route.py::TestRoute"
        assert result["test_skeleton_written"] is None

    def test_malformed_test_file_raises(self, store, fake_embedding):
        _mk_req(store, "REQ-t", "behavior", "parent", fake_embedding)
        with pytest.raises(ValueError):
            services.spec_add(
                store, "REQ-t", "d",
                test_file="tests/test_route.py",   # missing ::Class
            )


class TestValidateWithSpecTestFile:
    """Validator should force-override LLM test_to_write when spec has test_file."""

    def test_override_when_llm_invents_different_path(self):
        from services import _validate_task_proposals
        proposals = [{
            "title": "Add route",
            "files_to_modify": ["src/main.py"],
            "test_to_write": "tests/test_wrong.py::Wrong",
            "context_files": [],
        }]
        normalized, warnings = _validate_task_proposals(
            proposals, parent_spec="SPEC-x",
            spec_test_file="tests/test_right.py::Right",
        )
        assert normalized[0]["test_to_write"] == "tests/test_right.py::Right"
        assert any("replaced" in w for w in warnings)

    def test_passthrough_when_already_correct(self):
        from services import _validate_task_proposals
        proposals = [{
            "title": "Add route",
            "files_to_modify": ["src/main.py"],
            "test_to_write": "tests/test_right.py::Right",
            "context_files": [],
        }]
        normalized, warnings = _validate_task_proposals(
            proposals, parent_spec="SPEC-x",
            spec_test_file="tests/test_right.py::Right",
        )
        assert normalized[0]["test_to_write"] == "tests/test_right.py::Right"
        assert not any("replaced" in w for w in warnings)


class TestSpecList:
    def test_empty(self, store):
        assert services.spec_list(store) == []

    def test_filtered_by_parent(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "a", fake_embedding)
        _mk_req(store, "REQ-b", "behavior", "b", fake_embedding)
        services.spec_add(store, "REQ-a", "spec for a")
        services.spec_add(store, "REQ-b", "spec for b")

        for_a = services.spec_list(store, req_id="REQ-a")
        assert len(for_a) == 1
        assert for_a[0]["parent_req"] == "REQ-a"


class TestSpecLink:
    def test_missing_spec_raises(self, store, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("x\n")
        with pytest.raises(LookupError):
            services.spec_link(store, "SPEC-missing", str(f))

    def test_missing_file_raises(self, store, fake_embedding):
        _mk_req(store, "REQ-p", "behavior", "p", fake_embedding)
        sp = services.spec_add(store, "REQ-p", "spec")
        with pytest.raises(LookupError):
            services.spec_link(store, sp["spec_id"], "/nonexistent/x.py")

    def test_creates_impl(self, store, fake_embedding, tmp_path):
        _mk_req(store, "REQ-p", "behavior", "p", fake_embedding)
        sp = services.spec_add(store, "REQ-p", "spec")
        f = tmp_path / "impl.py"
        f.write_text("code\n")

        result = services.spec_link(store, sp["spec_id"], str(f))
        assert result["reused"] is False
        assert result["parent_req"] == "REQ-p"
        # Impl is now linked to the spec.
        impls = store.get_implementations_for_specification(sp["spec_id"])
        assert len(impls) == 1


class TestPatternAdd:
    def test_creates_pattern(self, store):
        result = services.pattern_add(
            store, "Retry w/ backoff", "exponential backoff for API calls",
        )
        assert result["pattern_id"].startswith("PAT-")
        assert result["applies_to"] == []
        assert result["missing_reqs"] == []

    def test_missing_reqs_reported(self, store, fake_embedding):
        _mk_req(store, "REQ-real", "behavior", "real", fake_embedding)
        result = services.pattern_add(
            store, "P", "desc", applies_to=["REQ-real", "REQ-ghost"],
        )
        assert result["missing_reqs"] == ["REQ-ghost"]
        # Pattern still created with both in applies_to.
        assert set(result["applies_to"]) == {"REQ-real", "REQ-ghost"}

    def test_empty_name_raises(self, store):
        with pytest.raises(ValueError):
            services.pattern_add(store, "", "description")


class TestPatternList:
    def test_empty(self, store):
        assert services.pattern_list(store) == []

    def test_shape(self, store):
        services.pattern_add(store, "N", "D")
        patterns = services.pattern_list(store)
        assert len(patterns) == 1
        assert set(patterns[0].keys()) >= {
            "id", "name", "description", "status",
            "applies_to", "implementation_count",
        }


class TestPatternApply:
    def test_unknown_pattern_raises(self, store):
        with pytest.raises(LookupError):
            services.pattern_apply(store, "PAT-missing", ["REQ-x"])

    def test_adds_and_skips(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "a", fake_embedding)
        _mk_req(store, "REQ-b", "behavior", "b", fake_embedding)
        p = services.pattern_add(store, "N", "D", applies_to=["REQ-a"])
        result = services.pattern_apply(
            store, p["pattern_id"], ["REQ-a", "REQ-b"]
        )
        # REQ-a already on pattern → skipped; REQ-b new → added.
        assert "REQ-b" in result["added"]
        assert "REQ-a" in result["skipped"]


class TestTestAdd:
    def test_unknown_req_raises(self, store):
        with pytest.raises(LookupError):
            services.test_add(store, "REQ-missing", description="d")

    def test_new_without_description_raises(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        with pytest.raises(ValueError):
            services.test_add(store, "REQ-x")

    def test_creates_and_merges(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        services.test_add(store, "REQ-x", description="first", steps=["a"])
        # Re-add without description: inherits existing description.
        result = services.test_add(store, "REQ-x", expected="pass")
        assert result["description"] == "first"
        assert result["expected"] == "pass"
        assert result["steps"] == ["a"]  # inherited


class TestTestVerify:
    def test_no_spec_raises(self, store):
        with pytest.raises(LookupError):
            services.test_verify(store, "REQ-missing")

    def test_marks_verified(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        services.test_add(store, "REQ-x", description="d")
        result = services.test_verify(store, "REQ-x")
        assert result["last_verified"] is not None


class TestTestList:
    def test_empty(self, store):
        assert services.test_list(store) == []

    def test_includes_added(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        services.test_add(store, "REQ-x", description="d")
        specs = services.test_list(store)
        assert len(specs) == 1
        assert specs[0]["req_id"] == "REQ-x"


class TestTestGenerate:
    def test_no_criteria_all_skipped(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        result = services.test_generate(store)
        assert result["generated"] == []
        assert "REQ-x" in result["no_criteria"]

    def test_generates_from_criteria(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        services.refine(
            store, "REQ-x",
            elaboration="how", acceptance_criteria=["a", "b"],
        )
        result = services.test_generate(store)
        assert "REQ-x" in result["generated"]
        # Re-running without force → skipped.
        result2 = services.test_generate(store)
        assert "REQ-x" in result2["skipped"]


class TestContext:
    def test_missing_file_raises(self, store):
        with pytest.raises(LookupError):
            services.context(store, "/nonexistent/path.py")

    def test_unlinked_file_returns_empty_briefing(self, store, tmp_path):
        f = tmp_path / "untracked.py"
        f.write_text("x = 1\n")
        data = services.context(store, str(f))
        assert data["linked"] is False
        assert data["drift_detected"] is False
        assert data["requirements"] == []
        assert data["specifications"] == []
        assert data["summary"] == ""

    def test_linked_file_lists_requirements(self, store, fake_embedding, tmp_path):
        from store import generate_impl_id
        _mk_req(store, "REQ-a", "behavior", "must do A", fake_embedding)
        _mk_req(store, "REQ-b", "data", "data rule B", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("pass\n")

        impl = Implementation(
            id=generate_impl_id(str(f), "1-5"),
            file=str(f), lines="1-5",
            content="pass\n", content_hash="h",
            satisfies=[{"req_id": "REQ-a"}, {"req_id": "REQ-b"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)

        data = services.context(store, str(f))
        assert data["linked"] is True
        assert data["drift_detected"] is False
        ids = {r["id"] for r in data["requirements"]}
        assert ids == {"REQ-a", "REQ-b"}
        # Domain and lines are surfaced for the agent to reason about scope.
        assert all(r["lines"] == "1-5" for r in data["requirements"])
        assert "2 req(s)" in data["summary"]
        assert "DRIFT" not in data["summary"]

    def test_drift_flagged_and_in_summary(self, store, fake_embedding, tmp_path):
        from store import generate_impl_id
        _mk_req(store, "REQ-stale", "behavior", "stale rule", fake_embedding)
        f = tmp_path / "x.py"
        f.write_text("pass\n")

        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="pass\n", content_hash="h",
            satisfies=[{"req_id": "REQ-stale"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        store.supersede_requirement("REQ-stale")

        data = services.context(store, str(f))
        assert data["drift_detected"] is True
        assert data["requirements"][0]["superseded"] is True
        assert "DRIFT" in data["summary"]
        assert "REQ-stale" in data["summary"]

    def test_aggregates_across_multiple_impls(self, store, fake_embedding, tmp_path):
        """`check()` wants an exact (file, lines) match; `context()` must not."""
        from store import generate_impl_id
        _mk_req(store, "REQ-a", "behavior", "A", fake_embedding)
        _mk_req(store, "REQ-b", "behavior", "B", fake_embedding)
        f = tmp_path / "wide.py"
        f.write_text("line1\nline2\nline3\n")

        impl1 = Implementation(
            id=generate_impl_id(str(f), "1-2"),
            file=str(f), lines="1-2",
            content="line1\nline2\n", content_hash="h1",
            satisfies=[{"req_id": "REQ-a"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        impl2 = Implementation(
            id=generate_impl_id(str(f), "3-3"),
            file=str(f), lines="3-3",
            content="line3\n", content_hash="h2",
            satisfies=[{"req_id": "REQ-b"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl1, fake_embedding)
        store.add_implementation(impl2, fake_embedding)

        data = services.context(store, str(f))
        assert {r["id"] for r in data["requirements"]} == {"REQ-a", "REQ-b"}


class TestCost:
    def _write_log(self, store, entries):
        import json as _json
        path = store.data_dir / ".hook-log.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for e in entries:
                if isinstance(e, str):
                    f.write(e + "\n")
                else:
                    f.write(_json.dumps(e) + "\n")
        return path

    def test_missing_log_returns_empty_stats(self, store):
        data = services.cost(store)
        assert data["exists"] is False
        assert data["fires"] == 0
        assert data["latency_ms"]["p50"] == 0.0

    def test_empty_log_flags_exists_true(self, store):
        (store.data_dir / ".hook-log.jsonl").write_text("", encoding="utf-8")
        data = services.cost(store)
        assert data["exists"] is True
        assert data["fires"] == 0

    def test_counts_fires_injections_and_overhead(self, store):
        self._write_log(store, [
            {"tool": "Edit", "fired": True, "latency_ms": 1.0, "bytes": 200,
             "reqs": 2, "specs": 0, "drift": False, "skipped": None},
            {"tool": "Edit", "fired": False, "latency_ms": 2.0, "bytes": 0,
             "reqs": 0, "specs": 0, "drift": False, "skipped": "no_link"},
            {"tool": "Write", "fired": True, "latency_ms": 3.0, "bytes": 100,
             "reqs": 1, "specs": 0, "drift": True, "skipped": None},
            {"tool": "Write", "fired": False, "latency_ms": 5.0, "bytes": 0,
             "reqs": 0, "specs": 0, "drift": False, "skipped": "cli_error"},
        ])
        data = services.cost(store)
        assert data["fires"] == 4
        assert data["injections"] == 2
        assert data["empty_fires"] == 2
        assert data["overhead_pct"] == 50.0
        assert data["drift_events"] == 1
        assert data["by_tool"] == {"Edit": 2, "Write": 2}
        assert data["skipped"] == {"no_link": 1, "cli_error": 1}
        assert data["bytes"]["total"] == 300
        # Token estimate is bytes / 4 (integer total, rounded avg).
        assert data["tokens_est"]["total"] == 75
        assert data["latency_ms"]["max"] == 5.0
        # With 4 entries, p50 ≈ the 2nd-smallest (2.0); p99 ≈ max (5.0).
        assert data["latency_ms"]["p50"] == 2.0
        assert data["latency_ms"]["p99"] == 5.0

    def test_tail_limits_window(self, store):
        entries = [
            {"tool": "Edit", "fired": True, "latency_ms": float(i), "bytes": 10,
             "reqs": 1, "specs": 0, "drift": False, "skipped": None}
            for i in range(10)
        ]
        self._write_log(store, entries)
        data = services.cost(store, tail=3)
        assert data["fires"] == 3
        # Last 3 entries have latencies 7,8,9.
        assert data["latency_ms"]["max"] == 9.0

    def test_malformed_lines_are_skipped(self, store):
        self._write_log(store, [
            {"tool": "Edit", "fired": True, "latency_ms": 1.0, "bytes": 40,
             "reqs": 1, "specs": 0, "drift": False, "skipped": None},
            "this is not json",
            "",
            {"tool": "Edit", "fired": False, "latency_ms": 2.0, "bytes": 0,
             "reqs": 0, "specs": 0, "drift": False, "skipped": "no_link"},
        ])
        data = services.cost(store)
        assert data["fires"] == 2
        assert data["injections"] == 1

    def test_log_path_override(self, store, tmp_path):
        import json as _json
        alt = tmp_path / "elsewhere.jsonl"
        alt.write_text(_json.dumps({
            "tool": "Edit", "fired": True, "latency_ms": 7.0, "bytes": 80,
            "reqs": 1, "specs": 0, "drift": False, "skipped": None,
        }) + "\n", encoding="utf-8")
        data = services.cost(store, log_path=alt)
        assert data["log_path"] == str(alt)
        assert data["fires"] == 1
        assert data["bytes"]["total"] == 80


class TestIncomplete:
    def test_empty_store(self, store):
        assert services.incomplete(store) == []

    def test_missing_elaboration_reported(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        incomplete = services.incomplete(store)
        assert len(incomplete) == 1
        assert "elaboration" in incomplete[0]["missing"]
        assert "acceptance criteria" in incomplete[0]["missing"]


class TestGaps:
    """Tests for services.gaps()."""

    def _mk_req(self, store, req_id, value="placeholder", elaboration=None, criteria=None, fake_embedding=None):
        """Create a requirement with optional elaboration and criteria."""
        req = Requirement(
            id=req_id,
            domain="behavior",
            value=value,
            source_msg_id="m1",
            source_session="s1",
            timestamp="2026-01-01T00:00:00Z",
            elaboration=elaboration,
            acceptance_criteria=criteria,
        )
        store.add_requirement(req, fake_embedding or [0.1] * 768)
        return req

    def _mk_impl(self, store, impl_id_file, impl_id_lines, satisfies_req_ids, fake_embedding=None):
        """Create an implementation with satisfies list."""
        from store import generate_impl_id
        impl = Implementation(
            id=generate_impl_id(impl_id_file, impl_id_lines),
            file=impl_id_file,
            lines=impl_id_lines,
            content="pass\n",
            content_hash="h",
            satisfies=[{"req_id": r} for r in satisfies_req_ids],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding or [0.1] * 768)
        return impl

    def test_empty_store_returns_empty_list(self, store):
        assert services.gaps(store) == []

    def test_missing_criteria_surfaced(self, store, fake_embedding):
        self._mk_req(store, "REQ-nc", elaboration="some elaboration text", fake_embedding=fake_embedding)
        gaps = services.gaps(store)
        matches = [g for g in gaps if g["entity_id"] == "REQ-nc"]
        assert any(g["type"] == "missing_criteria" for g in matches), \
            f"Expected missing_criteria gap for REQ-nc; got {matches}"

    def test_missing_elaboration_surfaced(self, store, fake_embedding):
        self._mk_req(store, "REQ-ne", criteria=["criterion one"], fake_embedding=fake_embedding)
        gaps = services.gaps(store)
        matches = [g for g in gaps if g["entity_id"] == "REQ-ne"]
        assert any(g["type"] == "missing_elaboration" for g in matches), \
            f"Expected missing_elaboration gap for REQ-ne; got {matches}"

    def test_orphan_impl_surfaced(self, store, fake_embedding):
        self._mk_impl(store, "/tmp/a.py", "1-5", ["REQ-does-not-exist"], fake_embedding=fake_embedding)
        gaps = services.gaps(store)
        assert any(g["type"] == "orphan_impl" for g in gaps), \
            f"Expected orphan_impl gap; got {gaps}"

    def test_impl_with_superseded_req_is_orphan(self, store, fake_embedding):
        self._mk_req(store, "REQ-old", elaboration="x", criteria=["c"], fake_embedding=fake_embedding)
        store.supersede_requirement("REQ-old")
        self._mk_impl(store, "/tmp/b.py", "1-5", ["REQ-old"], fake_embedding=fake_embedding)
        gaps = services.gaps(store)
        # An impl whose only linked req is superseded is orphan-adjacent.
        assert any(g["type"] == "orphan_impl" for g in gaps), \
            f"Expected orphan_impl gap for superseded-only impl; got {gaps}"

    def test_impl_with_any_live_req_is_not_orphan(self, store, fake_embedding):
        self._mk_req(store, "REQ-live", elaboration="x", criteria=["c"], fake_embedding=fake_embedding)
        self._mk_req(store, "REQ-dead", elaboration="x", criteria=["c"], fake_embedding=fake_embedding)
        store.supersede_requirement("REQ-dead")
        self._mk_impl(store, "/tmp/c.py", "1-5", ["REQ-live", "REQ-dead"], fake_embedding=fake_embedding)
        gaps = services.gaps(store)
        orphans = [g for g in gaps if g["type"] == "orphan_impl"]
        assert orphans == [], \
            f"Impl with at least one live linked req should not be orphan; got {orphans}"

    def test_uniform_shape(self, store, fake_embedding):
        self._mk_req(store, "REQ-a", fake_embedding=fake_embedding)
        self._mk_impl(store, "/tmp/d.py", "1-5", ["REQ-missing"], fake_embedding=fake_embedding)
        gaps = services.gaps(store)
        assert gaps, "expected at least one gap"
        required = {"type", "entity_id", "description", "blocks", "suggested_action"}
        for g in gaps:
            missing_keys = required - set(g.keys())
            assert not missing_keys, f"gap missing keys {missing_keys}: {g}"
            for k in required:
                assert g[k] is not None, f"field {k} was None in gap {g}"
            assert isinstance(g["blocks"], list), f"blocks must be list; got {type(g['blocks'])}"
            assert isinstance(g["suggested_action"], str), "suggested_action must be string"
            assert g["suggested_action"].strip(), "suggested_action must be non-empty"

    def test_ordering_by_priority(self, store, fake_embedding):
        # Two reqs: one needs criteria (higher priority), one needs elaboration.
        self._mk_req(store, "REQ-crit", elaboration="has elab", fake_embedding=fake_embedding)   # missing_criteria
        self._mk_req(store, "REQ-elab", criteria=["c1"], fake_embedding=fake_embedding)          # missing_elaboration
        self._mk_impl(store, "/tmp/e.py", "1-5", ["REQ-absent"], fake_embedding=fake_embedding)  # orphan_impl
        gaps = services.gaps(store)
        types_in_order = [g["type"] for g in gaps]
        # Every missing_criteria entry must appear before any missing_elaboration entry.
        if "missing_criteria" in types_in_order and "missing_elaboration" in types_in_order:
            assert types_in_order.index("missing_criteria") < types_in_order.index("missing_elaboration")
        # Every missing_elaboration must appear before any orphan_impl.
        if "missing_elaboration" in types_in_order and "orphan_impl" in types_in_order:
            assert types_in_order.index("missing_elaboration") < types_in_order.index("orphan_impl")

    def test_tie_break_by_entity_id(self, store, fake_embedding):
        self._mk_req(store, "REQ-b", elaboration="e", fake_embedding=fake_embedding)  # missing_criteria
        self._mk_req(store, "REQ-a", elaboration="e", fake_embedding=fake_embedding)  # missing_criteria
        gaps = services.gaps(store)
        mc = [g for g in gaps if g["type"] == "missing_criteria"]
        assert [g["entity_id"] for g in mc] == sorted(g["entity_id"] for g in mc), \
            "tie-break should be ascending entity_id"

    def test_type_filter(self, store, fake_embedding):
        self._mk_req(store, "REQ-x", fake_embedding=fake_embedding)  # both elab AND criteria missing
        self._mk_impl(store, "/tmp/f.py", "1-5", ["REQ-absent"], fake_embedding=fake_embedding)  # orphan_impl
        only_orphan = services.gaps(store, types=["orphan_impl"])
        assert all(g["type"] == "orphan_impl" for g in only_orphan), \
            f"types filter leaked other types: {only_orphan}"

    def test_limit_cap(self, store, fake_embedding):
        for i in range(5):
            self._mk_req(store, f"REQ-{i:02d}", elaboration="e", fake_embedding=fake_embedding)
        gaps = services.gaps(store, limit=3)
        assert len(gaps) <= 3

    def test_superseded_reqs_excluded_from_req_level_gaps(self, store, fake_embedding):
        self._mk_req(store, "REQ-sup", fake_embedding=fake_embedding)  # both elab + criteria missing
        store.supersede_requirement("REQ-sup")
        gaps = services.gaps(store)
        bad = [g for g in gaps
               if g["entity_id"] == "REQ-sup"
               and g["type"] in {"missing_criteria", "missing_elaboration"}]
        assert bad == [], f"superseded reqs must not surface as missing_* gaps; got {bad}"

    def test_complete_reqs_do_not_surface(self, store, fake_embedding):
        self._mk_req(store, "REQ-ok", elaboration="fully elaborated", criteria=["c1", "c2"], fake_embedding=fake_embedding)
        gaps = services.gaps(store)
        related = [g for g in gaps if g["entity_id"] == "REQ-ok"]
        assert related == [], f"complete req should not appear in gaps; got {related}"


def _mk_spec(store, spec_id, parent_req, fake_embedding):
    from store import Specification
    spec = Specification(
        id=spec_id, parent_req=parent_req,
        description=f"spec for {parent_req}",
        timestamp="2026-01-01T00:00:00Z",
        acceptance_criteria=["c1"],
    )
    store.add_specification(spec, fake_embedding)
    return spec


class TestTaskAdd:
    def test_basic_task_created(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "must X", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)
        result = services.task_add(
            store, parent_spec="SPEC-a", title="implement X",
            files_to_modify=["src/a.py"],
            test_to_write="tests/test_a.py::TestX",
        )
        assert result["id"].startswith("TASK-")
        assert result["status"] == "pending"
        assert result["parent_spec"] == "SPEC-a"

    def test_missing_spec_raises(self, store):
        with pytest.raises(LookupError):
            services.task_add(
                store, parent_spec="SPEC-ghost", title="x",
                files_to_modify=["a"], test_to_write="t::T",
            )

    def test_empty_title_raises(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)
        with pytest.raises(ValueError):
            services.task_add(
                store, parent_spec="SPEC-a", title="",
                files_to_modify=["a"], test_to_write="t::T",
            )

    def test_empty_files_raises(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)
        with pytest.raises(ValueError):
            services.task_add(
                store, parent_spec="SPEC-a", title="t",
                files_to_modify=[], test_to_write="t::T",
            )

    def test_unknown_dep_raises(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)
        with pytest.raises(ValueError):
            services.task_add(
                store, parent_spec="SPEC-a", title="t",
                files_to_modify=["a"], test_to_write="t::T",
                depends_on=["TASK-ghost"],
            )


class TestTaskLifecycle:
    def _seed(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)
        result = services.task_add(
            store, parent_spec="SPEC-a", title="do thing",
            files_to_modify=["src/a.py"], test_to_write="t::T",
        )
        return result["id"]

    def test_claim_then_complete(self, store, fake_embedding):
        tid = self._seed(store, fake_embedding)
        services.task_claim(store, tid, claimed_by="qwen3.5:latest")
        t = services.task_get(store, tid)
        assert t["status"] == "claimed"
        assert t["claimed_by"] == "qwen3.5:latest"
        services.task_complete(store, tid, impl_ids=["IMPL-xyz"])
        t = services.task_get(store, tid)
        assert t["status"] == "complete"
        assert t["completed_at"] is not None

    def test_cannot_claim_claimed(self, store, fake_embedding):
        tid = self._seed(store, fake_embedding)
        services.task_claim(store, tid, claimed_by="a")
        with pytest.raises(ValueError):
            services.task_claim(store, tid, claimed_by="b")

    def test_release_returns_to_pending(self, store, fake_embedding):
        tid = self._seed(store, fake_embedding)
        services.task_claim(store, tid, claimed_by="a")
        services.task_release(store, tid)
        t = services.task_get(store, tid)
        assert t["status"] == "pending"
        assert t["claimed_by"] is None

    def test_reject_non_escalated(self, store, fake_embedding):
        tid = self._seed(store, fake_embedding)
        services.task_claim(store, tid, claimed_by="a")
        services.task_reject(store, tid, reason="too broad")
        t = services.task_get(store, tid)
        assert t["status"] == "rejected"
        assert t["rejection_reason"] == "too broad"
        assert t["escalation_count"] == 0

    def test_reject_escalated(self, store, fake_embedding):
        tid = self._seed(store, fake_embedding)
        services.task_claim(store, tid, claimed_by="a")
        services.task_reject(store, tid, reason="NEED_CONTEXT: foo", escalate=True)
        t = services.task_get(store, tid)
        assert t["status"] == "escalated"
        assert t["escalation_count"] == 1

    def test_reject_requires_reason(self, store, fake_embedding):
        tid = self._seed(store, fake_embedding)
        services.task_claim(store, tid, claimed_by="a")
        with pytest.raises(ValueError):
            services.task_reject(store, tid, reason="")

    def test_complete_from_non_claimed_raises(self, store, fake_embedding):
        tid = self._seed(store, fake_embedding)
        with pytest.raises(ValueError):
            services.task_complete(store, tid)

    def test_task_get_missing(self, store):
        with pytest.raises(LookupError):
            services.task_get(store, "TASK-404")


class TestTaskList:
    def test_ready_only_excludes_blocked(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)
        t1 = services.task_add(store, parent_spec="SPEC-a", title="first",
                               files_to_modify=["a"], test_to_write="t::T")
        t2 = services.task_add(store, parent_spec="SPEC-a", title="second",
                               files_to_modify=["a"], test_to_write="t::T",
                               depends_on=[t1["id"]])

        ready = services.task_list(store, ready_only=True)
        assert {t["id"] for t in ready} == {t1["id"]}

        services.task_claim(store, t1["id"], claimed_by="w")
        services.task_complete(store, t1["id"])

        ready = services.task_list(store, ready_only=True)
        assert {t["id"] for t in ready} == {t2["id"]}

    def test_filter_by_status(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)
        a = services.task_add(store, parent_spec="SPEC-a", title="a",
                              files_to_modify=["x"], test_to_write="t::T")
        b = services.task_add(store, parent_spec="SPEC-a", title="b",
                              files_to_modify=["x"], test_to_write="t::T")
        services.task_claim(store, a["id"], claimed_by="w")
        pending = services.task_list(store, status="pending")
        assert {t["id"] for t in pending} == {b["id"]}


class TestTaskBuildPrompt:
    def test_prompt_assembles_context(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        store.update_requirement("REQ-a", {
            "elaboration": "how to do X",
            "acceptance_criteria": ["criterion1"],
        })
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)
        result = services.task_add(
            store, parent_spec="SPEC-a", title="do thing",
            files_to_modify=["src/a.py"], test_to_write="t::T",
            context_reqs=["REQ-a"], context_specs=["SPEC-a"],
        )
        prompt = services.task_build_prompt(store, result["id"])
        assert "# Task" in prompt
        assert "REQ-a" in prompt
        assert "SPEC-a" in prompt
        assert "how to do X" in prompt
        assert "criterion1" in prompt
        assert "Output contract" in prompt

    def test_prompt_missing_refs_are_skipped_silently(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)
        result = services.task_add(
            store, parent_spec="SPEC-a", title="x",
            files_to_modify=["a"], test_to_write="t::T",
            context_reqs=["REQ-ghost", "REQ-a"],
        )
        prompt = services.task_build_prompt(store, result["id"])
        assert "REQ-a" in prompt

    def test_prompt_for_missing_task_raises(self, store):
        with pytest.raises(LookupError):
            services.task_build_prompt(store, "TASK-404")


class TestDecomposeParsing:
    def test_spec_too_big_stop_token(self):
        out, data = services._parse_decompose_response(
            "SPEC_TOO_BIG: mixes auth and UI concerns"
        )
        assert out == "spec_too_big"
        assert "auth" in data

    def test_need_context_stop_token(self):
        out, data = services._parse_decompose_response(
            "NEED_CONTEXT: no acceptance criteria on parent req"
        )
        assert out == "need_context"

    def test_yaml_tasks_parsed(self):
        resp = (
            "```yaml\n"
            "tasks:\n"
            "  - title: t1\n"
            "    files_to_modify: [src/a.py]\n"
            "    test_to_write: tests/a.py::T\n"
            "```"
        )
        out, data = services._parse_decompose_response(resp)
        assert out == "tasks"
        assert len(data) == 1
        assert data[0]["title"] == "t1"

    def test_no_yaml_block(self):
        out, _ = services._parse_decompose_response("just prose, no yaml")
        assert out == "no_yaml"

    def test_malformed_yaml(self):
        out, _ = services._parse_decompose_response("```yaml\n::::: bad\n```")
        # Malformed YAML may either fail to parse (yaml_error) or produce a
        # non-dict scalar (also yaml_error per our strict top-level check).
        assert out == "yaml_error"


class TestValidateProposals:
    def test_minimum_fields_accepted(self):
        proposals = [{
            "title": "t1",
            "files_to_modify": ["src/a.py"],
            "test_to_write": "tests/a.py::T",
        }]
        norm, warns = services._validate_task_proposals(proposals, parent_spec="SPEC-a")
        assert len(norm) == 1
        assert norm[0]["parent_spec"] == "SPEC-a"
        assert norm[0]["size_budget_files"] == 2   # default
        assert norm[0]["size_budget_loc"] == 80    # default
        assert warns == []

    def test_missing_title_skipped(self):
        norm, warns = services._validate_task_proposals(
            [{"files_to_modify": ["a"], "test_to_write": "t::T"}],
            parent_spec="SPEC-a",
        )
        assert norm == []
        assert any("title" in w for w in warns)

    def test_duplicate_title_skipped(self):
        proposals = [
            {"title": "dup", "files_to_modify": ["a"], "test_to_write": "t::T"},
            {"title": "dup", "files_to_modify": ["b"], "test_to_write": "t::T"},
        ]
        norm, warns = services._validate_task_proposals(proposals, parent_spec="SPEC-a")
        assert len(norm) == 1
        assert any("duplicate" in w for w in warns)

    def test_empty_files_skipped(self):
        norm, warns = services._validate_task_proposals(
            [{"title": "t", "files_to_modify": [], "test_to_write": "t::T"}],
            parent_spec="SPEC-a",
        )
        assert norm == []

    def test_atomicity_warning_for_oversize_files(self):
        norm, warns = services._validate_task_proposals(
            [{"title": "huge", "files_to_modify": ["a", "b", "c", "d"],
              "test_to_write": "t::T", "size_budget_files": 2}],
            parent_spec="SPEC-a",
        )
        # Still normalized (we warn, don't drop — let the caller decide).
        assert len(norm) == 1
        assert any("exceeds budget" in w for w in warns)

    def test_unknown_deps_are_dropped_with_warning(self):
        proposals = [
            {"title": "a", "files_to_modify": ["x"], "test_to_write": "t::T"},
            {"title": "b", "files_to_modify": ["x"], "test_to_write": "t::T",
             "depends_on": ["a", "ghost"]},
        ]
        norm, warns = services._validate_task_proposals(proposals, parent_spec="SPEC-a")
        assert len(norm) == 2
        assert norm[1]["depends_on_titles"] == ["a"]  # ghost dropped
        assert any("not found" in w for w in warns)

    def test_forward_dep_treated_as_unknown(self):
        # Deps must reference EARLIER tasks; forward references dropped.
        proposals = [
            {"title": "a", "files_to_modify": ["x"], "test_to_write": "t::T",
             "depends_on": ["b"]},   # forward ref to later task
            {"title": "b", "files_to_modify": ["x"], "test_to_write": "t::T"},
        ]
        norm, warns = services._validate_task_proposals(proposals, parent_spec="SPEC-a")
        assert norm[0]["depends_on_titles"] == []
        assert any("not found" in w for w in warns)


class TestApplyDecomposition:
    def test_applies_tasks_and_wires_deps(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)
        proposals = [
            {"title": "t1", "parent_spec": "SPEC-a",
             "files_to_modify": ["src/a.py"], "test_to_write": "tests/a.py::T",
             "size_budget_files": 2, "size_budget_loc": 80,
             "depends_on_titles": []},
            {"title": "t2", "parent_spec": "SPEC-a",
             "files_to_modify": ["src/b.py"], "test_to_write": "tests/b.py::T",
             "size_budget_files": 2, "size_budget_loc": 80,
             "depends_on_titles": ["t1"]},
        ]
        result = services.apply_decomposition(store, proposals)
        assert len(result["created"]) == 2
        assert result["skipped"] == []
        # t2 should have t1's id as its dependency
        t1_id = result["created"][0]["id"]
        assert result["created"][1]["depends_on"] == [t1_id]

    def test_skips_bad_proposal_without_halting(self, store, fake_embedding):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)
        proposals = [
            {"title": "good", "parent_spec": "SPEC-a",
             "files_to_modify": ["src/a.py"], "test_to_write": "t::T",
             "size_budget_files": 2, "size_budget_loc": 80,
             "depends_on_titles": []},
            {"title": "bad", "parent_spec": "SPEC-ghost",  # parent missing
             "files_to_modify": ["src/b.py"], "test_to_write": "t::T",
             "size_budget_files": 2, "size_budget_loc": 80,
             "depends_on_titles": []},
        ]
        result = services.apply_decomposition(store, proposals)
        assert len(result["created"]) == 1
        assert len(result["skipped"]) == 1
        assert result["skipped"][0]["title"] == "bad"


class TestDecomposeService:
    def test_missing_spec_raises(self, store):
        with pytest.raises(LookupError):
            services.decompose(store, "SPEC-ghost")

    def test_dispatches_to_model_and_returns_parsed(
        self, store, fake_embedding, monkeypatch
    ):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)

        # Stub the LLM call to avoid any network traffic.
        fake = {
            "content": (
                "```yaml\n"
                "tasks:\n"
                "  - title: t1\n"
                "    files_to_modify: [src/a.py]\n"
                "    test_to_write: tests/a.py::T\n"
                "```"
            ),
            "elapsed_s": 0.1,
            "input_tokens": 500,
            "output_tokens": 50,
        }
        monkeypatch.setattr(services, "_call_decomposer_llm",
                            lambda model, prompt, **kw: fake)

        result = services.decompose(store, "SPEC-a", model="ollama:fake-model")
        assert result["outcome"] == "tasks"
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["title"] == "t1"
        assert result["model"] == "ollama:fake-model"
        assert result["input_tokens"] == 500

    def test_propagates_spec_too_big(
        self, store, fake_embedding, monkeypatch
    ):
        _mk_req(store, "REQ-a", "behavior", "v", fake_embedding)
        _mk_spec(store, "SPEC-a", "REQ-a", fake_embedding)

        fake = {
            "content": "SPEC_TOO_BIG: combines auth and UI",
            "elapsed_s": 0.1, "input_tokens": 500, "output_tokens": 10,
        }
        monkeypatch.setattr(services, "_call_decomposer_llm",
                            lambda model, prompt, **kw: fake)

        result = services.decompose(store, "SPEC-a", model="ollama:fake")
        assert result["outcome"] == "spec_too_big"
        assert "auth" in result["reason"]
        assert result["tasks"] == []


class TestDefaultModelSelection:
    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("LOOM_DECOMPOSER_MODEL", "ollama:custom")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
        assert services._default_decomposer_model() == "ollama:custom"

    def test_anthropic_default_when_key_set(self, monkeypatch):
        monkeypatch.delenv("LOOM_DECOMPOSER_MODEL", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
        assert services._default_decomposer_model() == "anthropic:claude-opus-4-7"

    def test_ollama_fallback(self, monkeypatch):
        monkeypatch.delenv("LOOM_DECOMPOSER_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert services._default_decomposer_model() == "ollama:qwen2.5-coder:32b"
