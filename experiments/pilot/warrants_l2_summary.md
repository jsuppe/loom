# Toulmin@v1 — Phase L2 evaluation

**Model:** `ollama:qwen3.5:latest`  
**Started:** 2026-05-04T12:04:23.321872+00:00  
**Finished:** 2026-05-04T12:04:47.123781+00:00  

## Acceptance summary

| Cut | Threshold | Result | Verdict |
|---|---|---|---|
| 1 — canary FP | 0/5 false positives | 0/5 | PASS |
| 2 — sample pass-rate band | 30–60% | 6/19 = 31.6% | PASS |
| score distribution | bimodal preferred | outer/inner = 8.50 | bimodal |

**Overall L2 acceptance:** PASS

## Score distribution (sample)

| Bin | Count |
|---|---|
| 0.00-0.25 | 11 |
| 0.25-0.50 | 0 |
| 0.50-0.75 | 2 |
| 0.75-1.00 | 6 |

## Per-canary outcome

| ID | category | actual_score | passes | actual_reason |
|---|---|---|---|---|
| canary-1-empty-restate | non_justification | 0.00 | rejected | The rationale is a placeholder ('Because we wanted to') that lacks any factual evidence (D |
| canary-2-tbd | placeholder | 0.00 | rejected | The input contains only the placeholder 'TBD' and lacks any data, warrant, qualifier, or r |
| canary-3-confident_assertion | ungrounded_claim | 0.00 | rejected | The input is a bare assertion lacking any data, warrant, qualifier, or rebuttal. |
| canary-4-tautology | tautology | 0.00 | rejected | The rationale is a tautology that restates the requirement as the reason for its existence |
| canary-5-restated-what | what_as_why | 0.00 | rejected | The rationale is a tautology that restates the requirement as the reason without providing |

## Per-sample outcome

| req_id | kind | score | passes | reason |
|---|---|---|---|---|
| REQ-0023dae0 | finding | 0.00 | fail | The input is a bare assertion stating a problem exists without providing any spe |
| REQ-0a83d16a | finding | 0.75 | **PASS** | The rationale provides specific empirical data about the Loom doctor's behavior  |
| REQ-2a621c40 | requirement | 0.75 | **PASS** | The rationale provides specific empirical data (the +40pp lift) and a warrant (c |
| REQ-44283927 | requirement | 0.75 | **PASS** | The rationale provides specific evidence (data) regarding the classifier's perfo |
| REQ-5c9db026 | finding | 0.50 | fail | The rationale provides specific experimental data (N=60 phT, N=50 phU) but lacks |
| REQ-5e01462c | finding | 0.00 | fail | The input is a bibliographic citation listing source files and a summary of expe |
| REQ-65f50316 | requirement | 0.50 | fail | The rationale provides specific experimental data comparing bare rules versus ra |
| REQ-73a0d7de | finding | 0.00 | fail | The text is a bare assertion stating a finding without providing any supporting  |
| REQ-763cd262 | finding | 0.00 | fail | The input is a bare assertion stating a surprising experimental finding without  |
| REQ-8eb5fca7 | requirement | 0.00 | fail | The text is a meta-commentary on experimental results and prose quality rather t |
| REQ-a521b281 | requirement | 0.75 | **PASS** | The rationale provides specific performance data (95.2% precision) and a warrant |
| REQ-a636de03 | requirement | 1.00 | **PASS** | The rationale provides specific experimental data points (compliance percentages |
| REQ-a9df428e | finding | 0.00 | fail | The input is a metadata header listing source files and a high-level implication |
| REQ-aaa595ca | requirement | 0.00 | fail | The text is a bare assertion of a conclusion without providing specific data, ev |
| REQ-ab5b84b0 | finding | 0.00 | fail | The text is a bare assertion stating that PASS labels outperform bare assertions |
| REQ-c0e06e44 | process_rule | 0.00 | fail | The input is a bare assertion stating a requirement without providing any suppor |
| REQ-d9e6ba58 | requirement | 0.75 | **PASS** | The rationale provides specific evidence (data) about the classifier's behavior  |
| REQ-e4d6f7d4 | process_rule | 0.00 | fail | The text describes a meta-discussion about the need for evidence and the costs o |
| REQ-ec36bd89 | requirement | 0.00 | fail | The text is a list of experimental results and feature comparisons without any e |