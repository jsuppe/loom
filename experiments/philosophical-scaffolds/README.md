# Experiment: philosophical scaffolds for LLM reasoning

**Status:** thinking doc. No harness yet, no findings. This file captures
the open question, the conceptual frame we settled on after some
back-and-forth, and the design choices still up for grabs. Coming back
to this later means picking up where the brainstorm left off.

## The question

Can structured philosophical-argument scaffolds (Cartesian decomposition,
Socratic elenchus, Humean is/ought, Popperian falsifiability, etc.)
applied around an LLM's reasoning measurably improve the *legibility*
and *auditability* of conversational inference — and by extension, the
quality of artifacts Loom captures (requirements, rationales, conflicts)?

## The reframe (important)

The naive port — "use Cartesian methodic doubt to give the model
foundations" — does not survive contact with reality. The cogito works
because the doubter has a *logical commitment* to non-contradiction;
denying that you're doubting contradicts the act of denial. LLMs have
no such commitment. They contradict their own utterances routinely,
across turns and under mild reframing pressure. Non-contradiction is
not a binding constraint on next-token generation.

So: we are **not** building foundations. The model's "axioms" are just
confidently-asserted contingencies, and no amount of decomposition turns
contingent claims into necessary ones (Hume's old point, recycled).

What survives is the **Socratic / dialectical** angle. Socrates'
interlocutors contradicted themselves constantly — the elenchus *expects*
this and uses an external structure to surface it. Reframed for LLMs:
philosophical scaffolds are not a property the model holds, they are an
**audit loop around the model**. The research question becomes:

> Does structured external dialectic reduce contradiction rate, surface
> load-bearing assumptions, and improve the legibility of model output
> on tasks Loom cares about — relative to plain chain-of-thought?

That's empirical, gradable, and falsifiable.

## Typology: philosophical methods as audit moves

Each method is a different lens for exposing hidden structure in
reasoning. They are not competing metaphysics here, just different
audit moves you can apply to a transcript or use as a prompt scaffold.

| Method | Audit move | Signal it surfaces |
|---|---|---|
| Socratic elenchus | force definitions before claims | term drift across turns |
| Humean is/ought | flag normative claims smuggled from descriptive ones | unsupported "should" leaps |
| Popperian falsifiability | demand a falsifier for every claim | unfalsifiable mush |
| Wittgensteinian language-game | check term usage against domain rules | terms smuggled across contexts |
| Hegelian dialectic | construct strongest antithesis before synthesis | strawmanned opposition |
| Kantian universalizability | "would this rule hold if applied generally?" | local hacks dressed as principles |
| Stoic dichotomy of control | separate what's known from what's guessed | confidence/evidence mismatch |

## Measurable proxies (must pick one before harness)

The whole experiment lives or dies on this. "Better reasoning" is not
gradable. These are:

- **Contradiction rate** — count of self-contradictions a second LLM
  finds in an N-turn transcript. Lower is better.
- **Assumption-explicitness** — can a second agent recover the
  load-bearing claims from the transcript without seeing the prompt?
  Higher is better.
- **Counterfactual reversibility** — flip a key premise; does the
  conclusion track? Tracking is better (the reasoning was actually
  load-bearing on the premise).
- **Definitional stability** — does the model use a key term
  consistently across turns? A drift score, lower is better.
- **Downstream Loom outcomes** — does scaffolded rationale improve
  conflict-detection precision (`loom conflicts`) or the human-auditor
  agreement rate on `loom check` outputs? Loom-native, most directly
  useful, hardest to grade.

## Where this plugs into Loom

Loom is a near-perfect host for this:

- `--rationale` strings are exactly where unfaithful reasoning hides.
  A scaffold layer could **type** rationales: "passed falsifiability
  check," "derived via elenchus," "smuggles an ought." That typing
  becomes an audit dimension orthogonal to drift and conflict.
- `loom conflicts` could get sharper: two requirements that look
  textually compatible may rest on contradictory implicit assumptions
  an elenchus pass would surface. (Currently `conflict_verify.py` does
  an LLM verification pass — a scaffolded version would be a natural
  v2.)
- The intake hook (`hooks/loom_intake.py`) classifies incoming chat
  messages. A "needs philosophical scrubbing" branch is plausible for
  high-stakes domains (security, finance) where smuggled normative
  claims matter.

## Risks to name up front

1. **Philosophical theatre.** Scaffolds add ceremony and produce more
   text without moving any measurable outcome. Mitigation: pick a
   measurable proxy and a null hypothesis *first*, before writing the
   scaffold. Be willing to publish a null result.
2. **Confabulated foundations.** The model is excellent at producing
   plausible-sounding bedrock claims that aren't load-bearing. Don't
   treat any model-derived "axiom" as audited until the audit loop has
   actually run on it.
3. **Domain-specificity.** Falsifiability matters for empirical claims;
   universalizability matters for design rules. Applying the wrong
   lens produces noise. The typology must be matched to task shape.
4. **Cost.** Each scaffold is at minimum one extra LLM pass, often
   several. Budget vs. measured improvement has to clear a bar.

## Open design choices (still up for grabs)

- **Scope.** Narrow (one scaffold × one Loom task, bake-off vs. plain
  CoT) vs. broad (taxonomy + multiple scaffolds × multiple tasks)?
  Narrow is the existing experiments-dir norm and produces cleaner
  signal. Broad is more programmatic but risks vibes-only output.
- **Pairing.** First scaffold-task pairing to try? Candidates:
  - Socratic elenchus × `loom extract` rationale generation
  - Popperian falsifiability × requirement acceptance criteria
  - Hegelian dialectic × `loom conflicts` candidate verification
- **Grader.** Self-grading with a frontier model, human auditor, or
  programmatic check (e.g. counterfactual reversibility can be coded)?
  Programmatic is cheapest and most defensible.
- **Baseline.** Plain CoT? Loom's existing prompts? An ablation that
  removes only the scaffold but keeps everything else?
- **Models.** Local (qwen3.5, gpt-oss) so it lines up with `loom_exec`,
  or frontier (Opus/Sonnet) where reasoning capacity is less of a
  confound? Probably both — a scaffold that only helps the small model
  is interesting in a different way than one that helps both.

## Prior art to dig into when this becomes real

(Stub list — fill in before harness.)

- Self-consistency / self-refine / chain-of-verification literature.
  The scaffold idea is in this neighborhood and shouldn't reinvent.
- Constitutional AI: structurally adjacent — external rules applied to
  outputs — but the rules there are normative, not epistemic.
- Faithfulness-of-reasoning literature (does CoT actually drive the
  answer, or post-hoc rationalize it?). Counterfactual reversibility
  is borrowed from there.

## What "done" looks like for the next step

Not a harness yet. Next step is either:

1. Pick one scaffold × one Loom task × one measurable proxy, write a
   2-page protocol doc next to this one, then build a minimal harness
   modeled on `experiments/gaps/` or `experiments/pilot/`.
2. Decide the question isn't ready and let this doc sit until either
   the prior-art review or a concrete Loom pain point sharpens it.
