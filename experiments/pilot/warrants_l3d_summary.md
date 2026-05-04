# Falsifiability@v1 — Phase L3d evaluation

**Model:** `ollama:qwen3.5:latest`  
**Started:** 2026-05-04T14:00:08.586306+00:00  
**Finished:** 2026-05-04T14:02:54.427933+00:00  

## Acceptance summary

| Cut | Threshold | Result | Verdict |
|---|---|---|---|
| 1 — canary FP | 0/5 false positives | 0/5 | PASS |
| 2 — sample pass rate | informational | 4/17 = 23.5% | n/a |
| 2 — bimodality | bimodal preferred | outer/inner = 3.25 | bimodal |

**Overall L3d acceptance:** PASS

## Score distribution (sample)

| Bin | Count |
|---|---|
| 0.00-0.25 | 9 |
| 0.25-0.50 | 4 |
| 0.50-0.75 | 0 |
| 0.75-1.00 | 4 |

## Cross-validator agreement (Toulmin@v1 × Falsifiability@v1)

| cell | count | members |
|---|---|---|
| both pass | 2 | REQ-0a83d16a, REQ-a636de03 |
| toulmin only | 1 | REQ-2a621c40 |
| falsifiability only | 2 | REQ-5e01462c, REQ-a9df428e |
| neither | 11 | REQ-0023dae0, REQ-5c9db026, REQ-65f50316, REQ-73a0d7de, REQ-763cd262... |

## Per-canary outcome

| ID | category | actual_score | passes | actual_reason |
|---|---|---|---|---|
| fcanary-1-aspiration | vague_aspiration | 0.00 | rejected | The claim is an aspiration regarding code quality ('clean architecture') without specifyin |
| fcanary-2-tbd | placeholder | 0.00 | rejected | The rationale is a placeholder ('TBD') that offers no observable failure mode, test, or co |
| fcanary-3-confidence | ungrounded_confidence | 0.00 | rejected | The rationale relies solely on a confidence assertion ('Trust me') and vague aspiration (' |
| fcanary-4-judgment | subjective_no_test | 0.00 | rejected | The rationale relies on the vague aspiration of 'better judgment' without specifying any o |
| fcanary-5-feel | subjective_no_threshold | 0.00 | rejected | The claim relies on subjective user perception ('feel performant') without defining any me |

## Per-sample outcome

| req_id | kind | score | passes | reason |
|---|---|---|---|---|
| REQ-0023dae0 | finding | 0.00 | fail | The rationale describes a specific bug behavior (spurious warnings) but fails to |
| REQ-0a83d16a | finding | 0.75 | **PASS** | The rationale explicitly describes a specific observable outcome (0% coverage wa |
| REQ-2a621c40 | requirement | 0.25 | fail | The rationale asserts a performance lift and a preference for 'PASS' labels over |
| REQ-4d3e74f2 | finding | 0.00 | fail | llm_error: RuntimeError: Ollama call failed: timed out |
| REQ-5c9db026 | finding | 0.00 | fail | The rationale makes a definitive claim about reliability and independence but pr |
| REQ-5e01462c | finding | 0.75 | **PASS** | The rationale specifies a clear empirical test (N≥10 per condition) and a replic |
| REQ-65f50316 | requirement | 0.00 | fail | The rationale presents absolute performance claims ('0% compliance', '100% compl |
| REQ-73a0d7de | finding | 0.00 | fail | The rationale presents a specific empirical finding (95% compliance vs 0%) but f |
| REQ-763cd262 | finding | 0.00 | fail | The rationale describes a surprising empirical observation but fails to specify  |
| REQ-8eb5fca7 | requirement | 0.25 | fail | The rationale relies on a qualitative observation ('almost matches', 'not even g |
| REQ-a636de03 | requirement | 0.90 | **PASS** | The rationale provides explicit numerical thresholds (100% vs 0%, 60% each) and  |
| REQ-a9df428e | finding | 0.75 | **PASS** | The rationale provides an implicit falsifier by specifying a replication boundar |
| REQ-aaa595ca | requirement | 0.25 | fail | The rationale relies on specific empirical observations to derive a conditional  |
| REQ-ab5b84b0 | finding | 0.25 | fail | The rationale relies on a subjective preference ('PASS labels outperform bare as |
| REQ-c0e06e44 | process_rule | 0.00 | fail | The rationale is a procedural directive about data retention rather than a claim |
| REQ-e4d6f7d4 | process_rule | 0.00 | fail | The rationale describes a procedural discipline and justifies a rule based on pa |
| REQ-ec36bd89 | requirement | 0.00 | fail | The rationale presents specific numerical results (percentages, point lifts) but |