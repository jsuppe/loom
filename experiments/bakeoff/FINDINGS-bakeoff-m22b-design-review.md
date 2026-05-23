# M22b Design Review — Pivot to Capture-Only (γ)

**Date:** 2026-05-23
**Status:** Designed; methodology-reviewed; NOT RUN
**Reviewer verdict:** Refused to launch as designed
**User decision:** γ — capture the methodology finding, stop

## What was proposed

After M22a-pilot, the M22a arc had three forward paths:
* α — scale up on m13_v1 at higher timeout (single-file workload)
* β — pivot to multi-file typelink workload (addresses M22a Flaw B)
* γ — stop, capture pilot findings

User picked β. The proposed M22b-pilot design:

* **Workload:** `experiments/bakeoff/benchmarks/cpp-inventory/` (13-file C++ project).
  Each scenario regenerates ONE FILE in context of the rest (other 12 from `ground_truth/reference/`).
* **Files:** 3 typelink-failure-shaped files (customer_service.cpp, inventory_service.cpp, persistence.cpp).
* **Four arms** (parallel to M22a-pilot): no_context / hook / pre_loaded / placebo (length-matched).
* **Subject:** qwen3.5:latest via Ollama, temp=0.
* **N:** 5 trials × 4 arms × 3 files = 60 trials. ~30-60 min wall, $0 cost.
* **Grading:** deterministic. Manifest's `test_command` (g++ compile+link) + `run_command`.
* **Methodology review:** spawn fresh sub-agent before building (D10 Role 1, same pattern that earned its keep on M22a.0).

## What the reviewer caught

The methodology-review sub-agent identified **three blockers** that would have invalidated the study:

### Blocker 1 — Factual error in the proposed injection text

The design specified the hook would inject `register_customer(name, email, address)`. The actual reference signature is `register_customer(id, name, email)`. The reviewer verified by reading `ground_truth/reference/include/services/customer_service.hpp`. If the harness had been built as written, the hook arm would have injected a wrong signature and failed systematically — the result would have been "hook makes things worse," and the conclusion would have been wrong.

### Blocker 2 — Structural confound: "the context contains the answer"

The hook arm as designed injects the literal function signature. But loom's actual value proposition is **rationale-mediated**, not fact-mediated:

* Fact-based injection: *"register_customer takes (id, name, email)"*
* Rationale-based injection: *"we standardized on id-first parameters across services for cross-service joining"*

The two are different studies:

* "Does putting the answer in the prompt help?" → trivially yes; uninteresting
* "Does putting the rationale that constrains the answer in the prompt help?" → loom's actual claim

The proposed design would have measured the first while claiming the second. The reviewer's fix: split `hook` into three variants (`hook-rationale`, `hook-signature`, `hook-both`) and treat only `hook-rationale` as the load-bearing comparison.

### Blocker 3 — The 12 reference files include the matching header

When a trial regenerates `customer_service.cpp`, the workspace ships `customer_service.hpp` from the reference solution. The header declares the exact signature the model needs to match. **The typelink failure mode that motivated the workload CAN'T HAPPEN** under this setup — the floor is artificially high.

Fix: hide the matching header for the file being regenerated, OR ship a stale/conflicting header that loom-rationale arbitrates.

## Other notable critiques

* **cpp-inventory has only 4 multi-file failures** in the audit. Slicing the smallest typelink corpus 3 ways isn't a workload. Dart benchmarks (12 dart-orders, 9 dart-inv failures) are the dominant typelink corpus.
* **Binary PASS/FAIL is too coarse.** Should use 4-bin outcome (compile_fail / link_fail / tests_fail / tests_pass) plus per-trial sub-test pass-rate (28 sub-tests / trial).
* **N=5/cell × ~80% base failure rate = detection floor ~30pp.** Same underpowering as M22a-pilot.
* **`<system-reminder>` and `REQ-shop-signatures` markers** are condition-identifying flags any judge would see.
* **`<list other files>` in the bare arm** leaks structure via filenames alone.
* **Path leak:** the hook cited `test/shop_test.cpp:42-50` but that file IS in the reference shipment.

## Decision: γ

The user picked γ — stop, capture the methodology finding. Rationale:

1. The conceptual insight (rationale vs fact injection) is the most important single finding from EITHER pilot's methodology review. It changes how loom-effectiveness studies must be designed.

2. Running a partially-fixed version (β-minimal — fix factual error + hide matching .hpp + ship `hook-rationale` only) would still cost ~1 day and would test a different claim than originally scoped, with results that depend entirely on whether a "rationale that doesn't contain the answer" can be written meaningfully for typelink contracts. For `register_customer`, the rationale IS substantially the signature contract.

3. The methodology-review-before-launch pattern (D10 Role 1) has now caught structurally fatal designs in both M22a.0 and M22b.0. The pattern itself is the validated contribution.

## Findings captured (kind=finding)

* **REQ-xxxxxxxx — "Context-injection studies of loom-augmentation must use rationale-only arms"** —
  derives from REQ-b235f905 (the M22a methodology-review meta-finding). The structural insight: a hook arm that injects the literal fact (signature, threshold, definitive claim) measures "answer-in-prompt" not "loom rationale delivery." Loom's actual value prop requires the captured rationale to *constrain* the answer without *being* the answer. Future M22-shape studies must define a rationale-only arm as the primary comparison.

* **REQ-xxxxxxxx — "Multi-file augmentation studies must hide the artifact being tested"** —
  the reference-file leak. When the workload is "regenerate file X in context of the rest," the workspace MUST exclude any sibling file that contains the answer (headers, type declarations, sibling files that reference X with the correct contract). Otherwise the failure mode can't manifest.

## What's still open

* Whether to attempt a properly-designed M22c later (Dart benchmark, rationale-only arms, hidden headers, 4-bin grading). On the queue but not committed.
* The M22a arc is closed for now. The honest deliverable is: pilot found suggestive positive direction for hook delivery beyond token-count (REQ-ebba327d); methodology refinement showed that follow-up studies must test rationale, not facts.

## Files

* `experiments/bakeoff/FINDINGS-bakeoff-m22b-design-review.md` (this doc)
* M22b-pilot HARNESS was not built; no `experiments/bakeoff/m22b_pilot/` directory exists by design.
