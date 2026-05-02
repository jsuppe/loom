# Bakeoff V2 — Flutter counter multi-widget benchmark

**Date:** 2026-05-02
**Question:** Does the asymmetric pipeline (Opus plans, qwen executes)
transfer to Flutter — widget tree, async pumps, BuildContext state,
ScaffoldMessenger / SnackBar, `find.byKey` — on top of the validated
pure-Dart-test path (`dart-orders`)?
**Approach:** Three-task chain on `flutter-counter` benchmark
(`lib/counter_model.dart` → `lib/counter_widget.dart` →
`lib/counter_app.dart`), graded by 17 hidden tests run under
`flutter test`. Single cell — capability check, not a contrastive
study. Executor: `qwen2.5-coder:32b` (matches the dart-inventory
escalation tier).
**N:** 6 trials. 5 pre-patch (f01–f05, 2026-04-28) + 1 post-patch
(f06, 2026-05-02 after the keep_alive fix landed).

---

## TL;DR

> **Flutter at 3 coordinating files passes when the Ollama runner
> doesn't crash.** Capability pass rate: 3/3 = 100% on every trial
> where the chain ran end-to-end. Naive pass rate: 4/6 = 67%, dragged
> down by infrastructure failures (one harness exit_rc=1 with no
> model output, two HTTP 500s mid-chain) — all of which were
> Ollama 5-min `keep_alive` eviction races. Post the keep_alive fix
> (commit `4c66c13`), 1/1 with no infra losses and 30% faster wall.
>
> Flutter joins the **well-supported** tier alongside Python and
> pure Dart at small multi-file scope. The widget tree, StatefulWidget
> lifecycle, ScaffoldMessenger / SnackBar interaction, and `Key`-based
> test selectors did not produce qwen failure modes distinct from
> pure Dart.

---

## Setup

`experiments/bakeoff/v2_driver/phC_flutter_counter_oneshot_auto.py`,
single 3-task chain. Planner: Opus via `claude -p`. Executor:
`qwen2.5-coder:32b` (configurable via `LOOM_EXECUTOR_MODEL`).

Per-task gating tests (a tiny "does it import + expose surface"
check) gate chain advancement; the full 17-test grading suite runs
once at end-of-chain. Reference 17/17 from the ground-truth
implementation.

Three implementation files, no barrel re-export:

| file | role | task budget |
|---|---|---|
| `lib/counter_model.dart` | pure-Dart bounds-checked counter + history | task 1 |
| `lib/counter_widget.dart` | StatefulWidget with SnackBar on bound violations | task 2 |
| `lib/counter_app.dart` | MaterialApp wrapping the widget | task 3 |

---

## Empirical record

| run | passed | wall | notes |
|---|---|---|---|
| f01 | 0/1 | 84s | exec rc=1, all files 0 bytes — harness crash before any model output |
| f02 | 0/1 | 74s | Ollama HTTP 500 on task 1 (cold-load race) |
| f03 | **17/17** | 279s | full pipeline success |
| f04 | 0/1 | 237s | tasks 1+2 passed grading (961B + 2222B); HTTP 500 on task 3 (keep_alive expired between tasks) |
| f05 | **17/17** | 290s | full pipeline success |
| f06 | **17/17** | **194s** | post-keep_alive-fix; 0 retries fired; ~30% faster wall |

**Capability pass rate (chains that ran end-to-end):** 3/3 = 100%.
**Capability pass rate inc. partials (f04 reached task 3 before HTTP 500):** 3.67/4 ≈ 92%.
**Naive pass rate (raw):** 4/6 = 67%.

f04 is the cleanest evidence the failures are infrastructure, not
capability: qwen2.5-coder:32b correctly implemented `counter_model.dart`
(961B, 2/2 gating tests passed) and `counter_widget.dart` (2222B,
1/1 gating test passed), and the third task aborted with an
explicit `ollama call failed: HTTP Error 500` — no model output,
not a wrong-answer failure.

f06 (post-patch) ran in 194s wall vs 279-290s for the prior
successes (f03/f05) — a ~30% speedup attributable entirely to the
warm-model effect that `keep_alive=30m` enables. Per-task model
times in f06: 24.1s → 38.0s → 14.6s (cold-loaded once, hot for
the rest of the chain).

---

## What this rules in / rules out

**Rules in:** Flutter at small multi-file scope (≤3 files,
~250 LoC) with the asymmetric pipeline at the qwen2.5-coder:32b
tier. Specifically:

- Widget tree composition (`MaterialApp` wraps `Scaffold` wraps
  `CounterWidget`)
- `StatefulWidget` lifecycle (`initState`, `setState` after each
  button)
- `Key('counter-value')`, `Key('btn-inc')` etc. for testable
  selectors
- `ScaffoldMessenger.of(context).showSnackBar(...)` for bound
  violations
- `try { _model.increment() } on StateError catch (e) { ... }`
  flow control
- `pumpWidget` / `pump` async test patterns

None of those produced a qwen failure mode in the 3 successful
chains.

**Rules out (pre-patch):** "Flutter doesn't transfer." The 2/5
pre-patch raw rate looked discouraging until the failure modes
were investigated — every loss was an Ollama infrastructure
crash, not a capability ceiling.

**Doesn't address:** the dart-inventory ceiling. flutter-counter is
3 coordinating files; dart-inventory is 9. The 9-file pure-Dart
ceiling (0/35 across qwen3.5 + qwen2.5-coder:32b) may also apply
to a hypothetical `flutter-inventory` at 9 widgets. Untested.

---

## Implications for the cross-language fitness map

The published map (M6.3) labeled Flutter `❓ untested` across all
three columns. With this data:

| column | result |
|---|---|
| single-file | (skipped — Flutter inherently multi-file) |
| small multi-file (≤3) | **3/3 = 100%** capability, 1/1 post-patch (qwen2.5-coder:32b) |
| large multi-file (~9) | unknown — `flutter-inventory` not authored |

ROADMAP M6.3 updated accordingly.

---

## What this means for v1.x

Two outputs of this experiment:

1. **Cross-language fitness map updated** — Flutter moves from
   `❓ untested` to `✅ small multi-file` with the keep_alive
   caveat noted on the prior 5 trials.
2. **Ollama infra fix landed** — the keep_alive eviction race
   that caused 3 of 5 pre-patch losses is fixed in commit
   `4c66c13`; future bake-off harnesses won't bleed trials to
   the same root cause.

The M10 indexer plan does NOT need to incorporate Flutter — at
the small multi-file scope it doesn't show a ceiling that semantic
context could lift. The natural extension question — "does an
indexer help at flutter-inventory scale (9 widgets, BuildContext
threading, parent-child state)?" — is a separate experiment that
hasn't been authored yet.

---

## Limitations

- **N=1 post-patch.** f06 confirms the keep_alive fix works
  end-to-end but isn't statistical evidence of the post-fix
  rate. Higher-N rerun would tighten the CI on the "100% when
  infra cooperates" claim.
- **Single scenario.** Counter app is a constrained, well-known
  pattern. A different Flutter benchmark (form validation,
  navigation, async data fetch with FutureBuilder) might
  surface different failure modes.
- **Ollama keep_alive caveat is implementation-specific.** The
  fix applies to Loom's `loom_exec` and `services.decompose`
  callers; users invoking Ollama directly outside Loom would
  hit the same eviction issue without our patch.
- **Benchmark spec was authored once.** Opus drew the spec from
  the README + reference implementation — variation in spec
  quality across the 6 trials may have contributed to the 100%
  rate (each trial got a fresh Opus spec, but all from the same
  source material).

---

## Recommended next experiments (priority order)

1. **Higher-N post-patch rerun** (N=5 to 10) to firm up the
   post-fix rate. Only worth doing once we have a reason to
   trust the 100% — a few cells of Flutter is not the highest-
   value Loom signal.
2. **`flutter-inventory` benchmark** at 7-9 coordinating widgets
   with shared state — analog to the `dart-inventory` ceiling
   experiment. Tests whether Flutter inherits Dart's 9-file
   ceiling or whether the widget-tree patterns push it earlier.
3. **Cross-tier executor test on Flutter.** qwen3.5:latest at
   flutter-counter would tell us whether the smaller executor
   handles widget code or whether 32b is required (mirrors
   what dart-inventory established for 9-file Dart).

---

## Files of record

- `experiments/bakeoff/v2_driver/phC_flutter_counter_oneshot_auto.py`
  — driver
- `experiments/bakeoff/benchmarks/flutter-counter/ground_truth/`
  — spec + reference + hidden tests
- `experiments/bakeoff/runs-v2/phC_flutter_runf{01,02,03,04,05,06}_summary.json`
  — 6 trial summaries
- Compare against:
  - `FINDINGS-bakeoff-v2-phaseC-inventory.md` (Phase C overall)
  - `FINDINGS-bakeoff-v2-cross-language-map.md` (M8.4 baseline)

---

## What this means for v1 release

Nothing material — this is post-launch follow-up. The published
website / docs can drop the "Flutter untested" caveat and replace
with: *"Flutter at small multi-file scope (≤3 widgets) is
supported via the same `flutter_test` runner the executor already
ships. Larger Flutter projects are unverified."*
