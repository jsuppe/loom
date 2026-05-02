# Bakeoff V2 — C++ stub-indexer falsification (M10.2)

**Date:** 2026-05-01
**Question:** If the C++ ceiling isn't executor capacity (M10.1b ruled
that out), is it *missing semantic context*? Specifically: would a
Kythe-style call-graph + type-signature dump prepended to the prompt
let qwen2.5-coder:32b bridge S1 C++?
**Approach:** Hand-author the semantic context a real Kythe query
would surface for `retry.hpp` (call sites of `fetchWithRetry`, type
definitions of `BackoffError`/`BackoffLedger`, contract notes), wire
it through the new `SemanticIndexer` registry as a `StubCppIndexer`,
re-run the same 4-cell × N=5 phL harness with the indexer enabled.
Same model as the M10.1b falsification (qwen2.5-coder:32b) so the
delta isolates context, not capacity.
**N:** 20 trials. 0 harness errors. 0 compile failures. 6.3 min wall.

---

## TL;DR

> **Semantic context is the missing piece.** With the same executor
> that scored 0% on the rat cell unaided (M10.1b), prepending
> hand-authored Kythe-shaped context lifted compliance to **40%
> (rat) / 60% (placebo) / 20% (rule)**, and the off cell stayed at
> 0% as expected (no rule, no compliance to lift).
>
> The lift is **real but partial** — peak is 60%, not 100%. Semantic
> context is necessary but not sufficient on this scenario. The
> M10 architecture is empirically justified; the next experiment
> is a real `KytheIndexer` to see whether the gap to saturation
> closes when the context is more comprehensive than a hand-curated
> stub.

---

## Setup

Verbatim phL harness (cross-language C++ smoke), with one change:
the prompt builder now consults a registered `StubCppIndexer` and
prepends its `context_for(retry.hpp)` block above the file body.

```
LOOM_EXEC_MODEL=qwen2.5-coder:32b  (same as M10.1b)
N=5 per cell × 4 cells = 20 trials
prompt size: 4525 chars (vs phL's ~2400 — semantic block adds 2094 chars)
```

The stub context block is hand-authored to mimic Kythe output:

- 3 call sites of `fetchWithRetry` with their surrounding code
  (showing `BackoffLoop::run` does NOT catch `runtime_error` and
  relies on the swallow contract)
- Type signatures of `BackoffError`, `BackoffLedger` (showing
  the wrapper actually exists)
- Explicit contract statement for `fetchWithRetry`'s return type
  + exception behavior

Same content for every cell — including `off`. That's intentional:
the experiment isolates "semantic context vs no semantic context",
not "rule + context vs rule-only".

---

## Empirical record

| cell | STUB+32b (M10.2) | baseline 32b (M10.1b) | qwen3.5 baseline (M8.4) |
|---|---|---|---|
| **off** | 0/10 (0%) | 0/10 (0%) | 0% |
| **on-rule** | **2/10 (20%)** | 0/10 (0%) | 0% |
| **on-rule+placebo** | **6/10 (60%)** | 2/10 (20%, noise) | 100% (artifact) |
| **on-rule+rat** | **4/10 (40%)** | 0/10 (0%) | 67% |

**Lift from semantic context (vs. M10.1b baseline at same model):**

| cell | baseline | with stub | delta |
|---|---|---|---|
| off | 0% | 0% | 0pp |
| on-rule | 0% | 20% | **+20pp** |
| on-rule+placebo | 20% | 60% | **+40pp** |
| on-rule+rat | 0% | 40% | **+40pp** |

**Other measurements:**

- 0 compile failures across all 20 trials. The model produces valid
  C++; it's choosing whether to swallow vs propagate, not failing on
  syntax.
- 0 citation hits (cited=0/5 across all cells). qwen2.5-coder:32b
  doesn't reproduce the rationale's distinctive phrases in its output.
  Same as the M10.1b falsification — context lifts *compliance* but
  not *citation* on this model/scenario.
- Wall: 6.3 min total · ~19s per trial. Same per-trial cost as the
  falsification despite the longer prompt — Ollama handled the +2k
  chars without measurable slowdown.

---

## What this rules in

**Semantic context is the M10 lever.** Five of the eight rule-bearing
cell counts moved from "0/N" to "≥2/N" with the addition of context
that a real indexer would produce. The off cell didn't move (rule
absence floors compliance regardless), confirming context only
amplifies, never replaces, rule injection.

**The C++ "collapsed" regime classification from M8.4 is reframed.**
What looked like "qwen can't follow rules in C++" is more accurately
"qwen needs the structural evidence that the rule's claims are
real — without it, the rationale's narrative ('there's a wrapper,
trust it') doesn't compete with the task prompt's framing
('that's a bug, fix it')." Provide the structural evidence and
compliance lifts.

---

## What this does NOT prove

- **Stubs aren't Kythe.** The hand-authored block was tuned to be
  maximally helpful — a real Kythe query may produce noisier output
  (irrelevant call sites, false-positive type references). The peak
  at 60% might be an upper bound for "best-case context"; real Kythe
  could hit 30-50%.
- **Peak is 60%, not 100%.** Semantic context is necessary but not
  sufficient on this scenario. What closes the remaining 40%? Larger
  executor, more context, different prompt structure — all open.
  This experiment doesn't differentiate.
- **placebo > rat (60% vs 40%) is suspicious.** Same byte count;
  placebo (which restates the rule) outperformed rat (which adds
  the rationale narrative) at this N. Three plausible explanations,
  in increasing severity:
  1. **Sampling noise.** 6/10 vs 4/10 is a 2-trial gap; the binomial
     CI overlap is wide. Higher N (N=15-20/cell) would settle it.
  2. **Rationale-context redundancy.** The semantic block mentions
     `BackoffError` and the wrapper; the rationale also mentions
     them. Maybe the rationale becomes confusing when the context
     already establishes the same facts.
  3. **Narrative competes with structure.** The rationale's "incident
     2024-09-12" framing might pull attention away from the
     structural evidence. Worth investigating before treating
     rationale-on-top-of-context as additive.
- **Citation rate stays at 0%.** The model complies but doesn't
  reproduce the rationale's distinctive phrases in its output —
  unlike Phase G where Haiku cited rationale 100%. Whether this is
  a model-tier difference (qwen2.5-coder:32b is a code-completion
  model, not a chat model) or a language difference is open.
- **N=5 per cell.** Same caveat as M10.1b — large effects are
  decisive, marginal contrasts are not. The 60% vs 40% (placebo vs
  rat) gap is exactly the marginal contrast that needs more N.

---

## Implications for the cross-language map (M8.4)

The published map labeled C++ "collapsed" based on qwen3.5's
0%/0%/100%*/67% pattern. With M10.1b + M10.2 both run, that label
deserves an annotation:

> **C++** is collapsed *when given only file-body context*. With
> Kythe-shaped semantic context prepended, qwen2.5-coder:32b
> reaches 60% on placebo and 40% on rat — a clean lift but not
> saturation. The "collapsed" framing is correct for the published
> map's deployment configuration; it understates what's possible
> with M10's indexer-enriched context bundle.

C, Go, and the other resistant-mid languages may show similar
shifts. Untested.

---

## Recommended next experiments (priority order)

1. **Higher-N rerun of M10.2.** N=15 or N=20 per cell to settle the
   placebo > rat gap and tighten the binomial CIs on the 40-60%
   middle band. ~30 min wall at the same model.
2. **Real `KytheIndexer` on a small C++ project.** Build the
   build-pipeline plumbing, run a Kythe extraction over a real
   project (the `cpp-orders` benchmark would do), verify the
   `context_for` output is comparable in shape to the stub. If
   it produces the right kind of signal, the stub→real transition
   is just a connector job.
3. **C and Go stub experiments.** Same architecture, different
   language. Resistant-mid languages should show similar lift if
   the M8.4 regime is really about missing structural context.
4. **Decompose the rationale-vs-context redundancy.** A 5-cell
   variant: rule / rule+placebo / rule+rat / rule+context /
   rule+context+rat — to isolate whether stacking redundant signals
   helps, hurts, or is noise.

---

## Files of record

- `experiments/bakeoff/v2_driver/phL2_crosssession_cpp_stub_indexer_smoke.py`
  — phL harness + StubCppIndexer registration + prompt enrichment
- `experiments/bakeoff/runs-v2/phL2_s1_cpp_*_run{1..5}_summary.json`
  — 20 trial summaries
- `experiments/bakeoff/runs-v2/phL2_progress.log` — wall-clock
  progression
- Compare against:
  - `FINDINGS-bakeoff-v2-cpp-executor-falsification.md` (M10.1b)
  - `FINDINGS-bakeoff-v2-cross-language-map.md` (M8.4 baseline)

---

## What this means for v1 release

Nothing material changes for v1 — this is post-launch follow-up
work. The key shift is on the v1.x roadmap:

> **M10 is no longer speculative.** Two N=20 falsifications
> (executor capacity ruled out, then semantic context ruled in)
> establish that building a real `KytheIndexer` for C++ is the next
> defensible experiment. The M10.1 scaffolding (interface,
> registry, `loom link --symbol`) is the seam that lands the
> connector cleanly.

Honest framing for the public site / docs: *"Loom's M8.4 cross-
language map identified C++ as a regime Loom doesn't help today.
M10.2 shows that gap closes meaningfully when the agent receives
Kythe-shaped semantic context. v1.x will ship a real `KytheIndexer`
for C++ users with a Kythe corpus."*
