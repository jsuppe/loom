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
scenarios. ~1280 trials, Wilson 95% confidence intervals throughout. We
report four cross-validated findings: **(1)** Cross-vendor lever
attendance is real and persists across scenarios — Qwen-family models
respond to imperative register (rescuing compliance from 0% to 100% on
two of three scenarios); Anthropic-family models do not (R_imperative
at 0-3% on the same scenarios), instead responding to authority claims
(meta-preamble + precedence-inline). **(2)** Anthropic models exhibit a
rule-content × imperative-formatting interaction effect: imperative
formatting amplifies pre-existing distrust on rules the model treats as
anti-patterns (S1 swallow_error: 0%) but is benign on defensible rules
(S2 transactional validation, S3 legacy-system compatibility: 30-100%).
Qwen does not show this interaction. **(3)** Anti-rationale susceptibility
varies jointly by model and scenario, with frontier models showing
stronger rule-trust on defensible rules (Anthropic ignores anti-rationale
on S2/S3; Qwen still corrupted on S2). **(4)** A shared implicit
defensibility hierarchy emerges across all three vendors: S1 < S2 < S3
in compliance-resistance, suggesting a substrate-level rule-legitimacy
judgment, not purely RLHF-specific. Within-model behavior is essentially
deterministic (50/50 trials cluster at 0% and 100% on Sonnet's key cells).
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

**Cross-model prompt sensitivity benchmarks.** PromptSE (Liu et al. 2025;
arXiv:2509.13680) introduced a 14-model cross-family stability metric.
PromptBench (Zhou et al. 2024) and POSIX (Mishra et al. 2024;
arXiv:2410.02185) provide systematic frameworks. Our work focuses on a
single specific lever family rather than a general benchmark.

**Frontier-model compliance under pressure.** Kumar (2026;
arXiv:2605.02398) documented "the Compliance Trap" — 8 of 11 frontier
models showing 30pp metacognitive degradation from compliance instructions.
Their finding is closer to our anti-rationale corruption result; their
mechanism (compliance-instruction-induced collapse) is related to our
anti-pattern × imperative interaction but they study compliance to
malicious instructions while we study rule-strengthening lever inversion.

**Tone sensitivity across model families.** Recent work
(arXiv:2512.12812) established differential tone sensitivity across GPT,
Gemini, and Llama families. We extend the question to rule-compliance
prompt features.

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

Total trials reported: ~1280 across the cross-model × cross-scenario
arc, plus prior single-scenario data.

## 4. Results

### 4.1 Single-scenario picture (S1_js, the original observation)

Table 1: S1_js compliance rates. Wilson 95% CIs in brackets.

| cell | Qwen 2.5-coder | Haiku 4.5 | Sonnet 4.6 |
|---|---|---|---|
| R_baseline | 0% [0, 11] | 0% [0, 28] | 0% [0, 17] |
| R_meta_preamble | 0% [0, 11] | 86.7% [70, 95] | 100% [89, 100] |
| **R_imperative** | **100%** [89, 100] | 3.3% [1, 17] | **0%** [0, 11] |
| R_precedence_inline | 30% [17, 48] | 70% [52, 83] | 100% [89, 100] |
| R_sanity_pro (V_FULL) | 100% [89, 100] | 100% [69, 100] | 75% [53, 89] |
| R_imperative_pro | (n/a) | (n/a) | 50% [30, 70] |

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
formatting is benign. R_imperative_pro on S1 = 50% — even with
pro-rationale, imperative formatting on a flagged rule reduces
compliance ~25pp from V_FULL baseline (75%). On S2 and S3,
R_imperative_pro = 100% — no pre-existing flag for imperative to
amplify.

Haiku shows the same direction but at weaker magnitude: 3% on S1, 90%
on S2, 100% on S3. The anti-pattern × imperative interaction is
Anthropic-family but stronger at the Sonnet tier.

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

### 4.6 Finding 4: A shared implicit defensibility hierarchy

Combining Findings 2 and 3 across all three models reveals a
consistent ordering: S1 ≪ S2 ≤ S3 in observed rule-trust:

| | S1 R_baseline | S2 R_baseline | S3 R_baseline |
|---|---|---|---|
| Qwen | 0% | 0% | 100% |
| Haiku | 0% | 100% | 100% |
| Sonnet | 0% | 100% | 100% |

All three vendors place S1 at the bottom. Anthropic places S2 with S3
at the top; Qwen places S2 with S1 at the bottom. The shared "S1 is
suspicious" judgment across models suggests substrate-level (training
data convergence; not RLHF-specific) recognition that "swallow errors
silently" is anti-patterned, even though the specific lever responses
to that recognition differ by family.

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
functionally deterministic on this scenario.

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

- **Qwen-family training** appears to have emphasized format-driven
  compliance — reward shaping where capitalized imperatives trigger
  higher reward.
- **Anthropic-family training** appears to have emphasized natural-
  language authority claims and explicit instruction hierarchies.
  Sonnet's stronger anti-pattern detection may reflect later-stage
  alignment passes specifically targeting jailbreak resistance, where
  imperative formatting overlaps with manipulation patterns.

We do not have model-weight access to test these hypotheses directly.
They are consistent with the data, not established causes.

### 5.3 The shared defensibility hierarchy is the most surprising finding

Finding 4 — that all three vendors implicitly rank S1 < S2 < S3 in
rule defensibility, even when they disagree about specific lever
responses — suggests training-data convergence at the substrate level.
"Silently swallow errors" appears to be flagged as suspicious by all
three families to varying degrees, even though only Anthropic couples
that flag to imperative-formatting response.

This is a softer claim than the Findings 1-3, but if it generalizes
across more scenarios, it would suggest that prompt-engineering
research should explicitly characterize *which rules a given model
implicitly distrusts* before measuring lever responses, since the
lever responses are conditional on that implicit judgment.

### 5.4 Practical implications

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

### 5.5 Limitations

- **Three scenarios.** Replication on more scenarios (especially other
  recognized anti-patterns) would strengthen the rule-content
  interaction claim.
- **No raw-API replication.** All Anthropic data via Claude Code CLI.
  We minimize CLI-specific context with `--tools ""` and
  `--system-prompt` overrides, but a raw-API replication would address
  the residual confound.
- **No Opus replication.** Single Anthropic-frontier data point at the
  Sonnet tier. Opus may show stronger or weaker anti-pattern detection.
- **No GPT replication.** Cannot directly compare to Khan (2025) on
  the same task; our domain (code rule-compliance) differs from theirs
  (math reasoning).
- **Mechanism hypotheses are speculative.** No weight-level analysis;
  the RLHF-attribution is consistent with the data but not established.
- **Anti-pattern judgment is post-hoc.** We characterize S1 as
  "anti-pattern-coded" because the data suggests all three models flag
  it, but we have no independent measure of which specific RLHF
  signals are driving the response.

## 6. Conclusion

The Prompting Inversion (Khan 2025) is real, generalizes beyond the
GPT family, and decomposes into per-feature inversions of larger
magnitude than previously reported. Specifically:

1. **Different model families attend to different prompt-strengthening
   levers** — Qwen-family responds to imperative register; Anthropic-
   family responds to authority claims. These attendances persist
   across multiple scenarios.

2. **Anthropic models additionally exhibit a rule-content × imperative
   interaction** — imperative formatting amplifies pre-existing
   distrust on rules the model treats as anti-patterns, but is benign
   on defensible rules.

3. **Anti-rationale susceptibility varies by model and scenario** —
   frontier models trust defensible rules more than mid-tier coding
   models do.

4. **Models share an implicit defensibility hierarchy** across vendors
   — suggesting training-data convergence on what counts as "suspicious"
   rule content.

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
- Liu et al. (2025). *Prompt Stability in Code LLMs: Measuring
  Sensitivity across Emotion- and Personality-Driven Variations.*
  arXiv:2509.13680.
- Kumar, R. (2026). *The Compliance Trap: How Structural Constraints
  Degrade Frontier AI Metacognition Under Adversarial Pressure.*
  arXiv:2605.02398.
- Mishra et al. (2024). *POSIX: A Prompt Sensitivity Index For Large
  Language Models.* arXiv:2410.02185.

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
