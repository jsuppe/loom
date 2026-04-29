# Bakeoff V2 Milestone 7 — Typelink V1 Validation

**Date:** 2026-04-29
**Question:** Does the typelink v1 implementation (Stage 7.1 + 7.3)
intercept the typelink-shaped failures the FAILURE_AUDIT identified
(27/28 = 96.4% of multi-file failures)?
**Approach:** Re-run the dart-inventory benchmark N=5 with `LOOM_TYPELINK=1`
enabled, observe typelink behavior and per-task progression.
**N:** 5 trials × 9 tasks (with chain dependency) = up to 45 task
observations; in practice 9 observed before chain stops.
**Errors:** 0 (no harness crashes, no typelink exceptions, no extractor
errors).

---

## TL;DR

> Typelink v1 wiring is correct and fires per task as designed. The
> empirically larger lift came from a **prerequisite fix to the
> dart-inventory planner prompt** that was uncovered during the
> validation: an outer ```` ```text ``` ```` wrapping instruction was
> suppressing inner ```` ```dart-contract ``` ```` fences from making
> it through `extract_spec`, so 0/9 contracts reached the executor
> across 10 prior runs.
>
> Once the planner prompt was fixed (commit `7bb480f`), Opus emits
> 9/9 contract blocks per spec at ~22k spec_chars (up from 0/9 at
> 2-4k). With contracts now flowing into `Specification.public_api`
> via `services.spec_add` auto-extract, qwen produces public surfaces
> that match the contracts cleanly — typelink prints `ok` 9/9 times
> across observed tasks, `FAIL` 0 times.
>
> The failure mode shifted: where the broken-driver baseline (tlk1-5)
> failed on `Method not found: 'Address'` style typelink-shaped
> errors, the fixed-driver run (tlkv2_1-5) fails on body-level bugs
> (missing email validation, etc.) that typelink doesn't claim to
> catch.
>
> Both observations support the design: **(a) authorship-side**
> (contract auto-extract from spec) reduces typelink-shaped failures
> upstream by giving the executor a structural blueprint;
> **(b) verification-side** (post-task `typelink_fail` outcome) is
> the safety net for cases where surface drift slips through.
> Validating (b) at scale requires either decoupling the task
> dependency chain (so tasks 3-9 run regardless of task 2 outcome)
> or a deliberately stripped-spec control trial — both deferred.

---

## What was committed

### Commit `61996d2` — typelink v1 (Stage 7.1 + 7.3)

- `src/store.py`: `Specification.public_api_json` field +
  `set/get_public_api()`; `Symbol` and `TypeContract` dataclasses;
  `type_contracts` ChromaDB collection + CRUD; back-compat preserved
  via `setdefault`.
- `src/typelink.py` (new, 688 LoC): per-language `Verifier` registry
  (Python `ast`, Dart regex + balanced-paren walker), `diff_symbols()`
  emitting `missing_symbol` / `signature_mismatch` / `extra_symbol`
  Diffs, `is_additive()` for non-breaking-changes check,
  `extract_public_api_from_spec()` parsing `*-contract` fenced
  blocks per `### path/to/file.ext` heading.
- `src/services.py::spec_add`: auto-extracts public_api from the
  spec body so Opus's existing `dart-contract` / `python-contract`
  fences become structural commitments.
- `scripts/loom_exec`: `LOOM_TYPELINK=1` post-task hook between
  static_check and grading; on actionable diff returns
  `typelink_fail` outcome with structured Diff list.
- `scripts/loom`: `typelink {show, check, diff}` subcommands.
- `tests/test_typelink.py` (new, 16 tests): TestSpecPublicApi,
  TestPythonExtractor, TestDartExtractor, TestDiff,
  TestContractFenceExtraction. **216/216 total tests pass** across
  store + services + typelink suites.

### Commit `7bb480f` — dart-inventory planner fix

The validation surfaced an upstream bug: 10/10 prior dart-inventory
runs produced `contracts_initial=0/9` with `spec_chars=2-4k`, vs
python-inventory's 5/5 runs producing 9/9 with 24-31k chars. Same
prompt shape; Opus follows the dart instruction literally and
ignores it for python.

The failure mechanism: 3-backtick fences cannot nest, so Opus's
literal compliance with `Output ONE top-level ```text``` block`
collapsed the inner `dart-contract` blocks. The fix:
- Drop the outer wrap requirement; tell Opus to output raw markdown
  with `dart-contract` as the only fenced blocks.
- Tighten `extract_spec` regex from optional `(text|markdown)?` to
  required `(text|markdown)` — the optional group could falsely
  match between two adjacent inner contract fences.

---

## Empirical record

### Broken-driver baseline (tlk1-5) — pre-planner-fix

| trial | spec_chars | contracts | pass | task 2 failure |
|---|---|---|---|---|
| tlk1 | 2801 | 0/9 | 0/1 | `Method not found: 'Address'` |
| tlk2 | 3955 | 0/9 | 0/1 | (same shape) |
| tlk3 | 3077 | 0/9 | 0/1 | (same shape) |
| tlk4 | 4083 | 0/9 | 0/1 | (same shape) |
| tlk5 | 4668 | 0/9 | 0/1 | (same shape) |

All 5 trials: chain stops at task 2 because qwen generated a
Customer class without the Address sibling type → typelink-shaped
failure (missing class). Typelink couldn't intercept because
`spec.public_api` was empty (no contract to compare against).

### Fixed-driver run (tlkv2_1-5) — post-planner-fix, LOOM_TYPELINK=1

| trial | spec_chars | contracts | pass | typelink_ok | typelink_fail | task 2 failure |
|---|---|---|---|---|---|---|
| tlkv2_1 | 21753 | 9/9 | 0/1 | 2 | 0 | email validation missing (body) |
| tlkv2_2 | 21895 | 9/9 | 0/1 | 2 | 0 | (body-level) |
| tlkv2_3 | 21490 | 9/9 | 0/1 | 2 | 0 | (body-level) |
| tlkv2_4 | 22084 | 9/9 | 0/1 | 1 | 0 | (body-level) |
| tlkv2_5 | 21905 | 9/9 | 0/1 | 2 | 0 | (body-level) |
| **total** | — | **45/45** | 0/5 | **9** | **0** | — |

### What the data shows

1. **Wiring is correct.** 9 typelink_ok prints across 5 trials,
   0 errors. The check fires per task, dispatches to the right
   verifier via `runner.fence`, compares spec contract to extracted
   surface, and silently passes when they match.
2. **Authorship-side intervention has measurable lift.** With
   contracts in the spec, qwen's Customer class includes Address;
   the broken-driver case omitted Address entirely. Failure type
   moved from "missing class" (typelink-shaped) to "missing
   validation logic" (body-level).
3. **Verification-side intervention had no material to fire on.**
   In 9 task observations, qwen's public surfaces matched the
   contracts. `typelink_fail` did not fire. Whether that's because
   the verifier is over-permissive or because qwen's surface
   compliance is genuinely high under contract guidance is
   unobservable without further trials.
4. **Pass rate identical (0/5 in both)** — but for different
   reasons. Broken driver: chain stops at task 2 due to typelink-
   shaped failure. Fixed driver: chain stops at task 2 due to
   body-level bug. Hidden grading sees the same incomplete
   workspace either way.

### Pass-rate is the wrong metric here

Both broken and fixed runs end at 0/1 pass because the dart-inventory
driver uses sequential chain dependencies: each task depends on the
previous. When task 2 fails (for any reason), tasks 3-9 don't run,
and hidden grading runs against a workspace with 7/9 files empty.
The hidden test errors are dominated by `Method not found: 'OrderService'`
type errors that are **artifacts of incomplete workspace**, not of
incorrect code.

To get a clean signal on typelink_fail behavior, the experimental
design needs adjustment: either (a) decouple the chain so tasks 3-9
run independently (with their own scratch state), or (b) deliberately
strip contracts from a control trial to see typelink_fail surface
clearly.

---

## Limitations and follow-on

- **Observability gap:** 9 task observations across 5 trials is a
  thin sample for binomial inference. With chain dependency stopping
  the run at task 2, we cannot observe typelink behavior on the
  more complex tasks 3-9 (services with cross-file dependencies).
- **Verifier sensitivity unknown.** typelink_fail fired 0 times.
  Either qwen's surface compliance is genuinely high under contract
  guidance, or the diff_symbols logic under-detects mismatches.
  Adding a deliberately-bad test case (mock executor that omits a
  field) would settle this.
- **Audit reclassification.** The FAILURE_AUDIT's "27/28 typelink-
  shaped" claim was based on data where contracts were 0/9 (the
  broken-driver state). With contracts at 9/9, the failure
  distribution shifts. The audit's headline rate is best read as
  "fraction of failures that the typelink data plane could in
  principle address" rather than "fraction the verifier will catch
  in production." Most of the lift looks to be on the authorship
  side, not the verification side.

### Recommended next experiments

1. **Decoupled-chain dart-inventory N=5.** Modify driver so each
   task creates an independent scratch + skips chain depends_on.
   Lets us observe typelink behavior on tasks 3-9.
2. **Stripped-spec control N=5.** Run with the fixed driver but
   programmatically remove `dart-contract` blocks from the spec
   before `services.spec_add`. Forces typelink to operate on
   broken-driver-shaped specs with the fix in place. Confirms
   verifier doesn't fire on empty-contract spec, and characterizes
   what failures look like with no structural blueprint.
3. **python-inventory regression with LOOM_TYPELINK=1.** Already
   100/100 hidden tests passing. Confirm no regression and observe
   typelink behavior on a benchmark where qwen consistently produces
   correct surfaces.
4. **Mock-bad-executor unit test.** In `tests/test_typelink.py`,
   add a regression test: known-good contract + deliberately
   stripped Customer.email field in qwen output → assert
   `typelink_fail` with `missing_symbol` Diff. Validates verifier
   sensitivity in isolation, no full benchmark run needed.

---

## Files of record

- `experiments/bakeoff/runs-v2/phC_dart_inv_runtlkv2_{1..5}_summary.json`
  — fixed-driver N=5 trial summaries
- `experiments/bakeoff/runs-v2/phC_dart_inv_runtlkv2_smoke_summary.json`
  — single-trial smoke that confirmed the planner fix
- `experiments/bakeoff/runs-v2/phC_dart_inv_runtlk{1..5}_summary.json`
  — broken-driver baseline (kept as historical evidence of the
  contract-suppression bug)
- `src/typelink.py`, `tests/test_typelink.py` — implementation
- `experiments/bakeoff/FAILURE_AUDIT.md` — pre-implementation
  audit that motivated the design
- `docs/TYPELINK_DESIGN.md` — design document
