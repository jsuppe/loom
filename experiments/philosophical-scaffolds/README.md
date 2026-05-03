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
  *(Update 2026-05-03: see "Integration with sdr-graph-memory" below
  — the warrant-dependency drift primitive already exists in
  Driftgraph as `BECAUSE_OF` + foundation-drift alerts. Loom should
  delegate this rather than reinvent it.)*

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
   for re-examination. *Resolution (2026-05-03):* Driftgraph
   (`jsuppe/sdr-graph-memory`) shipped this as Phase 9 — bitemporal
   `SUPERSEDES` edges plus `BECAUSE_OF` justification edges plus
   automatic foundation-drift alerts when a SUPERSEDES target is
   itself a `BECAUSE_OF` target. The integration plan below proposes
   Loom delegate to Driftgraph for this primitive rather than
   reinventing it.
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

## Integration with `sdr-graph-memory`

*Filled in 2026-05-03 by the agent on the `jsuppe/sdr-graph-memory`
side. Replaces the earlier TBD stub.*

### Naming clarification

`jsuppe/sdr-graph-memory` is the repo name, but the active product
line is **Driftgraph** (v0.3+). The "sdr" in the repo name is
historical — early prototypes used sparse distributed
representations, but the v0.3 codebase moved to dense embeddings
(`mxbai-embed-large`, 1024-d) in Neo4j vector indexes after SDRs
collapsed single-token object-side entities into mega-entities.
Read it as a graph-of-claims with vector retrieval and bitemporal
supersedes semantics, not as an SDR system.

### The hypothesis was right: Driftgraph is the substrate the ratchet wants

The mapping from the 6-step accumulation loop above onto Driftgraph
today:

| Ratchet step | Driftgraph today |
|---|---|
| 1. Agent reasons (CoT, exploratory) | Chat utterance / repo doc → `:Episode` (`kind = "chat"` or `"authoritative"`) |
| 2. Conclusions w/ candidate justifications | `ClaimExtractor` (llama3.1:8b) → SPO triples per Episode, with confidence and polarity |
| 3. Validation pass | `StructuralPlusOllama` does *contradiction* validation only. Toulmin / falsifiability / Hegelian validators don't exist in Driftgraph — **this is where Loom plugs in.** |
| 4. Validated reasons land as first-class entities | `:Claim` nodes with bitemporal columns: `valid_from`/`valid_to` (world time) AND `observed_at`/`invalidated_at` (transaction time). Two axes, not one. |
| 5. Retrieve + inject for next turn | `AnswerEngine` on @-mention; `RelevanceFinder` (proactive 📚 FYI); `aboutness` (periodic 🧭 conversation summary) |
| 6. Supersede + downstream flagging | `SUPERSEDES` for direct contradiction. **As of Phase 9 (2026-05-03):** `BECAUSE_OF` and `CONSIDERED` edges between Claims, with **foundation-drift alerts** when a SUPERSEDES target is itself a `BECAUSE_OF` target — i.e., a downstream warrant's grounding just moved. |

Step 6 specifically: Risk #3 in this doc was right that the
warrant-dependency drift primitive is what makes the ratchet
reversible. Driftgraph shipped that primitive last week. Demo
commands in the live prototype:

- `/why <topic>` walks `(SUPERSEDES* | BECAUSE_OF*)` backwards from
  the live claim and renders the chain with each step's source
  episode and the rationale on each transition.
- `/depends-on <adr>` walks `BECAUSE_OF` forward to surface every
  claim grounded in a named ADR — the "what breaks if I revisit
  this" lookup before re-litigating a decision.
- Foundation drift fires automatically: a chat utterance that
  supersedes a Claim that was a `BECAUSE_OF` target produces both
  the normal contradiction alert AND a separate amber 🪨 embed
  naming each downstream claim whose grounding just moved.

### Answers to the four open questions

**Q1 — Are validated warrants better stored as SDRs in a graph than
as embeddings in SQLite?** Mismatched. Driftgraph stores Claims as
first-class graph nodes with dense embedding properties
(`subject_emb`, `predicate_emb`, `object_emb`, all 1024-d). Vector
indexes (`claim_subject_vec`, `episode_text_vec`,
`entity_canon_vec`, `predicate_canon_vec`) provide cosine recall.
SDRs were tried in the v0.x research and abandoned — they collapsed
single-token object-side entities into mega-entities in
`nomic-embed-text`. Don't read "SDR" in the project name as a
current architectural choice.

**Q2 — Can warrant-dependency edges be stored natively as edges?**
Yes. Two new relationship types as of Phase 9 in
`experiments/v03/extract.py` and `experiments/v03/ingest.py`:

```
(:Claim)-[:BECAUSE_OF
   {rationale, confidence, extracted_from_episode_id, detected_at}
]->(:Claim)
```

— "this claim is grounded in those prior claims."

```
(:Claim)-[:CONSIDERED
   {rationale, confidence, extracted_from_episode_id, detected_at}
]->(:Claim)
```

— "this decision weighed and rejected this alternative."

The LLM extractor (`ClaimExtractor.extract_with_grounding`)
produces justification triples alongside SPO claims in a single
inference call — see `EXTRACTION_GROUNDING_PROMPT`. Edges are
written via `MERGE` so re-extraction is idempotent.

**Q3 — Does Driftgraph already do warrant-vs-warrant drift?** Yes,
at two granularities. *Per-claim*: a chat utterance that supersedes
an existing live Claim writes a `SUPERSEDES` edge with the conflict
judge's rationale. *Per-warrant*: when the SUPERSEDES target is
itself a `BECAUSE_OF` target from any other claim, the bot fires a
separate 🪨 alert naming the dependent claims that just had their
grounding moved (`product/discord_demo/chains.py:find_foundation_drift`).
Phase 11 added a periodic gap detector that surfaces structural
weaknesses in the graph (un-grounded ADRs, no-alternatives
decisions, orphan entities, chat-only hot entities), which doubles
as a way to spot warrant chains where the dependency structure is
incomplete.

**Q4 — Direction of integration?** **Loom calls Driftgraph as the
substrate; Driftgraph stays in charge of storage + drift
mechanics.** Driftgraph already owns: storage (Neo4j multi-database
isolation per project), retrieval (vector recall + structural graph
walks), and drift mechanics (SUPERSEDES, BECAUSE_OF, foundation
drift). Loom owns: extraction (its existing requirements pipeline),
code-link, and the *philosophical validators* this doc proposes.
The validator output gates which candidate claims get promoted into
Driftgraph as warrants. Loom is the gatekeeper; Driftgraph is the
warehouse.

### Composition sketch

```
[Loom]  conversation transcript / commit / PR description
   │
   ▼
[Loom]  existing extractor → candidate claim payload
   │
   ▼
[Loom]  philosophical validators (Toulmin, falsifiability, …)
   │      each returns pass/fail + score + critical-questions answers
   │
   ▼
[Loom]  validated warrant payload (only if ≥1 validator passed)
   │
   │  POST /warrants  (HTTP boundary — small Fastify/aiohttp on the
   │                   Driftgraph side; HMAC-signed)
   ▼
[Driftgraph]  Ingestor.ingest_episode(kind="warrant",
                   metadata={validator_id, validator_score, ...})
   │
   ▼
[Driftgraph]  :Claim nodes + BECAUSE_OF/CONSIDERED edges per validator
   │           findings; bitemporal SUPERSEDES if it conflicts with
   │           an existing live warrant
   │
   ▼
[Driftgraph]  /why /depends-on /quality /gaps  (existing query surface)
   │
   │  retrieve relevant accumulated warrants
   ▼
[Loom]  inject retrieved warrants into agent context before next gen
```

### Three small additions Driftgraph would need

For Loom to use Driftgraph cleanly as the warranted-reason substrate,
the v0.4 schema gets three small extensions:

1. **`kind = "warrant"`** alongside the existing `"chat"` and
   `"authoritative"` values. Reuses the existing tier-isolation
   logic in `FIND_PRIOR_CLAIMS` (warrants only check for
   contradictions against other warrants in the same scope).
2. **Validator metadata on `:Claim`** — `validator_id` (e.g.
   `"toulmin@v1"`), `validator_score` (float), free-form
   `validation_metadata` JSON. So `/why` can render "this claim was
   admitted by Toulmin@v1 with score 0.84" alongside its rationale.
3. **An HTTP boundary** — currently Loom is SQLite + python in one
   process and Driftgraph is Neo4j + python in another. A small
   Fastify/aiohttp endpoint accepting `POST /warrants` from Loom
   with HMAC signature verification. Reuses the auth pattern that
   Driftgraph's Phase 6 GH-Actions auto-sync would use.

These are tracked as **Phase 13 — Loom integration adapter** in
the Driftgraph roadmap (`product/discord_demo/docs/roadmap.md`).

### Shared opportunity: complementary quality dimensions

Driftgraph's Phase 10 `/quality` scoring and Phase 11 `/gaps`
detection are *structural* completeness checks: does this claim
have its source episode, its citation, its outbound `BECAUSE_OF`,
its incoming linkage. Loom's philosophical validators are *logical*
completeness checks: does this claim have its data, its warrant,
its qualifier, its rebuttal. The two are orthogonal and compose. A
claim that passes both is the strongest "high-quality anchor" for
the inference layer.

Concrete proposal: the validator metadata on `:Claim` (item 2
above) plumbs through to Driftgraph's quality scoring. A new
`logically_complete` dimension joins the existing five
(completeness, provenance, confidence, groundedness, linkability)
when Loom is in the loop. Score moves from 5 dimensions to 6+, the
new ones populated only for claims that came through Loom's
validators.

### Open design questions for Loom-side

- **Which validator first?** Toulmin × `loom extract` rationale is
  the closest to the ratchet test (does warrant-shape elicitation
  produce reusable structure?). Recommend that as the first scaffold
  Loom builds for the integration prototype.
- **Validator output schema.** Loom returns per-claim validation
  results as `{validator_id, score, passes: bool, critical_questions:
  [{q, a}], extracted_warrants: [...]}`. The `extracted_warrants`
  field maps to Driftgraph's BECAUSE_OF edges directly.
- **Retraction semantics.** When a Loom validator retracts a previous
  pass (e.g., a follow-up Toulmin run flips the verdict), Loom POSTs
  a retraction; Driftgraph supersedes the corresponding Claim, which
  triggers the existing foundation-drift cascade. No new
  Driftgraph code needed for retraction itself.

### Loom-side risks update

Risk #3 above ("Validated ≠ true") was the part of the ratchet most
in question; Driftgraph now provides the retraction-with-dependency-
tracking primitive natively. The remaining risk shifts to **the
trust boundary between Loom's validators and Driftgraph's storage**:
if Loom's Toulmin validator falsely admits a bad warrant, that
warrant's claims now live in the graph and influence retrieval until
the next contradiction surfaces it. Mitigations for this trust
boundary belong on the Loom side (validator self-tests, human-in-
the-loop sampling, periodic re-validation passes). Driftgraph's role
is to faithfully record what Loom asserted, not to second-guess
Loom's validators.

---

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
- **Storage layer for accumulated reasons.** *Resolved (2026-05-03):*
  delegate to Driftgraph. See "Integration with sdr-graph-memory"
  above. Loom's SQLite store remains the primary entity store for
  requirements / specs / patterns; warranted *reasons* live in
  Driftgraph's graph because the BECAUSE_OF / CONSIDERED edges and
  the foundation-drift cascade are the load-bearing primitives.

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

1. ~~Read sdr-graph-memory's README and architecture. Fill in the
   integration section above with concrete design.~~ *Done
   2026-05-03 by the agent on the Driftgraph side.* Direction of
   integration: Loom calls Driftgraph as the substrate; the schema
   extensions Driftgraph needs are tracked as Phase 13 in its
   roadmap.
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
   project). ~~Stub section above; awaiting that agent's input.~~
   *Resolved 2026-05-03* — Driftgraph is the substrate; it shipped
   the warrant-dependency drift primitive last week as Phase 9; the
   handoff section is filled in with composition + open questions
   on the Loom side.
