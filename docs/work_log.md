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
