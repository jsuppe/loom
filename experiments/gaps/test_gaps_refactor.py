"""
Grading test for the VERY HARD task: behavior-preserving refactor of gaps().

Target: split services.gaps() into 4 private detector helpers
(_detect_missing_criteria, _detect_missing_elaboration, _detect_orphan_impl,
_detect_drift). Each helper is module-level, takes store, returns a list
of gap dicts of its type. gaps() becomes a thin orchestrator.

This test enforces TWO classes of correctness:
  1. BEHAVIOR — all 20 cases from test_gaps_extend.py must still pass,
     verifying no regressions from the refactor.
  2. STRUCTURE — the 4 helpers must exist, be callable, and produce the
     correct gap type in isolation. This prevents the model from
     "refactoring" by renaming without actually splitting.
"""
from __future__ import annotations

import sys
import tempfile
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

import embedding  # noqa: E402
import services  # noqa: E402
from store import LoomStore, Requirement, Implementation, generate_impl_id  # noqa: E402


FAKE_EMBEDDING = [0.1] * 768


@pytest.fixture
def store():
    tmp = Path(tempfile.mkdtemp())
    s = LoomStore(project="test-gaps-refactor", data_dir=tmp)
    yield s
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(autouse=True)
def force_fallback_embedding(monkeypatch):
    embedding._embedding_cache.clear()

    def boom(*a, **kw):
        raise ConnectionResetError("no ollama in experiment")

    monkeypatch.setattr(embedding.urllib.request, "urlopen", boom)


def _mk_req(store, req_id, value="placeholder", elaboration=None, criteria=None):
    req = Requirement(
        id=req_id, domain="behavior", value=value,
        source_msg_id="m1", source_session="s1",
        timestamp="2026-01-01T00:00:00Z",
        elaboration=elaboration, acceptance_criteria=criteria,
    )
    store.add_requirement(req, FAKE_EMBEDDING)
    return req


def _mk_impl(store, file, lines, satisfies_req_ids):
    impl = Implementation(
        id=generate_impl_id(file, lines),
        file=file, lines=lines,
        content="pass\n", content_hash="h",
        satisfies=[{"req_id": r} for r in satisfies_req_ids],
        timestamp="2026-01-01T00:00:00Z",
    )
    store.add_implementation(impl, FAKE_EMBEDDING)
    return impl


# ===================================================================
# BEHAVIOR — 20 no-regression cases (copied from test_gaps_extend.py)
# ===================================================================


def test_gaps_is_callable():
    assert hasattr(services, "gaps")
    assert callable(services.gaps)


def test_missing_criteria_surfaced(store):
    _mk_req(store, "REQ-nc", elaboration="some elaboration text")
    gaps = services.gaps(store)
    assert any(g["type"] == "missing_criteria" and g["entity_id"] == "REQ-nc" for g in gaps)


def test_missing_elaboration_surfaced(store):
    _mk_req(store, "REQ-ne", criteria=["criterion one"])
    gaps = services.gaps(store)
    assert any(g["type"] == "missing_elaboration" and g["entity_id"] == "REQ-ne" for g in gaps)


def test_orphan_impl_surfaced(store):
    _mk_impl(store, "/tmp/a.py", "1-5", ["REQ-does-not-exist"])
    gaps = services.gaps(store)
    assert any(g["type"] == "orphan_impl" for g in gaps)


def test_impl_with_any_live_req_is_not_orphan(store):
    _mk_req(store, "REQ-live", elaboration="x", criteria=["c"])
    _mk_req(store, "REQ-dead", elaboration="x", criteria=["c"])
    store.supersede_requirement("REQ-dead")
    _mk_impl(store, "/tmp/c.py", "1-5", ["REQ-live", "REQ-dead"])
    gaps = services.gaps(store)
    orphans = [g for g in gaps if g["type"] == "orphan_impl"]
    assert orphans == []


def test_uniform_shape(store):
    _mk_req(store, "REQ-a")
    _mk_impl(store, "/tmp/d.py", "1-5", ["REQ-missing"])
    gaps = services.gaps(store)
    required = {"type", "entity_id", "description", "blocks", "suggested_action"}
    assert gaps
    for g in gaps:
        assert set(g.keys()) >= required
        for k in required:
            assert g[k] is not None
        assert isinstance(g["blocks"], list)
        assert isinstance(g["suggested_action"], str)
        assert g["suggested_action"].strip()


def test_ordering_by_priority(store):
    _mk_req(store, "REQ-crit", elaboration="has elab")
    _mk_req(store, "REQ-elab", criteria=["c1"])
    _mk_impl(store, "/tmp/e.py", "1-5", ["REQ-absent"])
    gaps = services.gaps(store)
    order = [g["type"] for g in gaps]
    if "missing_criteria" in order and "missing_elaboration" in order:
        assert order.index("missing_criteria") < order.index("missing_elaboration")
    if "missing_elaboration" in order and "orphan_impl" in order:
        assert order.index("missing_elaboration") < order.index("orphan_impl")


def test_tie_break_by_entity_id(store):
    _mk_req(store, "REQ-b", elaboration="e")
    _mk_req(store, "REQ-a", elaboration="e")
    gaps = services.gaps(store)
    mc = [g for g in gaps if g["type"] == "missing_criteria"]
    assert [g["entity_id"] for g in mc] == sorted(g["entity_id"] for g in mc)


def test_type_filter(store):
    _mk_req(store, "REQ-x")
    _mk_impl(store, "/tmp/f.py", "1-5", ["REQ-absent"])
    only_orphan = services.gaps(store, types=["orphan_impl"])
    assert all(g["type"] == "orphan_impl" for g in only_orphan)


def test_limit_cap(store):
    for i in range(5):
        _mk_req(store, f"REQ-{i:02d}", elaboration="e")
    gaps = services.gaps(store, limit=3)
    assert len(gaps) <= 3


def test_superseded_reqs_excluded_from_req_level_gaps(store):
    _mk_req(store, "REQ-sup")
    store.supersede_requirement("REQ-sup")
    gaps = services.gaps(store)
    bad = [g for g in gaps
           if g["entity_id"] == "REQ-sup"
           and g["type"] in {"missing_criteria", "missing_elaboration"}]
    assert bad == []


def test_empty_store_returns_empty_list(store):
    assert services.gaps(store) == []


def test_complete_reqs_do_not_surface(store):
    _mk_req(store, "REQ-ok", elaboration="fully elaborated", criteria=["c1", "c2"])
    gaps = services.gaps(store)
    related = [g for g in gaps if g["entity_id"] == "REQ-ok"]
    assert related == []


def test_impl_with_superseded_req_is_orphan(store):
    _mk_req(store, "REQ-old", elaboration="x", criteria=["c"])
    store.supersede_requirement("REQ-old")
    _mk_impl(store, "/tmp/b.py", "1-5", ["REQ-old"])
    gaps = services.gaps(store)
    assert any(g["type"] == "orphan_impl" for g in gaps)


def test_drift_type_exists(store):
    _mk_req(store, "REQ-drifted", elaboration="x", criteria=["c"])
    _mk_impl(store, "/tmp/drift1.py", "1-5", ["REQ-drifted"])
    store.supersede_requirement("REQ-drifted")
    gaps = services.gaps(store)
    drift = [g for g in gaps if g["type"] == "drift"]
    assert drift
    assert drift[0]["entity_id"] == "REQ-drifted"


def test_drift_not_surfaced_without_impl(store):
    _mk_req(store, "REQ-clean", elaboration="x", criteria=["c"])
    store.supersede_requirement("REQ-clean")
    gaps = services.gaps(store)
    assert [g for g in gaps if g["type"] == "drift"] == []


def test_drift_priority_before_missing_criteria(store):
    _mk_req(store, "REQ-drift", elaboration="x", criteria=["c"])
    _mk_impl(store, "/tmp/p.py", "1-5", ["REQ-drift"])
    store.supersede_requirement("REQ-drift")
    _mk_req(store, "REQ-nc", elaboration="has elab")
    gaps = services.gaps(store)
    order = [g["type"] for g in gaps]
    if "drift" in order and "missing_criteria" in order:
        assert order.index("drift") < order.index("missing_criteria")


def test_drift_shape_matches_uniform(store):
    _mk_req(store, "REQ-d", elaboration="x", criteria=["c"])
    _mk_impl(store, "/tmp/s.py", "1-5", ["REQ-d"])
    store.supersede_requirement("REQ-d")
    gaps = services.gaps(store)
    drift = [g for g in gaps if g["type"] == "drift"]
    assert drift
    required = {"type", "entity_id", "description", "blocks", "suggested_action"}
    for g in drift:
        assert set(g.keys()) >= required
        for k in required:
            assert g[k] is not None


def test_drift_type_filter(store):
    _mk_req(store, "REQ-d", elaboration="x", criteria=["c"])
    _mk_impl(store, "/tmp/t.py", "1-5", ["REQ-d"])
    store.supersede_requirement("REQ-d")
    _mk_req(store, "REQ-nc", elaboration="has elab")
    only_drift = services.gaps(store, types=["drift"])
    assert only_drift
    assert all(g["type"] == "drift" for g in only_drift)


def test_drift_with_multiple_impls(store):
    _mk_req(store, "REQ-multi", elaboration="x", criteria=["c"])
    _mk_impl(store, "/tmp/m1.py", "1-5", ["REQ-multi"])
    _mk_impl(store, "/tmp/m2.py", "10-20", ["REQ-multi"])
    store.supersede_requirement("REQ-multi")
    gaps = services.gaps(store)
    drift = [g for g in gaps if g["type"] == "drift" and g["entity_id"] == "REQ-multi"]
    assert len(drift) == 1


# ===================================================================
# STRUCTURE — verify the 4 helpers exist and work in isolation
# ===================================================================


HELPER_NAMES = [
    "_detect_missing_criteria",
    "_detect_missing_elaboration",
    "_detect_orphan_impl",
    "_detect_drift",
]


@pytest.mark.parametrize("name", HELPER_NAMES)
def test_helper_exists_and_callable(name):
    """Each of the 4 detector helpers must be a module-level callable."""
    assert hasattr(services, name), f"services.{name} must exist (module-level helper)"
    helper = getattr(services, name)
    assert callable(helper), f"services.{name} must be callable"


def test_helper_detect_missing_criteria_isolation(store):
    """_detect_missing_criteria returns only missing_criteria gaps."""
    _mk_req(store, "REQ-nc1", elaboration="e")
    _mk_req(store, "REQ-nc2", elaboration="e")
    _mk_req(store, "REQ-ne", criteria=["c"])  # different problem
    gaps = services._detect_missing_criteria(store)
    assert isinstance(gaps, list)
    assert gaps, "expected missing_criteria gaps"
    assert all(g["type"] == "missing_criteria" for g in gaps)
    ids = {g["entity_id"] for g in gaps}
    assert ids == {"REQ-nc1", "REQ-nc2"}


def test_helper_detect_missing_elaboration_isolation(store):
    _mk_req(store, "REQ-ne1", criteria=["c"])
    _mk_req(store, "REQ-nc", elaboration="e")  # different problem
    gaps = services._detect_missing_elaboration(store)
    assert isinstance(gaps, list)
    assert gaps
    assert all(g["type"] == "missing_elaboration" for g in gaps)
    assert {g["entity_id"] for g in gaps} == {"REQ-ne1"}


def test_helper_detect_orphan_impl_isolation(store):
    _mk_req(store, "REQ-ok", elaboration="e", criteria=["c"])
    _mk_impl(store, "/tmp/live.py", "1-5", ["REQ-ok"])         # not orphan
    _mk_impl(store, "/tmp/dead.py", "1-5", ["REQ-missing"])    # orphan
    gaps = services._detect_orphan_impl(store)
    assert isinstance(gaps, list)
    assert gaps
    assert all(g["type"] == "orphan_impl" for g in gaps)


def test_helper_detect_drift_isolation(store):
    _mk_req(store, "REQ-drift", elaboration="e", criteria=["c"])
    _mk_impl(store, "/tmp/drift.py", "1-5", ["REQ-drift"])
    store.supersede_requirement("REQ-drift")
    # Control: superseded with no impl
    _mk_req(store, "REQ-clean", elaboration="e", criteria=["c"])
    store.supersede_requirement("REQ-clean")
    gaps = services._detect_drift(store)
    assert isinstance(gaps, list)
    assert gaps, "expected drift gap"
    assert all(g["type"] == "drift" for g in gaps)
    assert {g["entity_id"] for g in gaps} == {"REQ-drift"}


def test_helpers_have_uniform_shape(store):
    """Each helper's output must have the uniform 5-field gap shape."""
    _mk_req(store, "REQ-a", elaboration="e")       # missing_criteria
    _mk_req(store, "REQ-b", criteria=["c"])        # missing_elaboration
    _mk_impl(store, "/tmp/o.py", "1-5", ["REQ-z"])  # orphan_impl
    _mk_req(store, "REQ-d", elaboration="e", criteria=["c"])
    _mk_impl(store, "/tmp/d.py", "1-5", ["REQ-d"])
    store.supersede_requirement("REQ-d")            # drift

    required = {"type", "entity_id", "description", "blocks", "suggested_action"}

    for name in HELPER_NAMES:
        helper = getattr(services, name)
        results = helper(store)
        for g in results:
            assert set(g.keys()) >= required, f"{name} returned gap missing fields: {g}"
            for k in required:
                assert g[k] is not None, f"{name} returned gap with None {k}: {g}"
            assert isinstance(g["blocks"], list)
            assert isinstance(g["suggested_action"], str)
