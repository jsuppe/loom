# js-singlefile benchmark

Three single-file JavaScript scenarios for M22e (workload-arm pivot from
M22c). Each scenario is one source file under `src/` with a corresponding
oracle test file under `test/`. Uses Node's built-in test runner (Node 22+);
no external dependencies.

## Scenarios

| target | concern | sub-tests |
|---|---|---|
| `src/validate.js` | declarative input validation with error aggregation | ~25 |
| `src/aggregate.js` | group-by + reduce data transformation with immutability | ~25 |
| `src/retry.js` | async retry wrapper with retriable vs terminal error classification | ~25 |

## Running

```bash
node --test test/                  # all
node --test test/validate_test.js  # one
```

Each reference solution passes 100% of its oracle sub-tests.

## Why this benchmark

Built for M22e to replicate the M22c hook-rationale study on a workload
where the M22c-identified confound (file-layout hallucination from
training-data priors, REQ-7e2d6518) cannot operate: layout is explicit
in the prompt, ES module imports are stable JS convention.

The 4-arm comparison (no_context / hook_rationale / hook_fact / placebo)
is unchanged from M22c. The model is `qwen3.5:latest` for both M22c
and M22e (isolating workload as the changed variable).

See `../../m22e_pilot/M22E_PREREGISTRATION.md` for the locked design.
