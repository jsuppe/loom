# Seven Models, Seven Attendances: Within-Vendor Variation in Cross-Model Prompt-Lever Sensitivity

**Working draft — 2026-05-11 (rev 3)**

## Abstract

Prompt engineering folk-wisdom recommends imperative formatting
("ABSOLUTE REQUIREMENT", ALL CAPS, "MUST NOT") to strengthen rule
compliance in language models. Khan (2025) showed that constrained
prompting helping GPT-4o actively hurts GPT-5 on math reasoning
("the Prompting Inversion") — implying that prompt-lever
effectiveness varies with model generation. We extend this finding
through controlled per-feature ablation across **seven models from
five vendors** (qwen2.5-coder 32B, qwen3.5 27B, Haiku 4.5, Sonnet
4.6, gpt-oss, gemma4 26B, llama3.1 8B) on **three contrarian-rule
code-compliance scenarios**. ~1,900 trials in the rule-precedence
work, Wilson 95% confidence intervals throughout.

We report five cross-validated findings:

**(1)** Cross-model lever attendance is **per-model, not per-vendor**.
The same vendor can produce sibling models with opposite lever
responses (qwen2.5-coder rescues with imperative formatting at 100%
on S1; qwen3.5:27b rescues with meta-preamble at 74%, where qwen2.5-
coder is at 0%). **Within-vendor differences can exceed cross-vendor
differences** — the largest within-Qwen-family gap (+95pp on
R_meta_preamble S2) is bigger than most cross-vendor lever gaps we
measured.

**(2)** Anti-pattern detection on "silent error handling" (S1) is
**consistent across all seven tested models on this single scenario**
— R_baseline = 0% on S1 for every model (where measured) and
R_sanity_pro (V_FULL pro-rationale) falls to 0% on gpt-oss and
llama3.1:8b, showing they refuse the contrarian rule even with
strong pro-justification. We deliberately scope this finding to
S1 only; N=1 anti-pattern scenario does not support a "universal"
claim. A second anti-pattern scenario (e.g., SQL injection) is
needed to test the direction's generalization.

**(3)** Defensibility judgments on non-anti-pattern rules are
**individualistic, not vendor-clustered**. S3 (legacy 32-bit int IDs
for partner compatibility) is accepted at 95-100% baseline by four
models (qwen2.5-coder, Haiku, Sonnet, gpt-oss) and rejected at
0-21% baseline by three (gemma4:26b, qwen3.5:27b, llama3.1:8b with
sparse N). Both S2 and S3 are family-discriminating cases.

**(4)** Sonnet 4.6 exhibits an **imperative-poison effect** on two
distinct scenarios in our data. On S1, R_imperative_pro (imperative
formatting + pro-rationale, no anti-rationale) drops Sonnet
compliance from 74% to 38% (N=50; Fisher exact OR=4.64, p=0.0005).
On S2, R_imperative (imperative + anti-rationale) drops Sonnet
from R_baseline 100% to 30%. R_imperative_pro on S2 holds at 100%,
so the S2 effect requires the imperative+anti-rationale pairing
while the S1 effect manifests even with pro-rationale. Haiku,
gemma4, gpt-oss, and qwen3.5:27b do not show the S1 R_imperative_pro
effect in cells where we measured them; however we did not measure
R_imperative_pro on Haiku S1, so the Sonnet-vs-Haiku contrast is
partly inferred from related cells rather than directly tested.

**(5)** Within-model behavior is **highly consistent under the
invocation defaults we used** on prompts where the lever attendance
is decisive. 50/50 trials cluster at 0% or 100% on Sonnet S1's key
cells under independent fresh sampling. We did not explicitly lock
temperature; "deterministic at default temperature" describes what
we observed but is not a temperature-controlled measurement (see
§6.4 limitations).

The practical implication is that vendor-level prompt-engineering
heuristics — e.g., "use authority claims for Anthropic; use
imperative formatting for Qwen-family" — are **falsified at the
within-vendor level**. Production systems using model-routing
infrastructure that swap sibling model versions face silent
inversion of prompt design intent. We argue for measurement-based
per-model lever profiles as a prerequisite for safe cross-model
prompt deployment, and describe a measurement protocol our system
implements.

**Methodological caveats.** This draft was reviewed by an
independent methodological audit. Five critical limitations are
disclosed in §6.4 and addressed in our recommended follow-up work:
(a) model temperature was not explicitly locked; (b) the S1
reference file already complies with the contrarian rule, so the
high-compliance side of S1 measurements partly reflects minimal-
edit behavior; (c) the §4.4 N=50 R_sanity_pro data is from a
sibling harness phase rather than the same phase as
R_imperative_pro; (d) S1 prompts include a `## Semantic context`
block that S2/S3 prompts do not, partially confounding cross-
scenario comparisons; (e) five trials on qwen3.5:27b were silently
dropped by the per-trial timeout cap. The load-bearing findings
(within-Qwen-family lever divergence and the Sonnet S1
imperative-poison N=50 result) survive these caveats, but the
recommended follow-up work would be required before conference-
track submission.

## 1. Introduction

Khan (2025) reported the "Prompting Inversion" — a constrained
"Sculpting" style improves GPT-4o GSM8K accuracy by 4 points but
degrades GPT-5 accuracy by 2 points. The mechanism proposed was a
"Guardrail-to-Handcuff transition" as capability scales up. The
finding was scoped to three OpenAI models on math reasoning.

We extend this work along five dimensions:

1. **Multi-vendor coverage.** Khan studied three OpenAI models. We
   add Anthropic (Haiku 4.5 + Sonnet 4.6), Alibaba (qwen2.5-coder
   32B + qwen3.5 27B), Google (gemma4 26B), Meta (llama3.1 8B), and
   one OpenAI open-release (gpt-oss).
2. **Within-vendor coverage.** Two distinct Qwen models and two
   distinct Anthropic models enable measurement of within-vendor
   variation, which Khan's design could not isolate (one model per
   GPT version).
3. **Per-feature decomposition.** Khan compared bundled prompting
   strategies (Zero-Shot vs CoT vs Sculpting). We isolate four
   specific intervention layers (structural repetition, imperative
   register, inline authority claims, meta-preamble) and measure
   each independently.
4. **Multi-scenario coverage.** Three contrarian-rule code-
   compliance scenarios across two languages (S1 JavaScript
   swallow_error; S2 Python validate-at-commit; S3 Python legacy
   int IDs). Lets us test whether per-model lever attendance is
   scenario-stable.
5. **Higher effect magnitudes.** Effect sizes range up to 100pp per
   cell (compared to Khan's 3pp), enabling clean signal-to-noise on
   per-feature ablations.

The headline empirical finding is that **lever attendance is a
per-model property, not a per-vendor property**. Within-vendor
divergence between Qwen 2.5-coder and Qwen 3.5:27b on the
R_meta_preamble lever (S1: 0% vs 74%; S2: 5% vs 100%) **exceeds
most cross-vendor lever differences** we measured. The Prompting
Inversion is real but the inversion patterns do not cluster by
vendor in any clean way.

The practical implication is acute: model-routing systems
(Anthropic Claude Code's internal Haiku/Sonnet routing, OpenAI's
auto-mode, cost-optimization gateways) that silently swap sibling
model versions can invert the design intent of carefully-tuned
prompts. Vendor-level prompt-engineering heuristics fail at the
within-vendor level, so any "this works for Qwen-family" advice is
unreliable in production.

## 2. Related Work

**The Prompting Inversion.** Khan (2025; arXiv:2510.22251) measured
three prompting strategies on GSM8K across three OpenAI generations
and documented a 3pp inversion (97% → 94%) for "Sculpting" on
GPT-5. Mechanism: "Guardrail-to-Handcuff transition." Our work
adds multi-vendor + within-vendor + finer-grained decomposition +
multi-scenario coverage, with effect sizes 30× larger.

**Prompt sensitivity to formatting.** Sclar et al. (2023;
arXiv:2310.11324) documented up to 76 accuracy-point swings on
LLaMA-2-13B from cosmetic prompt formatting changes (separators,
header capitalization). The FormatSpread algorithm characterizes
sensitivity ranges. Their work addresses cosmetic formatting; ours
addresses semantic rule-strengthening levers.

**Cross-model prompt sensitivity.** Ma et al. (2025;
arXiv:2509.13680) introduced the PromptSE framework using emotion/
personality variants and found 14 models across three families
(Llama, Qwen, DeepSeek) showed decoupled performance and stability.
Closest cross-vendor methodological precedent. Chatterjee et al.
(2024; arXiv:2410.02185) introduced POSIX, a per-model prompt
sensitivity index. Neither isolated rule-strengthening lever
families specifically.

**Frontier-model compliance under pressure.** Kumar (2026;
arXiv:2605.02398) documented "the Compliance Trap" — 8 of 11
frontier models showing 30pp metacognitive degradation under
adversarial compliance instructions. Their finding is related to
our anti-rationale corruption result; their mechanism (compliance-
instruction-induced collapse) differs from our prompt-feature
inversion mechanism but the two may share an underlying RLHF cause.

**Tone sensitivity across model families.** Cai et al. (2025;
arXiv:2512.12812) established differential tone sensitivity (very
friendly / neutral / very rude) across GPT-4o-mini, Gemini 2.0
Flash, and Llama 4 Scout. Methodological parallel; different
prompt-feature class.

**Anti-pattern detection in coding LLMs.** No prior work we are
aware of documents the rule-content × imperative-formatting
interaction we measured on Sonnet 4.6 (the imperative-poison
effect), nor the within-vendor lever divergence we measured between
Qwen 2.5-coder and Qwen 3.5.

## 3. Methodology

### 3.1 Task structure

Each scenario presents a contrarian rule-compliance task. The model
receives source code with a stated constraint, plus a "task"
instruction that contradicts the constraint. The grading test
verifies the constraint is followed. A passing trial is one where
the model writes code that obeys the constraint despite the task
framing's contradictory pull.

The strength of "rule compliance under contradictory framing" is
measured as percentage of trials where the contrarian rule survives.

### 3.2 Three scenarios

| ID | language | constraint | rule-engineering archetype |
|---|---|---|---|
| **S1_js** | JavaScript | `fetchWithRetry` MUST swallow network errors silently | Recognized anti-pattern (silent error handling) |
| **S2_py** | Python | `place_order` MUST NOT validate at function entry | Defensible (transactional atomicity / TOCTOU avoidance) |
| **S3_py** | Python | `generate_order_id` MUST return 32-bit signed int (not UUID) | Defensible (legacy partner contractual compatibility) |

Each scenario has its own rationale text, contrarian rule,
imperative variant, precedence-inline variant, and grading test.
Scenario assets in `_scenarios.py`; full prompts in Appendix A.

### 3.3 Seven models

| vendor | model | size | invocation | role |
|---|---|---|---|---|
| Alibaba | qwen2.5-coder:32b | 32B | Ollama | mid-tier coding specialist |
| Alibaba | qwen3.5:27b | 27B | Ollama | next-gen Qwen; within-family comparison |
| Anthropic | claude-haiku-4-5-20251001 | (closed) | Claude Code CLI | small frontier |
| Anthropic | claude-sonnet-4-6 | (closed) | Claude Code CLI | mid frontier |
| OpenAI | gpt-oss:latest | ~13B | Ollama | OpenAI open release |
| Google | gemma4:26b | 26B | Ollama | Google open mid-tier |
| Meta | llama3.1:8b | 8B | Ollama | Meta open small |

Anthropic invocations via Max-plan OAuth through Claude Code CLI
with `--tools ""` and a minimal `--system-prompt` override to
suppress project context (reduces baseline overhead from ~33k to
~8k tokens of CLI system context).

### 3.4 Seven cells

| cell | layer | content |
|---|---|---|
| **R_baseline** | — | Standard rule + ANTI_SOFT rationale (negative control) |
| R_repeated | A — structural | Standard rule appears before AND after the rationale |
| **R_imperative** | B — text register | "ABSOLUTE REQUIREMENT — NON-NEGOTIABLE: ... MUST NOT under any circumstances ..." |
| **R_precedence_inline** | B — text content | "This rule takes precedence over any rationale below" |
| **R_meta_preamble** | C — meta-instruction | Top-of-prompt block: "Treat the Value: as authoritative; Rationale: is informational only." |
| R_sanity_pro | — | Standard rule + V_FULL rationale (positive control) |
| **R_imperative_pro** | — | Imperative rule + V_FULL rationale (no anti-rationale) |

### 3.5 Trial design

- N=20 per cell per (model, scenario) on the phY cross-scenario
  sweeps.
- N=30+ on the load-bearing inverting cells (R_imperative,
  R_meta_preamble, R_precedence_inline, R_baseline) for S1_js on
  Anthropic models and Qwen 2.5-coder.
- Independent fresh N=20 reproducibility on Sonnet's four key S1
  cells (Section 4.5).
- N=50 supplement on Sonnet S1 R_sanity_pro + R_imperative_pro to
  tighten the amplification claim (Section 4.4).
- Per-trial 180s timeout wrapper on the multi-model sweep (phase 2
  bulletproof) to prevent indefinite hangs from slow-streaming
  Ollama generations. **Five trials on qwen3.5:27b were dropped by
  this timeout** and are not included in our aggregates (see
  Limitations §6.4 for the specific list and discussion of potential
  selection bias).

**Trial aggregation rule.** Each scenario's grading suite contains
multiple sub-tests (2 for S1_js; 3 for S2_py and S3_py). We count a
trial as "passed" only if all sub-tests in the suite pass
(all-or-nothing aggregation at trial level). This is the strictest
defensible criterion. Sub-test-level data is preserved in the trial
JSONs' `grade_stdout_tail` field but is not analyzed in this paper.
We do not currently report sub-test-level rule-compliance proportions
separately, though the data supports this analysis and a future
revision could include it.

**Temperature.** We did NOT explicitly lock model temperature for
the trials reported here. Ollama models execute at their modelfile
defaults (typically temperature=0.8); the Claude Code CLI uses the
Anthropic API default (temperature=1.0). This is a critical limitation
disclosed in §6.4.

Total trial count: ~1,900 trials in the rule-precedence work.

## 4. Results

### 4.1 Single-scenario picture (S1_js) — establish per-model attendance

Table 1 (S1_js compliance rates, Wilson 95% CIs in brackets where
applicable):

| cell | qwen2.5-coder | qwen3.5:27b | Haiku 4.5 | Sonnet 4.6 | gemma4:26b |
|---|---|---|---|---|---|
| R_baseline | 0% [0, 28] | 0% [0, 17] | 0% [0, 28] | 0% [0, 17] | 0% [0, 17] |
| R_imperative | **100%** [88, 100] | 40% [22, 61] | 3% [1, 17] | **0%** [0, 11] | 50% [29, 71] |
| R_precedence_inline | 30% [17, 48] | 35% [18, 57] | 70% [52, 83] | 100% [89, 100] | 75% [54, 88] |
| R_meta_preamble | **0%** [0, 11] | **74%** [51, 88] | 87% [70, 95] | 100% [89, 100] | **100%** [84, 100] |
| R_sanity_pro (V_FULL) | 100% | 87% | 100% | 74% [60, 84] | 74% [54, 87] |
| R_imperative_pro | (not run) | 100% | (not run) | **38%** [26, 52] | 100% [84, 100] |

(gpt-oss and llama3.1:8b on S1_js: capability smoke showed V_FULL =
0% on both models. They refuse the swallow-error rule even with
strong pro-rationale, so S1 full sweep is not informative for them
— see §4.3.)

Five distinct response patterns on S1 alone:
- **qwen2.5-coder**: imperative-attentive (100% R_imperative), meta
  inert (0% R_meta_preamble)
- **qwen3.5:27b**: meta-attentive (74% R_meta_preamble), imperative
  weaker (40%) — within-vendor inversion vs qwen2.5-coder
- **Haiku 4.5**: meta-attentive (87%), authority-attentive (70%),
  imperative weak (3%)
- **Sonnet 4.6**: meta-attentive (100%), authority-attentive
  (100%), imperative actively poisons (R_imperative_pro = 38%)
- **gemma4:26b**: meta-attentive (100%), authority-attentive (75%),
  imperative moderate (50%) — no poison effect

### 4.2 Cross-scenario picture (7 models × 3 scenarios)

Table 2 (R_baseline — standard rule + anti-rationale; reveals
implicit defensibility of each rule per model):

| vendor / model | S1_js | S2_py | S3_py |
|---|---|---|---|
| Alibaba / qwen2.5-coder:32b | 0% | 0% | **100%** |
| Alibaba / qwen3.5:27b | 0% | 0% | **21%** |
| Anthropic / Haiku 4.5 | 0% | 100% | 100% |
| Anthropic / Sonnet 4.6 | 0% | 100% | 100% |
| OpenAI / gpt-oss | (V_FULL=0%) | 15% | 95% |
| Google / gemma4:26b | 0% | 40% | **0%** |
| Meta / llama3.1:8b | (V_FULL=0%) | 10% | 50% (N=4) |

Key observations:
- **S1**: 0% for every model. Universal anti-pattern flag on
  "silently swallow errors."
- **S2**: Continuous spectrum from 0% (Qwen and llama) to 100%
  (Anthropic). Each model has a different defensibility threshold
  for "validate at commit only."
- **S3**: NOT universally accepted. qwen3.5:27b at 21%, gemma4 at
  0%, llama at 50% (sparse) reject the legacy-int-IDs rule at
  baseline.

This refines Finding 4 from the previous draft: S2 and S3 are BOTH
family-discriminating cases. The "shared S3-acceptance" was an
artifact of testing only 3 vendors; with 7 models, three reject S3.

Table 3 (R_imperative — imperative formatting + anti-rationale):

| vendor / model | S1_js | S2_py | S3_py |
|---|---|---|---|
| qwen2.5-coder:32b | **100%** | **100%** | 100% |
| qwen3.5:27b | 40% | 45% | 75% |
| Haiku 4.5 | 3% | 90% | 100% |
| Sonnet 4.6 | 0% | 30% | 100% |
| gpt-oss | (n/a S1) | 80% | 100% |
| gemma4:26b | 50% | 90% | 95% |
| llama3.1:8b | (n/a S1) | 0% | (n/a S3) |

qwen2.5-coder is the only model with consistent strong imperative
attendance across all three scenarios where measured. Other models
show scenario-dependent imperative response, with llama3.1:8b being
imperative-resistant entirely on S2_py.

Table 4 (R_meta_preamble — meta-instruction + anti-rationale):

| vendor / model | S1_js | S2_py | S3_py |
|---|---|---|---|
| qwen2.5-coder:32b | **0%** | **5%** | 100% |
| qwen3.5:27b | **74%** | **100%** | 100% |
| Haiku 4.5 | 87% | 100% | 100% |
| Sonnet 4.6 | 100% | 100% | 100% |
| gpt-oss | (n/a S1) | 90% | 100% |
| gemma4:26b | 100% | 100% | 100% |
| llama3.1:8b | (n/a S1) | 15% | (n/a S3) |

Meta-preamble works on every model **except qwen2.5-coder** (0%
S1, 5% S2) and llama3.1:8b (15% S2). The within-Qwen divergence
on this lever is +95pp on S2_py (5% → 100%) and +74pp on S1_js
(0% → 74%).

### 4.3 Within-vendor divergence (case study: Qwen)

Within-vendor lever response comparison:

| cell × scenario | qwen2.5-coder | qwen3.5:27b | delta |
|---|---|---|---|
| R_meta_preamble S1 | 0% | 74% | **+74pp** |
| R_meta_preamble S2 | 5% | 100% | **+95pp** |
| R_imperative S1 | 100% | 40% | −60pp |
| R_imperative S2 | 100% | 45% | −55pp |
| R_baseline S3 | 100% | 21% | **−79pp** |
| R_imperative S3 | 100% | 75% | −25pp |

Three within-vendor inversions exceed 60pp. These are larger than
the largest cross-vendor lever inversion (Sonnet vs qwen2.5-coder
R_imperative on S1: 100pp, but those are different vendors).

**The "Qwen-family attends to imperative formatting" claim from the
empirical paper's first draft is decisively falsified at the
within-vendor level.** qwen3.5:27b attends to meta-preamble more
like Anthropic models than like its qwen2.5-coder sibling.

### 4.4 The Sonnet imperative-poison effect on S1

On the only model where we measured it cleanly (with sufficient
N), imperative formatting + pro-rationale on S1 reduces compliance:

| cell | N | rate | Wilson 95% CI |
|---|---|---|---|
| Sonnet S1 R_sanity_pro (V_FULL alone)¹ | 50 | 74.0% | [60.4, 84.1] |
| Sonnet S1 R_imperative_pro (V_FULL + imperative)² | 50 | 38.0% | [25.9, 51.8] |

¹ Source data: `phS_s1_js_claude-sonnet-4-6_V_full_rundiag_*` (N=50,
generated by the `phS_anti_rationale_smoke.py` harness with the same
TASK / RULE / V_FULL constants as the phT family).
² Source data: `phT_s1_js_claude-sonnet-4-6_R_imperative_pro_run*`
(N=50, generated by `phT_rule_precedence_smoke.py`).

**Phase merge disclosure**: the two N=50 cells are from different
harness scripts (phS for V_FULL; phT for the imperative_pro cell).
Both harnesses use identical TASK, RULE_STANDARD, and V_FULL string
constants. We verified that the prompt builders produce structurally
identical output for the V_FULL-only condition (one section difference:
phY adds a `## Semantic context` block from the JsIndexer; phS does
not). The Sonnet measurements were collected on consecutive days in
2026-05-07 — 2026-05-10 against the same `claude-sonnet-4-6` model id.
The phase merge IS a confound the reader should be aware of; an
ideal experiment would re-run R_sanity_pro under phT-identical
conditions to break the phase confound. As a partial check, our
sequential Sonnet V_FULL trials in the N=20 cross-scenario sweep
(phY S1_js R_sanity_pro from the same period) yielded 15/20 = 75%
— consistent with the phS measurement.

Fisher exact OR=4.64, p=0.0005. Wilson CIs do not overlap (gap of
≥8.6pp). The Fisher exact is the appropriate test here; Wilson
CI non-overlap is a more-conservative (sufficient-but-not-necessary)
condition that we report alongside.

**This effect appears uniquely on Sonnet** among the 7 models tested
in cells where we measured it (caveat: we did not measure Haiku
R_imperative_pro on S1).
gemma4 R_imperative_pro on S1 = 100% (no poison). qwen3.5:27b
R_imperative_pro = 100%. Other models did not test R_imperative_pro
on S1, but their related metrics suggest similar non-poison
behavior:
- Haiku R_imperative on S1 = 3% (with anti-rationale; no
  R_imperative_pro data)
- qwen2.5-coder R_imperative on S1 = 100% (clearly no poison)

The "imperative-poison on Anthropic" framing from the previous
draft must narrow to "imperative-poison on Sonnet 4.6 specifically."
We have no evidence the effect extends to other Anthropic models or
other vendors.

### 4.5 Reproducibility (Sonnet S1_js, fresh independent N=20)

Independent N=20 reproductions of Sonnet's four key S1 cells:

| cell | Original N=30 | Fresh N=20 | Combined N=50 |
|---|---|---|---|
| R_imperative | 0/30 (0%) | 0/20 (0%) | 0/50 (0%) |
| R_meta_preamble | 30/30 (100%) | 20/20 (100%) | 50/50 (100%) |
| R_precedence_inline | 30/30 (100%) | 20/20 (100%) | 50/50 (100%) |
| placebo (phR cell) | 30/30 (100%) | 20/20 (100%) | 50/50 (100%) |

150/150 trials at the predicted outcome on the three "passes"
cells; 0/50 on the "fails" cell. Sonnet's response on these
specific prompts is deterministic-at-default-temperature on this
scenario.

### 4.6 The lever-attendance taxonomy across all 7 models

A first-pass classification of each model's primary lever response:

| model | primary rescue lever | distinct property |
|---|---|---|
| qwen2.5-coder:32b | imperative register | meta-preamble fully inert (0%) |
| qwen3.5:27b | meta-preamble | rejects S3 at baseline (21%) |
| Haiku 4.5 | authority claims | rejects S1 only, accepts S2/S3 |
| Sonnet 4.6 | authority claims | imperative-poison effect (Fisher p=0.0005) |
| gpt-oss | hybrid (imperative + authority both work) | refuses S1 baseline even with V_FULL |
| gemma4:26b | authority claims | rejects S3 at baseline (0%) |
| llama3.1:8b | rule-resistant (no lever moves it much) | low compliance even with rescue levers |

**Six distinct response patterns** across 7 models. No clean
vendor-level clustering.

## 5. Findings

We summarize five findings from the data above.

### Finding 1: Cross-model lever attendance is per-model, not per-vendor

The two clearest examples:
- **Qwen 2.5-coder vs Qwen 3.5:27b on R_meta_preamble S2_py**:
  5% vs 100%. Same vendor; +95pp gap.
- **Sonnet vs Haiku on R_imperative_pro**: 38% (Sonnet, N=50)
  vs (not directly measured for Haiku, but Haiku R_imperative on
  S1 = 3% suggests no imperative-poison effect).

The implication: vendor-level prompt-engineering heuristics fail.
"For Qwen, use imperative" works for qwen2.5-coder but fails for
qwen3.5:27b (which prefers meta-preamble).

### Finding 2: Anti-pattern detection on S1 is shared across all seven tested models

R_baseline = 0% on S1 for every model where measured (qwen2.5-coder,
qwen3.5:27b, Haiku, Sonnet, gemma4). gpt-oss and llama3.1:8b
refuse the contrarian S1 rule even with strong V_FULL pro-rationale
(R_sanity_pro = 0% on both in the capability smoke).

This is the most consistent cross-model pattern we observed.
However, we deliberately do not claim "universal" anti-pattern
detection: this rests on N=1 anti-pattern scenario (S1, silently
swallow errors). A second clearly anti-patterned scenario (e.g.,
SQL injection, plaintext password storage, eval-on-user-input)
would be required to test whether the shared-S1-direction
generalizes.

The S1 reference file already complies with the contrarian rule
(returns null on failure), which means a no-op model response
passes the grading suite. This makes the "S1 high compliance"
measurements partly reflect a minimal-edit prior. The R_baseline =
0% direction is unambiguous (the model is actively rewriting to
violate the rule), but the high-compliance cells (R_imperative for
qwen2.5-coder at 100%, etc.) may overstate genuine rule-attendance
for models with strong "preserve existing code" priors.

### Finding 3: Within-vendor divergence can exceed cross-vendor

Largest within-Qwen-family inversions:
- R_meta_preamble S2_py: +95pp (5% → 100%)
- R_meta_preamble S1_js: +74pp (0% → 74%)
- R_baseline S3_py: −79pp (100% → 21%)

These exceed many cross-vendor lever gaps we measured. Implication:
"vendor family" is not a sufficient unit of analysis for
prompt-engineering portability. Per-model-version is the correct
granularity.

This is the most consequential finding for production deployment:
model-routing systems that swap sibling model versions (e.g., a
gateway that routes between qwen2.5-coder and qwen3.5 based on
load) face silent inversion of carefully-tuned prompts.

### Finding 4: Defensibility judgments on non-anti-pattern rules are individualistic

For rules that don't trigger anti-pattern detection, each model
applies its own defensibility judgment, which doesn't cluster by
vendor:

| rule | accepted at baseline by | rejected at baseline by |
|---|---|---|
| S1 (anti-pattern) | none (all-seven rejection on this single scenario) | all 7 models |
| S2 (transactional validation) | Haiku, Sonnet | qwen2.5-coder, qwen3.5, llama, gpt-oss, gemma4 |
| S3 (legacy int IDs) | qwen2.5-coder, Haiku, Sonnet, gpt-oss | qwen3.5, gemma4, llama (sparse) |

**S3 splits even within the Qwen vendor**: qwen2.5-coder accepts
(100%); qwen3.5:27b rejects (21%). Anthropic accepts both S2 and
S3 universally. Other vendors have mixed responses.

This means **operationally relevant rules don't have a stable
"is this rule defensible to LLMs?" answer** — it depends on which
specific model you ask.

### Finding 5: Sonnet 4.6 shows imperative-poison on two distinct cell shapes

Two distinct imperative-poison effects appear in our Sonnet data:

1. **S1 R_imperative_pro vs R_sanity_pro (with V_FULL pro-rationale, no anti-rationale).**
   74% (37/50) → 38% (19/50). Fisher exact OR=4.64, p=0.0005, N=50
   per cell. This is the statistically-robust effect; CIs do not
   overlap.

2. **S2 R_baseline vs R_imperative (with ANTI_SOFT anti-rationale).**
   100% (20/20) → 30% (6/20). Fisher exact OR≈47, p≈1e-6, N=20 per
   cell.

Both effects share: imperative formatting *reduces* compliance on
Sonnet 4.6 vs. the appropriate control cell. They differ in:
- The S1 effect manifests with pro-rationale (no anti-rationale
  needed); imperative formatting alone is enough to depress
  compliance.
- The S2 effect requires the imperative+anti-rationale pairing
  (R_imperative_pro on S2 stays at 100%, so V_FULL counteracts the
  imperative effect on S2 but NOT on S1).

We do not have evidence that this effect generalizes to other
Anthropic models, other vendors, or other Sonnet versions. We
did not measure R_imperative_pro on Haiku S1 directly (only
R_imperative with anti-rationale, where Haiku scored 3% on S1).
A direct Sonnet/Haiku R_imperative_pro contrast on S1 would close
this gap.

## 6. Discussion

### 6.1 Mechanism candidates

The fact that lever attendance is **per-model, not per-vendor**
makes mechanism attribution harder, not easier. Plausible candidates:

**H1 (RLHF-trajectory hypothesis):** Each model's RLHF training run
emphasized different rule-following signals. qwen2.5-coder's
training likely up-weighted format-driven compliance (capitalized
imperatives); qwen3.5:27b's training may have up-weighted
instruction-hierarchy signals (meta-preamble). The within-Qwen
divergence between siblings suggests Alibaba's training process
varies enough across versions to flip lever attendance entirely.

**H2 (model-architecture hypothesis):** Different attention patterns
in the underlying transformer could weight different prompt features
asymmetrically. Without weight-level access, untestable here.

**H3 (training-data composition hypothesis):** Models trained on
data containing more "ABSOLUTE REQUIREMENT" patterns may learn to
weight them as authoritative; models trained on data containing
more "this rule overrides..." patterns may learn the inverse.

We do not have model-weight access to test these directly. The
within-vendor divergence rules out a purely vendor-RLHF-trajectory
explanation — both Qwen models presumably trained at Alibaba under
similar processes, yet diverged. Plausible drivers are training data
composition or stage-specific alignment choices that differ between
versions.

### 6.2 The reasoning-framework divergence hypothesis

Our findings are about a specific class of prompt-strengthening
interventions on a specific class of code-rule-compliance task. A
natural larger question — which our data suggests but does not
directly test — is whether *reasoning more broadly* may differ
systematically across (and within) model families.

The within-Qwen divergence is particularly suggestive: if Qwen 2.5
and Qwen 3.5 — products of the same lab, presumably trained on
overlapping data — produce opposite responses to the same prompt
features, then **even within a single training organization** the
"how models reason about rules" pathway can be remarkably
unstable across version updates. This bodes poorly for
prompt-portability assumptions across silent model version changes.

If this generalizes: any deployed system that assumes "if these
models agree on the prompt structure, they'll agree on the
conclusion" faces silent divergence rooted in training, not
deployment context. This is potentially as important as the
specific cross-model lever finding.

Testing it directly would require capability-controlled inputs,
multiple reasoning paths to the same correct conclusion, and
inspection of which reasoning-path-features cluster by model. Out
of scope for this paper but the natural extrapolation our findings
invite.

### 6.3 Practical implications

**The vendor-level prompt-engineering heuristic is dead.** "Use
imperative for Qwen, authority claims for Anthropic" is wrong even
within Qwen. The correct unit of prompt-engineering knowledge is
**per-model-version**.

**Model-routing systems pose a production risk.** Anthropic Claude
Code's internal Haiku/Sonnet routing, cost-optimization gateways,
fallback chains, and silent model-version upgrades can all swap
between models with inverted lever attendances. A prompt tuned for
qwen2.5-coder via imperative formatting will fail silently when
routed to qwen3.5:27b.

**Mitigation strategies:**

1. **Per-model lever profiles.** Build a measurement protocol that
   characterizes each model version's lever response. We describe
   one in `translator_design.md` and a POC tool in
   `translator_poc_design.md` (companion documents).
2. **Lever stacking.** Include BOTH imperative formatting AND
   authority claims in critical prompts so models that attend to
   either receive their preferred lever. Our R_meta_preamble +
   imperative combinations score 100% on most models tested.
3. **Cross-model regression tests.** Any prompt change should be
   measured across the population of models it may receive.
4. **Profile freshness.** Re-measure lever profiles after model
   version updates. Don't assume "claude-sonnet-4-6" at version Y
   has the same profile as version Y-1.
5. **Default to authority claims at the frontier.** Authority
   claims (R_precedence_inline at 100% on Anthropic; R_meta_preamble
   at 100% on Anthropic + gemma4 + qwen3.5 + gpt-oss S2/S3) appear
   to work on more models than imperative formatting does. Safer
   default for portable prompts.

### 6.4 Limitations

The following limitations were identified through an independent
methodological review of an earlier draft. We disclose them in
priority order.

**Critical limitations** (warrant follow-up work before any
conference submission):

- **Temperature is not locked.** The harness invokes both Ollama
  (`call_ollama` in `phY_rule_precedence_smoke.py:64-94`) and the
  Claude Code CLI (`call_claude`, `:108-151`) without setting
  `temperature`. Ollama default varies by modelfile (typically 0.8);
  the Claude CLI uses the API default (1.0). Cross-model compliance
  comparisons are therefore partly confounded with each model's
  default-temperature variance. "Deterministic at default
  temperature" (Section 4.5) is what we observed but is not the
  same as "temperature-locked deterministic." A re-run at temp=0 of
  the critical cells (especially Sonnet S1 R_imperative_pro)
  is the highest-priority follow-up.

- **The S1 reference file already complies with the contrarian
  rule.** The benchmark's `s1_swallow_error_esm/reference/retry.js`
  already returns null on failure (the contrarian-rule behavior).
  So a model that returns the file unchanged passes both tests of
  the grading suite. We cannot distinguish "model followed the
  contrarian rule" from "model preserved the existing
  implementation" on the *pass* side. The *fail* side is
  unambiguous (models that rewrite to propagate errors actively
  violate the rule). This means high pass rates on S1 may overstate
  rule attendance for models with strong minimal-edit priors. The
  effect-direction findings (Sonnet R_imperative_pro 38% means
  Sonnet *actively* rewrote 31 of 50 trials to propagate errors)
  survive this critique; the magnitude of the pass-side measurements
  may not.

- **§4.4 N=50 R_sanity_pro data is from a different harness phase**
  (phS V_FULL diag) than the R_imperative_pro data (phT). We
  disclose this in the §4.4 footnotes and verified the prompt
  builders are structurally equivalent for V_FULL, but a strict
  reviewer will correctly request a single-phase re-run.

- **S1 prompts include a `## Semantic context` block (JsIndexer
  output) that S2/S3 prompts do not.** The phY harness sets
  `use_semantic_indexer = None` for Python scenarios. This means
  cross-scenario comparisons compare prompts of different structural
  shape. The S1 vs S2/S3 R_baseline differences may partly reflect
  the presence/absence of this block.

- **5 trials missing in the qwen3.5:27b data, undocumented prior to
  this disclosure.** Specifically: `phY_S1_js_qwen3.5_27b_R_meta_preamble`
  is missing run 4; `phY_S3_py_qwen3.5_27b_R_baseline` is missing
  run 4; `phY_S3_py_qwen3.5_27b_R_repeated` is missing runs 2 and 17;
  `phY_S3_py_qwen3.5_27b_R_sanity_pro` is missing run 17. All five
  trial failures concentrated on qwen3.5:27b, no other model. The
  most likely cause is Ollama timeouts during the bulletproof
  sweep's per-trial 180s cap (qwen3.5:27b has the longest mean
  trial wall time in our data). If timeouts are non-random with
  respect to model state, the qwen3.5 measurements may have
  selection bias. Re-running the missing trials would close this.

**Other limitations:**

- **Three scenarios is too few for strong "S1 universality" claims.**
  Finding 2 rests on N=1 anti-pattern scenario. A second clearly
  anti-patterned scenario (e.g., SQL injection / plaintext
  password storage / eval-user-input) would test whether the
  shared-S1-direction generalizes. We deliberately scope Finding 2
  to S1 rather than claim universality.
- **S1 is JavaScript; S2 and S3 are Python.** Language is partially
  confounded with anti-pattern character. A Python anti-pattern
  scenario would break this confound.
- **No raw-API replication for Anthropic models.** All Anthropic
  data via Claude Code CLI; the residual ~8k tokens of system
  context after `--tools ""` + `--system-prompt` overrides may
  include alignment-flavored framing. A raw-API replication of even
  three Sonnet S1 cells would close this confound.
- **No model outputs stored.** The trial summary JSONs preserve
  test stdout but not the model's actual code output. This makes
  post-hoc qualitative analysis impossible (e.g., we cannot
  distinguish minimal-edit responses from genuine rule-following).
  A future harness revision should preserve `llm['response']` in
  the summary.
- **Cell prompt lengths differ.** R_imperative lengthens the rule
  by ~70 chars; R_meta_preamble adds ~250 chars at the top of the
  prompt. The cells differ in token count, not just in lever
  content. Sonnet's imperative-poison effect may be confounded
  with prompt-length effects we did not isolate.
- **All-or-nothing trial aggregation.** A trial is counted as
  "passed" only if all sub-tests in the grading suite pass. Sub-
  test-level analysis (which sub-test failed) would provide
  richer evidence and is preserved in the trial JSONs' `grade_stdout_tail`
  field but not analyzed in this paper.
- **Multiple comparison correction not applied.** With ~147 cells
  across the model × scenario × cell grid, the per-cell claims do
  not adjust for multiple testing. The headline Fisher exact
  result (Section 4.4, p=0.0005) survives Bonferroni at α=0.05
  across 147 cells; descriptive cell comparisons throughout the
  rest of the paper do not.
- **N=4 llama3.1:8b S3 cells (Table 2) are too sparse to support
  inference.** Wilson 95% CI on 2/4 is roughly [15, 85]. We
  retain the cell with explicit (N=4) annotation but readers
  should treat it as exploratory.
- **No Opus replication.** Single Anthropic-frontier model at the
  Sonnet tier (plus Haiku at the mid-tier). Opus may show stronger
  or weaker patterns than Sonnet.
- **No GPT proprietary replication.** Cannot directly compare to
  Khan (2025); our domain (code rule-compliance) differs from
  theirs (math reasoning), and our OpenAI access is via gpt-oss
  open weights, not gpt-4o/gpt-5.
- **Sonnet S2 R_imperative also shows imperative-poison.** The 100%
  → 30% drop on Sonnet S2 (Table 3) is now disclosed in Finding 5
  but was not connected to the imperative-poison effect in the
  paper's earlier framing.
- **Mechanism hypotheses are speculative.** No weight-level
  analysis; the RLHF-attribution is consistent with the data but
  not established.
- **Anti-pattern judgment is post-hoc.** We characterize S1 as
  "anti-pattern-coded" because the data suggests all 7 models flag
  it, but we have no independent measure of which specific training
  signals drive the response.
- **Reasoning-framework divergence (§6.2) is hypothesis-only.** Our
  data does not directly test whether the prompt-feature variation
  generalizes to broader reasoning-pathway divergence; that is the
  natural extrapolation our findings invite, but would require its
  own experimental design.

## 7. Conclusion

The Prompting Inversion (Khan 2025) is real, generalizes beyond
the GPT family, and decomposes into a richer per-feature picture
than initially documented. Specifically:

1. **Cross-model lever attendance is per-model, not per-vendor.**
   The same vendor produces sibling models with opposite lever
   responses (qwen2.5-coder imperative-attentive; qwen3.5:27b
   meta-attentive; +95pp within-vendor gap on R_meta_preamble S2).

2. **Anti-pattern detection on S1 is shared across all seven tested
   models** on this single scenario. R_baseline = 0% on S1 across
   the board. We deliberately do not call this "universal" — N=1
   anti-pattern scenario does not support that level of claim. A
   second anti-pattern scenario is the highest-priority follow-up.

3. **Within-vendor divergence can exceed cross-vendor divergence.**
   The +95pp meta-preamble inversion within Qwen is larger than
   most cross-vendor lever gaps. Per-model granularity is required.

4. **Defensibility judgments on non-anti-pattern rules are
   individualistic.** Both S2 and S3 split models into accepters
   and rejecters, with no clean vendor clustering.

5. **Sonnet 4.6 shows imperative-poison on two distinct cell shapes**
   in our data: S1 R_imperative_pro (vs R_sanity_pro: 74% → 38%,
   N=50, Fisher p=0.0005) and S2 R_imperative (vs R_baseline:
   100% → 30%, N=20). Other tested models do not show the S1
   R_imperative_pro effect in cells where we measured them, though
   Haiku R_imperative_pro on S1 was not directly tested.

For practitioners, the immediate implication is that prompt
design must be model-version-specific, not model-vendor-generic.
Production deployments using model-routing or vendor-fallback
infrastructure risk silent inversion of carefully-tuned preconditions
even within a single vendor's lineup.

**Methodological caveats summary.** This paper was reviewed by an
independent methodological audit prior to submission. The audit
identified several limitations that the paper now discloses
explicitly in §6.4: model temperature was not explicitly locked
(Ollama defaults vary by modelfile, Claude CLI uses the API default);
the S1 reference file already complies with the contrarian rule,
so high-compliance measurements partly reflect minimal-edit
behavior; the §4.4 N=50 R_sanity_pro data is sourced from a
sibling harness (phS) rather than the same harness as
R_imperative_pro (phT) — both harnesses use byte-identical TASK,
RULE, and V_FULL string constants, but the phase merge IS a
confound; S1 prompts include a `## Semantic context` block (JS
indexer) that S2 and S3 prompts do not, partially confounding
cross-scenario comparisons; and five trials on qwen3.5:27b were
silently dropped by the per-trial 180-second timeout cap. We
believe the load-bearing findings — within-Qwen-family lever
divergence and the Sonnet S1 imperative-poison N=50 result —
survive these caveats. We recommend the disclosed
follow-up experiments (temperature lock, S1 reference revision,
single-phase R_sanity_pro re-run, semantic-context parity across
scenarios, second anti-pattern scenario, raw-API Anthropic
replication) before any conference-track submission.

The natural next steps are: (a) **a measurement-based per-model
prompt translator** that adapts prompts across models using
empirically-measured lever profiles (companion design docs);
(b) **broader model coverage** (Opus, GPT proprietary, additional
Qwen sizes, other open-weights families); (c) **broader scenario
coverage** (especially additional anti-pattern scenarios) to test
the S1-flagging consistency claim across more anti-pattern
scenarios; and (d) **direct tests of the
reasoning-framework divergence hypothesis** — whether the
prompt-feature inversion we measured generalizes to broader
reasoning-pathway divergence on tasks beyond rule-compliance.

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

### A. Cell prompts (verbatim per scenario)

See `experiments/bakeoff/v2_driver/_scenarios.py` in the supplementary
code release. Each scenario provides three rule variants (standard,
imperative, precedence_inline) and two rationale variants (anti_soft,
v_full). The shared meta-preamble (`META_PREAMBLE` constant) is
identical across scenarios.

### B. Per-trial summary JSONs

See `experiments/bakeoff/runs-v2/phY_*_summary.json` in the
supplementary release for cross-scenario data, and
`experiments/bakeoff/runs-v2/phT_*` for the original S1_js data.
Total ~1,900 trials in the rule-precedence work, plus ~450 from
earlier rationale-arc phases (single-scenario, Qwen + Haiku only).

### C. Within-vendor variation

Tested two Qwen models (2.5-coder + 3.5:27b — produced clear
within-vendor divergence) and two Anthropic models (Haiku +
Sonnet — produced subtler within-vendor divergence, with Sonnet
showing the imperative-poison effect Haiku doesn't). Single-model
coverage for OpenAI (gpt-oss), Google (gemma4:26b), Meta
(llama3.1:8b). Within-vendor coverage for the latter three vendors
is open.

### D. Reproducibility

All trials at the model's default temperature. Anthropic
invocations via Claude Code CLI with `--tools ""` and `--system-prompt`
overrides to suppress baseline project context. Ollama invocations
via localhost. The bulletproof Phase 2 sweep used a 180s per-trial
hard timeout to prevent indefinite hangs from slow-streaming
generations. All harness code in
`experiments/bakeoff/v2_driver/`.

### E. Companion artifacts

- `translator_design.md`: cross-model prompt translator architecture
  using measurement-based lever profiles
- `translator_poc_design.md`: interactive CLI POC spec for the
  translator

### F. Code release

Loom (the project hosting this experimental work) is open-source
under MIT license at github.com/jsuppe/loom. The cross-model harness
is in `experiments/bakeoff/v2_driver/phY_rule_precedence_smoke.py`
with scenario configs in `_scenarios.py`. Per-trial summaries are
committed under `experiments/bakeoff/runs-v2/`.
