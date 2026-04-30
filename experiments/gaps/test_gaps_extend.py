"""
Grading test for the HARDER task: extending gaps() with drift detection.

Inherits all 14 cases from test_gaps_task1.py (no-regression check) and adds
6 new cases that verify drift detection. A passing run proves the model read
the existing gaps() function, preserved its behavior on the 3 original types,
AND correctly added a 4th type (drift) without breaking the shape contract,
priority ordering, type filter, or limit cap.

Drift semantics:
    A superseded requirement that still has at least one linked implementation
    whose id is present in the store is a drift gap. The implementation may
    itself be pointing at multiple reqs; what matters for DRIFT is that the
    superseded req_id still appears in some impl's satisfies list.

    Priority 2 (surfaces before the existing types 3/5/6).
    entity_id = the superseded req's id (not the impl's).
"""
from __future__ import annotations

import sys
import tempfile
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from loom import embedding  # noqa: E402
from loom import services  # noqa: E402
from loom.store import LoomStore, Requirement, Implementation, generate_impl_id  # noqa: E402


FAKE_EMBEDDING = [0.1] * 768


@pytest.fixture
def store():
    tmp = Path(tempfile.mkdtemp())
    s = LoomStore(project="test-gaps-extend", data_dir=tmp)
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


# ------------------- original 14 cases (no-regression) -------------------


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
    assert gaps
    required = {"type", "entity_id", "description", "blocks", "suggested_action"}
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
    types_in_order = [g["type"] for g in gaps]
    if "missing_criteria" in types_in_order and "missing_elaboration" in types_in_order:
        assert types_in_order.index("missing_criteria") < types_in_order.index("missing_elaboration")
    if "missing_elaboration" in types_in_order and "orphan_impl" in types_in_order:
        assert types_in_order.index("missing_elaboration") < types_in_order.index("orphan_impl")


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


# ------------------- NEW: drift detection cases -------------------


def test_drift_type_exists(store):
    """A superseded req with a linked impl must surface as type='drift'."""
    _mk_req(store, "REQ-drifted", elaboration="x", criteria=["c"])
    _mk_impl(store, "/tmp/drift1.py", "1-5", ["REQ-drifted"])
    store.supersede_requirement("REQ-drifted")
    gaps = services.gaps(store)
    drift = [g for g in gaps if g["type"] == "drift"]
    assert drift, f"expected drift gap; got types={[g['type'] for g in gaps]}"
    assert drift[0]["entity_id"] == "REQ-drifted"


def test_drift_not_surfaced_without_impl(store):
    """A superseded req with no linked impl is not drift (nothing to worry about)."""
    _mk_req(store, "REQ-clean", elaboration="x", criteria=["c"])
    store.supersede_requirement("REQ-clean")
    gaps = services.gaps(store)
    drift = [g for g in gaps if g["type"] == "drift"]
    assert drift == []


def test_drift_priority_before_missing_criteria(store):
    """Priority order: drift (2) surfaces before missing_criteria (3)."""
    _mk_req(store, "REQ-drift", elaboration="x", criteria=["c"])
    _mk_impl(store, "/tmp/p.py", "1-5", ["REQ-drift"])
    store.supersede_requirement("REQ-drift")
    _mk_req(store, "REQ-nc", elaboration="has elab")  # missing_criteria
    gaps = services.gaps(store)
    types_in_order = [g["type"] for g in gaps]
    if "drift" in types_in_order and "missing_criteria" in types_in_order:
        assert types_in_order.index("drift") < types_in_order.index("missing_criteria")


def test_drift_shape_matches_uniform(store):
    """Drift gaps follow the same 5-field uniform shape."""
    _mk_req(store, "REQ-d", elaboration="x", criteria=["c"])
    _mk_impl(store, "/tmp/s.py", "1-5", ["REQ-d"])
    store.supersede_requirement("REQ-d")
    gaps = services.gaps(store)
    drift = [g for g in gaps if g["type"] == "drift"]
    assert drift
    g = drift[0]
    required = {"type", "entity_id", "description", "blocks", "suggested_action"}
    assert set(g.keys()) >= required
    for k in required:
        assert g[k] is not None
    assert isinstance(g["blocks"], list)
    assert isinstance(g["suggested_action"], str)
    assert g["suggested_action"].strip()


def test_drift_type_filter(store):
    """types=['drift'] filters to drift only and excludes the other existing types."""
    _mk_req(store, "REQ-d", elaboration="x", criteria=["c"])
    _mk_impl(store, "/tmp/t.py", "1-5", ["REQ-d"])
    store.supersede_requirement("REQ-d")
    _mk_req(store, "REQ-nc", elaboration="has elab")  # missing_criteria
    only_drift = services.gaps(store, types=["drift"])
    assert only_drift
    assert all(g["type"] == "drift" for g in only_drift)


def test_drift_with_multiple_impls(store):
    """Superseded req with >1 linked impl still yields a single drift gap."""
    _mk_req(store, "REQ-multi", elaboration="x", criteria=["c"])
    _mk_impl(store, "/tmp/m1.py", "1-5", ["REQ-multi"])
    _mk_impl(store, "/tmp/m2.py", "10-20", ["REQ-multi"])
    store.supersede_requirement("REQ-multi")
    gaps = services.gaps(store)
    drift = [g for g in gaps if g["type"] == "drift" and g["entity_id"] == "REQ-multi"]
    assert len(drift) == 1, f"expected exactly one drift gap per superseded req; got {drift}"
