# Loom Roadmap

> **Catch-up note (2026-06-18):** Milestones M14–M32 below were
> back-filled in one pass after the roadmap drifted behind the commit
> log (it had stalled at M13). Each entry is terse by design — the
> authoritative detail lives in the per-experiment `FINDINGS.md` files
> under `experiments/`, the captured `kind=finding` requirements in the
> Loom store, and `docs/EFFECTIVENESS.md`. Reverse-chronological:
> newest first.

## Milestone 32: Verified Contract Card validation (IN FLIGHT — review-gated)

**Motivation.** M10.2-N10 (see M28-arc below) confirmed that one kind of
context reproducibly lifts C++ contrarian-rule compliance — but the
M10.2 carrier was *unverifiable fictional context* (call sites in files
that don't exist, an invented incident anchor). M31 designed the
**Verified Contract Card** pattern to keep that content shape while
constraining every citation to resolve against real code. M32 is the
falsifying experiment: does a *verified* card recover the M10.2 lift, or
was the effect specific to unfalsifiability?

- [x] **32.0 Pre-registration locked (draft).** `experiments/m32_verified_contract_card/PRE_REGISTRATION.md`.
      H1 (rat ≥ 30%, matching M10.2-N10's 40%), H2 (within ±15pp of
      M10.2), H3 STOP gate (off ≤ 20% — the card's contract section
      restates the rule descriptively, so an off-cell lift means the
      card substituted for the rule). Predictor's prior locked at ~50%
      confirm / ~40% refute / ~10% inconclusive.
- [x] **32.1 Scenario extension authored** (awaiting review-lock).
      `reference/backoff_loop.hpp` (BackoffError/BackoffLedger/BackoffLoop::run),
      `src/sync_worker.cpp` (SyncWorker::pull), `docs/ARCHITECTURE.md`
      (ADR-014). Both TUs compile clean under `-std=c++17 -Wall -Wextra`.
      Replaces M10.2's fictional callers with real ones.
- [x] **32.2 Locked card authored** (awaiting review-lock).
      `experiments/m32_verified_contract_card/locked_card.md` — every
      caller/type citation cross-checked against the extended scenario
      (caught + fixed a 3-line citation drift in the first draft, which
      validates the pattern's verifiability constraint pre-experiment).
- [ ] **32.3 Harness** (`m32_smoke.py` — clone of m28 + card block).
- [ ] **32.4 N=40 sweep + verdict.**

**Status:** blocked on user review of three items — H3 threshold
(20% vs 10%), scenario shape, card wording. Scenario + card sit
**uncommitted in the working tree** by design; a single LOCK commit
follows sign-off.

## Milestone 31: Verified Contract Card pattern (DONE)

Shipped the user-facing C++ prompting pattern derived from the M28-arc
findings. The four empirically load-bearing content categories
(explicit return+throw contract, caller-side assumption narration,
decision-history anchor, type/identity references) structured into a
card whose every reference Loom can verify against the codebase.

- [x] **31.0** REQ-8c890e85 refined (5 acceptance criteria) +
      `proposed → adopted`.
- [x] **31.1** `docs/patterns/VERIFIED_CONTRACT_CARD.md` — card
      structure, per-field verifiability rules, worked example,
      enforcement design (clangd cross-check + `loom doctor`), Loom
      entity mapping, when-to-use / when-not.
- [x] **31.2** `PAT-c1e17beb` captured as a queryable Pattern row.

`loom contract <symbol>` CLI is design-only; cards are authorable today
via existing Specification CLI. Outcome validation is M32.

## Milestone 30: Token-efficiency tracking (DONE)

`experiments/_meta/token_efficiency_rollup.py` walks every per-trial
JSON under `experiments/bakeoff/runs-*/` and computes mean input/output
tokens, pass rate (Wilson 95% CI), and **tokens-per-pass** by
(intervention, cell). `docs/EFFECTIVENESS.md` gained a "Token-efficiency
frontier" section. Surfaced what pass-rate tables hide: the qwen3.5
baseline was leaking ~7k output tokens/trial; M10.2 stub is the
Pareto-optimal point (2,740 tok/pass); M28/M29/M28v2 paid tokens for
zero passes. Generic — new interventions slot into the `SOURCES` list.

## Milestone 28: C++ semantic-context arc (DONE — all hypotheses falsified or reframed)

**Motivation.** C++ sat in the cross-language map's "weak" zone (M8.4).
M10.2's hand-curated stub indexer had shown a +40pp rationale-cell lift,
making semantic context the candidate lever. This arc tested whether a
*real, scalable* mechanism could replicate it. Methodology pattern
(REQ-3896db58) earned its keep across the whole arc — every step
pre-registered with a locked falsifier + predictor's prior.

- [x] **28.0–28.4 ClangdIndexer Phase 1.** Shipped `src/loom/indexers_cpp.py`
      (LSP-backed C/C++ indexer, mirrors JsIndexer, 22 tests) +
      `compile_commands.json` for the S1 scenario + clangd 22.1.7
      toolchain. N=40 sweep: **rat cell 0/10 — H1 REFUTED.** Real LSP
      structural facts do NOT replicate the stub. Finding REQ-2007b144.
- [x] **29 Style constraint (Phase A).** N=40 with an explicit C++17
      style block. **rat 0/10 — H1 REFUTED**, exactly as the locked
      predictor's prior predicted (the contrarian rule already pins the
      idiom, making the style block redundant). Finding REQ-e349a0ad.
- [x] **28v2 ClangdIndexer + LLM-summarized prose.** N=40. **rat 0/10 —
      H1 REFUTED**; predictor's prior (expected confirm) overturned.
      Re-reading the M10.2 stub revealed it references files that don't
      exist + an invented incident anchor. Finding REQ-b096c333.
- [x] **M10.2 replication at N=10.** Re-ran the *original* M10.2 stub at
      N=10 to test noise-vs-signal. **rat 4/10 = 40% (CI 17-69%) — H1
      CONFIRMS.** The M10.2 effect is real and reproducible — but its
      carrier is unverifiable fictional context. Mechanism:
      qwen2.5-coder:32b treats plausibly-shaped unverifiable context as
      authoritative. Not a deployable Loom feature; a finding about LLM
      plausibility-vs-verifiability weighting. Finding REQ-c38ea918.

**Net:** C++ stays **weak** in `docs/EFFECTIVENESS.md` (honest-null
entries #4–#7). No scalable C++ S1 mechanism demonstrated. M31/M32
pursue the verifiable-equivalent question. Methodology pattern: 9/9.

## Milestone 26: Loom-builds-Loom dogfooding pilot (DONE — pipeline gaps captured)

First attempt to use `loom decompose` + `loom_exec` to ship a real
feature (the spec-quality scorer, REQ-6dec889f / SPEC-85e02906) into
Loom's own source on a local model.

- [x] **26.0–26.5** Three-band calibration set (10 high / 21 mid /
      10 low specs) locked as pre-registration; grading test
      (`tests/test_spec_scoring.py`) committed before the scorer
      existed (α-mode: eval-as-grading-test).
- [x] **26.6–26.8** Decompose → `loom_exec --loop`. **Halted at
      dry-run** — surfaced 7 product gaps (F1–F7) before a single LLM
      call. Captured as findings.
- [x] **Q-path.** Shipped F1 (silent-fallback warning), F5
      (per-extension prompt+apply via `services.select_fence_and_mode`),
      F8 (no_code response logging) into production. F6 workaround
      (per-task smoke tests). Re-ran: **T1 (prompt file) SUCCEEDED**
      end-to-end on qwen3.5 — first real "Loom built Loom" artifact;
      T2 surfaced F9/F10 (decompose self-consistency + re-export
      awareness). Findings F1–F10 captured.

**Carry-over:** v2-readiness gap backlog (F2/F3/F4/F7/F9/F10) — a
coherent future sprint: decomposer repo-layout grounding, pre-reg file
protection, re-export-chain awareness.

## Milestone 25: Spec-required enforcement (DONE)

REQ-7df25683: requirements MUST link to implementations through a
Specification; direct Requirement→Implementation links forbidden.
`services.link()` raises on direct `satisfies` links without specs
(`_bypass_spec_check_for_tests` escape hatch for fixtures). `loom doctor`
gains a `legacy_direct_links` check. Migration tool LLM-generated 21
contract-style specs from existing impls; all 21 loom-self direct links
migrated. Tests in `tests/test_spec_required.py`.

## Milestone 24: Team-shareable export/import (DONE)

`loom export` writes `.loom/*.jsonl` (one file per kind, sorted by id,
canonical field order, LF newlines) into the repo as the team-shareable
canonical text; SQLite store stays per-developer in `$HOME`. `loom import`
materializes it with auto-embedding-rebuild. Embeddings + audit logs +
`Implementation.content` + `last_referenced` excluded by design.
Byte-deterministic round-trip. Format locked in
`docs/specs/M24_LOOM_EXPORT_FORMAT.md`. Default import errors on
local-only data; `--force`/`--merge` opt in.

## Milestone 23: Local web UI (DONE)

`loom ui -p <project>` — FastAPI + Jinja2 server on `localhost:8090`,
read-only HTML views for reqs/findings/specs/files + semantic search +
`/api/*` JSON mirrors. Opt-in via `pip install loom-cli[ui]`.
Server-rendered, no JS build, single-project per start, 127.0.0.1-bound.
(Bug fixed during dogfooding: spec views rendered `spec.value` — the
Specification field is `description`.)

## Milestone 22: Augmentation-effectiveness research arc (DONE)

Pre-registered studies of *what* the Loom payload actually changes in
agent behavior. M22a pilot (N=120, 4 arms) + 4-bin re-grade refined the
value-prop from "loom → more cautious" to **"loom → confident
scope-aware decisions"** (hook arm: 41% proceeded-with-reasoning vs ≤6%
controls). M22b killed pre-launch (sub-agent review caught 3 structural
confounds). M22c/M22e Dart/JS workload pivots — pilots ceiling-saturated,
sweeps not run. The 5-step methodology pattern (REQ-3896db58) was forged
and hardened here.

## Milestone 21 / 20 / 17 / 16 / 15 / 14: v1 hardening (DONE)

- **M20.1** `loom unlink` + supersession workflow closure (enumerate
  affected impls, suggest cleanup). Idempotent `loom sync`.
- **M17.1–.3** POSIX-relative impl paths (portable across machines) +
  slug aliases + unified kind-faceted traceability matrix.
- **M16 / M16.3** Trace line-range rendering (`path:42-87`,
  GitHub-permalink style) + PreToolUse hook auto-capture of edited
  ranges. **PyIndexer** — LSP-backed Python indexer via `pylsp`
  (28 tests).
- **M15** Requirement lifecycle wired to real signals: `loom link`
  bumps pending→in_progress; `loom verify` → implemented;
  `loom verify-stable --apply` → verified after N drift-free days.
  Strict transition graph with audit-log events per hop.
- **M14** Intake noise-pollution gap closed: four lexical screens
  (session-scoped / scenario-paste / tool-docs / speculation) +
  provisional capture + `loom triage`. Took dogfooded intake precision
  55% → 100% on the audit corpus.

## Milestone 19: Drift-detection precision eval (DONE)

v1 (100% precision but hash-trivial sample) → v2 (enriched links;
surfaced + fixed 3 production bugs: `_read_file_content` encoding,
`_ollama_embed` 4000-char truncation + empty-input guard) → v3
(hand-curated tight-link req-relevance study; **v3.4 hand-classification
+ v3.5 findings still open** — tasks #87/#88).

## Milestone 13: Driftgraph integration (v1.x — in flight)

**Motivation.** Per PR #13's "Operationalizing the integration:
Loom-side build plan", Loom integrates with Driftgraph (the
`jsuppe/sdr-graph-memory` substrate) as the warrant storage +
retrieval + drift-detection layer. Loom owns extraction +
philosophical validators (Toulmin, falsifiability, Hegelian);
Driftgraph owns storage + retrieval + drift mechanics. Loom is
the gatekeeper, Driftgraph is the warehouse.

- [x] **13.L1 Wire test (Toulmin@v0 heuristic).** New module
      `src/loom/warrants.py` with HMAC-authenticated HTTP client,
      `push_warrant` / `push_retraction`, secret loader (env →
      canonical `~/.driftgraph/loom-webhook-secret` → empty), and
      a 5-line Toulmin@v0 heuristic (length / justification keyword
      / sentence completeness). CLI: `loom warrant push <REQ-id>`
      and `loom warrant retract <claim_id>`. End-to-end smoke: 3
      real loom rationales pushed (3 episodes, 9 claim_ids), 1
      retraction (200 + supersedes_edges_written: 1). 18 tests in
      `tests/test_warrants.py` (Toulmin@v0 shape + HMAC signing +
      secret loader precedence). Substrate-side note flagged:
      the bash curl smoke in PR #13 fails on Git-Bash for
      Windows because `echo -n` doesn't suppress newlines reliably.
- [x] **13.L2 First real validator (Toulmin@v1 LLM-driven).**
      `toulmin_v1(rationale)` extracts the Toulmin shape (claim,
      data, warrant, qualifier, rebuttal) via the M11.5 model
      dispatch (Anthropic Haiku if `ANTHROPIC_API_KEY` set, else
      qwen3.5:latest via Ollama; override via
      `LOOM_TOULMIN_V1_MODEL`). Pass threshold = 0.75 (data +
      warrant + qualifier-OR-rebuttal). Acceptance per PR #13
      comment 2 — both gates cleared:
        * **Cut 1 — Canary 0/5 false positives** on the
          hand-curated `tests/data/toulmin_canary_v1.json`
          (placeholder, ungrounded claim, tautology, restated-
          what-as-why, and "because we wanted to"). All 5
          rejected with score=0.00.
        * **Cut 2 — Pass-rate band 30–60%** on a 19-rationale
          sample from the dogfooded loom store: 6/19 = 31.6%
          (just inside the lower edge). Bimodality ratio = 8.50
          (heavy weight at 0.0–0.25 and 0.75–1.00; ZERO entries
          in the muddled 0.25–0.5 middle bin) — qwen3.5 is
          confidently distinguishing, not hedging.
        * (Bonus, optional) Cut 3 alignment via Cypher — deferred.
      Live: 6 toulmin@v1 claims pushed to Driftgraph (6 episodes,
      18 claim_ids; in the 6–12 target).
      **Secondary finding captured as REQ-4d3e74f2** (kind=
      finding, status=confirmed): requirement-shaped rationales
      pass at ~5x the rate of finding-shaped rationales (55.6%
      vs 12.5%). The dogfooded findings are citation-shaped
      ("Source: harness.py + FINDINGS-X.md, N=10 per condition")
      — they CITE evidence but don't ARGUE warrant inline. This
      is a real signal about the loom rationale-capture
      conventions: when downstream Toulmin validation matters,
      capture inline argument, not just citation.
      Eval harness: `experiments/pilot/warrants_l2_eval.py`;
      results: `warrants_l2_results.json` +
      `warrants_l2_summary.md`. 2 new tests in
      `TestToulminV1Canary` (canary dataset exists, validator
      rejects 0/5).
- [x] **13.L3a Claim-id tracking** (warrants log JSONL sidecar).
      `<data_dir>/.warrants-log.jsonl` records every `push_warrant`
      and `push_retraction` call; `record_push` /
      `record_retraction` are best-effort (logging failures never
      break the network call). `lookup_active_claims_for_req`
      returns the most-recent-push claim_ids minus anything later
      retracted. `lookup_latest_push_for_req` returns the full
      record so callers can recover the `project_tag` used at push
      time (without this the L3c cascade defaulted to the loom
      project name and Driftgraph rejected with HTTP 404 'project
      unknown' — surfaced + fixed during dogfooding). 8 new tests
      in `TestWarrantsLog`.
- [x] **13.L3b `loom warrant retract --req REQ-id`.** Looks up
      every active claim for the req via the warrants log,
      retracts each, persists each retraction. Pulls
      `project_tag` from the original push record automatically.
      Smoke: pushed REQ-2a621c40 (11 claims), retracted by `--req`,
      11/11 succeeded; subsequent lookup returns empty.
- [x] **13.L3c `loom supersede` auto-cascade** (opt-in via
      `LOOM_WARRANTS_AUTO_RETRACT=1`). When the env flag is set
      and the superseded req has active Driftgraph claims, each
      gets retracted as a side-effect. Failures are warnings,
      never fatal — the supersede is what the user asked for.
      Smoke: pushed REQ-a521b281 (4 claims), `LOOM_WARRANTS_AUTO_
      RETRACT=1 loom supersede REQ-a521b281` triggered cascade,
      4/4 retracted with the right project_tag from the push
      record. Without the env flag the supersede runs untouched
      (verified). Behind the env flag rather than always-on
      because v0 wants explicit opt-in for cross-system
      side-effects.
- [x] **13.L3d Falsifiability@v1.** Second LLM-driven validator
      (Popperian falsifier extraction). Different prompt: "what
      observation would falsify this claim?" Passes if the
      rationale identifies (explicitly or implicitly) a falsifier
      — concrete condition, threshold, replication boundary, or
      rebuttal that would invalidate the claim. Same dispatch
      pattern as Toulmin@v1 (Anthropic Haiku if
      ANTHROPIC_API_KEY set, else qwen3.5; override via
      LOOM_FALSIFIABILITY_V1_MODEL).
      Acceptance: **0/5 false positives on canary**
      (`tests/data/falsifiability_canary_v1.json` — vague
      aspiration, placeholder, ungrounded confidence,
      subjective-no-test, subjective-no-threshold). All 5
      rejected with score=0.00 by qwen3.5.
      Sample (same 17 valid rationales as L2 minus the 2 that
      were superseded during L3c): pass rate 4/17 = 23.5%.
      Bimodality 3.25 (above 1.5 threshold; bin 0.5–0.75 is
      empty, bins 0–0.25 = 9 and 0.75–1.0 = 4).
      **Cross-validator matrix vs L2's Toulmin@v1** (the
      headline L3d finding):
        both pass:           2  (REQ-0a83d16a, REQ-a636de03)
        toulmin only:        1  (REQ-2a621c40 — well-argued but
                                 no falsifier)
        falsifiability only: 2  (REQ-5e01462c, REQ-a9df428e —
                                 measurable thresholds without
                                 inline argument)
        neither:            11
      The validators are **complementary, not redundant** — they
      catch different failure modes. A "fully warranted" claim
      needs BOTH gates, not OR. Captured as REQ-bdb1e667
      (kind=finding, status=confirmed).
      Live in Driftgraph: 4 falsifiability@v1 episodes (4 claim_ids
      written for the 4 passing rationales).
      Eval: `experiments/pilot/warrants_l3d_eval.py` →
      `warrants_l3d_results.json` + `warrants_l3d_summary.md`.
      2 new tests in `TestFalsifiabilityV1Canary` (canary exists,
      validator rejects 0/5 — both pass live).
- [ ] **13.L3e End-to-end retraction → foundation-drift demo.**
      The signal the Driftgraph dev wants: push parent + child
      warrants where child's rationale references parent's
      claim_id (creating BECAUSE_OF edge); retract parent;
      verify amber 🪨 foundation-drift indicator appears in
      `/why <topic>`. Captures as `experiments/pilot/
      warrants_l3_retraction_demo.py`.
- [-] **13.L4 Productionize.** Partial — observability shipped;
      retries/idempotency/secret-rotation still open.
      **Done:**
        * `loom warrant stats` CLI + `services.warrant_stats`
          rollup over `.warrants-log.jsonl`. Reports totals
          (pushes, retracts, failures, success rate),
          per-validator (count, score p50/p95, latency
          p50/p95/p99/max), per-project, retraction sources
          (manual / by_req / supersede_cascade), failure
          breakdown (by_kind, by_status, recent 5), and
          currently-active claim count. `--since N` and
          `--tail N` flags for windowed views.
        * `push_warrant` now stamps `_elapsed_ms` on responses
          + on `WarrantPushError` instances so callers can
          forward latency to the warrants log without timing
          the call themselves.
        * `record_push_failure` — new logger for failed pushes
          (HTTP 4xx/5xx, network errors, ValueError on missing
          secret). Without this, the warrants log was
          successes-only and stats couldn't compute success rate.
        * `record_push` / `record_retraction` gain optional
          `elapsed_ms` field; pre-L4 records (no elapsed_ms)
          are silently skipped from latency aggregates but
          still counted in totals.
        * 6 new tests in `TestWarrantStats`: empty log,
          push+retract aggregation, failure logging drops
          success rate, pre-L4 records skipped from latency,
          retraction-source classification, since_days window.
      **Empirical first read on the dogfooded loom store**
      (after 9 pushes + 22 retracts since L1):
        - toulmin@v1 latency p50=7456ms p95=7456ms (n=1; the
          rest predate the L4 instrumentation)
        - 100% push success rate after the bogus-project
          smoke (which we logged + cleaned up)
        - 18 by_req retractions + 4 supersede_cascade — the
          cascade is working as designed
      **Still open** for L4 completion:
        * Retries on transient failures (5xx, URLError) with
          exponential backoff
        * Idempotency — don't double-write if a retried push
          succeeded after we marked it failed (probably needs
          a substrate-side dedup_key; flag back to dev)
        * Secret rotation — graceful handling when the secret
          file changes mid-process
        * Push-success-rate alerting threshold (e.g. doctor
          warns when 24h success rate < 95%)
- [x] **13.5a-c Inbound channel — Driftgraph signals in
      `loom context` / PreToolUse hook (Architecture B).**
      v0 of the inbound channel; Loom now sees Driftgraph
      foundation-drift signals before edits, not just outbound
      warrant pushes. New `src/loom/driftgraph_query.py`:
        * Repo discovery (env var → `~/Downloads/grag` →
          `~/dev/grag` → `~/dev/sdr-graph-memory`)
        * In-process import of Driftgraph's `chains` module +
          `experiments.v03.schema.connect()` via sys.path
        * `is_available()` — True iff repo + Neo4j both reachable
          (graceful degrade everywhere else)
        * `find_drifted_ancestors_for_claim(project, claim_id)` —
          walks BECAUSE_OF up to 5 hops; surfaces any ancestor
          with `invalidated_at IS NOT NULL`
        * `find_drifted_ancestors_for_req(data_dir, req_id)` —
          looks up active claim_ids from .warrants-log.jsonl,
          queries each, returns
          `{drifted, claim_ids, drifted_ancestors, available}`
      services.context() additions:
        * `graph_drift_detected: bool` — top-level signal
        * `graph_drift: list` — per-req {req_id, drifted_ancestors}
        * each `requirements[i].graph_drifted` — per-req tag
        * `summary` appends "GRAPH-DRIFT on REQ-A, REQ-B"
      `loom context` CLI: per-req `🪨 graph-drift` tag + bottom
      "Foundation drift on Driftgraph" section enumerating
      drifted ancestors; exit code 2 on either local OR graph
      drift. PreToolUse hook: per-req `[GRAPH-DRIFT]` tag +
      "Driftgraph foundation-drift — upstream evidence moved"
      section; `LOOM_HOOK_BLOCK_ON_DRIFT=1` blocks on either.
      pyproject.toml: `[driftgraph]` extra (`neo4j>=5.0`).
      Without the extra, every public function in
      driftgraph_query degrades to "no signal" — agent gets
      M11.5/M12-era context as if M13.5 didn't exist.
      End-to-end smoke verified by manufacturing a synthetic
      drift case via direct Cypher (live → BECAUSE_OF →
      retracted), running `find_drifted_ancestors`, verifying
      it returns the drifted ancestor with hops=1, then
      cleaning up the synthetic edge.
      Tests: 15 in `test_driftgraph_query.py` — all use
      monkeypatched modules so no live Neo4j needed in CI.
      Architecture B trade-off: Loom imports from a sibling
      repo via sys.path hack. Migrating to a clean read API
      (Path C — substrate-side HTTP /claims/<id>) only swaps
      `_ensure_modules`; everything else stays.
      **One real substrate-side finding from this work:** zero
      of our currently-live Loom claims have BECAUSE_OF parents
      in the graph. Driftgraph isn't auto-extracting BECAUSE_OF
      edges from rationale text mentioning prior claim_ids;
      either claim-extraction post-processing doesn't catch
      this pattern, or the explicit `justifications` field in
      the warrant payload (per `warrants_endpoint.py` line 30)
      is the intended path. Worth flagging back to the
      Driftgraph dev — orthogonal to M13.5 itself but needed
      before the L3e end-to-end demo can produce real drift.
- [x] **13.5d Push-based cache + receiver (Loom-side).**
      Built per the dev's response on the 5 escalation
      questions: dev recommended skip-B-as-runtime, ship
      Path C (HTTP read API) + push webhook from substrate.
      Substrate-side work is in-flight on their PR; Loom-side
      shipped now so the receiver is ready when events start
      arriving.
        * `src/loom/driftgraph_cache.py` — local mirror of
          graph state. `record_event()` appends webhook payloads
          to `<data_dir>/.driftgraph-cache.jsonl` (verbatim +
          received_at). `compute_claim_state(claim_id)` replays
          the log to compute `{invalidated, foundation_drifted,
          drifted_ancestors}` per claim. `lookup_drifted_for_req`
          mirrors the M13.5b query API exactly so
          `services.context()` can swap implementations
          transparently.
        * `hooks/loom_drift_webhook.py` — stdlib `http.server`
          receiver. Listens on configurable port (default 8081
          / `LOOM_DRIFT_PORT`), exposes `GET /health` +
          `POST /drift-events`. Verifies HMAC-SHA256 via the
          same `LOOM_WEBHOOK_SECRET` as the outbound /warrants
          endpoint (substrate ↔ Loom symmetric). Refuses to
          start if no secret is configured. Filters events by
          project (so one substrate broadcasting to multiple
          Loom receivers doesn't pollute each other's caches).
          Stdlib-only on purpose — receiver is a v0 piece; no
          new deps.
        * `services.context()` priority order: cache (M13.5d)
          → in-process Cypher (M13.5b/Architecture B fallback)
          → no signal. New `graph_drift_source` field surfaces
          which channel produced the result (debug visibility).
        * Live smoke: started receiver locally, POSTed a
          synthetic foundation_drift event with valid HMAC,
          verified the event landed in
          `.driftgraph-cache.jsonl` with auto-stamped
          received_at, verified `compute_claim_state(...)`
          returned `foundation_drifted=True` for the dependent
          claim_id. Cleaned up the synthetic event afterward.
      **Architecture B kept in place as v0 fallback** rather
      than torn out. Two reasons: (1) zero-signal degradation
      when neither channel works is the right behavior, and B
      provides "neither channel" coverage for users without the
      receiver running yet; (2) `loom warrant cache-replay` /
      debug-drift CLI tools (future) can use it for emergency
      querying without spinning up the receiver. When the
      substrate's read API ships and the cache is mature, B can
      delete in a single commit.
      Tests: 19 new in `tests/test_driftgraph_cache.py` —
      record_event (creation, received_at handling, silent
      failure), has_cache (3 states), compute_claim_state
      (claim_invalidated, supersedes, foundation_drift,
      ancestor de-dupe, corrupt-line resilience),
      lookup_drifted_for_req (the no-cache → fallback path,
      cache-present-no-claims, cache-with-drift), receiver
      HMAC verification (correct sig, tampered body, missing
      prefix, empty secret).
- [-] **13.5e Substrate-side Phase 13.5 contract integration.**
      Driftgraph dev shipped Phase 13.5 (read API) + 13.5b (push
      webhook) in their PR — three new HTTP routes plus per-
      project `loom_drift_webhook` config. Loom-side updates:
        * **Cache event-name update** — substrate uses
          `claim_invalidated`, `claim_superseded`,
          `foundation_drift_detected`, `warrant_ingested` per
          `webhook_dispatcher.py`. `compute_claim_state` now
          handles all four (legacy `supersedes` and
          `foundation_drift` names retained for any pre-13.5b
          records). 2 new tests cover the new event names.
        * **HTTP read API client** — new
          `src/loom/driftgraph_http.py`:
            - `get_claim_status(project, claim_id)` — Bearer
              auth → claim row including `foundation_drifted`
              bool + `n_invalidated_parents`
            - `bulk_claim_lookup(project, claim_ids)` — HMAC
              over body, capped at 500 IDs (raises rather
              than silently truncating)
            - `list_foundation_drifted(project, limit)` —
              cold-start cache seeding
            - `is_available()` — probes `/health`
            - `find_drifted_ancestors_for_req(data_dir, req_id)`
              — same-shape convenience matching the cache + B
              wrappers so `services.context()` can swap.
          Bearer header is `Authorization: Bearer <secret>`
          with the same shared `LOOM_WEBHOOK_SECRET`. All
          functions degrade to None / no-signal on transport
          failure.
        * **services.context() priority order updated** —
          three paths now: cache (best) → HTTP read API
          (cold-start) → Cypher (Architecture B fallback,
          will eventually delete). `graph_drift_source`
          field exposes which channel produced the result
          ("cache" | "http" | "cypher" | None).
        * Live smoke against the running substrate:
          `is_available()=True`; `get_claim_status` /
          `bulk_claim_lookup` / `list_foundation_drifted` all
          return the expected shapes; the substrate's L3e
          smoke claim (`clm_90db5b107c6c41c6` with
          `validator_id=l3e-direct@v0`) shows
          `foundation_drifted=True` /
          `n_invalidated_parents=1` — verified end-to-end.
      Tests: 15 new in `test_driftgraph_http.py` + 2 added
      to `test_driftgraph_cache.py` for the new event names.
      All use mocked urllib so no live substrate needed in CI.
      **Still open:**
        - Run a fresh end-to-end demo against the real Phase 9
          machinery (push parent + child where child's
          rationale uses substrate `justifications` field to
          create a BECAUSE_OF edge; retract parent; verify the
          webhook fires; verify cache shows drift)
        - `loom warrants run-receiver` background-service
          examples (systemd / launchctl / Windows scheduled-
          task)
        - Document the env config + setup steps in README

## Milestone 12: Research mode (v1.x)

**Motivation.** Loom was designed for software-development workflows
(capture imperative requirements, link to code, detect drift). The
M10/M11 work doing prompt-engineering research surfaced a different
shape: capturing findings, methodology decisions, hypotheses, and
process rules. Dogfooding the M11 capture mechanism on the 9
prompt-engineering lessons surfaced 7 friction points spec'd in
[`docs/DESIGN-research-mode.md`](docs/DESIGN-research-mode.md).

### 12.1 Tasks

- [x] **12.3 stdin encoding fix.** Real bug: `loom extract` reading
      value text via stdin used the system locale (CP1252 on Windows),
      corrupting non-ASCII characters. An em-dash entered as 3 UTF-8
      bytes got read back as 3 separate CP1252 characters. Symptom:
      deterministic req_id silently changed, breaking downstream
      `loom link --req`. Fix: extend the existing stdout/stderr UTF-8
      reconfigure block to include stdin. 3 regression tests in
      `tests/test_cli_encoding.py`. Verified em-dash round-trip:
      predicted req_id matches stored req_id post-fix. (commit `10fc67d`)
- [x] **12.1 `Requirement.kind` field.** Typological generalization
      adding an optional `kind` field with values
      `requirement|finding|methodology|hypothesis|process_rule`.
      Default `"requirement"` preserves all existing data and behavior
      via `setdefault` in `from_dict`. New `VALID_KINDS` constant in
      `services.py` mirrors `VALID_STATUSES`. `services.extract` gains
      a `kind=` parameter with validation; new `services.set_kind`
      reclassifies an existing req. CLI: `loom extract --kind finding`,
      `loom list --kind finding` filter, kind tag surfaced in
      human-readable list output (`<finding>` etc, hidden when default).
      10 new tests in `TestExtract`. Foundation for M12.2/12.5/12.6.
- [x] **12.2 Per-kind renderers (filenames + framing).**
      `KIND_DOC_CONFIG` maps each kind to filename, title, intro
      text, and noun pluralization. `generate_requirements_doc`
      gains a `kind` parameter (default `"requirement"` for
      back-compat); the renderer filters to that kind, picks the
      kind-aware filename, and uses the kind-aware intro. The
      traceability matrix is skipped for non-requirement kinds
      (findings/methodology don't have specs/impls in the
      implementation sense). `services.sync` walks all 5 configured
      kinds; emits files only for kinds with at least one entry
      (no empty `PROCESS-RULES.md` if there are no process rules).
      Result shape gains `kind_paths` dict. Smoke-tested against a
      mixed-kind store: REQUIREMENTS.md / FINDINGS.md /
      METHODOLOGY.md all emitted with kind-appropriate framing.
      9 new tests (4 in TestDocGeneration, 3 in TestSync, +
      reuses 2 existing kind round-trip tests). Per-kind
      lifecycle states deferred as M12.2b (now done).
- [x] **12.2b Per-kind lifecycle states.** Each kind gets its
      own status enum (`VALID_STATUSES_BY_KIND`) reflecting its
      domain lifecycle, plus three universal terminal/debt
      states (`superseded`, `archived`, `rationale_needed`)
      accepted across all kinds:
        * `requirement` — pending → in_progress → implemented
          → verified  (preserved verbatim from M0)
        * `finding` — preliminary → confirmed | falsified |
          refined  (empirical-claim lifecycle)
        * `methodology` — proposed → adopted → deprecated
        * `hypothesis` — proposed → testing → confirmed |
          falsified
        * `process_rule` — proposed → active → deprecated
      `valid_statuses_for(kind)` is the public lookup;
      `services.set_status` and `services.refine` validate
      against the kind's enum (loading the req first to know
      its kind) with error messages that name the kind and
      list valid statuses. `store.set_requirement_status`
      gains the same per-kind validation (mirrored literal,
      synced to the services constant). `services.extract`
      uses `DEFAULT_STATUS_BY_KIND` for the initial status
      when rationale is provided — findings start
      `preliminary`, methodology/hypothesis/process_rule
      start `proposed`, requirements still start `pending`.
      When rationale is missing, all kinds still default to
      the universal `rationale_needed` debt marker. CLI
      `set-status` help text enumerates per-kind options.
      10 new tests in TestSetStatus (per-kind acceptance,
      cross-kind rejection, universal-state acceptance,
      kind-aware error message, helper, kind-aware initial
      status, rationale_needed universality).
      Drift-target hints per kind (the original M12.2b
      sub-item) are out of scope here — M12.6's evidences
      semantic already differentiates the most important
      drift surface (finding evidence vs. requirement
      implementation).
- [x] **12.4 `loom chain` traverses rationale_links.** Extended
      `services.chain` to walk the rationale-link DAG in both
      directions: `rationale_ancestors` (transitive parents — what
      this builds on) and `rationale_descendants` (transitive
      children — what builds on this). Both cycle-protected via
      visited set, depth-bounded at 20. Each node carries its
      `kind` (M12.1) so the chain shows the kind tag for each link.
      `loom chain` CLI gains "⬆️ BUILDS ON" and "⬇️ DERIVED FROM
      THIS" sections with depth-indented tree rendering. Smoke-
      tested on the dogfooded lessons store: `loom chain
      REQ-ec36bd89` (L1_rationale) shows L0_meta as ancestor and
      L7/L3/L8/L9 as direct descendants + L6 at depth 2 via L7.
      7 new tests in TestChain (10 total).
- [x] **12.5 Kind-aware classifier (intake hook).** Extended the
      M11.5 classifier prompt with definitions and examples for all
      five kinds (`requirement|finding|methodology|hypothesis|
      process_rule`); the classifier now emits `kind` alongside
      `is_requirement`. `parse_classifier_output` validates the
      kind against `_VALID_KINDS` and falls back to `"requirement"`
      on missing/invalid values, preserving M11.5 back-compat for
      models that don't know the field. `process_message`:
        * passes `kind` through both `services.extract` calls
        * skips auto-link for non-requirement kinds (the
          `derives_from` semantic is requirement-to-requirement;
          findings need M12.6's `evidences` link instead)
        * skips the propose branch for non-requirement kinds — they
          flow straight through to capture-with-rationale or
          rationale-needed
        * relaxes the `AUTO_CAPTURE_DOMAINS` whitelist for
          non-requirement kinds (findings legitimately use
          domains like `experimental`/`operational`)
        * propagates kind into the reminder text and intake-log
          record (`"Loom captured this finding as REQ-..."`).
      `services.intake_stats` gains a `by_kind` tally so users can
      see whether captures are landing in the right per-kind file or
      everything's still defaulting to requirement. `loom
      intake-stats` human output adds a "By kind (captured)"
      section. `loom intake` human output appends a `<kind>` tag
      when non-default. 12 new tests (5 parser, 6 process_message,
      1 intake_stats); all 30 pre-existing intake tests still pass
      with no modifications. Hand-labeled dataset extension
      deferred — the prompt is now structurally correct;
      calibration can be collected from real fires via `loom
      intake-stats --json` once the hook is registered.
- [x] **12.6 `evidences` link type alongside `satisfies`.**
      Each entry in `Implementation.satisfies` now carries a
      `link_type` of `"satisfies"` (this code IMPLEMENTS the
      requirement) or `"evidences"` (this file SUPPORTS a
      finding/hypothesis — drift means the empirical claim should
      be re-evaluated, not that an implementation regressed).
      `services.link()` gains a `link_type` parameter:
        * Explicit value (`"satisfies"` | `"evidences"`) forces
          the type for all req links in the call.
        * `None` (default) auto-detects per-req from the
          requirement's kind: `finding` / `hypothesis` →
          `"evidences"`; everything else → `"satisfies"`.
        * Spec-derived parent links are always `"satisfies"`
          (specs ARE the implementation contract).
        * Explicit `"evidences"` against a non-finding /
          non-hypothesis req warns but proceeds (sometimes
          intentional, e.g. evidencing a methodology).
        * Invalid values raise `ValueError`.
      `services.check()` surfaces `link_type` and `kind` per req
      so the CLI can render the differentiated drift message.
      `services.trace()` (file branch) splits results into
      "Implements" vs "Evidences" sections. Back-compat: entries
      written before M12.6 omit the field; readers default to
      `"satisfies"` everywhere via `.get("link_type", "satisfies")`.
      The `implementation_linked` event now includes `link_type`
      so future metrics can break implementation vs. evidence
      linking down separately. CLI: `loom link <file> --evidences`
      flag; success line distinguishes "✓ Linked X to N satisfies
      + M evidences"; `loom check` content-drift message
      reframes for evidence files ("EVIDENCE CHANGED — re-evaluate
      the finding"); `loom trace <file>` shows separate
      "📋 Implements" and "🔬 Evidences" sections with
      `<finding>`/`<hypothesis>` kind tags. 10 new tests in
      TestLink (default-from-kind for requirement/finding/
      hypothesis/methodology, explicit override both directions,
      invalid value rejection, check + trace surfacing, old-shape
      back-compat). All 472 pre-M12.6 tests still pass.
- [x] **12.7 Kind-aware doctor / metrics / health-score.**
      Closes the dogfooding-surfaced gap where doctor flagged
      legitimate finding/process_rule domains as "non-standard"
      and metrics' coverage % counted findings as "missing test
      specs," producing 0% coverage warnings on stores rich in
      findings. Three changes:
        * `valid_domains_for(kind)` / `VALID_DOMAINS_BY_KIND` —
          per-kind allowed domain sets. `requirement` keeps its
          M0 set (behavior/ui/data/architecture/terminology);
          `finding` adds experimental/evaluation; `methodology`
          and `hypothesis` are experimental/evaluation;
          `process_rule` is operational/workflow/behavior.
          Doctor's domain check now buckets unknowns by kind:
          "Non-standard domains in findings: lunar_phase"
          instead of one global list. Result shape: `domains.
          custom_by_kind: {kind: [domains]}`.
        * Doctor's test-coverage check scopes to
          `kind=requirement` only and exposes
          `test_coverage.scope = "kind=requirement"` so the user
          knows what the percentage is computed against.
          Findings/methodology/process_rules don't have test
          specs in the same sense; they no longer count as
          "missing."
        * `services.metrics` adds `requirements.by_kind` (per-
          kind {total, active, archived, superseded, by_status}
          rollup) and exposes `coverage.scope` +
          `coverage.denominator` so the percentage's basis is
          transparent. Coverage numerators + denominators are
          requirement-only; pre-M12.7 they were diluted by
          findings.
        * `services.health_score`: `impl_coverage` and
          `test_coverage` are kind=requirement-only signals.
          Empty-requirement-set stores get 100 on those signals
          (no signal == no degradation), so a research-only
          store of findings isn't scored 0/100. New
          `active_requirement_kind` field surfaces the scoped
          denominator.
      CLI: `loom doctor` per-kind domain warnings + scope tag on
      coverage. `loom metrics` "By kind" section + scope tag on
      coverage line. `loom health-score` unchanged shape; just
      stops being misleading on mixed-kind stores.
      Empirical impact on the dogfooded loom store (8 findings,
      2 process_rules, 10 requirements):
        coverage 47.1% → 88.9% (denominator went 17 → 9)
        health-score ~50 → 74
        spurious "Non-standard domains: experimental, operational"
          warning replaced with the two real per-kind issues
          ("operational in findings", "data in process_rules")
      that user can fix via set-kind / domain reclassification.
      9 new tests (3 doctor, 2 metrics, 2 health-score, +
      1 fixture-update for the M12.7 domains shape change).
      All pre-M12.7 tests still pass with one shape-update for
      `domains.custom` → `domains.custom_by_kind`.
- [x] **12.7b Per-kind doc generator skips archived items.**
      `docs.generate_requirements_doc` and `generate_test_spec_doc`
      called the low-level `store.list_requirements
      (include_superseded=False)` which only filters by
      `superseded_at`. Archived items (status=="archived") leaked
      through, surfacing as `**Active <kind>:** N+1` with the
      archived item rendered in the body — surfaced via
      dogfooding when REQ-94590539 (the misclassified handoff
      I'd just archived) showed up in PROCESS-RULES.md as
      "Active Process rules: 3" instead of 2. Two-line fix
      (each generator gets a `r.status != "archived"` filter).
      `services.list_requirements` already had this filter; only
      the doc surface was missing it. Two regression tests in
      `TestDocGeneration` cover both surfaces. Live docs
      re-synced + verified: zero references to the two archived
      IDs (REQ-94590539 + REQ-8a9f714b) across REQUIREMENTS.md
      / FINDINGS.md / PROCESS-RULES.md / TEST_SPEC.md.

## Milestone 11: Rationale linkage (v1.x)

**Motivation.** The full M10 series (phQ3 / phQ4 / phQ5 / phQ7) showed
that **rationale is the load-bearing signal** for compliance on
contrarian specs — not the indexer, not the executor, not model size.
Bare rule + no rationale = 0% compliance regardless of indexer; rule
+ rationale = 100% saturation. So rationale capture is the single
most important user discipline, and the discipline users skip most
often.

M11.1 makes rationale a structured field, not just free-form prose:
requirements can derive from earlier decisions via citation chains
(`rationale_links: list[req_id]`), and reqs without rationale or
linkage are flagged with a visible-debt status `rationale_needed`
rather than silently captured as "thin." Prepares the ground for a
later intake hook (proposed M11.2) that auto-detects requirement-
shaped utterances and proposes linkage from existing decisions.

Design + threshold-calibration pilot in
[`docs/DESIGN-rationale-linkage.md`](docs/DESIGN-rationale-linkage.md).

### 11.1 Tasks

- [x] **11.1a Threshold calibration pilot.** Synthesized a 24-req
      Loom-domain corpus + 8 hand-labeled queries; ran them through
      `services.query` to find a confidence threshold that cleanly
      separates "real candidate" from "noise." Result: top-1
      precision 71%, **top-2 precision 100%**, correct-match scores
      0.713–0.818, unrelated baseline 0.600. Recommended threshold
      0.66. Validated the "propose top-2, user picks" UX over
      auto-link top-1 (Q4 had a 0.003-point separation between
      correct and noise — top-1 alone is unreliable on ambiguous
      queries). Pilot:
      `experiments/pilot/rationale_linkage_pilot.py`.
- [x] **11.1b Mechanic shipped.** `Requirement.rationale_links`
      field (`list[str]`, backward-compat via `setdefault`).
      `rationale_needed` added to `VALID_STATUSES`.
      `services.find_related_requirements(text, min_score=0.66,
      limit=2)` wraps `query` with score floor + status filter +
      structured shape. `services.extract` accepts `rationale_links`
      with full validation (link must resolve, must not be
      superseded/archived, no self-links, no transitive cycles).
      Reqs with neither prose rationale nor links default to
      `status=rationale_needed`. CLI: `loom extract --derives-from`
      (repeatable), `loom related "..."`, `loom needs-rationale`.
      Bug-fix: `LoomStore.set_requirement_status` had a hardcoded
      valid-status list missing `archived` (M2.3 era) and now
      `rationale_needed` — synced to match `services.VALID_STATUSES`.
      Tests: 14 new (8 in TestExtract for rationale-linkage paths,
      6 in TestFindRelatedRequirements for retrieval semantics).

### 11.2 Open work (deferred)

- [x] **11.2 Doc rendering.** Three additions to
      `src/loom/docs.generate_requirements_doc`: (a) a "Builds on:"
      subsection per requirement when `rationale_links` is non-empty,
      showing each parent's id, value (truncated to 80 chars), and
      rationale (truncated to 80 chars, italicized); (b) `⚠
      rationale_needed` suffix on the section heading for reqs in
      that status, plus a remediation prompt body when both rationale
      and links are absent; (c) traceability matrix gains a "Derives
      from" column only when at least one active req has linkage —
      avoids cluttering the matrix for projects that haven't started
      using `--derives-from`. New helper
      `docs._format_link_chain(store, link_ids)` does the rendering;
      missing/deleted parents fall through cleanly. 5 new tests in
      `tests/test_store.py::TestDocGeneration` (11 total). Full suite
      passes.
- [x] **11.3 Health-score integration.** Added `rationale_coverage`
      as a 5th equal-weighted component to `services.health_score`.
      Active requirement set excludes `rationale_needed` reqs from
      the denominator — that status is *precisely* "no rationale,"
      so counting them would double-count against the score.
      `rationale_coverage = % of active reqs with prose rationale OR
      rationale_links non-empty`. Score formula:
      `mean(impl_coverage, test_coverage, freshness, non_drift,
      rationale_coverage)`. **Breaking change** — projects with CI
      thresholds pinned to the M5.3 4-component score may need to
      retune. CLI updates `loom health-score` output to surface the
      new component. 10 tests in TestHealthScore (was 3): existing
      perfect-score test updated to include rationale; new tests for
      full-via-prose, full-via-links, zero, partial-split,
      rationale_needed exclusion, 5-component formula, 5-key
      components dict.
- [x] **11.4 `is_complete()` extension (Phase A).**
      `Requirement.is_complete()` now respects
      `LOOM_REQUIRE_RATIONALE_FOR_COMPLETE=1`: when set, ALSO requires
      prose `rationale` OR non-empty `rationale_links` on top of the
      existing elaboration + acceptance_criteria check. Default off
      preserves prior behavior; only the literal `"1"` enables (so
      `"0"`, `"false"`, empty are all off). Phase B (next release)
      flips the default to on; Phase C removes the flag.

      `services.audit_rationale(store)` previews the impact of
      flipping by classifying every active requirement as one of:
      `would_flip` (currently `is_complete()=True`, would become
      False), `already_failing` (basic check fails, no behavior
      change), `unaffected` (passes both checks). Properly excludes
      archived and `rationale_needed` reqs from active. Restores
      the env flag on exit so the audit doesn't pollute the
      caller's environment.

      CLI: `loom audit-rationale [--json]` pretty-prints the buckets
      and lists `would_flip` reqs with a remediation suggestion.

      Tests: 12 new (7 in `TestIsCompleteGate` + 5 in
      `TestAuditRationale`) covering env-flag semantics, both
      rationale sources qualifying, classification correctness,
      and env-leak prevention. Full suite passes.

      **M11 milestone complete.** All five sub-items shipped (M11.1
      mechanic, M11.2 doc rendering, M11.3 health-score, M11.4
      gated is_complete, M11.5 intake hook P0-P4).
- [ ] **11.5 Intake hook.** UserPromptSubmit hook that classifies
      incoming user messages, runs `find_related_requirements`,
      proposes top-2 candidates as system-reminder, and surfaces
      `rationale_needed` debt back into the agent's context.
      Detailed spec in
      [`docs/DESIGN-rationale-linkage.md`](docs/DESIGN-rationale-linkage.md)
      Part 2. Five implementation phases:
    - [x] **P0 classifier pilot (gate).** 40 labeled chat
          utterances run through the spec prompt with
          qwen3.5:latest. **Precision 95.2%** (1 FP, ambiguous
          hedge-language case), recall 100%, F1 0.976, p50 latency
          454ms. Cleared the ≥90% precision gate. Findings:
          [`experiments/pilot/FINDINGS-intake-classifier-pilot.md`](experiments/pilot/FINDINGS-intake-classifier-pilot.md).
          One spec addition called out: softener-detection
          guardrail (lexical match on "if possible" / "try to" /
          "would be nice" → downgrade auto-capture to propose).
    - [x] **P1 hook scaffold.** Three pieces shipped: testable core
          at `src/loom/intake.py` (classifier prompt, six-branch
          decision tree including a new `duplicate` branch added
          after a real-world collision was caught in smoke testing,
          softener-detection guardrail from P0 findings, daily
          auto-capture budget, domain whitelist), CLI manual-test
          surface `loom intake --text "..."` (or stdin), and the
          unregistered Claude Code hook shim
          `hooks/loom_intake.py` (P2 will register it in
          `.claude/settings.json`). 22 unit tests cover parser
          tolerance + every branch + every guardrail. Full suite
          passes. The duplicate-branch addition is worth flagging:
          the M11.5 spec didn't anticipate this case, but it's
          obvious in retrospect — running the same intake message
          twice produced the same deterministic req_id, and the
          auto-link path tried to link the req to itself. The
          duplicate branch correctly catches "we already have this"
          and returns a refine-suggesting reminder instead.
    - [x] **P2 Claude Code integration.** Three pieces shipped:
          (a) `hooks/settings.sample.json` extended with the
          `UserPromptSubmit` block so users have a canonical install
          template; (b) `hooks/README.md` gains a full `loom_intake.py`
          section covering install, manual testing via `loom intake`,
          env vars, six branches, three guardrails, logging, sample
          system-reminders, and failure modes; (c) the active
          `.claude/settings.json` for the loom repo itself registers
          the hook so it fires on real Claude Code sessions in this
          repo. Backed by the loom dev store (currently empty), so
          most messages will route through `rationale_needed` until
          dogfooding builds the corpus — which is exactly what the
          spec wants the hook to drive.
    - [x] **P3 stats + observability.** `services.intake_stats`
          aggregates the intake JSONL log into per-branch counts,
          captured (auto_link + captured_with_rationale) %, noop
          breakdown by reason, guardrail trigger frequency, and
          latency percentiles + top-candidate-score distribution.
          New `loom intake-stats [--tail N] [--json]` CLI surfaces
          it. `services.doctor` gains an `intake` check that warns
          when classifier p95 latency exceeds the 5s budget after
          ≥5 fires (otherwise informational). 8 new tests
          (TestIntakeStats). Full suite passes.
    - [x] **P4 documentation + agents.d snippet.** Three docs
          updates: (a) `agents.d/loom-integration.md` gains a
          "When a Decision is Made" section covering
          `--derives-from`, `loom related`, and the
          `rationale_needed` debt surface; a new "Automatic Intake
          (M11.5)" section covering hook behavior and the four
          branches an agent will see; quick-reference table
          extended with intake / related / needs-rationale /
          intake-stats / indexer-doctor / link --symbol; env-var
          table extended with LOOM_INTAKE_*; (b) `CLAUDE.md`
          gains the new modules in repo layout + key-modules
          sections, and the new commands in the CLI reference
          table with milestone tags; (c) `hooks/README.md`
          loom_intake.py section already shipped in P2 covers
          install + behavior. M11.5 complete.

## Milestone 10: Semantic indexer integration (PLANNED — v1.x)

**Motivation.** The cross-language map (M8.4) showed C++ in a "collapsed"
regime: off=0%, on-rule=0%, +placebo=100%* (artifact), +rat=67%. C/Go
share the resistant-mid neighborhood. The hypothesis is that the
"include the file body" context bundle is too thin for languages where
meaning lives in headers, templates, ADL, and call-graph context that
the local file doesn't carry.

Before building anything heavy, the falsifying experiment is to swap
qwen3.5:latest → **qwen2.5-coder:32b** on S1 C++ (cpp-orders already
hit 6/6 with that executor at single-file in Phase C). If 32b bridges
S1, C++ is an executor-capacity ceiling, not a context ceiling — and
indexers are overkill. If it stays flat, semantic context becomes the
next lever, and this milestone defines how it integrates with Loom.

### 10.1 `SemanticIndexer` interface (DOES NOT REQUIRE Kythe)

A pluggable registry mirroring `runners.py`. Lives at `src/loom/indexers.py`.

```python
class SemanticIndexer:
    def supports(self, language: str) -> bool: ...
    def context_for(self, file: Path) -> str:
        """Symbol-level context for the executor prompt — definitions of
        referenced symbols, override chains, call sites. Empty string
        when no signal."""
    def resolve_symbol(self, ref: str) -> SymbolHit | None:
        """`app::OrderService::commit` → (file, byte-range, ticket)."""
    def signature_of(self, ticket: str) -> str | None:
        """Stable hash of the symbol's structural signature, for
        drift detection."""
```

`INDEXERS` registry holds zero or more registered indexers. Default is
**`NoOpIndexer`** — `supports()` returns False for everything;
`context_for()` returns `""`; `resolve_symbol()` returns `None`. Loom
keeps working unchanged when no real indexer is plugged in.

### 10.2 Context-bundle enrichment

When `loom_exec` builds a task prompt, it asks the registered indexer
for the target file's language: `context_for(file)`. The returned
string gets stitched into the prompt above the file body as
`// SEMANTIC CONTEXT`. Smallest invasive change — no data-model edits,
no link-surface changes.

This is the falsifying experiment for "is C++'s ceiling about
context, not capacity." Run S1 C++ with the indexer-enriched prompt
and compare against the cross-language map's baseline.

### 10.3 Symbol-level linking — `loom link --symbol`

Today: `loom link app/orders.cpp --req REQ-xxx` records a `(file,
line-range)` link. With an indexer:

```bash
loom link --symbol 'app::OrderService::commit' --req REQ-xxx
```

resolves the symbol via `indexers.resolve_symbol()` to a concrete
`(file, byte-range, kythe-ticket)`. The `Implementation` row gains two
new optional fields:

| field | purpose |
|---|---|
| `symbol_ticket: Optional[str]` | indexer's stable identity for the symbol |
| `symbol_signature_hash: Optional[str]` | hash of the symbol's structural signature at link time |

Both default to `None` (`setdefault` in `from_dict` for backward
compat). Existing stores keep loading; existing `--req` / `--spec`
links keep working.

### 10.4 Structural drift detection

Today: drift = `content_hash(file) != stored_hash`. A whitespace edit
trips drift; a function-signature change can hide if the bytes happen
to match. With `symbol_signature_hash` recorded:

```
drift_signals = {
    "content": stored.content_hash != recompute_content_hash(file),
    "structural": indexer.signature_of(ticket) != stored.symbol_signature_hash,
}
```

Reports both. The structural signal is far more useful for catching
"someone changed the API of the function this requirement is linked
to" — which is the actual concern requirements traceability is
trying to surface.

### 10.5 Build-time pipeline (the hard part)

Kythe's clang indexer needs a `compile_commands.json` extracted by
your build system. For a `pip install loom-cli` user that's
non-trivial onboarding. Realistic shape: **Loom integrates with your
existing Kythe deployment**, opinionated infra rather than bundled.
A `loom indexer doctor` health-check tells the user whether their
project has a working Kythe corpus before they try `--symbol`.

Other languages, other indexers. The registry pattern means each
plugs in independently:

| language | likely indexer | invocation |
|---|---|---|
| C++ | Kythe (clang-based) | `kythe -corpus loom -build_config compile_commands.json` |
| Java | Kythe (javac extractor) | same Kythe pipeline |
| Go | Kythe (Go indexer) | same Kythe pipeline |
| Python | Pyright (LSP) | runtime, no extraction step |
| TypeScript | tsserver (LSP) | runtime, no extraction step |
| Rust | rust-analyzer (LSP) | runtime, no extraction step |

LSP-backed indexers (Python/TS/Rust) are operationally cheaper than
Kythe — no graphstore to maintain, no extraction step. The Kythe
languages get the richest cross-references but pay for it in build-
pipeline complexity.

### 10.6 Tasks (status)

- [x] **10.1a Roadmap captured** — this section.
- [x] **10.1b Falsification: qwen2.5-coder:32b on S1 C++** — 20 trials
      (4 cells × N=5), 5.9 min wall. Result: **0/10 off, 0/10 on-rule,
      2/10 +placebo (noise), 0/10 +rat**. The bigger executor did NOT
      bridge S1 C++ — actually scored *worse* on the rat cell than
      qwen3.5's 67%. Conclusion: **C++ ceiling is NOT executor
      capacity**, semantic context becomes the next defensible lever.
      See `FINDINGS-bakeoff-v2-cpp-executor-falsification.md`.
- [x] **10.1c `SemanticIndexer` abstract interface + registry +
      `NoOpIndexer`** — `src/loom/indexers.py`.
- [x] **10.1d `Implementation.symbol_ticket` + `symbol_signature_hash`
      fields** — backward-compatible via `setdefault`.
- [x] **10.1e `loom link --symbol` plumbing** — works as a stub error
      path until a real indexer is registered.
- [x] **10.2 Context-bundle enrichment falsified with stub indexer**
      — phL2 ran 20 trials (4 cells × N=5) with a hand-authored
      `StubCppIndexer` that returns Kythe-shaped semantic context
      for `retry.hpp`. Same model as M10.1b (qwen2.5-coder:32b).
      Result vs the falsification baseline:
      | cell | baseline | with stub | delta |
      |---|---|---|---|
      | off | 0% | 0% | +0pp |
      | on-rule | 0% | 20% | **+20pp** |
      | on-rule+placebo | 20% | 60% | **+40pp** |
      | on-rule+rat | 0% | 40% | **+40pp** |
      Conclusion: **semantic context is the M10 lever for C++.** Lift
      is real but partial (peak 60%, not saturation) — context is
      necessary but not sufficient on this scenario. Wiring through
      `loom_exec` proper is now blocked only on a real indexer
      backend; the prompt-assembly seam is validated. Findings doc:
      `FINDINGS-bakeoff-v2-cpp-stub-indexer.md`.

- [x] **10.3 Multi-language stub-indexer extension** — extended the
      M10.2 falsification to two more languages from the cross-
      language map: C (resistant-mid) via phM2 + `StubCIndexer`,
      and JavaScript (graded-no-saturation) via phQ2 + `StubJsIndexer`.
      Same architecture, same `qwen2.5-coder:32b` executor, ~30
      trials (some cells N<5 due to runner crashes). Three different
      responses to the same intervention:

      | language | regime | rat baseline | with stub | takeaway |
      |---|---|---|---|---|
      | **C++** | collapsed | 0% (32b-no-stub) | **40%** | partial bridge |
      | **C** | resistant-mid | 60% | 50% | no measurable lift |
      | **JS** | graded-no-sat | 60% | **100%** | saturating lift |

      JS additionally jumped from 0% → 60% in the *off* cell —
      meaning the JSDoc-style stub was encoding an implicit rule.
      Conclusion: **the M10 architecture (pluggable per-language
      indexers) is right, but per-language plug-ins do different
      things.** The "one-indexer-fixes-all-resistant-languages"
      framing is wrong; C needs different signal than C++ and JS.
      Findings doc:
      `FINDINGS-bakeoff-v2-stub-indexer-multilang.md`.

      Side fix: phL2/phM2/phQ2 harnesses patched to write summary
      files even on Ollama-call failure, so future 32b crashes don't
      silently drop trials.
- [x] **10.3a phQ3 — clean-stub falsification of phQ2 (JS).** Stripped
      the JSDoc-style contract assertions from the JS stub, leaving
      peek-references-style structural facts only. N=40 (4 cells × 10).
      Result: phQ2's striking 0→60% off-cell lift was the JSDoc rule
      leak; on the clean stub it collapses back to 0%. The on-rule
      cell collapses below the no-stub baseline (0% vs 20%) — bare
      structural facts can be an *active distractor* without
      explanation alongside. Placebo and rationale cells stay near
      saturation (90% / 100%). Findings:
      [`FINDINGS-bakeoff-v2-js-stub-clean.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-js-stub-clean.md).
- [x] **10.3b phQ4 — 32b no-stub baseline (JS).** Holds the model at
      qwen2.5-coder:32b and removes the stub. N=40. Decomposes the
      phQ3 vs phQ baseline +rat 60→100% lift into +20pp model tier
      and +20pp stub effect (additive). Surfaces a counter-intuitive
      finding: **the bigger code-specialist model HURTS bare-rule
      cells on contrarian specs** (-20pp on rule, -30pp on placebo
      vs qwen3.5). qwen2.5-coder:32b's "good practice" priors fight
      the contrarian rule. The stub effect is concentrated on
      placebo (**+80pp**, 10→90%) — strongest cell-specific stub
      effect across all M10 experiments. Reframes the JsIndexer
      product pitch: the indexer **amplifies the rationale signal**,
      it doesn't fix bare rule compliance. Findings:
      [`FINDINGS-bakeoff-v2-js-no-stub-32b.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-js-no-stub-32b.md).
- [x] **10.3c First real indexer: `JsIndexer` (LSP-backed,
      typescript-language-server).** `src/loom/indexers_js.py`.
      Subprocess wraps `typescript-language-server --stdio` over
      JSON-RPC, surfaces peek-references-style context shaped to
      match the phQ3 stub. Soft-fails to empty context with a one-
      time warning when the binary isn't on PATH. Validated against
      a JS fixture: cross-file references resolve correctly through
      ES module imports (CommonJS `require()` is a known limitation
      of `tsserver` checkJs mode — pending follow-up). 13 unit +
      integration tests pass. Install: `npm install -g
      typescript-language-server typescript`.
- [x] **10.3d phQ5 — JsIndexer end-to-end validation.** Authored
      a parallel ESM scenario (`s1_swallow_error_esm/`) with real
      sibling files (`retry.js` + `backoff_loop.js` + `sync_worker.js`
      + `package.json` + `jsconfig.json`) so typescript-language-server
      could index a real project. N=40, 4 cells × 10. **Validated
      partially:** rat cell saturates at 100% (matches phQ3 stub),
      confirming the rationale-amplification pitch holds with real
      LSP output. **Falsified partially:** placebo cell drops 90%
      → 20% (-70pp) — the phQ3 stub's lift on placebo was not pure
      structural facts. The hand-authored stub had additional
      curated content (test references, adjacent type definitions)
      that real `textDocument/references` doesn't surface. Identifies
      two concrete follow-ups to close the gap (import-filtering,
      adjacent type defs). Findings:
      [`FINDINGS-bakeoff-v2-js-real-lsp.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-js-real-lsp.md).
- [x] **10.3e JsIndexer v2: filter import refs + adjacent type defs.**
      Both improvements landed in `src/loom/indexers_js.py`:
      `_is_import_ref` heuristic skips import-statement references
      before emission, and `_collect_adjacent_type_defs` queries
      `documentSymbol` on each sibling file with surviving refs and
      appends top-level Class signatures. 22 unit + integration tests
      pass (13 from M10.3c + 9 new). Validation via phQ6 (N=40)
      lifted placebo from 20% → **30%** (+10pp) — useful but well
      short of phQ3's 90%. Rationale held at 100%, off / on-rule
      held at 0%. **Falsifies** the M10.3d hypothesis that adjacent
      type defs were the load-bearing missing piece (phQ6 v2 has
      MORE type defs than phQ3, still 60pp short on placebo).
      Identifies the test-reference (`assert(result === null)`) as
      the most likely remaining missing ingredient. Findings:
      [`FINDINGS-bakeoff-v2-js-real-lsp-v2.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-js-real-lsp-v2.md).
- [x] **10.3f phQ7 — test-reference surfacing experiment.** Tested
      the phQ6 hypothesis that test references were the load-bearing
      missing piece. **Confirmed strongly.** No JsIndexer code
      change required — `_walk_project` already includes test files
      because they're not in `_PROJECT_GLOB_IGNORE_DIRS`. The phQ5/
      phQ6 placebo gap was an artifact of harness workspace setup
      excluding `tests/`. With test file copied alongside source
      (one-line `setup_workspace` change), the LSP indexes it
      naturally and surfaces its references with the load-bearing
      `if (result === null) { console.log("PASS: ...") }` snippets.
      Result: placebo **30% → 70% (+40pp)**, the largest single-
      intervention effect across the entire M10 series. Rationale
      held at 100%, off / on-rule held at 0%. Remaining 20pp gap
      to phQ3's stub (90%) is plausibly N=10 noise. Operational
      guidance: instantiate `JsIndexer(root=...)` with the project
      root, not a subset that excludes tests. Findings:
      [`FINDINGS-bakeoff-v2-js-test-refs.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-js-test-refs.md).
- [x] **10.4 Multi-channel drift detection in `services.check`.**
      The original task was structural drift; investigation showed
      content-hash drift wasn't actually wired in either, so this
      milestone delivers both. `services.check` now returns a
      `drift_signals` dict alongside the existing `drift_detected`
      boolean, with three channels:
      - **content**: file's current content_hash differs from the
        impl's stored content_hash at link time (whitespace-sensitive,
        always available). The plain "the code changed since you
        linked it" signal that was missing.
      - **structural**: when an indexer's `signature_of()` returns
        a different hash than the impl's stored
        `symbol_signature_hash`. Catches API-shape changes that
        whitespace-sensitive content drift would either miss
        (renamed function with same bytes) or false-flag (whitespace
        edit to function body). Always False for impls without a
        `symbol_ticket` (i.e. impls linked without `loom link
        --symbol`); architecture is in place for users with
        registered indexers + symbol-resolved links.
      - **superseded**: existing signal — at least one linked
        requirement has been superseded since link time.
      `drift_detected` is the OR of all three (backwards-compatible
      with existing callers). `drift_detected` events in the M5.1
      log now also record which `signals` fired, so future metrics
      can break drift down by channel. CLI's `loom check` surfaces
      content + structural drift in the human-readable output.
      Tests: 5 new (8 total in TestCheck), full suite passes.
      Implementation note: JsIndexer's `signature_of()` MVP is a
      separate follow-up — until that lands, the structural channel
      is wired but reports False for JS impls. Other indexers
      (Pyright, Kythe, …) can light it up immediately by
      implementing `signature_of()` and registering.
- [x] **10.5 `loom indexer-doctor`** — health check for the
      semantic-indexer pipeline. `services.indexer_doctor(store)`
      enumerates registered indexers, calls each one's `health()`
      method (added to the `SemanticIndexer` interface as a default
      no-op; `JsIndexer` overrides to verify
      typescript-language-server is on PATH), and walks the store for
      symbol-linked `Implementation` rows to flag any whose language
      lacks a registered indexer (their structural drift channel is
      silently broken). CLI subcommand: `loom indexer-doctor [--json]`.
      Exit code 1 when not OK. Roll-up `ok` requires (a) at least one
      non-NoOp indexer registered, (b) all registered indexers report
      healthy, (c) every symbol-linked impl has an indexer for its
      language. Tests: 6 (TestIndexerDoctor). Full suite passes.
      Side-effect: added `LoomStore.list_implementations()` since the
      doctor needs a store-wide impl walk and only per-req/spec/pattern
      lookups existed before.

### 10.7 Open questions

- **Cache invalidation.** Kythe graphs go stale on file edits. Watch
  with inotify, re-run on every `loom link`, or accept eventual-
  consistency with surfaced "stale-index" warnings? Probably the third
  for v1.x.
- **Pricing.** Indexer infra is opinionated. Whether `loom-cli[kythe]`
  ships a Kythe deployment or just connects to a user-supplied one is
  a deployment-shape decision tied to the broader Loom-as-product story.
- **Python and friends.** LSP-backed indexers can run inline without
  any extraction step — they may be the cheaper proving ground for the
  whole architecture even though Python isn't the language with the
  ceiling. A `PyrightIndexer` would prove the seams without the Kythe
  build complexity.

## Milestone 9: PyPI packaging (DONE)

Loom installs from PyPI as `loom-cli`. Two console scripts (`loom`,
`loom_exec`) plus a real Python package (`import loom`,
`from loom.store import LoomStore`).

- [x] **9.1 Package layout** — `src/loom/` is the canonical package
      (was bare `src/*.py`). Internal imports use relative form
      (`from .store import …`); external callers (tests, scripts,
      mcp_server, experiments) use absolute (`from loom.store import …`).
- [x] **9.2 In-package data** — `prompts/` and `templates/` moved
      under `src/loom/` so they ship in the wheel; lookups switched
      to `Path(__file__).parent / "prompts"` etc.
- [x] **9.3 CLI entry points** — `scripts/loom` and `scripts/loom_exec`
      reduced to thin shims (`from loom.cli import main`); the real
      argparse logic lives in `src/loom/cli.py` and
      `src/loom/exec_cli.py`. `pyproject.toml::project.scripts`
      registers `loom = loom.cli:main` and
      `loom_exec = loom.exec_cli:main` so a `pip install` exposes
      both on PATH.
- [x] **9.4 pyproject.toml** — setuptools backend, Python 3.10+,
      single runtime dep (`PyYAML`); optional `mcp` and `dev`
      extras. `pip install -e .` validated end-to-end (313/313 tests
      pass against the editable install).

## Milestone 0: Small-model execution pipeline (DONE)

Capability-substitution thesis validated empirically. See
[`experiments/gaps/FINDINGS.md`](experiments/gaps/FINDINGS.md).

- [x] **0.1 Hook instrumentation** — `hooks/loom_pretool.py` injects linked
      reqs/specs/drift on Edit/Write as a system-reminder; logs per-fire
      `{latency_ms, bytes, reqs, specs, drift, fired, skipped}` to
      `<project>/.hook-log.jsonl`.
- [x] **0.2 `loom cost`** — Aggregates the hook log. Reports p50/p95/p99
      latency, total injected bytes, overhead percentage, skipped-vs-fired.
- [x] **0.3 LLM-verified conflict detection** — `src/conflict_verify.py`
      adds an LLM confirmation pass over embedding-overlap candidates so
      `loom conflicts` reports real conflicts only.
- [x] **0.4 Task entity** — `Task` dataclass + `tasks` table +
      `add_task`/`list_tasks`/`list_ready_tasks`/`update_task`/
      `set_task_status`/`search_tasks` store methods. Lifecycle: pending →
      claimed → complete | rejected | escalated. Atomicity budget (≤2 files,
      ≤80 LoC default) and dep DAG enforced at validation time.
- [x] **0.5 `loom task` CLI** — add/list/show/claim/release/complete/reject/
      prompt verbs. `loom task prompt` emits the assembled executor prompt
      for a task (context bundle included).
- [x] **0.6 `loom decompose`** — Propose atomic-task decomposition for a
      spec. Dispatches to Anthropic or Ollama by `provider:model` prefix.
      Defaults: `anthropic:claude-opus-4-7` if `ANTHROPIC_API_KEY` set, else
      `ollama:qwen2.5-coder:32b`. Validates atomicity + dep graph before
      persisting. `--apply` writes to the store.
- [x] **0.7 `scripts/loom_exec`** — End-to-end runner: claim next ready
      task, assemble context bundle, call Ollama, extract code, apply to
      scratch copy, run grading test, promote on pass. Logs to
      `<project>/.exec-log.jsonl`. Default model `LOOM_EXECUTOR_MODEL`
      falling back to `qwen3.5:latest`.
- [x] **0.8 Capability validation** — `benchmarks/ollama_gaps*.py` runners
      across three task shapes (write, extend, behavior-preserving
      refactor). `qwen3.5:latest` (9.7B, local) matched Opus 4.7 on every
      trial; findings documented in `experiments/gaps/FINDINGS.md`.

**Headline:** `qwen3.5:latest` local execution at `temperature=0` is
byte-deterministic and matches frontier cloud models on atomic Loom-specced
tasks at effectively zero marginal cost.

**Carry-overs (not blockers):**
- Cross-module tasks are untested — benchmark covers single-file mods only.
- Ambiguous specs (require design judgment) are untested.
- Non-Python codebases untested.
- `loom_exec` currently supports a single grading-test-runs-pytest
  criterion; multi-criteria grading (lint + type + test) is future work.

## Milestone 0.5: Onboarding & generalization (DONE)

Turn the pipeline from "dogfoods on Loom" into "works on any Python+pytest
repo." Validated against agentforge in
[`experiments/wild/FINDINGS-wild.md`](experiments/wild/FINDINGS-wild.md).

- [x] **0.5a `loom_exec --target-dir` / `LOOM_TARGET_DIR`** — Runner no
      longer hard-coded to Loom's own repo. Separates "store name" from
      "source root."
- [x] **0.5b `loom decompose --target-dir`** — Validator auto-adds
      `files_to_modify` entries that exist on disk to `context_files`,
      so the executor sees real source instead of hallucinating.
- [x] **0.5c UTF-8 stdout** — Emoji no longer crash the CLI on Windows
      cp1252 when output is piped.
- [x] **0.5d `-p` at every position** — `loom doctor -p foo` works (was
      KNOWN_ISSUES C1).
- [x] **0.5e `loom init`** — Writes `.loom-config.json` at the target
      repo root, runs health-check (Ollama, models, pytest, tests/),
      prints next-steps. Everything downstream picks up defaults from
      the config so `loom extract` / `loom decompose` / `loom_exec`
      don't need flags once init has run.
- [x] **0.5f Config precedence** — CLI flag > env > config > built-in
      default. `src/config.py` owns the resolution.

- [x] **0.5g Templates (Interpretation B)** — `loom init --template
      <name>` scaffolds files from a template. Template registry:
      `~/.loom/templates/<name>/` wins over `<loom-repo>/templates/
      <name>/`. One starter ships (`python-minimal`) as a reference;
      users are expected to fork it. Variables declared in
      `manifest.yaml`, prompted interactively or passed via `--var
      KEY=VALUE`. `{{ var }}` substitution in file contents and
      file/directory names. Shipped starter validated end-to-end: scaffold
      → `pip install -e '.[dev]'` → `pytest` passes.
- [x] **0.5h₂ Per-runtime starter templates** — Three new starters
      ship (`dart-minimal`, `flutter-minimal`, `typescript-minimal`) to
      pair with each shipped runner. Template manifests gain a
      `config_overrides` section — `services.init()` merges those into
      `.loom-config.json`, so `loom init --template flutter-minimal`
      produces a Flutter-shaped config without manual editing. The
      runner-dep health-check also dispatches by runner (pytest in
      requirements.txt / pubspec.yaml for Dart / package.json for TS)
      so non-Python projects stop getting spurious "pytest not
      declared" warnings. All four starters validated end-to-end: fresh
      scaffold → native deps install → smoke test passes.
- [x] **0.5h Multi-runtime `loom_exec`** — Pluggable test-runner
      registry (`src/runners.py`) replaces the hardcoded pytest call.
      Shipped runners: `pytest` (Python, append-mode), `dart_test` /
      `flutter_test` (Dart, replace-mode), `vitest` (TypeScript,
      replace-mode). Each runner owns its command shape, result parser,
      code-block fence, apply mode, and failing-placeholder skeleton.
      `.loom-config.json`'s `test_runner` selects which. Downstream
      (`loom_exec`, `task_build_prompt`, `loom spec --test`, decompose
      prompt) all dispatch through the registry. Validated end-to-end
      against real `dart test` and `npx vitest run` output. Authoring
      a new runner = a single `Runner(...)` entry; no other code changes.
- [x] **0.5i Duplicate-spec detection (D1 from sparkeye audit)** —
      `services.spec_add` refuses to create a second non-superseded
      spec under the same parent requirement (raises `DuplicateSpecError`
      with the siblings on it); CLI prints the existing spec(s) and the
      two options (supersede or `--force`). `services.doctor` gains a
      `duplicate_specs` check that surfaces the same condition in
      existing stores — validated on the sparkeye store where the check
      correctly flags `REQ-ef81f657 → {SPEC-c6aa6b90, SPEC-30fdda42}`.
      Caught at creation time for new specs; surfaced retroactively for
      existing ones. Addresses the "agent generated duplicate specs
      with different path conventions, nothing flagged it" failure mode
      from yesterday's sparkeye audit.

## Milestone 1: CLI Foundations (DONE)

Make Loom reliable for tool use by AI agents.

- [x] **1.1 Portable shebang** — `#!/usr/bin/env python3`
- [x] **1.2 `--json` output** — 11 commands now support `--json` / `-j`
- [x] **1.3 Exit codes** — 0=success, 1=error, 2=drift/conflicts
- [x] **1.4 `rationale` field** — `--rationale` on `extract`, included in docs and JSON
- [x] **1.5 Implementation links in docs** — REQUIREMENTS.md shows linked files, drift warnings, traceability matrix; TEST_SPEC.md shows covered/uncovered code

## Milestone 2: Requirement Hygiene (DONE — minus optional 2.4)

Surfaces staleness without automatic deletion. Requirements are decisions
— Loom helps users review and decide, never silently deletes.

- [x] **2.1 `last_referenced` timestamp** — `Requirement.last_referenced`
      is stamped by every read/link operation: `services.query`, `check`,
      `link`, `trace`, and `chain` all call `store.touch_requirement(req_id)`
      on each requirement they surface. Backward-compatible via
      `setdefault(None)` in `Requirement.from_dict`.
- [x] **2.2 `loom stale` command** — `services.stale()` ranks
      requirements by `last_referenced` ascending (never-referenced
      coldest, sorted by creation timestamp). Filters: `--older-than N`
      (days), `--unlinked` (no Implementation rows), `--include-archived`.
      `--json` for agent consumption. Superseded requirements are always
      excluded.
- [x] **2.3 `loom archive` command** — `archived` is a fifth state in
      `VALID_STATUSES`, distinct from `superseded`. `services.archive()`
      sets it; recoverable via `set_status(req_id, "pending")`. Filtered
      from `list`, `query`, and `stale` by default; opt in via
      `--include-archived` (or `--all` on `list`).
- [ ] **2.4 `loom review` (optional)** — Interactive walkthrough of
      stale requirements. Skipped for v1: the non-interactive flow
      (`loom stale --json` + `loom archive`/`set-status`) is sufficient
      for agent + scripted use cases. Revisit if interactive UX
      becomes a real demand.

Design principle: **surface, don't delete.**
1. `last_referenced` tracks activity passively (zero effort)
2. `loom stale` shows what's cold (read-only, safe)
3. User/agent decides: keep, archive, or supersede (explicit action)

## Milestone 3: Pluggable Embeddings (DONE)

Removes hard dependency on local Ollama. Three providers ship; the
SQLite store pins its embedding dimension on first write so a
provider switch can't silently corrupt search.

- [x] **3.1 Provider interface** — `src/embedding.py` dispatches to
      `ollama` (default; `nomic-embed-text` @ 768d), `openai`
      (`text-embedding-3-small` @ 1536d via `OPENAI_API_KEY`, urllib
      no-SDK), and `hash` (explicit deterministic, dim configurable
      via `model="hash:N"`). Selection precedence: `--embedding-provider`
      → `LOOM_EMBEDDING_PROVIDER` → `.loom-config.json::embedding_provider`
      → `ollama`. Cache key includes (provider, model) so switching
      providers can't return a stale vector. The Ollama-outage hash
      fallback is preserved (back-compat); other providers raise
      explicitly so misconfiguration surfaces.
- [x] **3.2 Dimension validation** — `LoomStore` adds a `_loom_meta`
      table that pins `embedding_dim` on the first vector write. All
      six collections route their writes through one `_check_embedding_dim`
      callback; mismatched writes raise `EmbeddingDimensionMismatch`
      with actionable advice ("provider likely changed; revert,
      use a fresh -p, or re-embed"). Legacy stores back-fill the
      dim from existing data on next open.

## Milestone 4: Claude Code Integration (PARTIAL)

First-class tool integration with Claude Code sessions.

- [x] **4.1 Hooks** — `.claude/settings.json` with SessionStart (doctor + status), PostToolUse on Edit/Write (drift check), PostToolUse on Bash git commit (sync docs). Plus `hooks/loom_pretool.py` (Milestone 0.1) with JSONL telemetry.
- [x] **4.2 MCP server (Phase A + B)** — Thin Python MCP server wrapping `LoomStore` as typed MCP tools. Phase A (read) and Phase B (write) tools are shipped. Only `init-private` remains CLI-only. See `mcp_server/README.md`.

### 4.2 MCP server — design

**Location:** `mcp_server/server.py` (thin) + `mcp_server/tools.py` (handlers). Imports `src/store.py` directly — same `sys.path` trick as `scripts/loom`. Do not duplicate business logic.

**Phase A — read tools (ship first):**
| Tool | Wraps | Notes |
|---|---|---|
| `loom_query` | `LoomStore.query` | `text`, `project?`, `limit?` |
| `loom_list` | `LoomStore.list_requirements` | `project?`, `status?` |
| `loom_status` | `cmd_status` logic | drift summary |
| `loom_trace` | `cmd_trace` | bidirectional |
| `loom_chain` | `cmd_chain` | full req→specs→impls→tests |
| `loom_doctor` | `cmd_doctor` | health checks |
| `loom_coverage` | `cmd_coverage` | gap analysis |

**Phase B — write tools:**
| Tool | Wraps | Confirmation? |
|---|---|---|
| `loom_extract` | `cmd_extract` | ask (creates requirement) |
| `loom_link` | `cmd_link` | ask (mutates store) |
| `loom_check` | `cmd_check` | no (read-only) |
| `loom_spec_create` | `cmd_spec` | ask |
| `loom_supersede` | `cmd_supersede` | ask (destructive-ish) |
| `loom_sync` | `cmd_sync` | no (regenerates docs) |

**Resources:**
- `loom://requirements/{project}` — live REQUIREMENTS.md
- `loom://testspec/{project}` — live TEST_SPEC.md
- `loom://drift/{project}` — current drift report (JSON)

**Project scoping:** every tool takes optional `project`. Default from `LOOM_PROJECT` env var, then falls back to `get_project_name()` from the MCP server's cwd (usually the project dir the user launched Claude Code from).

**State wins:** per-session embedding cache survives across tool calls (vs. cold cache on every CLI subprocess).

**Registration:** ship a sample `.mcp.json` in the repo root so users can enable Loom in their Claude Code session with one file.

**Non-goals for 4.2:**
- Don't reimplement the CLI. The MCP server and CLI must call the same `LoomStore` methods.
- Don't replace hooks. Hooks fire on deterministic events (Edit/Write, SessionStart); MCP tools are model-initiated. They're complementary.

## Milestone 5: Metrics & Effectiveness Measurement (DONE)

Tracks whether Loom is actually helping. Without measurement, you can't
tell if the token cost is justified.

### 5.1 Event log (DONE)

Append-only JSONL log at `<store.data_dir>/.loom-events.jsonl`. One
JSON object per line, written by `services._record_event` from the
five canonical touchpoints:

| event | written by |
|---|---|
| `requirement_extracted` | `services.extract` |
| `conflict_found` | `services.extract` (per conflict it surfaces) |
| `implementation_linked` | `services.link` (per linked req) |
| `drift_detected` | `services.check` (when drift seen) |
| `check_clean` | `services.check` (when no drift) |

The `cost` log (`.hook-log.jsonl`) and `exec` log (`.exec-log.jsonl`)
remain separate — they capture different layers (PreToolUse hook
firings, executor task runs). The events log is for *user-meaningful*
operations.

### 5.2 `loom metrics` command (DONE)

Reads the event log and store state, returns a structured snapshot:

```
loom metrics -p proj                # human-readable
loom metrics -p proj --json         # for agents / CI
loom metrics -p proj --since 30d    # clip activity window to N days
```

Output shape:
- **requirements:** total / active / archived / superseded
- **coverage:** with_impls (count + %), with_test_specs (count + %)
- **drift:** events / files_affected / clean_checks / drift_ratio_pct
- **conflicts:** caught (count of conflict_found events)
- **activity:** extracted / linked (windowed by `--since`)
- **staleness:** never / over_30d / over_60d / over_90d buckets
                  (driven by `last_referenced` from M2.1)

### 5.3 `loom health-score` (DONE)

Single 0-100 score, equal-weighted average of four components:

| component | meaning |
|---|---|
| `impl_coverage` | % of active reqs with at least one linked Implementation |
| `test_coverage` | % of active reqs with a TestSpec |
| `freshness`     | % of active reqs referenced in the last 90 days |
| `non_drift`     | % of recent (90-day) checks that found no drift; 100 when no checks recorded yet (no signal ≠ degradation) |

```bash
SCORE=$(loom health-score -p proj --json | jq '.score')
[ "$SCORE" -lt 50 ] && echo "Requirements health is degrading"
```

Empty stores return `score=0`, never crash. Useful for CI gates.

## Dependency Graph

```
Milestone 1 (DONE)
       │
       ├──────────────────────────┐
       ▼                          ▼
Milestone 2 (Hygiene)    Milestone 3 (Embeddings)
       │                          │
       ▼                          ▼
Milestone 4 (Integration) ◄──────┘
       │
       ▼
Milestone 5 (Metrics)
  5.1 Event log (needs extract/check/link/conflicts to log events)
  5.2 loom metrics (needs event log)
  5.3 loom health-score (needs metrics + coverage data)
```

Milestones 2 and 3 are independent and can run in parallel. Milestone 5 depends on Milestone 1 (JSON output) and benefits from 2 (staleness data feeds metrics).

## Milestone 6: Cross-language validation (DONE)

**Last updated:** 2026-04-30

This milestone tracks empirical evidence for *where* the asymmetric
pipeline works (Opus plans, qwen executes), broken down by language
and project size. Original Phase C companion:
[`FINDINGS-bakeoff-v2-phaseC-inventory.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-phaseC-inventory.md).
Headline expansion (9 languages × S1 cross-session smoke):
[`FINDINGS-bakeoff-v2-cross-language-map.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-cross-language-map.md).

### 6.0 Original objectives (recap)

1. **Capture** decisions and their rationale into a structured store,
   not just chat history.
2. **Surface** those decisions back to the agent before it edits the
   relevant code.
3. **Detect drift** when code changes diverge from documented
   decisions.
4. **Coordinate** an asymmetric pipeline: a frontier model plans, a
   small local model executes.
5. **Persist** rationale across separate sessions so a successor
   agent can pick up an absent predecessor's intent.

### 6.1 Data-backed claims

| claim | phase | result | data |
|---|---|---|---|
| Pre-edit hook lifts compliance at sub-frontier tiers | E | **+93 pp Sonnet, +60 pp Haiku, 0 pp Opus** | 30 trials |
| Hook lift transfers across model tiers | E.cross-tier | confirmed Haiku→Sonnet→Opus | 60 trials |
| Hook hard-block reliably stops drift | E.block | 30/30 mechanism reliable | 30 trials |
| Hook latency is constant at scale | E.scale | ~800 ms floor at 100/500 files | 16 trials |
| File-content drift is detected and surfaced | F | gap closed; end-to-end verified | committed |
| Asymmetric pipeline matches frontier quality at lower cost (single-file Python) | D | **~8× cheaper at N=20 matched-pricing**, parity quality | 60 trials |
| Cross-session rationale carries forward | G | **100 % citation Haiku, 93 % Sonnet** vs 0 % placebo | 120 trials |
| Pipeline transfers to single-file C++ | C/cpp-orders | 5/5 = 100% (qwen2.5-coder:32b) | 11 trials |
| Pipeline transfers to small multi-file Dart | C/dart-orders | 40 % → **100 %** after Tier 1+2 (qwen3.5) | 25 trials |

### 6.2 Null / mixed results

| claim | phase | result |
|---|---|---|
| Loom helps in-session at saturated benchmarks | A | Honest null — bounded cost overhead, no measurable correctness lift on benchmarks every Claude tier already passes |
| Asymmetric pipeline scales to 9-file Dart with qwen3.5 | C/dart-inventory | **0/30** — Dart-specific failure cluster (named-args, `const`, records) |
| Contract binding lifts the dart-inventory ceiling | C/dart-inventory | Cell A 0/15 vs Cell B 0/15 — no separation |

### 6.3 Per-language fitness map

| language | single-file | small multi-file (≤3) | large multi-file (~9) | verdict |
|---|---|---|---|---|
| **Python** | ✅ 100% (Phase D) | (skipped) | ✅ **5/5 = 100%** (qwen3.5) | use it freely up to ~9 files |
| **Dart (pure)** | (skipped) | ✅ 100% after Tier 2 | ❌ 0/35 (qwen3.5 + qwen2.5-coder:32b) | use for ≤ 3 files; ceiling robust to executor at 9 |
| **C++** | ✅ 100% (cpp-orders) | (skipped) | v1 header-only: 2/5 = 40% · **v2 split:** **4/5 = 80%** (qwen2.5-coder:32b) | use split `.h/.cpp` convention; matching qwen's native idiom doubled the pass rate |
| **Flutter Dart** | (skipped, multi-file by nature) | ✅ **3/3 = 100%** capability (qwen2.5-coder:32b) | ❓ untested (no `flutter-inventory` benchmark) | use for ≤ 3 widgets; widget-tree + ScaffoldMessenger + Key selectors all carry |

**Cross-language S1 smoke (Milestone 8)** added 7 more languages on
a focused contrarian-rule scenario (single file, qwen3.5):

| language | regime | rule lift | rationale lift |
|---|---|---|---|
| Java | bridging | +60 pp | +40 pp |
| TypeScript | bridging-graduated | +40 pp | +60 pp |
| JavaScript | graded (caps at 60%) | +20 pp | +40 pp |
| Go | volatile | +40 pp | +0 pp |
| C | resistant-mid | +0 pp | +10 pp |
| Rust | rule-saturates | **+100 pp** | +0 pp |
| Asm (NASM x86-64) | rule-saturates | **+100 pp** | +0 pp |

See [`FINDINGS-bakeoff-v2-cross-language-map.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-cross-language-map.md) for the full classification + per-trial behavior.

### 6.4 Project-size fit (qwen3.5:latest as default executor)

- **≤ 250 LoC, ≤ 3 files of any tested language**: well-supported.
- **Single-header C++**: well-supported with qwen2.5-coder:32b.
- **9-file Python**: directionally supported (N=1).
- **9-file Dart**: not supported. Bring a different executor or a
  Dart-aware validator.
- **9-file C++**: unknown.
- **> 9 files**: unknown.

### 6.5 Design work the data points to

1. **Per-language semantic validators between body pass and grading.**
   The dart-inventory failures are deterministic and detectable:
   missing required getter, positional-vs-named arg mismatch,
   stripped `const`. A `dart analyze` / `pyright` / `clang-tidy`
   pass between body-write and grading would catch those before
   they cascade into the next task.

2. **Executor selection should be language-aware.** qwen3.5:latest
   is fine for Python; insufficient for 9-file Dart. A
   `LOOM_EXEC_MODEL_FOR_LANG` map (qwen2.5-coder:32b for Dart/C++,
   qwen3.5:latest for Python) is a small change with potentially
   large lift.

3. **Negotiated-contract architecture: revisit but evolve.** The
   `Specification.contracts_json` + `ContractAmendment` data plane
   was rolled back after experiments showed contracts can't
   manufacture executor capability. If reintroduced, the binding
   should focus on *cross-file invariants* (e.g. "every service
   constructor takes `Store&` first") that qwen *can* follow, not
   on signatures qwen reproducibly violates.

4. **Production-mode demonstration is missing.** The "your Claude
   Code session is the architect; loom_exec dispatches body work to
   qwen; failures surface back as structured tool output" workflow
   has the data plane to support it but no end-to-end demonstration
   trial. A worked example on a real (small) project is the
   clearest sales pitch.

5. **N-confidence on the 9-file Python claim.** N=1 is enough for
   direction but not for stat confidence. N≥5 in Python at 9 files
   is the cheapest experiment to firm up the cross-language story.

6. **Flutter / TS / real-world coverage.** Sales-relevant gaps —
   Flutter especially, given the audience.

### 6.6 Tasks (DONE)

- [x] **6.6.1 Python N=5 at 9 files** — **5/5 = 100%**.
- [x] **6.6.2 C++ N=5 at 9 files** — v1: 2/5 = 40%, v2 split: 4/5 = 80%.
- [x] **6.6.3 qwen2.5-coder:32b on dart-inventory N=5** — 0/5 = 0%, ceiling holds.
- [x] **6.6.4 Per-language static check between body and grading** — `LOOM_EXEC_STATIC_CHECK=1`.
- [x] **6.6.5 Worked-example demo** — `docs/WORKED_EXAMPLE.md`.
- [x] **6.6.6 Flutter multi-widget benchmark** — authored + run.
      6 trials on `qwen2.5-coder:32b`, 3/3 = 100% capability when
      the chain ran end-to-end. Naive 4/6 = 67% — pre-patch losses
      were Ollama keep_alive eviction races (fixed in commit
      `4c66c13`). Findings:
      [`FINDINGS-bakeoff-v2-flutter-counter.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-flutter-counter.md).

### 6.7 Pointers to data and code

- **Bake-off run summaries:** `experiments/bakeoff/runs-v2/`
- **Benchmarks:** `experiments/bakeoff/benchmarks/<lang>-<scope>/ground_truth/`
- **Drivers:** `experiments/bakeoff/v2_driver/`
- **Findings docs:** `experiments/bakeoff/FINDINGS-bakeoff-v2-*.md`

---

## Milestone 7: typelink (ROLLED BACK)

**Status:** Removed in commit `2599f15` after empirical validation
showed the verifier never intervened.

The hypothesis: a per-file public-API contract (extracted from
`*-contract` fenced blocks in the spec) would let `loom_exec`
catch surface drift between body-pass output and the spec's
declared shape, before grading. ~1300 LoC delivered: extractors
(Python ast, Dart regex), `Specification.public_api_json` field,
`Symbol`/`TypeContract` dataclasses, `type_contracts` ChromaDB
collection, post-task hook in `loom_exec`, CLI subcommands.

The rollout: 50+ trials with `LOOM_TYPELINK=1` produced
`typelink_fail = 0` across every run. The R1 lift in the python-
first smoke came entirely from Opus authoring contract-rich spec
text that gets injected into the executor's prompt via
`task_build_prompt` — *the contract reaches qwen whether or not
typelink parses it into structured form.*

The verifier hadn't earned its keep. ~1300 LoC removed in
`2599f15`. The data-plane lessons (contract-fence authoring is
the load-bearing part) are preserved in
[`FINDINGS-bakeoff-v2-milestone7.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-milestone7.md).

---

## Milestone 8: Python-first smoke series + cross-language map (DONE)

**Last updated:** 2026-04-30

After the Phase C cross-language ceiling work, a focused smoke
series isolated *what mechanism actually carries the lift* and
*how it generalizes across languages*. Headline result reframes
the Loom value claim.

### 8.1 D-smoke (R1 add a class) — delivery is the mechanism

5-cell A/B/C/D/E refactor smoke on `pyschema` library
(R1: add `RegexField`). 25 trials. Findings doc:
[`FINDINGS-bakeoff-v2-pythonfirst-smoke.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-pythonfirst-smoke.md).

| cell | acceptance | what's in Loom | spec → exec prompt |
|---|---|---|---|
| D0 greenfield | 99 % | full build spec | yes |
| D1 qwen-only | 0 % | placeholder | no |
| D2 stored, undelivered | **0 %** | seeded refactor spec | **no** |
| D3 standard delivery | **95 %** | seeded refactor spec | **yes** |
| D4 + LOOM_TYPELINK=1 | 100 % | seeded refactor spec | yes |

**D2 vs D3 = 0 % vs 95 %** — same data in store; only `task.context_specs`
differs. The +95pp lift comes entirely from the standard
`task_build_prompt` injection. The Loom value-add is in delivery, not
storage.

### 8.2 R2-smoke (rename) — Loom adds nothing when task is easy

Same 5-cell shape on `pubsub` library, R2 rename refactor. 25 trials.

D1 = D3 = 100 %. qwen3.5 alone handles a pure rename perfectly given
the file context + clear task title. Loom's pipeline cannot lift a
100 % baseline. **The R1 result is real but task-specific.**

### 8.3 Cross-session smoke (3 contrarian scenarios on Python)

Tests Loom's longitudinal claim: agent B reads agent A's stored
rationale via Loom and respects a constraint it would otherwise
contradict. 3 scenarios × 4 cells × N=5 = 60 trials. Findings:
[`FINDINGS-bakeoff-v2-crosssession.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-crosssession.md).

Result: **rule-alone saturates compliance at 100 % across all 3
scenarios** in Python. Adding `Requirement.rationale` field provides
zero measurable lift over the rule. Pre-registered hypothesis (rationale
> rule by ≥10pp) is not supported in Python.

### 8.4 Cross-language map (9 languages, S1 contrarian)

Direct port of S1 to 7 more languages (C++, C, Java, Go, Rust, JS,
TS) plus Asm (NASM x86-64). 180 trials. **The headline finding.**
[`FINDINGS-bakeoff-v2-cross-language-map.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-cross-language-map.md).

| language | off | on-rule | +placebo | +rat | regime |
|---|---|---|---|---|---|
| Python | 80 % | 100 % | 100 % | 100 % | already-saturated |
| Rust | 0 % | 100 % | 100 % | 100 % | rule-saturates **(+100 pp)** |
| Java | 0 % | 60 % | 100 % | 100 % | bridging |
| TypeScript | 0 % | 40 % | 80 % | 100 % | bridging-graduated ✓ |
| JavaScript | 0 % | 20 % | 40 % | 60 % | graded, no saturation |
| Go | 20 % | 60 % | 100 % | 60 % | volatile |
| C | 50 % | 50 % | 60 % | 60 % | resistant-mid |
| C++ | 0 % | 0 % | 100 %* | 67 % | collapsed |
| Asm | 0 % | 100 % | 100 % | 100 % | rule-saturates (+100 pp) |

**Off-cell fitness alone does NOT predict Loom lift.** Five languages
at off=0 % span the full Loom-response spectrum. The hidden variable
is qwen's "rule-followingness" in the language — a property of training
data + language characteristics, not raw fluency.

**Loom strong-fit zone:** Python, Java, TypeScript, Rust.
**Mixed:** JavaScript.
**Weak:** C, Go, C++.

### 8.5 Storage backend — SQLite swap

ChromaDB had intermittent cross-process flakiness ("hnsw segment
reader: Nothing found on disk") that bit the bakeoff harness.
Replaced with single-file SQLite + Python-side cosine NN
(commit `b8376d8`). 200/200 tests pass post-swap. 53KB single
file per project, inspectable with `sqlite3` CLI, zero new
dependencies (sqlite3 is stdlib). For Loom's actual scale (≤2k
vectors per collection in real projects), brute-force cosine is
faster than HNSW indexing — no approximation error, simpler code.

### 8.6 Recommended next experiments

1. **Rerun cross-language matrix with `qwen2.5-coder:32b`.** Most
   likely to shift C/Go/C++ from resistant to bridging at a higher
   model tier. Tests whether the regime pattern is qwen3.5-tier-
   specific.
2. **Re-run Go at higher N.** The +rat dropping below +placebo's
   100 % to 60 % is suspicious — N=10/20 would clarify.
3. **JS rule+rat at higher N.** The 60 % plateau is the most
   informative "graduated" result; tightening its CI would either
   confirm a real ceiling or reveal noise.
4. **S2 + S3 ports across languages.** Test whether per-language
   regime classification is stable across scenario types.

---

## Older feature work and contract data plane

`claude/bakeoff-v1` branch.
