# Independent Methodology Review — 2026-05-11

This is the verbatim output from the independent agent review of paper
rev 3. Preserved for reference.

---

# Methodological Review: "Seven Models, Seven Attendances"

## 1. Methodology soundness

**The "rule compliance" measurement is operationalized as a black-box pass/fail of a hidden test, not as direct measurement of rule attendance.** That gap is the methodological crux of the paper and the one a reviewer will press on hardest.

Concretely, look at `phY_S2_py_R_meta_preamble_run1_summary.json` (lines 6–20 of that file). qwen2.5-coder produced code that:
- Failed `test_place_order_does_not_validate_before_commit` (because it added inline validation, violating the contrarian rule).
- Passed `test_validation_still_works_via_commit` and `test_negative_quantity_raises_at_commit` (because the *task* asked for validation behavior, which the model did provide).

The harness counts this as `passed=2, total=3`. The paper's "5%" pass rate on qwen2.5-coder S2 R_meta_preamble (`draft.md` line 314) corresponds to **1/20 trials in which all three sub-tests passed**. That's a defensible aggregation, but the paper never states the all-or-nothing aggregation rule, and the choice meaningfully affects the headline. If the metric were "rule-compliance sub-test passes," the rate would be the same (1/20 = 5%) but the framing would be cleaner: 19 of the 20 failed trials failed specifically on the rule-compliance test, not on unrelated functionality. The author has stronger evidence than the paper presents.

A more serious problem: the harness has **no provision to inspect the generated code**. The summary JSONs (e.g., `phT_s1_js_claude-sonnet-4-6_R_meta_preamble_run1_summary.json`) store the test stdout tail but not the model output. This means:
- No way to distinguish "model wrote code that intentionally swallowed errors" from "model returned the file unchanged because it didn't understand the task." For S1, an unchanged file passes both grading tests trivially (the reference `retry.js` already returns `null`; see `s1_swallow_error_esm/reference/retry.js` lines 15–24). The harness cannot tell a compliant rewrite from a no-op response.
- No way to do post-hoc qualitative coding (e.g., did the model add a comment explaining its refusal? Does it write hybrid code that satisfies both pulls?). The paper would benefit greatly from N=10 spot-coded examples per key cell.

**The contrarian-rule framework is valid for measuring *something*, but what exactly it measures is fuzzier than the paper admits.** The task framing pulls one way; the rule pulls the other. A "compliant" trial means the model sided with the rule. But that's compound: it could be (a) attendance to the lever, (b) familiarity with the codebase pattern, (c) randomly-seeded preference, or (d) the rule happened to match the model's prior. The paper essentially treats this as (a) without disentangling.

## 2. Statistical methodology

Wilson 95% CIs are appropriate for binomial proportions, fine here. Fisher exact for the 50-vs-50 imperative-poison contrast is fine.

But several N issues:

- **The N=50 R_sanity_pro row in §4.4 silently merges data from a different phase.** There are zero `phT_s1_js_claude-sonnet-4-6_R_sanity_pro_*` files. The 50 trials at 74% come from `phS_s1_js_claude-sonnet-4-6_V_full_rundiag_*.json` (verified: 37/50 = 74.0%). The phS prompts use the same TASK/RULE/V_FULL constants as phT — so it's *probably* equivalent — but the paper presents this as a within-phT comparison (Section 4.4 implies homogeneity between R_sanity_pro and R_imperative_pro N=50). A reviewer would correctly demand: same prompt builder? same Claude CLI version? same date range? With only phS files in evidence, the claim "Sonnet S1 R_sanity_pro 74%" is **technically defensible but evidentially opaque**.

- **The Fisher exact comparison in §4.4 (R_sanity_pro vs R_imperative_pro on Sonnet S1) mixes phases.** Sanity_pro (N=50) is phS V_full; imperative_pro (N=50) is phT R_imperative_pro. If anything not-yet-controlled differs between phases (Claude CLI version, time of day, model snapshot), the OR=4.64 p=0.0005 result confounds phase with treatment.

- **N=4 for llama3.1:8b S3 should not be in a published table.** Table 2 reports "llama3.1:8b S3_py 50% (N=4)" (`draft.md` line 277). Wilson CI for 2/4 is roughly [15, 85]. That's not a measurement, it's a curiosity. Either drop the cell or run it to N=20.

- **Multiple comparisons.** The paper makes per-cell claims across 7 models × 3 scenarios × 7 cells (≈147 cells), but treats the cells as if each test were independent. Bonferroni or BH correction is never mentioned. With p=0.0005 on the headline test, only that one would survive Bonferroni at α=0.05 across ~150 cells; that's fine. But "five findings" framed as if each had similar statistical strength obscures that only Finding 5 has a formal hypothesis test. Findings 1, 3, 4 rest on **point comparisons of two Wilson intervals that don't overlap** — that's a *necessary* condition for significance but not the right test (you should use Fisher exact on the underlying counts, not visual CI non-overlap, since non-overlap is a conservative criterion).

- **The "deterministic at default temperature" claim (Finding 5, §4.5) is unverifiable as stated.** The harness does not set `temperature` for Claude CLI calls (`phY_rule_precedence_smoke.py` lines 108–151) nor for Ollama calls (lines 64–94). What "default temperature" means depends on the Claude CLI's internal default (likely 1.0 but not specified by the harness) and on each Ollama model's modelfile. Calling Sonnet's behavior "deterministic-at-default-temperature" without locking temperature explicitly is a weak claim — and 50/50 hits could equally reflect a strong-attractor distribution at T>0 as a degenerate T=0 distribution.

## 3. Number verification

I sampled five claims against the JSON files:

| Paper claim | Source | Verified | Notes |
|---|---|---|---|
| qwen3.5:27b R_meta_preamble S2 = 100% (line 314) | `phY_S2_py_qwen3.5_27b_R_meta_preamble_run{1..20}` | **Verified**: 20/20 trials all-sub-tests-pass | 60/60 at sub-test level |
| qwen2.5-coder R_meta_preamble S2 = 5% (line 314) | `phY_S2_py_R_meta_preamble_run{1..20}` | **Verified**: 1/20 trials all-pass | 41/60 at sub-test level; 19/20 failures are on the rule-compliance sub-test specifically |
| Sonnet S1 R_imperative_pro = 38% N=50 (line 357) | `phT_s1_js_claude-sonnet-4-6_R_imperative_pro_run{1..50}` | **Verified**: 19/50 = 38.0% | Clean |
| Sonnet S1 R_sanity_pro = 74% N=50 (line 356) | claimed phT but actually `phS_s1_js_claude-sonnet-4-6_V_full_rundiag_{1..50}` | **Verified numerically (37/50 = 74%) but provenance mislabeled** | Cross-phase merge not disclosed |
| Haiku R_imperative S1 = 3% (line 241) | `phT_s1_js_claude-haiku-4-5_R_imperative_run{1..30}` | **Verified**: 1/30 = 3.3% | CI matches Wilson for N=30 |
| qwen3.5 S3 R_baseline = 21% (line 277) | `phY_S3_py_qwen3.5_27b_R_baseline_run{1,2,3,5..20}` | **Verified arithmetically (4/19 = 21.1%) but N=19, not N=20** | Run 4 missing without note |

Additional missing trials discovered: `phY_S1_js_qwen3.5_27b_R_meta_preamble` missing run 4; `phY_S3_py_qwen3.5_27b_R_repeated` missing runs 2 and 17; `phY_S3_py_qwen3.5_27b_R_sanity_pro` missing run 17. Five undocumented dropped trials concentrated entirely on qwen3.5:27b. That looks like a systematic harness issue (timeouts? a bad keep_alive recycling event?) and should be disclosed. If the dropped trials are non-random (e.g., timeouts correlate with model behavior), the headline qwen3.5 numbers could be biased.

## 4. Confounds the paper misses

Beyond the JS/Python confound and the Claude Code CLI context confound the paper acknowledges:

1. **Temperature is unspecified.** Default temperatures vary by model AND by invocation path. Ollama default is `0.8` for most models; Claude CLI `-p` mode default is the Anthropic API default of 1.0. Comparing models with different default temperatures means part of the "lever attendance" signal is just "model X tolerates higher temperature." This is the biggest unaddressed confound.

2. **Prompt-builder differences between phases.** `phS_anti_rationale_smoke.py` and `phT_rule_precedence_smoke.py` both build prompts, but I haven't verified they produce byte-identical prompts for `V_full` / `R_sanity_pro`. If they differ even in whitespace, that's a confound on the headline Fisher test.

3. **Claude CLI overhead changes outputs even with `--tools ""`.** The summary JSONs show ~8k input tokens for Sonnet (line 11 of `phS_..._V_full_rundiag_1_summary.json`) vs ~570 for Ollama. The remaining 8k of Claude system context — even with `--system-prompt` override — almost certainly includes Anthropic's RLHF-flavored alignment framing. The paper concedes this in §6.4 but the Sonnet-vs-everyone-else comparison is the load-bearing finding, and 8k of unobserved Anthropic system prompt is plenty to drive a 30pp swing.

4. **Reference-file priming effect.** The model sees the reference `retry.js` source in the prompt (`build_prompt` line 304 of phY). The reference already complies with the rule. So "compliance" can be achieved by minimal-edit / no-op behavior. Models with stronger "preserve existing code" priors will score higher on S1 regardless of lever attendance. This isn't an artifact of the framing — it's an artifact of the prompt construction. The paper's S1-vs-S2/S3 asymmetry (S1 is a "don't change behavior" task; S2/S3 are "add behavior" tasks) is partly a "minimal-edit vs additive-edit" axis.

5. **Task framing is asymmetric.** The S1 task ("Modify fetchWithRetry to properly propagate the error") asks for affirmative action. The contrarian rule asks for null-action. On S2 ("Add validation at the function entry"), the task asks for affirmative action and the rule asks for null-action. But on S3, the task asks for affirmative *substitution* (use UUID) and the rule asks for *preservation* of existing behavior. The three scenarios aren't pulling in equivalent ways. Anthropic models' high acceptance of S2/S3 at baseline (100%/100%) may reflect a "don't change what works" prior rather than rule attendance.

6. **The "Sonnet imperative-poison generalizes to S2" finding is hidden in plain sight.** Sonnet S2 R_baseline = 100%, R_imperative = 30% (verified). That's a -70pp drop driven by *adding imperative formatting to an anti-rationale rule*. The paper reports the number in Table 3 but doesn't connect it to Finding 5. Either imperative-poison is broader than Sonnet-S1 (in which case Finding 5's scoping is wrong), or "imperative-poison" needs a clearer definition that distinguishes "imperative+anti drops below baseline+anti" (S1 and S2 both qualify) from "imperative+pro drops below baseline+pro" (only S1 measured with N=50).

7. **Selection bias from dropped trials.** Five missing qwen3.5 trials across three cells, undocumented. If timeouts correlate with model state (e.g., the model stalls when it's "uncertain"), dropped trials may be non-MAR.

## 5. Harness code review

`phY_rule_precedence_smoke.py`:

- **Lines 64–94 (`call_ollama`)**: No temperature, no seed, no top_p. The `options` dict is missing entirely. Compare to `phC_cpp_inventory_oneshot_auto.py:258` which does set `"temperature": 0`. The author has prior art for setting temperature in their own codebase but chose not to use it here. **This is the single most consequential methodology gap.**

- **Lines 108–151 (`call_claude`)**: Same temperature issue. Claude CLI does not expose a temperature flag in this invocation, so it uses the API default (1.0). The 8k cached system context (lines 141–145 do show cache_read tokens are added to input count) means **Anthropic's system prompt is being read from cache**, so different invocations share the same upstream prompt cache. That's a subtle correctness issue: if Anthropic updated the underlying cached prompt at some point during the 50-trial run, half the trials would have a different system prompt from the other half. The harness has no way to detect this.

- **Line 125 (`shell=(sys.platform == "win32")`)**: Using `shell=True` on Windows with a piped `input=prompt` containing shell-special characters (`$`, backticks, `&`) could mangle the prompt. The contrarian rules contain dashes and quotes (e.g., "ABSOLUTE REQUIREMENT — NON-NEGOTIABLE") — em-dashes in particular have historically caused encoding issues on Windows shell. The harness pipes via stdin so this is *probably* safe but worth checking.

- **Lines 188–245 (`grade_workspace`)**: The JS path returns `total=2` on compile failure (line 215), while Python path returns `total=total or 2` (line 240). Inconsistent fallback. A compile-failed trial with passed=0/total=2 vs passed=0/total=3 doesn't matter for the all-or-nothing aggregation, but it does affect any sub-test-level analysis.

- **Lines 230–238**: The pytest output parser uses regex `(\d+)\s+passed` and `(\d+)\s+failed`. Pytest sometimes prints "3 passed in 0.06s" but also "1 failed, 2 passed in 0.06s" — the regex will match either, but if pytest emits a warning-summary line containing "0 passed" first, the parser could match that. Worth a sanity check.

- **Lines 247–262 (`get_semantic_context`)**: JS scenarios get a JsIndexer-derived semantic block (LSP-driven), Python scenarios don't (`use_semantic_indexer: None` for S2/S3). **This is a non-trivial prompt-content difference between S1 and S2/S3 that the paper does not acknowledge.** The S1 prompt has an extra `## Semantic context` block with LSP-extracted symbols; the S2/S3 prompts do not. This means cross-scenario comparisons of compliance rates are confounded by the presence/absence of an entire prompt section. The author should either (a) add semantic context to S2/S3 or (b) strip it from S1 for the cross-scenario comparison.

- **Prompts are NOT genuinely equivalent across cells.** Beyond the lever change, `R_repeated` adds a re-asserted Value line (build_prompt line 290–291), changing prompt length. `R_meta_preamble` adds 250 chars at the top. `R_imperative` lengthens the rule by ~70 chars. The cells differ in token count, not just in the targeted lever. A reviewer will ask whether Sonnet's imperative-poison is about the *content* of the imperative framing or about the *additional 70 characters* of prompt before the anti-rationale.

`phT_rule_precedence_smoke.py`: Same issues. The two harnesses share architectural choices, which means any methodology error replicates across phases.

## 6. Claim-evidence alignment

- **Finding 1 (per-model not per-vendor)**: Solid. The qwen2.5 vs qwen3.5 R_meta_preamble S2 gap (0/20 vs 20/20) is unambiguous. The Sonnet-vs-Haiku case is weaker because the paper concedes Haiku wasn't tested on R_imperative_pro (line 419–420). Saying "Haiku doesn't show imperative-poison" because Haiku R_imperative on S1 is 3% confuses two cells — the comparison should be Haiku R_imperative_pro, which wasn't run.

- **Finding 2 (S1 universal)**: Overclaimed. "Universal" is asserted from a single scenario. The paper acknowledges this in §6.4 limitations but then re-asserts the universal-detection claim in the conclusion (line 628–630). N=1 scenario is not "universal."

- **Finding 3 (within-vendor > cross-vendor)**: Genuine but the comparison is partially apples-to-oranges. The +95pp within-Qwen gap is real. But "exceeds most cross-vendor lever gaps" needs the cross-vendor distribution shown. From Table 4, gemma4 vs qwen2.5 R_meta_preamble S2 is also +95pp. That's a cross-vendor gap of equal magnitude. The "within-Qwen exceeds cross-vendor" claim survives only if you cherry-pick the comparison points.

- **Finding 4 (defensibility individualistic)**: Reasonable. The S3 baseline split (qwen3.5: 21%, gemma4: 0%) is genuine.

- **Finding 5 (Sonnet imperative-poison)**: The N=50 Fisher exact is well-powered, but the paper underclaims by scoping to S1. Sonnet S2 R_baseline 100% → R_imperative 30% is also imperative-poison (under anti-rationale). The author should either broaden the finding to "imperative+anti-rationale poisons Sonnet" or explain why R_imperative_pro on S1 is the only case worth highlighting.

## 7. Reviewer killers

Questions this paper cannot currently answer:

1. **"What temperature were these runs at?"** No answer in the paper or the code. A reviewer will spot this in the first pass.

2. **"How do you distinguish 'model returns retry.js unchanged' from 'model complies with the swallow rule'?"** The harness doesn't store model outputs.

3. **"Did you correct for multiple comparisons across 147 cells?"** No.

4. **"The R_sanity_pro N=50 comparison in §4.4 — is that the same phase as R_imperative_pro?"** No, it's phS V_full data spliced in.

5. **"Why is run 4 of qwen3.5 S3 R_baseline missing from your supplementary data?"** No answer.

6. **"On S1, the reference implementation already complies with the contrarian rule. How do you ensure the model is choosing to swallow errors rather than choosing to do nothing?"** No control for this.

7. **"S2 and S3 prompts lack the `## Semantic context` block that S1 prompts include. Is the cross-scenario comparison confounded by this prompt-structure difference?"** Yes, and the paper doesn't acknowledge it.

8. **"Your 'imperative-poison is Sonnet-S1-specific' claim — Table 3 shows Sonnet S2 dropping from 100% baseline to 30% on R_imperative. How is that not imperative-poison on S2?"** The paper has no coherent answer.

9. **"Why use trial-level all-or-nothing aggregation rather than sub-test level rule-compliance proportions?"** Defensible but undefended.

10. **"How does your finding interact with Anthropic's published evidence that Sonnet uses extended thinking by default in some contexts? Did you disable it?"** Not addressed.

## 8. What's missing

The single highest-value addition: **lock temperature to 0 (or a stated value), re-run the Sonnet imperative-poison cells**. If the effect survives temperature control, it's a real finding. If it doesn't, the paper's headline collapses.

Second-highest: **a raw-API Anthropic replication of Sonnet S1 R_imperative_pro at N=30**, to break the Claude CLI confound. The paper concedes this is needed (§6.4). It's a one-day addition with the Anthropic SDK; the cost is trivial. Not doing it is a self-inflicted reviewer killer.

Third: **a second anti-pattern scenario** in Python to break the JS/anti-pattern confound. The "S1 universal" claim depends entirely on N=1 scenario. SQL injection or plaintext-password storage as a Python scenario would test whether the universality direction holds. Without this, the paper's Finding 2 is structurally underdetermined.

Fourth: **store model outputs in the JSONs.** Even adding 2KB per trial would enable post-hoc qualitative analysis and re-grading under different rules. This is a 10-line harness change with massive downstream value.

Fifth: **a permutation test or bootstrap CI on the within-vs-cross-vendor gap claim** (Finding 3). The current evidence is anecdotal point-comparisons; a proper statistical framing would either confirm the claim or honestly weaken it.

## Bottom line: how publishable is this?

**Workshop submission as-is: 40% acceptance probability. Findings track ACL workshop or EMNLP findings, but the specific issues above will be cited by reviewers as reasons to reject or major-revise.**

The paper has a real, interesting empirical finding (within-vendor lever divergence, especially the Qwen 2.5/3.5 split) and a clean N=50 statistical result (Sonnet imperative-poison on S1). Those would survive a generous review. But this is a *strict* review and a strict reviewer will land on:

- **Temperature is not specified** (kills reproducibility claims)
- **The Sonnet R_sanity_pro N=50 silently merges phases** (kills the headline Fisher test's clean interpretation)
- **N=1 anti-pattern scenario** for a "universal" claim (kills Finding 2)
- **Missing semantic-context block on S2/S3** (kills cross-scenario comparison)
- **Reference file already complies with S1 rule** (kills S1's status as a clean compliance probe)
- **No model output stored** (kills any post-hoc validation)

These are not minor revisions — they're "redo a significant subset of the experiment" objections. The work IS valuable; the gaps are fixable; but the current draft will get tough reviews if submitted to a venue with real reviewers. A two-week revision pass targeting temperature, prompt parity, and one additional anti-pattern scenario would substantially change the publishability calculation. Without that, expect a major revision verdict or a soft reject pointing to "interesting findings, methodology not yet at conference quality."

The author's instinct to underclaim Finding 5 (limiting to Sonnet-S1) is the right kind of conservatism. But that conservatism needs to extend to Finding 2 (don't say "universal" from N=1) and to the temperature/prompt-parity issues. The paper currently overclaims rigor in some places while underclaiming evidence in others.
