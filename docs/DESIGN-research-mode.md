# Design — Loom in research mode (proposed M12)

**Status:** sketch, not committed. Grounded in real friction
encountered during the M11 dogfooding pass on 2026-05-03.
**Companion artifacts:**
- `experiments/pilot/dogfood_lessons.py` — capture pass
- `experiments/pilot/dogfood_link_harnesses.py` — link pass
- `experiments/pilot/dogfood_friction.md` — raw friction log
- `experiments/pilot/dogfood_lessons_mapping.json` — lesson → req_id

## Why this exists

Loom was designed for software-development workflows: capture
imperative requirements ("X must do Y"), link to code, detect drift.
The M10/M11 work doing prompt-engineering research surfaced a
different shape: capturing research findings, methodology decisions,
hypotheses, and process rules. We tried using current Loom for this
work and dogfooded the M11 capture mechanism on the 9 lessons that
emerged. The friction is real, and below.

## The seven friction points dogfooding surfaced

### 1. Findings don't fit "imperative requirement" shape

The lessons we captured are findings ("we observed that rationale
is load-bearing"), not requirements ("Loom requirements MUST
include rationale"). To fit the current model we had to invert each
finding into an imperative recommendation. That works but loses the
distinction between *what we observed* and *what we recommend*.

The actual finding: "Bare-rule requirements produce 0% compliance
on contrarian specs."
The forced imperative form: "Loom requirements MUST include
rationale to avoid 0% compliance failures."

These are related but distinct. The first is a measurement; the
second is a derived recommendation. Conflating them in a single
field hides the experimental provenance.

### 2. No `kind` field to distinguish capture types

Real projects mix kinds:

| kind | example | drift target |
|---|---|---|
| `requirement` (current) | "Users must confirm before deleting" | code |
| `finding` | "Rationale is load-bearing on contrarian specs" | harness scripts + summary data |
| `methodology` | "Use phQ6 conditions for rationale ablations" | future harness files |
| `hypothesis` | "Anti-rationale will collapse to placebo" (was wrong) | corresponding finding's confirmation |
| `process_rule` | "All experimental findings must be retained in github" | git state |

Currently all of these are `Requirement` rows that look identical
in `loom list`. No way to filter, render separately, or apply
kind-specific lifecycle rules.

### 3. The intake classifier noops on findings

24 intake hook fires this session. 22 noops. The classifier was
trained on imperative requirements ("X must do Y") via the M11.5 P0
pilot's labeled dataset. Statements like "we found that rationale
is load-bearing" don't match the trained shape — they get classified
as not-a-requirement and dropped.

This is the original product-fit gap. The classifier needs either
broader training data OR a separate kind-aware classifier branch.

### 4. stdin encoding bug in `loom extract`

**Real bug, not just a design gap.** When `loom extract` reads value
text from stdin on Windows, non-ASCII characters get corrupted via
a UTF-8 / CP1252 transcoding mixup. An em-dash `—` (U+2014) entered
as a 3-byte UTF-8 sequence got read back as `â€"` (3 separate
CP1252 characters).

Symptom in the dogfooding pass: my pre-computed deterministic req_id
didn't match the actually-stored req_id, so the linker pass couldn't
find the requirement when given the user-supplied (uncorrupted) ID.

```
Predicted (from clean text):  REQ-92b4c153
Stored (from corrupted text): REQ-a636de03
```

**Fix shape:** force UTF-8 stdin reading in `loom.cli.cmd_extract`.
Set `sys.stdin.reconfigure(encoding="utf-8")` early, or use
`sys.stdin.buffer.read().decode("utf-8")` explicitly. Same fix
pattern as the M0.5c stdout reconfig.

### 5. `loom chain` doesn't traverse rationale_links

We built the M11.1 rationale-link DAG for exactly this purpose — to
chain decisions across time. After capture, the rationale_link graph
is in the store. But `loom chain REQ-x` only walks
patterns/specifications/implementations, not rationale_links. So
querying "what's the chain from this lesson back to its parent
findings?" doesn't work.

**Fix shape:** extend `services.chain` to include a `rationale_chain`
field showing transitive `rationale_links` ancestors. Render in
`loom chain` output and add to the JSON shape.

### 6. Linking harness scripts uses the same mechanism as linking implementing code

`loom link <file> --req REQ-X` was designed for "this code file
satisfies/implements this requirement." It records an
`Implementation` row with `satisfies: [REQ-X]`.

We used the same command to express "this harness file *provides
evidence for* this finding." Conceptually different relationship —
the harness doesn't *implement* the finding the way code implements
a requirement. It *demonstrates* it.

The implications differ:
- For code-implements-req: drift = code changed without req
  changing, action = audit code
- For harness-evidences-finding: drift = harness changed (new
  experiment), action = re-evaluate finding's confidence

Same data shape, different semantics. The tooling can't currently
tell them apart.

### 7. No `FINDINGS.md` or `METHODOLOGY.md` generator

`loom sync` produces REQUIREMENTS.md and TEST_SPEC.md. The 9 captured
lessons in the loom store render as a flat list under `## Behavior`
and `## Architecture` headers — indistinguishable from
implementation requirements. The PROMPT-ENGINEERING-LESSONS.md doc
remains hand-edited, which is exactly the M11 anti-pattern (decision
rationale captured in ad-hoc markdown rather than the structured
store).

**Fix shape:** with a `kind` field, add `loom sync` renderers per
kind. `kind=finding` → FINDINGS.md with experimental provenance.
`kind=methodology` → METHODOLOGY.md. Etc. Or one consolidated
`KNOWLEDGE.md` grouped by kind.

## Proposed M12 sub-milestones

### M12.1 — `Requirement.kind` field

Single new optional field, backward-compat via setdefault:

```python
@dataclass
class Requirement:
    ...
    kind: str = "requirement"  # requirement | finding | methodology | hypothesis | process_rule
```

`VALID_KINDS = ("requirement", "finding", "methodology", "hypothesis", "process_rule")`.
Validated at extract / set_kind. Defaults to "requirement" so existing
data and callers keep working.

CLI: `loom extract --kind finding` (or `--as finding` for short).
`loom list --kind finding` filter.

Cost: ~80 LoC + tests.

### M12.2 — Per-kind renderers + lifecycle states

Each kind gets its own:
- Rendered output file (`REQUIREMENTS.md` / `FINDINGS.md` /
  `METHODOLOGY.md` / `PROCESS-RULES.md`)
- Status enum (e.g. finding has `hypothesis|confirmed|falsified|refined|superseded`)
- Drift-detection target hint

Cost: ~150 LoC across docs.py + status validation + tests.

### M12.3 — stdin encoding fix in `loom extract`

Single-line fix per the bug analysis above. Should be a tiny
defensive change, plus a test that covers an em-dash round-trip.

Cost: ~10 LoC + 1 test.

### M12.4 — `loom chain` traverses rationale_links

Extend `services.chain` to include rationale_link traversal with
cycle protection (already implemented in M11.1's
`_validate_rationale_links` — reuse the BFS).

Cost: ~30 LoC + tests.

### M12.5 — Kind-aware classifier (intake hook)

Extend the M11.5 classifier prompt to return `kind` as well as
`is_requirement`/`is_capturable`. Train (or hand-prompt) for each
kind. The intake hook routes to kind-appropriate branches:
- `requirement`: current behavior (auto-link or propose)
- `finding`: capture with rationale_link chain to prior findings
  if any related; otherwise capture with the empirical claim as
  rationale source
- `methodology`: capture with project-state link instead of
  prior-decision link
- `process_rule`: like requirement but renders separately

Cost: ~150 LoC + 50-utterance hand-labeled extension to the M11.5 P0
dataset for the new kinds.

### M12.6 — `evidences` link type alongside `satisfies`

Distinguish "this code implements this requirement" from "this
file evidences this finding." Add an `evidences` list to
`Implementation` parallel to `satisfies`. Drift detection treats
them differently:
- `satisfies` drift → audit the code against the requirement
- `evidences` drift → re-evaluate the finding's confidence

CLI: `loom link <file> --evidences REQ-X` (vs current `--req`).

Cost: ~70 LoC + tests.

## Implementation order

```
M12.1 (kind field)
  │
  ├──── M12.2 (per-kind renderers + lifecycle)
  ├──── M12.4 (chain traversal)
  └──── M12.5 (kind-aware classifier)
            │
            └──── M12.6 (evidences link type)

M12.3 (stdin encoding) — independent, ship anytime
```

Recommended: ship M12.3 first as a bug fix (cheap, high-impact for
correctness). Then M12.1 as the foundation. Then 2/4/5 in parallel.
M12.6 last — it's the most semantically opinionated change.

## Decisively-validated friction (do these regardless)

The two friction points that DON'T require M12 to address:

1. **PROMPT-ENGINEERING-LESSONS.md should be auto-generated** —
   even before M12 ships, the lessons are now in the loom store
   (REQ-73a0d7de meta + REQ-ec36bd89 L1 + 8 others). A small
   generator could replace the hand-edited markdown with a
   regenerated one keyed by kind=finding (or, pre-M12, by
   custom-kind-tag in the rationale field).

2. **Loom should be used in research mode going forward.** Even
   without M12's full kind support, capturing findings as Loom
   reqs (with the imperative-inversion workaround) is better than
   not capturing them at all. Continue dogfooding.

## Open questions

1. **Should `kind` affect drift-check semantics?** A `finding`
   linked to a harness file: if the harness changes, the finding's
   confidence is in question, not the harness. Different message
   shape than current drift output.

2. **Should the intake classifier be unified or per-kind?** One
   classifier with a `kind` output field is simpler. Per-kind
   classifiers (sequential or routed) might hit higher precision
   per-kind. Untested.

3. **Should `Requirement` be renamed?** With multiple kinds, the
   class name "Requirement" is misleading. Rename to
   `CapturedDecision` or similar? Big breaking change, not
   recommended for v1.x. Probably accept the misleading name and
   note in the docstring.

4. **Should `loom sync --public` filter by kind?** Findings and
   methodology might be private (internal R&D); requirements and
   process-rules might be public-shareable. Per-kind privacy
   defaults could be useful but adds complexity. Defer until
   asked.
