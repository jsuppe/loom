/* claims.js — detail content for every numeric / experimental claim
 * surfaced on the homepage. Each entry powers the modal opened by
 * clicking the corresponding tile/row.
 *
 * Schema:
 *   id           — short stable key (matches `data-claim` in HTML)
 *   phase        — short phase label shown in the modal title bar
 *   status       — short tag like [ DONE ], [ NULL ], [ FIXED ]
 *   headline     — single-sentence restatement of the claim
 *   what         — bulleted: what was measured + how
 *   numbers      — bulleted: the actual data points
 *   constraints  — bulleted: what was held constant, what varied
 *   limitations  — bulleted: what this experiment did NOT prove
 *   calculations — bulleted: explicit step-by-step math behind the headline
 *   subtext      — single short string shown directly on the homepage card/row
 *   repo         — link to the FINDINGS doc in the public repo
 */
window.LOOM_CLAIMS = {
  // ===================== Card 1: ~8x cheaper =====================
  "cost-15x": {
    phase: "PHASE D",
    status: "[ VALIDATED — UPDATED N=20 ]",
    headline:
      "On single-file Python benchmarks, an Opus-plans / qwen-executes pipeline produced parity quality at ~8× lower cost than Opus iterating end-to-end. The original N=5 measurement reported 10-16× — but a follow-up N=20 with matched-pricing baseline showed the larger sample is closer to ~8×.",
    what: [
      "Phase D AUTO architecture: claude -p with --model opus reads the benchmark README and writes a detailed implementation spec. The spec is stored as a Loom Specification.",
      "loom_exec dispatches a single one-shot task to qwen3.5:latest via Ollama. qwen writes the entire target file in one append.",
      "Final correctness is graded by running the hidden pytest suite, which neither agent ever sees.",
      "Compared against a Phase A/B baseline where two Claude Opus subagents iterate on the same benchmark in-session.",
    ],
    numbers: [
      "python-state-machine (21 tests): 5/5 trials hit 21/21. Median Opus cost $0.131, median wall 69.6s. Phase B Opus-symmetric baseline: $2.06 / 145s. Ratio: 15.7× cheaper, 2.1× faster.",
      "python-queue (15 tests): 5/5 trials hit 15/15. Median Opus cost $0.186, median wall 61.8s. Phase A Opus-symmetric baseline: $1.85 / 139.6s. Ratio: 10.0× cheaper, 2.3× faster.",
      "qwen execution adds $0 marginal cost (local Ollama).",
      "Cost figures from claude -p's reported total_cost_usd — directly measured per call, not estimated.",
    ],
    constraints: [
      "Both agents use the same fresh workspace and same hidden test suite per trial.",
      "claude -p is invoked with --no-session-persistence so each trial starts cold.",
      "qwen3.5:latest is invoked at default temperature; no fine-tuning, no system prompt beyond the spec bundle.",
      "Realistic qwen cost model: 200W GPU draw × ~11s compute × $0.16/kWh = $0.0001 energy/trial; plus $2,500 workstation amortized over 3 years × 4 active hrs/day = $0.0017 hardware/trial. Total ≈ $0.002/trial.",
      "If qwen runs on a machine you already own and use (typical dev workstation, M-series Mac, etc.), the amortization is already a sunk cost; marginal cost approaches the energy floor ($0.0001/trial).",
    ],
    limitations: [
      "Two single-file Python benchmarks (~150 LoC each). Multi-file Dart in Phase C: 4/5 with qwen2.5-coder:32b, 2/5 with qwen3.5 — multi-file generalization is brittle and executor-sensitive.",
      "Greenfield-from-spec only. We did not test refactors, large-codebase edits, or maintenance work.",
      "qwen3.5 is not optimal for non-Python languages. On Dart, qwen3.5 invented patterns with missing dependencies (e.g., `class HistoryEntry extends Equatable`); qwen2.5-coder:32b was more conservative.",
      "The asymmetric multi-task variant (Opus decomposes into 6+ atomic tasks) scored 0-38% on the same benchmark — the one-shot variant is the validated configuration.",
      "Cost shift observed Apr 24 → Apr 26: Phase D AUTO Opus cost roughly doubled despite identical spec content. Phase B baseline did not move similarly. Suggests the big-output one-shot Opus call is sensitive to billing changes that the iterative back-and-forth is not.",
      "N=5 per benchmark cell originally; expanded to N=20 in Tier 1. Original N=5 medians were unrepresentatively low (cheaper-pricing-day + sampling).",
      "Cost model assumptions: $0.16/kWh electricity (US average; varies 2-5× internationally), $2,500 workstation cost (varies based on GPU choice), 3-year amortization, 4-hour daily utilization. Heavy continuous use shrinks per-trial amortization; light use grows it. The $0.002 figure is a midpoint estimate, not a measurement.",
      "Cloud-only alternative: if you ran qwen on a rented GPU instance instead of local hardware, the per-trial cost would be different — typically $0.005-0.02/trial on AWS/Lambda Cloud spot instances. Still 1-2 orders of magnitude below the Opus call cost.",
    ],
    calculations: [
      "── ORIGINAL Apr 24 measurement (N=5) ─────────────────",
      "state-machine Opus cost per trial (5 trials): sort([0.1272, 0.1488, 0.1305, 0.1312, 0.1437]) → median = $0.1312",
      "Phase B Opus-symmetric baseline (5 trials, Apr 24): sort([1.84, 2.06, 2.10, 1.80, 2.12]) → median = $2.06",
      "Apr 24 ratio: $2.06 / $0.1312 = 15.70× cheaper.",
      "python-queue Apr 24 ratio: $1.854 / $0.1858 = 9.98× cheaper.",
      "── FOLLOW-UP Apr 26 with N=20 (Tier 1) ───────────────",
      "Phase D AUTO state-machine N=20 median Opus cost: $0.2264 — significantly higher than the N=5 $0.1312 from 2 days earlier.",
      "Spec lengths essentially identical: Apr 24 mean 12,366 chars; Apr 26 mean 12,231 chars. Output content not the cause.",
      "Phase B baseline retest Apr 26 (N=5): median = $1.7760. Comparable to Apr 24's $2.06 (within sample variance).",
      "Conclusion: the cost shift is Phase D AUTO-specific, NOT a broad pricing change. Likely Anthropic-side billing change for big-output Opus calls, OR new thinking-token charging. Iterative back-and-forth baseline held steady.",
      "── Matched-pricing Apr 26 ratio ──────────────────────",
      "state-machine: $1.7760 / ($0.2264 + $0.002) = 7.78× cheaper.",
      "python-queue (today's baseline NOT retested; using Apr 24 $1.854): $1.854 / ($0.2122 + $0.002) = 8.65× cheaper.",
      "── Qwen (local executor) cost model ──────────────────",
      "GPU power at load (mid-range, e.g. RTX 4070): ~200W.",
      "Median qwen compute time per trial: ~11s (Phase D AUTO).",
      "Energy: 200W × 11s = 0.611 Wh = 0.000611 kWh × $0.16/kWh = $0.0001/trial.",
      "Hardware amortization: $2,500 workstation ÷ 3 yrs ÷ (4 active hrs/day × 365) = $0.57/active-hr → $0.0017/trial at 11s.",
      "Total realistic qwen cost/trial ≈ $0.002. On hardware you already own, marginal cost ≈ $0.0001 (energy only).",
      "── Wall-clock ────────────────────────────────────────",
      "state-machine median wall (Phase D AUTO N=20): 69.3s. Phase B baseline: 145s (Apr 24) / 117s (Apr 26 retest). Ratio: ~2× faster.",
      "── Headline ──────────────────────────────────────────",
      "Today's matched-pricing N=20 ratio: 7.8× to 8.7× across both benchmarks → reported as ~8× cheaper.",
      "The original 10-16× was a real measurement but on a sample (N=5) and pricing day where Opus calls landed unusually cheap. The matched-pricing N=20 figure is the more defensible number.",
    ],
    subtext: "Apr 24 N=5: 15.7× (state-machine) · Apr 26 N=20: 9.0× vs old baseline · Apr 26 N=20 matched-pricing: 7.8× · the original was a low-side sample on a cheaper-Opus day",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-phaseD.md",
  },

  // ===================== Card 2: +60-93pp compliance =====================
  "hook-93pp": {
    phase: "PHASE E",
    status: "[ VALIDATED ]",
    headline:
      "Loom's pre-edit hook surfaces linked requirements before each tool call. On 3 codebase-rule scenarios, compliance rose from 7% to 100% on Sonnet and from 40% to 100% on Haiku.",
    what: [
      "PreToolUse hook fires before Edit/Write tool calls. It runs `loom context <file>` and injects the linked requirements as a system-reminder.",
      "Trial-level A/B: same starter codebase, same task prompt, same model. Only the hook config (.claude/settings.json) is toggled.",
      "Each scenario has a codebase-specific rule that contradicts the LLM's natural default (e.g., 'use LegacyConfig.get, not os.environ').",
      "Verifier checks the produced file against the rule with a regex/AST predicate.",
    ],
    numbers: [
      "3 scenarios (config_api, error_type, storage_api), N=5 per cell, 3 model tiers — 90 trials total.",
      "Sonnet: off 1/15 (7%), on 15/15 (100%). Lift +93pp.",
      "Haiku: off 6/15 (40%), on 15/15 (100%). Lift +60pp.",
      "Opus: off 15/15 (100%), on 15/15 (100%). Lift +0pp (Opus reads codebase context and complies without injection).",
      "Cost overhead: ~$0.004/trial Haiku, ~$0.027/trial Sonnet, ~$0 Opus (cents per edit).",
    ],
    constraints: [
      "Scenarios were authored to be contrarian to Pythonic defaults but defensible from in-file context.",
      "Hook is non-blocking by default — it injects context but lets the edit proceed.",
      "Same regex verifier was used to grade every trial; no human-in-the-loop scoring.",
    ],
    limitations: [
      "3 synthetic scenarios on small (3-file) Python projects. Real codebases may behave differently.",
      "Single hook firing per trial. Multi-edit sessions where the hook fires repeatedly are untested.",
      "Opus saturated on these scenarios because the constraint was visible in adjacent files. Constraints stored only in Loom (not visible in any file) might still benefit from the hook even at Opus tier.",
      "Hard-block variant (LOOM_HOOK_BLOCK_ON_DRIFT=1) tested separately: 30/30 mechanism reliable across all tiers, but Haiku misnarrated 2/5 blocked trials as success.",
      "Did not capture 'responsible refusal' — when the agent pauses for permission rather than complying, the binary verifier scores it identically to silent noncompliance.",
    ],
    calculations: [
      "Sonnet hook=off compliance: 1 / 15 trials = 6.67% (rounded to 7%).",
      "Sonnet hook=on compliance: 15 / 15 trials = 100%.",
      "Sonnet lift: 100% − 7% = +93 percentage points.",
      "Haiku hook=off compliance: 6 / 15 = 40%.",
      "Haiku hook=on compliance: 15 / 15 = 100%.",
      "Haiku lift: 100% − 40% = +60 percentage points.",
      "Opus hook=off: 15/15 = 100%. Opus hook=on: 15/15 = 100%. Opus lift: +0pp (saturated baseline).",
      "Cost overhead per Sonnet trial: avg(hook=on cost) − avg(hook=off cost) = $0.0714 − $0.0449 = +$0.0265 (≈ 2.65 cents).",
      "Each compliance fraction is over 3 scenarios (config_api, error_type, storage_api) × 5 trials per cell.",
    ],
    subtext: "Sonnet 1/15 → 15/15 (+93pp) · Haiku 6/15 → 15/15 (+60pp) · Opus 15/15 → 15/15 (saturated)",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-phaseE.md",
  },

  // ===================== Card 3: 100% citation =====================
  "citation-100": {
    phase: "PHASE G",
    status: "[ VALIDATED — Haiku ]",
    headline:
      "When a requirement carries a textual rationale, Haiku cites the rationale's specific facts back in 100% of trials. Without rationale, citation is 0–13%. Identical injected byte count between placebo and rationale cells — only content carries the lift.",
    what: [
      "4-cell A/B/C/D design: off (no hook) / on-rule (rule only) / on-rule+placebo (rule + length-matched bland filler) / on-rule+rat (rule + true rationale).",
      "Placebo cell controls for the byte-count salience confound: identical injected byte count to the rat cell, but content adds no real information.",
      "Two metrics per trial: pass (file content respects the rule) AND cited_rationale (agent's response text matches a regex for unique rationale facts like incident dates).",
    ],
    numbers: [
      "3 scenarios × 4 cells × N=5 = 60 trials, Haiku 4.5, $1.84, 15.0 min wall.",
      "Compliance: off 0/15 (0%), on-rule 10/15 (67%), on-rule+placebo 11/15 (73%), on-rule+rat 14/15 (93%).",
      "Citation: off 1/15 (7%), on-rule 0/15 (0%), on-rule+placebo 2/15 (13%), on-rule+rat 15/15 (100%).",
      "Compliance decomposition: rule alone +67pp; placebo over rule +6pp (byte-salience); rationale over placebo +20pp (content effect); rationale over rule +26pp combined.",
      "All three scenarios' rat cells: 5/5 cited (100%) on the strict regex.",
    ],
    constraints: [
      "Same model (Haiku 4.5), same starter codebase, same task prompts across all 4 cells.",
      "Placebo text generated per scenario: a verbose restatement of the rule with the same byte count as the true rationale, but no incident dates, ADR references, or external constraints.",
      "Strict regex (per scenario): `BackoffError|2024-09-12|backoff_loop|wrapper|ledger|incident` for S1, `TOCTOU|db\\.commit|transaction|atomic|2024-03-15|race` for S2, `legacy|partner|2027|ADR.?0042|truncat|contract` for S3.",
    ],
    limitations: [
      "Haiku 4.5 only on this branch. A Sonnet replication exists on a sibling branch (`claude/bakeoff-v1`) showing the citation effect transfers (+80pp gap on Sonnet); not yet merged into main.",
      "Opus tier untested. Phase E showed Opus saturates compliance on similar scenarios; whether the citation effect transfers further up is open.",
      "3 synthetic scenarios with well-structured rationales (incident dates, ADR references). Messier real-world rationale text may produce different citation rates.",
      "Precondition: the hook was silently dropping rationale before reaching the agent. Fixed in commit a2e5bf9 before the experiment ran. Without that fix, every cell reduces to on-rule regardless of what's seeded.",
    ],
    calculations: [
      "Compliance per cell (15 trials each, 3 scenarios × N=5):",
      "  off 0/15 = 0% · on-rule 10/15 = 67% · placebo 11/15 = 73% · rat 14/15 = 93%.",
      "Citation per cell:",
      "  off 1/15 = 7% · on-rule 0/15 = 0% · placebo 2/15 = 13% · rat 15/15 = 100%.",
      "The +87pp citation gap between placebo and rat (with identical byte counts) is the decisive content-vs-salience finding — the same number of bytes hits the agent but only true-rationale content gets internalized.",
      "Compliance decomposition (Haiku):",
      "  rule alone over nothing: +67pp",
      "  placebo over rule (byte-salience):  +6pp",
      "  rationale over placebo (content):  +20pp",
      "  rationale over rule (combined):    +26pp",
    ],
    subtext: "rat 100% cited vs 0–13% across other cells · same byte count as placebo · only content carries the lift",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-phaseG.md",
  },

  // ===================== ~830 trials hero claim =====================
  "trial-count": {
    phase: "BAKEOFF V2",
    status: "[ COMMITTED ]",
    headline:
      "~830 pre-registered A/B trials across the bake-off series. Every result published, including ceiling-effect nulls and rolled-back features, regardless of direction.",
    what: [
      "Each phase has a pre-registered PROTOCOL.md or amendment committed BEFORE any data is collected.",
      "Each phase has a corresponding FINDINGS-bakeoff-v2-*.md committed immediately after the run, regardless of direction.",
      "Per-trial JSON summaries committed under experiments/bakeoff/runs-v2/ — anyone can re-aggregate from raw data.",
    ],
    numbers: [
      "Phase A — TaskQueue ±Loom in-session: 50 trials.",
      "Phase B — state-machine ±Loom in-session + Apr-26 retest: 35 trials.",
      "Phase D — Asymmetric pipeline (manual + AUTO + N=20 extension): 60 trials.",
      "Phase E — Pre-edit hook on/off, single tier + cross-tier + scale + block: 136 trials.",
      "Phase G — Cross-session rationale memory: 60 trials (main; commit 50e9e9b).",
      "Phase D smoke (R1: add field) — 5-cell isolation of delivery vs storage: 25 trials.",
      "Phase R2 (rename) — control on saturated task: 25 trials.",
      "Phase K — cross-session memory on qwen+loom_exec: 60 trials.",
      "Phase C dart-orders Tier-progression (5 tiers × N=5): 25 trials.",
      "Phase C cpp-orders smoke + N=5: 11 trials.",
      "Phase C dart-inventory bake-offs (v3 + v4): 40 trials.",
      "Phase C python-inventory at 9 files (qwen3.5): 5 trials.",
      "Cross-language map (S1 contrarian × 9 languages × 4 cells × N=5): 180 trials.",
      "R6 series (multi-file refactor on pyschema-extended; T/U/V harnesses): ~120 trials.",
    ],
    constraints: [
      "claude -p invoked with --no-session-persistence per trial — each starts cold.",
      "Hidden test suites are committed to the repo and never shown to either agent during a trial.",
      "All claude -p cost numbers are direct from the JSON response, not estimated.",
    ],
    limitations: [
      "Phases A and B saturated on correctness — every cell hit 100% pass. They function as a cost-overhead measurement only, not a correctness benefit measurement.",
      "Most cells are N=5 — sufficient for the large effects reported but underpowered for marginal contrasts. Phase D N=20, Phase E.cross-tier N=15, and Phase G N=15/cell are the higher-power cells.",
      "Synthetic benchmarks (3-700 LoC each). Real production codebases are much larger and more idiosyncratic.",
      "qwen3.5:latest is the executor for most local trials. Cross-language results are tier-specific; whether qwen2.5-coder:32b or larger models flip resistant languages (C/Go/C++) into bridging territory is open.",
    ],
    calculations: [
      "50 (A) + 35 (B) + 60 (D) + 136 (E + cross-tier + scale + block) + 60 (G main) + 25 (D smoke / R1) + 25 (R2) + 60 (K) + 25 (C dart-orders) + 11 (C cpp) + 40 (C dart-inventory) + 5 (C python-inventory) + 180 (cross-language) + ~120 (R6 series) = ~830 trials.",
      "Errors across all phases: 0 (no run failed for harness reasons).",
    ],
    subtext: "~830 committed bakeoff trials across 9 languages · 0 harness errors · all FINDINGS-*.md committed alongside the runs",
    repo: "https://github.com/jsuppe/loom/tree/main/experiments/bakeoff",
  },

  // ===================== Cross-language map (NEW headline) =====================
  "phase-cross-lang": {
    phase: "CROSS-LANGUAGE",
    status: "[ THE HEADLINE ]",
    headline:
      "Same scenario, same model, ported across 9 languages: Loom's lift varies dramatically by language. Off-cell fitness alone does NOT predict where Loom helps.",
    what: [
      "S1 contrarian-rule scenario (swallow vs propagate OSError) ported to C++, C, Java, Go, Rust, JavaScript, TypeScript, NASM x86-64 Asm — alongside the existing Python.",
      "Same 4-cell A/B/C/D harness as Phase G: off / on-rule / on-rule+placebo / on-rule+rat.",
      "Same executor (qwen3.5:latest), same task prompt, same regex verifier — only the language scaffolding changes.",
      "180 trials total. The result is the cross-language Loom-lift map.",
    ],
    numbers: [
      "Python:     off 80%, on-rule 100%, +placebo 100%, +rat 100%  (already-saturated)",
      "Rust:       off  0%, on-rule 100%, +placebo 100%, +rat 100%  (rule-saturates: +100pp)",
      "Java:       off  0%, on-rule  60%, +placebo 100%, +rat 100%  (bridging)",
      "TypeScript: off  0%, on-rule  40%, +placebo  80%, +rat 100%  (bridging-graduated)",
      "JavaScript: off  0%, on-rule  20%, +placebo  40%, +rat  60%  (graded, no saturation)",
      "Go:         off 20%, on-rule  60%, +placebo 100%, +rat  60%  (volatile)",
      "C:          off 50%, on-rule  50%, +placebo  60%, +rat  60%  (resistant-mid)",
      "C++:        off  0%, on-rule   0%, +placebo 100%*, +rat 67%  (collapsed; *placebo artifact)",
      "Asm NASM:   off  0%, on-rule 100%, +placebo 100%, +rat 100%  (rule-saturates: +100pp)",
    ],
    constraints: [
      "Same executor model (qwen3.5:latest at temperature 0) across every language cell.",
      "Per-language scaffolding (file structure, test runner) authored to match each language's idioms — not a Python translation dropped into other languages.",
      "Each cell N=5; per-language total N=20 across the 4 cells.",
    ],
    limitations: [
      "qwen3.5:latest tier only. Whether qwen2.5-coder:32b shifts C/Go/C++ from resistant into bridging is open.",
      "S1 is a single contrarian-rule scenario. Whether the regime classification holds for S2/S3-shaped scenarios needs ports.",
      "Synthetic 3-file scaffolds. Real-codebase friction (idiomatic patterns, library APIs, build tooling) may differ.",
      "Off-cell variance for Go and C is high — N=5 isn't enough to distinguish 'volatile' from 'partial saturation'.",
    ],
    calculations: [
      "Loom strong-fit zone (qwen3.5 hits ≥100% on rule alone or ≤30pp shy of saturation): Python, Java, TypeScript, Rust, Asm.",
      "Mixed: JavaScript (caps around 60%, never saturates).",
      "Weak: C, Go, C++ (≤+10pp lift, or volatile direction).",
      "The hidden variable is qwen's 'rule-followingness' in each language — a property of training-data rule-following more than raw fluency. Five languages share off=0% but span the full Loom-response spectrum.",
    ],
    subtext: "9 languages · 180 trials · Loom strong on Python/Java/TS/Rust/Asm; mixed on JS; weak on C/Go/C++",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-cross-language-map.md",
  },

  // ===================== D-smoke isolation (NEW) =====================
  "phase-D-isolation": {
    phase: "D.SMOKE",
    status: "[ DELIVERY IS THE MECHANISM ]",
    headline:
      "Same Loom store contents in D2 and D3; only `task.context_specs` linkage differs. D2 = 0%, D3 = 95%. The lift comes entirely from delivering the spec to the executor — stored data alone is invisible.",
    what: [
      "5-cell A/B/C/D/E refactor smoke on the pyschema library: D0 greenfield / D1 qwen-only / D2 stored-undelivered / D3 standard-delivery / D4 + LOOM_TYPELINK.",
      "D2 has the refactor spec in the Loom store. D3 has the same spec, plus the task references it via context_specs. The only difference is that line.",
      "Acceptance grader: a hidden 5-test pytest suite for the new RegexField class.",
    ],
    numbers: [
      "D0 greenfield (full build spec, fresh code): 99% acceptance",
      "D1 qwen-only (placeholder spec, pre-written code): 0% acceptance",
      "D2 stored-undelivered (real spec stored, NOT in prompt): 0% acceptance",
      "D3 standard-delivery (real spec stored AND in prompt): 95% acceptance",
      "D4 + LOOM_TYPELINK=1 (typelink layer on top): 100% acceptance",
      "D2 vs D3 = +95pp lift on the same store contents; only the prompt assembly differed.",
    ],
    constraints: [
      "Same fresh workspace per trial. Same hidden test suite.",
      "Same Loom store contents in D2 and D3 — verified by `loom list` and `loom specs` returning identical data.",
      "Difference: D2's task has `context_specs=[]`; D3's task has `context_specs=[<the spec id>]`.",
    ],
    limitations: [
      "Single refactor type (add a class). Whether the same isolation holds for cross-cutting refactors is open (R6 series partially answers this).",
      "qwen3.5:latest only. Whether stronger executors close the D2 gap by reading the spec implicitly via embeddings is untested.",
      "5-cell N=5 each — the +95pp gap is large enough to be unambiguous but the marginal D3 vs D4 (95% vs 100%) is at noise floor.",
    ],
    calculations: [
      "D2 acceptance: 0/5 = 0%.",
      "D3 acceptance: 19/20 across the rerun = 95% (4/5 in original N=5 + 15/15 across higher-N retests).",
      "D3 − D2 lift: +95 percentage points on identical store contents.",
      "Headline interpretation: 'storing data in Loom' adds nothing on its own. The mechanism is the prompt-assembly path.",
    ],
    subtext: "D2 = 0%, D3 = 95% on the same Loom store · the +95pp lift is the prompt-assembly path",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-pythonfirst-smoke.md",
  },

  // ===================== M7 (typelink rolled back) =====================
  "phase-M7": {
    phase: "MILESTONE 7",
    status: "[ ROLLED BACK — published null ]",
    headline:
      "typelink (Specification.public_api_json + per-file contract verifier) was implemented, then removed after 50+ trials produced typelink_fail = 0 across every run. The contract-fence text in spec body was carrying the lift, not the structured public_api parsing.",
    what: [
      "~1300 LoC across 7 commits: AST extractors (Python, Dart regex), Specification.public_api_json field, Symbol/TypeContract dataclasses, type_contracts ChromaDB collection, post-task hook in loom_exec, CLI subcommands.",
      "Hypothesis: a per-file declarative public-API contract would let loom_exec catch surface drift between body output and the spec's declared shape, before grading.",
      "Rollout: 50+ trials with LOOM_TYPELINK=1 — the verifier was supposed to surface mismatches as `typelink_fail` events.",
    ],
    numbers: [
      "typelink_fail count across 50+ LOOM_TYPELINK=1 trials: 0.",
      "The R1 lift attributed to typelink was actually carried by Opus authoring contract-rich spec text that gets injected via task_build_prompt — the contract reaches qwen whether typelink parses it or not.",
      "Decision: remove ~1300 LoC. Cleaner code path, identical results.",
    ],
    constraints: [
      "Verifier run on every loom_exec task completion when LOOM_TYPELINK=1.",
      "Compared against same trials with LOOM_TYPELINK=0; no measurable difference in pass rate or output quality.",
    ],
    limitations: [
      "The data-plane lessons (contract-fence authoring is the load-bearing piece) are preserved in FINDINGS-bakeoff-v2-milestone7.md.",
      "If reintroduced, the binding should focus on cross-file invariants (e.g. 'every service constructor takes Store& first') that qwen can follow, not on signatures qwen reproducibly violates.",
    ],
    calculations: [
      "typelink_fail observed in 0 / 50+ trials.",
      "LoC removed in rollback commit 2599f15: ~1300 across src/, scripts/, tests/, harnesses.",
    ],
    subtext: "50+ trials, typelink_fail=0 → ~1300 LoC removed · the data plane (contract-fence text) carried the lift, not the structured parser",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-milestone7.md",
  },

  // ===================== Findings table rows =====================
  "phase-AB": {
    phase: "PHASES A / B",
    status: "[ NULL — published ]",
    headline:
      "Loom-as-in-session-tools adds bounded cost overhead with no measurable correctness benefit on saturated single-file benchmarks.",
    what: [
      "Both agents (Product Owner and Engineer) run a Claude model. The Engineer agent has Loom CLI tools available in-session.",
      "Engineer can call loom extract / loom link / loom check at will during the iteration loop.",
      "Compared against the same setup with Loom tools disabled.",
    ],
    numbers: [
      "Phase A — TaskQueue (15 tests), 50 trials across 10 cells: every cell hit 15/15.",
      "Phase B — state-machine (21 tests), 30 trials across 6 cells: 29/30 hit 21/21. The single failure was a Haiku+Loom run that stalled at 15/21 for 5 iters.",
      "Cost overhead with Loom tools: +12% (Opus symmetric) to +48% (asymmetric pairs).",
    ],
    constraints: [
      "Both benchmarks are pre-specified single-file Python libraries with hidden pytest suites.",
      "Each iteration of the in-session loop = one PO subagent call + one Engineer subagent call + one test run.",
    ],
    limitations: [
      "Pure ceiling effect — TaskQueue and state-machine are too easy for any Claude tier to fail. Loom's correctness contribution cannot be measured under saturation.",
      "Phases A/B are the wrong design to test Loom — Phase D and Phase E are.",
      "We publish them anyway because they're the cost-overhead story for the in-session-tools deployment shape.",
    ],
    calculations: [
      "Phase A pass rate: 50/50 cells hit 15/15 → 100% saturated (no headroom for measurement).",
      "Phase B pass rate: 29/30 hit 21/21 → 96.7% saturated. The 1 fail was a Haiku+Loom run with stop_reason='no_progress' at 15/21.",
      "Cost overhead by cell (Phase A):",
      "  Opus symmetric: median +Loom $1.92 vs no-Loom $1.71 → +12.3% overhead.",
      "  Sonnet symmetric: median $1.04 vs $0.81 → +28%.",
      "  Sonnet→Opus asymm: median +Loom $2.18 vs no-Loom $1.47 → +48.3%.",
    ],
    subtext: "Phase A: 50/50 saturated · Phase B: 29/30 saturated · cost overhead +12% to +48% with Loom-as-tools",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-phaseB.md",
  },

  "phase-C": {
    phase: "PHASE C",
    status: "[ VALIDATED at 3-file · CEILING at 9-file Dart ]",
    headline:
      "Tier 1+2 orchestration improvements lift qwen3.5 on 3-file Dart from 40% to 100%. Same pipeline transfers to single-file C++ at 100% and to 9-file Python at 100%. At 9-file Dart, qwen3.5 hits a complexity ceiling that orchestration cannot surmount; the ceiling is robust to executor swap.",
    what: [
      "Phase D AUTO architecture (Opus writes spec; loom_exec drains tasks; small executor writes each file) extended to multi-file Dart, single-file C++, 9-file Python, and 9-file Dart.",
      "Hidden test suite per benchmark; 21 tests for dart-orders + cpp-orders, 28 tests for dart-inventory, ~30 tests for python-inventory.",
      "Tier 1: per-task retry-with-error-feedback, pre-pinned dependency context (closes the 'qwen invents Equatable' failure mode), tighter output-contract phrasing.",
      "Tier 2: temperature ramp on retries (T=0.0/0.4/0.7), code-specialized model escalation (qwen3.5:27b or qwen2.5-coder:32b) when retries exhaust.",
      "Per-task gating tests verify each impl file compiles and exposes basic surface area before allowing the chain to advance.",
    ],
    numbers: [
      "── dart-orders (3 files, qwen3.5:latest) — Tier-progression at N=5 ──",
      "  Baseline (no retries):                2/5 (40%)",
      "  Tier 1 (retries+deps+contract):       3/5 (60%)",
      "  Tier 1 + #4 full-spec context:        3/5 (60%)",
      "  Tier 1 + #4 + temp ramp:              4/5 (80%)",
      "  Tier 1 + #4 + temp ramp + escalation: 5/5 (100%)",
      "── cpp-orders (1 file, std-lib only, qwen2.5-coder:32b) ──",
      "  Smoke + N=5: 6/6 (100%) · median Opus $0.26 · median wall 312s",
      "── python-inventory (9 files, qwen3.5:latest) ──",
      "  N=5: 5/5 (100%) — directional evidence that 9-file works in Python.",
      "── dart-inventory (9 files, 4-layer DAG) ──",
      "  qwen3.5:latest: 0/15 across cells (ceiling effect).",
      "  qwen2.5-coder:32b at 9-file Dart: 0/5 (ceiling holds with stronger executor).",
      "  Across all dart-inventory experiments: 0/35 — Dart-specific failure cluster.",
    ],
    constraints: [
      "Same Opus planner across all variants of a given benchmark; only the executor and orchestration tier change.",
      "Pre-written barrel for multi-file Dart is identical content across all variants.",
      "Grading uses real `dart test` / `g++` / `pytest` against hidden test files.",
    ],
    limitations: [
      "9-file Dart ceiling holds across both qwen3.5 and qwen2.5-coder:32b executors. Whether a much larger model (e.g. Llama 70B or a frontier model) breaks through is open. Python at 9 files works because qwen3.5 has higher rule-followingness in Python — see the cross-language map.",
      "Dart failure modes cluster: missing required getter (lineTotal, total), wrong arg-passing (named vs positional), const-constructor stripping. These are Dart idioms qwen consistently misses regardless of orchestration.",
      "Multi-file pipeline gating tests are a real source of brittleness — if any per-file gate fails, the chain stops and downstream files never get written.",
    ],
    calculations: [
      "dart-orders qwen3.5 progression (N=5/cell): 40% → 60% → 60% → 80% → 100% across the 5 tiers above.",
      "cpp-orders qwen2.5-coder:32b: 6/6 = 100%.",
      "python-inventory at 9 files (qwen3.5): 5/5 = 100%.",
      "dart-inventory cumulative across all bake-offs: 0/35 — published as a counter-example.",
    ],
    subtext: "3-file Dart: 100% · cpp single-file: 100% · 9-file Python: 100% · 9-file Dart: 0/35 (ceiling)",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-phaseC-inventory.md",
  },

  "phase-D": {
    phase: "PHASE D",
    status: "[ VALIDATED ]",
    headline:
      "The Opus-plans / qwen-executes asymmetric pipeline delivers parity quality on hidden test suites at 10-16× lower cost.",
    what: [
      "See `cost-15x` for full detail. Same data set.",
    ],
    numbers: [
      "state-machine: 5/5 trials, 21/21 each, $0.131 vs $2.06 (15.7× ratio).",
      "python-queue: 5/5 trials, 15/15 each, $0.186 vs $1.85 (10.0× ratio).",
      "Multi-task variant (decompose into 6+ atomic tasks per benchmark): 0-38% pass — the one-shot variant is the validated configuration.",
    ],
    constraints: [
      "Opus reads the README and writes the spec; qwen reads the spec and writes the code; hidden tests grade.",
      "qwen execution is local-Ollama, $0 marginal cost.",
    ],
    limitations: [
      "Two single-file Python benchmarks. Cross-language is being tested in Phase C (Dart, in progress).",
      "qwen3.5 is the executor. Cost ratio depends on qwen handling the language; weaker results expected on niche languages.",
    ],
    calculations: [
      "See `cost-15x` for full derivation. Same data set.",
      "Phase D AUTO state-machine: $2.06 / $0.131 = 15.7×.",
      "Phase D AUTO python-queue: $1.85 / $0.186 = 10.0×.",
      "Phase D multi-task variant (different configuration, same domain): pass rate dropped to 0/5, 8/21, 8/21 across 3 trials — published as a counter-example for the multi-task path.",
    ],
    subtext: "Phase D AUTO: 5/5 trials × 2 benchmarks → 21/21 + 15/15 → 15.7× and 10.0× cheaper",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-phaseD.md",
  },

  "phase-E": {
    phase: "PHASE E",
    status: "[ VALIDATED ]",
    headline: "Pre-edit hook lifts compliance on codebase-specific rules from 7-40% to 100%.",
    what: [
      "See `hook-93pp` for full detail.",
    ],
    numbers: [
      "Sonnet: 7% → 100% (lift +93pp).",
      "Haiku: 40% → 100% (lift +60pp).",
      "Opus: 100% → 100% (lift +0pp; Opus reads in-file context).",
    ],
    constraints: [
      "3 synthetic scenarios with codebase-specific rules contradicting Pythonic defaults.",
      "Trial-level A/B; only the hook config toggles.",
    ],
    limitations: [
      "3 scenarios in Python only. Multi-edit sessions, larger codebases, and non-Python untested.",
      "Cross-tier shows the hook's value scales inversely with model capacity.",
    ],
    calculations: [
      "See `hook-93pp`. Sonnet 1/15 → 15/15 = +93pp; Haiku 6/15 → 15/15 = +60pp; Opus 15/15 → 15/15 = 0pp.",
      "Cost overhead per Sonnet trial: avg(on) − avg(off) = $0.0714 − $0.0449 = +$0.0265.",
    ],
    subtext: "+93pp Sonnet · +60pp Haiku · +0pp Opus · ~$0.027/trial overhead",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-phaseE.md",
  },

  "phase-Escale": {
    phase: "PHASE E.SCALE",
    status: "[ VALIDATED ]",
    headline:
      "Hook latency stays constant at realistic codebase scale (100-500 files); compliance lift survives noise from neighboring requirements.",
    what: [
      "Synthetic projects with N handler files and M generic requirements (each linked to a random subset of files).",
      "One specific configuration requirement is then linked to the agent's target file.",
      "Measured: loom context latency (10 iterations) and same Phase E config_api compliance task.",
    ],
    numbers: [
      "100 files / 30 reqs (~100 implementations stored): loom context p50 = 800ms (+2.7ms over 1-impl baseline).",
      "500 files / 100 reqs (~300 implementations): p50 = 802ms (+8.8ms).",
      "Compliance: 0/3-5 → 3-5/3-5 across both scales — same lift as small-N Phase E.",
      "Onboarding seed time: 4.0s for 30 reqs, 13.5s for 100 reqs (linear, ~150ms/link, dominated by Ollama embedding).",
    ],
    constraints: [
      "Synthetic projects with template handlers; each generic req is linked to 2-5 random files at seed time.",
      "Latency measured with 10 fresh `loom context` calls per scale, p50 reported.",
    ],
    limitations: [
      "Synthetic project structure (uniform template handlers). Real codebases have heterogeneous file sizes and linking patterns.",
      "Sonnet only. Compliance survival at scale was not retested across all model tiers.",
    ],
    calculations: [
      "Latency p50 measurement: 10 fresh `loom context` invocations per scale; output piped through Python timing.",
      "1-impl baseline (newly-seeded store): p50 = 797ms.",
      "100 files / 30 reqs (~100 impls): p50 = 800ms. Delta = 800 − 797 = +2.7ms.",
      "500 files / 100 reqs (~300 impls): p50 = 802ms. Delta = +8.8ms.",
      "Latency dominated by Python startup + ChromaDB client init; metadata lookup itself is sub-10ms even at 300+ impls.",
      "Compliance: 100f/30r → 0/5 off, 5/5 on (same +93pp Sonnet lift). 500f/100r → 0/3 off, 3/3 on (smaller N due to time budget).",
      "Onboarding seed time per impl: ~150ms (Ollama embedding call dominates). 30 reqs × ~150ms ≈ 4.5s observed (4.0s actual).",
    ],
    subtext: "100/500 files: latency p50 800ms / 802ms (+3ms / +9ms over baseline) · compliance lift unchanged",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-phaseE.md",
  },

  "phase-F": {
    phase: "PHASE F",
    status: "[ FIXED + VALIDATED ]",
    headline:
      "File-content drift detection: stored-but-never-read content_hash field was wired into the consumption path; PreToolUse hook now surfaces real file drift.",
    what: [
      "Grep audit found `content_hash` had 6 write sites and 0 read sites in the codebase.",
      "services.check() and services.context() were extended to re-hash the file (or its linked range), compare against the stored hash, and surface drift in the `drift_detected` field.",
      "End-to-end smoke: link a file, modify it externally, re-fetch context — drift is now correctly reported.",
    ],
    numbers: [
      "Code change: ~30 LoC in src/services.py.",
      "Regression test added: tests/test_services.py::TestLink::test_content_drift_detected_after_external_edit.",
      "202/202 → 203/203 tests pass after the change (one prior test fixture was using a stub hash and needed updating).",
    ],
    constraints: [
      "Whole-file hash for impls linked to lines='all'; line-range hash for impls with explicit ranges.",
      "Hook code unchanged; it already consumed `drift_detected` so the new content-drift signal flows automatically.",
    ],
    limitations: [
      "Cross-platform line-ending issue: a CRLF↔LF normalization mismatch could produce false-positive drift. Not yet handled.",
      "Line-shift issue: an Implementation linked to lines 5-10 will produce false-positive drift when code is inserted above the linked range. Future work.",
      "We have no data on how often content drift actually appears in practice — usage data not collected yet.",
    ],
    calculations: [
      "grep audit before fix: `content_hash` had 6 write call sites and 0 read call sites.",
      "Code change diff: services.check() and services.context() each gained ~10 LoC for re-hash + compare.",
      "Test suite: 202 → 203 (one new regression test added).",
    ],
    subtext: "stored-but-never-read gap closed · regression test added · 203/203 tests pass",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-phaseF.md",
  },

  "phase-G": {
    phase: "PHASE G",
    status: "[ VALIDATED — Haiku ]",
    headline: "Loom's rationale field carries content the agent cites in its response. With true rationale, citation is 100%; with placebo of identical byte count, 13%.",
    what: [
      "See `citation-100` for full detail.",
    ],
    numbers: [
      "60 Haiku 4.5 trials across 4 cells × 3 scenarios. 0 errors. $1.84 / 15 min.",
      "Citation: rat 15/15 (100%); placebo 2/15 (13%); on-rule 0/15 (0%); off 1/15 (7%).",
      "Compliance: off 0% → on-rule 67% → placebo 73% → rat 93%. Net +26pp combined effect.",
    ],
    constraints: [
      "Same model (Haiku 4.5), same starter codebase, same task prompt across all 4 cells.",
      "Placebo cell injects bland filler of identical byte count (~520b) to the true rationale.",
    ],
    limitations: [
      "Haiku tier only on main. Sonnet replication exists on bakeoff-v1 sibling branch.",
      "3 synthetic scenarios with well-structured rationales (incident dates, ADR refs).",
      "Precondition (commit a2e5bf9) closed a silent rationale-dropping gap in services.context().",
    ],
    calculations: [
      "Citation per cell (15 trials each): off 1/15 (7%) · on-rule 0/15 (0%) · placebo 2/15 (13%) · rat 15/15 (100%).",
      "Compliance: off 0/15 → rule 10/15 (67%) → placebo 11/15 (73%) → rat 14/15 (93%).",
      "Decomposition: rule alone +67pp · placebo over rule +6pp (salience) · rat over placebo +20pp (content) · rat over rule +26pp combined.",
    ],
    subtext: "100% rationale-citation · 13% with byte-matched placebo · placebo-controlled isolation of content effect",
    repo: "https://github.com/jsuppe/loom/blob/main/experiments/bakeoff/FINDINGS-bakeoff-v2-phaseG.md",
  },
};
