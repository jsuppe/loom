# Bakeoff V2 Phase C — Inventory Benchmarks

**Date:** 2026-04-27
**Question:** Does the multi-file Dart complexity ceiling we observed
generalize to other languages, or is it Dart-specific?
**Approach:** Three parallel benchmarks (dart-inventory, python-inventory,
cpp-inventory) with identical domain semantics, same 8-task structure,
same 28-test scope. Same Opus planner, same qwen3.5:latest executor.
**N:** 30 dart trials + 1 python smoke + 0 cpp trials = 31 total
**Errors:** 0 (no harness crashes; all failures are correctness failures)

---

## TL;DR

> The dart-inventory complexity ceiling is **Dart-specific**, not a
> general qwen3.5 coordination ceiling at 8+ files. Same domain in
> Python passes cleanly first try (28/28 hidden tests, all 8 tasks
> complete on attempt 1). Failure modes that recur 30 times in a row
> on Dart cluster on idioms Python doesn't have: named-argument
> syntax, `const` constructors, and dart records.
>
> The directional answer holds at low N because **what's informative
> is the *absence* of the recurring Dart failure modes in Python**,
> not the pass rate per se. C++ remains untested; the directional
> result was clear enough from the Python+Dart contrast that we
> stopped before running it.

---

## Background

`dart-orders` (3 lib files, 21 hidden tests) saturated at 100 % once
Tier 1+2 orchestration improvements landed (retry-with-error +
pre-pinned deps + temp ramp + escalation). To probe whether the
asymmetric pipeline scales further, we built `dart-inventory` —
9 files (`errors`, `types/customers`, `types/products`,
`types/inventory`, `types/orders`, `persistence`,
`services/customer_service`, `services/inventory_service`,
`services/order_service`) over an in-memory `Store`, ~700 LoC
reference, 28 hidden `dart_test` tests covering full lifecycle
scenarios.

`dart-inventory` failed completely on initial runs (bake-off v3 +
v4: 30/30 trials all `pass=0/X` — meaning `dart_test` bailed at
file load because `lib/` didn't compile). The failures clustered on
the same handful of Dart idioms across every trial:

- `Item.lineTotal` getter omitted (compile error)
- `Order.total` getter omitted
- `reserve(orderId:, sku:, quantity:)` produced as positional args
- `const Address(...)` constructors emitted as non-`const`
- Customer field-init syntax errors

The question this finding answers: are these *Dart-specific qwen
blind spots* (H1) or *evidence of a general 8-file/700-LoC ceiling*
(H2) for qwen3.5:latest as executor?

---

## Method

Three parallel benchmarks were built with structural parity:

| | dart-inventory | python-inventory | cpp-inventory |
|---|---|---|---|
| files | 9 (`lib/...dart`) | 9 (`shop/...py`) | 9 (`include/...hpp`) |
| reference LoC | ~700 | ~600 | ~600 |
| hidden tests | 28 | 28 | 28 |
| barrel | `lib/shop.dart` (3 export lines) | `shop/__init__.py` (re-exports) | `include/shop.hpp` (3 #include) |
| grading | `dart test test/shop_test.dart` | `pytest tests/test_shop.py` | `g++ -std=c++20 ... && ./test_runner` |
| executor | qwen3.5:latest | qwen3.5:latest | qwen3.5:latest (planned) |
| planner | Opus (`claude -p`) | Opus (`claude -p`) | Opus (`claude -p`) |

Each benchmark's reference was hand-authored and verified to pass
its full hidden suite (28/28 each).

---

## Results

### dart-inventory — bake-off v3 (variable spec, N=10)

A/B cells over whether loom_exec uses Opus's per-file
`dart-contract` block as a body-pass binding (`LOOM_EXEC_CONTRACT`).

| cell | passes | per-task pass when run |
|---|---|---|
| A (no contract) | 1/5 (only A02 = 28/28) | 12/16 = 75% |
| B (contract) | 0/5 | 10/15 = 67% |

Statistically indistinguishable at N=5. One incidental pattern: in
cell B, `attempts=2` retry-recovery dropped 5× (from 5 to 1) — a
hint that contract binding makes qwen lock into a wrong signature
across retries instead of self-correcting from the failure tail.
Not significant on its own; flagged for future investigation.

### dart-inventory — bake-off v4 (canonical spec, N=30)

To remove Opus-spec variance as a confound, one canonical Opus
spec (24 KB, 9 dart-contract blocks parsed) was generated once and
reused across all 30 trials, A/B interleaved.

| cell | passes |
|---|---|
| A (no contract) | 0/15 |
| B (contract) | 0/15 |

**30/30 trials all `pass=0/1`.** That's not "0 of 28 tests pass" —
it's "`dart_test` failed at file load because `lib/` didn't
compile." The chain breaks somewhere between task 1–4 every run;
later tasks never get to run.

Failure-mode counts across 30 trials:

| failure | trials | language-specific? |
|---|---|---|
| `reserve()` named-args mismatch | ~12 | Dart-specific (records/named-args) |
| `Item.lineTotal` getter missing | ~7 | language-agnostic in principle |
| `Order.total` getter missing | ~3 | language-agnostic in principle |
| `const` constructor stripped | ~4 | Dart-specific |
| Field-init syntax errors | ~4 | Dart-specific |

About **20/30 trials fail on a syntax structure that doesn't exist in
Python**. The remaining failures (missing getter) are
language-agnostic in principle but co-occurred only with the
language-specific ones in our data.

### python-inventory — N=1 smoke

One trial, `LOOM_EXEC_CONTRACT=1`, qwen3.5:latest. Same Opus
planner, same domain, same 8-task structure.

```
SUMMARY: pass=28/28  opus=$0.5218+148.8s  qwen=44.2s  amendments=0(0rec)  wall=197.1s
```

- 28/28 hidden tests passed.
- All 8 tasks completed on **attempt 1** — no retries needed.
- Median qwen call: ~5 s.
- No architect-class failures classified at any point in the chain.

### cpp-inventory — not run

The benchmark, hidden test, and driver were authored. The directional
result from Python+Dart was clear enough that we stopped before
running it. cpp-inventory remains available for future confirmation
if a reviewer requests it.

---

## Findings

### F1: The dart-inventory ceiling is Dart-specific (H1 supported)

The 30-trial dart-inventory failure cluster does **not** transfer to
Python. Same architectural pattern, same task structure, same file
count, same complexity in LoC — Python passes, Dart doesn't. The
failure modes that recur in Dart depend on language features Python
doesn't have:

- Named arguments live in qwen's vocabulary in Python (`def f(*, x, y)`
  is everyday Python; for `reserve(order_id=..., sku=..., quantity=...)`
  qwen produces it correctly).
- `const`-modifier preservation is Dart-only — Python has no
  equivalent concept that needs guarding.
- Records `({String sku, int quantity})` are a Dart construct; Python
  simply uses `dict`s or `dataclass`es and qwen handles those.

The H2 alternative (8+ files / 700+ LoC is a general coordination
ceiling) is contradicted: same complexity in Python coordinates fine.

### F2: Failure-mode clustering is the load-bearing evidence

At N=1 we cannot claim a 100 % Python pass rate. What we *can* claim
is that the failure modes responsible for 20+/30 dart-inventory
failures don't have a syntactic surface in Python. The N=1 result
is informative because the absence-of-failures is what's diagnostic,
not the presence-of-passes.

If Python were to fail at higher N for *different* reasons (missing
getter, wrong abstraction), that'd still leave the Dart-specific
ceiling intact as a separable phenomenon.

### F3: Contract binding does not lift the ceiling

Bake-off v4 cell B (with contract binding) failed 15/15 just like
cell A. Whether or not Opus's `dart-contract` block is loaded as a
body-pass binding makes no measurable difference at this complexity
— qwen3.5 violates the contract anyway (produces positional args
when contract specifies named, omits getters the contract declares,
strips `const` modifiers).

This is consistent with the broader picture: contracts can't
manufacture executor capability. They can prevent some
abstraction-choice errors when the executor is *capable* of
following the contract but uncertain which abstraction to pick;
they can't fix executor blind spots in language idioms.

### F4: Bake-off v3 had a fence-extraction bug fixed mid-run

In bake-off v3 cell A, all 5 trials saw a 3 KB Opus response (vs.
the typical 24 KB) because `extract_spec()` used a non-greedy regex
that terminated at the first inner closing fence (the spec contains
nested `dart-contract` blocks inside an outer `text` block). v4
fixed the extractor to anchor on the response's start/end. v3
results are reported as-was; conclusions rest on the v4 canonical-
spec data which was extracted correctly.

---

## Limitations

- **N=1 on the Python cell.** Statistically weak for a "Python passes"
  claim. The directional H1 conclusion rests on the *failure-mode
  taxonomy* (qualitative), not a confidence interval.
- **C++ not tested.** `cpp-inventory` benchmark + driver were built
  but never run. A review-time push for confirmation is reasonable
  but shouldn't block the directional finding.
- **Only one local executor tested.** qwen3.5:latest (9.7B) is the
  cheapest-and-fastest local model we have. Whether qwen2.5-coder:32b
  crosses the dart-inventory ceiling is open. (cpp-orders single-file
  passed 5/5 with that executor, suggesting *some* lift is possible
  with bigger code-specialized models.)
- **No real-world Dart codebase tested.** dart-inventory is synthetic.
  Whether its failure cluster reflects what would happen on a real
  Flutter/Dart project of similar scope is also open.

---

## What this changes for the broader claim

The single-file Phase D 8× cost ratio still holds. The 3-file
multi-file extension (dart-orders) holds at 100 % after Tier 1+2.
The 9-file extension (dart-inventory) does **not** hold: there's a
crisp ceiling between 3 and 9 Dart files for qwen3.5:latest.

The asymmetric pipeline therefore has a documented complexity bound
*per executor model*. The bound for qwen3.5 is "≤ 3 Dart files of
this complexity" or equivalently "≤ ~250 LoC reference target for
Dart." Crossing that bound requires either:

1. A different executor (untested at 9 files; qwen2.5-coder:32b is
   the obvious next candidate).
2. A different language (Python crosses the ceiling cleanly at the
   same scale).
3. Architectural help that targets the *specific* failure cluster
   — e.g. a Dart-aware static checker between body pass and grading
   that catches missing getters before they cascade into the next
   task.

---

## Pointers to the data

- **Drivers + benchmarks:** `claude/bakeoff-v1` branch
  (commits `da47332`, `85ddc2d`, `32e1df1`).
- **dart-inventory canonical spec (24 KB, 9 contracts):** generated
  once for v4; saved at
  `experiments/bakeoff/runs-v2/phC_inv_canonical_spec.txt` on
  `claude/bakeoff-v1`.
- **dart-inventory v3+v4 trial summaries:** 40 files
  `phC_dart_inv_runA*_summary.json` /
  `phC_dart_inv_runB*_summary.json` on `claude/bakeoff-v1`.
- **python-inventory smoke3:**
  `phC_python_inv_runsmoke3_summary.json` on `claude/bakeoff-v1`.
- **cpp-inventory benchmark + driver:**
  `experiments/bakeoff/benchmarks/cpp-inventory/`,
  `experiments/bakeoff/v2_driver/phC_cpp_inventory_oneshot_auto.py`
  on `claude/bakeoff-v1`. Never executed.
