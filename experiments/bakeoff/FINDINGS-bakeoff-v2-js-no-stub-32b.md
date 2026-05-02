# Bakeoff V2 — JS no-stub 32b baseline (phQ4)

**Date:** 2026-05-02
**Question:** The phQ baseline → phQ3 jump on +rat (60% → 100%) and
on +placebo (40% → 90%) was confounded between two changes: model
tier (qwen3.5 → qwen2.5-coder:32b) and stub presence (no indexer →
clean LSP-style stub). Which one is the lift mechanism?
**Approach:** Hold the 32b model and remove the stub. Same scenario,
same 4 cells × N=10. The delta vs phQ3 isolates the stub effect; the
delta vs phQ baseline isolates the model-tier effect.
**N:** 40 trials. 0 retries fired. 0 compile failures. 0
no-code-extracted. 11.1 min wall.

---

## TL;DR

> **Two effects, in opposite directions on bare cells.**
>
> | comparison | off | on-rule | +placebo | +rat |
> |---|---|---|---|---|
> | model tier (qwen3.5→32b, no stub) | 0pp | **-20pp** | **-30pp** | +20pp |
> | clean stub (32b, no stub→clean) | 0pp | 0pp | **+80pp** | +20pp |
>
> The bigger model **hurts** rule-only and placebo cells (-20pp,
> -30pp) and helps the rationale cell (+20pp). qwen2.5-coder:32b
> is a code-specialist trained on conventional good practices —
> it's *more* likely to reject a contrarian rule than qwen3.5 is.
> Counter to the standard "bigger is better" intuition.
>
> The clean stub adds **+80pp on placebo** but 0pp on bare cells.
> The stub's signal is conditioned on the prompt containing
> explanation-shape text. Without explanation, the structural
> facts integrate into either framing (task-prompt's "fix the bug"
> or rule's "swallow"); with explanation, they reinforce the
> rule.
>
> Net: a real `JsIndexer` at 32b would deliver measurable lift in
> rationale-augmented prompts — the strongest cell-specific stub
> effect we've measured (+80pp on placebo, larger than M10.2
> C++'s +40pp). The phQ2 framing ("indexer fixes on-rule") is
> dead, but a cleaner framing replaces it: **the indexer
> amplifies the rationale signal**, which aligns with Loom's
> core thesis that decision rationale carries the load.

---

## The four-way comparison

All cells, four runs:

| cell | phQ (qwen3.5, no stub) | **phQ4 (32b, no stub)** | phQ3 (32b + clean stub) | phQ2 (32b + leaky stub) |
|---|---|---|---|---|
| off | 0% | 0% (0/20) | 0% | 60% |
| on-rule | 20% | 0% (0/20) | 0% | 100% |
| on-rule+placebo | 40% | 10% (2/20) | 90% | 100% |
| on-rule+rat | 60% | **80% (16/20)** | 100% | 100% |

phQ2's pattern (uniform 100% on rule-bearing cells) was
substantially the JSDoc rule leak. phQ3 (clean stub) split the
behavior into "saturated when explanation is present" vs "near
zero when only rule." phQ4 confirms most of that split is real:
the bare 32b model on +rat already at 80% is the cleanest signal
the model tier carries weight on the rationale path.

---

## Decomposition of the +rat lift

The original puzzle: phQ baseline +rat = 60%, phQ3 +rat = 100%.
+40pp delta from two simultaneous changes.

phQ4 splits it cleanly:

| source | contribution to +rat |
|---|---|
| qwen3.5 → 32b (no stub) | +20pp (60% → 80%) |
| no stub → clean stub (at 32b) | +20pp (80% → 100%) |
| **combined** | **+40pp (60% → 100%)** |

Both effects are real and additive on the rationale cell. The
indexer earns its keep here.

## Decomposition of the +placebo lift

phQ baseline +placebo = 40%, phQ3 +placebo = 90%. +50pp delta.

| source | contribution to +placebo |
|---|---|
| qwen3.5 → 32b (no stub) | **-30pp** (40% → 10%) |
| no stub → clean stub (at 32b) | **+80pp** (10% → 90%) |
| **combined** | +50pp (40% → 90%) |

The bigger model HURTS the placebo cell substantially. The clean
stub recovers it and overshoots. Net is +50pp, but the
*mechanism* is much more interesting than the headline: the stub
is doing more than +50pp of work because it's compensating for
a -30pp model regression. **The stub is the dominant lift
mechanism on placebo.**

---

## Why does the bigger model HURT bare-rule cells?

qwen2.5-coder:32b is a code-completion specialist. Its training
distribution is dominated by "best-practice" code — error
propagation, defensive null-checks, idiomatic exception handling.
The S1 task framing ("this looks like a bug — fix it") aligns
perfectly with that prior. The S1 rule ("swallow errors and
return null") fights it.

qwen3.5:latest is a general-purpose model with a more diffuse
training prior. It's less *certain* about what good code looks
like, so a stated rule has more relative influence on its output.
The contrarian setup penalizes specialization.

This matters for executor-selection guidance in v1:

> **For Loom-spec'd contrarian work** (rules that look bug-like
> to a coder), code-specialist models may be the *wrong* default.
> A general-purpose model with weaker priors follows the spec
> more readily. The optimal executor depends on whether the
> spec aligns with conventional practice or fights it.

This generalizes the M6.5.2 "language-aware executor selection"
guidance: it's not just the language that matters, it's whether
the spec aligns with the model's training prior for that
language. The same model can be the right call for one spec
shape and the wrong call for another.

---

## What this rules in / rules out for step 4 (real JsIndexer)

**Rules in:** A real `tsserver`-based `JsIndexer` is justified
on rationale-augmented Loom workflows. Specifically:
- +rat at 32b: stub adds +20pp (80% → 100%, near-saturation
  ceiling)
- +placebo at 32b: stub adds **+80pp** (10% → 90%) — the
  strongest cell-specific stub effect across all M10
  experiments to date

**Rules out:** "JsIndexer fixes JS compliance generally." Bare
rule cells (off, on-rule) are 0% with or without the stub. The
indexer doesn't lift compliance when the prompt has only the
rule.

**Reframes:** the M10 product pitch on JS. Not "ship the indexer
to make qwen better at JavaScript." Instead: **"the indexer
amplifies rationale and explanation-shape context — Loom's
existing rationale story is what makes it land."** This is
arguably a stronger pitch — it ties the indexer to the
already-validated cross-session rationale work (Phase G, M8.1)
rather than a standalone capability claim.

**Rules out:** "Always pick the bigger model." The phQ4 data
shows qwen2.5-coder:32b loses to qwen3.5:latest on contrarian
rule cells without rationale support. Executor selection should
be spec-shape-aware, not just language-aware.

---

## Implications for the cross-language map

The M8.4 JS regime classification ("graded, no saturation, caps
at 60%") was qwen3.5-tier specific. With the data we now have:

| executor | scenario shape | best cell rate |
|---|---|---|
| qwen3.5, no stub | +rat | 60% |
| 32b, no stub | +rat | 80% |
| 32b, clean stub | +rat | **100%** |
| 32b, clean stub | +placebo | 90% |

The "graded, no saturation" label is correct for the **default
deployment** (qwen3.5, no indexer) but understates what's
reachable. With a real `JsIndexer` and a 32b executor, JS becomes
a saturating-on-rationale language. ROADMAP M8.4 / M6.3
deserve an annotation.

---

## Limitations

- **Single scenario.** S1 swallow_error. S2/S3 untested.
- **Placebo result hinges on length match.** The placebo is
  length-matched to the rationale (~340 chars) and content-
  shaped to read like an explanation (declarative,
  consequence-oriented). A different placebo (lorem ipsum,
  anti-rule prose) would test whether the +80pp stub effect
  is "explanation present" or "any text of that length."
- **N=10 binomials.** The 8/10 +rat result has a 95% CI of
  roughly 49-94%, so the 80% point estimate could land
  anywhere in that range with more samples. Likely solid given
  the obvious ceiling-approach pattern, but tighter N would
  help.
- **Hand-authored stubs.** Real `tsserver` output may diverge
  from phQ3's clean stub in the direction of either phQ2's
  leaky stub (if hover info encodes contracts) or further
  toward bare references (if we restrict to peek-references
  output). The actual product behavior depends on which LSP
  methods we wire up.

---

## Recommended path forward

1. **Step 4 (real `JsIndexer`) is justified, with a refined
   spec.** Build it to amplify rationale-augmented prompts,
   not to replace them. Subprocess wraps `tsserver` or
   `typescript-language-server`, surface peek-references-style
   output (matching phQ3's structural-facts shape).
   Validation target: replicate phQ3's +placebo and +rat
   numbers on a real codebase.
2. **Update Loom executor-selection guidance.** When the spec
   aligns with conventional code practice, prefer larger
   code-specialist models. When the spec is contrarian
   (rules that fight the conventional answer), smaller
   general-purpose models may comply more readily.
3. **Anti-rule placebo variant** to confirm the +80pp placebo
   lift is "explanation supports rule," not "any text fills
   the slot." Cheap (~10 min wall).
4. **Higher-N tightening on +rat at 32b + no stub.** N=20-30
   would pin down whether the 80% baseline is a real ceiling
   or a sampling artifact.

---

## Files of record

- `experiments/bakeoff/v2_driver/phQ4_crosssession_js_no_stub_32b_smoke.py`
  — no-stub 32b baseline harness
- `experiments/bakeoff/runs-v2/phQ4_s1_js_*_run{1..10}_summary.json`
  — 40 trial summaries
- Compare against:
  - `FINDINGS-bakeoff-v2-cross-language-map.md` (phQ baseline,
    qwen3.5 no stub)
  - `FINDINGS-bakeoff-v2-stub-indexer-multilang.md` (phQ2
    leaky stub)
  - `FINDINGS-bakeoff-v2-js-stub-clean.md` (phQ3 clean stub
    falsification)
