# Loom Work Log

A session-by-session narrative of significant decisions, pivots, and findings.
**Goal:** be able to track back to "what did we decide and why" without
re-reading the entire commit history or chat transcripts.

Complements (does not replace):
- **Git commit log** (`git log`) — what code changed, when
- **Loom store findings** (`loom list --kind finding`) — what we learned,
  with rationale + lifecycle status
- **experiments/bakeoff/FINDINGS-\*.md** — long-form experiment writeups
- **Driftgraph warrants** (`project=sparkeye` on the substrate) — what's been
  pushed as evidence
- **Auto-memory** at `~/.claude/projects/C--Users-jonsu-dev-loom/memory/` —
  durable preferences and project context for AI agent continuity

## Convention

One entry per significant working session, dated. Append-only — corrections
go in a follow-up entry, not edits. Each entry has:

- **What we did** — two or three bullets, the actual activity
- **What we decided** — the load-bearing decisions worth remembering
- **What's still open** — anything that's a thread to pick up
- **Pointers** — commit hashes, REQ IDs captured/refined, findings docs

Add notes like "session reset / new conversation" when the assistant context
breaks, since that's an important continuity marker.

---

## 2026-05-25 — M22c pilot — pre-reg gates stopped the sweep

### What we did

- **Continued the M22c arc from prior session** (session reset / new
  conversation). Resumed at M22c.2 (Dart workload scaffolding) after
  the compaction.
- **Built scenarios.json** — 3 service files (customer, inventory,
  order) for the dart-inventory benchmark with per-scenario
  hide_files + strip_from_files rules implementing the pre-reg's
  "hide contract" operational rule. Each style-rationale pre-graded
  leak-score 0.
- **Built m22c_pilot.py harness** — 4-arm runner (no_context /
  hook_rationale / hook_fact / placebo). Workspace setup applies
  hide-rules to a temp copy of the reference solution; grader
  re-adds shop_test.dart for testing (model never sees it).
  Captured 2 smoke-test fixes: `think:false` on Ollama (qwen3.5
  reasoning was consuming num_predict and producing empty
  response — same shape as M22a F3) + compile_fail priority
  over test_fail in the parser (Dart loader emits spurious "-1"
  for compile errors).
- **Ran the pilot N=24.** Resumed in ~4 minutes.
- **Pilot FAILED gates 2 + 6.** 0/24 trials compile-pass across all
  four arms. Even hook_fact (literal signature in prompt) compiles
  0%. McNemar Δ=+0.0pp p=1.00 for every paired comparison.

### What we decided

- **Sweep does NOT run.** Per the pre-reg's null-result pre-commit:
  the workload + grader + model combo floors below where any
  rationale-shaped signal could surface. Honest verdict: "this
  benchmark setup cannot measure the effect" — not "hook-rationale
  is ineffective."
- **Root cause = model-capability ceiling**, NOT hide-rule design.
  qwen3.5:latest (7B) writes correct-looking Dart but doesn't emit
  the right `import` statements even when given the method
  signatures verbatim. A redesign of hide-rules cannot fix this.
- **REQ-3896db58 (methodology pattern) earned its keep 6/6.** First
  time the pattern STOPPED a study before sweep cost was paid.
  Pre-reg gates paid for themselves on first use (~4 min of pilot
  caught what a full sweep would have missed at higher compute +
  much higher writeup cost).
- **Three pivot options surfaced (each requires a NEW pre-reg, not
  continuation of M22c):** (a) M22d model-arm pivot to a stronger
  executor, (b) M22e workload-simplification pivot, (c) accept
  refuted-via-floor and rest on M22a-regrade's engagement 4-bin
  signal that already produced loom-rationale's positive result
  ("proceeded with reasoning" 41% vs ≤6% other arms).
- **Pre-reg's anti-Texas-sharpshooter rule held.** Did NOT swap
  primary metric to LLM-judged 4-bin engagement when compile/test
  went against us. The pre-reg pre-committed against exactly this
  move; we honored it.

### What's still open

- **User decision on pivot path** (A/B/C above). No autonomous
  follow-up.
- M22d / M22e remain unscheduled until user picks direction.
- Lower-priority queue from earlier roadmap: M16.3 Python LSP
  indexer, M17.4 export formats, M18.4 Sonnet replication,
  M20.3 L4 productionization, M20.4 Driftgraph webhook activation,
  M19 real-world drift evaluation, M21 transcript-eval harness,
  M14.4 interactive triage loop, M15.4 hard-require `--reason` flip.

### Pointers

- **Commits:** `239b00a` (harness + scenarios), `82df6c3` (pre-reg
  from prior session)
- **Findings doc:** `experiments/bakeoff/m22c_pilot/M22C_PILOT_FINDINGS.md`
- **Pre-reg:** `experiments/bakeoff/m22c_pilot/M22C_PREREGISTRATION.md`
- **Trial summaries:** `experiments/bakeoff/runs-m22c-pilot/` (24 JSON
  + raw outputs)

---

## 2026-05-10 (evening) — Three-vendor × three-scenario cross-validation, paper draft

### What we did

- **Built generalized phY harness with scenario registry.** New
  `_scenarios.py` (S1_js + S2_py + S3_py with rules, rationales, paths,
  language config) and `phY_rule_precedence_smoke.py` (parameterized on
  scenario; supports JS Node grading and Python pytest grading; reuses
  call_ollama / call_claude pattern from phT). Added `R_imperative_pro`
  diagnostic cell to phT (imperative rule + V_FULL rationale) to isolate
  whether imperative formatting requires anti-rationale to manifest its
  effect.
- **Tier 1 reproducibility (Sonnet, S1_js).** Independent fresh N=20 on
  Sonnet's four key cells (R_imperative, R_meta_preamble,
  R_precedence_inline, placebo) — every cell reproduced exactly within
  sampling noise. Combined N=50: 0/50 on R_imperative, 50/50 on each of
  the other three cells. Sonnet's response on these prompts is
  functionally deterministic.
- **Tier 1 N=30 supplements (Qwen + Haiku + Sonnet, S1_js).** Tightened
  Wilson CIs on the four inversion cells. Headline numbers held except
  R_precedence_inline on Haiku (corrected from N=10 90% to N=30 70%).
- **Sonnet diagnostics on S1_js.** Three quick tests to isolate
  imperative-poison mechanism: phS V_full, phT R_baseline (independently),
  phT R_imperative_pro. Established that imperative formatting reduces
  Sonnet compliance even with pro-rationale (R_imperative_pro = 50% vs
  V_FULL alone 75%) — confirming the imperative effect is not purely
  about anti-rationale.
- **Cross-scenario sweeps on three models, three scenarios.** Built phY,
  ran Sonnet on S2_py + S3_py, Haiku on S2_py + S3_py, Qwen on S2_py +
  S3_py. ~840 trials across the cross-scenario arc (7 cells × 20 × 2
  scenarios × 3 models, minus minor counts).
- **Literature review on cross-model prompt sensitivity.** Khan (2025)
  "The Prompting Inversion" (arxiv 2510.22251) is the closest prior art
  — describes the same phenomenon in OpenAI models on math reasoning.
  Other adjacent work: Sclar 2023 (arxiv 2310.11324, formatting
  sensitivity), PromptSE 2025 (arxiv 2509.13680, cross-family
  stability), Compliance Trap 2026 (arxiv 2605.02398, frontier
  metacognitive collapse), POSIX 2024 (arxiv 2410.02185).
- **Paper draft.** `experiments/paper/draft.md` (518 lines, ~3500
  words) with full structure: abstract / intro / related work /
  methodology / results (4 findings) / discussion / conclusion /
  references / appendices.

### What we found

Cross-scenario results substantially **narrowed** the original
"imperative inverts on Sonnet" thesis but produced a **richer**
publication story with four cross-validated findings:

1. **Cross-vendor lever attendance generalizes across scenarios.**
   Where rescue is needed, Qwen rescues with imperative (100% on S1
   AND S2); Anthropic rescues with authority claims (meta-preamble
   87-100% across scenarios). Qwen does not respond to meta-preamble
   on S1 (0%) or S2 (5%). Sonnet does not respond to imperative on
   S1 (0%). Pattern is family-stable, not S1-specific.
2. **Anthropic rule-content × imperative interaction.** Imperative
   poisons Sonnet at 0% on S1 (anti-pattern rule), 30% on S2
   (defensible), 100% on S3 (defensible). Haiku shows same direction
   weaker. Qwen shows no such interaction (100% across all 3).
3. **Anti-rationale susceptibility is jointly model × scenario.**
   Anthropic ignores anti-rationale on defensible rules (100%); Qwen
   still corrupted (0% on S2).
4. **Shared implicit defensibility hierarchy** across vendors: all
   three rank S1 < S2 < S3 in compliance-resistance, suggesting
   substrate-level (training-data convergence) rule-legitimacy
   judgment that's independent of vendor-specific RLHF lever
   responses.

### What we decided

- **Publication framing**: extend Khan rather than claim novelty of
  the inversion phenomenon. Lead with cross-vendor lever attendance
  (Finding 1) + per-feature decomposition + cross-scenario rigor as
  the distinct contribution. Workshop / findings-track fit; possibly
  EMNLP findings.
- **Honest narrowing acceptable**: original "Sonnet imperative-poison"
  framing falsified across scenarios but the rule-content interaction
  mechanism that emerged is more interesting and publishable.
- **Tier 2 work to consider before submission**: Opus replication
  (~30-60 min, single missing tier in Anthropic family); raw API
  replication (~$5, addresses CLI-context confound); one additional
  Qwen size (within-Qwen-family generalization).

### What's still open

- **Tier 2 validation work** (Opus, raw API, Qwen variants) — your
  call on which.
- **Paper review pass** — draft is ready for honest read-through.
- **CLAUDE.md / hook prompt audit** for imperative-only formulations
  that may be at risk of inversion (mentioned in §5.4 of the draft as
  a Loom-side action item).

### Pointers

- Commits: this commit (data + draft + work_log) + previous commit
  (code: phY harness + R_imperative_pro cell).
- New code:
  - `experiments/bakeoff/v2_driver/_scenarios.py` (scenario registry)
  - `experiments/bakeoff/v2_driver/phY_rule_precedence_smoke.py` (generalized harness)
  - `experiments/bakeoff/v2_driver/phT_rule_precedence_smoke.py` (R_imperative_pro cell added)
- Paper draft: `experiments/paper/draft.md`
- Trial data: ~1260 new JSONs in `experiments/bakeoff/runs-v2/phY_*` and
  `phR_/phS_/phT_*_run{>10}_summary.json` from the N=30 supplements,
  reproducibility, diagnostics, and cross-scenario sweeps.

---

## 2026-05-10 (later) — Cross-model rationale arc landed: mirror-image picture

### What we did

- Ran the full cross-model rationale arc on `claude-haiku-4-5-20251001`
  via Claude Code CLI shell-out (Max plan auth). Four sweeps, 230
  trials, ~75 min total wall (faster than the 3.2hr estimate due to
  system-prompt caching).
- Updated all four FINDINGS docs with actual cross-model numbers and
  the synthesized framing.

### Cross-model results (final)

| phase | original Qwen finding | Haiku replication | verdict |
|---|---|---|---|
| **phS** anti-rationale | core: anti-rationale beats rule (0%); sub: ANTI_HARD has 15% retention | core: replicates (0%); sub: falsified (ANTI_HARD also 0%) | **partial — core survives** |
| **phR** reframe load-bearing | V_no_reframe drops 20pp; specific feature matters | V_no_reframe = 100%; no feature is load-bearing | **falsified** |
| **phT** rule precedence | R_imperative 100%, R_meta_preamble 0% | R_imperative 10%, R_meta_preamble 80% | **inverts** |
| **phU** L9 decomposition | each L9 component ~60pp alone | components 0-20% alone; full+meta still 100% but meta carries the lift | **falsifies decomposition; combo replicates for different reason** |

### What we decided

- **Cross-model Lesson 9 v3 needs to be model-aware.** Qwen-family
  attends to imperative register (capitalized absolutes, "MUST NOT");
  Anthropic-family attends to authority claims (inline "this rule
  overrides any rationale" or top-of-prompt meta-preamble). The
  portable Loom rule kit needs BOTH — strip either lever and one
  population loses 70-100pp of compliance lift.
- **Higher placebo floor on Haiku** (60% vs Qwen 30%) means
  rhetorical-feature ablations have ~half the dynamic range. The
  Qwen "reframe is load-bearing" finding is not measurable on Haiku
  not because reframe doesn't matter but because the floor is too
  high for any single feature to be detectable in 30pp range.
- **Production drift-warning text (M13.7d v3)** uses scope-qualifier
  language — primarily an authority-claim. The phT data predicts v3
  should work even better on Anthropic models than on the Qwen it
  was tuned against. Worth re-running M13.7e on Haiku to confirm.

### What's still open

- **Sonnet replication** — still pending. Haiku is one Anthropic data
  point; Sonnet would test whether the "Anthropic attends to authority
  claims, not register" pattern holds across the Anthropic tier
  spectrum.
- **M13.7e Haiku counterfactual** — back on the table. Now a high-value
  test given v3's authority-claim shape predicts strong Anthropic
  performance.
- **Loom prompt-engineering doc updates** — Lessons 1 and 9 need v3
  rewrites with cross-model framing. The current docs frame these as
  universal; they're not.
- **CLAUDE.md / hook prompt audit** — existing structured-rule injection
  in Loom's CLAUDE.md is largely Qwen-tuned. Cross-population auditing
  pass would surface where authority-claim text is missing.

### Pointers

- Commits: `4846418` README pass; `2efcfee` harness ports + work_log
  entry; this commit FINDINGS docs + work_log update.
- Cross-model trial summaries: `runs-v2/ph{R,S,T,U}_s1_js_claude-haiku-4-5-20251001_*_run*_summary.json`
  (230 files).
- Sweep logs: `runs-v2/ph{R,S,T,U}_haiku_sweep.log`.
- Updated findings docs:
  - `FINDINGS-bakeoff-v2-anti-rationale.md` (phS — partial replication)
  - `FINDINGS-bakeoff-v2-rhetorical-ablation.md` (phR — falsified)
  - `FINDINGS-bakeoff-v2-rule-precedence.md` (phT — inverted)
  - `FINDINGS-bakeoff-v2-imperative-followups.md` (phU — falsified decomposition)

---

## 2026-05-10 — README pass + cross-model rationale arc port (Max via CLI)

*[Assistant context reset partway through; resumed from summary.]*

### What we did

- **Documentation pass on README.md** — extended "What Loom does" from
  7 to 10 bullets covering M11.5 intake hook, M12 research-mode kinds,
  M10 semantic indexers, and M13 Driftgraph integration. Added a
  "Headline finding 3" subsection with the locked m13_v1 result table
  (v3: 100% recall / 12% FPR / F1 0.965) and Wilson 95% CIs. Added 6
  Features bullets (research mode, intake hook, rationale tracking,
  semantic indexers, Driftgraph integration, drift-warning eval
  harness). Extended the Commands table with `related`,
  `needs-rationale`, `intake`, `intake-stats`, `audit-rationale`,
  `indexer-doctor`. Fixed the stale "ChromaDB" reference in the
  D2 vs D3 callout.
- **Synced GitHub repo description + topics.** New description: "🧵
  Semantic traceability + research-mode capture for AI-assisted
  development. Extract requirements & findings, link to code, detect
  drift, drive small-model execution." Dropped `chromadb` topic
  (factually wrong since M3); added `sqlite`, `claude-code`,
  `drift-detection`, `small-model-execution`, `research-mode`.
- **Ported phR / phS / phT / phU rationale-arc harnesses to support
  the Claude CLI.** Each now has a `call_claude()` shell-out alongside
  the existing `call_ollama()` plus a `_call_model()` dispatcher that
  picks based on the `EXEC_MODEL` env var prefix. Pattern adapted
  from `phG_rationale_smoke.py`. Uses `--tools ""` and a minimal
  `--system-prompt` override from a clean tempdir cwd to avoid
  inheriting the loom project's CLAUDE.md / tool loadout (~8k tokens
  baseline overhead remains; ~33-45k baseline if not overridden).
- **Patched output-filename pattern** to embed model name for
  non-Qwen runs. Original `phS_s1_js_<cell>_run<N>_summary.json`
  paths preserved for the canonical Qwen baselines; cross-model runs
  land at `phS_s1_js_<model>_<cell>_run<N>_summary.json` so they
  coexist without clobbering. Caught the clobber issue mid-flight
  on the first sweep attempt — restored 6 V_full Qwen baseline
  files from git before they were lost.

### What we decided

- **User runs cross-model on Max plan, not API key.** API would have
  been ~$1 for the rationale arc, ~$5-10 for M13.7e counterfactual,
  but Max is included in the existing subscription. Trade-off: Claude
  CLI shell-out is 7-8x slower per call due to startup + cached system
  context, vs ~$0 marginal cost.
- **Honest ceiling on cross-model claim.** All four rationale-arc
  findings (phR reframe, phS anti-rationale corrosion, phT R_imperative
  override, phU L9 decomposition) were `qwen2.5-coder:32b`-only. Per
  the existing FINDINGS docs, every one of them flags "Anthropic
  Haiku / Sonnet / GPT-4 may show different feature priorities." This
  cross-model run on Haiku 4.5 is the missing replication.
- **Two commits.** README pass + GitHub sync as one bundle (the
  documentation work). Harness ports + work_log entry as a separate
  bundle (the methodology work).

### What's still open

- **Cross-model sweep itself** — phS / phU / phT / phR queued (smallest-
  to-largest order per user request). Estimated total wall time ~3.2
  hrs across all four phases. Will land at
  `experiments/bakeoff/runs-v2/ph*_s1_js_claude-haiku-*_*.json`.
- **FINDINGS doc updates** — once cross-model results land, the four
  rationale-arc findings docs will need a "Cross-model replication"
  subsection. If Haiku confirms the pattern → universality claim
  strengthens. If Haiku diverges (e.g. handles equivocation better)
  → findings stay Qwen-specific and we update framing accordingly.
- **Sonnet replication** — Haiku gives one Anthropic data point; a
  Sonnet replication would add a third tier. Higher confidence,
  longer wall time (~5x).
- **M13.7e Haiku counterfactual** — on hold per cost/time tradeoff.
  ~2.7k Haiku calls would be heavy on Max (~30-90 min CLI overhead
  alone, possible rate-limit pressure). API key would be the better
  path for that one if/when added later.

### Pointers

- Commits: `4846418` README pass + GitHub sync; this commit harness
  ports + work_log entry.
- Modified harnesses: `phR_rhetorical_ablation_smoke.py`,
  `phS_anti_rationale_smoke.py`, `phT_rule_precedence_smoke.py`,
  `phU_imperative_followups_smoke.py` — each ~80 lines added for
  `call_claude` / `_call_model` plus the filename patch.
- Reference pattern: `experiments/bakeoff/v2_driver/phG_rationale_smoke.py`
  (the original Anthropic shell-out, dating from M13 outbound work).
- Findings captured: REQ-c0907768 (intake-hook capture of the
  "use Max for rationale arc replication" decision).

---

## 2026-05-07 (late) — Established work-log + memory protocol

### What we did

- User asked whether we maintain a work log beyond repo state.
  Honest answer: no narrative session-spanning log; only typed
  memory entries (`feedback_*.md`), the loom store (findings),
  operational JSONL logs, ephemeral task output.
- Built both:
  1. `docs/work_log.md` (this file) — canonical, in git, append-only
  2. `~/.claude/projects/.../memory/project_work_log_pointer.md` —
     auto-memory entry telling future-me to read the log on session
     start

### What we decided

- **Convention** (in this file's preamble): append-only,
  date-headed, "what we did / decided / what's still open / pointers."
- **Memory entry as pointer, not duplicate.** The log itself is
  canonical; memory just tells future agents where to find it.
- **Read recent 1-2 entries on session start** for cold-context
  recovery (per the memory entry's instruction).
- Backfilled five prior session arcs (2026-05-02 through
  2026-05-07) so the log has continuity from M12 ship through
  M13.7e counterfactual.

### What's still open

- Whether to commit `docs/work_log.md` immediately or wait for
  user direction. Per the user's "track back on previous
  information or decisions" framing, committing makes sense —
  what's the point of a log not in git history.

### Pointers

- New file: `docs/work_log.md`
- New memory: `~/.claude/projects/C--Users-jonsu-dev-loom/memory/project_work_log_pointer.md`
- Updated: `~/.claude/projects/.../memory/MEMORY.md` (added pointer line)
- No commits yet (pending user direction)

---

## 2026-05-07 (afternoon) — Response file drafted for Driftgraph dev

### What we did

- Drafted a substantive response to the Driftgraph dev's methodology
  pushback on M13.7d. Saved to
  `experiments/pilot/m13_response_to_driftgraph_2026-05-07.md`.
  Covers all three batches of methodology engagement work
  (counterfactual ablation, hand-label spot-check, latency
  comparison) plus Wilson CI re-framing of v3's metrics, the
  updated A/B/C production recommendation, and the substrate-side
  HTTP 500 observation.
- Established file-based message exchange convention: both devs
  share the same machine's filesystem, so messages go via shared
  paths rather than chat copy/paste. Drop a markdown file at
  `experiments/pilot/<name>.md`, share the path via chat.

### What we decided

- **Response files don't go in git** — they're correspondence,
  not artifacts. The findings, harnesses, eval results, and
  summaries that BACK the response stay in git per the
  findings-retention rule (REQ-c0e06e44); the message itself
  doesn't.
- **Production warning choice (A=v3 / B=bare_rule / C=no_warning)
  is on hold** until the Driftgraph dev reads the response. v3
  remains in production unchanged.
- The response file format is structured by section: methodology
  results table, Wilson CI re-framing, updated production
  recommendation, substrate-side observations, Loom-side TODOs,
  open questions.

### What's still open

- Same as the methodology entry: awaiting Driftgraph dev's read
  on the response file.

### Pointers

- New file (loose, NOT in git per decision): `experiments/pilot/m13_response_to_driftgraph_2026-05-07.md`
- No commits

---

## 2026-05-07 — Methodology pushback engagement (M13.7e counterfactual)

### What we did

- Drafted a response to Driftgraph dev's substantive methodology pushback
  on the M13.7d v3-scope-qualifier result. Saved to
  `experiments/pilot/m13_response_to_driftgraph_2026-05-07.md`
  (loose, not in git per user direction; both devs share the filesystem).
- Established workflow: file-based message exchange between Loom dev and
  Driftgraph dev via shared filesystem paths, since they share the same
  host machine.
- Built three variants of methodology engagement in parallel:
  1. **Counterfactual prompt ablation** (8 conditions × 170 scenarios on
     m13_v1; 45 min wall time on qwen3.5/temp=0)
  2. **Hand-label spot-check** of 17 scenarios (5 known-ambiguous + 12
     random with seed=42); 94% agreement with LLM labeler
  3. **Latency / token comparison** across 8 warning variants

### What we decided

- **L9 pattern transfer claim is falsified.** Counterfactual showed:
  - v2 (L9 imperative without scope) is the OUTLIER among warning-bearing
    variants at 48% FPR; vs `bare_rule` at 20%, `no_warning` at 18%
  - All four simpler alternatives (bare_rule, conditional, descriptive,
    ask_back) match v3's F1 within 3-5pp
  - v3's marginal win is mostly cleaning up v2's specific over-firing,
    not L9 transfer
  - REQ-5b784ced (the v3-as-L9-transfer finding) status downgraded to
    `refined`; new finding REQ-7ed1bdd2 captures the falsification
- **v3 is +35% prompt length over v2** — measured ~530 vs 393 estimated
  tokens. Real latency cost on PreToolUse hot path (~3 sec added per
  edit at qwen3.5).
- **m13_v1 labels stand.** Hand-label spot-check showed 4 of 5 ambiguous
  cases were labeler-correct and generator-confused (internally
  inconsistent scenarios), not labeling bias.
- **Production warning choice is now a real tradeoff** between v3 (best
  F1, +35% latency), `bare_rule` (3pp F1 sacrifice, -27% latency), and
  `no_warning` (2pp F1 sacrifice, -31% latency). Lean B or C in
  production but holding pending dev's read.

### What's still open

- **Production warning choice** — A (v3) / B (bare_rule) / C (no_warning).
  Awaiting Driftgraph dev's read on the response file.
- **Cross-model replication** — blocked on Anthropic API key. v3 (and
  the L9-falsification finding) is qwen3.5-only at temp=0.
- **HTTP 500 on warrant push** for REQ-7ed1bdd2 — substrate-side issue;
  flagged in the response file.
- **Documentation pass** — apply Wilson CIs to m13_v1 README + M13.7d
  findings doc; will do regardless of dev's response.

### Pointers

- **Findings captured today** (all kind=finding):
  - REQ-7ed1bdd2 (counterfactual ablation falsifies L9 transfer; toulmin@v1=1.0; Driftgraph push failed HTTP 500, locally captured)
  - REQ-f539e598 (94% labeler-agreement spot-check + +35% v3 latency cost; toulmin@v1=1.0)
- **Refined**:
  - REQ-5b784ced (v3-as-L9-transfer claim — narrative empirically wrong)
- **Result files**: `experiments/bakeoff/runs-v3/eval_m13_v1_ollama_qwen3.5_latest_counterfactual-{variant}.json` × 8
- **No commits today** (response file is loose; production code unchanged)

---

## 2026-05-06 — Synthetic eval set + production v3 (M13.7 + M13.7d)

### What we did

- Locked **m13_v1** evaluation set at 170 scenarios across all 21
  (stratum × edit_type) cells, each n≥5. Curated via 100-scenario M13.7
  pilot + 70-scenario targeted augmentation (`m13_eval_curate.py`).
- Built four-tool eval lifecycle: `m13_eval_curate` / `m13_eval_lock` /
  `m13_eval_runner` / `m13_eval_compare`. Eval set is now a persistent
  regression suite usable across model/prompt iterations.
- Pinned v2 baseline: TP=68 FP=23 FN=0 TN=74, F1=0.855, fp_trap
  drift_pause=48% (worse than the n=100 read had suggested — earlier
  result was concentrated in 2 edit_types).
- M13.7d: tried v3 scope-qualifier prompt (Proposal 1 from the
  deficiency analysis). **Result: F1=0.965, fp_trap=12%, recall=100%**.
  All three acceptance criteria cleared.
- Shipped v3 to production (`src/loom/services.py::context()`).

### What we decided

- The "fp_trap" stratum (drift in context, edit unrelated) is the
  load-bearing FPR test. m13_v1 stratifies it explicitly.
- The v3 scope-qualifier addition (positive/negative scope listing
  what the warning applies / doesn't apply to) was the right Proposal 1
  fix at the time. Note: M13.7e (next day) showed the L9-transfer
  framing was overstated — the scope qualifier is doing most of the
  work, not the L9 imperative.
- **Acceptance criteria pinned in `m13_eval_compare.py`**:
  recall floor ≥95%, no_drift FPR ceiling ≤5%, fp_trap FPR target ≤25%,
  per-cell regression ≥10pp.
- Eval-set versioning policy: v1.0 (current), v1.1 (Anthropic Haiku as
  second labeler), v1.2 (Haiku-generated scenarios), v2.0 (human-curated
  real-world).

### What's still open

- Methodology pushback from Driftgraph dev on the L9-transfer framing
  (engaged on the next day).
- Cross-model replication (Haiku) blocked on API key.

### Pointers

- **Commits**: `3cf39e8` (eval set + harness lock), `ff5242f` (v3 ship)
- **Findings**: REQ-c89637cc (m13_v1 baseline, FPR=48%), REQ-5b784ced
  (v3-as-L9-transfer — later refined)
- **Files**: `experiments/bakeoff/eval_sets/m13_v1/` (locked dataset +
  pinned baselines), `experiments/bakeoff/v3_driver/m13_eval_*.py`
  (4 lifecycle tools), `experiments/bakeoff/FINDINGS-bakeoff-v3-scope-qualifier.md`

---

## 2026-05-05 — Self-supersede demo + M13 status check

### What we did

- Demonstrated the full M13 inbound→outbound→inbound loop
  self-referentially. Pushed REQ-5bc9a36f and REQ-c0b0a242 (chained
  rationale_links). Wired BECAUSE_OF edges substrate-side via direct
  Cypher (since auto-extraction doesn't fire from rationale text).
  Ran `loom supersede REQ-5bc9a36f` with `LOOM_WARRANTS_AUTO_RETRACT=1`;
  cascade retracted 9/10; foundation_drift fired on REQ-c0b0a242's
  claims; loom context produced the v2 imperative warning text on the
  descendant finding.
- Patched `services.context()` ancestor enrichment + dedupe (M13.5e v0.1)
  — was rendering 3 bare claim_ids; now shows 1 line with subject text.
- Engaged with the user's "does it work?" directness — admitted M13
  was a soft nudge, ran the M13.6c evidence-dependent ablation that
  revealed 33pp soft-nudge effect (not behavioral guardrail), then
  ran M13.6d which showed the L9-imperative pattern lifts pause to 100%.
- M13.6d shipped v2 imperative warning to production.

### What we decided

- **M13's drift signal works at the comprehension layer** but had
  limited behavioral effect under v1 generic warning (33pp).
- **L9 imperative pattern (REQ-a636de03) seemed to transfer** —
  M13.6d gave 100% pause / 0% bake-in on hand-crafted tasks. (Later
  M13.7e counterfactual showed this framing was incomplete.)
- The end-to-end cascade demo proved the full pipeline works: cache
  → context → hook → reminder → agent. Substrate's foundation-drift
  detector fires correctly when ancestors are retracted.

### What's still open

- The "soft nudge" v1 finding (REQ-5bc9a36f) was superseded by the
  v2 imperative finding (REQ-c0b0a242).
- Hand-crafted tasks ≠ representative distribution. Synthetic eval
  proposed for next session.

### Pointers

- **Commits**: `99205c6` (M13.5e v0.1 enrichment), `ea98bf7` (M13.6d v2
  imperative warning shipped)
- **Findings**: REQ-7b40fdd8 (self-referential demo), REQ-c0b0a242
  (v2 guardrail confirmed on hand-crafted tasks), REQ-5bc9a36f
  (v1 soft nudge — superseded), REQ-e33f06c1 (acknowledgement-layer
  works)

---

## 2026-05-04 — M13 inbound channel architecture

### What we did

- Started M13.5 inbound channel (Driftgraph → Loom signal). Built three
  paths: cache (M13.5d webhook receiver + JSONL log), HTTP read API
  (M13.5e against substrate's Phase 13.5 routes), in-process Cypher
  fallback (M13.5b/Architecture B).
- `services.context()` priority order: cache → HTTP → Cypher → no signal.
  `graph_drift_source` field surfaces which channel produced the result.
- Driftgraph dev shipped Phase 13.5 (read API: `GET /claims/<id>`,
  `POST /claims/lookup`, `GET /projects/<n>/foundation-drift`) +
  Phase 13.5b (push webhook with `loom_drift_webhook` config in
  projects.yaml). Loom-side wired both.
- Built `hooks/loom_drift_webhook.py` — stdlib HTTP receiver, HMAC-
  verified, persists events to `<data_dir>/.driftgraph-cache.jsonl`.
- Updated cache event-name handling for substrate's actual event
  kinds (`claim_invalidated`, `claim_superseded`,
  `foundation_drift_detected`).
- L4 partial: `loom warrant stats` rollup, latency capture in
  push_warrant, `record_push_failure` for failed pushes.

### What we decided

- **Architecture B (in-process import) was correct for v0** but the
  Driftgraph dev recommended Path C (HTTP) for the runtime path. We
  shipped both — B as a fallback when HTTP is unreachable, HTTP as the
  current runtime since the substrate webhook isn't activated yet.
- **The cache becomes the runtime when the webhook activates** — that's
  the optimal state. Currently HTTP is the active source per
  `graph_drift_source`.
- **Substrate's read API uses Bearer auth on GETs, HMAC-over-body on
  POST**. Same `LOOM_WEBHOOK_SECRET` for both directions.

### What's still open

- Substrate webhook activation in `projects.yaml` (commented out).
  Receiver is ready when dev wants to flip the switch.
- BECAUSE_OF auto-extraction from rationale text — substrate doesn't
  do it; `justifications` field on the warrants payload is the
  intended path. **Loom-side TODO**: wire `justifications` from
  Loom's `rationale_links` into `push_warrant`.
- Parent-subject enrichment in `/claims/<id>` response — minor;
  optional substrate-side change to save a round trip.

### Pointers

- **Commits**: `86788dd` (M13.5a-c), `e6e8416` (M13.5d cache + receiver),
  `6a3be06` (L4 partial: warrant stats + HTTP read API client),
  `7f25ecd` (M12.2b lifecycle states)
- Memory updates: none

---

## 2026-05-03 — M13 outbound + M12 dogfooding

### What we did

- Started M13 (Driftgraph integration) per PR #13's "Operationalizing
  the integration" section. Built outbound side: HMAC-authenticated
  HTTP client, Toulmin@v0 heuristic + Toulmin@v1 LLM-driven validator,
  Falsifiability@v1, claim-id tracking via `.warrants-log.jsonl`,
  `loom warrant push / retract / stats` CLI, supersede auto-cascade
  behind `LOOM_WARRANTS_AUTO_RETRACT=1`.
- L1 wire test passed: 3 real loom rationales pushed, 1 retraction.
- L2 evaluation: Toulmin@v1 N=20 cleared 0/5 false positives on canary
  + 31.6% pass rate on 19-rationale sample.
- L3a-c (claim-id tracking, `retract --req`, supersede cascade) all
  smoke-tested live on 4 real Loom captures.
- L3d Falsifiability@v1: 2nd validator; 0/5 canary FPs;
  cross-validator agreement matrix vs Toulmin@v1 showed 4 different
  cells (both pass / Toulmin only / Falsifiability only / neither).
- L3e Phase 1: synthetic foundation-drift demo via direct Cypher
  manipulation; loom context surfaced graph_drift_detected=True
  through HTTP path with v2 warning.
- M12 dogfooding closure: archived junk req, reclassified
  REQ-c0e06e44 to process_rule + REQ-73a0d7de to finding,
  captured 5 empirical findings + 1 process_rule, ran
  `loom sync` to populate FINDINGS.md / PROCESS-RULES.md.
- M12.7: doctor + metrics + health_score made kind-aware (no longer
  flag finding/process_rule domains as "non-standard"; coverage %
  scoped to kind=requirement).
- M12.7b/c: archived items leaking into per-kind doc generators —
  fixed.

### What we decided

- **Outbound first** before tackling inbound channel (M13.5).
- **Per the dev's L4 design**: log every push/retract/failure to
  `.warrants-log.jsonl` for stats + observability. Hot-path latency
  is captured via `_elapsed_ms` field.
- **Toulmin@v1 + Falsifiability@v1 are complementary, not redundant**
  (REQ-bdb1e667). The validators catch different failure modes.
- **M12 stack working end-to-end**: kind, per-kind renderers,
  classifier, evidences link type, lifecycle states, kind-aware
  metrics — all dogfooded against the loom store itself.

### What's still open at this point

- M13.5 inbound channel (substrate → loom) — design questions out
  to dev (Architecture A vs B vs C; cache/poll/push tradeoffs).
- The dogfooded loom store now has a chain of findings about M13's
  own design — next session: capture L1+L2 findings as kind=finding
  with derives_from chains.

### Pointers

- **Commits**: many — `15a2bb6` (L1), `72b3b0c` (L2), `5c29450`
  (L3a-c), `13bd3a7` (L3d), `8accfea` (M12 dogfooding), `0377db1`
  (M12.7), `8974546` (M12.7b)
- **Findings**: 8 captured (the M12 lessons + dogfooded patterns)
- **Files**: `src/loom/warrants.py` (HMAC client + 2 validators),
  `experiments/pilot/dogfood_m12.py`, `experiments/pilot/warrants_l*_*.py`

---

## 2026-05-02 and earlier — M12 (research mode) shipped

### What we did

- M12 milestone shipped: `kind` field (M12.1), per-kind renderers
  (M12.2), per-kind lifecycle states (M12.2b), stdin UTF-8 fix
  (M12.3), chain rationale traversal (M12.4), kind-aware classifier
  (M12.5), evidences link type (M12.6), kind-aware doctor/metrics
  (M12.7).
- Loom can now distinguish requirement / finding / methodology /
  hypothesis / process_rule, render them to separate docs
  (REQUIREMENTS.md / FINDINGS.md / METHODOLOGY.md / etc), validate
  per-kind status enums, route classifier output to the right kind.

### What we decided

- The M12 vision is "loom for research workflows, not just software
  development." Each kind has its own lifecycle and validity rules.
- Per-kind renderers are emitted only for kinds with active items —
  no empty `HYPOTHESES.md` if no hypotheses exist.

### Pointers

- See `git log --oneline` between `955a4d7` and `7f25ecd` for the
  full M12 commit chain.
- **Findings**: 12 captured (M12 dogfood, prompt-engineering lessons,
  process rules)

---

## Convention notes (referenced from `MEMORY.md`)

- **Append-only** — corrections via follow-up entry, not edit.
- **Date-headed** — one entry per significant working session.
- **No emojis in headings** unless explicitly requested.
- **REQ IDs are lifecycle markers** — note when a finding gets
  refined / superseded / archived in subsequent sessions.
- **Pointers section** — always include commit hashes for that
  session and the REQ IDs of findings captured/refined.
- **Add note when assistant context resets** (new conversation,
  session reset reminder, etc.) so the continuity break is visible.
