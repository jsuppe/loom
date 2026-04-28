#!/usr/bin/env python3
"""
Phase C — C++ multi-header inventory benchmark.

Direct sibling of phC_python_inventory and phC_dart_inventory. Same
domain (customers + products + inventory + orders + persistence),
same 28-test scope, same 8-task structure. Used to disambiguate
H1 (Dart-specific qwen blind spots) vs H2 (general complexity
ceiling) for the dart-inventory result.

Like cpp-orders, this driver BYPASSES loom_exec — the .hpp gating
contract doesn't fit the pytest/dart_test runners loom_exec knows.
Instead, the driver calls Ollama directly per file in topological
order, then grades by g++ + ./test_runner.

Default executor: qwen3.5:latest. Override via PHC_EXEC_MODEL.
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
BENCHMARK_DIR = BAKEOFF_DIR / "benchmarks" / "cpp-inventory" / "ground_truth"
HIDDEN_TEST = BENCHMARK_DIR / "tests" / "shop_test.cpp"
README = BENCHMARK_DIR / "README.md"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass


PROJECT = "phC_cpp_inventory_oneshot_auto"
OLLAMA_URL = "http://localhost:11434/api/generate"

# Tasks run in topological order: errors → types → persistence → services.
TARGET_FILES = [
    "include/errors.hpp",
    "include/types/customers.hpp",
    "include/types/products.hpp",
    "include/types/inventory.hpp",
    "include/types/orders.hpp",
    "include/persistence.hpp",
    "include/services/customer_service.hpp",
    "include/services/inventory_service.hpp",
    "include/services/order_service.hpp",
]
BARREL_PATH = "include/shop.hpp"
BARREL_CONTENT = """\
// shop.hpp — barrel header re-including the public API.
//
// Pre-written by the Phase C cpp-inventory driver; not a qwen task.
#pragma once

#include "errors.hpp"
#include "persistence.hpp"
#include "services/customer_service.hpp"
#include "services/inventory_service.hpp"
#include "services/order_service.hpp"
#include "types/customers.hpp"
#include "types/inventory.hpp"
#include "types/orders.hpp"
#include "types/products.hpp"
"""


PLANNER_SYSTEM = """\
You are a senior C++ architect writing an implementation specification
for a header-only multi-service C++20 library named `shop`. The
downstream executor is a small local model (qwen3.5, 9.7B parameters)
that will write each header in a single replace-mode pass. Your spec
must be self-contained, exhaustive about C++20 specifics, and
explicit about which symbols live in which header.

The library is split across 9 implementation headers (the barrel
include/shop.hpp re-including these is pre-written by the harness;
do NOT include a section for it):

  include/errors.hpp                         — domain error hierarchy
  include/types/customers.hpp                — Customer + Address
  include/types/products.hpp                 — Product
  include/types/inventory.hpp                — StockLevel + ReservationToken
  include/types/orders.hpp                   — Item, Transition, Order, OrderStatus, OrderLine helper
  include/persistence.hpp                    — Store + Snapshot
  include/services/customer_service.hpp      — CustomerService
  include/services/inventory_service.hpp     — InventoryService
  include/services/order_service.hpp         — OrderService

Cross-file commitments to fix early in your spec:
  - All errors derive from `class DomainError : public std::runtime_error`.
    Every subclass uses `using DomainError::DomainError;` to inherit
    constructors. Do NOT add fields or override what.
  - Keep the EXACT subclass names listed in the README — tests assert
    on type. Do not invent merged or renamed errors.
  - `OrderStatus` is `enum class`: `New, Paid, Shipped, Delivered, Cancelled`.
  - `Item` validates in constructor: quantity > 0, unit_price >= 0.
    `double line_total() const` returns quantity * unit_price.
  - `Order::status` is mutable; `Order::history` is `std::vector<Transition>`.
  - `Transition::from_status` is `std::optional<OrderStatus>` (nullopt
    on the initial creation record).
  - `StockLevel` constructor takes ONLY `std::string sku_` (other
    fields default to 0). Method `int available() const`.
  - `ReservationToken` has mutable `bool committed = false, released = false`.
    `bool is_open() const` returns `!committed && !released`.
  - `Store::snapshot()` value-copies the five maps. `Store::restore(snap)`
    assigns each member from the snapshot.
  - `OrderLine` is a small helper struct `{std::string sku; int quantity;}`
    used as input to `OrderService::place(...)`.
  - Token IDs `rsv-NNNNNN` and Order IDs `ord-NNNNNN` use
    `std::ostringstream` + `std::setw(6) << std::setfill('0')`.

Critical C++20 specifics for the executor:
  - Header-only library: each header has `#pragma once` at top.
  - Standard library only — NO third-party deps (boost, fmt, doctest,
    Catch2, etc.). The benchmark workspace has nothing extra installed.
  - Every service's constructor takes `Store&` (reference, not pointer
    or value) and stores it as `Store& store_;` member.
  - `OrderService` constructor takes `Store&, CustomerService&, InventoryService&`.
  - Use `std::map<std::string, T>` (NOT `std::unordered_map`) so test
    iteration order is stable.
  - Methods on services return references (e.g. `Customer&`,
    `Order&`) NOT values, so test code can chain operations.
  - Errors thrown by std::runtime_error subclasses use string-only
    constructors; concatenate via `std::string("a") + "b"` or use
    `std::to_string(int)` for numeric values.
  - The barrel re-includes every public header.

For each header, give:
  - `#include` declarations needed (with relative paths)
  - public class/struct signatures
  - constructor behavior including validations
  - method signatures + concrete bodies (no pseudocode)
  - field declarations with types and defaults

CONTRACT BLOCKS — each `### include/<path>.hpp` section MUST end with a
```cpp-contract
…
```
fenced block containing declaration-only C++ code: every public
class/struct, field, constructor, method, and enum that the executor
must produce, with full signatures and types but no method bodies.
Constructors with member init lists may end with `;` and no body.

Output ONE top-level ```text``` block wrapping the whole spec.
Inside it, organize as 9 sections each labeled exactly
`### include/<path>.hpp` (matching the file paths above), in the
listed order. Each section has the prose description followed by its
`cpp-contract` block.
"""


def call_opus(prompt: str, model: str = "opus") -> dict:
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
    pattern = re.compile(r"^### (include/\S+\.hpp)\s*$", re.MULTILINE)
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


def call_ollama(prompt: str, model: str, retries: int = 3) -> dict:
    """Direct Ollama call with simple retry — bypasses loom_exec.

    qwen2.5-coder:32b runner has been seen to crash mid-session with
    HTTP 500 ("llama runner has terminated"). When that happens, the
    Ollama daemon usually recovers if you give it a few seconds.
    Retry up to `retries` times with exponential backoff before
    giving up.
    """
    import urllib.request
    import urllib.error
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }).encode()
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                OLLAMA_URL, data=body,
                headers={"Content-Type": "application/json"},
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode())
            return {"response": data.get("response", ""),
                    "elapsed_s": round(time.time() - t0, 1),
                    "attempts": attempt}
        except urllib.error.HTTPError as e:
            last_err = e
            wait = 5 * attempt  # 5s, 10s, 15s
            print(f"[qwen] HTTP {e.code} on attempt {attempt}/{retries}; "
                  f"retrying in {wait}s")
            time.sleep(wait)
        except Exception as e:
            last_err = e
            wait = 5 * attempt
            print(f"[qwen] {type(e).__name__}: {e} on attempt {attempt}/{retries}; "
                  f"retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"ollama failed after {retries} attempts: {last_err}")


def extract_cpp(text: str) -> str:
    for fence in ("cpp", "c++"):
        m = re.search(rf"```{re.escape(fence)}\s*\n(.*?)\n```",
                      text, re.DOTALL)
        if m: return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)\n```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def parse_runner_output(stdout: str) -> tuple[int, int]:
    p = f = 0
    for line in stdout.splitlines():
        m = re.search(r"(\d+)\s+passed,\s*(\d+)\s+failed", line)
        if m:
            p, f = int(m.group(1)), int(m.group(2))
            break
    return p, p + f


def grade(workspace: Path) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix="phC_cpp_inv_grade_"))
    # Copy entire include tree
    shutil.copytree(workspace / "include", grade_dir / "include")
    (grade_dir / "test").mkdir()
    shutil.copy(HIDDEN_TEST, grade_dir / "test" / "shop_test.cpp")
    compile_proc = subprocess.run(
        ["g++", "-std=c++20", "-I", "include",
         "test/shop_test.cpp", "-o", "test_runner.exe"],
        cwd=grade_dir, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
        shell=(sys.platform == "win32"),
    )
    if compile_proc.returncode != 0:
        return {"passed": 0, "total": 28,
                "pass_rate": 0.0,
                "compile_failed": True,
                "stdout_tail": compile_proc.stderr[-2500:],
                "grade_dir": str(grade_dir)}
    run_proc = subprocess.run(
        [str(grade_dir / "test_runner.exe")],
        cwd=grade_dir, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
        shell=(sys.platform == "win32"),
    )
    p, total = parse_runner_output(run_proc.stdout)
    if total == 0:
        total = 28
    return {
        "passed": p, "total": total,
        "pass_rate": p / total if total else 0,
        "compile_failed": False,
        "stdout_tail": run_proc.stdout[-2000:] + run_proc.stderr[-500:],
        "grade_dir": str(grade_dir),
    }


def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phC_cpp_inv_"))
    (ws / "include").mkdir()
    (ws / "include" / "types").mkdir()
    (ws / "include" / "services").mkdir()
    # Pre-write the barrel
    (ws / BARREL_PATH).write_text(BARREL_CONTENT, encoding="utf-8")
    return ws


def run_one(run_id: str = "1") -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] workspace: {workspace}")

    # Step 1: Opus authors the spec (fresh or cached)
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
            f"Below is a benchmark README that describes a 9-header C++20 "
            f"multi-service library named `shop`. Write a complete "
            f"implementation spec, organized as 9 `### include/...hpp` "
            f"sections so a downstream executor can produce each header in "
            f"a single replace pass. Each section MUST end with a "
            f"```cpp-contract``` block per the system instructions. "
            f"Output ONLY a ```text``` block.\n\n"
            f"---README---\n{readme}\n---END README---"
        )
        opus_t0 = time.time()
        opus_resp = call_opus(planner_prompt)
        opus_elapsed = time.time() - opus_t0
        print(f"[opus] {opus_elapsed:.1f}s  cost=${opus_resp['cost_usd']:.4f}")

    spec_text = extract_spec(opus_resp["content"])
    sections = split_spec_by_file(spec_text)
    print(f"[opus] spec_chars={len(spec_text)}  sections={len(sections)}")

    # Step 2: per-file Ollama calls in topological order. Each call sees
    # the full spec PLUS a pointer at its target section. After each file
    # is written, the next file's qwen call sees prior files in the spec.
    exec_model = os.environ.get("PHC_EXEC_MODEL", "qwen3.5:latest")
    qwen_total_elapsed = 0.0
    file_outcomes = {}
    for tf in TARGET_FILES:
        section = sections.get(tf, spec_text)
        prompt = (
            f"You are writing the file `{tf}` for the multi-header C++20 "
            f"library `shop`. Below is the complete implementation spec; "
            f"focus on the section labeled `### {tf}`. Standard library "
            f"only (no third-party deps). Header-only style with `#pragma "
            f"once`. Output ONE ```cpp``` code block containing the COMPLETE "
            f"header file. Nothing before or after the fence.\n\n"
            f"---SPEC---\n{spec_text}\n---END SPEC---\n\n"
            f"Write `{tf}` per the section labeled `### {tf}` in the spec.\n"
        )
        try:
            qwen_resp = call_ollama(prompt, exec_model)
        except Exception as e:
            print(f"[qwen] {tf}: ollama error: {e}")
            file_outcomes[tf] = {"error": str(e)}
            continue
        code = extract_cpp(qwen_resp["response"])
        out_path = workspace / tf
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(code, encoding="utf-8")
        qwen_total_elapsed += qwen_resp["elapsed_s"]
        file_outcomes[tf] = {
            "elapsed_s": qwen_resp["elapsed_s"],
            "code_chars": len(code),
        }
        print(f"[qwen] {tf}: {qwen_resp['elapsed_s']}s  {len(code)} chars")

    # Step 3: hidden grading — g++ compile + run
    g = grade(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}  "
          f"compile_failed={g.get('compile_failed', False)}")

    summary = {
        "phase": "C_cpp_inventory_oneshot_auto",
        "run_id": run_id,
        "benchmark": "cpp-inventory",
        "planner": "opus(claude -p)",
        "executor": exec_model,
        "passed": g["passed"], "total": g["total"],
        "pass_rate": g["pass_rate"],
        "compile_failed": g.get("compile_failed", False),
        "opus_duration_s": round(opus_elapsed, 1),
        "opus_cost_usd": opus_resp["cost_usd"],
        "spec_chars": len(spec_text),
        "spec_sections_found": list(sections.keys()),
        "qwen_total_elapsed_s": round(qwen_total_elapsed, 1),
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "grade_dir": g["grade_dir"],
        "file_outcomes": file_outcomes,
        "grade_stdout_tail": g.get("stdout_tail", ""),
    }
    out_path = OUT_DIR / f"phC_cpp_inv_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSUMMARY: pass={g['passed']}/{g['total']}  "
          f"opus=${opus_resp['cost_usd']:.4f}+{opus_elapsed:.1f}s  "
          f"qwen={qwen_total_elapsed:.1f}s  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    run_one(rid)
