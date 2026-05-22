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

from loom import embedding  # noqa: E402
from loom import services  # noqa: E402
from loom.store import LoomStore, Requirement, Implementation, generate_content_hash  # noqa: E402


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
            content="pass", content_hash=generate_content_hash("pass"),
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
            content="x = 1", content_hash=generate_content_hash("x = 1"),
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
            content="a", content_hash=generate_content_hash("a"),
            satisfies=[{"req_id": "REQ-1"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(direct, fake_embedding)
        data = services.chain(store, "REQ-1")
        assert len(data["direct_implementations"]) == 1
        assert data["direct_implementations"][0]["file"] == "src/a.py"
        assert data["specifications"] == []

    # M12.4 — rationale-link DAG traversal

    def test_rationale_chain_empty_when_no_links(self, store):
        services.extract(store, domain="behavior", value="standalone", rationale="r")
        # Find the req we just created.
        all_reqs = list(store.list_requirements())
        rid = all_reqs[0].id
        data = services.chain(store, rid)
        assert data["rationale_links"] == []
        assert data["rationale_ancestors"] == []
        assert data["rationale_descendants"] == []

    def test_rationale_chain_walks_ancestors(self, store):
        # A → B → C: C derives from B, B derives from A.
        a = services.extract(store, domain="behavior", value="A: anchor", rationale="origin")
        b = services.extract(
            store, domain="behavior", value="B: builds on A",
            rationale_links=[a["req_id"]],
        )
        c = services.extract(
            store, domain="behavior", value="C: builds on B",
            rationale_links=[b["req_id"]],
        )
        data = services.chain(store, c["req_id"])
        # rationale_links is just direct parents
        assert data["rationale_links"] == [b["req_id"]]
        # ancestors walks transitively, sorted by depth
        assert len(data["rationale_ancestors"]) == 2
        assert data["rationale_ancestors"][0]["id"] == b["req_id"]
        assert data["rationale_ancestors"][0]["depth"] == 1
        assert data["rationale_ancestors"][1]["id"] == a["req_id"]
        assert data["rationale_ancestors"][1]["depth"] == 2

    def test_rationale_chain_walks_descendants(self, store):
        # A has two children B and C; C has a child D.
        a = services.extract(store, domain="behavior", value="A", rationale="r")
        b = services.extract(
            store, domain="behavior", value="B (child of A)",
            rationale_links=[a["req_id"]],
        )
        c = services.extract(
            store, domain="behavior", value="C (child of A)",
            rationale_links=[a["req_id"]],
        )
        d = services.extract(
            store, domain="behavior", value="D (child of C)",
            rationale_links=[c["req_id"]],
        )
        data = services.chain(store, a["req_id"])
        descendant_ids = {x["id"] for x in data["rationale_descendants"]}
        assert descendant_ids == {b["req_id"], c["req_id"], d["req_id"]}
        # D should be at depth 2 (grandchild)
        d_entry = next(
            x for x in data["rationale_descendants"] if x["id"] == d["req_id"]
        )
        assert d_entry["depth"] == 2

    def test_rationale_chain_includes_kind_per_node(self, store):
        a = services.extract(store, domain="behavior", value="anchor", rationale="r")
        f = services.extract(
            store, domain="behavior", value="finding builds on anchor",
            rationale_links=[a["req_id"]], kind="finding",
        )
        data_a = services.chain(store, a["req_id"])
        # The finding-kind descendant carries its kind.
        assert any(
            x["id"] == f["req_id"] and x["kind"] == "finding"
            for x in data_a["rationale_descendants"]
        )
        # Reverse: chain on the finding shows the requirement-kind ancestor.
        data_f = services.chain(store, f["req_id"])
        assert any(
            x["id"] == a["req_id"] and x["kind"] == "requirement"
            for x in data_f["rationale_ancestors"]
        )


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
            assert result["checks"]["test_runner_deps"]["ok"] is True
            assert result["checks"]["test_runner_deps"]["where"] == "requirements.txt"

    def test_pytest_detected_in_nested_requirements(self):
        with tempfile.TemporaryDirectory() as td:
            backend = Path(td) / "src" / "backend"
            backend.mkdir(parents=True)
            (backend / "requirements.txt").write_text(
                "fastapi\npytest-asyncio\n", encoding="utf-8",
            )
            result = services.init(target_dir=td, project="p")
            assert result["checks"]["test_runner_deps"]["ok"] is True
            # Forward-slash path regardless of platform
            assert "backend" in result["checks"]["test_runner_deps"]["where"]

    def test_pytest_missing_warns(self):
        with tempfile.TemporaryDirectory() as td:
            result = services.init(target_dir=td, project="p")
            assert result["checks"]["test_runner_deps"]["ok"] is False
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

    def test_template_config_overrides_merged_into_config(self):
        """A Flutter template sets test_runner=flutter_test in .loom-config.json."""
        import json as _json
        with tempfile.TemporaryDirectory() as td:
            result = services.init(
                target_dir=td, project="dogfood",
                template="flutter-minimal",
                variables={"app_name": "dogfood", "description": "x",
                           "author": "a", "sdk_constraint": "^3.0.0"},
            )
            cfg_path = Path(td) / ".loom-config.json"
            cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
            assert cfg["test_runner"] == "flutter_test"
            assert cfg["language"] == "dart"
            assert cfg["test_dir"] == "test"
            # tests/ was NOT created; test/ was (per the override)
            assert (Path(td) / "test").is_dir()
            assert not (Path(td) / "tests").exists()
            # result reflects the overrides too
            assert result["config"]["test_runner"] == "flutter_test"

    def test_template_without_overrides_keeps_defaults(self):
        """python-minimal declares no config_overrides — config uses DEFAULTS."""
        import json as _json
        with tempfile.TemporaryDirectory() as td:
            services.init(
                target_dir=td, project="demo",
                template="python-minimal",
                variables={"app_name": "demoapp", "description": "t",
                           "author": "a", "python_version": "3.10"},
            )
            cfg = _json.loads((Path(td) / ".loom-config.json").read_text(encoding="utf-8"))
            assert cfg["test_runner"] == "pytest"
            assert cfg["test_dir"] == "tests"

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
            from loom import templates as _tpl
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
        # Domains check passes (no reqs, no custom domains).
        # M12.7: shape changed from "custom" (flat list) to
        # "custom_by_kind" (dict keyed by kind).
        assert data["checks"]["domains"]["custom_by_kind"] == {}

    def test_duplicate_specs_surfaced(self, store, fake_embedding):
        """doctor flags any req with >1 non-superseded spec."""
        _mk_req(store, "REQ-dup", "behavior", "x", fake_embedding)
        _mk_req(store, "REQ-single", "behavior", "y", fake_embedding)
        # Two specs under REQ-dup (via force to bypass the sibling check)
        services.spec_add(store, "REQ-dup", "spec one")
        services.spec_add(store, "REQ-dup", "spec two", force=True)
        # One spec under REQ-single — not a duplicate
        services.spec_add(store, "REQ-single", "only spec")
        data = services.doctor(store)
        dup = data["checks"]["duplicate_specs"]
        assert dup["count"] == 1
        assert dup["items"][0]["req_id"] == "REQ-dup"
        assert len(dup["items"][0]["spec_ids"]) == 2
        assert any("REQ-dup" in w for w in data["warnings"])

    def test_duplicate_specs_count_zero_when_clean(self, store, fake_embedding):
        _mk_req(store, "REQ-clean", "behavior", "y", fake_embedding)
        services.spec_add(store, "REQ-clean", "only one")
        data = services.doctor(store)
        assert data["checks"]["duplicate_specs"]["count"] == 0

    def test_orphan_impl_warned(self, store, fake_embedding):
        # Impl that points at a req that doesn't exist → orphan
        impl = Implementation(
            id="IMPL-orphan", file="src/x.py", lines="1-1",
            content="x", content_hash=generate_content_hash("x"),
            satisfies=[{"req_id": "REQ-ghost"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        data = services.doctor(store)
        assert data["checks"]["orphans"]["count"] == 1
        assert any("REQ-ghost" in w for w in data["warnings"])

    def test_ollama_models_not_truncated(self, store, monkeypatch):
        """FINDINGS-wild F3: the old [:5] slice hid models on multi-model setups."""
        from loom import services as _services
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
            content="x", content_hash=generate_content_hash("x"),
            satisfies=[{"req_id": "REQ-old"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        store.supersede_requirement("REQ-old")
        data = services.doctor(store)
        assert data["checks"]["drift"]["count"] == 1

    # ---- M12.7: kind-aware doctor ----

    def test_doctor_test_coverage_scopes_to_requirement_kind(self, store):
        # 1 requirement (no spec) + 2 findings (no spec) + 1 process_rule.
        # M12.7: only the requirement counts as "missing test spec".
        services.extract(
            store, domain="behavior", value="real req", rationale="r",
        )
        services.extract(
            store, domain="experimental", value="some finding",
            rationale="r", kind="finding",
        )
        services.extract(
            store, domain="experimental", value="another finding",
            rationale="r", kind="finding",
        )
        services.extract(
            store, domain="operational", value="some rule",
            rationale="r", kind="process_rule",
        )
        data = services.doctor(store)
        tc = data["checks"]["test_coverage"]
        assert tc["total"] == 1, "only kind=requirement counted"
        assert tc["missing"] == 1
        assert tc["scope"] == "kind=requirement"

    def test_doctor_domain_check_is_per_kind(self, store):
        # finding with domain=experimental should NOT trigger the
        # "non-standard domains" warning (experimental IS standard
        # for findings).
        services.extract(
            store, domain="experimental", value="some finding",
            rationale="r", kind="finding",
        )
        services.extract(
            store, domain="operational", value="a rule",
            rationale="r", kind="process_rule",
        )
        data = services.doctor(store)
        # No "Non-standard domains" warning for the kind-appropriate domains.
        assert not any("Non-standard domains" in w for w in data["warnings"])
        assert data["checks"]["domains"]["custom_by_kind"] == {}

    def test_doctor_domain_check_flags_truly_custom_per_kind(self, store):
        # An invented domain on a finding (e.g. "lunar_phase") should
        # still surface — but as a finding-kind warning, not generic.
        services.extract(
            store, domain="lunar_phase", value="some finding",
            rationale="r", kind="finding",
        )
        data = services.doctor(store)
        assert "lunar_phase" in str(data["warnings"])
        assert "finding" in str(data["warnings"])
        assert data["checks"]["domains"]["custom_by_kind"] == {
            "finding": ["lunar_phase"],
        }


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

    # M11.1 — rationale linkage tests

    def test_no_rationale_no_links_defaults_to_rationale_needed(self, store):
        result = services.extract(
            store, domain="behavior", value="some bare requirement",
        )
        assert result["status"] == "rationale_needed"
        req = store.get_requirement(result["req_id"])
        assert req.status == "rationale_needed"
        assert req.rationale is None
        assert (req.rationale_links or []) == []

    def test_rationale_text_alone_is_pending(self, store):
        result = services.extract(
            store, domain="behavior", value="rate limit again",
            rationale="incident 2026-01",
        )
        assert result["status"] == "pending"

    def test_rationale_links_alone_is_pending(self, store):
        parent = services.extract(
            store, domain="behavior", value="parent decision",
            rationale="originator",
        )
        result = services.extract(
            store, domain="behavior", value="derives from parent",
            rationale_links=[parent["req_id"]],
        )
        assert result["status"] == "pending"
        assert result["rationale_links"] == [parent["req_id"]]
        req = store.get_requirement(result["req_id"])
        assert req.rationale_links == [parent["req_id"]]

    def test_rationale_links_round_trip_through_store(self, store):
        parent = services.extract(
            store, domain="behavior", value="round-trip parent",
            rationale="origin",
        )
        child = services.extract(
            store, domain="behavior", value="round-trip child",
            rationale_links=[parent["req_id"]],
        )
        roundtrip = store.get_requirement(child["req_id"])
        assert roundtrip.rationale_links == [parent["req_id"]]

    def test_rationale_links_dedup_and_strip(self, store):
        p1 = services.extract(store, domain="b", value="p1", rationale="r")
        p2 = services.extract(store, domain="b", value="p2", rationale="r")
        result = services.extract(
            store, domain="b", value="dedup test",
            rationale_links=[
                p1["req_id"], p2["req_id"], p1["req_id"], "  ",
                f"  {p2['req_id']}  ",
            ],
        )
        # Dupes dropped, blanks dropped, whitespace stripped.
        assert result["rationale_links"] == [p1["req_id"], p2["req_id"]]

    def test_invalid_link_target_raises(self, store):
        with pytest.raises(ValueError, match="does not resolve"):
            services.extract(
                store, domain="behavior", value="bad link",
                rationale_links=["REQ-doesnotexist"],
            )

    def test_superseded_link_target_raises(self, store):
        parent = services.extract(
            store, domain="b", value="superseded parent", rationale="x",
        )
        store.supersede_requirement(parent["req_id"])
        with pytest.raises(ValueError, match="superseded"):
            services.extract(
                store, domain="b", value="links to superseded",
                rationale_links=[parent["req_id"]],
            )

    def test_archived_link_target_raises(self, store):
        parent = services.extract(
            store, domain="b", value="will be archived", rationale="x",
        )
        services.set_status(store, parent["req_id"], "archived")
        with pytest.raises(ValueError, match="archived"):
            services.extract(
                store, domain="b", value="links to archived",
                rationale_links=[parent["req_id"]],
            )

    def test_cycle_detection_via_transitive_chain(self, store, fake_embedding):
        # A → B → C; trying to create D that derives from A is fine,
        # but trying to make A derive from D would be a cycle. Since
        # extract doesn't expose post-creation linkage editing, we
        # construct the cycle scenario by directly manipulating the
        # store: a pre-existing req whose rationale_links transitively
        # point at an id that would be the new req's deterministic id.
        from loom.store import Requirement
        # Step 1: figure out what new_req_id the about-to-be-extracted
        # req would get, so we can make an existing req link to it.
        import hashlib as _h
        domain = "behavior"
        value = "cycle anchor target"
        new_id = "REQ-" + _h.sha256(f'{domain}:{value}'.encode()).hexdigest()[:8]
        # Step 2: hand-craft an existing req that already links to new_id.
        existing = Requirement(
            id="REQ-cyclesrc",
            domain="behavior",
            value="existing req that links forward",
            source_msg_id="test", source_session="test",
            timestamp="2026-01-01T00:00:00Z",
            rationale="originator",
            rationale_links=[new_id],
        )
        store.add_requirement(existing, fake_embedding)
        # Step 3: try to extract the new req with rationale_links pointing
        # back to REQ-cyclesrc — that closes the loop.
        with pytest.raises(ValueError, match="cycle"):
            services.extract(
                store, domain=domain, value=value,
                rationale_links=["REQ-cyclesrc"],
            )

    def test_self_link_rejected(self, store):
        # The deterministic ID lets us anticipate the new req's id and
        # try to link to itself. The validator must reject.
        import hashlib as _h
        domain = "behavior"
        value = "self-link attempt"
        self_id = "REQ-" + _h.sha256(f'{domain}:{value}'.encode()).hexdigest()[:8]
        with pytest.raises(ValueError, match="itself"):
            services.extract(
                store, domain=domain, value=value,
                rationale_links=[self_id],
            )

    # M12.1 — kind field tests

    def test_default_kind_is_requirement(self, store):
        result = services.extract(
            store, domain="behavior", value="default-kind test", rationale="r",
        )
        assert result["kind"] == "requirement"
        req = store.get_requirement(result["req_id"])
        assert req.kind == "requirement"

    def test_kind_finding_persisted(self, store):
        result = services.extract(
            store, domain="behavior", value="finding-kind test",
            rationale="r", kind="finding",
        )
        assert result["kind"] == "finding"
        req = store.get_requirement(result["req_id"])
        assert req.kind == "finding"

    def test_kind_round_trips_through_store(self, store):
        for k in ("methodology", "hypothesis", "process_rule"):
            result = services.extract(
                store, domain="behavior",
                value=f"{k} value", rationale="r", kind=k,
            )
            req = store.get_requirement(result["req_id"])
            assert req.kind == k, f"kind {k} failed to round-trip"

    def test_invalid_kind_raises(self, store):
        with pytest.raises(ValueError, match="Invalid kind"):
            services.extract(
                store, domain="behavior", value="bad kind",
                rationale="r", kind="not_a_real_kind",
            )

    def test_kind_normalized_to_lowercase(self, store):
        result = services.extract(
            store, domain="behavior", value="case test",
            rationale="r", kind="FINDING",
        )
        assert result["kind"] == "finding"

    def test_existing_reqs_default_to_requirement_kind_on_load(self, store, fake_embedding):
        # Hand-construct a Requirement WITHOUT kind to simulate a
        # pre-M12.1 store. The setdefault in from_dict should assign
        # kind="requirement" on load.
        from loom.store import Requirement
        # Build via from_dict to exercise the setdefault path.
        d = {
            "id": "REQ-legacy",
            "domain": "behavior",
            "value": "legacy req from before M12.1",
            "source_msg_id": "m", "source_session": "s",
            "timestamp": "2026-01-01T00:00:00Z",
        }
        req = Requirement.from_dict(d)
        assert req.kind == "requirement"

    def test_list_filter_by_kind(self, store):
        services.extract(store, domain="behavior", value="r1", rationale="r")
        services.extract(store, domain="behavior", value="f1", rationale="r", kind="finding")
        services.extract(store, domain="behavior", value="m1", rationale="r", kind="methodology")

        all_reqs = services.list_requirements(store)
        assert len(all_reqs) == 3

        only_findings = services.list_requirements(store, kind="finding")
        assert len(only_findings) == 1
        assert only_findings[0]["text"] == "f1"
        assert only_findings[0]["kind"] == "finding"

        only_methodology = services.list_requirements(store, kind="methodology")
        assert len(only_methodology) == 1
        assert only_methodology[0]["text"] == "m1"

    def test_set_kind_reclassifies(self, store):
        result = services.extract(
            store, domain="behavior", value="reclassify test", rationale="r",
        )
        assert result["kind"] == "requirement"
        services.set_kind(store, result["req_id"], "finding")
        req = store.get_requirement(result["req_id"])
        assert req.kind == "finding"

    def test_set_kind_invalid_raises(self, store):
        result = services.extract(
            store, domain="behavior", value="set-kind validation", rationale="r",
        )
        with pytest.raises(ValueError, match="Invalid kind"):
            services.set_kind(store, result["req_id"], "garbage")

    def test_set_kind_unknown_req_raises(self, store):
        with pytest.raises(LookupError):
            services.set_kind(store, "REQ-doesnotexist", "finding")


class TestFindRelatedRequirements:
    """M11.1 — semantic candidate retrieval for rationale linkage."""

    def test_finds_close_match(self, store):
        services.extract(
            store, domain="behavior",
            value="Drift detection should fire when file content has "
                  "diverged from the linked requirement's recorded snapshot.",
            rationale="catch byte-level changes",
        )
        results = services.find_related_requirements(
            store, "report drift when file body changes after linking",
            min_score=-10.0,  # accept any score (hash-fallback embeddings can go negative)  # accept anything for this test
        )
        assert len(results) >= 1
        assert "drift" in results[0]["value"].lower()

    def test_respects_min_score(self, store):
        services.extract(
            store, domain="behavior", value="totally unrelated thing",
            rationale="x",
        )
        results = services.find_related_requirements(
            store, "rate limit the API endpoint",
            min_score=0.99,  # impossibly high
        )
        assert results == []

    def test_excludes_superseded(self, store):
        r = services.extract(
            store, domain="behavior", value="will be superseded soon",
            rationale="x",
        )
        store.supersede_requirement(r["req_id"])
        results = services.find_related_requirements(
            store, "will be superseded soon", min_score=0.0,
        )
        assert all(x["req_id"] != r["req_id"] for x in results)

    def test_excludes_rationale_needed(self, store):
        # A req captured without rationale starts at rationale_needed
        # — those should not be candidates for new rationale linkage
        # (you can't ground a chain in something that itself has no
        # justification).
        r = services.extract(
            store, domain="behavior", value="captured without explanation",
        )
        assert r["status"] == "rationale_needed"
        results = services.find_related_requirements(
            store, "captured without explanation", min_score=0.0,
        )
        assert all(x["req_id"] != r["req_id"] for x in results)

    def test_returns_top_n_only(self, store):
        for i in range(5):
            services.extract(
                store, domain="behavior",
                value=f"requirement number {i} about caching policy",
                rationale="x",
            )
        results = services.find_related_requirements(
            store, "caching policy requirement",
            limit=2, min_score=-10.0,  # hash-fallback scores can be negative
        )
        assert len(results) == 2

    def test_empty_store_returns_empty(self, store):
        results = services.find_related_requirements(
            store, "any text", min_score=0.0,
        )
        assert results == []


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
        from loom.store import generate_impl_id, generate_content_hash
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        f = tmp_path / "x.py"
        body = "# impl\n"
        f.write_text(body)

        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content=body, content_hash=generate_content_hash(body),
            satisfies=[{"req_id": "REQ-x"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        store.supersede_requirement("REQ-x")

        data = services.check(store, str(f))
        assert data["linked"] is True
        assert data["drift_detected"] is True
        assert data["requirements"][0]["drifted"] is True
        # M10.4: superseded signal channel reports what kind of drift
        assert data["drift_signals"]["superseded"] is True
        assert data["drift_signals"]["content"] is False

    def test_drift_signals_returns_zeros_when_unlinked(self, store, tmp_path):
        # M10.4: even unlinked files should expose the signals dict
        # so callers don't have to special-case its absence.
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        data = services.check(store, str(f))
        assert data["drift_signals"] == {
            "content": False, "structural": False, "superseded": False,
        }

    def test_content_drift_detected_when_file_changes(self, store, fake_embedding, tmp_path):
        # M10.4: re-reading the file and re-hashing should catch
        # changes that the existing superseded-only check missed.
        from loom.store import generate_impl_id, generate_content_hash
        _mk_req(store, "REQ-y", "behavior", "y", fake_embedding)
        f = tmp_path / "y.py"
        original = "def foo(): return 1\n"
        f.write_text(original)
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content=original, content_hash=generate_content_hash(original),
            satisfies=[{"req_id": "REQ-y"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)

        # Edit the file underneath the link.
        f.write_text("def foo(): return 2\n")
        data = services.check(store, str(f))
        assert data["drift_signals"]["content"] is True
        assert data["drift_signals"]["superseded"] is False
        assert data["drift_detected"] is True

    def test_no_content_drift_when_file_unchanged(self, store, fake_embedding, tmp_path):
        from loom.store import generate_impl_id, generate_content_hash
        _mk_req(store, "REQ-z", "behavior", "z", fake_embedding)
        f = tmp_path / "z.py"
        body = "def bar(): return 'b'\n"
        f.write_text(body)
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content=body, content_hash=generate_content_hash(body),
            satisfies=[{"req_id": "REQ-z"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        data = services.check(store, str(f))
        assert data["drift_signals"]["content"] is False
        assert data["drift_signals"]["structural"] is False
        assert data["drift_signals"]["superseded"] is False
        assert data["drift_detected"] is False

    def test_structural_drift_via_indexer(self, store, fake_embedding, tmp_path, monkeypatch):
        # M10.4: when an impl carries a symbol_ticket, the registered
        # indexer's signature_of() is consulted for structural drift.
        # We monkey-patch a fake indexer into the registry to drive
        # the path without standing up a real LSP.
        from loom.store import generate_impl_id, generate_content_hash
        from loom import indexers

        class FakeIndexer(indexers.SemanticIndexer):
            name = "fake"
            languages = ("python",)
            sig: str = "after"
            def signature_of(self, ticket):
                return self.sig

        _mk_req(store, "REQ-s", "behavior", "s", fake_embedding)
        f = tmp_path / "s.py"
        body = "def fn(): pass\n"
        f.write_text(body)
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content=body, content_hash=generate_content_hash(body),
            satisfies=[{"req_id": "REQ-s"}],
            timestamp="2026-01-01T00:00:00Z",
            symbol_ticket="loom://py/fn",
            symbol_signature_hash="before",
        )
        store.add_implementation(impl, fake_embedding)

        idx = FakeIndexer()
        indexers.register(idx)
        try:
            data = services.check(store, str(f))
        finally:
            indexers.unregister(idx)

        assert data["drift_signals"]["structural"] is True
        assert data["drift_signals"]["content"] is False
        assert data["drift_detected"] is True

    def test_no_structural_drift_when_signature_matches(self, store, fake_embedding, tmp_path):
        from loom.store import generate_impl_id, generate_content_hash
        from loom import indexers

        class StableIndexer(indexers.SemanticIndexer):
            name = "stable"
            languages = ("python",)
            def signature_of(self, ticket):
                return "stable-sig"

        _mk_req(store, "REQ-q", "behavior", "q", fake_embedding)
        f = tmp_path / "q.py"
        body = "def quux(): pass\n"
        f.write_text(body)
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content=body, content_hash=generate_content_hash(body),
            satisfies=[{"req_id": "REQ-q"}],
            timestamp="2026-01-01T00:00:00Z",
            symbol_ticket="t",
            symbol_signature_hash="stable-sig",
        )
        store.add_implementation(impl, fake_embedding)

        idx = StableIndexer()
        indexers.register(idx)
        try:
            data = services.check(store, str(f))
        finally:
            indexers.unregister(idx)
        assert data["drift_signals"]["structural"] is False
        assert data["drift_signals"]["content"] is False


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

    # ---- M12.6: link_type / evidences ----

    def test_link_default_kind_requirement_is_satisfies(
        self, store, fake_embedding, tmp_path,
    ):
        # kind=requirement (the default) → link_type defaults to satisfies.
        _mk_req(store, "REQ-a", "behavior", "a", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("def a(): pass\n")
        result = services.link(store, str(f), req_ids=["REQ-a"])
        sat = result["satisfies"][0]
        assert sat["link_type"] == "satisfies"

    def test_link_finding_kind_auto_selects_evidences(
        self, store, tmp_path,
    ):
        # kind=finding → link_type defaults to evidences.
        out = services.extract(
            store, domain="experimental",
            value="we measured a 12pp lift", rationale="phS",
            kind="finding",
        )
        f = tmp_path / "phS.json"
        f.write_text("{}")
        result = services.link(store, str(f), req_ids=[out["req_id"]])
        sat = result["satisfies"][0]
        assert sat["link_type"] == "evidences"

    def test_link_hypothesis_kind_auto_selects_evidences(
        self, store, tmp_path,
    ):
        out = services.extract(
            store, domain="experimental",
            value="we expect anti-rationale to underperform",
            rationale="prior", kind="hypothesis",
        )
        f = tmp_path / "design.md"
        f.write_text("# design\n")
        result = services.link(store, str(f), req_ids=[out["req_id"]])
        assert result["satisfies"][0]["link_type"] == "evidences"

    def test_link_methodology_kind_auto_selects_satisfies(
        self, store, tmp_path,
    ):
        # methodology decisions are implemented (e.g. an N=10 harness
        # IS the methodology) — defaults to satisfies, not evidences.
        out = services.extract(
            store, domain="experimental",
            value="use N=10 trials per ablation", rationale="variance",
            kind="methodology",
        )
        f = tmp_path / "harness.py"
        f.write_text("N = 10\n")
        result = services.link(store, str(f), req_ids=[out["req_id"]])
        assert result["satisfies"][0]["link_type"] == "satisfies"

    def test_link_explicit_evidences_overrides_kind_default(
        self, store, fake_embedding, tmp_path,
    ):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        f = tmp_path / "smoke.json"
        f.write_text("{}")
        result = services.link(
            store, str(f), req_ids=["REQ-x"], link_type="evidences",
        )
        sat = result["satisfies"][0]
        assert sat["link_type"] == "evidences"
        # Should warn — evidences against a requirement-kind is unusual.
        assert any("evidences" in w for w in result["warnings"])

    def test_link_explicit_satisfies_overrides_finding_default(
        self, store, tmp_path,
    ):
        out = services.extract(
            store, domain="experimental", value="some finding",
            rationale="r", kind="finding",
        )
        f = tmp_path / "f.py"
        f.write_text("x = 1\n")
        result = services.link(
            store, str(f), req_ids=[out["req_id"]], link_type="satisfies",
        )
        assert result["satisfies"][0]["link_type"] == "satisfies"

    def test_link_invalid_link_type_raises(
        self, store, fake_embedding, tmp_path,
    ):
        _mk_req(store, "REQ-a", "behavior", "a", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("x\n")
        with pytest.raises(ValueError, match="link_type"):
            services.link(
                store, str(f), req_ids=["REQ-a"], link_type="bogus",
            )

    def test_check_surfaces_link_type_per_req(
        self, store, tmp_path,
    ):
        # Link a file as evidence for a finding; check() should
        # report link_type="evidences" so the CLI can render the
        # differentiated drift message.
        out = services.extract(
            store, domain="experimental", value="finding F",
            rationale="r", kind="finding",
        )
        f = tmp_path / "ev.json"
        f.write_text("{}")
        services.link(store, str(f), req_ids=[out["req_id"]])
        data = services.check(store, str(f))
        assert data["linked"] is True
        r = data["requirements"][0]
        assert r["link_type"] == "evidences"
        assert r["kind"] == "finding"

    def test_trace_file_surfaces_link_type(self, store, tmp_path):
        out = services.extract(
            store, domain="experimental", value="finding T",
            rationale="r", kind="finding",
        )
        f = tmp_path / "t.json"
        f.write_text("{}")
        services.link(store, str(f), req_ids=[out["req_id"]])
        data = services.trace(store, str(f))
        assert data["type"] == "file"
        r = data["requirements"][0]
        assert r["link_type"] == "evidences"
        assert r["kind"] == "finding"

    def test_link_back_compat_old_entries_default_to_satisfies(
        self, store, fake_embedding, tmp_path,
    ):
        # Simulate an old-shape entry (no link_type field) by writing
        # an Implementation directly with a satisfies entry that
        # omits link_type — services.check / trace must default to
        # "satisfies" rather than crashing or returning None.
        # M17.1: also use normalize_file_path so the test impl_id
        # matches what services.check now generates on lookup.
        from loom.store import Implementation, generate_content_hash, generate_impl_id
        from loom.paths import normalize_file_path
        _mk_req(store, "REQ-old", "behavior", "old", fake_embedding)
        f = tmp_path / "legacy.py"
        content = "legacy = True\n"
        f.write_text(content)
        stored = normalize_file_path(f)
        impl = Implementation(
            id=generate_impl_id(stored, "all"),
            file=stored,
            lines="all",
            content=content,
            content_hash=generate_content_hash(content),
            timestamp="2025-01-01T00:00:00Z",
            satisfies=[{"req_id": "REQ-old", "req_version": "v1"}],  # no link_type
        )
        store.add_implementation(impl, fake_embedding)
        # check
        data = services.check(store, str(f))
        assert data["requirements"][0]["link_type"] == "satisfies"
        # trace (file branch)
        td = services.trace(store, str(f))
        assert td["requirements"][0]["link_type"] == "satisfies"


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

    def test_kind_paths_empty_when_no_non_default_kinds(self, store, tmp_path):
        # Plain requirement-only store → kind_paths should be empty
        # (REQUIREMENTS.md still emits, but no FINDINGS.md etc).
        services.extract(
            store, domain="behavior", value="just a req", rationale="r",
        )
        result = services.sync(store, str(tmp_path))
        assert result["kind_paths"] == {}
        from pathlib import Path
        assert (Path(tmp_path) / "REQUIREMENTS.md").exists()
        assert not (Path(tmp_path) / "FINDINGS.md").exists()

    def test_kind_paths_emits_findings_md(self, store, tmp_path):
        # Adding a kind=finding req should produce FINDINGS.md.
        services.extract(
            store, domain="behavior", value="finding example",
            rationale="r", kind="finding",
        )
        result = services.sync(store, str(tmp_path))
        from pathlib import Path
        assert "finding" in result["kind_paths"]
        findings_path = Path(result["kind_paths"]["finding"])
        assert findings_path.name == "FINDINGS.md"
        assert findings_path.exists()
        content = findings_path.read_text(encoding="utf-8")
        assert "# Findings" in content
        assert "finding example" in content

    def test_kind_paths_emits_all_non_default_kinds_with_entries(self, store, tmp_path):
        services.extract(store, domain="behavior", value="req", rationale="r")
        services.extract(
            store, domain="behavior", value="find", rationale="r", kind="finding",
        )
        services.extract(
            store, domain="architecture", value="meth", rationale="r",
            kind="methodology",
        )
        services.extract(
            store, domain="behavior", value="hyp", rationale="r",
            kind="hypothesis",
        )
        result = services.sync(store, str(tmp_path))
        assert set(result["kind_paths"]) == {"finding", "methodology", "hypothesis"}
        # process_rule was NOT extracted → no PROCESS-RULES.md.
        assert "process_rule" not in result["kind_paths"]
        from pathlib import Path
        assert not (Path(tmp_path) / "PROCESS-RULES.md").exists()

    def test_provisional_hidden_from_requirements_doc(
        self, store, tmp_path,
    ):
        # M14.3: provisional captures live in the store but stay out
        # of the published REQUIREMENTS.md.
        services.extract(
            store, domain="behavior", value="real requirement", rationale="r",
        )
        services.extract(
            store, domain="behavior", value="provisional one", rationale="r",
            status="provisional",
        )
        services.sync(store, str(tmp_path))
        from pathlib import Path
        content = (Path(tmp_path) / "REQUIREMENTS.md").read_text(encoding="utf-8")
        assert "real requirement" in content
        assert "provisional one" not in content

    def test_provisional_only_kind_does_not_get_per_kind_doc(
        self, store, tmp_path,
    ):
        # M14.3: a kind whose only entries are provisional should NOT
        # produce a per-kind file (same shape as the M12.7c
        # archived-only-kind fix).
        services.extract(
            store, domain="experimental", value="provisional finding",
            rationale="r", kind="finding", status="provisional",
        )
        result = services.sync(store, str(tmp_path))
        assert "finding" not in result["kind_paths"]
        from pathlib import Path
        assert not (Path(tmp_path) / "FINDINGS.md").exists()


class TestListProvisional:
    """M14.4 lite — services.list_provisional surfaces the triage queue."""

    def test_empty_store_returns_empty(self, store):
        assert services.list_provisional(store) == []

    def test_only_provisional_reqs_returned(self, store):
        # Mix: one provisional, one normal. Only the provisional shows.
        services.extract(
            store, domain="behavior", value="real one", rationale="r",
        )
        prov = services.extract(
            store, domain="behavior", value="provisional one", rationale="r",
            status="provisional",
        )
        items = services.list_provisional(store)
        assert len(items) == 1
        assert items[0]["req_id"] == prov["req_id"]
        assert items[0]["status"] == "provisional"

    def test_kind_filter(self, store):
        services.extract(
            store, domain="behavior", value="req prov", rationale="r",
            status="provisional",
        )
        services.extract(
            store, domain="experimental", value="finding prov", rationale="r",
            kind="finding", status="provisional",
        )
        only_req = services.list_provisional(store, kind="requirement")
        only_find = services.list_provisional(store, kind="finding")
        assert len(only_req) == 1
        assert only_req[0]["kind"] == "requirement"
        assert len(only_find) == 1
        assert only_find[0]["kind"] == "finding"

    def test_limit_caps_result(self, store):
        for i in range(5):
            services.extract(
                store, domain="behavior", value=f"prov {i}", rationale="r",
                status="provisional",
            )
        items = services.list_provisional(store, limit=2)
        assert len(items) == 2

    def test_ordered_most_recent_first(self, store):
        import time
        services.extract(
            store, domain="behavior", value="older", rationale="r",
            status="provisional",
        )
        # Sleep so the second extract gets a later timestamp.
        time.sleep(0.01)
        services.extract(
            store, domain="behavior", value="newer", rationale="r",
            status="provisional",
        )
        items = services.list_provisional(store)
        assert items[0]["value"] == "newer"
        assert items[1]["value"] == "older"


class TestDoctorProvisionalWarning:
    """M14.4 lite — doctor warns on a large provisional backlog."""

    def test_no_warning_when_under_threshold(self, store, monkeypatch):
        monkeypatch.setenv("LOOM_PROVISIONAL_BACKLOG_WARN", "10")
        for i in range(3):
            services.extract(
                store, domain="behavior", value=f"prov {i}", rationale="r",
                status="provisional",
            )
        result = services.doctor(store)
        assert result["checks"]["provisional"]["count"] == 3
        assert not any("provisional" in w.lower() for w in result["warnings"])

    def test_warning_fires_when_over_threshold(self, store, monkeypatch):
        monkeypatch.setenv("LOOM_PROVISIONAL_BACKLOG_WARN", "2")
        for i in range(5):
            services.extract(
                store, domain="behavior", value=f"prov {i}", rationale="r",
                status="provisional",
            )
        result = services.doctor(store)
        assert result["checks"]["provisional"]["count"] == 5
        assert result["checks"]["provisional"]["threshold"] == 2
        assert any(
            "provisional" in w.lower() and "triage" in w.lower()
            for w in result["warnings"]
        )


class TestExtractStatusKwarg:
    """M14.3 — services.extract accepts an explicit status."""

    def test_explicit_status_overrides_default(self, store):
        result = services.extract(
            store, domain="behavior", value="x", rationale="r",
            status="provisional",
        )
        req = store.get_requirement(result["req_id"])
        assert req.status == "provisional"

    def test_explicit_status_overrides_rationale_needed(self, store):
        # Without rationale, the default is "rationale_needed". An
        # explicit status= argument should override that too.
        result = services.extract(
            store, domain="behavior", value="x",
            status="provisional",
        )
        req = store.get_requirement(result["req_id"])
        assert req.status == "provisional"

    def test_invalid_status_for_kind_raises(self, store):
        # "in_progress" is requirement-only; not in the finding enum.
        with pytest.raises(ValueError, match="status"):
            services.extract(
                store, domain="experimental", value="x", rationale="r",
                kind="finding", status="in_progress",
            )

    def test_provisional_valid_for_all_kinds(self, store):
        for kind, domain in [
            ("requirement", "behavior"),
            ("finding", "experimental"),
            ("methodology", "experimental"),
            ("hypothesis", "experimental"),
            ("process_rule", "operational"),
        ]:
            result = services.extract(
                store, domain=domain, value=f"x-{kind}", rationale="r",
                kind=kind, status="provisional",
            )
            req = store.get_requirement(result["req_id"])
            assert req.status == "provisional", (
                f"kind={kind} should accept provisional"
            )


class TestM17PathNormalization:
    """M17.1 — abs/rel/mixed-slash inputs all hit the same impl row."""

    def test_link_stores_relative_path(
        self, store, fake_embedding, tmp_path, monkeypatch,
    ):
        # Make tmp_path look like a git project root.
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        sub = tmp_path / "src" / "foo.py"
        sub.parent.mkdir()
        sub.write_text("pass\n")
        # Link via absolute path.
        result = services.link(store, str(sub), req_ids=["REQ-x"])
        # Stored form should be POSIX-relative.
        assert result["file"] == "src/foo.py"
        impl = store.get_implementation(result["impl_id"])
        assert impl.file == "src/foo.py"

    def test_check_via_relative_finds_abs_link(
        self, store, fake_embedding, tmp_path, monkeypatch,
    ):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        # Link with absolute path.
        services.link(store, str(f), req_ids=["REQ-x"])
        # Check with relative path — should find the same impl.
        data = services.check(store, "a.py")
        assert data["linked"] is True
        assert data["requirements"][0]["req_id"] == "REQ-x"

    def test_check_via_abs_finds_rel_link(
        self, store, fake_embedding, tmp_path, monkeypatch,
    ):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        # Link with relative path (cwd is project root).
        services.link(store, "a.py", req_ids=["REQ-x"])
        # Check with absolute — same impl found.
        data = services.check(store, str(f))
        assert data["linked"] is True

    def test_unlink_via_relative_drops_abs_link(
        self, store, fake_embedding, tmp_path, monkeypatch,
    ):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        link_result = services.link(store, str(f), req_ids=["REQ-x"])
        impl_id = link_result["impl_id"]
        result = services.unlink(store, "a.py")
        assert result["unlinked"] is True
        assert store.get_implementation(impl_id) is None

    def test_path_outside_root_stored_absolute(
        self, store, fake_embedding, tmp_path, monkeypatch,
    ):
        # File lives outside the "project root" — store as absolute
        # (the rare cross-repo link case).
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".git").mkdir()
        outside = tmp_path / "elsewhere" / "shared.py"
        outside.parent.mkdir()
        outside.write_text("pass\n")
        monkeypatch.chdir(proj)
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        result = services.link(store, str(outside), req_ids=["REQ-x"])
        # Should still be absolute (POSIX form). The relative path
        # would have ".." which we avoid.
        assert "/" in result["file"]
        assert ".." not in result["file"]
        # Look it up by the same absolute — round-trip.
        data = services.check(store, str(outside))
        assert data["linked"] is True


class TestUnlink:
    """Counterpart to TestLink — covers REQ-81a67c36 affordance."""

    def test_no_impl_returns_unlinked_false_with_warning(self, store, tmp_path):
        f = tmp_path / "ghost.py"
        f.write_text("x = 1\n")
        result = services.unlink(store, str(f))
        assert result["unlinked"] is False
        assert result["deleted"] is False
        assert result["warnings"]

    def test_whole_impl_unlink_removes_row(
        self, store, fake_embedding, tmp_path,
    ):
        _mk_req(store, "REQ-a", "behavior", "a", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("def a(): pass\n")
        link_result = services.link(store, str(f), req_ids=["REQ-a"])
        impl_id = link_result["impl_id"]
        assert store.get_implementation(impl_id) is not None

        result = services.unlink(store, str(f))
        assert result["unlinked"] is True
        assert result["deleted"] is True
        assert result["impl_id"] == impl_id
        assert store.get_implementation(impl_id) is None

    def test_per_req_unlink_keeps_others(
        self, store, fake_embedding, tmp_path,
    ):
        _mk_req(store, "REQ-a", "behavior", "a", fake_embedding)
        _mk_req(store, "REQ-b", "behavior", "b", fake_embedding)
        f = tmp_path / "ab.py"
        f.write_text("def ab(): pass\n")
        link_result = services.link(
            store, str(f), req_ids=["REQ-a", "REQ-b"],
        )
        impl_id = link_result["impl_id"]

        result = services.unlink(store, str(f), req_id="REQ-a")
        assert result["unlinked"] is True
        assert result["deleted"] is False
        remaining = [s["req_id"] for s in result["remaining_satisfies"]]
        assert remaining == ["REQ-b"]
        # Impl row still exists, with the shortened satisfies list.
        impl = store.get_implementation(impl_id)
        assert impl is not None
        assert [s["req_id"] for s in impl.satisfies] == ["REQ-b"]

    def test_per_req_unlink_deletes_when_last(
        self, store, fake_embedding, tmp_path,
    ):
        # Last-req unlink on an impl with no specs/patterns → drop the row.
        _mk_req(store, "REQ-a", "behavior", "a", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("def a(): pass\n")
        link_result = services.link(store, str(f), req_ids=["REQ-a"])
        impl_id = link_result["impl_id"]

        result = services.unlink(store, str(f), req_id="REQ-a")
        assert result["unlinked"] is True
        assert result["deleted"] is True
        assert store.get_implementation(impl_id) is None

    def test_unlink_unknown_req_returns_false_no_mutation(
        self, store, fake_embedding, tmp_path,
    ):
        _mk_req(store, "REQ-a", "behavior", "a", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("def a(): pass\n")
        link_result = services.link(store, str(f), req_ids=["REQ-a"])
        impl_id = link_result["impl_id"]

        result = services.unlink(store, str(f), req_id="REQ-ghost")
        assert result["unlinked"] is False
        assert result["deleted"] is False
        # Impl untouched.
        impl = store.get_implementation(impl_id)
        assert impl is not None
        assert [s["req_id"] for s in impl.satisfies] == ["REQ-a"]


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
        assert result["affected_impls"] == []
        # Verify mutation persisted.
        req = store.get_requirement("REQ-x")
        assert req.superseded_at is not None

    def test_supersede_lists_linked_impls(
        self, store, fake_embedding, tmp_path,
    ):
        # REQ-51455681 closure: supersede should surface the impls that
        # are now orphaned so the user has a punch list.
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        f = tmp_path / "x.py"
        f.write_text("def x(): pass\n")
        services.link(store, str(f), req_ids=["REQ-x"])

        result = services.supersede(store, "REQ-x")
        assert len(result["affected_impls"]) == 1
        impl_info = result["affected_impls"][0]
        # M17.1: stored paths are POSIX-form.
        assert impl_info["file"] == f.as_posix()
        assert impl_info["satisfies_count"] == 1

    def test_supersede_does_not_unlink(
        self, store, fake_embedding, tmp_path,
    ):
        # REQ-51455681: deliberately no auto-unlink. The drift signal
        # is the prompt; the user must act via `loom unlink`.
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        f = tmp_path / "x.py"
        f.write_text("def x(): pass\n")
        link_result = services.link(store, str(f), req_ids=["REQ-x"])
        impl_id = link_result["impl_id"]

        services.supersede(store, "REQ-x")
        # Impl row is still there — the user is supposed to decide
        # whether to unlink, re-link, or leave for drift to surface.
        assert store.get_implementation(impl_id) is not None


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
        # M15: set_status returns an extra `path` key (the fast-forward
        # traversal). pending → implemented walks through in_progress.
        result = services.set_status(
            store, "REQ-x", "implemented", reason="test",
        )
        assert result["req_id"] == "REQ-x"
        assert result["status"] == "implemented"
        assert result["path"] == ["in_progress", "implemented"]
        assert store.get_requirement("REQ-x").status == "implemented"

    # ---- M12.2b: per-kind lifecycle states ----

    def test_finding_accepts_confirmed_status(self, store):
        out = services.extract(
            store, domain="experimental", value="some finding",
            rationale="r", kind="finding",
        )
        result = services.set_status(store, out["req_id"], "confirmed")
        assert result["status"] == "confirmed"
        assert store.get_requirement(out["req_id"]).status == "confirmed"

    def test_finding_rejects_implemented_status(self, store):
        # "implemented" is the requirement-kind enum; not valid for findings.
        out = services.extract(
            store, domain="experimental", value="some finding",
            rationale="r", kind="finding",
        )
        with pytest.raises(ValueError, match="finding"):
            services.set_status(store, out["req_id"], "implemented")

    def test_methodology_accepts_adopted_status(self, store):
        out = services.extract(
            store, domain="experimental", value="use N=10 trials",
            rationale="prior variance", kind="methodology",
        )
        services.set_status(store, out["req_id"], "adopted")
        assert store.get_requirement(out["req_id"]).status == "adopted"

    def test_hypothesis_accepts_falsified_status(self, store):
        out = services.extract(
            store, domain="experimental", value="prediction P",
            rationale="prior result", kind="hypothesis",
        )
        services.set_status(store, out["req_id"], "falsified")
        assert store.get_requirement(out["req_id"]).status == "falsified"

    def test_process_rule_accepts_active_status(self, store):
        out = services.extract(
            store, domain="operational",
            value="all findings retained in github",
            rationale="audit trail", kind="process_rule",
        )
        services.set_status(store, out["req_id"], "active")
        assert store.get_requirement(out["req_id"]).status == "active"

    def test_universal_archived_accepted_for_all_kinds(self, store):
        # archived/superseded/rationale_needed work across kinds.
        for kind, value in [
            ("finding", "f1"), ("methodology", "m1"),
            ("hypothesis", "h1"), ("process_rule", "p1"),
        ]:
            out = services.extract(
                store, domain="experimental", value=value,
                rationale="r", kind=kind,
            )
            services.set_status(store, out["req_id"], "archived")
            assert store.get_requirement(out["req_id"]).status == "archived"

    def test_invalid_status_message_includes_kind(self, store):
        out = services.extract(
            store, domain="experimental", value="some finding",
            rationale="r", kind="finding",
        )
        try:
            services.set_status(store, out["req_id"], "in_progress")
        except ValueError as e:
            msg = str(e)
            assert "finding" in msg
            assert "preliminary" in msg or "confirmed" in msg
        else:
            raise AssertionError("expected ValueError")

    def test_valid_statuses_for_helper(self):
        # Public helper: VALID_STATUSES_BY_KIND is the truth source.
        assert "preliminary" in services.valid_statuses_for("finding")
        assert "implemented" not in services.valid_statuses_for("finding")
        assert "implemented" in services.valid_statuses_for("requirement")
        assert "adopted" in services.valid_statuses_for("methodology")
        assert "active" in services.valid_statuses_for("process_rule")
        # Unknown kind falls back to requirement enum (defensive).
        assert services.valid_statuses_for("zzz") == services.VALID_STATUSES

    def test_extract_initial_status_is_kind_appropriate(self, store):
        # M12.2b: when rationale IS provided, the initial status
        # should reflect the kind, not always "pending".
        f = services.extract(
            store, domain="experimental", value="finding x",
            rationale="r", kind="finding",
        )
        assert store.get_requirement(f["req_id"]).status == "preliminary"

        h = services.extract(
            store, domain="experimental", value="hypothesis x",
            rationale="r", kind="hypothesis",
        )
        assert store.get_requirement(h["req_id"]).status == "proposed"

        m = services.extract(
            store, domain="experimental", value="methodology x",
            rationale="r", kind="methodology",
        )
        assert store.get_requirement(m["req_id"]).status == "proposed"

        # Requirement-kind keeps "pending" — back-compat.
        r = services.extract(
            store, domain="behavior", value="req x", rationale="r",
        )
        assert store.get_requirement(r["req_id"]).status == "pending"

    def test_extract_without_rationale_still_uses_rationale_needed(self, store):
        # Universal rationale_needed marker — kind doesn't change this.
        f = services.extract(
            store, domain="experimental", value="finding y", kind="finding",
        )
        assert store.get_requirement(f["req_id"]).status == "rationale_needed"


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

    def test_duplicate_spec_blocked_by_default(self, store, fake_embedding):
        """A second non-superseded spec under the same req should raise."""
        _mk_req(store, "REQ-d", "behavior", "dup test", fake_embedding)
        first = services.spec_add(store, "REQ-d", "first spec")
        with pytest.raises(services.DuplicateSpecError) as excinfo:
            services.spec_add(store, "REQ-d", "second spec, different path")
        assert len(excinfo.value.siblings) == 1
        assert excinfo.value.siblings[0]["id"] == first["spec_id"]

    def test_duplicate_spec_bypassed_with_force(self, store, fake_embedding):
        _mk_req(store, "REQ-f", "behavior", "force test", fake_embedding)
        services.spec_add(store, "REQ-f", "first spec")
        result = services.spec_add(
            store, "REQ-f", "second spec (forced)", force=True,
        )
        assert result["spec_id"].startswith("SPEC-")
        assert len(result["siblings_bypassed"]) == 1

    def test_superseded_sibling_does_not_block(self, store, fake_embedding):
        """Once the first spec is superseded, a new one is fine."""
        _mk_req(store, "REQ-s", "behavior", "supersede test", fake_embedding)
        first = services.spec_add(store, "REQ-s", "first spec")
        store.supersede_specification(first["spec_id"])
        # No force needed — previous spec isn't a sibling anymore.
        result = services.spec_add(store, "REQ-s", "replacement spec")
        assert result["spec_id"] != first["spec_id"]
        assert result["siblings_bypassed"] == []

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
        from loom.services import _validate_task_proposals
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
        from loom.services import _validate_task_proposals
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
        from loom.store import generate_impl_id
        _mk_req(store, "REQ-a", "behavior", "must do A", fake_embedding)
        _mk_req(store, "REQ-b", "data", "data rule B", fake_embedding)
        f = tmp_path / "a.py"
        f.write_text("pass\n")

        impl = Implementation(
            id=generate_impl_id(str(f), "1-5"),
            file=str(f), lines="1-5",
            content="pass\n", content_hash=generate_content_hash("pass\n"),
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
        from loom.store import generate_impl_id
        _mk_req(store, "REQ-stale", "behavior", "stale rule", fake_embedding)
        f = tmp_path / "x.py"
        f.write_text("pass\n")

        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="pass\n", content_hash=generate_content_hash("pass\n"),
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

    def test_rationale_surfaced_in_context_briefing(self, store, fake_embedding, tmp_path):
        """`context()` must propagate Requirement.rationale to the briefing dict
        so the PreToolUse hook can render it. Without this, agents see only
        the *what* of a requirement, never the *why* — defeating the
        cross-session memory claim."""
        from loom.store import generate_impl_id
        services.extract(
            store, domain="behavior", value="swallow OSError in fetch_with_retry",
            rationale="The retry wrapper in app/backoff_loop.py re-issues on BackoffError; "
                      "raising OSError directly breaks the wrapper contract.",
        )
        # The deterministic ID for this domain+value:
        rid = next(iter(store.list_requirements())).id

        f = tmp_path / "retry.py"
        f.write_text("def fetch_with_retry():\n    pass\n")
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="def fetch_with_retry():\n    pass\n", content_hash=generate_content_hash("def fetch_with_retry():\n    pass\n"),
            satisfies=[{"req_id": rid}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)

        data = services.context(store, str(f))
        assert data["linked"] is True
        assert len(data["requirements"]) == 1
        entry = data["requirements"][0]
        assert "rationale" in entry, "rationale must be in the briefing dict"
        assert entry["rationale"] is not None
        assert "wrapper contract" in entry["rationale"]

    def test_aggregates_across_multiple_impls(self, store, fake_embedding, tmp_path):
        """`check()` wants an exact (file, lines) match; `context()` must not."""
        from loom.store import generate_impl_id
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
        from loom.store import generate_impl_id
        impl = Implementation(
            id=generate_impl_id(impl_id_file, impl_id_lines),
            file=impl_id_file,
            lines=impl_id_lines,
            content="pass\n",
            content_hash=generate_content_hash("pass\n"),
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
    from loom.store import Specification
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


# ---------------------------------------------------------------------------
# M2 — Hygiene (last_referenced + archive + stale)
# ---------------------------------------------------------------------------

class TestLastReferencedTouch:
    """M2.1 — read/link operations stamp last_referenced so the
    requirement records when an agent last engaged with it."""

    def test_query_stamps_last_referenced(self, store, fake_embedding):
        _mk_req(store, "REQ-1", "behavior", "rate-limit logins", fake_embedding)
        before = store.get_requirement("REQ-1").last_referenced
        assert before is None

        services.query(store, "rate-limit", limit=5)

        after = store.get_requirement("REQ-1").last_referenced
        assert after is not None

    def test_check_stamps_for_linked_reqs(self, store, fake_embedding, tmp_path):
        from loom.store import generate_impl_id
        _mk_req(store, "REQ-1", "behavior", "rule", fake_embedding)
        f = tmp_path / "f.py"
        f.write_text("pass\n")
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="pass\n", content_hash=generate_content_hash("pass\n"),
            satisfies=[{"req_id": "REQ-1"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)

        services.check(store, str(f))

        assert store.get_requirement("REQ-1").last_referenced is not None

    def test_trace_by_req_id_stamps(self, store, fake_embedding):
        _mk_req(store, "REQ-2", "behavior", "x", fake_embedding)
        services.trace(store, "REQ-2")
        assert store.get_requirement("REQ-2").last_referenced is not None

    def test_chain_stamps(self, store, fake_embedding):
        _mk_req(store, "REQ-3", "behavior", "x", fake_embedding)
        services.chain(store, "REQ-3")
        assert store.get_requirement("REQ-3").last_referenced is not None

    def test_link_stamps_each_req(self, store, fake_embedding, tmp_path):
        _mk_req(store, "REQ-4", "behavior", "x", fake_embedding)
        f = tmp_path / "g.py"
        f.write_text("pass\n")
        services.link(store, str(f), req_ids=["REQ-4"])
        assert store.get_requirement("REQ-4").last_referenced is not None


class TestArchive:
    """M2.3 — archive sets status, recoverable via set_status."""

    def test_archive_sets_status(self, store, fake_embedding):
        _mk_req(store, "REQ-1", "behavior", "x", fake_embedding)
        result = services.archive(store, "REQ-1")
        assert result["status"] == "archived"
        assert store.get_requirement("REQ-1").status == "archived"

    def test_archive_unknown_raises(self, store):
        with pytest.raises(LookupError):
            services.archive(store, "REQ-ghost")

    def test_archived_excluded_from_list_by_default(self, store, fake_embedding):
        _mk_req(store, "REQ-1", "behavior", "active", fake_embedding)
        _mk_req(store, "REQ-2", "behavior", "deprecated", fake_embedding)
        services.archive(store, "REQ-2")

        ids = {r["id"] for r in services.list_requirements(store)}
        assert ids == {"REQ-1"}

        ids_all = {r["id"] for r in services.list_requirements(
            store, include_archived=True)}
        assert ids_all == {"REQ-1", "REQ-2"}

    def test_archived_excluded_from_query_by_default(self, store, fake_embedding):
        _mk_req(store, "REQ-1", "behavior", "rate limit", fake_embedding)
        _mk_req(store, "REQ-2", "behavior", "old design", fake_embedding)
        services.archive(store, "REQ-2")

        ids = {r["id"] for r in services.query(store, "limit", limit=5)}
        assert "REQ-2" not in ids

    def test_archived_recoverable_via_set_status(self, store, fake_embedding):
        _mk_req(store, "REQ-1", "behavior", "x", fake_embedding)
        services.archive(store, "REQ-1")
        services.set_status(store, "REQ-1", "pending")
        assert store.get_requirement("REQ-1").status == "pending"


class TestAuditRationale:
    """M11.4 — preview the impact of flipping
    LOOM_REQUIRE_RATIONALE_FOR_COMPLETE=1."""

    def _refined(self, store, *, req_id, value, fake_embedding,
                 rationale=None, rationale_links=None):
        from loom.store import Requirement
        req = Requirement(
            id=req_id, domain="behavior", value=value,
            source_msg_id="m", source_session="s",
            timestamp="2026-01-01T00:00:00Z",
            elaboration="how to satisfy this",
            acceptance_criteria=["criterion 1"],
            rationale=rationale,
            rationale_links=rationale_links,
        )
        store.add_requirement(req, fake_embedding)
        return req

    def test_empty_store_returns_zero_counts(self, store):
        out = services.audit_rationale(store)
        assert out["active_total"] == 0
        assert out["would_flip_count"] == 0
        assert out["unaffected"] == 0
        assert out["already_failing"] == 0

    def test_classifies_unaffected_already_failing_and_would_flip(
        self, store, fake_embedding,
    ):
        # Three reqs:
        # - REQ-good: refined + has rationale → unaffected
        # - REQ-flip: refined but NO rationale → would_flip
        # - REQ-bare: no elaboration → already_failing
        from loom.store import Requirement
        self._refined(
            store, req_id="REQ-good", value="g",
            fake_embedding=fake_embedding, rationale="r",
        )
        self._refined(
            store, req_id="REQ-flip", value="f",
            fake_embedding=fake_embedding,
            rationale=None, rationale_links=None,
        )
        bare = Requirement(
            id="REQ-bare", domain="behavior", value="b",
            source_msg_id="m", source_session="s",
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_requirement(bare, fake_embedding)

        out = services.audit_rationale(store)
        assert out["active_total"] == 3
        assert out["unaffected"] == 1
        assert out["already_failing"] == 1
        assert out["would_flip_count"] == 1
        assert out["would_flip"][0]["req_id"] == "REQ-flip"

    def test_links_count_as_rationale(self, store, fake_embedding):
        # A req with rationale_links (and no prose) should NOT be in
        # would_flip — the linkage chain qualifies as rationale.
        self._refined(
            store, req_id="REQ-anchor", value="a",
            fake_embedding=fake_embedding, rationale="origin",
        )
        self._refined(
            store, req_id="REQ-derived", value="d",
            fake_embedding=fake_embedding,
            rationale_links=["REQ-anchor"],
        )
        out = services.audit_rationale(store)
        assert out["would_flip_count"] == 0
        assert out["unaffected"] == 2

    def test_excludes_archived_and_rationale_needed(self, store, fake_embedding):
        # archived and rationale_needed reqs should not appear in any
        # bucket (they're filtered out of "active").
        self._refined(
            store, req_id="REQ-good", value="g",
            fake_embedding=fake_embedding, rationale="r",
        )
        self._refined(
            store, req_id="REQ-arc", value="arc",
            fake_embedding=fake_embedding,
        )
        services.set_status(store, "REQ-arc", "archived")
        # Force a rationale_needed status onto another req.
        self._refined(
            store, req_id="REQ-rn", value="rn",
            fake_embedding=fake_embedding,
        )
        services.set_status(store, "REQ-rn", "rationale_needed")

        out = services.audit_rationale(store)
        assert out["active_total"] == 1  # only REQ-good

    def test_does_not_leak_env_flag(self, store, fake_embedding, monkeypatch):
        # The audit toggles LOOM_REQUIRE_RATIONALE_FOR_COMPLETE
        # internally; it must restore the original value (or
        # absence) on exit.
        import os
        monkeypatch.delenv("LOOM_REQUIRE_RATIONALE_FOR_COMPLETE", raising=False)
        services.audit_rationale(store)
        assert "LOOM_REQUIRE_RATIONALE_FOR_COMPLETE" not in os.environ

        monkeypatch.setenv("LOOM_REQUIRE_RATIONALE_FOR_COMPLETE", "preserved")
        services.audit_rationale(store)
        assert os.environ["LOOM_REQUIRE_RATIONALE_FOR_COMPLETE"] == "preserved"


class TestStale:
    """M2.2 — surface cold/unlinked requirements."""

    def test_never_referenced_ranks_first(self, store, fake_embedding):
        # Both untouched; sort key falls back to creation timestamp.
        # Insert "older" first so it ranks ahead.
        old = Requirement(
            id="REQ-OLD", domain="behavior", value="old",
            source_msg_id="m", source_session="s",
            timestamp="2024-01-01T00:00:00Z",
        )
        new = Requirement(
            id="REQ-NEW", domain="behavior", value="new",
            source_msg_id="m", source_session="s",
            timestamp="2026-04-30T00:00:00Z",
        )
        store.add_requirement(old, fake_embedding)
        store.add_requirement(new, fake_embedding)

        rows = services.stale(store)
        assert [r["id"] for r in rows] == ["REQ-OLD", "REQ-NEW"]
        assert all(r["last_referenced"] is None for r in rows)

    def test_older_than_filter(self, store, fake_embedding):
        # 2024 → very old; 2026-04-30 → today; older_than=180 keeps only old.
        old = Requirement(
            id="REQ-OLD", domain="behavior", value="old",
            source_msg_id="m", source_session="s",
            timestamp="2024-01-01T00:00:00Z",
        )
        new = Requirement(
            id="REQ-NEW", domain="behavior", value="new",
            source_msg_id="m", source_session="s",
            timestamp="2026-04-29T00:00:00Z",
        )
        store.add_requirement(old, fake_embedding)
        store.add_requirement(new, fake_embedding)

        rows = services.stale(store, older_than_days=180)
        assert [r["id"] for r in rows] == ["REQ-OLD"]

    def test_unlinked_only_filter(self, store, fake_embedding, tmp_path):
        from loom.store import generate_impl_id
        _mk_req(store, "REQ-LINKED", "behavior", "x", fake_embedding)
        _mk_req(store, "REQ-ORPHAN", "behavior", "y", fake_embedding)

        f = tmp_path / "g.py"
        f.write_text("pass\n")
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="pass\n", content_hash=generate_content_hash("pass\n"),
            satisfies=[{"req_id": "REQ-LINKED"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)

        rows = services.stale(store, unlinked_only=True)
        ids = [r["id"] for r in rows]
        assert "REQ-ORPHAN" in ids
        assert "REQ-LINKED" not in ids

    def test_archived_excluded_by_default(self, store, fake_embedding):
        _mk_req(store, "REQ-1", "behavior", "x", fake_embedding)
        _mk_req(store, "REQ-2", "behavior", "y", fake_embedding)
        services.archive(store, "REQ-2")

        ids = {r["id"] for r in services.stale(store)}
        assert ids == {"REQ-1"}

    def test_superseded_always_excluded(self, store, fake_embedding):
        _mk_req(store, "REQ-A", "behavior", "rate limit", fake_embedding)
        _mk_req(store, "REQ-B", "behavior", "rate limit v2", fake_embedding)
        store.supersede_requirement("REQ-A")

        ids = [r["id"] for r in services.stale(store)]
        assert "REQ-A" not in ids


class TestLinkSymbol:
    """M10.1 — services.link(symbol=...) routes through the registered
    SemanticIndexer. Most behavior is shape-checking the error paths;
    the happy path is exercised with a fake indexer."""

    @pytest.fixture(autouse=True)
    def clean_indexer_registry(self):
        from loom import indexers
        snapshot = list(indexers._INDEXERS)
        indexers._INDEXERS.clear()
        yield
        indexers._INDEXERS.clear()
        indexers._INDEXERS.extend(snapshot)

    def test_symbol_without_language_raises(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        with pytest.raises(ValueError, match="requires language"):
            services.link(store, symbol="app::commit", req_ids=["REQ-x"])

    def test_no_indexer_registered_raises_with_actionable_message(self, store, fake_embedding):
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        with pytest.raises(ValueError, match="no SemanticIndexer registered"):
            services.link(store, symbol="app::commit", language="c++",
                          req_ids=["REQ-x"])

    def test_indexer_returns_none_raises(self, store, fake_embedding):
        from loom import indexers

        class CantResolve(indexers.SemanticIndexer):
            name = "cant"
            languages = ("python",)
            # resolve_symbol returns None per the abstract default.

        indexers.register(CantResolve())
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)
        with pytest.raises(ValueError, match="could not resolve"):
            services.link(store, symbol="app::missing", language="python",
                          req_ids=["REQ-x"])

    def test_no_file_no_symbol_raises(self, store):
        with pytest.raises(ValueError, match="file_path or symbol"):
            services.link(store, req_ids=["REQ-x"])

    def test_symbol_happy_path_persists_ticket(self, store, fake_embedding, tmp_path):
        """Fake indexer resolves a symbol; resulting Implementation
        carries the ticket + signature_hash forward."""
        from loom import indexers

        f = tmp_path / "app.py"
        f.write_text("def commit():\n    pass\n")

        class FakePy(indexers.SemanticIndexer):
            name = "fake-py"
            languages = ("python",)
            def resolve_symbol(self, ref):
                return indexers.SymbolHit(
                    ticket=f"fake://{ref}",
                    file=f,
                    byte_range=(0, len(f.read_text())),
                    signature_hash="sig:test",
                )

        indexers.register(FakePy())
        _mk_req(store, "REQ-x", "behavior", "x", fake_embedding)

        result = services.link(
            store, symbol="app::commit", language="python",
            req_ids=["REQ-x"],
        )
        assert result["linked"] is True
        # M17.1: stored paths are POSIX-form, regardless of platform.
        assert result["file"] == f.as_posix()

        impl = store.get_implementation(result["impl_id"])
        assert impl.symbol_ticket == "fake://app::commit"
        assert impl.symbol_signature_hash == "sig:test"


# ---------------------------------------------------------------------------
# M5 — Metrics & Effectiveness
# ---------------------------------------------------------------------------

class TestEventRecording:
    """M5.1 — extract / link / check / conflicts append typed events."""

    def _read_events(self, store):
        import json as _json
        path = store.data_dir / services.EVENTS_FILENAME
        if not path.exists():
            return []
        return [_json.loads(line) for line in path.read_text().splitlines() if line]

    def test_extract_logs_requirement_extracted(self, store):
        services.extract(store, domain="behavior", value="rate limit")
        events = self._read_events(store)
        types = [e["event"] for e in events]
        assert "requirement_extracted" in types

    def test_extract_logs_rationale_flag(self, store):
        services.extract(
            store, domain="behavior", value="x",
            rationale="prevent abuse",
        )
        events = self._read_events(store)
        ext = [e for e in events if e["event"] == "requirement_extracted"][0]
        assert ext["has_rationale"] is True

    def test_link_logs_implementation_linked_per_req(self, store, fake_embedding, tmp_path):
        _mk_req(store, "REQ-1", "behavior", "x", fake_embedding)
        _mk_req(store, "REQ-2", "behavior", "y", fake_embedding)
        f = tmp_path / "f.py"
        f.write_text("pass\n")
        services.link(store, str(f), req_ids=["REQ-1", "REQ-2"])

        events = self._read_events(store)
        linked = [e for e in events if e["event"] == "implementation_linked"]
        assert {e["req_id"] for e in linked} == {"REQ-1", "REQ-2"}

    def test_check_logs_drift_detected_when_drifted(self, store, fake_embedding, tmp_path):
        from loom.store import generate_impl_id
        _mk_req(store, "REQ-1", "behavior", "x", fake_embedding)
        f = tmp_path / "f.py"
        f.write_text("pass\n")
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="pass\n", content_hash=generate_content_hash("pass\n"),
            satisfies=[{"req_id": "REQ-1"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        store.supersede_requirement("REQ-1")

        services.check(store, str(f))
        events = self._read_events(store)
        types = [e["event"] for e in events]
        assert "drift_detected" in types
        assert "check_clean" not in types

    def test_check_logs_check_clean_when_no_drift(self, store, fake_embedding, tmp_path):
        from loom.store import generate_impl_id
        _mk_req(store, "REQ-1", "behavior", "x", fake_embedding)
        f = tmp_path / "f.py"
        f.write_text("pass\n")
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="pass\n", content_hash=generate_content_hash("pass\n"),
            satisfies=[{"req_id": "REQ-1"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)

        services.check(store, str(f))
        events = self._read_events(store)
        types = [e["event"] for e in events]
        assert "check_clean" in types
        assert "drift_detected" not in types


class TestMetrics:
    """M5.2 — services.metrics aggregates events + store state."""

    def test_empty_store_returns_zeros(self, store):
        m = services.metrics(store)
        assert m["requirements"]["total"] == 0
        assert m["coverage"]["with_impls_pct"] == 0.0
        assert m["activity"]["extracted"] == 0
        assert m["staleness"]["never"] == 0

    def test_requirements_buckets(self, store, fake_embedding):
        _mk_req(store, "REQ-1", "behavior", "active", fake_embedding)
        _mk_req(store, "REQ-2", "behavior", "old", fake_embedding)
        _mk_req(store, "REQ-3", "behavior", "deprecated", fake_embedding)
        store.supersede_requirement("REQ-2")
        services.archive(store, "REQ-3")

        m = services.metrics(store)
        r = m["requirements"]
        assert r["total"] == 3
        assert r["active"] == 1
        assert r["superseded"] == 1
        assert r["archived"] == 1

    # ---- M12.7: per-kind metrics rollup ----

    def test_metrics_by_kind_rollup(self, store):
        # Mix kinds: 2 reqs, 1 finding (confirmed), 1 process_rule.
        services.extract(store, domain="behavior", value="r1", rationale="r")
        services.extract(store, domain="behavior", value="r2", rationale="r")
        f = services.extract(
            store, domain="experimental", value="finding 1",
            rationale="r", kind="finding",
        )
        services.set_status(store, f["req_id"], "confirmed")
        services.extract(
            store, domain="operational", value="rule 1",
            rationale="r", kind="process_rule",
        )

        m = services.metrics(store)
        bk = m["requirements"]["by_kind"]
        assert bk["requirement"]["total"] == 2
        assert bk["finding"]["total"] == 1
        assert bk["finding"]["active"] == 1
        assert bk["finding"]["by_status"]["confirmed"] == 1
        assert bk["process_rule"]["total"] == 1
        # Coverage denominator is requirement-only (M12.7).
        assert m["coverage"]["denominator"] == 2
        assert m["coverage"]["scope"] == "kind=requirement"

    def test_metrics_coverage_denominator_excludes_findings(
        self, store, fake_embedding, tmp_path,
    ):
        from loom.store import generate_impl_id
        # 1 requirement WITH impl + 2 findings WITHOUT impls.
        _mk_req(store, "REQ-real", "behavior", "linked", fake_embedding)
        services.extract(
            store, domain="experimental", value="f1",
            rationale="r", kind="finding",
        )
        services.extract(
            store, domain="experimental", value="f2",
            rationale="r", kind="finding",
        )
        f = tmp_path / "f.py"
        f.write_text("pass\n")
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="pass\n", content_hash=generate_content_hash("pass\n"),
            satisfies=[{"req_id": "REQ-real"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)

        m = services.metrics(store)
        # Pre-M12.7 this would have been 1/3 = 33.3%; post-M12.7 it's
        # 1/1 = 100% because the 2 findings don't dilute the denominator.
        assert m["coverage"]["with_impls"] == 1
        assert m["coverage"]["denominator"] == 1
        assert m["coverage"]["with_impls_pct"] == 100.0

    def test_coverage_with_impls(self, store, fake_embedding, tmp_path):
        from loom.store import generate_impl_id
        _mk_req(store, "REQ-A", "behavior", "linked", fake_embedding)
        _mk_req(store, "REQ-B", "behavior", "orphan", fake_embedding)

        f = tmp_path / "f.py"
        f.write_text("pass\n")
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="pass\n", content_hash=generate_content_hash("pass\n"),
            satisfies=[{"req_id": "REQ-A"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)

        m = services.metrics(store)
        assert m["coverage"]["with_impls"] == 1
        assert m["coverage"]["with_impls_pct"] == 50.0

    def test_drift_ratio_from_check_events(self, store, fake_embedding, tmp_path):
        from loom.store import generate_impl_id
        _mk_req(store, "REQ-1", "behavior", "x", fake_embedding)

        f = tmp_path / "f.py"
        f.write_text("pass\n")
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="pass\n", content_hash=generate_content_hash("pass\n"),
            satisfies=[{"req_id": "REQ-1"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)

        # 1 clean check
        services.check(store, str(f))
        # supersede → drift
        store.supersede_requirement("REQ-1")
        services.check(store, str(f))

        m = services.metrics(store)
        assert m["drift"]["events"] == 1
        assert m["drift"]["clean_checks"] == 1
        assert m["drift"]["drift_ratio_pct"] == 50.0

    def test_activity_counts_extract_and_link(self, store, fake_embedding, tmp_path):
        services.extract(store, domain="behavior", value="x")
        services.extract(store, domain="behavior", value="y")
        # link the first req
        rid = next(iter(store.list_requirements())).id
        f = tmp_path / "f.py"
        f.write_text("pass\n")
        services.link(store, str(f), req_ids=[rid])

        m = services.metrics(store)
        assert m["activity"]["extracted"] == 2
        assert m["activity"]["linked"] == 1

    def test_since_days_clips_window(self, store, fake_embedding):
        # Hand-write a 2-event log with one historical and one fresh
        # entry; that lets us test the clip without sleeping.
        import json as _json
        from datetime import datetime, timezone
        path = store.data_dir / services.EVENTS_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        old = {"event": "requirement_extracted",
               "ts": "2024-01-01T00:00:00+00:00"}
        recent = {"event": "requirement_extracted",
                  "ts": datetime.now(timezone.utc).isoformat()}
        path.write_text(_json.dumps(old) + "\n" + _json.dumps(recent) + "\n",
                        encoding="utf-8")

        m_all = services.metrics(store)
        m_recent = services.metrics(store, since_days=30)
        assert m_all["activity"]["extracted"] == 2
        assert m_recent["activity"]["extracted"] == 1


class TestHealthScore:
    """M5.3 — single 0-100 score over coverage + freshness + drift."""

    def test_empty_store_returns_zero(self, store):
        h = services.health_score(store)
        assert h["score"] == 0
        assert h["active_requirements"] == 0

    def test_perfect_score_with_full_coverage(self, store, fake_embedding, tmp_path):
        from loom.store import generate_impl_id, Requirement
        from loom.testspec import TestSpecStore, TestSpec

        # M11.3: active reqs need rationale to score on the
        # rationale_coverage axis. Add it directly to the seed req.
        req = Requirement(
            id="REQ-1", domain="behavior", value="x",
            source_msg_id="m1", source_session="s1",
            timestamp="2026-01-01T00:00:00Z",
            rationale="prevent abuse",
        )
        store.add_requirement(req, fake_embedding)
        # Touch to mark as fresh.
        store.touch_requirement("REQ-1")

        # Linked impl.
        f = tmp_path / "f.py"
        f.write_text("pass\n")
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="pass\n", content_hash=generate_content_hash("pass\n"),
            satisfies=[{"req_id": "REQ-1"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)

        # Test spec.
        ts = TestSpecStore(store.data_dir)
        ts.add_spec(TestSpec(
            req_id="REQ-1", description="d", steps=["s"],
            expected="ok", automated=False,
        ))

        h = services.health_score(store)
        assert h["score"] == 100
        assert h["components"]["impl_coverage"] == 100.0
        assert h["components"]["test_coverage"] == 100.0
        assert h["components"]["freshness"] == 100.0
        # No checks recorded → non_drift defaults to 100.
        assert h["components"]["non_drift"] == 100.0
        # M11.3: rationale present → rationale_coverage = 100.
        assert h["components"]["rationale_coverage"] == 100.0

    def test_no_coverage_no_freshness_drops_score(self, store, fake_embedding):
        _mk_req(store, "REQ-1", "behavior", "x", fake_embedding)
        # Never touched, no impl, no test, no rationale.
        h = services.health_score(store)
        # M11.3: 5-component avg now. impl=0, test=0, freshness=0,
        # non_drift=100, rationale=0 → avg = 20.
        assert h["score"] == 20

    # M11.3 — rationale_coverage component

    def test_rationale_coverage_full_when_all_have_prose(self, store):
        services.extract(store, domain="behavior", value="A", rationale="r1")
        services.extract(store, domain="behavior", value="B", rationale="r2")
        h = services.health_score(store)
        assert h["components"]["rationale_coverage"] == 100.0

    def test_rationale_coverage_full_when_all_have_links(self, store):
        a = services.extract(store, domain="behavior", value="anchor", rationale="origin")
        services.extract(
            store, domain="behavior", value="derived",
            rationale_links=[a["req_id"]],
        )
        h = services.health_score(store)
        assert h["components"]["rationale_coverage"] == 100.0

    def test_rationale_coverage_zero_when_none_have_either(self, store, fake_embedding):
        _mk_req(store, "REQ-1", "behavior", "x", fake_embedding)
        h = services.health_score(store)
        assert h["components"]["rationale_coverage"] == 0.0

    def test_rationale_coverage_partial_split(self, store, fake_embedding):
        # 1 of 2 active reqs has rationale → 50.0%.
        _mk_req(store, "REQ-1", "behavior", "no rationale", fake_embedding)
        services.extract(store, domain="behavior", value="has rationale", rationale="r")
        h = services.health_score(store)
        assert h["components"]["rationale_coverage"] == 50.0

    def test_rationale_needed_excluded_from_active(self, store, fake_embedding):
        # rationale_needed reqs must NOT count in the active denominator.
        # Create one bare req and one with rationale; the bare one will
        # be `rationale_needed` because services.extract defaults
        # to that status when no rationale source is provided.
        bare = services.extract(store, domain="behavior", value="bare requirement")
        assert bare["status"] == "rationale_needed"
        services.extract(store, domain="behavior", value="grounded", rationale="r")

        h = services.health_score(store)
        # Only the grounded req counts as active → rationale_coverage 100%.
        assert h["active_requirements"] == 1
        assert h["components"]["rationale_coverage"] == 100.0

    def test_score_formula_is_5_component_average(self, store, fake_embedding):
        # Hand-construct a state where each component lands at a
        # known value, then verify the score is the 5-way mean.
        services.extract(store, domain="behavior", value="anchor", rationale="r")
        # Components for this single req in a virgin store:
        #   impl_coverage = 0   (no Implementation linked)
        #   test_coverage = 0   (no TestSpec)
        #   freshness     = 0   (last_referenced is None)
        #   non_drift     = 100 (no checks recorded)
        #   rationale_coverage = 100 (it has prose rationale)
        # → mean = (0+0+0+100+100)/5 = 40
        h = services.health_score(store)
        assert h["components"]["rationale_coverage"] == 100.0
        assert h["components"]["non_drift"] == 100.0
        assert h["score"] == 40

    # ---- M12.7: kind-aware coverage signals ----

    def test_findings_dont_dilute_impl_coverage(
        self, store, fake_embedding, tmp_path,
    ):
        from loom.store import generate_impl_id
        # 1 requirement WITH impl + 3 findings WITHOUT impls.
        # Pre-M12.7 this would have made impl_coverage = 25%; after
        # M12.7 it's 100% because findings don't have impls.
        _mk_req(store, "REQ-1", "behavior", "x", fake_embedding)
        store.touch_requirement("REQ-1")
        f = tmp_path / "f.py"
        f.write_text("pass\n")
        impl = Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="pass\n", content_hash=generate_content_hash("pass\n"),
            satisfies=[{"req_id": "REQ-1"}],
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_implementation(impl, fake_embedding)
        for i in range(3):
            services.extract(
                store, domain="experimental", value=f"finding {i}",
                rationale="r", kind="finding",
            )
        h = services.health_score(store)
        assert h["components"]["impl_coverage"] == 100.0
        # active_requirement_kind reflects the requirement-only count.
        assert h["active_requirement_kind"] == 1

    def test_findings_only_store_impl_coverage_is_100(self, store):
        # No requirement-kind reqs at all — impl_coverage and
        # test_coverage should be 100 (no signal == no degradation),
        # not 0 (which would penalize a research-only store).
        services.extract(
            store, domain="experimental", value="finding A",
            rationale="r", kind="finding",
        )
        services.extract(
            store, domain="experimental", value="finding B",
            rationale="r", kind="finding",
        )
        h = services.health_score(store)
        assert h["components"]["impl_coverage"] == 100.0
        assert h["components"]["test_coverage"] == 100.0
        assert h["active_requirement_kind"] == 0

    def test_score_components_dict_has_5_keys(self, store):
        h = services.health_score(store)
        assert set(h["components"].keys()) == {
            "impl_coverage", "test_coverage", "freshness",
            "non_drift", "rationale_coverage",
        }


class TestIndexerDoctor:
    """M10.5 — `loom indexer-doctor` health check for the indexer pipeline."""

    def _clear_indexers(self):
        """Drop any indexers registered by other tests (registry is
        process-global)."""
        from loom import indexers
        for ix in list(indexers.registered()):
            indexers.unregister(ix)

    def test_no_indexers_reports_warning(self, store):
        self._clear_indexers()
        d = services.indexer_doctor(store)
        assert d["ok"] is False
        assert d["indexer_count"] == 0
        assert d["has_real_indexer"] is False
        assert any("No real indexer" in w for w in d["warnings"])

    def test_real_indexer_passes_when_healthy(self, store):
        from loom import indexers
        self._clear_indexers()

        class FakeIndexer(indexers.SemanticIndexer):
            name = "fake"
            languages = ("python",)
            def health(self):
                return {"ok": True, "detail": "fixture indexer"}

        ix = FakeIndexer()
        indexers.register(ix)
        try:
            d = services.indexer_doctor(store)
        finally:
            indexers.unregister(ix)

        assert d["ok"] is True
        assert d["has_real_indexer"] is True
        assert d["indexer_count"] == 1
        assert d["indexers"][0]["name"] == "fake"
        assert d["indexers"][0]["health"]["ok"] is True
        assert d["warnings"] == []

    def test_unhealthy_indexer_fails_overall(self, store):
        from loom import indexers
        self._clear_indexers()

        class BrokenIndexer(indexers.SemanticIndexer):
            name = "broken"
            languages = ("python",)
            def health(self):
                return {"ok": False, "detail": "binary missing"}

        ix = BrokenIndexer()
        indexers.register(ix)
        try:
            d = services.indexer_doctor(store)
        finally:
            indexers.unregister(ix)

        assert d["ok"] is False
        assert d["indexers"][0]["health"]["ok"] is False
        assert any("unhealthy" in w for w in d["warnings"])

    def test_health_method_raising_does_not_crash_doctor(self, store):
        from loom import indexers
        self._clear_indexers()

        class FlakyIndexer(indexers.SemanticIndexer):
            name = "flaky"
            languages = ("python",)
            def health(self):
                raise RuntimeError("network down")

        ix = FlakyIndexer()
        indexers.register(ix)
        try:
            d = services.indexer_doctor(store)
        finally:
            indexers.unregister(ix)
        assert d["ok"] is False
        assert "raised" in d["indexers"][0]["health"]["detail"]

    def test_symbol_linked_impls_counted_by_language(self, store, fake_embedding, tmp_path):
        from loom.store import generate_impl_id
        from loom import indexers
        self._clear_indexers()

        class JsFake(indexers.SemanticIndexer):
            name = "js-fake"
            languages = ("javascript",)
        indexers.register(JsFake())

        _mk_req(store, "REQ-a", "behavior", "a", fake_embedding)
        f1 = tmp_path / "a.js"
        f1.write_text("//\n")
        f2 = tmp_path / "b.js"
        f2.write_text("//\n")
        for f in (f1, f2):
            store.add_implementation(Implementation(
                id=generate_impl_id(str(f), "all"),
                file=str(f), lines="all",
                content="//\n", content_hash=generate_content_hash("//\n"),
                satisfies=[{"req_id": "REQ-a"}],
                timestamp="2026-01-01T00:00:00Z",
                symbol_ticket=f"loom://js/{f.stem}",
                symbol_signature_hash="sig",
            ), fake_embedding)

        try:
            d = services.indexer_doctor(store)
        finally:
            self._clear_indexers()
        assert d["symbol_linked_impls"]["total"] == 2
        assert d["symbol_linked_impls"]["by_language"]["javascript"] == 2
        assert d["symbol_linked_impls"]["uncovered_by_language"] == {}

    def test_symbol_linked_impls_without_indexer_warn(self, store, fake_embedding, tmp_path):
        # Symbol-linked impl exists but no indexer covers its language —
        # structural drift channel is silently broken for that impl.
        from loom.store import generate_impl_id
        self._clear_indexers()

        _mk_req(store, "REQ-z", "behavior", "z", fake_embedding)
        f = tmp_path / "x.go"
        f.write_text("package x\n")
        store.add_implementation(Implementation(
            id=generate_impl_id(str(f), "all"),
            file=str(f), lines="all",
            content="package x\n",
            content_hash=generate_content_hash("package x\n"),
            satisfies=[{"req_id": "REQ-z"}],
            timestamp="2026-01-01T00:00:00Z",
            symbol_ticket="loom://go/X",
            symbol_signature_hash="sig",
        ), fake_embedding)

        d = services.indexer_doctor(store)
        assert d["symbol_linked_impls"]["uncovered_by_language"] == {"go": 1}
        assert any(
            "no registered indexer" in w for w in d["warnings"]
        )
        assert d["ok"] is False  # uncovered impls fail overall
