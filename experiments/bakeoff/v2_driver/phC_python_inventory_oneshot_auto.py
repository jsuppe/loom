#!/usr/bin/env python3
"""
Phase C — Python-INVENTORY multi-file Phase D AUTO.

Direct sibling of phC_dart_inventory_oneshot_auto.py — same 8-task
structure, same domain (customers + products + inventory + orders +
persistence), but the executor writes Python instead of Dart. Used
to disambiguate H1 (Dart-specific qwen blind spots) vs H2 (general
complexity ceiling) for the dart-inventory result.

Default executor: qwen3.5:latest. Override via PHC_EXEC_MODEL.
Toggle contract binding with LOOM_EXEC_CONTRACT=1 in the env.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"
OUT_DIR = BAKEOFF_DIR / "runs-v2"
BENCHMARK_DIR = BAKEOFF_DIR / "benchmarks" / "python-inventory" / "ground_truth"
HIDDEN_TEST = BENCHMARK_DIR / "tests" / "test_shop.py"
README = BENCHMARK_DIR / "README.md"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom.store import LoomStore  # noqa
from loom import services  # noqa


PROJECT = "phC_python_inventory_oneshot_auto"

# Tasks run in topological order: errors first, then types, then
# persistence, then services. Same DAG shape as dart-inventory.
TARGET_FILES = [
    "shop/errors.py",
    "shop/types/customers.py",
    "shop/types/products.py",
    "shop/types/inventory.py",
    "shop/types/orders.py",
    "shop/persistence.py",
    "shop/services/customer_service.py",
    "shop/services/inventory_service.py",
    "shop/services/order_service.py",
]
# During the chain, the package barrel is intentionally EMPTY because
# Python's `from .x import y` cascade-loads every submodule — if the
# chain has only built `errors.py`, an aggregating barrel that imports
# from `persistence.py` (still empty) breaks every gating test that
# touches `shop.<anything>`. We swap in the populated barrel only at
# grading time, after all 8 tasks are done.
BARREL_PATH = "shop/__init__.py"
BARREL_CONTENT_CHAIN = '"""shop — populated at grading time."""\n'
BARREL_CONTENT_FULL = '''"""shop — multi-service domain (customers + products + inventory + orders).

Pre-written by the Phase C python-inventory driver; not a qwen task.
"""

from .errors import (
    ConflictError,
    DomainError,
    InsufficientStockError,
    InvalidTransitionError,
    NotFoundError,
    ReservationError,
    ValidationError,
)
from .persistence import Snapshot, Store
from .services.customer_service import CustomerService
from .services.inventory_service import InventoryService
from .services.order_service import OrderService
from .types.customers import Address, Customer
from .types.inventory import ReservationToken, StockLevel
from .types.orders import Item, Order, OrderStatus, Transition
from .types.products import Product

__all__ = [
    "Address",
    "ConflictError",
    "Customer",
    "CustomerService",
    "DomainError",
    "InsufficientStockError",
    "InvalidTransitionError",
    "InventoryService",
    "Item",
    "NotFoundError",
    "Order",
    "OrderService",
    "OrderStatus",
    "Product",
    "ReservationError",
    "ReservationToken",
    "Snapshot",
    "StockLevel",
    "Store",
    "Transition",
    "ValidationError",
]
'''

# Empty __init__.py for sub-packages so imports work
SUBPKG_INITS = {
    "shop/types/__init__.py": "",
    "shop/services/__init__.py": "",
}

# Per-task gating tests. Each verifies the file imports and surfaces
# the basic public symbol — not deep correctness. The hidden suite
# does the real grading after all tasks complete.
GATING_TESTS = {
    "shop/errors.py": '''
from shop.errors import (
    DomainError, ValidationError, NotFoundError, ConflictError,
    InsufficientStockError, InvalidTransitionError, ReservationError,
)

def test_error_hierarchy():
    assert issubclass(ValidationError, DomainError)
    assert issubclass(NotFoundError, DomainError)
    assert issubclass(ConflictError, DomainError)
    assert issubclass(InsufficientStockError, DomainError)
    assert issubclass(InvalidTransitionError, DomainError)
    assert issubclass(ReservationError, DomainError)
''',
    "shop/types/customers.py": '''
from shop.types.customers import Customer, Address

def test_customer_construct():
    c = Customer(id="c1", name="A", email="a@x.com")
    assert c.id == "c1"

def test_customer_bad_email_raises():
    import pytest
    from shop.errors import ValidationError
    with pytest.raises(ValidationError):
        Customer(id="c1", name="A", email="noat")

def test_address_value_type():
    a = Address(street="1 St", city="X", postal_code="1")
    assert a.city == "X"
''',
    "shop/types/products.py": '''
from shop.types.products import Product

def test_product_valid():
    p = Product(sku="A", name="W", price=1.0)
    assert p.sku == "A"

def test_product_non_positive_price_raises():
    import pytest
    from shop.errors import ValidationError
    with pytest.raises(ValidationError):
        Product(sku="A", name="W", price=0)
''',
    "shop/types/inventory.py": '''
from shop.types.inventory import StockLevel, ReservationToken

def test_stock_level_available():
    s = StockLevel(sku="A", on_hand=10, reserved=3)
    assert s.available == 7

def test_reservation_token_is_open_toggles():
    t = ReservationToken(token_id="t1", order_id="o1", sku="A", quantity=1)
    assert t.is_open
    t.committed = True
    assert not t.is_open
''',
    "shop/types/orders.py": '''
from shop.types.orders import Item, Order, OrderStatus

def test_item_line_total():
    i = Item(sku="A", quantity=3, unit_price=2.0)
    assert i.line_total == 6.0

def test_order_status_has_5_values():
    assert len(list(OrderStatus)) == 5

def test_order_construct_and_total():
    o = Order(id="o1", customer_id="c1", items=[
        Item(sku="A", quantity=2, unit_price=5.0),
    ])
    assert o.total == 10.0
    assert o.status == OrderStatus.NEW
''',
    "shop/persistence.py": '''
from shop.persistence import Store

def test_store_has_empty_maps():
    s = Store()
    assert s.customers == {}
    assert s.products == {}

def test_snapshot_restore_round_trips():
    s = Store()
    snap = s.snapshot()
    s.restore(snap)
    assert s.customers == {}
''',
    "shop/services/customer_service.py": '''
from shop.persistence import Store
from shop.services.customer_service import CustomerService

def test_register_and_get_round_trips():
    svc = CustomerService(Store())
    svc.register(id="c1", name="A", email="a@x.com")
    assert svc.get("c1").name == "A"
''',
    "shop/services/inventory_service.py": '''
from shop.persistence import Store
from shop.services.inventory_service import InventoryService

def test_register_add_stock_reserve():
    svc = InventoryService(Store())
    svc.register_product(sku="A", name="W", price=1.0)
    svc.add_stock("A", 10)
    t = svc.reserve(order_id="o1", sku="A", quantity=3)
    assert t.quantity == 3
    assert svc.stock_of("A").reserved == 3
''',
    "shop/services/order_service.py": '''
from shop.persistence import Store
from shop.services.customer_service import CustomerService
from shop.services.inventory_service import InventoryService
from shop.services.order_service import OrderService
from shop.types.orders import OrderStatus

def test_place_and_mark_paid_sequence():
    s = Store()
    cs = CustomerService(s)
    inv = InventoryService(s)
    os_ = OrderService(s, cs, inv)
    cs.register(id="c1", name="A", email="a@x.com")
    inv.register_product(sku="A", name="W", price=1.0)
    inv.add_stock("A", 10)
    o = os_.place(customer_id="c1", lines=[{"sku": "A", "quantity": 2}])
    assert o.status == OrderStatus.NEW
    os_.mark_paid(o.id)
    assert os_.get(o.id).status == OrderStatus.PAID
''',
}

GATING_TEST_TARGETS = {
    tf: f"tests/test_gate_{tf.replace('/', '_').replace('.py', '')}.py"
    for tf in TARGET_FILES
}


PLANNER_SYSTEM = """\
You are a senior Python architect writing an implementation specification
for a multi-file, multi-service Python library called `shop`. The
downstream executor is a small local model (qwen3.5, 9.7B parameters)
that will write each file in a single replace-mode pass. Your spec
must be self-contained, exhaustive about Python-specific syntax, and
explicit about which symbols live in which file.

The library is split across 9 implementation files (the barrel
shop/__init__.py re-exporting these is pre-written by the harness;
do NOT include a section for it):

  shop/errors.py                            — domain error hierarchy
  shop/types/customers.py                   — Customer + Address
  shop/types/products.py                    — Product
  shop/types/inventory.py                   — StockLevel + ReservationToken
  shop/types/orders.py                      — Item, Transition, Order, OrderStatus
  shop/persistence.py                       — Store + Snapshot
  shop/services/customer_service.py         — CustomerService
  shop/services/inventory_service.py        — InventoryService
  shop/services/order_service.py            — OrderService

Cross-file commitments to fix early in your spec:
  - All errors derive from `class DomainError(Exception)`. Subclasses
    are bare `pass` bodies (`class X(DomainError): pass`).
  - Keep the EXACT subclass names listed in the README — tests assert
    on type. Do not invent merged or renamed errors.
  - `OrderStatus(Enum)` has values `NEW, PAID, SHIPPED, DELIVERED,
    CANCELLED`. Use uppercase identifiers.
  - `Item` is `@dataclass(frozen=True)`. `unit_price: float`
    (snapshotted at order time). Has `@property line_total`.
  - `Order` is `@dataclass`. `status` mutable (default
    `OrderStatus.NEW`). `history` mutable `List[Transition]`. Use
    `field(default_factory=list)` for mutable defaults.
  - `Transition.from_status: Optional[OrderStatus]` (None on creation).
    `@dataclass(frozen=True)`.
  - `StockLevel` is `@dataclass`. `sku: str`, `on_hand: int = 0`,
    `reserved: int = 0`. `@property available` returns
    `self.on_hand - self.reserved`. Constructor MUST accept `sku=`.
  - `ReservationToken` is `@dataclass` with mutable `committed: bool`
    and `released: bool` flags; `@property is_open` returns
    `not self.committed and not self.released`.
  - `Store.snapshot()` MUST DEEP-COPY mutable state (StockLevel,
    Order with its history list, ReservationToken). Use
    `copy.deepcopy(v)` per value. Customers and Products are
    immutable (frozen) so `dict(self.customers)` is fine.
  - Order line records are passed as `List[dict]` with `'sku'` and
    `'quantity'` keys (e.g., `[{"sku": "A", "quantity": 2}]`).
  - Token IDs: `f"rsv-{seq:06d}"`. Order IDs: `f"ord-{seq:06d}"`.

Critical Python specifics for the executor:
  - All services use **keyword-only arguments** for register/place
    methods. Use `def register(self, *, id: str, name: str, email: str)`.
  - Use `@dataclass` and `@dataclass(frozen=True)` from `dataclasses`.
  - Use `field(default_factory=list)` (NOT `[]`) for mutable defaults.
  - Use `from typing import List, Optional` for type hints.
  - Use `from .errors import X` for relative imports inside the
    `shop` package; cross-package imports use `..errors` from
    `services/` and `types/` subpackages.
  - Validate in `__post_init__` for dataclasses; raise the exact
    error subclass (e.g., `ValidationError`).
  - `OrderService.place(*, customer_id, lines)` releases all
    already-reserved tokens via `try/except` if any reservation
    fails mid-loop, then re-raises.

For each file, give:
  - import declarations needed
  - public class/function signatures with types
  - method bodies described concretely (not pseudocode)
  - field declarations (typed, defaults where applicable)
  - `__post_init__` validation behavior

CONTRACT BLOCKS — each `### shop/<path>.py` section MUST end with a
```python-contract
…
```
fenced block containing declaration-only Python code: every public
class, dataclass field, method signature, property, and enum that
the executor must produce, with full signatures and types but no
method bodies (use `...` or `raise NotImplementedError` in method
bodies; dataclass classes can be declared with their fields).

The contract block is the BINDING for the executor — every named
parameter, field, method signature, and property in the contract
becomes a hard commitment.

Output ONE top-level ```text``` block wrapping the whole spec.
Inside it, organize as 9 sections each labeled exactly
`### shop/<path>.py` (matching the file paths above), in the listed
order. Each section has the prose description followed by its
`python-contract` block.
"""


def call_opus(prompt: str, model: str = "opus") -> dict:
    """Stateless `claude -p` planner call (subscription-billed)."""
    args = [
        "claude", "-p",
        "--no-session-persistence",
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "--model", model,
        "--append-system-prompt", PLANNER_SYSTEM,
    ]
    t0 = time.time()
    proc = subprocess.run(
        args, input=prompt,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=600,
    )
    elapsed = time.time() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p rc={proc.returncode}\n"
                           f"stderr: {proc.stderr[-500:]}")
    data = json.loads(proc.stdout)
    return {
        "content": data.get("result", ""),
        "duration_ms": data.get("duration_ms", int(elapsed * 1000)),
        "cost_usd": data.get("total_cost_usd") or data.get("cost_usd", 0),
    }


def extract_spec(opus_response: str) -> str:
    text = opus_response.strip()
    m = re.match(
        r"^```(?:text|markdown)\s*\n(.*)\n```\s*$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def split_spec_by_file(spec_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    pattern = re.compile(r"^### (shop/\S+\.py)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(spec_text))
    if not matches:
        return {f: spec_text for f in TARGET_FILES}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(spec_text)
        sections[m.group(1)] = spec_text[start:end].strip()
    for f in TARGET_FILES:
        sections.setdefault(f, spec_text)
    return sections


def extract_python_contracts(spec_text: str) -> dict[str, str]:
    """Pull a `python-contract` block out of every section."""
    contracts: dict[str, str] = {}
    sections = split_spec_by_file(spec_text)
    fence_re = re.compile(r"```python-contract\s*\n(.*?)\n```", re.DOTALL)
    for path, section in sections.items():
        m = fence_re.search(section)
        if m:
            contracts[path] = m.group(1).rstrip()
    return contracts


def parse_pytest(stdout: str) -> tuple[int, int]:
    """Parse `pytest -q` output for passed and total counts."""
    m = re.search(r"(\d+)\s+passed", stdout)
    p = int(m.group(1)) if m else 0
    f = 0
    m_fail = re.search(r"(\d+)\s+failed", stdout)
    if m_fail:
        f = int(m_fail.group(1))
    e = 0
    m_err = re.search(r"(\d+)\s+error", stdout)
    if m_err:
        e = int(m_err.group(1))
    return p, p + f + e


def grade(workspace: Path) -> dict:
    """Run the hidden test suite against the workspace's shop/."""
    grade_dir = Path(tempfile.mkdtemp(prefix="phC_pyinv_grade_"))
    shutil.copytree(workspace, grade_dir, dirs_exist_ok=True)
    (grade_dir / "tests").mkdir(exist_ok=True)
    shutil.copy(HIDDEN_TEST, grade_dir / "tests" / "test_shop.py")
    # Swap the empty chain barrel for the populated one. During the
    # chain we used an empty __init__.py to avoid Python's cascade-
    # import problem; now that all files exist, the hidden test can
    # do `from shop import (...)` against the full barrel.
    (grade_dir / BARREL_PATH).write_text(
        BARREL_CONTENT_FULL, encoding="utf-8")
    proc = subprocess.run(
        ["python3", "-m", "pytest", "-q", "tests/test_shop.py"],
        cwd=grade_dir, capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace",
    )
    p, total = parse_pytest(proc.stdout)
    if total == 0:
        total = 28
    return {
        "passed": p, "total": total,
        "pass_rate": p / total if total else 0,
        "stdout_tail": (proc.stdout + proc.stderr)[-2500:],
        "grade_dir": str(grade_dir),
    }


def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phC_python_inv_"))
    (ws / "shop").mkdir()
    (ws / "shop" / "types").mkdir()
    (ws / "shop" / "services").mkdir()
    (ws / "tests").mkdir()
    (ws / ".loom-config.json").write_text(
        json.dumps({"test_runner": "pytest", "model": "qwen3.5:latest"},
                   indent=2),
        encoding="utf-8",
    )
    for tf in TARGET_FILES:
        (ws / tf).write_text("", encoding="utf-8")
    (ws / BARREL_PATH).write_text(BARREL_CONTENT_CHAIN, encoding="utf-8")
    for sub_init, content in SUBPKG_INITS.items():
        (ws / sub_init).write_text(content, encoding="utf-8")
    for tf, gate_path in GATING_TEST_TARGETS.items():
        (ws / gate_path).write_text(GATING_TESTS[tf], encoding="utf-8")
    # conftest so pytest finds the package
    (ws / "conftest.py").write_text(
        "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parent))\n",
        encoding="utf-8",
    )
    return ws


def run_one(run_id: str = "1") -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] workspace: {workspace}")

    store_dir = Path.home() / ".openclaw" / "loom" / PROJECT
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=PROJECT)

    # Step 1: Opus authors the spec (or load cached canonical).
    cached_path = os.environ.get("PHC_INV_CANONICAL_SPEC", "").strip()
    if cached_path and Path(cached_path).exists():
        opus_t0 = time.time()
        raw_response = Path(cached_path).read_text(encoding="utf-8")
        opus_elapsed = time.time() - opus_t0
        opus_resp = {
            "content": raw_response,
            "duration_ms": int(opus_elapsed * 1000),
            "cost_usd": 0.0,
        }
        print(f"[opus] cached spec from {cached_path}  raw_chars={len(raw_response)}")
    else:
        readme = README.read_text(encoding="utf-8")
        planner_prompt = (
            f"Below is a benchmark README that describes a 9-file Python "
            f"multi-service library named `shop`. Write a complete "
            f"implementation spec, organized as 9 `### shop/...py` "
            f"sections so a downstream executor can produce each file in "
            f"a single replace pass. Each section MUST end with a "
            f"```python-contract``` block per the system instructions. "
            f"Output ONLY a ```text``` block.\n\n"
            f"---README---\n{readme}\n---END README---"
        )
        opus_t0 = time.time()
        opus_resp = call_opus(planner_prompt)
        opus_elapsed = time.time() - opus_t0
        print(f"[opus] {opus_elapsed:.1f}s  cost=${opus_resp['cost_usd']:.4f}")

    spec_text = extract_spec(opus_resp["content"])
    sections = split_spec_by_file(spec_text)
    contracts = extract_python_contracts(spec_text)
    print(f"[opus] spec_chars={len(spec_text)}  sections={len(sections)}  "
          f"contracts={len(contracts)}/{len(TARGET_FILES)}")

    # Step 2: Loom seeding — full-spec context + per-file contracts.
    req = services.extract(
        store, domain="behavior",
        value="Implement the python-inventory multi-service library as specified.",
        rationale="Phase C python-inventory benchmark — disambiguates Dart-specific "
                  "vs general complexity ceiling for qwen3.5.",
    )
    spec = services.spec_add(store, req["req_id"], spec_text)
    # Per-file contract blocks are inlined inside the spec text already.
    # The standalone contract data plane was rolled back from main; the
    # full spec (with python-contract blocks visible) still reaches the
    # executor through the spec description loom_exec assembles into
    # the body prompt.
    _ = contracts  # kept for summary count, no separate storage

    task_ids = []
    for i, tf in enumerate(TARGET_FILES):
        depends = [task_ids[i - 1]] if task_ids else []
        result = services.task_add(
            store,
            parent_spec=spec["spec_id"],
            title=f"Implement {tf} per the section labeled `### {tf}` in the spec",
            files_to_modify=[tf],
            test_to_write=GATING_TEST_TARGETS[tf],
            context_reqs=[req["req_id"]],
            context_specs=[spec["spec_id"]],
            context_files=[tf],
            depends_on=depends,
            size_budget_files=1,
            size_budget_loc=400,
            created_by="opus_planner_python_inventory",
        )
        task_ids.append(result["id"])

    # Step 3: loom_exec drains the queue.
    exec_env = {**os.environ}
    if "LOOM_EXEC_CONTRACT" not in exec_env:
        exec_env["LOOM_EXEC_CONTRACT"] = "1"
    exec_t0 = time.time()
    exec_proc = subprocess.run(
        [sys.executable, str(LOOM_DIR / "scripts" / "loom_exec"),
         "--next", "--loop",
         "--model", os.environ.get("PHC_EXEC_MODEL", "qwen3.5:latest"),
         "-p", PROJECT, "--target-dir", str(workspace),
         ],
        env=exec_env,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=1800,
    )
    exec_elapsed = time.time() - exec_t0
    print(f"[exec] {exec_elapsed:.1f}s rc={exec_proc.returncode}")
    print("[exec] tail:")
    print("\n".join(exec_proc.stdout.splitlines()[-40:]))

    # Step 4: hidden grading
    g = grade(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}")

    file_sizes = {}
    for tf in TARGET_FILES:
        p = workspace / tf
        if p.exists():
            file_sizes[tf] = len(p.read_text(encoding="utf-8"))

    # Amendment data plane is rolled back on main; no amendments fire.
    amendments: list = []

    summary = {
        "phase": "C_python_inventory_oneshot_auto",
        "run_id": run_id,
        "benchmark": "python-inventory",
        "planner": "opus(claude -p)",
        "executor": os.environ.get("PHC_EXEC_MODEL", "qwen3.5:latest"),
        "contract_enabled": exec_env.get("LOOM_EXEC_CONTRACT") == "1",
        "passed": g["passed"], "total": g["total"],
        "pass_rate": g["pass_rate"],
        "opus_duration_s": round(opus_elapsed, 1),
        "opus_cost_usd": opus_resp["cost_usd"],
        "spec_chars": len(spec_text),
        "contracts_initial": len(contracts),
        "amendment_count": len(amendments),
        "amendments_recovered": sum(1 for a in amendments if a["recovered"]),
        "amendments": amendments,
        "exec_duration_s": round(exec_elapsed, 1),
        "exec_rc": exec_proc.returncode,
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "grade_dir": g["grade_dir"],
        "file_sizes": file_sizes,
        "spec_sections_found": list(sections.keys()),
        "exec_stdout_tail": "\n".join(exec_proc.stdout.splitlines()[-80:]),
        "grade_stdout_tail": g.get("stdout_tail", ""),
    }
    out_path = OUT_DIR / f"phC_python_inv_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSUMMARY: pass={g['passed']}/{g['total']}  "
          f"opus=${opus_resp['cost_usd']:.4f}+{opus_elapsed:.1f}s  "
          f"qwen={exec_elapsed:.1f}s  "
          f"amendments={summary['amendment_count']}({summary['amendments_recovered']}rec)  "
          f"wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    run_one(rid)
