#!/usr/bin/env python3
"""
Phase C — Dart-INVENTORY multi-file Phase D AUTO.

Bigger sibling of phC_dart_oneshot_auto.py:
  - 9 lib files (8 executor tasks + 1 pre-written barrel) vs 4 / 3
  - 3 services coordinating through an in-memory persistence Store
  - 4-layer dependency DAG (errors → types/* → persistence → services/*)
  - 28 hidden tests covering full lifecycle scenarios

Sized so Tier 2 alone does not saturate, leaving headroom for a
blueprint pass to demonstrate lift. Drives Opus → 8 qwen tasks
through loom_exec; grades with `dart test` against the hidden suite.

Default executor: qwen3.5:latest. Override via PHC_EXEC_MODEL.
Toggle blueprint pass with LOOM_EXEC_BLUEPRINT=1 in the environment.
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
BENCHMARK_DIR = BAKEOFF_DIR / "benchmarks" / "dart-inventory" / "ground_truth"
HIDDEN_TEST = BENCHMARK_DIR / "tests" / "shop_test.dart"
README = BENCHMARK_DIR / "README.md"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom.store import LoomStore  # noqa
from loom import services  # noqa


PROJECT = "phC_dart_inventory_oneshot_auto"

# Tasks run in topological order: errors first (no internal deps),
# then types, then persistence, then services.
TARGET_FILES = [
    "lib/errors.dart",
    "lib/types/customers.dart",
    "lib/types/products.dart",
    "lib/types/inventory.dart",
    "lib/types/orders.dart",
    "lib/persistence.dart",
    "lib/services/customer_service.dart",
    "lib/services/inventory_service.dart",
    "lib/services/order_service.dart",
]
BARREL_PATH = "lib/shop.dart"
BARREL_CONTENT = (
    "/// shop.dart — barrel re-exporting the public multi-service API.\n"
    "/// Pre-written by the Phase C dart-inventory driver; not a qwen task.\n\n"
    "export 'errors.dart';\n"
    "export 'persistence.dart';\n"
    "export 'types/customers.dart';\n"
    "export 'types/products.dart';\n"
    "export 'types/inventory.dart';\n"
    "export 'types/orders.dart';\n"
    "export 'services/customer_service.dart';\n"
    "export 'services/inventory_service.dart';\n"
    "export 'services/order_service.dart';\n"
)

PUBSPEC = """name: shop
description: Multi-service shop domain (customers + products + inventory + orders).
publish_to: none
environment:
  sdk: '>=3.4.0 <4.0.0'
dev_dependencies:
  test: ^1.24.0
"""

# Per-task gating tests. Each verifies the file imports and surfaces
# the basic public symbol — not a deep correctness check. Real
# correctness gate is the hidden suite, run after all 8 tasks complete.
GATING_TESTS = {
    "lib/errors.dart": '''
import 'package:test/test.dart';
import 'package:shop/errors.dart';

void main() {
  test('error hierarchy', () {
    expect(const ValidationError('x'), isA<DomainError>());
    expect(const NotFoundError('x'), isA<DomainError>());
    expect(const ConflictError('x'), isA<DomainError>());
    expect(const InsufficientStockError('x'), isA<DomainError>());
    expect(const InvalidTransitionError('x'), isA<DomainError>());
    expect(const ReservationError('x'), isA<DomainError>());
  });
}
''',
    "lib/types/customers.dart": '''
import 'package:test/test.dart';
import 'package:shop/types/customers.dart';

void main() {
  test('Customer construct + bad email throws', () {
    final c = Customer(id: 'c1', name: 'A', email: 'a@x.com');
    expect(c.id, 'c1');
    expect(() => Customer(id: 'c1', name: 'A', email: 'noat'), throwsA(anything));
  });
  test('Address value type', () {
    const a = Address(street: '1 St', city: 'X', postalCode: '1');
    expect(a.city, 'X');
  });
}
''',
    "lib/types/products.dart": '''
import 'package:test/test.dart';
import 'package:shop/types/products.dart';

void main() {
  test('Product valid', () {
    final p = Product(sku: 'A', name: 'W', price: 1.0);
    expect(p.sku, 'A');
  });
  test('Product non-positive price throws', () {
    expect(() => Product(sku: 'A', name: 'W', price: 0), throwsA(anything));
  });
}
''',
    "lib/types/inventory.dart": '''
import 'package:test/test.dart';
import 'package:shop/types/inventory.dart';

void main() {
  test('StockLevel.available', () {
    final s = StockLevel(sku: 'A', onHand: 10, reserved: 3);
    expect(s.available, 7);
  });
  test('ReservationToken.isOpen toggles', () {
    final t = ReservationToken(tokenId: 't1', orderId: 'o1', sku: 'A', quantity: 1);
    expect(t.isOpen, true);
    t.committed = true;
    expect(t.isOpen, false);
  });
}
''',
    "lib/types/orders.dart": '''
import 'package:test/test.dart';
import 'package:shop/types/orders.dart';

void main() {
  test('Item.lineTotal', () {
    final i = Item(sku: 'A', quantity: 3, unitPrice: 2.0);
    expect(i.lineTotal, 6.0);
  });
  test('OrderStatus has 5 values', () {
    expect(OrderStatus.values.length, 5);
  });
  test('Order constructor + total', () {
    final o = Order(id: 'o1', customerId: 'c1', items: [
      Item(sku: 'A', quantity: 2, unitPrice: 5.0),
    ]);
    expect(o.total, 10.0);
    expect(o.status, OrderStatus.newly);
  });
}
''',
    "lib/persistence.dart": '''
import 'package:test/test.dart';
import 'package:shop/persistence.dart';

void main() {
  test('Store has empty maps', () {
    final s = Store();
    expect(s.customers, isEmpty);
    expect(s.products, isEmpty);
  });
  test('snapshot + restore round trips', () {
    final s = Store();
    final snap = s.snapshot();
    s.restore(snap);
    expect(s.customers, isEmpty);
  });
}
''',
    "lib/services/customer_service.dart": '''
import 'package:test/test.dart';
import 'package:shop/persistence.dart';
import 'package:shop/services/customer_service.dart';

void main() {
  test('register + get round trips', () {
    final svc = CustomerService(Store());
    svc.register(id: 'c1', name: 'A', email: 'a@x.com');
    expect(svc.get('c1').name, 'A');
  });
}
''',
    "lib/services/inventory_service.dart": '''
import 'package:test/test.dart';
import 'package:shop/persistence.dart';
import 'package:shop/services/inventory_service.dart';

void main() {
  test('register + addStock + reserve', () {
    final svc = InventoryService(Store());
    svc.registerProduct(sku: 'A', name: 'W', price: 1.0);
    svc.addStock('A', 10);
    final t = svc.reserve(orderId: 'o1', sku: 'A', quantity: 3);
    expect(t.quantity, 3);
    expect(svc.stockOf('A').reserved, 3);
  });
}
''',
    "lib/services/order_service.dart": '''
import 'package:test/test.dart';
import 'package:shop/persistence.dart';
import 'package:shop/services/customer_service.dart';
import 'package:shop/services/inventory_service.dart';
import 'package:shop/services/order_service.dart';
import 'package:shop/types/orders.dart';

void main() {
  test('place + markPaid sequence', () {
    final s = Store();
    final cs = CustomerService(s);
    final inv = InventoryService(s);
    final os = OrderService(s, cs, inv);
    cs.register(id: 'c1', name: 'A', email: 'a@x.com');
    inv.registerProduct(sku: 'A', name: 'W', price: 1.0);
    inv.addStock('A', 10);
    final o = os.place(customerId: 'c1', lines: [(sku: 'A', quantity: 2)]);
    expect(o.status, OrderStatus.newly);
    os.markPaid(o.id);
    expect(os.get(o.id).status, OrderStatus.paid);
  });
}
''',
}

GATING_TEST_TARGETS = {
    tf: f"test/_gate_{tf.replace('/', '_').replace('.dart', '')}.dart"
    for tf in TARGET_FILES
}


PLANNER_SYSTEM = """\
You are a senior Dart architect writing an implementation specification
for a multi-file, multi-service Dart library called `shop`. The
downstream executor is a small local model (qwen3.5, 9.7B parameters)
that will write each file in a single replace-mode pass. Your spec
must be self-contained, exhaustive about Dart-specific syntax, and
explicit about which symbols live in which file.

The library is split across 9 implementation files (the barrel
lib/shop.dart re-exporting these is pre-written by the harness; do
NOT include a section for it):

  lib/errors.dart                          — domain error hierarchy
  lib/types/customers.dart                 — Customer + Address
  lib/types/products.dart                  — Product
  lib/types/inventory.dart                 — StockLevel + ReservationToken
  lib/types/orders.dart                    — Item, Transition, Order, OrderStatus
  lib/persistence.dart                     — Store + Snapshot
  lib/services/customer_service.dart       — CustomerService
  lib/services/inventory_service.dart      — InventoryService
  lib/services/order_service.dart          — OrderService

Cross-file commitments to fix early in your spec:
  - All errors extend `DomainError implements Exception` (do NOT extend
    Exception directly). Subclasses use `super.message` to forward.
  - Keep the EXACT subclass names listed in the README — tests assert
    on type. Do not invent merged or renamed errors.
  - `OrderStatus` enum: `newly, paid, shipped, delivered, cancelled`.
    Use `newly` (not `new` — Dart reserves `new`).
  - `Item` snapshots `unitPrice: double` at order time.
  - `Order.status` is mutable; `Order.history` is a mutable List<Transition>.
  - `Transition.fromStatus` is `OrderStatus?` (nullable, null on creation).
  - `StockLevel` is mutable; carries `String sku`, `int onHand`,
    `int reserved`, plus derived `int get available => onHand - reserved`.
    The constructor MUST take `required String sku`.
  - `ReservationToken` has mutable `committed` and `released` flags;
    `bool get isOpen => !committed && !released`.
  - `Store.snapshot()` MUST DEEP-COPY mutable state (StockLevel,
    Order, ReservationToken) so post-snapshot mutations don't bleed
    through `restore()`. Customers and Products are immutable so
    shallow Map.from is fine for them.
  - Records syntax for order lines:
    `({String sku, int quantity})`.
  - Token IDs: `rsv-NNNNNN` zero-padded ascending. Order IDs:
    `ord-NNNNNN` zero-padded ascending.

Critical Dart specifics for the executor:
  - `new` is reserved; the enum value is `newly`.
  - Errors should `implements Exception` (not extend it).
  - Use `super.message` for forwarded constructor params in error subclasses.
  - Use `required this.x` named-param constructor pattern.
  - Use `package:shop/<path>.dart` for cross-file imports.
  - Maps with named values: `Map<String, T>.from(other)` for shallow,
    `other.map((k,v) => MapEntry(k, deepCopy(v)))` for deep.

For each file, give:
  - import declarations needed (with full package paths)
  - public symbols with full signatures (typed parameters and returns)
  - method/getter bodies described concretely (not pseudocode)
  - field declarations (typed, defaults where applicable)
  - constructor behavior and validations

CONTRACT BLOCKS — each `### lib/<path>.dart` section MUST end with a
```dart-contract
…
```
fenced block containing declaration-only Dart code: every public
class, field, constructor, getter, method, and enum that the executor
must produce, with full signatures and types but no method bodies
(end with `;` or `=> throw UnimplementedError();`). Constructors that
use `this.x` parameter init lists end with `;` and NO body — the
`const` modifier MUST be preserved on value types so test code can
construct them as `const Foo(...)`.

The contract block is the BINDING for the executor — every named
parameter, field, and method signature in the contract becomes a
hard commitment. A small downstream loop may ask you to AMEND a
specific contract block if the executor surfaces a missing symbol;
amendments are additive (you may add fields/params/methods, never
rename or remove).

Output the spec as raw markdown (NOT wrapped in any outer fenced
block). Organize as 9 sections each labeled exactly
`### lib/<path>.dart` in the listed order. Each section has the prose
description followed by its `dart-contract` fenced code block. The
inner `dart-contract` blocks must be the ONLY fenced code blocks in
the output — do not wrap the whole response in ```text``` or any
other outer fence, since 3-backtick fences do not nest.
"""


def call_opus(prompt: str, model: str = "opus") -> dict:
    """Stateless `claude -p` planner call (subscription-billed).

    Used for the bake-off comparison "no contract" vs "with contract"
    where amendments are deliberately disabled — keeps everything on
    the user's Claude Code subscription. The OpusSession path
    (src/opus_session.py) is reserved for hands-off automated
    benchmarks that need API-direct multi-turn.
    """
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
    # Only unwrap if Opus actually used an explicit text/markdown outer
    # fence. Optional language tag would falsely match between two
    # inner ```dart-contract``` fences and silently drop spec content.
    m = re.search(r"```(?:text|markdown)\s*\n(.*?)\n```",
                  opus_response, re.DOTALL)
    return m.group(1).strip() if m else opus_response.strip()


def extract_dart_contracts(spec_text: str) -> dict[str, str]:
    """Pull a `dart-contract` block out of every `### lib/...dart` section.

    Returns a dict mapping target file paths (e.g. "lib/x.dart") to the
    raw dart-contract block text. Files without a contract block are
    omitted; the amendment loop handles missing-contract recovery.
    """
    contracts: dict[str, str] = {}
    sections = split_spec_by_file(spec_text)
    fence_re = re.compile(
        r"```dart-contract\s*\n(.*?)\n```", re.DOTALL)
    for path, section in sections.items():
        m = fence_re.search(section)
        if m:
            contracts[path] = m.group(1).rstrip()
    return contracts


def split_spec_by_file(spec_text: str) -> dict[str, str]:
    """Split Opus's spec into per-file sections by `### lib/...dart` headers.

    Falls back to giving each task the full spec if headers aren't present.
    """
    sections: dict[str, str] = {}
    pattern = re.compile(r"^### (lib/\S+\.dart)\s*$", re.MULTILINE)
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


def parse_dart_test(stdout: str) -> tuple[int, int]:
    """Parse `dart test` output for passed and total test counts."""
    last_line = ""
    for line in stdout.splitlines():
        if "+" in line and ":" in line:
            last_line = line
    m_pass = re.search(r"\+(\d+)", last_line)
    m_fail = re.search(r"-(\d+)", last_line)
    p = int(m_pass.group(1)) if m_pass else 0
    f = int(m_fail.group(1)) if m_fail else 0
    return p, p + f


def grade(workspace: Path) -> dict:
    """Run the hidden test suite against the workspace's lib/."""
    grade_dir = Path(tempfile.mkdtemp(prefix="phC_inv_grade_"))
    shutil.copytree(workspace, grade_dir, dirs_exist_ok=True)
    (grade_dir / "test").mkdir(exist_ok=True)
    shutil.copy(HIDDEN_TEST, grade_dir / "test" / "shop_test.dart")
    pub_get = subprocess.run(
        ["dart", "pub", "get"], cwd=grade_dir,
        capture_output=True, text=True, timeout=180,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    if pub_get.returncode != 0:
        return {"passed": 0, "total": 28,
                "error": f"pub get failed: {pub_get.stderr[-300:]}",
                "grade_dir": str(grade_dir)}
    proc = subprocess.run(
        ["dart", "test", "test/shop_test.dart", "--reporter", "expanded"],
        cwd=grade_dir, capture_output=True, text=True, timeout=240,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    p, total = parse_dart_test(proc.stdout)
    if total == 0:
        total = 28  # known reference test count
    return {
        "passed": p, "total": total,
        "pass_rate": p / total if total else 0,
        "stdout_tail": proc.stdout[-2500:],
        "grade_dir": str(grade_dir),
    }


def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phC_dart_inv_"))
    (ws / "lib").mkdir()
    (ws / "lib" / "types").mkdir()
    (ws / "lib" / "services").mkdir()
    (ws / "test").mkdir()
    (ws / "pubspec.yaml").write_text(PUBSPEC, encoding="utf-8")
    (ws / ".loom-config.json").write_text(
        json.dumps({"test_runner": "dart_test", "model": "qwen3.5:latest"},
                   indent=2),
        encoding="utf-8",
    )
    for tf in TARGET_FILES:
        (ws / tf).write_text("", encoding="utf-8")
    (ws / BARREL_PATH).write_text(BARREL_CONTENT, encoding="utf-8")
    for tf, gate_path in GATING_TEST_TARGETS.items():
        (ws / gate_path).write_text(GATING_TESTS[tf], encoding="utf-8")
    pub = subprocess.run(
        ["dart", "pub", "get"], cwd=ws,
        capture_output=True, text=True, timeout=180,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    if pub.returncode != 0:
        raise RuntimeError(f"pub get failed in workspace: {pub.stderr[-500:]}")
    return ws


def run_one(run_id: str = "1") -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] workspace: {workspace}")

    store_dir = Path.home() / ".openclaw" / "loom" / PROJECT
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=PROJECT)

    # Step 1: Opus authors the spec.
    print(f"[opus] calling claude -p --model opus on README ...")
    readme = README.read_text(encoding="utf-8")
    planner_prompt = (
        f"Below is a benchmark README that describes a 9-file Dart "
        f"multi-service library named `shop`. Write a complete "
        f"implementation spec, organized as 9 `### lib/...dart` "
        f"sections so a downstream executor can produce each file in "
        f"a single replace pass. Each section MUST end with a "
        f"```dart-contract``` block per the system instructions. "
        f"Output raw markdown — do not wrap the response in any outer "
        f"fenced block. The dart-contract blocks must be the only "
        f"fenced code blocks in your output.\n\n"
        f"---README---\n{readme}\n---END README---"
    )

    # Subprocess `claude -p` for the planner — subscription-billed.
    # No persistent session; if loom_exec hits an architect-class
    # failure it logs a structured event but does not call Opus
    # automatically (LOOM_EXEC_AMEND_VIA_OPUS=0 by default).
    opus_t0 = time.time()
    opus_resp = call_opus(planner_prompt)
    opus_elapsed = time.time() - opus_t0
    spec_text = extract_spec(opus_resp["content"])
    sections = split_spec_by_file(spec_text)
    contracts = extract_dart_contracts(spec_text)
    print(f"[opus] {opus_elapsed:.1f}s  cost=${opus_resp['cost_usd']:.4f}  "
          f"spec_chars={len(spec_text)}  sections={len(sections)}  "
          f"contracts={len(contracts)}/{len(TARGET_FILES)}")

    # Step 2: Loom seeding — full-spec context + per-file contracts.
    req = services.extract(
        store, domain="behavior",
        value="Implement the dart-inventory multi-service library as specified.",
        rationale="Phase C dart-inventory benchmark — multi-file orchestration "
                  "test with cross-service contracts.",
    )
    spec = services.spec_add(store, req["req_id"], spec_text)
    # Per-file contract blocks are inlined inside the spec text already.
    # The standalone contract data plane was rolled back from main.
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
            created_by="opus_planner_dart_inventory",
        )
        task_ids.append(result["id"])

    # Step 3: loom_exec drains the queue. The "contract" cell of the
    # bake-off sets LOOM_EXEC_CONTRACT=1; the "no-contract" baseline
    # leaves it unset. LOOM_EXEC_AMEND_VIA_OPUS stays off — production
    # amendments go through the calling agent, not a separate API call.
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
    final_opus_cost = opus_resp["cost_usd"]

    summary = {
        "phase": "C_dart_inventory_oneshot_auto",
        "run_id": run_id,
        "benchmark": "dart-inventory",
        "planner": "opus(claude -p)",
        "executor": os.environ.get("PHC_EXEC_MODEL", "qwen3.5:latest"),
        "contract_enabled": exec_env.get("LOOM_EXEC_CONTRACT") == "1",
        "blueprint_enabled": os.environ.get("LOOM_EXEC_BLUEPRINT", "0") == "1",
        "passed": g["passed"], "total": g["total"],
        "pass_rate": g["pass_rate"],
        "opus_duration_s": round(opus_elapsed, 1),
        "opus_cost_usd": final_opus_cost,
        "opus_planner_cost_usd": opus_resp["cost_usd"],
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
    out_path = OUT_DIR / f"phC_dart_inv_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSUMMARY: pass={g['passed']}/{g['total']}  "
          f"opus=${final_opus_cost:.4f}+{opus_elapsed:.1f}s  "
          f"qwen={exec_elapsed:.1f}s  "
          f"amendments={summary['amendment_count']}({summary['amendments_recovered']}rec)  "
          f"wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    run_one(rid)
