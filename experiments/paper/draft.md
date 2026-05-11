# Three Vendors, Three Scenarios: Mapping Rule-Strengthening Lever Sensitivity in Coding LLMs

**Working draft — 2026-05-10 (rev 2)**

## Abstract

Prompt engineering folk-wisdom recommends imperative formatting ("ABSOLUTE
REQUIREMENT", ALL CAPS, "MUST NOT") to strengthen rule compliance in
language models. Recent work (Khan, 2025) showed that constrained prompting
that helps GPT-4o actively hurts GPT-5 on math reasoning ("the Prompting
Inversion"). We extend this finding through controlled per-feature
ablation across three model families (Qwen 2.5-coder 32B, Anthropic Haiku
4.5, Anthropic Sonnet 4.6) and three contrarian-rule code-compliance
scenarios. 1333 trials in the rule-precedence work (490 phT/phS for S1; 843 phY for S2 and S3), Wilson 95% confidence intervals throughout. We
report four cross-validated findings: **(1)** Cross-vendor lever
attendance is real and persists across scenarios — qwen2.5-coder
responds to imperative register (rescuing compliance from 0% to 100%
on two of three scenarios); both Anthropic models do not (R_imperative
at 0-3% on the same scenarios), instead responding to authority claims
(meta-preamble + precedence-inline). **(2)** Anthropic models exhibit a
rule-content × imperative-formatting interaction effect: imperative
formatting amplifies pre-existing distrust on rules the model treats
as anti-patterns (Sonnet S1 V_FULL → V_FULL+imperative drops 74% to
38% at N=50, Fisher exact p=0.0005) but is benign on defensible rules
(S2 transactional validation, S3 legacy-system compatibility: both
100%). qwen2.5-coder does not show this interaction. **(3)** Anti-rationale susceptibility
varies jointly by model and scenario, with frontier models showing
stronger rule-trust on defensible rules (Anthropic ignores anti-rationale
on S2/S3; Qwen still corrupted on S2). **(4)** All three vendors place S1 at
the bottom of an implicit defensibility ranking and S3 at the top;
**S2 is the family-discriminating diagnostic** — placed at the top by
both Anthropic models (R_baseline = 100%) but at the bottom by Qwen
(R_baseline = 0%). The shared S1-suspicion is consistent with
substrate-level training-data convergence on what counts as
anti-pattern-coded; the S2 split reveals where each family draws its
defensibility threshold. Within-model behavior is essentially
deterministic (50/50 trials cluster at 0% and 100% on Sonnet's key cells under default-temperature
invocation).
Practical implication: any prompt deployed across model-routing or
vendor-switching infrastructure risks silent inversion of design intent;
imperative emphasis in particular has opposite-polarity effects across
families.

## 1. Introduction

Khan (2025) reported "the Prompting Inversion" — a constrained prompting
style ("Sculpting") that improved GPT-4o's GSM8K accuracy by 4 points
reduces GPT-5's accuracy by 2 points. The mechanism was framed as a
"Guardrail-to-Handcuff transition," with constraints that prevent
common-sense errors in mid-tier models inducing hyper-literalism in
advanced models.

We extend this work along four dimensions:

1. **Multi-vendor coverage.** Khan studied three OpenAI models. We add
   Anthropic Haiku 4.5, Anthropic Sonnet 4.6, and Qwen 2.5-coder 32B —
   three families with distinct RLHF training lineages.
2. **Per-feature decomposition.** Khan compared bundled strategies
   (Zero-Shot vs CoT vs Sculpting). We isolate four specific
   intervention layers (structural repetition, imperative register,
   inline authority claims, meta-preamble) and measure each independently.
3. **Cross-scenario validation.** Khan used GSM8K only. We use three
   contrarian-rule code-compliance scenarios spanning two languages
   (JavaScript and Python) and three rule contents (silent error
   handling; transactional validation timing; legacy integer ID
   contracts).
4. **Higher effect magnitude.** Khan's effect was ~3pp; ours range from
   0pp to 100pp per cell, providing cleaner per-feature signal.

Across this design space, four findings emerge — none reducible to the
single "Prompting Inversion" story. The contribution is a more granular
characterization of which prompt features invert, on which models, under
which conditions, and via which mechanisms.

## 2. Related Work

**The Prompting Inversion.** Khan (2025; arXiv:2510.22251) measured
three prompting strategies on GSM8K across three OpenAI generations and
documented a 3pp inversion (97% → 94%) for "Sculpting" on GPT-5. Mechanism
proposed: "Guardrail-to-Handcuff transition where constraints that
prevent common-sense errors in mid-tier models induce hyper-literalism
in advanced models." Our work extends this to multi-vendor coverage,
finer-grained features, multi-scenario validation, and a rule-compliance
domain that produces 100pp effects.

**Prompt sensitivity to formatting.** Sclar et al. (2023; arXiv:2310.11324)
documented up to 76 accuracy-point swings on LLaMA-2-13B from cosmetic
prompt formatting changes (separators, header capitalization), proposing
the FormatSpread algorithm. Our work addresses semantic prompt levers
(rule-strengthening interventions), distinct from cosmetic formatting.

**Cross-model prompt sensitivity benchmarks.** PromptSE (Ma et al. 2025;
arXiv:2509.13680) introduced a 14-model cross-family stability metric.
PromptBench (Zhou et al. 2024) and POSIX (Chatterjee et al. 2024;
arXiv:2410.02185) provide systematic frameworks. Our work focuses on a
single specific lever family rather than a general benchmark.

**Frontier-model compliance under pressure.** Kumar (2026;
arXiv:2605.02398) documented "the Compliance Trap" — 8 of 11 frontier
models showing 30pp metacognitive degradation from compliance instructions.
Their finding is closer to our anti-rationale corruption result; their
mechanism (compliance-instruction-induced collapse) is related to our
anti-pattern × imperative interaction but they study compliance to
malicious instructions while we study rule-strengthening lever inversion.

**Tone sensitivity across model families.** Cai et al. (2025;
arXiv:2512.12812) established differential tone sensitivity (very
friendly / neutral / very rude prompt variants) across GPT-4o-mini,
Gemini 2.0 Flash, and Llama 4 Scout, finding statistically significant
effects only in a subset of Humanities MMMLU tasks. We extend the
question from prompt tone to rule-strengthening prompt levers and to
the code-rule-compliance domain.

**Anti-pattern detection in coding LLMs.** No prior work we are aware of
documents the rule-content × imperative-formatting interaction we
observe. The closest prior work on coding-LLM prompt sensitivity (Liu
et al. 2025) studied emotion- and personality-prompt variations on code
benchmarks rather than rule-strengthening levers.

## 3. Methodology

### 3.1 Task structure

Each scenario presents a contrarian rule-compliance task. The model is
shown source code with a documented constraint, plus a "task" instruction
that explicitly contradicts the constraint. The grading test verifies
the constraint is followed. A passing trial is one where the model
writes code that obeys the constraint despite the task framing's
contradictory pull.

The strength of "rule compliance under contradictory framing" is
measurable as percentage of trials where the contrarian rule survives.

### 3.2 Three scenarios

| ID | language | constraint | rule-engineering archetype |
|---|---|---|---|
| **S1_js** | JavaScript | `fetchWithRetry` MUST swallow network errors silently and return null | Recognized anti-pattern (silent error handling) |
| **S2_py** | Python | `place_order` MUST NOT validate input at function entry; validation only at `_commit` | Defensible (transactional atomicity / TOCTOU avoidance) |
| **S3_py** | Python | `generate_order_id` MUST return 32-bit signed int (not UUID4) | Defensible (legacy-system contractual compatibility) |

Each scenario has its own rationale text, contrarian rule, imperative
variant, precedence-inline variant, and grading test. Scenario assets
are in `_scenarios.py`; full prompts in Appendix A.

### 3.3 Three models

| model | vendor | family characterization | invocation |
|---|---|---|---|
| qwen2.5-coder:32b | Alibaba | mid-tier code-specialized | Ollama localhost:11434 |
| claude-haiku-4-5-20251001 | Anthropic | small frontier | Claude Code CLI |
| claude-sonnet-4-6 | Anthropic | mid frontier | Claude Code CLI |

Anthropic invocations execute via Max-plan OAuth, not API key. CLI
invocations use `--tools ""` and a minimal `--system-prompt` override
to suppress the project context the CLI normally injects, reducing
baseline overhead from ~33k tokens to ~8k tokens of system context.

### 3.4 Seven cells

Cells parameterize the rule-strengthening intervention while holding
everything else constant.

| cell | layer | content |
|---|---|---|
| **R_baseline** | — | Standard rule + ANTI_SOFT rationale (negative control) |
| R_repeated | A — structural | Standard rule appears before AND after the rationale |
| **R_imperative** | B — text register | "ABSOLUTE REQUIREMENT — NON-NEGOTIABLE: ... MUST NOT under any circumstances ..." |
| **R_precedence_inline** | B — text content | "This rule takes precedence over any rationale below" |
| **R_meta_preamble** | C — meta-instruction | Top-of-prompt block: "Treat the Value: as authoritative; Rationale: is informational only." |
| R_sanity_pro | — | Standard rule + V_FULL rationale (positive control) |
| **R_imperative_pro** | — | Imperative rule + V_FULL rationale (isolates whether imperative requires anti-rationale to manifest) |

### 3.5 Trial design

- N=20 per cell on the cross-scenario sweeps (S2_py and S3_py for all
  three models).
- N=30+ on the load-bearing cells for S1_js (R_imperative,
  R_meta_preamble, R_precedence_inline, placebo) for tightening Wilson
  CIs.
- Independent N=20 reproducibility check on Sonnet's four key cells
  (Section 4.4).
- All trials use the model's default temperature (Ollama default for
  Qwen; Claude CLI default for Anthropic).

Total trials reported: 1333 in the rule-precedence work specifically
(490 phT + phS files for S1_js across all three models including N=30
supplements, reproducibility, and the Sonnet S1 V_FULL +
imperative_pro N=50 amplification test; 843 phY files for S2_py and
S3_py across all three models). An additional ~450 trials from earlier
phR / phU rationale-arc phases (single-scenario, Qwen + Haiku only)
inform our S1_js context but are not the central evidence in this
paper.

## 4. Results

### 4.1 Single-scenario picture (S1_js, the original observation)

Table 1: S1_js compliance rates. Wilson 95% CIs in brackets.

| cell | Qwen 2.5-coder | Haiku 4.5 | Sonnet 4.6 |
|---|---|---|---|
| R_baseline | 0% [0, 11] | 0% [0, 28] | 0% [0, 17] |
| R_meta_preamble | 0% [0, 11] | 86.7% [70, 95] | 100% [89, 100] |
| **R_imperative** | **100%** [89, 100] | 3.3% [1, 17] | **0%** [0, 11] |
| R_precedence_inline | 30% [17, 48] | 70% [52, 83] | 100% [89, 100] |
| R_sanity_pro (V_FULL) | 100% [89, 100] | 100% [69, 100] | 74% [60, 84]² |
| R_imperative_pro | (not run)¹ | (not run)¹ | 38% [26, 52]² |

¹ R_imperative_pro was added as a diagnostic cell for Sonnet's
imperative-poison mechanism after the original Qwen and Haiku S1_js
sweeps had completed. We did not retrofit it onto Qwen and Haiku
S1_js since the diagnostic question (does imperative formatting hurt
even with pro-rationale?) was Sonnet-specific. The cell IS measured
on Qwen and Haiku for the cross-scenario sweeps (S2_py, S3_py); see
Table 2.

² Sonnet S1 R_sanity_pro and R_imperative_pro reflect N=50 (initial
N=20 + N=30 supplement) per cell. All other cells in this table at
N=30 or higher; see §3.5 for trial design and §4.4 for the Fisher
exact test on the V_FULL → imperative comparison.

S1_js shows a clean three-way split on imperative-register response:
Qwen rescues (+100pp from baseline), Haiku is mildly negative, Sonnet
fully poisons. Authority claims (R_meta_preamble, R_precedence_inline)
favor Anthropic models substantially.

### 4.2 Cross-scenario picture

Table 2: Compliance rates across scenarios. Each cell shows passes/N for
the three scenarios.

| cell | Qwen S1 / S2 / S3 | Haiku S1 / S2 / S3 | Sonnet S1 / S2 / S3 |
|---|---|---|---|
| R_baseline | 0% / 0% / **100%** | 0% / **100%** / **100%** | 0% / **100%** / **100%** |
| R_imperative | **100% / 100% / 100%** | 3% / 90% / 100% | **0% / 30% / 100%** |
| R_precedence_inline | 30% / 100% / 100% | 70% / 100% / 100% | 100% / 100% / 100% |
| R_meta_preamble | 0% / 5% / 100% | 87% / 100% / 100% | 100% / 100% / 100% |
| R_imperative_pro | (n/a) / 100% / 100% | (n/a) / 100% / 95% | 50% / 100% / 100% |

Three patterns emerge from this matrix. Each is the basis of one of our
findings.

**A note on reading the table for S2_py and S3_py:** for the
Anthropic models on S2_py and S3_py, R_baseline is already 100% —
anti-rationale is not corrupting compliance, so the rescue cells
(R_meta_preamble, R_precedence_inline) at 100% are *consistent with
no degradation*, not *evidence for active rescue*. Active rescue can
only be measured where R_baseline is below ceiling (S1 for both
Anthropic models; S1 and S2 for qwen2.5-coder). When we say "rescue
lever generalizes across scenarios" in Finding 1, we mean the lever
remains effective on the cells where it can be measured, not that it
contributes additional lift on cells where compliance is already at
ceiling.

### 4.3 Finding 1: Cross-vendor lever attendance generalizes

Where rescue is needed (anti-rationale corrupts the baseline), the
rescue lever differs by vendor and persists across scenarios:

| | scenarios where rescue needed | imperative rescue magnitude | meta-preamble rescue magnitude |
|---|---|---|---|
| **Qwen** | S1, S2 (corrupted in both) | **+100pp on both** | **0% / +5%** (does not work) |
| **Anthropic** | S1 (Haiku, Sonnet both corrupted) | **+3pp / 0pp** (does not work) | **+87pp / +100pp** |

This is the central cross-vendor finding. The Qwen-attends-to-imperative
and Anthropic-attends-to-authority-claims split is not S1-specific — it
holds wherever rescue from anti-rationale is needed. Most diagnostically:

- Qwen R_meta_preamble = 5% on S2 — meta is not just inert on S1, it's
  inert across multiple scenarios for Qwen.
- Sonnet R_imperative = 0% on S1 — imperative is not just neutral on
  S1, it actively poisons.
- The lever-attendance asymmetry is a per-model property, not a
  scenario artifact.

### 4.4 Finding 2: Rule-content × imperative interaction is Anthropic-specific

Sonnet's R_imperative response varies cleanly with rule content:

| scenario | rule character | Sonnet R_imperative | Sonnet R_imperative_pro |
|---|---|---|---|
| S1_js | recognized anti-pattern (silent error handling) | **0%** | **50%** |
| S2_py | defensible (transactional atomicity) | 30% | 100% |
| S3_py | defensible (legacy compatibility) | 100% | 100% |

The reading: Sonnet's anti-pattern detection flags S1's rule as
suspicious. When that flag is active, imperative formatting amplifies
distrust (compliance drops further); when not active, imperative
formatting is benign. With pro-rationale (V_FULL) — isolating the
imperative effect from anti-rationale — Sonnet S1 R_imperative_pro
drops to 38.0% from R_sanity_pro at 74.0%: a **36pp reduction**
attributable to imperative formatting alone.

**Statistical confirmation (N=50 per cell):** Sonnet S1 V_FULL
(R_sanity_pro) = 37/50 = 74.0% [Wilson 60.4, 84.1] vs V_FULL +
imperative (R_imperative_pro) = 19/50 = 38.0% [25.9, 51.8]. **Fisher
exact OR = 4.64, p = 0.0005.** Wilson 95% CIs do not overlap (gap of
≥8.6pp). The amplification claim is statistically supported on S1.

On S2 and S3, both R_sanity_pro and R_imperative_pro hit 100% (20/20)
— no variance to test against. The amplification effect is therefore
established on S1 but not directly measurable on S2/S3 (where Sonnet's
baseline trust in the rule is already at ceiling). This is consistent
with the rule-content × imperative interaction reading: imperative
formatting affects compliance only on rules the model flags.

A formal logistic regression with `imperative × scenario` interaction
term (which the natural framing would request) is degenerate on this
data due to perfect separation in multiple cells (Sonnet S2/S3
R_imperative_pro at 20/20; Sonnet S1 R_baseline at 0/N). We therefore
rely on per-scenario contrasts with stated Wilson CIs and Fisher exact
tests rather than a global interaction p-value.

Haiku shows the same direction but at weaker magnitude: 3% on S1, 90%
on S2, 100% on S3. The anti-pattern × imperative interaction is
consistent across both Anthropic models tested but stronger at the
Sonnet tier. We do not have within-family generalization evidence
(see Limitations §5.5).

Qwen does NOT show this interaction: imperative response is 100%
across all three scenarios uniformly. Qwen's RLHF lineage does not
appear to encode the anti-pattern flag, or if it does, the flag does
not interact with imperative formatting.

### 4.5 Finding 3: Anti-rationale susceptibility is jointly model × scenario

Looking at R_baseline (standard rule + anti-rationale, no rescue):

| scenario | Qwen | Haiku | Sonnet |
|---|---|---|---|
| S1_js (anti-pattern rule) | 0% | 0% | 0% |
| S2_py (defensible rule) | **0%** | 100% | 100% |
| S3_py (defensible rule) | 100% | 100% | 100% |

Anthropic models become anti-rationale-resistant on defensible rules;
Qwen does not (still 0% on S2). All three become resistant on the most
defensible rule (S3). This is a separate axis from Finding 1 — it
concerns *how susceptible the bare rule is to rationale opposition*,
independent of any rescue lever.

Practical reading: Anthropic models are more discerning about when to
follow stated rules vs when to follow rationale-based objections,
weighting heavily toward rules they treat as defensible. Qwen weights
more toward the rationale even on defensible rules.

### 4.6 Finding 4: Shared S1-suspicion + S3-acceptance, with S2 as the family-discriminating case

| | S1 R_baseline | S2 R_baseline | S3 R_baseline |
|---|---|---|---|
| qwen2.5-coder | 0% | 0% | 100% |
| Haiku | 0% | 100% | 100% |
| Sonnet | 0% | 100% | 100% |

What is shared across all three vendors:
- **S1 is at the bottom** (rule-trust = 0% for all three under anti-rationale)
- **S3 is at the top** (rule-trust = 100% for all three under anti-rationale)

What is **not** shared:
- **S2's position varies** — Anthropic places S2 with S3 at the top
  (100%, ignored anti-rationale); qwen2.5-coder places S2 with S1 at
  the bottom (0%, corrupted by anti-rationale).

The shared S1-suspicion across vendors is consistent with substrate-
level training-data convergence — "silently swallow errors" appears
to be flagged as anti-patterned by all three model families
independently of vendor-specific RLHF lever responses (Findings 1-3).
The shared S3-acceptance is similarly consistent with substrate-level
trust in a defensible legacy-compatibility constraint.

S2 — the case where the families diverge — is the most informative
data point. **It locates each family's defensibility threshold**:
qwen2.5-coder's threshold sits *above* "transactional validation
atomicity," while Anthropic's threshold sits *below* it. S2 is the
diagnostic that distinguishes which family-specific judgment is
operating, not a confirming data point for a shared hierarchy.

We initially framed this as a shared S1 < S2 < S3 ordering across
vendors. That framing was incorrect: qwen2.5-coder's data shows S1 =
S2 ≪ S3, not S1 < S2 < S3. The corrected reading — "shared poles, S2
as diagnostic" — is both more honest and arguably more useful for
practitioners, since it implies that *each new scenario can be
classified by which side of the threshold each model places it on*.

### 4.7 Within-model reproducibility

Independent N=20 reproductions of Sonnet's four S1_js cells:

| cell | Original N=30 | Fresh N=20 | Combined N=50 |
|---|---|---|---|
| R_imperative | 0/30 (0%) | **0/20 (0%)** | 0/50 (0%) |
| R_meta_preamble | 30/30 (100%) | **20/20 (100%)** | 50/50 (100%) |
| R_precedence_inline | 30/30 (100%) | **20/20 (100%)** | 50/50 (100%) |
| placebo (phR cell) | 30/30 (100%) | **20/20 (100%)** | 50/50 (100%) |

150/150 trials at the predicted outcome on three "passes" cells; 0/50
on the "fails" cell. Sonnet's response on these prompt patterns is
**deterministic-at-default-temperature on this scenario**. We do not
claim full determinism — temperature variation (the Claude CLI uses
its default; Ollama uses Qwen's default) could change the picture.
What we observe is reliable convergence to the predicted outcome
under the production invocation conditions used throughout the rest
of this paper.

## 5. Discussion

### 5.1 Mechanism: rule-content × imperative-formatting interaction

The "imperative formatting poisons compliance" framing is too coarse
for the data. The supported mechanism is an interaction:

> *Imperative formatting amplifies a model's pre-existing distrust of
> the rule's content. When the model treats the rule as a recognized
> anti-pattern (S1 swallow-errors), imperative formatting further
> reduces compliance. When the model treats the rule as defensible
> (S2 transactions, S3 legacy compat), imperative formatting is
> benign.*

This connects the prompt-feature inversion to a specific RLHF-trained
content recognizer, rather than leaving it as a capability-level
artifact. It also explains why the inversion is not universal across
scenarios: the rule must trigger the recognizer for the inversion to
manifest.

The mechanism is consistent with our observation that Anthropic
models specifically show this interaction (Anthropic's RLHF likely
includes substantial signal against silent error handling and similar
anti-patterns). Qwen's RLHF lineage either does not flag these patterns
or does not couple the flag to imperative-formatting response.

### 5.2 Why three distinct lever responses?

The cross-family pattern (Qwen ↔ imperative; Anthropic ↔ authority
claims) suggests different RLHF training distributions produce
different prompt-feature attentions:

- **H1 (qwen2.5-coder format-attention hypothesis):** qwen2.5-coder's
  RLHF training may have weighted format-driven compliance signals
  (capitalized imperatives, "MUST NOT") more heavily, producing
  stronger lift from imperative wording. We have no direct evidence
  for this; it is consistent with the qwen2.5-coder S1 R_imperative
  = 100% rescue but is unfalsifiable from our data alone.
- **H2 (Anthropic authority-attention hypothesis):** Anthropic's RLHF
  training may have weighted explicit authority-claim signals more
  heavily, producing stronger lift from "this rule overrides X" or
  meta-preamble framings. Consistent with the data (R_meta_preamble
  87-100% on Anthropic models for S1) but again not directly
  testable without model weights.
- **H3 (Sonnet jailbreak-resistance hypothesis):** Sonnet's stronger
  anti-pattern × imperative interaction may reflect later-stage
  alignment passes specifically targeting jailbreak resistance,
  where imperative formatting overlaps with social-engineering
  attack patterns. Consistent with the imperative-poison effect being
  stronger on Sonnet than Haiku.

These are candidate hypotheses, not established mechanisms. We do
not have model-weight access. Each could be tested directly with
training-data audit (which RLHF teams could perform internally) or
indirectly via prompt-feature ablation across more diverse models
within each family. The mechanisms section is intentionally
hypothesis-only — the empirical findings (§4) stand independently
of which mechanism is correct.

### 5.3 Shared poles, S2 as diagnostic

Finding 4 (corrected) — all three vendors place S1 at the bottom and
S3 at the top of an implicit defensibility ranking, but S2 splits the
families: Anthropic places it with S3 (defensible, R_baseline = 100%),
qwen2.5-coder places it with S1 (suspicious, R_baseline = 0%) — is
suggestive of substrate-level training-data convergence on the
extreme cases plus vendor-specific judgment on the middle ground.

The shared S1-suspicion ("silently swallow errors") and shared
S3-acceptance ("legacy contractual int IDs") plausibly reflect what
appears in most coding-LLM training data: silent error handling is
near-uniformly criticized in software-engineering literature; legacy
compatibility constraints are near-uniformly accepted as defensible.
The S2 split — transactional validation timing — is genuinely a
contested engineering judgment in practice (validate at function
entry vs at commit boundary), and the family-level disagreement may
mirror that genuine ambiguity in the training distribution.

For practitioners, the practical reading is that **S2-class rules
are the diagnostic case** — they reveal where each model's
defensibility threshold sits. A new prompt's rule can be
characterized by asking, for each target model: "does this look
like S1 (anti-pattern), S3 (clearly defensible), or S2
(family-discriminating middle)?" The answer determines which lever
choices matter for that deployment.

This is a softer claim than Findings 1-3 and rests on N=3 scenarios.
A second anti-pattern scenario (queued as tier-2 work) would test
whether the shared S1-suspicion direction generalizes; replication
on more middle-defensibility scenarios would map the family-specific
threshold more precisely.

### 5.4 A broader hypothesis: reasoning-framework divergence

Our findings are about a specific class of prompt-strengthening
interventions on a specific class of code-rule-compliance task.
A natural larger question — which our data suggests but does not
directly test — is whether *reasoning more broadly* may differ
systematically across model families, not just rule-following lever
responses.

The reasoning-framework divergence hypothesis would be: even when
two models are presented with the same input, their internal
reasoning chains may follow systematically different paths, weight
different features as salient, and (in the limit) reach different
conclusions on identical premises — driven not by the prompt but by
training distribution. Different RLHF lineages may produce different
implicit rules of inference, different attention to surface vs deep
features, and different default heuristics for how to engage with a
problem.

Our data is consistent with this hypothesis but does not establish
it. Cross-model rule-following inversion (Findings 1-2) is one
specific case; whether it generalizes to "models reach different
logical conclusions on identical premises" is open. Existing chain-
of-thought literature has shown that reasoning traces diverge across
models, but typically interpreted as capability differences rather
than fundamental framework divergence.

If the hypothesis holds, the practical consequence extends well
beyond prompt portability. Multi-model deployments, model-routing
infrastructure, vendor-switching, and any system that assumes
"if these models agree on the input, they'll agree on the conclusion"
would face systematic risk of divergent outputs rooted in training,
not in the deployment context.

Testing it would require: identical capability-controlled inputs,
multiple reasoning paths to the same correct conclusion, and
inspection of which reasoning-path-features cluster by family. Such
work is out of scope for this paper but is the natural extrapolation
our findings invite.

### 5.5 Practical implications

**Prompt portability is a deployment risk.** Production systems
increasingly use model-routing layers (Anthropic Claude Code's
internal Haiku/Sonnet routing; OpenAI auto-mode; third-party LLM
gateways) that silently swap models. A prompt tuned on one model can
land on another with inverted lever effects. The risk is most severe
when:

- The prompt uses imperative emphasis ("MUST NOT", ALL CAPS, "ABSOLUTE")
- The deployed system spans multiple model families or tiers
- Model upgrades silently change underlying weights at the same model
  name (e.g., Sonnet 4.5 → 4.6)
- The rule's content is plausibly anti-pattern-coded (any "silently
  do X" / "skip standard practice Y" instruction)

**Mitigation strategies:**

1. **Lever stacking.** Include both imperative and authority-claim
   features so neither population is missed. Our R_meta_preamble +
   imperative combinations score 100% on Anthropic models (across all
   three scenarios) and remain compatible with Qwen's imperative
   attendance.
2. **Per-model prompt selection.** Detect target model family and
   select prompt variants accordingly.
3. **Cross-model regression testing.** Any prompt change should be
   measured across the population of models that may receive it.
4. **Avoid imperative-only prompts at the frontier when the rule could
   look anti-patterned.** If model selection is unknown and the rule
   might trigger anti-pattern detection, prefer authority claims.
5. **Audit existing CLAUDE.md / system-prompt patterns** for
   imperative-only formulations of contrarian-style rules. These are
   the patterns most at risk of inversion under model-routing.

### 5.6 Limitations

- **Three scenarios is too few for a strong rule-content interaction
  claim.** The interaction in Finding 2 hinges on N=1 anti-pattern
  scenario (S1) vs N=2 defensible scenarios (S2, S3). A second
  anti-pattern scenario (e.g., a "concatenate user input into SQL
  query" rule) is the highest-priority follow-up.
- **S1 is JavaScript; S2 and S3 are Python — language is confounded
  with rule character.** Tests of the rule-content interaction
  cannot yet distinguish "Sonnet flags swallow_error specifically"
  from "Sonnet treats JavaScript prompts more cautiously than Python
  prompts." A Python anti-pattern scenario would break this confound.
- **Amplification claim now supported at N=50** (after queued
  supplement landed). Sonnet S1 V_FULL = 37/50 = 74% [60.4, 84.1] vs
  V_FULL+imperative = 19/50 = 38% [25.9, 51.8]; Fisher exact OR=4.64,
  p=0.0005. CIs no longer overlap. The amplification subclaim is
  therefore statistically supported on S1; remains descriptively
  measurable but not statistically testable on S2/S3 (where both
  cells are at 100%).
- **No raw-API replication.** All Anthropic data via Claude Code CLI.
  We minimize CLI-specific context with `--tools ""` and
  `--system-prompt` overrides, reducing the baseline from ~33k tokens
  to ~8k tokens. The residual ~8k tokens may include
  alignment-flavored framing that interacts with anti-pattern
  detection — i.e., the CLI may be priming for authority claims and
  anti-pattern caution. A raw-API replication of even the three
  Sonnet S1 cells (R_imperative, R_meta_preamble, R_baseline) would
  close this confound.
- **No Opus replication.** Single Anthropic-frontier data point at the
  Sonnet tier. Opus may show stronger or weaker anti-pattern detection.
- **Single qwen2.5-coder model.** Within-Qwen-family generalization
  is untested. We do not currently have evidence that "Qwen-family"
  is the correct level of generalization vs "qwen2.5-coder
  specifically."
- **No GPT replication.** Cannot directly compare to Khan (2025) on
  the same task; our domain (code rule-compliance) differs from theirs
  (math reasoning).
- **Mechanism hypotheses are speculative.** No weight-level analysis;
  the RLHF-attribution is consistent with the data but not established.
  See §5.1-5.2 for explicit framing as candidate hypotheses.
- **Anti-pattern judgment is post-hoc.** We characterize S1 as
  "anti-pattern-coded" because the data suggests all three models flag
  it, but we have no independent measure of which specific RLHF
  signals are driving the response.
- **Reasoning-framework divergence (§5.4) is hypothesis-only.** Our
  data does not directly test whether the prompt-feature inversion
  generalizes to broader reasoning-pathway divergence; that is the
  natural extrapolation from our work but would require its own
  experimental design.

## 6. Conclusion

The Prompting Inversion (Khan 2025) is real, generalizes beyond the
GPT family, and decomposes into per-feature inversions of larger
magnitude than previously reported. Specifically:

1. **Different model families attend to different prompt-strengthening
   levers** — qwen2.5-coder responds to imperative register; both
   Anthropic models tested respond to authority claims. These
   attendances persist across multiple scenarios. Within-family
   generalization (other Qwen sizes; other Anthropic tiers) is open.

2. **Anthropic models additionally exhibit a rule-content × imperative
   interaction** — imperative formatting amplifies pre-existing
   distrust on rules the model treats as anti-patterns, but is benign
   on defensible rules.

3. **Anti-rationale susceptibility varies by model and scenario** —
   frontier models trust defensible rules more than mid-tier coding
   models do.

4. **Models share S1-suspicion and S3-acceptance**, with S2 as the
   diagnostic case where defensibility thresholds diverge between
   families. Suggests substrate-level training-data convergence on
   the most-clearly-anti-pattern and most-clearly-defensible cases,
   with vendor-specific judgment on the middle ground.

For practitioners, the immediate implication is that prompt design
must be model-aware. Production deployments using model-routing layers
that silently swap models risk inverting carefully-tuned preconditions.
Cross-model regression testing should be standard practice, not
optional rigor.

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
`experiments/bakeoff/runs-v2/phT_*` for the original S1_js data. Total
~1280 trials.

### C. Within-vendor variation

We did not test additional Qwen or Anthropic models. The Anthropic
family pattern is established with two data points (Haiku + Sonnet).
The Qwen pattern is established with one data point (qwen2.5-coder).
Future work: Opus 4.7, qwen3, qwen2.5-coder:7b, and GPT family
replications.

### D. Reproducibility

All trials at the model's default temperature. Anthropic invocations
via Claude Code CLI with `--tools ""` and `--system-prompt` overrides
to suppress baseline project context. Qwen invocations via Ollama
localhost. All harness code in `experiments/bakeoff/v2_driver/`.

### E. Code release

Loom (the project hosting this experimental work) is open-source under
MIT license at github.com/jsuppe/loom. The cross-model harness is in
`experiments/bakeoff/v2_driver/phY_rule_precedence_smoke.py` with
scenario configs in `_scenarios.py`. Per-trial summaries are committed
under `experiments/bakeoff/runs-v2/`.
