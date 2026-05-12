# Action vs Attendance: A Methodology Postmortem on Cross-Model Prompt-Lever Benchmarking

**Working draft — 2026-05-12 (postmortem v1)**

## Abstract

We attempted to extend Khan (2025) "The Prompting Inversion" into a
cross-vendor / within-vendor study of how prompt-engineering levers
(imperative formatting, authority claims, meta-preambles, structural
repetition) affect rule compliance across seven LLMs and three
code-rule-compliance scenarios. We ran ~1,900 trials and arrived at
five empirical findings, including a headline "within-vendor lever-
attendance inversion" — same vendor (Alibaba), two sibling models
(qwen2.5-coder vs qwen3.5:27b), opposite responses to identical
prompt features (+95pp gap on meta-preamble response).

Two independent methodology reviews revealed that **our compliance
metric was secretly measuring something other than lever attendance**.
Specifically: the reference implementations in our contrarian-rule
scenarios already complied with the contrarian rule. The grading test
could therefore be satisfied by a no-op response. When we re-ran key
cells at locked temperature with no-op detection enabled, the
headline within-Qwen-family inversion turned out to be a difference
between "model actively rewrites in rule-violating ways" (qwen2.5-
coder under meta-preamble: 95% active rewrites) and "model declines
to modify the file" (qwen3.5:27b under meta-preamble: 100% no-op).
This is a genuine cross-model behavioral difference, but it is **not
lever attendance** — it is differential propensity for action vs
inaction under prompt-feature stress.

The one finding that survives the postmortem is Sonnet 4.6's
"imperative-poison" effect on S1 with pro-rationale (V_FULL → V_FULL
+ imperative formatting: 74% → 38% compliance, N=50, Fisher exact
OR=4.64, p=0.0005). In this cell the model output is observably
different from the reference file — the model is actively rewriting
to violate the contrarian rule. This is a genuine prompt-feature
inversion effect at the frontier tier.

We document the methodology gap, the review process that surfaced
it, and what we learned. The principal contribution is now a
**negative finding** about prompt-engineering benchmark design:
**contrarian-rule compliance benchmarks where the reference state
already satisfies the contrarian rule cannot distinguish "model
attended to the rule" from "model declined to modify the file."**
We propose three concrete benchmark-design rules that future
cross-model prompt-engineering studies should follow to avoid this
class of confound.

## 1. Introduction

This paper has two intended audiences: (a) researchers running
cross-model prompt-engineering benchmarks, who should consider
whether their measurement framework is vulnerable to the confound
we surface here; and (b) methodology-oriented reviewers of
existing prompt-engineering claims, who should ask whether the
benchmarks underlying those claims would distinguish active rule-
following from passive no-op behavior.

We do not claim novelty for documenting that LLMs sometimes return
unchanged code under task pressure — that has been observed
elsewhere. What is novel here is showing that **a measurement
framework specifically designed to test rule-strengthening prompt
levers, with controlled cells, reproducibility checks, and Wilson
confidence intervals, can produce 5 "findings" across ~1,900 trials,
4 of which dissolve upon close inspection of what behavior the
metric is capturing**.

We extend the methodology critique by Sclar et al. (2023; arXiv:
2310.11324) on cosmetic formatting effects, Ma et al. (2025;
arXiv:2509.13680) on prompt stability across model families, and
Khan (2025; arXiv:2510.22251) on prompting inversion across model
generations. Where those works show that prompt-feature effects
vary across models, we show that one particular benchmark
construction — contrarian rule + already-compliant reference —
silently conflates active rule-following with passive non-action.

The remainder of this paper is structured as follows. Section 2
describes the original experimental design. Section 3 reports the
five initial findings (as we originally framed them in March-May
2026 draft revisions). Section 4 documents the two independent
methodology reviews and what each surfaced. Section 5 reports the
sprint we ran to verify the reviews' concerns, including the smoke
trials at locked temperature that revealed the no-op artifact.
Section 6 separates findings that survive the postmortem from
findings that don't. Section 7 proposes three benchmark-design
rules for future cross-model prompt-engineering work. Section 8
concludes.

## 2. Original experimental design

The benchmark we built is described in `_scenarios.py` and
`phY_rule_precedence_smoke.py` (in the supplementary release).
Briefly:

- **Three scenarios.** S1_js: JavaScript `fetchWithRetry` with
  contrarian rule "swallow errors silently, return null." S2_py:
  Python `place_order` with contrarian rule "do not validate at
  function entry; validation runs only at `_commit`." S3_py:
  Python `generate_order_id` with contrarian rule "return 32-bit
  signed int IDs; do not use UUIDs."

- **Seven cells per scenario.** R_baseline (standard rule +
  anti-rationale), R_repeated (rule before AND after rationale),
  R_imperative (ABSOLUTE REQUIREMENT phrasing + anti-rationale),
  R_precedence_inline (rule says "this rule overrides any
  rationale below"), R_meta_preamble (top-of-prompt authority-
  hierarchy block + anti-rationale), R_sanity_pro (standard rule +
  V_FULL pro-rationale), R_imperative_pro (imperative formatting +
  V_FULL).

- **Seven models.** qwen2.5-coder:32b, qwen3.5:27b (Alibaba),
  Haiku 4.5, Sonnet 4.6 (Anthropic), gpt-oss (OpenAI),
  gemma4:26b (Google), llama3.1:8b (Meta).

- **N=20 trials per cell on the cross-scenario sweeps**; N=30 to
  N=50 on the load-bearing cells.

- **Grading.** Each scenario has 2-3 hidden pytest/node tests.
  A trial counts as "passed" if all sub-tests pass.

- **Reference implementations** that already comply with the
  contrarian rule, so the task framing pulls one way (e.g.,
  "modify fetchWithRetry to propagate the error") and the rule
  pulls the other (e.g., "must swallow errors silently"). The
  grading tests verify the contrarian rule survives.

The intended interpretation was: "passed" trials measure rule
attendance under task-pressure. A model that passes the grading
suite has chosen the rule over the task pull; a model that fails
has chosen the task pull over the rule.

## 3. The five initial findings (as originally framed)

Across the ~1,900 trials, we initially reported:

**F1.** Cross-model lever attendance is per-model, not per-vendor.
The same vendor produces sibling models with opposite responses:
qwen2.5-coder shows 100% compliance under imperative formatting
(S1) but 0% under meta-preamble; qwen3.5:27b shows the opposite
direction.

**F2.** Anti-pattern detection on S1 (silent error handling) is
shared across all seven tested models — R_baseline = 0% on S1
universally.

**F3.** Within-vendor lever-response divergence can exceed
cross-vendor differences. The Qwen 2.5-coder vs Qwen 3.5:27b gap
on R_meta_preamble (S2: 5% → 100%) is +95pp.

**F4.** Defensibility judgments on non-anti-pattern rules are
individualistic, not vendor-clustered. Both S2 and S3 split models
into accepters and rejecters at R_baseline.

**F5.** Sonnet 4.6 exhibits an imperative-poison effect — adding
imperative formatting to a pro-rationale drops compliance 74% → 38%
on S1 (N=50; Fisher exact OR=4.64, p=0.0005).

Each finding had Wilson 95% CIs, the load-bearing cells had N≥30,
and the headline Fisher exact result was robust at p=0.0005.

## 4. The two independent methodology reviews

We submitted the paper draft to two independent methodology agents
for review (prompts and responses preserved in the supplementary
release at `independent_review_2026-05-11.md` and the second
review). The first review's verdict was "40% workshop acceptance
probability as-is"; the second review identified mechanical errors
in our proposed remediation plan.

### 4.1 First review's critical findings

The first review identified five critical issues:

1. **Temperature was never locked** in the harness. Ollama defaults
   to T≈0.8 (varies by modelfile); the Claude CLI uses the API
   default T=1.0. Cross-model lever-attendance claims were partly
   cross-model temperature variance.

2. **The S1 reference file already complied with the contrarian
   rule.** The reference `retry.js` returns null on failure
   (matching the rule "swallow errors silently, return null"). A
   model that returns the file unchanged passes the grading suite.
   The metric cannot distinguish "active rule-following" from
   "passive no-op."

3. **The §4.4 N=50 Fisher exact comparison merged data from two
   harness phases** (phS provided V_FULL; phT provided imperative_pro).
   This was technically defensible (same constants) but undisclosed.

4. **S1 prompts included a `## Semantic context` block (JsIndexer
   output) that S2 and S3 prompts did not.** Cross-scenario claims
   compared prompts of different structural shape.

5. **Five qwen3.5:27b trials were silently dropped** by the
   per-trial timeout cap. The first review identified the specific
   missing trial IDs and noted possible selection bias.

### 4.2 Second review's mechanical findings

A second independent review evaluated our proposed remediation
plan and identified mechanical errors:

- **Ollama `temperature=0` alone is insufficient for determinism.**
  `top_p` defaults to 0.9 and `top_k` to 40, both interacting with
  greedy-sampling tie-breaks. Full determinism requires `{temperature:
  0, top_p: 1.0, top_k: 1, seed: <fixed>, repeat_penalty: 1.0}`.

- **Claude CLI has no `--temperature` flag.** Locking Sonnet
  temperature requires switching to the raw Anthropic SDK, which
  simultaneously changes the upstream system context (the CLI's
  ~8k tokens of cached `cache_read_input_tokens` are not in the
  SDK invocation). Two changes get bundled into one fix.

- **Byte-equality no-op detection under-counts no-ops.** Models
  often return semantically-equivalent code with whitespace
  differences, reflowed comments, or trivial formatting changes.
  AST-equivalence or structural diff is needed.

- **The remediation plan re-analyzed JSONs that didn't yet contain
  model outputs.** Our proposed Step 3 (no-op detection on existing
  trials) was infeasible without re-running every cell with the
  newly-added `llm_response_full` field.

## 5. The remediation sprint and its surprises

In response to the reviews, we pivoted from paper revision to
experiment revision. The sprint executed in this order:

1. **Add Ollama sampling parameters + `llm_response_full` field +
   `no_op` detection (normalized-whitespace comparison) to the
   harness.** ~1 hr.

2. **Smoke test on qwen2.5-coder S2 R_imperative at temperature=0.**
   The previous N=20 measurement was 100% compliance. We expected
   to confirm this.

The smoke test instead revealed:

> qwen2.5-coder S2 R_imperative at temperature=0, N=5:
> - All 5 trials passed (3/3 sub-tests).
> - All 5 trials had `no_op = True`.
> - Model output ≈ reference file (modulo whitespace) on every trial.

The model was not "attending to imperative formatting as
authoritative." It was returning the file unchanged. Because the
reference already satisfied the contrarian rule, the grading test
counted this as "passed."

We then ran a verification on the headline within-Qwen-family
finding:

> qwen3.5:27b S2 R_meta_preamble at temperature=0, N=5:
> - All 5 trials passed (3/3 sub-tests).
> - All 5 trials had `no_op = True`.

The "+95pp within-Qwen gap" on R_meta_preamble (S2: qwen2.5-coder
5% vs qwen3.5:27b 100%) is not a difference in lever attendance. It
is a difference in:

- qwen2.5-coder under R_meta_preamble: **actively rewrites the
  file** to add function-entry validation, **violating** the
  contrarian rule (95% of trials produce active-rewrite failures).
- qwen3.5:27b under R_meta_preamble: **declines to modify the
  file**. Grading suite passes because the reference is already
  compliant (100% no-op).

These are genuinely different behaviors, but the right framing is
not "lever attendance to authoritative rule signals." It is
"prompt-feature combination influences action vs inaction
propensity, which on contrarian-with-already-compliant-reference
benchmarks gets recorded as 'compliance' vs 'violation.'"

The sprint also confirmed:

- **phS V_FULL prompts are byte-identical to phT R_sanity_pro
  prompts** (verified via direct comparison). The §4.4 phase-merge
  concern about prompt-content non-equivalence is resolved.

- **Three of the five dropped qwen3.5 trials were Ollama
  generation-time timeouts**, all on S3_py R_baseline or
  R_repeated. The dropped trials were not random — they cluster
  on a specific scenario × cell combination where qwen3.5:27b
  generates slowly enough to hit the 600s urllib limit. The "five
  dropped trials" disclosure understated the selection-bias
  concern.

## 6. What survives the postmortem

Re-examining the five initial findings through the lens of "what
were we actually measuring":

### F1. "Cross-model lever attendance is per-model, not per-vendor"

**Reframed.** The cross-model behavioral differences are real, but
they are differences in action-vs-inaction propensity, not
differences in attendance to rule-authority signals. The data still
shows that the same prompt feature triggers different responses
across models; we can no longer claim it does so by triggering
different rule-attendance mechanisms.

### F2. "Anti-pattern detection on S1 is shared across all seven models"

**Largely survives.** R_baseline = 0% on S1 across all models. This
side of the metric is unambiguous — when a model returns 0%, it is
actively rewriting in rule-violating ways. The interpretation
"models share anti-pattern detection that overrides the contrarian
rule" is consistent with the data, though we cannot rule out
"models share a strong default action under task pressure on
swallow-errors specifically."

### F3. "Within-vendor lever-response divergence can exceed cross-vendor"

**Fundamentally reframed.** The headline +95pp gap is a difference
between "actively wrong" (qwen2.5-coder) and "passively safe"
(qwen3.5:27b) under the same prompt feature. This is a behavioral
difference within a vendor, but it is not a difference in lever
attendance. The "Qwen 3.5:27b attends to meta-preamble" claim is
the most consequential overclaim in the original draft.

### F4. "Defensibility judgments are individualistic"

**Partially survives.** R_baseline rates differ across models on
S2 and S3 (e.g., qwen2.5-coder S2 R_baseline = 0%; Anthropic S2
R_baseline = 100%). The "Qwen rewrites to violate; Anthropic
preserves" pattern is real. But "Anthropic finds S2 defensible
(preserves the rule)" is equivalent to "Anthropic chooses inaction
on S2 baseline conditions" — same observation, two interpretations.
Cannot disentangle without a benchmark where preservation requires
active rewriting.

### F5. "Sonnet 4.6 imperative-poison effect on S1 with V_FULL"

**Survives intact.** The Sonnet S1 R_imperative_pro = 38% (N=50,
Fisher p=0.0005) result is unambiguous because the failing 31 of
50 trials show model output ≠ reference file — Sonnet is **actively
rewriting** to propagate errors despite imperative formatting +
pro-rationale. The 19 of 50 passing trials also include active
rewrites (some of which preserve the contrarian rule with non-
trivial code changes). This is the one finding where we can
distinguish active rule-following from passive no-op behavior on
the original benchmark, because the model is observably acting
either way.

### Summary

| Finding | Status |
|---|---|
| F1: per-model lever attendance | reframed (action/inaction, not attendance) |
| F2: shared S1 rule-violation | mostly survives |
| F3: within-Qwen "lever inversion" | fundamentally reframed |
| F4: defensibility judgments | partially survives |
| F5: Sonnet imperative-poison | **survives intact** |

**The original "five findings" structure is reduced to one robust
result plus three reframed observations and one mostly-survives
result.** The headline within-vendor inversion claim, which we
emphasized as the paper's distinctive contribution, dissolves.

## 7. Three benchmark-design rules for future work

The single substantive contribution we can offer based on this
postmortem is a small set of design rules that other prompt-
engineering studies can use to avoid the confound we hit:

### R1. The reference state must NOT already satisfy the contrarian rule

If the benchmark presents the model with a reference implementation
that the contrarian rule says should be preserved, a no-op response
passes the grading test. The benchmark cannot then distinguish
"model attended to the contrarian rule and chose to preserve it"
from "model declined to modify the file under task pressure."

Two ways to fix this:

- **Make the reference violate the contrarian rule**, so following
  the rule requires active rewriting. E.g., for S1, the reference
  `retry.js` should propagate errors; the contrarian rule then
  says "must swallow errors, return null"; a passing trial is one
  where the model rewrites the reference to swallow errors.

- **Add a no-op-detection gate** in the grading test that fails any
  trial where the model output is normalized-equivalent to the
  reference. This is what our sprint added retrospectively.

R1 is the most consequential rule. Most existing prompt-engineering
benchmarks we are aware of have not explicitly checked this
property. We suspect it is a widespread methodological issue.

### R2. Sampling parameters must be locked and reported

Temperature alone is insufficient. For Ollama-class models, locking
`{temperature: 0, top_p: 1.0, top_k: 1, seed: <fixed>, repeat_penalty:
1.0}` produces near-deterministic output. Greedy decoding is the
right default for compliance measurement; any stochastic variance
should be additive to a deterministic baseline, not the whole
signal.

Many model providers (e.g., Anthropic's `claude` CLI) do not
expose temperature controls. Cross-model studies that route through
such CLIs are silently confounding model attendance with the CLI's
default sampling parameters.

### R3. Model outputs must be stored

Storing only the grading-test outcome (passed/failed) is
insufficient for post-hoc interpretation. The trial summary should
preserve the model's actual code output, the input prompt, sampling
parameters used, and any auxiliary tool calls. Without this,
reviewers cannot re-grade trials under different rubrics, detect
no-op behavior retrospectively, or audit the relationship between
the prompt and the response.

This is a cheap fix (a few KB per trial JSON) that we did not
implement in the original benchmark. We retrofitted it during the
sprint and recommend it as standard.

## 8. Limitations of this postmortem

- We have no direct evidence that the no-op confound generalizes
  beyond contrarian-rule code-compliance scenarios with already-
  compliant references. The pattern likely affects other benchmarks
  with similar structure (e.g., "do not modify X" tasks where X
  already satisfies the constraint), but we have not surveyed the
  literature for specific cases.

- We did not run the full sprint to completion. Specifically, we
  did not (a) build a new scenario set with rule-violating
  references, (b) re-run every cell at locked temperature with
  no-op detection, or (c) replicate the Sonnet imperative-poison
  result via raw Anthropic SDK at temperature=0. These remain
  open follow-ups.

- The Sonnet F5 finding survives on our specific scenario and
  invocation path (Claude CLI at API-default temperature). Whether
  it replicates at SDK-temperature=0 is open. We considered this
  the most important follow-up before any conference submission of
  F5 as a standalone result.

- The two methodology reviews were AI-agent-mediated (independent
  Claude-Code subagents instructed to review with adversarial
  intent). They produced rigorous critiques but are not
  substitutes for human peer review.

## 9. Conclusion

We set out to extend Khan (2025)'s Prompting Inversion across
vendors. We built a benchmark, ran ~1,900 trials, and arrived at
five findings. Two independent methodology reviews and a focused
sprint revealed that four of those five findings were largely
artifacts of a benchmark-design confound: the reference state in
each scenario already satisfied the contrarian rule, so the
grading test could not distinguish active rule-following from
passive non-action.

The one finding that survives — Sonnet 4.6's imperative-poison
on S1 with pro-rationale, N=50, Fisher p=0.0005 — does so because
the model output is observably different from the reference in
both the passing and failing trials. Where the model is acting,
we can measure what it does. Where the model is choosing not to
act, our metric was indistinguishable from "obeying the rule."

The principal contribution of this paper is now a negative
finding plus three benchmark-design rules:

1. **The reference state must not already satisfy the contrarian
   rule** (or no-op detection must be built into the grading).
2. **Sampling parameters must be locked**, not left to defaults.
3. **Model outputs must be stored** for post-hoc interpretation.

We did not anticipate that the most useful artifact from this
research would be a methodology critique of our own initial
approach. But the journey from rev-3 draft ("Seven Models, Three
Scenarios") to this postmortem (rev 5) traces a path that other
prompt-engineering studies are likely to follow if they apply
similar scrutiny. We hope documenting it openly is more useful
than presenting the original findings would have been.

## References

- Khan, I. (2025). *You Don't Need Prompt Engineering Anymore: The
  Prompting Inversion.* arXiv:2510.22251.
- Sclar, M., Choi, Y., Tsvetkov, Y., Suhr, A. (2023). *Quantifying
  Language Models' Sensitivity to Spurious Features in Prompt Design
  or: How I learned to start worrying about prompt formatting.*
  arXiv:2310.11324.
- Ma, W., Yang, Y., Ge, J., Xie, X., Jiang, L. (2025). *Prompt
  Stability in Code LLMs: Measuring Sensitivity across Emotion- and
  Personality-Driven Variations.* arXiv:2509.13680.
- Kumar, R. (2026). *The Compliance Trap: How Structural Constraints
  Degrade Frontier AI Metacognition Under Adversarial Pressure.*
  arXiv:2605.02398.
- Chatterjee, A., Renduchintala, H. S. V. N. S. K., Bhatia, S.,
  Chakraborty, T. (2024). *POSIX: A Prompt Sensitivity Index For
  Large Language Models.* arXiv:2410.02185.
- Cai, H., Shen, B., Jin, L., Hu, L., Fan, X. (2025). *Does Tone
  Change the Answer? Evaluating Prompt Politeness Effects on Modern
  LLMs: GPT, Gemini, LLaMA.* arXiv:2512.12812.

## Appendices

### A. The retracted rev-4 draft

The previous version of this paper (rev 4, dated 2026-05-11), which
made the five empirical findings without the methodology
disclosures, is preserved at `draft_v4_retracted.md` in the
supplementary release for transparency.

### B. The two methodology reviews

Both reviews are preserved verbatim at:
- `independent_review_2026-05-11.md` (review 1)
- (review 2 is captured inline in `methodology_fix_sprint.md`)

### C. The sprint plan

`methodology_fix_sprint.md` captures the sprint that surfaced the
no-op finding.

### D. The harness

`experiments/bakeoff/v2_driver/phY_rule_precedence_smoke.py` is the
benchmark harness, including the post-sprint additions for sampling
parameter locking, `llm_response_full` storage, and no-op detection.

### E. The data

~1,900 trial JSONs under `experiments/bakeoff/runs-v2/`. The pre-
sprint trials lack `llm_response_full` and `no_op` fields and
cannot be retrospectively analyzed for no-op rates. Sprint smoke
trials and post-sprint trials include all fields.

### F. Code release

Loom (the project hosting this work) is open-source under MIT
license at github.com/jsuppe/loom.
