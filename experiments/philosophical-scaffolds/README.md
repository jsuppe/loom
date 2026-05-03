# Experiment: philosophical scaffolds for LLM reasoning

**Status:** thinking doc / research-program proposal. No harness yet, no
findings. This file captures the conceptual arc developed over a
brainstorming session on branch `claude/philosophical-llm-reasoning-wjmyj`.
It is meant to read cold for someone who wasn't in the conversation —
including handoff to collaborators or other agents working on adjacent
projects (notably `jsuppe/sdr-graph-memory`, see "Integration with
sdr-graph-memory" below).

## The original question

Can structured philosophical-argument scaffolds (Cartesian decomposition,
Socratic elenchus, Humean is/ought separation, Popperian falsifiability,
etc.) applied around an LLM's reasoning measurably improve the
*legibility* and *auditability* of conversational inference — and by
extension, the quality of artifacts Loom captures (requirements,
rationales, conflicts)?

The seed observation: in Descartes' *Meditations*, "I think, therefore
I am" emerges from structured decomposition (methodic doubt). Could a
similar structured-decomposition scaffold give an LLM a fundamental
basis from which higher-level reasoning could be built?

## Why the Cartesian port fails

The naive port — "use methodic doubt to give the model foundations" —
does not survive contact with how LLMs actually behave. The cogito works
because the doubter has a *logical commitment* to non-contradiction;
denying that you're doubting contradicts the act of denial. LLMs have
no such commitment. They contradict their own utterances routinely,
across turns and under mild reframing pressure. Non-contradiction is
not a binding constraint on next-token generation.

So we are **not** building foundations. The model's "axioms" are just
confidently-asserted contingencies, and no amount of decomposition
turns contingent claims into necessary ones (Hume's old point recycled).

What survives is the **Socratic / dialectical** angle. Socrates'
interlocutors contradicted themselves constantly — the elenchus *expects*
this and uses an external structure to surface it. Reframed for LLMs:
philosophical scaffolds are not a property the model holds, they are an
**audit loop around the model**.

## Reframe: legibility, not foundations

The research question becomes:

> Does structured external dialectic reduce contradiction rate, surface
> load-bearing assumptions, and improve the legibility of model output
> on tasks Loom cares about — relative to plain chain-of-thought?

Empirical, gradable, falsifiable.

## Chain of thought vs chain of reason

A second sharpening: most CoT research conflates two different kinds of
chain.

- **Deliberative chain (what CoT actually is).** Forward-looking,
  problem-solving: "to get from question to answer, first do A, then B,
  then C." Each step is an *operation*. Chain terminates at an answer,
  then dissolves. "Let's think step by step" elicits this.
- **Justificatory chain.** Backward-looking, ground-seeking: "claim X
  is warranted by Y; Y is warranted by Z; Z bottoms out at..." Each
  step is a *warrant* or *premise*. Chain terminates at a ground (or a
  regress) and persists as a record of *why* the claim is held.

These have different formal shapes and different failure modes.
Deliberative chains fail by getting an operation wrong; justificatory
chains fail by smuggling unwarranted premises, by circularity, or by
infinite regress. Different audit moves catch different failures.

The CoT literature mostly studies deliberative chains. Justificatory
chains live in a different (older, less LLM-flavored) literature:

- **Toulmin argument schemas** — claim / data / warrant / backing /
  qualifier / rebuttal. *The Uses of Argument* (1958) is foundational.
- **Walton argumentation schemes** — taxonomy of dozens of justification
  patterns, each with their own critical questions. Compatible with
  the "audit move" framing.
- **Argument mining (NLP subfield)** — extracts argument structure from
  text, typically using Toulmin/Walton as targets.
- **Epistemology of justification** — foundationalism vs coherentism vs
  infinitism. The regress problem is exactly the question of how a
  justificatory chain terminates.

For Loom, this distinction matters: `--rationale` strings are
*justifications*, not deliberations. So if the philosophical-scaffolds
idea pays off, it likely wants justificatory-chain methodology
(Toulmin-style structure, Walton-style critical questions), not
CoT-style "think step by step."

## The accumulation loop (the ratchet)

Third and most consequential sharpening: CoT and chain-of-reason are
not opposites — they are two distinct phases of one process.

- **Exploration phase (CoT shape).** Generate hypotheses, test them,
  see which survive. Transient. Chain dissolves after answer is
  produced.
- **Accumulation phase (chain-of-reason shape).** Hypotheses that
  survived become *validated warrants* — reusable building blocks for
  future reasoning. Persistent. Chain does not dissolve; it accretes.

CoT research mostly misses the second phase. CoT is studied as one-shot
deliberation. What we are describing is a **ratchet**: each round of
CoT, when its conclusions clear validation, leaves behind a durable
artifact the next round builds on rather than re-derives.

Formal analogs worth naming:

- **Lemma accumulation in proof assistants** (Lean, Coq, Isabelle). A
  lemma is a small validated claim that becomes a primitive in
  subsequent proofs. The system works because the proof environment is
  the validator. The proposal here is essentially lemma accumulation
  for natural-language reasoning, with Loom as the proof environment.
- **Skill libraries in agentic systems** (Voyager, Wang et al). Voyager
  builds a persistent library of validated *code skills* and reuses
  them. This proposal is the same shape, but for *validated warrants*
  rather than skills.
- **Memory-augmented agents** (MemGPT, generative agents). These
  persist experiences. The proposal here persists *validated reasons*,
  which is a sharper and less explored category.

### The loop, made concrete

1. Agent reasons about something (CoT, exploratory).
2. Conclusions emerge with candidate justifications.
3. Loom runs validation passes (Toulmin-shape check, falsifiability
   check, conflict-with-existing-reasons check). This is where the
   philosophical-scaffold typology earns its keep — each scaffold is a
   different validator.
4. Validated reasons land in the store as first-class entities.
5. Next reasoning turn, Loom retrieves relevant accumulated reasons and
   injects them as context. The agent builds on warranted ground rather
   than re-deriving.
6. If new evidence supersedes an old reason, supersede semantics handle
   the retraction; downstream reasons that depended on it get flagged
   (drift detection, but for warrants instead of code).

## Why Loom is structurally well-suited to be the validator/persister

Loom already has the right primitives, used for slightly different
purposes:

- **Persistent SQLite store** for first-class entities — currently
  requirements, specs, patterns. Could host warranted-reason entities
  natively (new entity type, same store/embedding/conflict pattern).
- **Embedding-based retrieval** — surface relevant prior reasons at
  generation time. Same machinery as `loom query`.
- **Conflict detection** — already flags when two requirements are in
  tension (`conflict_verify.py`). The same machinery would flag when a
  candidate reason contradicts an accumulated one.
- **Supersede / archive lifecycle** — critical for reason accumulation,
  because validated ≠ true forever. Reasons need to be retractable.
  Loom already models this for requirements.
- **Hooks for feedback into generation** — `hooks/loom_pretool.py`
  already injects reqs + rationales into the agent's context before
  edits. Extending it to inject validated reasons before reasoning
  turns is structurally the same operation.
- **Drift detection** — when a reason is retracted, Loom can flag
  downstream entities depending on it (the same way it flags drifted
  code). Critical for ratchet reversibility, though the machinery
  needs extending from code-link drift to warrant-dependency drift.

## Typology: philosophical methods as audit moves

Each method is a different lens for exposing hidden structure in
reasoning. They are not competing metaphysics; they are different audit
moves applicable to a transcript or as a prompt scaffold.

| Method | Audit move | Signal it surfaces |
|---|---|---|
| Socratic elenchus | force definitions before claims | term drift across turns |
| Humean is/ought | flag normative claims smuggled from descriptive ones | unsupported "should" leaps |
| Popperian falsifiability | demand a falsifier for every claim | unfalsifiable mush |
| Wittgensteinian language-game | check term usage against domain rules | terms smuggled across contexts |
| Hegelian dialectic | construct strongest antithesis before synthesis | strawmanned opposition |
| Kantian universalizability | "would this rule hold if applied generally?" | local hacks dressed as principles |
| Stoic dichotomy of control | separate what's known from what's guessed | confidence/evidence mismatch |

Each scaffold becomes a candidate validator in the accumulation loop.

## Measurable proxies (must pick one before harness)

The whole experiment lives or dies on this. "Better reasoning" is not
gradable. Candidates:

- **Contradiction rate** — count of self-contradictions a second LLM
  finds in an N-turn transcript. Lower is better.
- **Assumption-explicitness** — can a second agent recover the
  load-bearing claims from the transcript without seeing the prompt?
- **Counterfactual reversibility** — flip a key premise; does the
  conclusion track? (Borrowed from CoT-faithfulness literature, Lanham
  et al, Anthropic 2023.)
- **Definitional stability** — does the model use a key term
  consistently across turns? Drift score, lower is better.
- **Downstream Loom outcomes** — does scaffolded rationale improve
  conflict-detection precision (`loom conflicts`) or human-auditor
  agreement on `loom check` outputs? Loom-native, most directly useful.
- **Ratchet-specific: accumulated-reason reuse rate** — once a reason
  is validated and stored, how often does it get retrieved and applied
  in future generations? High reuse with stable downstream answers
  suggests the ratchet is doing real work.

## Risks

1. **Philosophical theatre.** Scaffolds add ceremony and produce more
   text without moving any measurable outcome. Mitigation: pick a
   measurable proxy and a null hypothesis *first*, before writing the
   scaffold. Be willing to publish a null result.
2. **Confabulated foundations.** The model is excellent at producing
   plausible-sounding bedrock claims that aren't load-bearing. Don't
   treat any model-derived "axiom" as audited until the audit loop has
   actually run on it.
3. **Validated ≠ true.** Validation is fallible (especially LLM-driven
   validation). The ratchet only works if it's reversible. Need
   explicit retraction semantics with dependency tracking — when reason
   R is retracted, downstream reasons that built on R must be flagged
   for re-examination. Loom's drift-detection machinery is the right
   primitive but needs extending from code-link drift to
   warrant-dependency drift.
4. **Voyager noise problem.** Skill libraries grow unboundedly. Reason
   libraries will too. Need pruning/staleness signals — Loom's
   `last_referenced` and `loom stale` machinery is exactly the right
   primitive.
5. **Recursive uncertainty.** If validation is LLM-driven and
   accumulation is LLM-driven and reasoning is LLM-driven, we have an
   LLM grading an LLM grading an LLM. The loop must bottom out at
   programmatic checks, human review, or reality (test pass/fail).
6. **Domain-specificity.** Falsifiability matters for empirical claims;
   universalizability matters for design rules. Wrong lens = noise.
   Typology must be matched to task shape.
7. **Cost.** Each scaffold is at minimum one extra LLM pass, often
   several. Budget vs. measured improvement must clear a bar.

## Integration with `sdr-graph-memory` (HANDOFF SECTION — TBD)

**Status of this section:** intentionally a stub. The
`jsuppe/sdr-graph-memory` repository is private; the agent that wrote
this doc could not access its README or architecture, so cannot fill in
the integration design. This section is meant to be picked up by the
agent working on `sdr-graph-memory`, who has that context.

**Hypothesis:** sdr-graph-memory is structurally adjacent to the
accumulation loop described above and may serve as either the substrate
or the consumer for it. The name suggests sparse distributed
representations + a graph structure + (the word "drift") drift
detection — all of which line up suspiciously well with what the
ratchet wants from a storage layer.

**Open questions to bring to that lens** (the agent on the other side
should answer or correct these):

- If sdr-graph-memory uses **sparse distributed representations**, do
  validated warrants have a natural SDR encoding? Are accumulated
  reasons better stored as SDRs in a graph than as embeddings in a
  SQLite table? (Loom currently uses dense embeddings via Ollama
  `nomic-embed-text` 768d or OpenAI 1536d.)
- If sdr-graph-memory has a **graph structure**, can warrant-dependency
  edges (reason R supports reason R'; reason R undermines R') be
  stored natively as edges? Loom's flat embedding store does not model
  these dependencies as first-class edges; the graph project might.
- The "drift" framing in both projects suggests overlap. Loom currently
  detects code-vs-requirement drift via embedding similarity + content
  hashes. The ratchet needs *warrant-vs-warrant* drift (when a new
  validated reason undermines an old one). Does sdr-graph-memory
  already do something analogous?
- **Direction of integration:** does Loom *call into* sdr-graph-memory
  as the storage/retrieval layer for accumulated reasons, or does
  sdr-graph-memory consume Loom's validation pipeline as its quality
  filter? Probably one of those two; the choice determines which repo
  is the host of the ratchet.

**Next step on this section:** when the agent on sdr-graph-memory reads
this doc, they should respond with (a) which of these questions are
real and which are mismatched, (b) a sketch of how the architectures
would compose, and (c) a recommendation on direction of integration.
After that, this section gets rewritten with concrete design.

## Open design choices (still up for grabs)

- **Scope.** Narrow (one scaffold × one Loom task, bake-off vs. plain
  CoT) vs. broad (taxonomy + multiple scaffolds × multiple tasks)?
  Narrow is the existing experiments-dir norm and produces cleaner
  signal. Broad is more programmatic but risks vibes-only output.
- **First scaffold-task pairing to try?** Candidates:
  - Toulmin schema × `loom extract` rationale validation (closest to
    ratchet — directly tests warrant-shape elicitation)
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
- **Storage layer for accumulated reasons.** Native Loom SQLite entity,
  or delegate to sdr-graph-memory if its graph model is a better fit?
  Pending the integration handoff above.

## Sharpened research question

Original framing: *do philosophical scaffolds help?*

After the sharpening above: *does a reason-accumulation architecture,
with Loom (and possibly sdr-graph-memory) as validator and persistence
layer, measurably improve downstream LLM generation vs. (a) plain CoT,
(b) plain retrieval-augmented generation, (c) skill-library-style
accumulation without warrant structure?*

Substantially sharper than the original. No longer just a thinking doc
— it's a system design proposal with an empirical question attached.

## Prior art to dig into

CoT/agent side (study deliberation):

- *Measuring Faithfulness in Chain-of-Thought Reasoning* — Lanham et
  al, Anthropic 2023. Counterfactual-reversibility methodology.
- *Chain-of-Verification Reduces Hallucination* — Dhuliawala et al
  2023. Closest extant Socratic-shaped scaffold.
- *Self-Refine* — Madaan et al 2023. Iterative critique/revise.
- *Improving Factuality and Reasoning ... through Multiagent Debate* —
  Du et al 2023. The dialectic angle.
- *Let's Verify Step by Step* — Lightman et al, OpenAI 2023. Step-level
  grading (process reward models).
- *DSPy* — Khattab et al, Stanford. Prompts as parameters; likely the
  right harness host if this becomes real.
- *Voyager* — Wang et al. Skill-library accumulation in Minecraft.
  Closest analog to the ratchet, but for code skills not warrants.

Argumentation/justification side (study justification — less LLM-
flavored but probably more apt for the chain-of-reason direction):

- Toulmin, *The Uses of Argument* (1958). Foundational schema.
- Walton, argumentation schemes literature. Taxonomy + critical
  questions.
- Argument mining literature in NLP. Methodology for extracting
  warrant structure from text.

The CoT/agent literature studies *deliberation*. The argumentation
literature studies *justification*. The proposal here lives in the gap
between them.

## What "done" looks like for the next step

This is no longer a pure thinking doc — it's a research-program
proposal. Possible next steps in priority order:

1. **Read sdr-graph-memory's README and architecture.** Fill in the
   integration section above with concrete design. Decide direction of
   integration. (Blocked on agent with access to that repo.)
2. **Write a 2-page protocol doc** for the first scaffold-task pairing.
   Best initial candidate: Toulmin schema × `loom extract` rationale,
   since it directly tests the ratchet's value-add.
3. **Build a minimal harness** modeled on `experiments/gaps/` or
   `experiments/pilot/`. Single scaffold, single proxy, baseline-vs-
   scaffolded.
4. **Run the harness, write a FINDINGS doc, decide whether to expand
   the typology or kill the program.**

## Conversation arc (handoff aid)

This doc was developed in a single brainstorming session. The arc:

1. Seed: can structured philosophical decomposition give an LLM a
   foundational reasoning basis (Cartesian-style)?
2. Realization: LLMs contradict themselves freely, so the Cartesian
   port fails. The cogito requires a logical commitment to non-
   contradiction the model lacks.
3. Reframe: not foundations, but *legibility/auditability* via external
   dialectic loops (Socratic, not Cartesian).
4. Sharpening: most CoT research conflates deliberative and
   justificatory chains. What we want is the latter — Toulmin/Walton
   territory, not "let's think step by step" territory.
5. Big move: CoT and chain-of-reason are *both phases of one process*.
   CoT explores; chain-of-reason accumulates the survivors as a
   ratchet of validated warrants. Loom is a near-perfect host for
   this ratchet.
6. Integration prompt: relate this to `sdr-graph-memory` (other agent's
   project). Stub section above; awaiting that agent's input.
