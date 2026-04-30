"""
Grading test for TASK-gaps-1.

Success = every assertion here passes. This test is intentionally thorough:
it verifies each postcondition from task.md independently so a near-miss
shows up as a specific failure, not a single green/red bit.

Run from the repo root:
    python -m pytest experiments/gaps/test_gaps_task1.py -v
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
    s = LoomStore(project="test-gaps-experiment", data_dir=tmp)
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
        id=req_id,
        domain="behavior",
        value=value,
        source_msg_id="m1",
        source_session="s1",
        timestamp="2026-01-01T00:00:00Z",
        elaboration=elaboration,
        acceptance_criteria=criteria,
    )
    store.add_requirement(req, FAKE_EMBEDDING)
    return req


def _mk_impl(store, impl_id_file, impl_id_lines, satisfies_req_ids):
    impl = Implementation(
        id=generate_impl_id(impl_id_file, impl_id_lines),
        file=impl_id_file,
        lines=impl_id_lines,
        content="pass\n",
        content_hash="h",
        satisfies=[{"req_id": r} for r in satisfies_req_ids],
        timestamp="2026-01-01T00:00:00Z",
    )
    store.add_implementation(impl, FAKE_EMBEDDING)
    return impl


def test_gaps_is_callable():
    assert hasattr(services, "gaps"), "services.gaps() must exist"
    assert callable(services.gaps)


def test_missing_criteria_surfaced(store):
    _mk_req(store, "REQ-nc", elaboration="some elaboration text")  # criteria omitted
    gaps = services.gaps(store)
    matches = [g for g in gaps if g["entity_id"] == "REQ-nc"]
    assert any(g["type"] == "missing_criteria" for g in matches), \
        f"Expected missing_criteria gap for REQ-nc; got {matches}"


def test_missing_elaboration_surfaced(store):
    _mk_req(store, "REQ-ne", criteria=["criterion one"])  # elaboration omitted
    gaps = services.gaps(store)
    matches = [g for g in gaps if g["entity_id"] == "REQ-ne"]
    assert any(g["type"] == "missing_elaboration" for g in matches), \
        f"Expected missing_elaboration gap for REQ-ne; got {matches}"


def test_orphan_impl_surfaced(store):
    _mk_impl(store, "/tmp/a.py", "1-5", ["REQ-does-not-exist"])
    gaps = services.gaps(store)
    assert any(g["type"] == "orphan_impl" for g in gaps), \
        f"Expected orphan_impl gap; got {gaps}"


def test_impl_with_superseded_req_is_orphan(store):
    _mk_req(store, "REQ-old", elaboration="x", criteria=["c"])
    store.supersede_requirement("REQ-old")
    _mk_impl(store, "/tmp/b.py", "1-5", ["REQ-old"])
    gaps = services.gaps(store)
    # An impl whose only linked req is superseded is orphan-adjacent.
    assert any(g["type"] == "orphan_impl" for g in gaps), \
        f"Expected orphan_impl gap for superseded-only impl; got {gaps}"


def test_impl_with_any_live_req_is_not_orphan(store):
    _mk_req(store, "REQ-live", elaboration="x", criteria=["c"])
    _mk_req(store, "REQ-dead", elaboration="x", criteria=["c"])
    store.supersede_requirement("REQ-dead")
    _mk_impl(store, "/tmp/c.py", "1-5", ["REQ-live", "REQ-dead"])
    gaps = services.gaps(store)
    orphans = [g for g in gaps if g["type"] == "orphan_impl"]
    assert orphans == [], \
        f"Impl with at least one live linked req should not be orphan; got {orphans}"


def test_uniform_shape(store):
    _mk_req(store, "REQ-a")
    _mk_impl(store, "/tmp/d.py", "1-5", ["REQ-missing"])
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


def test_ordering_by_priority(store):
    # Two reqs: one needs criteria (higher priority), one needs elaboration.
    _mk_req(store, "REQ-crit", elaboration="has elab")   # missing_criteria
    _mk_req(store, "REQ-elab", criteria=["c1"])          # missing_elaboration
    _mk_impl(store, "/tmp/e.py", "1-5", ["REQ-absent"])  # orphan_impl (lowest)
    gaps = services.gaps(store)
    types_in_order = [g["type"] for g in gaps]
    # Every missing_criteria entry must appear before any missing_elaboration entry.
    if "missing_criteria" in types_in_order and "missing_elaboration" in types_in_order:
        assert types_in_order.index("missing_criteria") < types_in_order.index("missing_elaboration")
    # Every missing_elaboration must appear before any orphan_impl.
    if "missing_elaboration" in types_in_order and "orphan_impl" in types_in_order:
        assert types_in_order.index("missing_elaboration") < types_in_order.index("orphan_impl")


def test_tie_break_by_entity_id(store):
    _mk_req(store, "REQ-b", elaboration="e")  # missing_criteria
    _mk_req(store, "REQ-a", elaboration="e")  # missing_criteria
    gaps = services.gaps(store)
    mc = [g for g in gaps if g["type"] == "missing_criteria"]
    assert [g["entity_id"] for g in mc] == sorted(g["entity_id"] for g in mc), \
        "tie-break should be ascending entity_id"


def test_type_filter(store):
    _mk_req(store, "REQ-x")                      # both elab AND criteria missing
    _mk_impl(store, "/tmp/f.py", "1-5", ["REQ-absent"])  # orphan_impl
    only_orphan = services.gaps(store, types=["orphan_impl"])
    assert all(g["type"] == "orphan_impl" for g in only_orphan), \
        f"types filter leaked other types: {only_orphan}"


def test_limit_cap(store):
    for i in range(5):
        _mk_req(store, f"REQ-{i:02d}", elaboration="e")
    gaps = services.gaps(store, limit=3)
    assert len(gaps) <= 3


def test_superseded_reqs_excluded_from_req_level_gaps(store):
    _mk_req(store, "REQ-sup")  # both elab + criteria missing
    store.supersede_requirement("REQ-sup")
    gaps = services.gaps(store)
    bad = [g for g in gaps
           if g["entity_id"] == "REQ-sup"
           and g["type"] in {"missing_criteria", "missing_elaboration"}]
    assert bad == [], f"superseded reqs must not surface as missing_* gaps; got {bad}"


def test_empty_store_returns_empty_list(store):
    assert services.gaps(store) == []


def test_complete_reqs_do_not_surface(store):
    _mk_req(store, "REQ-ok", elaboration="fully elaborated", criteria=["c1", "c2"])
    gaps = services.gaps(store)
    related = [g for g in gaps if g["entity_id"] == "REQ-ok"]
    assert related == [], f"complete req should not appear in gaps; got {related}"
