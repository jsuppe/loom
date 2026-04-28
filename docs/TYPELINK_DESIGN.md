# Loom Typelink — Cross-File Type Consistency

**Status:** design sketch — not implemented
**Last updated:** 2026-04-28
**Motivating data:** [`FINDINGS-bakeoff-v2-phaseC-inventory.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-phaseC-inventory.md), specifically the cpp-inventory v2_01 failure where each `.cpp` compiled cleanly in isolation but the final link failed because qwen wrote `Address` with a constructor signature the test couldn't call.

---

## 1. The problem

Today, every Loom primitive is local to one file or one decision:

- `Implementation.content_hash` — "this file's bytes match what we
  linked" → only sees one file.
- Drift detection — "file changed since req was superseded" →
  content-level, not type-level.
- `Specification` — "HOW a requirement is implemented" → free prose;
  not machine-checkable.
- `loom check` / pre-edit hook — "what reqs apply to this file" →
  hint, not enforcement.

The cpp-inventory v2_01 failure made the gap visible: `Address`'s
constructor signature is the *agreement* between
`include/types/customers.hpp` and `tests/shop_test.cpp`. That
agreement is **not in either file alone**. It only exists *between*
them. Loom has no primitive that captures it.

Same gap exists every time:

- A test file expects `Customer.add_address(addr)` and a service
  task produces `Customer.appendAddress(addr)`.
- Two services that both call `Inventory.reserve(...)` use
  inconsistent argument orders.
- A python-inventory consumer uses `dict` keys for ordering; a
  sibling implementation uses `OrderedDict` indexing — both
  individually compile but break at runtime.
- Multi-agent edits across sessions: agent A renames
  `Customer.email`; agent B's Loom hook sees the *file change* but
  not that the rename breaks every consumer that referenced
  `customer.email`.

These are all **cross-file type/signature consistency issues**.
None are detected by today's Loom.

## 2. The thesis

Loom should track not just *what files exist and what they
contain*, but *what public types/symbols each file declares* and
*which other files reference those declarations*. With that graph,
Loom can:

1. **Verify** at task-completion time: did the body pass produce a
   file whose public surface matches what the spec / siblings /
   tests expect?
2. **Warn** at edit time: this edit changes a public symbol that
   N other files reference; here are the consumers.
3. **Detect drift** at the *type* level: not "file changed" but
   "Customer's constructor changed shape since v3."
4. **Explain** failures in compile-error terms agents can act on,
   even when the failure is across files an agent doesn't see in
   one prompt.

We argue this is **structurally fundamental** to Loom — not an
addition. Loom's value prop is *making implicit decisions explicit
so they can be verified*. Type-level cross-file agreements are the
largest class of implicit decisions in real codebases that Loom
currently can't see.

## 3. Definitions

- **Public symbol** — a class, struct, function, type, or constant
  that another file may reference. Per-language definition:
  - Python: top-level `class`, `def`, type alias, constant
    (excluding `_underscored` privates)
  - TypeScript: `export class | function | const | type | interface`
  - Dart: top-level + class members (no `_` prefix)
  - C++: anything declared in `include/`-style headers
- **Type contract** — the canonicalized signature of a public
  symbol. For a class, includes: name, public field types,
  constructor signature, public method signatures, generic params.
- **TypeLink** — a recorded fact that file A's type contract is
  referenced by file B. Edges in the type-link graph.
- **Type contract drift** — the contract for symbol S in file A
  has changed in a way that's not Liskov-compatible with the
  contract that consumers in B/C/D were verified against.

## 4. Data model

### 4.1 Per-file type contract

A new dataclass `TypeContract`, persisted as a sibling of
`Implementation`:

```python
@dataclass
class TypeContract:
    id: str                          # TC-xxx
    file: str                        # path/to/file
    language: str                    # "python" | "typescript" | "dart" | "cpp"
    extracted_at: str                # ISO timestamp
    extractor: str                   # "manual" | "libclang" | "ast" | "tsc" | "dart-analyze"
    content_hash: str                # hash of the file when extracted
    symbols: list[Symbol]            # extracted public symbols
    parent_spec: Optional[str]       # SPEC-xxx that authored this file
```

```python
@dataclass
class Symbol:
    name: str                        # "Customer", "register_customer"
    kind: str                        # "class" | "function" | "type" | "const" | "method"
    parent: Optional[str]            # for methods: enclosing class
    signature: str                   # canonical signature string
    fields: list[Field]              # for classes/structs
```

A signature is canonicalized: parameter names dropped where they
don't matter (e.g. C++ `void f(int)` and `void f(int x)` both →
`void f(int)`); whitespace normalized; visibility tokens removed
where redundant.

Stored in a new ChromaDB collection `type_contracts`. Embedded by
the canonical signature, so semantic-search can answer "where do we
have something shaped like `Customer`?"

### 4.2 The type-link graph

A new dataclass `TypeLink`:

```python
@dataclass
class TypeLink:
    id: str                          # TL-xxx
    consumer_file: str               # the file that references the symbol
    producer_file: str               # the file that declares the symbol
    symbol: str                      # "Customer" or "Customer.add_address"
    referenced_at: list[str]         # line ranges in the consumer
    created_at: str
    last_verified: str               # ISO timestamp of last consistency check
    last_verified_status: str        # "ok" | "drift" | "missing"
```

A new collection `type_links`. Embedded by the symbol name + a
short context string.

The type-link graph is a directed acyclic relationship: file
references file. Cycles are allowed in principle (mutual
recursion) but rare; a cycle detector flags them.

### 4.3 Spec extension

Existing `Specification` gains an optional structured field:

```python
@dataclass
class Specification:
    # ... existing fields ...
    public_api_json: str = ""        # JSON: file → list[Symbol] expected
```

`public_api_json` is the *spec's commitment* to a public surface:
"by the time this spec is implemented, these symbols must exist
with these signatures." It's the source-of-truth contract that
verifiers check against.

Authored either by the agent at `loom spec --add` time
(structured), by an LLM extraction pass on the prose spec, or
inferred from the spec's existing prose with the user's review.

## 5. Verifier interface

Per-language verifiers register into a registry similar to
`runners.py`:

```python
@dataclass
class TypeVerifier:
    name: str                        # "python_ast", "tsc", "dart_analyze", "libclang"
    language: str
    file_extensions: list[str]       # [".py"], [".ts"], [".dart"], [".hpp", ".cpp"]
    extract_contract: Callable[[Path], TypeContract]
    diff_contracts: Callable[[TypeContract, TypeContract], list[Diff]]
    additive_check: Callable[[TypeContract, TypeContract], bool]
```

`extract_contract(file)` parses the file (using language tooling
where possible — `ast`, `tsc --emitDeclarationOnly`, `dart_analyze`,
`libclang`) and produces a `TypeContract`. Implementation can range
from regex (cheap, brittle) to full tree-sitter parse (correct,
heavier).

`diff_contracts(old, new)` returns a structured list of changes
between two contracts: added/removed/renamed symbols, signature
changes per field/method, etc.

`additive_check(old, new)` returns True if the new contract is a
strict superset of the old (only adds, doesn't change or remove).
Used to gate edits to public surfaces — additive changes are safe;
others trigger a flag.

### 5.1 Per-language extractor sketches

**Python (`python_ast`):**
- `ast.parse(source)` → walk for top-level `ClassDef`, `FunctionDef`
  (skip names starting with `_`).
- For classes: walk members; capture decorators, base classes,
  field annotations, method signatures (using
  `ast.unparse(node.args)` for canonical form).
- Type hints captured verbatim; no resolution needed for v1.
- Cost: ~10–50 ms per file.

**TypeScript (`tsc`):**
- Run `tsc --emitDeclarationOnly --outFile -` on the file.
- Parse the resulting `.d.ts` to extract symbols.
- Or: invoke TypeScript compiler API programmatically (more setup,
  more accurate).
- Cost: ~500 ms per file with `tsc`; subsecond if amortized via
  watcher.

**Dart (`dart_analyze`):**
- `dart analyze --machine <file>` produces JSON with errors.
- For type extraction: `dartdoc` or the analyzer package via
  `dart pub run`.
- Cheaper alt: regex-based extractor for v1 (matches what we
  already do in `validate_blueprint`).

**C++ (`libclang`):**
- Use `clang.cindex` Python bindings (libclang).
- Walk AST for `CXCursor_ClassDecl`, `CXCursor_FunctionDecl`,
  capture USR (Unified Symbol Resolution) and type signature.
- Handles templates, `using` declarations, etc.
- Heavyweight (~500 ms+ per file) but correct.
- Fallback: regex extractor for prototype.

### 5.2 Cross-language unification

A single `TypeContract.symbols` schema across languages enables
limited cross-language analysis ("Python `Customer` and
TypeScript `Customer` should agree on the field set"). For v1
this is per-language only; cross-language is a v2 feature.

## 6. Lifecycle integration

### 6.1 At `loom spec --add`

If `--public-api` is supplied (structured), parse + persist.

If not supplied AND the spec text contains code-fenced declaration
blocks (e.g. `dart-contract`, `python-contract`, `cpp-contract`),
auto-extract them as the public_api.

If neither, an LLM extraction pass over the prose can derive a draft
public_api. User reviews via `loom spec public-api SPEC-xxx --edit`.

### 6.2 At `loom link`

When a file is linked to a requirement/spec, run
`extract_contract(file)` and persist the resulting `TypeContract`.
If the spec has a declared `public_api`, immediately diff:
- `diff_contracts(spec.public_api[file], extracted)` → if there
  are non-additive diffs, surface as a warning (not a block).

### 6.3 At `loom_exec` body completion (the v2_01 fix)

After a body pass writes to a scratch file, before grading:

```python
contract = verifier.extract_contract(scratch_file)
if spec.has_public_api(target_file):
    expected = spec.public_api[target_file]
    diffs = verifier.diff_contracts(expected, contract)
    if diffs:
        return {
            "outcome": "typelink_fail",
            "expected": expected,
            "got": contract,
            "diffs": diffs,
        }
```

The agent gets a structured "this signature didn't match" instead
of the eventual link error. This is what catches v2_01.

### 6.4 At edit time (PreToolUse hook)

When the hook fires on Edit/Write to file `F`:
- Look up `TypeContract` for `F` if any.
- Lookup `TypeLink` edges *into* `F` (consumers).
- If consumer count > 0, inject "N files reference symbols in F:
  `Customer.add_address` (test_shop.py:42), …" into the
  system-reminder. The agent sees what it's about to break.

Optional hard mode (`LOOM_HOOK_BLOCK_ON_TYPELINK_DRIFT=1`):
- Run `extract_contract(F)` after the edit attempt.
- If the new contract is non-additive over the old, block the edit
  with a structured error.

### 6.5 At `loom sync`

The generated `REQUIREMENTS.md` gets a new "Public API" section
per-spec listing the declared public symbols + the consumers
counted from the type-link graph. Living docs become *living
type docs* too.

## 7. CLI surface

```bash
# Re-extract type contracts for tracked files (does this for you on
# loom link automatically; this is for re-syncing after edits).
loom typelink scan [--path <subtree>] [--language <lang>]

# Show the type contract for a file.
loom typelink show <file> [--json]

# Find consumers of a symbol.
loom typelink consumers Customer.add_address

# Show what's drifted since a spec was approved.
loom typelink drift [--spec SPEC-xxx]

# Verify the public API against the spec.
loom typelink check [--spec SPEC-xxx] [--file F] [--strict]

# View a contract diff (between current and the spec's expectation).
loom typelink diff <file>
```

`loom typelink check --strict` exits with code 2 (drift convention)
when the file's contract doesn't match the spec's expectation. Use
in CI.

## 8. Failure semantics

A `typelink_fail` outcome surfaced from `loom_exec` looks like:

```json
{
  "outcome": "typelink_fail",
  "task_id": "TASK-...",
  "file": "include/types/customers.hpp",
  "expected_signature": "Address::Address(std::string street, std::string city, std::string postal_code)",
  "got_signature": "Address::Address(std::string a, std::string b)",
  "consumers_affected": [
    "test/shop_test.cpp:74"
  ],
  "diff": [
    {"kind": "param_count", "expected": 3, "got": 2},
    {"kind": "param_name", "pos": 0, "expected": "street", "got": "a"}
  ]
}
```

The structured form lets the calling agent (in production-mode use,
the user's Claude Code session; in bake-off use, retry-with-feedback
in the executor) make a precise fix. Today's `compile_failed=True`
+ a 2 KB error tail is much harder to act on.

## 9. Migration / coexistence

Existing Loom stores have no type contracts. Migration:
- `loom typelink scan` is idempotent — runs across every linked
  file, extracts a contract, persists.
- Specs without `public_api_json` are tagged "legacy"; verifiers
  skip them. Adding `public_api` to a spec is a `loom spec
  refine` operation.
- Hook behavior is unchanged unless `LOOM_HOOK_BLOCK_ON_TYPELINK_DRIFT=1`
  is set — gradual adoption.

The Specification's existing prose `description` stays the source
of truth for "what we're building"; `public_api_json` is the
*verifiable surface* of that prose. The two complement each other:
prose for understanding, public_api for enforcement.

## 10. Connections to existing primitives

- **Drift (Phase F)**: today's drift is content-hash; type-link
  drift is a stricter, more useful notion of "this file changed in
  a way that breaks consumers." Subsumes today's drift for many
  cases.
- **Contract data plane** (rolled back): the earlier
  `Specification.contracts_json` was right in spirit but bound
  qwen too tightly to specific tokens. Type contracts are *less
  prescriptive* (what the public surface must be, not how the
  bodies are written) but *more enforceable* (machine-checked,
  not LLM-checked).
- **Pre-edit hook**: today the hook tells you "what reqs apply
  here." Tomorrow it tells you "what consumers depend on the
  public symbols you're about to edit."
- **`loom decompose`**: today the decomposer emits tasks with
  `files_to_modify`. Tomorrow it emits tasks with a *target
  public_api per file*, derived from the spec's `public_api_json`.
  Each task carries its acceptance criterion in machine-checkable
  form.

## 11. Open questions

These need answers before implementation:

1. **How prescriptive should `public_api` be?** Strict matching
   feels right for v1 ("this is the contract") but might be too
   brittle when implementations need to add private helpers or
   minor signature tweaks. Solution path: `additive_check` for
   "is this a non-breaking addition?" and a strict `diff` for
   "does this match the spec exactly?"

2. **Who authors `public_api` initially?** Asking users to type
   structured signatures is friction. Three options:
   - LLM extraction from prose spec (drafty but unblocking).
   - Auto-generation from a passing first task (use the task's
     output as the contract; ratchet from there).
   - Required at `loom spec --add` time, validated immediately.
   v1 ships option 1 + option 2; user chooses per-spec.

3. **Cost of language tooling**. libclang is heavy; tsc takes a
   second; dart-analyze runs a JIT. Per-task overhead matters for
   the asymmetric pipeline. Solution: run extractor in a daemon
   process, feed via stdin/stdout — most language tools support
   this. Or: cheap regex extractors for v1, swap in proper tools
   later.

4. **What does drift look like across languages?** A Python
   `dataclass` and a TypeScript `interface` describe the same
   conceptual `Customer` differently. v1 is per-language. v2
   would have a "logical Customer" entity that maps to per-language
   manifestations and verifies they agree on field set.

5. **Performance at scale.** A 500-file repo has thousands of
   public symbols. Hook latency is currently ~800 ms; we don't
   want to blow that up. Type-link queries need to be O(1) or
   O(log N) — well-served by ChromaDB's id lookups for direct
   queries. The per-edit re-extraction is the bottleneck; only
   re-extract files actually touched.

6. **False positives**. Strict checks could reject correct-but-
   stylistically-different code (e.g. `void f(int x)` vs
   `void f(int)`). Canonicalization matters. Need a robust
   normalization pass and probably an `--ignore` list for
   stylistic differences.

## 12. Staging — Milestone 7 detailed

| stage | scope | days | tests | gates |
|---|---|---:|---|---|
| **7.1 manual public_api** | Spec gains `public_api_json` field; CLI commands `loom typelink show/check/diff`; manual authoring; one-language verifier (Python ast) | 2 | unit tests on extract_contract; CLI tests | spec dataclass back-compat; existing tests pass |
| **7.2 C++ verifier** | libclang or regex extractor for C++ | 2-3 | extract real cpp-inventory v2_01 file and detect the v2_01 mismatch | typelink check correctly fails v2_01, passes v2_02 |
| **7.3 wire into loom_exec** | post-task `typelink_fail` outcome + retry-with-feedback hook | 1 | re-run cpp-inventory v2 N=10 with TYPELINK=1; confirm typelink catches v2_01-class failures cheaply | pass rate ≥ 80%, with failure tails categorized |
| **7.4 TS + Dart verifiers** | tsc + dart-analyze backends | 2-3 each | extract real ts-inventory + dart-inventory files | per-language extraction correct on the inventory benchmarks |
| **7.5 LLM extraction** | auto-derive `public_api_json` from prose spec | 1-2 | round-trip: spec text → public_api → reconstructed prose | round-trip fidelity > 90% on 5 hand-checked specs |
| **7.6 hook integration** | PreToolUse extends to flag type-link drift | 1 | hook fires on a deliberate signature change in cpp-inventory; surfaces consumers; optional block | latency ≤ 1.5× current hook |
| **7.7 cross-file consistency** | type-link graph + drift detection across the graph | 2 | demo: rename `Customer.email` in customers.hpp → 4 consumer files flagged | drift detected within hook latency budget |

**Minimum viable to test the v2_01 hypothesis: 7.1 + 7.2 + 7.3.**
About 5–6 focused days. Re-running cpp-inventory v2 N=10 with
typelink would predict the residual 20% failure rate becoming a
clean reject + retry instead of a final-grade fail.

If 7.1–7.3 land cleanly, the rest of milestone 7 follows naturally.
If 7.1–7.3 expose unexpected complexity, we re-scope before
committing to 7.4+.

## 13. What this changes for the project narrative

**Before milestone 7:** Loom is a context substrate that helps
agents make consistent decisions and detects when they don't.
Validation is post-hoc (drift, conflicts).

**After milestone 7:** Loom is a context substrate AND a real-
time consistency enforcer. The agent learns about a contract
violation at task-completion time, not at grade time. Cross-
session edits surface their consumer impact before the edit
lands. The "stored-but-never-read" gap (Phase F) closes for type-
level decisions, not just content.

This is the kind of capability that changes whether multi-agent
work is *feasible*, not just possible. It's plausible-sounding
that this is the missing fundamental piece.

## 14. What we'd lose by not building this

A sober honest case: today Loom works perfectly well for solo-
agent, single-session, language-agnostic projects. The
type-checker your IDE/build runs catches everything we'd catch
in the typelink layer.

But:

- Multi-agent coordination is bottlenecked by *invisible cross-
  file agreements* that no single agent's context window covers.
- Multi-session continuity (Phase G) is bottlenecked by the same
  problem at the type level.
- The asymmetric pipeline (qwen-executes) hits ceilings precisely
  on cross-file type consistency (cpp-inventory v2_01,
  dart-inventory's named-args cluster).
- Real production projects have real type drift across modules
  that today's drift detection misses entirely.

The risk of *not* building this: Loom remains a useful
documentation / requirements tool but doesn't become the
context substrate it was designed to be for multi-agent
multi-language code generation.

## 15. Recommendation

Treat this as **Milestone 7 — high priority**. Add to
`ROADMAP.md` with the 7-stage breakdown above. Don't start
implementation until 7.1–7.3 scope is reviewed (spec dataclass
extension, Python verifier, wire-in to loom_exec).

If the user agrees this is a real pivot, hold the TS benchmark
and other "more cells" experiments — those add data points to a
known story. Milestone 7 is a *new capability* that changes
which stories are tellable.

If the user wants more validation data before pivoting, finish
the queued runs (Flutter, cpp v2 N=10, TS N=5) for completeness,
then start milestone 7.

Either is defensible. Both should not happen in parallel unless
we're staffed for it.

---

## 16. Scope resolution (post-audit)

[`FAILURE_AUDIT.md`](../experiments/bakeoff/FAILURE_AUDIT.md)
empirically settled the "is this fundamental" question with
**27 / 28 (96 %) of multi-file failures classified as
typelink-shaped** (real number 28 / 28 with one regex
mis-classification corrected). With that, the open questions
worth resolving for v1 are:

### 16.1 Q6 — public_api authorship default

**Audit-driven resolution: leverage what Opus already produces.**

Every failed multi-file trial in our 28-failure cluster used a
spec that *already contained* a `dart-contract` /
`python-contract` / `cpp-contract` fenced block, emitted by Opus
under the planner system prompt we built during the
negotiated-contract work (then rolled back). Those fenced blocks
are *exactly* the public_api in machine-extractable form.

The contract data plane we rolled back was right in spirit —
the implementation bound qwen too tightly to specific tokens.
Typelink reuses the same data for a different purpose:
*structural verification* of the produced output, not
*token-level binding* of the input.

**v1 default:** at `loom spec --add` time:

1. Look for fenced declaration blocks in the spec text
   (`*-contract` fences). If found, extract them into
   `public_api_json` directly.
2. If no fences found AND `LOOM_TYPELINK_LLM_EXTRACT=1`, run a
   one-shot LLM extraction over the prose (cost: ~$0.05 per spec).
3. Otherwise: spec is "legacy" — typelink layer is a no-op for it.

**v1 user override:** `loom spec public-api SPEC-xxx --edit` opens
a structured editor for hand-correction.

**v1 ratchet (deferred to v2):** auto-derive from the first
passing task. Useful for incremental edits but not for our
greenfield-failure cluster, so out of v1 scope.

### 16.2 Q7 — language scope

**Audit-driven resolution: Dart-first, Python second, defer C++/TS.**

Per-language failure counts:

| language | typelink-shaped failures | tooling cost |
|---|---:|---|
| Dart (orders + inv + flutter) | **24 / 28 (86 %)** | medium (regex v1; dart-analyze v1.5) |
| C++ | 4 / 28 (14 %) | heavy (libclang) |
| Python | **0 / 28** | cheapest (stdlib `ast`) |
| TypeScript | not benchmarked | medium (tsc) |

Conclusion: **the failures live in Dart.** Python has zero
typelink failures (the python-inventory benchmark passed every
trial). Building Python-only would validate the architecture
without addressing where the actual problems live.

**v1 language ship list:**

1. **Dart (regex extractor)** — catches the 24 typelink failures.
   A careful regex over `class X { ... }` and `Type method(...)`
   declarations covers the inventory benchmark's surface; matches
   what we already do in `validate_blueprint`. ~50 ms per file.
2. **Python (stdlib `ast`)** — adds Python coverage at near-zero
   cost. Useful for python-inventory regression testing and as
   the architecture validator.

**v1.5 upgrade path:** Dart `dart analyze --machine` JSON output
for fuller fidelity (handles edge cases regex misses). ~500 ms
JIT cold; can be amortized via daemon.

**v2 / deferred:**
- C++ (libclang or full clang invocation) — covers the 4
  cpp-inventory failures
- TypeScript (tsc) — needed when we add TS benchmarks to the
  bake-off

### 16.3 v1 implementation surface (revised)

With Q6 + Q7 resolved, v1 is significantly tighter than the
original 7-stage plan:

| stage | original scope | v1 scope (post-audit) | days |
|---|---|---|---:|
| 7.1 | manual public_api + Python ast | spec field + extract from `*-contract` fences + Python `ast` extractor + CLI `loom typelink show/check/diff` | 2 |
| 7.2 | C++ verifier | **Dart regex extractor** (covers the failure cluster) | 1-2 |
| 7.3 | wire into loom_exec | post-task `typelink_fail` outcome on dart-inventory + cpp-inventory v2 reruns | 1 |

**v1 minimum: 4–5 focused days** (was 5–6 in the original
estimate). Tightened by:
- Dropping libclang setup (deferred to v2)
- Reusing Opus's existing fenced-block emission as the authorship
  default (no new LLM-extraction code on the critical path)
- Regex-based Dart extractor (defers dart-analyze daemon work)

### 16.4 What v1 measurably changes

After v1 lands, we re-run:

1. **dart-inventory N=5 with `LOOM_TYPELINK=1`.** Prediction: of
   the 9/9 typelink-shaped failures we saw, the typelink check
   intercepts each at task time and emits a structured
   `typelink_fail` with the missing-symbol/signature-mismatch
   diff. The chain still terminates (we're not adding retry
   logic in v1) but the diagnostic is precise — no more
   "the test couldn't load" tails.
2. **cpp-inventory v2 N=10 with `LOOM_TYPELINK=1`.** Prediction:
   v2_01-class failures (1/5 in our existing data) show up as
   `typelink_fail` rather than final-grade compile fails.
3. **python-inventory N=5 with `LOOM_TYPELINK=1`.** Prediction:
   no behavior change (Python had 0 typelink failures); the
   feature is silently passing. This is the regression check.

The deliverable for v1 is therefore: **structured diagnosis of
the 28-failure multi-file cluster.** Not yet a fix (that's v2's
retry-with-typelink-feedback), but a clear signal that we
*understand* what failed, well enough to feed back to the agent
in production-mode use.

### 16.5 Out of v1 scope (explicitly)

- Cross-file consumer graph (TypeLink edges into a file) — v2
- PreToolUse hook integration (warn on edits) — v2
- LLM extraction from prose for legacy specs — v2
- TypeScript and C++ verifiers — v2
- Retry-with-feedback loop in `loom_exec` — separate decision
- Cross-language unification — v2+

### 16.6 Decision needed

Three things to confirm before I start building v1:

1. **Dart-first scope?** Audit says yes; alternative is
   Python-first (cheaper but doesn't address actual failures).
2. **Reuse existing `*-contract` fences as authorship default?**
   Trades simplicity for reliance on the planner's fence
   discipline. Alternative is to require structured
   `--public-api` at `loom spec --add` (more friction; better
   UX guarantees).
3. **v1 deliverable = diagnostic only, no retry?** Means v1
   doesn't *fix* the failures, just *explains* them. The fix
   layer is a separate decision.
