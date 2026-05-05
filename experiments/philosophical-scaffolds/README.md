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

## Operationalizing the integration: Loom-side build plan

*Added 2026-05-03 by the agent on the `jsuppe/sdr-graph-memory`
side as a follow-up to the handoff section above. The handoff
section answered "what does Driftgraph offer?" — this section
answers "what does Loom need to build to consume it?", in
phased deliverables a single agent can pick up as a work
package.*

### Status as of this write-up

Driftgraph's Phase 13 ships the substrate:

- `POST /warrants` HTTP endpoint live on `127.0.0.1:8080` (HMAC-
  SHA256 via `X-Hub-Signature-256`, secret in
  `LOOM_WEBHOOK_SECRET`)
- `GET /health` for connection sanity checks
- `:Episode` accepts `kind="warrant"` alongside `chat` /
  `authoritative`; tier isolation already filters warrants from
  contradicting chat or repo claims
- `:Claim` carries `validator_id` / `validator_score` /
  `validation_metadata` properties when Loom supplies them
- New `/warrants` Discord slash command surfacing the
  validator-admitted subset's quality + per-validator breakdown
- `/quality` now scores 6 dimensions including `logically_complete`
  (`validator_id` set AND `validator_score >= 0.7`)
- `/why` chain rendering shows `_validated by <id> (score X.XX)`
  per step where applicable
- Per-project opt-in via `loom_enabled: true` in
  `projects.yaml`. Sparkeye is opted in by default
- End-to-end smoke-tested with curl: a valid POST → 201 with
  `episode_id` + `claim_ids`; the warrant lands in Neo4j with
  `kind="warrant"` and is queryable via `/warrants`

**There is nothing left to build on the Driftgraph side for
the v0 integration.** Everything in the build plan below is
Loom-side.

### Why this is sequenced as four phases

The temptation is to build the full philosophical apparatus
(Toulmin + falsifiability + Hegelian + …) before exercising
the wire. Resist it. Each unbuilt piece is risk. The four
phases below front-load the wire test (cheapest, highest
information value) so failures show up before philosophical
investment.

If Phase L1 reveals the contract is wrong or the latency budget
is impossible, no Toulmin work is wasted. If Phase L2's first
real validator produces garbage when run against existing
`loom extract` rationales, that's data about whether Toulmin is
actually a useful structure for software-spec rationale (a
finding worth publishing on its own).

### Phase L1 — Wire test (smallest viable, ~1–2 hours)

**Goal:** prove the wire works end-to-end. Ship a Python module
that posts a hand-supplied "validated warrant" to the Driftgraph
endpoint and verify it lands.

**Build:**

1. New `loom/warrants.py` (~30 lines) with one function and one
   CLI entrypoint:

   ```python
   # loom/warrants.py
   import hmac, hashlib, json
   import requests

   def push_warrant(secret: str, endpoint: str, payload: dict) -> dict:
       body = json.dumps(payload).encode("utf-8")
       sig = "sha256=" + hmac.new(
           secret.encode("utf-8"), body, hashlib.sha256
       ).hexdigest()
       r = requests.post(
           endpoint,
           data=body,
           headers={
               "Content-Type": "application/json",
               "X-Hub-Signature-256": sig,
           },
           timeout=15,
       )
       r.raise_for_status()
       return r.json()

   def push_retraction(secret: str, endpoint: str, project: str,
                       claim_id: str, reason: str = "") -> dict:
       return push_warrant(secret, endpoint, {
           "project": project,
           "validator_id": "loom-retraction",
           "validator_score": 0.0,
           "retraction_target_claim_id": claim_id,
           "rationale": reason,
       })
   ```

2. **Trivial validator (Toulmin@v0):** a regex/heuristic
   "validator" that just checks the rationale has shape — at
   least 50 chars, contains "because" or "given" or "since",
   doesn't end mid-word. NO LLM. Output: `{passes: bool,
   score: float, validator_id: "toulmin@v0", reason: str}`. Goal
   is to have *something* that produces the payload shape;
   real validation lands in Phase L2.

3. **CLI:** `python -m loom warrant push --project sparkeye
   --rationale "..." [--source-claim req-123]`. Calls the
   trivial validator, then `push_warrant` if it passes.

4. **Config — shared secret + endpoint URL.**

   The HMAC secret is stored at a canonical filesystem path that
   both Driftgraph and Loom read on Jon's machine:

   - **Path:** `C:\Users\jonsu\.driftgraph\loom-webhook-secret`
     (Windows). On Linux/macOS dev machines the convention would
     be `~/.driftgraph/loom-webhook-secret`.
   - **Format:** the file contains the secret as plain text, no
     trailing newline. 64 hex chars (32 bytes) generated via
     `python -c "import secrets; print(secrets.token_hex(32))"`.
   - **Driftgraph reads it indirectly** via the
     `LOOM_WEBHOOK_SECRET` env var in
     `<grag>/product/discord_demo/.env`, which currently mirrors
     the file's contents. When rotated, both copies must be
     updated together. (For v0 this manual mirror is fine; if
     rotation becomes a hot path, Driftgraph can grow a small
     loader that reads the file directly.)
   - **Loom should also read this file** rather than asking Jon
     to paste the secret into Loom's config. Recommended Loom-side
     pattern:

     ```python
     # in loom/warrants.py
     import os, pathlib

     def _load_secret() -> str:
         p = pathlib.Path.home() / ".driftgraph" / "loom-webhook-secret"
         if p.exists():
             return p.read_text(encoding="utf-8").strip()
         # Fallback to env var so CI / non-Jon machines can override
         return os.environ.get("LOOM_WEBHOOK_SECRET", "")
     ```

     The home-directory path is the source of truth on the dev
     machine; the env var is the override knob for any machine
     where the file isn't available (CI, containers, second dev
     setups). Both fall through gracefully — empty string when
     neither is set, which the wrapper should treat as "Loom
     warrants integration disabled."

   - **Endpoint URL:** the bot listens on `127.0.0.1:8080` by
     default. Loom should default to
     `http://127.0.0.1:8080/warrants` and accept an override via
     `LOOM_DRIFTGRAPH_ENDPOINT` env var for non-default deployments.

   - **Sanity check before any code:** on the dev machine, run
     `Get-Content $env:USERPROFILE\.driftgraph\loom-webhook-secret`
     (Windows) or `cat ~/.driftgraph/loom-webhook-secret`
     (Linux/macOS). It should print a 64-char hex string. If the
     file is missing on the loom dev's machine, flag back — the
     `jsuppe/sdr-graph-memory` agent needs to either re-share the
     secret or coordinate regeneration.

**Acceptance:**

**Phase L1 is NOT measured by fire rate.** The fire-rate /
pass-rate signal lives in Phase L2 once a real LLM-driven
validator exists. L1 is a per-call wire test — pass/fail per
request, not a statistical rate. The acceptance is binary:

- `python -m loom warrant push --project sparkeye --rationale
  "We picked Pixel 8 because the wide lens is non-negotiable
  and on-device LLM rules out GoPro."` returns
  `{"episode_id": "ep_...", "claim_ids": [...]}`.
- The bot's `/warrants` slash command in `#sparkeye-demo`
  shows the new claim with `validator_id: toulmin@v0`.
- Bad rationale (`--rationale "lol idk"`) fails the trivial
  validator locally and never POSTs.
- A `push_retraction` call against a previously-pushed claim_id
  returns 200 and shows the claim as invalidated in `/warrants`.

**Verification you can run BEFORE writing any code:**

```bash
# 1. Substrate health check
curl http://127.0.0.1:8080/health
# expected: {"ok": true, "service": "driftgraph-warrants"}

# 2. End-to-end smoke (proves the wire is live).
#    Two flavors below — pick whichever your shell supports cleanly.

# === Option A: Python-based HMAC (recommended, works on every shell) ===
python -c "
import hmac, hashlib, json, pathlib, sys, urllib.request

secret = pathlib.Path.home().joinpath('.driftgraph', 'loom-webhook-secret').read_text(encoding='utf-8').strip()
body = json.dumps({
    'project': 'sparkeye',
    'validator_id': 'manual@v0',
    'validator_score': 0.9,
    'claim_text': 'Manual smoke',
    'rationale': \"posted by python -c from loom dev's machine.\",
}).encode('utf-8')
sig = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
req = urllib.request.Request(
    'http://127.0.0.1:8080/warrants',
    data=body,
    headers={'Content-Type': 'application/json', 'X-Hub-Signature-256': sig},
    method='POST',
)
with urllib.request.urlopen(req) as r:
    print(r.status, r.read().decode())
"
# expected: 201 with {"episode_id": "...", "claim_ids": [...]}

# === Option B: Pure bash (uses printf — DO NOT use echo -n; it's
# unreliable on Git-Bash for Windows because of xpg_echo quirks.
# The body bytes signed must EXACTLY match the body bytes sent.) ===
SECRET=$(cat ~/.driftgraph/loom-webhook-secret)   # Linux/macOS
# Windows Git-Bash: SECRET=$(cat "$USERPROFILE/.driftgraph/loom-webhook-secret")
BODY='{"project":"sparkeye","validator_id":"manual@v0","validator_score":0.9,"claim_text":"Manual smoke","rationale":"posted by curl from loom dev'\''s machine."}'
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $NF}')"
curl -X POST http://127.0.0.1:8080/warrants \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $SIG" \
  -d "$BODY"
# expected: 201 with {"episode_id": "...", "claim_ids": [...]}

# 3. Confirm in Discord
# (run /warrants in #sparkeye-demo on the Magi server — should show your claim)
```

If those three steps work, Phase L1's coding job is just
wrapping #2 in Python. If they don't work, the substrate is
broken and Loom-side coding is premature — flag the
`jsuppe/sdr-graph-memory` agent before proceeding.

### Phase L2 — First real validator (Toulmin@v1, ~half day)

**Goal:** replace the trivial heuristic Toulmin@v0 with an
LLM-driven extraction that produces the full Toulmin shape
(claim / data / warrant / qualifier / rebuttal).

**Build:**

1. Toulmin prompt template that takes a free-form rationale +
   optionally the claim it justifies, and emits structured
   JSON:
   ```json
   {
     "claim": "...",
     "data": "...",
     "warrant": "...",
     "qualifier": "...",
     "rebuttal": "..."
   }
   ```
2. Validator wrapper: if the LLM returns all five fields with
   non-empty `claim` + `data` + `warrant`, it passes (score
   based on completeness — 1.0 for all five, 0.6 if missing
   qualifier, 0.4 if missing rebuttal, fail if missing the
   first three).
3. The `validator_metadata` POSTed to Driftgraph includes the
   five extracted fields. This is what `/why` and audit queries
   in Driftgraph will surface as the audit trail.
4. Pick the proving ground: `loom extract` rationale validation
   is the doc's recommended starting point. Run Toulmin@v1 on
   each rationale Loom extracts; warrants that pass go to
   Driftgraph.

**Acceptance — three cuts you tune against:**

Phase L2 is "done" when **all three** of the following hold.
None of them is a single number; they're complementary signals.

**Cut 1 — Coverage band: 30–60% pass on a 20-rationale sample.**

Sample 20 existing Loom rationale strings (whatever your existing
extraction has produced — random sample, not curated). Run
Toulmin@v1 on each. Count how many pass.

- < 30% pass → prompt is over-strict, rejecting things a human
  reviewer would accept. Loosen.
- 30–60% pass → prompt is doing real work. The 30–60% band is
  empirical: it's the range where you've separated "real warrants"
  from "thin assertions" rather than rubber-stamping or rubber-
  rejecting everything.
- \> 60% pass → prompt is too permissive. Tighten.

The band is the broad target. Inside it, look at the *score*
distribution: bimodal (most claims either ~0.9 or ~0.2) means the
validator is confidently discriminating. Clustered around 0.5 with
low confidence everywhere means it isn't.

**Cut 2 — Zero false positives on a 5-rationale canary set.**

Hand-curate 5 obviously-bad rationales as a hard-fail probe:

1. `"we picked X because we wanted to"`
2. `"TBD"`
3. `"this is the right call"`
4. A single-sentence non-justification (e.g., `"because reasons"`)
5. A rationale that names no prior facts and gives no reasoning
   (e.g., `"after thinking about it we should use Postgres"`)

Toulmin@v1 must reject **all 5**. A single false positive means
the prompt admits things that aren't warrants, and the substrate
becomes unreliable. Tune until 0/5 admit. Add to the canary set
over time as you find new failure modes.

**Cut 3 — Downstream Driftgraph alignment (informative, optional).**

Push all 20 rationales through (passing AND failing) into Drift-
graph as separate `kind="warrant"` claims. Run `/quality` and
look at the per-validator breakdown. Then in cypher-shell:

```cypher
MATCH (c:Claim {validator_id: "toulmin@v1"})
WHERE c.invalidated_at IS NULL
WITH c, c.validator_score AS s,
     COUNT { (c)-[:BECAUSE_OF]->() } AS n_grd,
     COUNT { (c)<-[:BECAUSE_OF]-() } AS n_lnk
RETURN
  CASE WHEN s >= 0.7 THEN "passing" ELSE "failing" END AS band,
  count(c) AS n,
  avg(toFloat(n_grd > 0)) AS pct_grounded,
  avg(toFloat(n_lnk > 0)) AS pct_linked
```

If the passing subset's `pct_grounded` and `pct_linked` are
materially higher than the failing subset's, Toulmin@v1's
selectivity aligns with the graph's other quality signals — good
evidence the validator is catching real structure. If the two
subsets score the same, Toulmin@v1 is selecting on a different
axis from what the graph captures. **Either finding is publishable
on its own** — don't gate Phase L2 completion on this; record
the result and continue.

**Phase L2 done-checklist:**

- [ ] Tuned Toulmin@v1 prompt hits 30–60% pass on 20 real rationales
- [ ] 0/5 false positives on the canary set
- [ ] At least 6–12 `validator_id="toulmin@v1"` claims live in
      Driftgraph (sparkeye), browsable via `/warrants`
- [ ] (Bonus, optional) Cut 3 downstream alignment check run, result
      logged regardless of direction

**Open question for this phase:** what's the right default score?
Toulmin completeness alone doesn't measure rightness. Consider:
pass-with-low-score (e.g. 0.4 if all five fields exist but the
rebuttal is "n/a") vs hard-fail. The `logically_complete`
Driftgraph dimension uses 0.7 as the cut; calibrate Toulmin@v1
scores so genuinely-good warrants clear that bar and weak ones
don't. The Cut 3 query above is also useful for picking the right
threshold — sweep `s >= X` and find the X that maximizes the
gap in `pct_grounded` between passing and failing.

### Reading from Driftgraph: read API + push webhook (Phase 13.5 + 13.5b — substrate-side, just shipped)

*Added 2026-05-05 in response to the loom dev's M13.5 scope check
question. Both sides shipped + smoke-tested end-to-end.*

The substrate now exposes a small read HTTP API (3 routes) plus a
push-back webhook so Loom can build a low-latency cache mirror
without polling. This is the path the loom dev's PreToolUse hook
should use — direct Cypher and in-process imports stay open for
debugging but neither needs to be a runtime dependency.

#### Read API

All endpoints are on the same `WARRANTS_PORT` (default 8080) as
the inbound `/warrants` endpoint. Auth follows two patterns:

- **GET endpoints** use `Authorization: Bearer <secret>` with the
  same `LOOM_WEBHOOK_SECRET` as inbound. Bearer (not HMAC) because
  there's no body to sign over.
- **POST endpoints** use HMAC-SHA256 over the body in
  `X-Hub-Signature-256`, identical to the inbound flow.

```
GET  /claims/{claim_id}?project=<name>
  → 200 with the full claim status, including foundation_drifted
    and supersedes_chain. 404 if claim_id doesn't exist in the
    project's database.

GET  /projects/{project_name}/foundation-drift?limit=<int>
  → 200 with the list of live claims whose direct BECAUSE_OF
    target has been invalidated. limit defaults to 100, capped
    at 500.

POST /claims/lookup
  body: {"project": "...", "claim_ids": [...]}
  → 200 with the per-claim status (same shape as GET /claims/{id})
    for each id, plus a missing_claim_ids list. Capped at 500
    claim_ids per request.
```

Single-claim response shape:

```json
{
  "claim_id": "clm_...",
  "kind": "warrant",                 // or "chat" / "authoritative"
  "valid": true,                     // false if invalidated_at is set
  "invalidated_at": null,            // unix-ms or null
  "observed_at": 1777904984684,
  "confidence": 0.9,                 // extractor confidence
  "validator_id": "toulmin@v1",      // null when not validator-tagged
  "validator_score": 0.85,
  "subject": "POC v1 scope",
  "predicate": "uses",
  "object": "ask-anything path only",
  "source_episode_id": "ep_...",
  "source": "loom_warrant",
  "supersedes_chain": ["clm_...", "clm_..."],   // SUPERSEDES* outbound, longest path
  "because_of_targets": ["clm_..."],            // direct BECAUSE_OF outbound
  "foundation_drifted": false,                  // any BECAUSE_OF target invalidated?
  "n_invalidated_parents": 0
}
```

Foundation-drift response shape:

```json
{
  "project": "sparkeye",
  "drifted_claims": [
    {
      "claim_id": "clm_...",
      "kind": "warrant",
      "subject": "...", "predicate": "...", "object": "...",
      "validator_id": "toulmin@v1",
      "validator_score": 0.85,
      "source": "loom_warrant",
      "broken_chain": [
        {
          "target_claim_id": "clm_<the retracted parent>",
          "target_subject": "...",
          "target_object": "...",
          "retracted_at": 1777976981831,
          "retraction_validator": "toulmin-revalidate",
          "rationale": "<the BECAUSE_OF rationale on the original edge>"
        }
      ]
    }
  ],
  "count": 1
}
```

Bulk lookup response shape:

```json
{
  "project": "sparkeye",
  "claims": [<single-claim shape>, <single-claim shape>, null],
  "found_count": 2,
  "missing_claim_ids": ["clm_doesnt_exist"]
}
```

Note: `claims` preserves request order; missing IDs land as `null`
in the array AND are listed separately in `missing_claim_ids`.
This means Loom can zip the response array against its request
list directly.

Smoke-test commands (from any shell):

```bash
SECRET=$(cat ~/.driftgraph/loom-webhook-secret)

# 1. Single claim
curl -s "http://127.0.0.1:8080/claims/clm_<id>?project=sparkeye" \
  -H "Authorization: Bearer $SECRET"

# 2. Foundation-drift across project
curl -s "http://127.0.0.1:8080/projects/sparkeye/foundation-drift" \
  -H "Authorization: Bearer $SECRET"

# 3. Bulk lookup (HMAC over body, like the inbound POST)
BODY='{"project":"sparkeye","claim_ids":["clm_a","clm_b"]}'
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $NF}')"
curl -s -X POST "http://127.0.0.1:8080/claims/lookup" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $SIG" \
  -d "$BODY"
```

#### Push webhook (the recommended path for PreToolUse latency)

Polling per-edit at 6s p95 will feel terrible. Push from Driftgraph
to Loom's webhook eliminates per-edit Driftgraph hits entirely —
PreToolUse reads from Loom's local cache with 0ms latency, and the
cache stays current via push events.

Configure on the Driftgraph side: add `loom_drift_webhook: "<url>"`
to the project's entry in `projects.yaml`. The bot will register
the dispatcher at next startup and start firing events.

Three event types:

```
event: "foundation_drift_detected"
  // Fired when a chat utterance supersedes a Claim that's a
  // BECAUSE_OF target (i.e., a downstream warrant's grounding
  // just moved). One event per detection batch with the full
  // list of affected dependents inline.
{
  "event": "foundation_drift_detected",
  "project": "sparkeye",
  "fired_at": 1777977055759,
  "triggering_episode_id": "ep_...",
  "superseded_claim_ids": ["clm_..."],
  "affected_dependents": [
    {
      "claim_id": "clm_<dependent>",
      "subject": "...", "predicate": "...", "object": "...",
      "source": "loom_warrant",
      "repo_path": "docs/decisions/0007-...md",  // null for chat sources
      "url": "https://github.com/.../blob/main/...",
      "rationale": "<original BECAUSE_OF rationale>",
      "target_claim_id": "clm_<the superseded parent>"
    }
  ],
  "n_dependents": 1
}

event: "claim_superseded"
  // Fired per SUPERSEDES write inside _process_message. Each
  // alert in the chat = one event. Loom can use this to know
  // which claims are no longer live.
{
  "event": "claim_superseded",
  "project": "sparkeye",
  "fired_at": 1777977055759,
  "new_claim": {
    "claim_id": "clm_...",
    "subject": "...", "object": "...",
    "episode_id": "discord_<id>"
  },
  "old_claim": {
    "claim_id": "clm_...",
    "subject": "...", "object": "...",
    "episode_id": "..."
  },
  "predicate": "...",
  "topic": "<canonical entity>",
  "confidence": 0.92,
  "rationale": "<the conflict judge's rationale>"
}

event: "claim_invalidated"
  // Fired when Loom POSTs a retraction (POST /warrants with
  // retraction_target_claim_id). Echoes back so Loom's cache
  // doesn't have to wait for a poll to know its own retraction
  // landed.
{
  "event": "claim_invalidated",
  "project": "sparkeye",
  "fired_at": 1777977055759,
  "claim_id": "clm_...",
  "retraction_validator": "toulmin-revalidate@v1",
  "rationale": "no longer passes Toulmin shape check",
  "invalidated_at": 1777977055728
}
```

Auth: every webhook POST is HMAC-SHA256 signed with
`LOOM_WEBHOOK_SECRET` in `X-Hub-Signature-256`, exactly like the
inbound `/warrants` flow. User-Agent is `driftgraph-webhook/1`.

Delivery semantics: **fire-and-forget**, not at-least-once. The
substrate doesn't retry on failure (Loom timeout, 5xx, network
glitch all silently drop). For a robust cache mirror, Loom should
periodically re-sync via the read API as a backstop — e.g., a
nightly "fetch all foundation-drifted claims and reconcile" pass.
That covers any push events that didn't make it through.

Smoke-test pattern: a tiny aiohttp catcher script lives in the
Driftgraph repo at `sdr-benchmark/_webhook_catcher.py` for
verifying signatures and payload shapes locally without running
real Loom. Loom's webhook handler should mirror its auth + parsing
behavior.

#### What this changes for the loom dev's PreToolUse hook

Before Phase 13.5 + 13.5b, the only path was direct Cypher (your
A) or in-process import (your B). Now there's a clean HTTP read
path AND push events to keep a local cache fresh.

Recommended PreToolUse pattern:

1. On bot/Loom startup, hit `GET /projects/<name>/foundation-drift`
   to seed the local cache with everything currently drifted
2. Subscribe to the push webhook to receive deltas
3. On each PreToolUse: read from local cache only (no Driftgraph
   round-trip)
4. Periodically (e.g., hourly) re-fetch the foundation-drift list
   as a backstop in case any push events were dropped
5. Optional: when a tool's edit references specific claim_ids
   (e.g., it's editing an ADR file), hit `POST /claims/lookup`
   for those specific IDs to get the freshest state — falls back
   to cache on network failure

Cost target: PreToolUse adds ≤1ms to every edit (cache hit), with
backstop polling at 1 request per hour. Push events arrive within
seconds of the underlying state change.

---

### How `BECAUSE_OF` edges actually get written (read this before L3e)

*Added 2026-05-04 in response to a clarifying question from the
loom dev: "does Driftgraph create BECAUSE_OF edges automatically
from claim_text mentioning a prior claim_id, or is there an
explicit edge-creation API?"*

Two write paths, both supported. Pick the right one for the use
case.

**Path 1 — Explicit `target_claim_id` in the POST justifications
array (DETERMINISTIC; recommended for L3e and any case where you
know the parent claim_id).**

```json
{
  "project": "sparkeye",
  "validator_id": "toulmin@v1",
  "validator_score": 0.85,
  "claim_text": "Defer meeting summarizer to v2",
  "rationale": "Out of scope for POC v1.",
  "justifications": [
    {
      "kind": "because_of",
      "target_claim_id": "clm_f5ef189165604a60",
      "rationale": "meeting summarizer is out of scope per established POC v1 scope",
      "confidence": 0.95
    }
  ]
}
```

Driftgraph MERGEs the edge directly: `MATCH (src:Claim) MATCH
(tgt:Claim) MERGE (src)-[:BECAUSE_OF]->(tgt)`. No canonicalization
lookup, no LLM resolution, no chance of the edge silently failing
because of normalization mismatches. Loom retrieves the parent's
`claim_id` from the parent POST's response (`claim_ids[0]`) and
threads it into the child POST. Returns
`explicit_justifications_resolved: 1, explicit_edges_written: 1`
on success.

**Path 2 — Semantic `(target_subject, target_predicate, target_object)`.**

```json
{
  "justifications": [
    {
      "kind": "because_of",
      "target_subject": "POC v1 scope",
      "target_predicate": "is_set_to",
      "target_object": "ask-anything path only",
      "rationale": "...",
      "confidence": 0.9
    }
  ]
}
```

Driftgraph runs `RESOLVE_ENTITY` (vector cosine ≥ 0.92 on
`target_subject` against existing `:Entity` nodes) +
`RESOLVE_PRED` (vector cosine ≥ 0.85 on `target_predicate`) +
`FIND_PRIOR_CLAIMS` to locate the existing live `:Claim` whose
canonical entity + predicate match. **Brittle** because:

- The LLM that originally extracted the parent may have
  canonicalized `"POC v1 scope"` → `"POC scope"` (entity tau
  doesn't always match across distinct LLM calls)
- The predicate normalizer maps `"is_set_to"` → `"is_set_to"`
  but `"is"` → `"uses"`. Different post bodies producing
  different canonical predicates won't resolve.

When semantic resolution fails, the response shows
`explicit_justifications_dropped: N, explicit_edges_written: 0`.
That's the signal to switch to Path 1 instead, OR to verify what
the parent POST actually canonicalized to (Cypher snippet below).

**Path 3 — Implicit (LLM-extracted from the rationale text).**

If the rationale text contains "given that X", "because Y is",
"follows from Z", etc., the Phase 9 grounding-aware extractor
inside `Ingestor.ingest_episode` emits its own justifications and
they get resolved via the same semantic path. This works
opportunistically — useful when the rationale is naturally
written with inline argument, but not reliable enough for L3e
where you need a *specific* edge to exist.

**Don't put `clm_xxxxx` literals in the rationale text.** The
extractor would treat them as a literal string entity and
produce nonsense. Path 1 (target_claim_id) is the right way
to reference a prior claim by id.

**Verify what canonical form the parent POST landed at:**

```bash
# Replace ep_<id> with the parent POST's episode_id from response
cypher-shell -u neo4j -p $NEO4J_PASSWORD -d sparkeye \
  "MATCH (ep:Episode {episode_id:'ep_<id>'})-[:OBSERVED]->(c:Claim)-[:ABOUT {role:'subject'}]->(e:Entity) \
   MATCH (c)-[:HAS_PREDICATE]->(p:Predicate) \
   RETURN c.claim_id AS claim_id, e.canonical AS subject_entity, \
          p.canonical AS predicate, c.object_text AS object"
```

This shows you the canonical entity name and predicate for each
claim the parent POST produced — useful both for diagnosing why
a Path 2 lookup failed AND for deciding whether to use the
canonical form for Path 2 or just lock in Path 1's claim_id.

### Phase L3 — Multi-validator + retraction (~half day)

**Goal:** prove the system handles more than one validator
and that retraction works.

**Build:**

1. Add a second validator. Falsifiability is the natural pick
   — it composes with Toulmin (Toulmin extracts shape; falsifi-
   ability checks "is there a real falsifier?"). Two validators
   means each warrant gets multiple `validator_id` entries
   (each is its own Driftgraph claim/episode) OR a composite
   validator that runs both and returns a combined score.
   Recommend the former for v0 — separate claims per validator
   keeps the audit trail clean.
2. Retraction trigger. When does Loom retract? Three options:
   - Re-run validators on every commit that touches the
     underlying rationale (most aggressive)
   - Re-run on demand via a CLI command
   - Re-run on a schedule (nightly)
   For v0, recommend the CLI-triggered re-run. Operator runs
   `loom warrant revalidate --project sparkeye` periodically.
3. If a previously-passing warrant fails on re-validation, call
   `push_retraction(claim_id)`. Driftgraph handles the
   foundation-drift cascade.
4. **For the L3e demo specifically:** use Path 1 above
   (`target_claim_id`). Construct parent → child as two
   sequential POSTs; the child's `justifications[0].target_claim_id`
   is the `claim_ids[0]` returned in the parent POST's response.
   That guarantees the BECAUSE_OF edge exists, so retracting the
   parent reliably triggers the foundation-drift cascade for the
   child. Don't rely on Path 2 or Path 3 for L3e — they're
   subject to canonicalization variance.

**Acceptance:**

- A warrant passes Toulmin@v1 AND Falsifiability@v1, lands as
  two separate claims in Driftgraph (different `validator_id`).
- `/warrants` in Driftgraph shows both validators in the
  per-validator breakdown.
- Retracting one of them via `push_retraction` invalidates the
  corresponding claim; if it had `BECAUSE_OF` dependents (Path 1
  or Path 2 or Path 3 — all fire the same cascade), the
  amber 🪨 foundation-drift alert fires next time a query
  walks past.

### Phase L4 — Productionize (~variable)

Out of scope for the prototype, but worth listing:

- **Network failures.** Phase L1's `requests.post` will raise
  on connection errors. Add a retry loop with exponential
  backoff + a dead-letter file for warrants that fail to push
  after retries. Loom should be able to re-push from the
  dead-letter on demand.
- **Idempotency.** Driftgraph generates `episode_id` server-
  side, so duplicate POSTs from a retry create duplicate
  warrants. Add a client-side hash of `(project, claim_text,
  validator_id, rationale)` and dedupe before pushing — the
  same rationale shouldn't validate twice in the same week.
- **Observability.** Log every push attempt, success, failure.
  If Loom is running in Jon's CI / dev env, dump logs where
  he'll see them.
- **Secret rotation.** The HMAC secret currently lives in two
  places (`.env` files on each side). Rotate together, never
  in production without coordination.
- **Strong secret.** Both sides should generate via
  `python -c "import secrets; print(secrets.token_hex(32))"`
  and avoid the test value (`test-secret-phase13-…`) for any
  real run.

### Open questions for the loom dev (decide before Phase L1)

These affect the integration shape and are easier to answer
than to refactor.

1. **Hosting.** Is Loom running on the same machine as the
   Driftgraph bot (Jon's Windows machine)? If yes, the
   `127.0.0.1:8080` default is fine. If Loom moves to a server
   or runs in CI, the bot needs `WARRANTS_BIND=0.0.0.0` (or a
   tunnel) and HTTPS termination — neither of which is in
   place yet.
2. **Validator latency.** Phase L2's Toulmin call adds 5–15s
   per LLM pass. If Loom runs validators inside `loom extract`
   synchronously, every extract gets 5–15s slower. Acceptable?
   Or async via an in-process queue + background worker?
3. **Retraction policy.** Phase L3 punts on this with "CLI on
   demand." What's the longer-term policy — retrigger on every
   commit, schedule-based, only manual?
4. **Validator versioning.** `validator_id="toulmin@v1"` bakes
   the version into the identifier. When Toulmin@v2 ships, do
   old v1 warrants get re-validated against v2 (and possibly
   retracted), or do v1 warrants stay v1 forever and only new
   ones use v2? Recommend the former for trust, but it's a
   non-trivial migration.

### What's parked / out of scope for this build plan

- Real philosophical scaffolds beyond Toulmin (Hegelian
  dialectic, Popperian falsifiability beyond the falsifier
  field, Kantian universalizability, etc.). Wait until
  Toulmin@v1 proves the loop works on real data.
- Multi-tenant Loom (one client / one project for now —
  sparkeye).
- Driftgraph-side schema changes. None needed; Phase 13 is
  complete.
- Bidirectional flow (Driftgraph → Loom). Currently Loom pushes;
  Driftgraph never pushes back. If Loom needs to know about
  graph state changes (e.g., a chat utterance superseded a
  warrant), it polls or queries Driftgraph directly. Bidirec-
  tional was never proposed in the original ratchet doc.

### What "done" looks like for the next loom-dev session

The minimum signal that Phase 13 integration works
end-to-end:

1. Run the curl smoke test in "Verification you can run BEFORE
   writing any code" (above). Confirm 201 + claim shows up in
   `/warrants`.
2. Build Phase L1 (the Python client + trivial validator + CLI).
3. Push three real Loom rationales through it. Confirm:
   - `/warrants` in Discord shows them
   - Driftgraph `/quality` reflects them in `logically_complete`
   - One of them, when `loom warrant push` is re-run with
     identical args, doesn't double-write (or does — file an
     issue if so; deduping is Phase L4).
4. Commit + open a PR with the work, tagging this doc.

The loom dev should NOT block on Phase L2+ before opening that
first PR. Phase L1's signal — does the wire work with real
Loom data? — is what determines whether Phase L2's investment
is justified.

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
proposal AND a build plan. Possible next steps in priority order:

1. ~~Read sdr-graph-memory's README and architecture. Fill in the
   integration section above with concrete design.~~ *Done
   2026-05-03.* Direction of integration: Loom calls Driftgraph as
   the substrate; Driftgraph's Phase 13 (now shipped) provides the
   `POST /warrants` endpoint, validator-metadata `:Claim` properties,
   `kind="warrant"` Episode kind, and the `/warrants` slash command.
2. **Run the smoke test** in *Operationalizing the integration → Phase L1 → Verification you can run BEFORE writing any code*. Three curl calls. Confirms the substrate is reachable from your dev machine before any Loom-side code is written.
3. **Build Phase L1 (~1–2 hours):** the `loom/warrants.py` HTTP client + a trivial heuristic Toulmin@v0 + `loom warrant push` CLI. Push three real Loom rationales through it. The wire-test proves the contract before philosophical investment.
4. **Build Phase L2 (~half day):** Toulmin@v1 — replace the heuristic with an LLM-driven extraction emitting the five Toulmin fields. Run on existing `loom extract` output to produce a fire-rate signal.
5. **Optionally Phase L3 + L4** depending on what L2 reveals. See the build plan above for scoping.

The original "write a 2-page protocol doc" / "build a minimal
harness" / "run the harness, write FINDINGS" sequence still applies
*on top of* the integration above — Phases L1–L4 just deliver the
substrate the harness measures with. The harness compares plain
Loom-extract rationale vs Toulmin-validated rationale on a chosen
proxy (contradiction rate, counterfactual reversibility, etc.) —
and Driftgraph's `/quality` per-validator breakdown becomes one of
the read-out metrics.

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
