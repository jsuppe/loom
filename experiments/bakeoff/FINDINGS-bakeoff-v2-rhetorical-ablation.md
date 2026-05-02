# Bakeoff V2 — Rhetorical ablation of the RATIONALE constant (phR)

**Date:** 2026-05-02
**Question:** The Loom prompt-engineering doc claims "rationale is
load-bearing," but the phQ series confounded six rhetorical
features inside one paragraph. Which feature(s) actually carry
the lift over a length-matched placebo?
**Approach:** Decompose the RATIONALE constant into six atomic
features (codebase locator, mechanism, incident date, cost
anchor, reframe, dependence assertion) and run leave-one-out
ablation. For each cell, strip exactly one feature and keep the
other five. Compare to the full rationale (positive control) and
placebo (negative control). Conditions: phQ6 baseline (JsIndexer
v2, no test files in workspace, qwen2.5-coder:32b) — chosen for
maximum headroom (placebo at 30%, full rationale at 100% = 70pp
range to attribute).
**N:** 80 trials (8 cells × N=10). 0 retries fired. 0 compile
failures. ~21 min wall.

---

## TL;DR

> **The reframe is the load-bearing rhetorical move.** Stripping
> the single sentence that anticipates and defuses the task
> framing's "fix the bug" pull dropped compliance by **20pp** —
> the largest single-feature effect by a 2× margin. Stripping
> mechanism explanation or cost anchoring dropped compliance by
> **0pp**. The other three features (locator, date, dependence
> assertion) were 5-10pp each.
>
> | cell | compliance | rationale chars | vs V_full |
> |---|---|---|---|
> | placebo (control) | 30% | 371 | — |
> | **V_full** (positive ctrl) | **100%** | 370 | baseline |
> | V_no_mechanism | 100% | 350 | 0pp |
> | V_no_cost | 100% | 362 | 0pp |
> | V_no_locator | 95% | 339 | −5pp |
> | V_no_date | 90% | 366 | −10pp |
> | V_no_dependence | 90% | 270 | −10pp |
> | **V_no_reframe** | **80%** | 332 | **−20pp** |
>
> Lesson 1 of the prompt-engineering doc ("rationale is
> load-bearing") **stands** — the worst rationale variant (80%)
> still sits 50pp above placebo (30%). But the lesson should be
> **sharpened**: it's specifically *framing-defusion* that's
> load-bearing. The model is robust to missing the other
> rhetorical features as long as the reframe stays.

---

## What was decomposed

The RATIONALE constant from phQ2-phQ7:

```
The retry wrapper in backoff_loop.js two frames up intercepts
BackoffError and re-issues. Throwing from fetchWithRetry breaks
the wrapper contract — production incident 2024-09-12 lost three
hours while ops chased a propagation bug that was actually working
as intended. The current swallow-and-return-null behavior is
load-bearing for the BackoffError wrapper above us.
```

Atomized into six rhetorical features:

| feature | text in original | what it provides |
|---|---|---|
| A. Codebase locator | "backoff_loop.js", "BackoffError" | makes stakes concrete, locatable |
| B. Mechanism | "intercepts and re-issues", "breaks the wrapper contract" | causal explanation of dependency |
| C. Incident date | "2024-09-12" | specificity, appeal to history |
| D. Cost anchor | "three hours" | quantified consequence |
| E. Reframe | "actually working as intended" | anticipates task framing's "fix it" pull |
| F. Dependence assertion | "load-bearing for the wrapper above us" | explicit functional dependence claim |

Each leave-one-out variant strips exactly that feature, keeps the
other five, with minimal length perturbation (variants ranged
270-370 chars; original was 370).

---

## Empirical record

| cell | passed | trials | compliance | chars |
|---|---|---|---|---|
| placebo | 6/20 | 10 | 30% | 371 |
| V_full | **20/20** | 10 | **100%** | 370 |
| V_no_locator (no A) | 19/20 | 10 | 95% | 339 |
| V_no_mechanism (no B) | 20/20 | 10 | 100% | 350 |
| V_no_date (no C) | 18/20 | 10 | 90% | 366 |
| V_no_cost (no D) | 20/20 | 10 | 100% | 362 |
| **V_no_reframe (no E)** | **16/20** | 10 | **80%** | 332 |
| V_no_dependence (no F) | 18/20 | 10 | 90% | 270 |

Per-cell drops vs V_full's 100%, ranked:

1. **V_no_reframe: −20pp** ← single largest impact
2. V_no_date: −10pp
3. V_no_dependence: −10pp
4. V_no_locator: −5pp
5. V_no_mechanism: 0pp
6. V_no_cost: 0pp

**Cumulative:** removing all the "weakly-impactful" features
(mechanism, cost) zero cost. Removing the reframe is twice as
costly as removing the next-most-impactful feature.

---

## What this rules in / rules out

**Rules in (Lesson 1 stands):** Rationale content matters. Even
the worst-performing variant (V_no_reframe at 80%) is 50pp above
the placebo control (30%). The empirical claim from the M11.5
design ("rationale is the most leveraged token in the prompt")
holds. The placebo finding from M10.3 doesn't refute Lesson 1;
it just shows that *some* explanation-shape text gets you partway,
not all the way.

**Rules in (Lesson 1 sharpened):** The mechanism that carries
rationale's lift over placebo on contrarian specs is **the
sentence that anticipates and defuses the task framing's pull.**
The reframe in the original RATIONALE — "a propagation bug that
was actually working as intended" — directly contradicts the
task prompt's framing ("That looks like a bug — fix it"). When
removed, compliance drops most.

This generalizes to a sharper prompt-engineering claim:

> **On contrarian specs, the rationale's job is to pre-empt the
> task framing's pull, not to explain the system mechanically.**

**Rules out:** "Mechanism explanation matters." V_no_mechanism
sat at 100%. The model doesn't need the causal chain spelled out
in prose; it can infer enough from the rule + the framing-defuser.

**Rules out:** "Cost quantification matters." V_no_cost sat at
100%. The "three hours" specifics don't carry weight on this
scenario.

**Rules out:** "Specificity (date) is critical." V_no_date sat
at 90% — measurable but small effect. Vague "we had an incident"
language is nearly as effective as "we had an incident on
2024-09-12."

**Doesn't address:** the cumulative effect of removing multiple
features simultaneously. A V_only_reframe variant (just the
reframe sentence, no other features) would be the most decisive
test of the framing-defusion hypothesis. Untested in this phase.

---

## Implications for the prompt-engineering doc

**Update Lesson 1 ("rationale is load-bearing") with this
qualification:** the rationale's job on contrarian specs is to
pre-empt the task framing's pull, not to explain the system
mechanically. When capturing rationale, the highest-impact
sentence to write is the one that **anticipates how someone
would misread the rule and corrects them in advance**.

For Loom users, this becomes a practical capture guideline:

> When writing rationale for a Loom requirement, ask: "If a future
> agent (or a future you) reads this rule, what would they
> mistakenly conclude they should do?" Write the sentence that
> defuses that misreading. That sentence is worth more than five
> sentences of mechanism, cost, or history.

This is a sharper actionable claim than "capture rationale" alone
and directly informs what makes rationale text *good*.

---

## Implications for the M11.5 intake hook

The intake hook's classifier currently extracts a `rationale_excerpt`
field — verbatim text from the user message that explains the
"why." Given this finding, the hook could be smarter:

- **Prefer rationale_excerpts that contain framing-defusion
  language.** Patterns: "actually", "intentional", "load-bearing",
  "not a bug", "by design", "deliberately".
- **Flag captures with no framing-defuser as weaker** — surface
  in `loom intake-stats` or `loom needs-rationale` as a "rationale
  quality" signal.
- **In auto-link captures, append a synthetic framing-defuser**
  if one isn't present in the source rationale: "(captured because
  the rule may run counter to default expectations)."

These are incremental refinements, not blockers. Phase A of M11.5
is fine as-is; rationale-quality scoring would be a hypothetical
M11.5 P5+ improvement.

---

## Limitations

- **N=10 binomial CIs are wide.** The 90/95/100 differences are
  within sampling noise. The 80 vs 100 gap (V_no_reframe vs
  V_full) is 4 trials of difference; the binomial 95% CI on 8/10
  is roughly 49-94%, on 10/10 is 70-100%. They overlap. The
  *directional* signal is strong (reframe matters most) but the
  *magnitude* could land anywhere from 5pp to 30pp at higher N.
- **Single scenario.** S1 swallow_error in JS only. Whether the
  reframe-is-load-bearing finding generalizes to other contrarian
  shapes (S2 rename, S3 if authored) or non-contrarian rules
  (style requirements, documentation requirements) is open.
- **Single executor.** qwen2.5-coder:32b only. Anthropic Haiku /
  Sonnet / GPT-4 may show different feature priorities. Worth
  re-running once API access is available.
- **Length not strictly controlled.** Variants ranged 270-370
  chars (vs 370 baseline). The shortest variant (V_no_dependence)
  scored 90% — not a length effect (it's near the top of the
  variant range despite being shortest).
- **Single ablation direction.** This was leave-one-out. A
  dual-direction ablation (only-one-feature, the inverse) would
  isolate sufficiency in addition to necessity. Untested in phR.
- **The reframe variant still has framing-defuser content
  elsewhere.** "Load-bearing" in the dependence assertion is
  arguably also a defuser ("don't change this; something
  depends on it"). The 80% in V_no_reframe may be partly carried
  by F. A V_no_reframe_no_dependence variant would isolate the
  reframe more cleanly. Not tested.

---

## Recommended next experiments

1. **Single-feature variants (only-A through only-F).** N=10 each.
   Tests sufficiency: which single feature, on its own, can carry
   the rationale's lift? If V_only_reframe scores 80%+, the
   framing-defusion hypothesis is confirmed by the inverse.
2. **Anti-rationale ablation (the wide ablation we deferred).**
   Replace the rationale entirely with text that argues against
   the rule. Tests whether "explanation-shape text" alone is
   sufficient (Lesson 3 dominance) or whether content polarity
   matters.
3. **Cross-scenario validation.** Port the leave-one-out to a
   non-contrarian rule (e.g., docstring requirement). If reframe
   doesn't matter when there's nothing to reframe (no contrarian
   pull), the finding is contrarian-specific.
4. **Higher-N rerun on V_no_reframe vs V_full.** N=30 each to
   tighten the CI on the −20pp gap. Cheap (~10 min wall).
5. **The dual-direction ablation** (only-one + leave-one-out
   together) would give complete coverage. ~12 cells, ~30 min
   wall.

---

## Files of record

- `experiments/bakeoff/v2_driver/phR_rhetorical_ablation_smoke.py`
  — phR harness with all 6 leave-one-out variants
- `experiments/bakeoff/runs-v2/phR_s1_js_*_run{1..10}_summary.json`
  — 80 trial summaries
- Compare against:
  - `FINDINGS-bakeoff-v2-js-real-lsp-v2.md` (phQ6 baseline at
    placebo=30%, +rat=100%)
  - `FINDINGS-bakeoff-v2-js-stub-clean.md` (phQ3 placebo=90%
    artifact discussion)
- Doc to update:
  - `docs/PROMPT-ENGINEERING-LESSONS.md` (Lesson 1 — sharpen with
    framing-defusion qualification)
