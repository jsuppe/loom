# M19v3.1 — Tight (file, req) Link Candidates

**For user review before lock.** Per pre-reg, M19v3.1 surfaces a
candidate list and the user picks the final 20 (or fewer if some
are rejected).

Confidence labels:
* **TIGHT** — req text directly captures the file's primary intent; competent reviewer would agree
* **MODERATE** — fits a meaningful aspect of the file but file has other concerns too
* **EVIDENCE** — file IS evidence/data for the linked finding-kind REQ (legitimate evidence-link)

Loom-self has only 17 `requirement`-kind REQs total, so the available
pool of tight fits is structurally limited. Below is the honest list,
not padded.

## TIGHT candidates (8)

| # | File | Req | Confidence | Rationale |
|---|---|---|---|---|
| 1 | `src/loom/indexers_js.py` | REQ-2a621c40 | TIGHT | Req: "JsIndexer (and similar LSP-backed indexers) MUST be pointed at the project root including test files." File IS the JsIndexer implementation. |
| 2 | `src/loom/indexers_py.py` | REQ-2a621c40 | TIGHT | Same req (covers "similar LSP-backed indexers"). PyIndexer follows the same pattern. |
| 3 | `src/loom/intake.py` | REQ-ec36bd89 | TIGHT | Req: "Loom requirements MUST include rationale (prose or rationale_links). Bare-rule reqs without rationale rejected." The intake hook enforces exactly this at capture time. |
| 4 | `src/loom/exec_cli.py` | REQ-aaa595ca | TIGHT | Req: "Loom executor selection MUST consider spec contrarian-shape, not just language." File is the loom_exec executor; executor-selection IS its concern. |
| 5 | `src/loom/driftgraph_http.py` | REQ-6c353203 | TIGHT | Req: "use a push-based webhook architecture for foundation drift events." driftgraph_http is the push/webhook surface. |
| 6 | `experiments/bakeoff/sampling.lock` | REQ-019da056 | TIGHT | Req: "Bake-off harnesses MUST lock sampling parameters (temperature, top_p, seed, max_tokens) and record them..." File IS the locked sampling artifact. |
| 7 | `experiments/bakeoff/_methodology.py` | REQ-1d49ce5b | TIGHT | Req: "Bake-off harnesses MUST retain every model response as a separate file alongside the trial summary..." File implements `retain_output` + related methodology helpers. |
| 8 | `src/loom/testspec.py` | REQ-c9fb1238 | TIGHT | Req: "We should create an evaluation set of tasks to track changes." File implements the TestSpec store (JSON-backed). |

## MODERATE candidates (5)

| # | File | Req | Confidence | Rationale |
|---|---|---|---|---|
| 9 | `src/loom/indexers.py` | REQ-2a621c40 | MODERATE | Same req as #1/#2. File is the indexer REGISTRY (abstract surface), not a specific LSP indexer. Could argue the file is meta-infra. |
| 10 | `src/loom/intake_filters.py` | REQ-ec36bd89 | MODERATE | Same req as #3. File implements specific filter detectors (softener detection, domain whitelist, daily budget) supporting the rationale-required rule. |
| 11 | `src/loom/driftgraph_cache.py` | REQ-6c353203 | MODERATE | Same req as #5. File caches driftgraph webhook events; supports the push architecture indirectly. |
| 12 | `src/loom/driftgraph_query.py` | REQ-6c353203 | MODERATE | Same req as #5. File queries driftgraph's Neo4j directly (Architecture B); related to the webhook architecture but different concern. |
| 13 | `src/loom/store.py` | REQ-27023c4b | MODERATE | Req: "The system must maintain a log to enable tracking back on previous information or decision." store.py IS the SQLite-backed log; broader than just "log" but close. |

## EVIDENCE candidates (8) — link_type=evidences

These are findings docs / results files linking to the finding-kind
REQ they document. Drift on these files = "the documented finding
content changed," which is genuinely meaningful for the linked finding.

| # | File | Req | Confidence | Rationale |
|---|---|---|---|---|
| 14 | `experiments/bakeoff/m22c_pilot/M22C_PILOT_FINDINGS.md` | REQ-9f24f46e | EVIDENCE | File IS the M22c pilot finding writeup. |
| 15 | `experiments/bakeoff/m22e_pilot/M22E_PILOT_FINDINGS.md` | REQ-73bcd158 | EVIDENCE | File IS the M22e pilot finding writeup. |
| 16 | `experiments/m19_drift_eval/M19_FINDINGS.md` | REQ-56811be1 | EVIDENCE | File IS the M19v1 finding writeup. |
| 17 | `experiments/m19_drift_eval/M19V2_FINDINGS.md` | REQ-6834d5b6 | EVIDENCE | File IS the M19v2 finding writeup. |
| 18 | `experiments/bakeoff/m22a_pilot/REGRADE_PREREGISTRATION.md` | REQ-40b70660 | EVIDENCE | File IS the M22a-regrade pre-reg; finding is the 4-bin re-grade result. |
| 19 | `experiments/bakeoff/m22c_pilot/M22C_PREREGISTRATION.md` | REQ-9f24f46e | EVIDENCE | Pre-reg authored for the M22c result; legitimate evidence link. |
| 20 | `experiments/bakeoff/m22e_pilot/M22E_PREREGISTRATION.md` | REQ-73bcd158 | EVIDENCE | Pre-reg authored for the M22e result. |
| 21 | `experiments/bakeoff/m22c_pilot/scenarios.json` | REQ-9f24f46e | EVIDENCE | Locked scenarios that produced the M22c finding. |

## REJECTED (not surfaced as candidates) — why

These were considered but rejected:

* `src/loom/services.py` — no single req captures the multi-concern services layer (touchpoints, link, check, query, sync, doctor, metrics, …). Would be too loose.
* `src/loom/cli.py` — no req captures "CLI dispatcher" as such.
* `src/loom/embedding.py` — no req about embedding pluggability.
* `src/loom/runners.py` — no req about test-runner registry.
* `src/loom/conflict_verify.py` — no req about LLM-verified conflict.
* `src/loom/docs.py` — no req about doc generation.
* `src/loom/templates.py` — no req about scaffolding templates (would link to a *feedback* memory not a loom REQ).
* `src/loom/warrants.py` — no req about HMAC warrant client.
* `src/loom/config.py` — no req about config precedence.
* `src/loom/paths.py` — too small + no req.
* Any link to recently-captured finding-kind REQ that isn't an evidence file (per M19v2 finding: vocabulary-overlap noise).

## User decisions before lock

Three open decisions per the pre-reg:

1. **Which of the 21 candidates to include in the final lock?**
   * Recommend: include all 13 TIGHT+MODERATE for the source-impl
     side, all 8 EVIDENCE for the evidence-link side = N=21 (close
     to the 20 target). If you want to drop any, name them.
   * Or: include only the 8 TIGHT + 8 EVIDENCE = N=16 (cleaner
     interpretation, smaller sample).
2. **Loose M19v2 links cleanup?** Pre-reg default is "leave parallel"
   (M19v3 reads only from `tight_links.lock`). Confirm or override.
3. **Predicted band 30-60%?** Confirm or adjust BEFORE locking.

After your decisions, I'll write `tight_links.lock` and move to
M19v3.2 (harness adaptation).
