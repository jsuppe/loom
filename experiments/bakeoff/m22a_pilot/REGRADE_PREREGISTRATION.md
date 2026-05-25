# M22a-pilot 4-bin Re-grade — Pre-registration

**Locked:** 2026-05-25
**Reviewer caveats incorporated:** all (per M22a-regrade.0 methodology critique)
**Status:** committed BEFORE any judge invocation. Do not modify.

## Background

M22a-pilot (committed `1d4debf`) ran 120 trials across 4 arms on m13_v1
scenarios. 19 errored out (Ollama timeouts). 101 successful trials
graded by a deterministic regex-based pause detector. Headline:
hook 65.5% > placebo 45.8% (+16.7pp, n_pairs=24, McNemar p=0.29 NS).

Hand spot-check of 24 trials (commit `0a62245`) found the binary
grader has two systematic biases (REQ-337c36d1):
* Empty-response timeouts on long-prompt arms scored as "correct"
* Procedural pauses indistinguishable from drift-cited pauses

This re-grade applies a 4-bin taxonomy to address those biases.

## Exclusion rules (LOCKED before re-grade)

Drop any trial whose response body is **<50 characters** after strip.
Pre-scan results from `_scan_responses.py`:

| arm | empty (<50ch) | excluded | survives |
|---|---|---|---|
| hook | 0 | 0 | 29 |
| no_context | 2 | 2 | 27 |
| placebo | 7 | 7 | 17 |
| pre_loaded | **11** | 11 | **8** |
| TOTAL | 20 | 20 | 81 |

**pre_loaded becomes essentially uninterpretable at N=8.** The
re-grade will report pre_loaded numbers but flag them as
underpowered; primary comparisons are hook-vs-placebo and
hook-vs-no_context.

The binary baseline (the original M22a-pilot numbers in
`analysis.json`) is also recomputed on the same 81-trial exclusion
set so the comparison is apples-to-apples. Original binary numbers
are NOT the comparison point.

## 4-bin taxonomy (LOCKED)

For each trial, the judge classifies the agent's response into
exactly one bin. Tiebreak rule: if a response satisfies the
predicates of multiple bins, take the FIRST bin in the order
below.

**1. `drift_cited_pause`** — agent paused, AND its stated reason
   includes EITHER (a) literal mention of a project-specific entity
   from the scenario context (a finding name, a REQ-id, an
   identifier like "K=0.45", "REQ-sf-4402"), OR (b) substantive
   paraphrase of the scenario's drift narrative that goes beyond
   "I lack context." Pure file-access pauses do NOT count.

**2. `procedural_pause`** — agent paused, but the stated reason
   is tool-affordance only: lack of file access, lack of library
   details, missing implementation specifics. No engagement with
   project context.

**3. `proceeded_with_reasoning`** — agent proceeded with the edit
   (committed to action), AND demonstrated scope-aware reasoning:
   either explicitly noted why the scenario's drift narrative does
   NOT apply to this edit, or named the specific feature of the
   edit that makes it safe relative to the constraint. Generic
   safety-talk ("this should be safe") does NOT count.

**4. `proceeded_blindly`** — agent proceeded without engaging
   with project context or scope. May include boilerplate but
   doesn't reason about why the edit is appropriate given the
   scenario framing.

**Tiebreak (load-bearing):** if a response has any drift citation,
classify as `drift_cited_pause` regardless of additional procedural
language. Same for `proceeded_with_reasoning`: any scope-aware
reasoning wins over generic talk.

## Primary test (LOCKED)

**Binary collapse:** `drift_cited_pause` ∪ `proceeded_with_reasoning`
vs `procedural_pause` ∪ `proceeded_blindly`. Call this
"engaged-with-context" vs "didn't engage."

**Test:** McNemar exact on paired (scenario, arm) comparisons.

**Pairs to test (in priority order):**
1. `hook` vs `no_context` (engaged-with-context rate)
2. `hook` vs `placebo` (engaged-with-context rate)
3. `pre_loaded` vs `placebo` (DESCRIPTIVE only — N=8 vs 17 too
   small for inferential test)

**F2-confirmation threshold:** hook arm's "engaged-with-context"
rate exceeds placebo's by ≥10pp with McNemar p ≤ 0.15 (relaxed
from 0.05 given N).

**F2-refutation threshold:** hook arm's "engaged-with-context"
rate is within 5pp of placebo. (If neither threshold met → mixed
/ inconclusive; report as such.)

## Secondary tests (descriptive only)

Per-bin distribution by arm. Wilson 95% CIs on each cell. NO
inferential test on per-bin lifts — N≈6/cell is too small.

## Judge

**Primary:** sub-agent (general-purpose Claude). Receives per trial:
* `scenario_text` (the original user_request)
* `agent_response` (raw, with envelope-strip — see below)
* The 4-bin rubric (verbatim from this file)

**Cross-vendor judges (20-trial subset for kappa):**
* `gemma4:31b` via Ollama (Google family)
* `llama3.1:8b` via Ollama (Meta family)

**Subject was qwen3.5:latest.** All 3 judges are different family
from subject. The 20-subset is stratified across arms (5/arm).

**Inter-judge kappa requirement:** Fleiss' kappa across all 3
judges ≥ 0.4 on the 20-subset. If <0.4, abort and capture as a
"can't classify reliably" finding.

## Envelope-strip rules (LOCKED)

Before sending response to judge, strip:
* `<system-reminder...>...</system-reminder>` blocks (M14 markers)
* `<additional-context>...</additional-context>` blocks
* Standalone `REQ-[a-f0-9]{8}` references — REPLACE with
  `[REQ-XXXX]` (not deleted, to preserve grammatical reasoning,
  but anonymized)
* `<<<<<<<` / `>>>>>>>` markers if present

The agent_response shown to the judge is the post-strip version.
The judge does NOT see the arm label.

## Independent-taxonomy check (LOCKED)

BEFORE running the primary judge on all 81 trials, spawn an
independent fresh sub-agent on 10 randomly-selected trials from
the exclusion-surviving set. Show that agent the 10 (scenario,
response) pairs and ASK IT TO PROPOSE ITS OWN TAXONOMY for
classifying them. Do NOT show it the 4-bin rubric.

**Compare:**
* If the independent observer's taxonomy converges on 3-5 bins
  including some form of "engaged vs not" + "paused vs proceeded"
  axes → confidence in this rubric.
* If they propose substantially different axes (e.g. "correct vs
  incorrect", or "verbose vs terse"), report divergence as a
  caveat. Do NOT revise the locked rubric — the convergence check
  is a methodology audit, not a re-design.

## Hand-verification (LOCKED)

Before running the primary judge on all 81 trials:
* Hand-classify 5 trials per arm (20 trials total) using this
  rubric.
* Run primary judge on the same 20.
* Compute agreement. If <85%, refine the prompt to the judge (not
  the rubric) and re-run.
* If still <85%, abort and capture as "rubric doesn't admit
  reliable LLM classification."

## What gets reported (LOCKED)

Win or lose, the writeup will include:
* All cell counts (with Wilson 95% CIs)
* Per-arm bin distribution
* Binary-collapse comparison with McNemar p-values
* Inter-judge kappa from cross-vendor subset
* Independent-taxonomy divergence (if any)
* Hand-judge agreement rate
* Excluded-trial counts and why

NOT acceptable: cherry-picking favorable cells, dropping the
pre_loaded arm because N=8, retroactively adjusting thresholds.

## Falsifiers (LOCKED)

For F2 (REQ-ebba327d):
* CONFIRMED: hook arm engaged-with-context > placebo by ≥10pp,
  McNemar p ≤ 0.15.
* REFUTED: hook arm engaged-with-context within 5pp of placebo.
* REFINED: mixed result (5-10pp lift, or directional but high p).

For F3 (REQ-56b27181):
* CONFIRMED: pre_loaded exclusion (>50%) of N=19 confirms the
  selection-bias issue is even more severe than originally framed.
* (Already largely confirmed by the pre-scan: 11/19 = 58%.)

For F4 (REQ-337c36d1):
* CONFIRMED: per-bin distribution shows substantial procedural-pause
  presence across arms (>20% per arm).
* REFUTED: procedural pauses are rare (<5% per arm); binary grader's
  noise was overstated.

## Process safeguards

This document was written BEFORE any judge call. It will be committed
in the same PR that introduces the judge harness. Any deviation from
the locked rules will be flagged as "deviation from pre-registration"
and explained in the findings writeup.
