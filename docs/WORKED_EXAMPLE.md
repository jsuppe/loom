# Worked Example: Loom in production mode

This document walks through the production-mode workflow of Loom end
to end, using the `python-inventory` benchmark as a real, runnable
example. Reader follows along from a Claude Code session, with
Loom as a tool the assistant invokes.

The example builds an 8-module Python library for a shop domain
(customers + products + inventory + orders) over an in-memory
persistence store. Reference passes 28/28 hidden tests.

## What "production mode" means

The session you're in is the architect. Loom is the persistence
layer for the architect's decisions. `loom_exec` dispatches body
implementation to a small local model (qwen3.5:latest by default).
When body work fails on a missing-symbol error, the structured
failure surfaces back to the architect for amendment.

```
You ask Claude Code for something
        │
        ▼
Claude Code (you, the architect)
   - reads the requirement
   - writes a spec
   - decomposes into tasks
   - invokes loom_exec
        │
        ▼
loom_exec (orchestrator)
   - claims next ready task
   - assembles context bundle from the Loom store
   - calls qwen3.5 once
   - applies output to a scratch copy
   - runs the gating test
   - on pass: promotes to working tree, marks task complete
   - on fail: surfaces error tail back to the architect
        │
        ▼
Hidden test suite (the grader)
   - runs only after all tasks complete
   - reports pass/total
```

## Setup

```bash
# Install Loom (one-time):
pip install loom-cli                   # registers `loom` and `loom_exec` on PATH
# Or, from a clone in dev mode:
#   pip install -e .

# Install Ollama deps (one-time):
ollama pull qwen3.5:latest
ollama pull nomic-embed-text           # default embedding provider
ollama serve                            # must be running on localhost:11434
```

For a step-by-step onboarding guide with success indicators, see
[`docs/GETTING_STARTED.md`](GETTING_STARTED.md). This document is
the deeper-dive walkthrough on a real benchmark.

## Step 1 — Capture the requirement

Loom holds *decisions* and their *rationale*. The first thing the
session does is record what we're building and why.

```bash
loom extract -p shop --rationale "Multi-service shop with snapshot/restore for testability" <<EOF
REQUIREMENT: behavior | Implement an 8-module Python library exposing
CustomerService, InventoryService, OrderService over an in-memory
Store, with Snapshot deep-copy semantics on mutable state.
EOF
```

This creates a `Requirement` (REQ-xxxx) with id, domain, value,
rationale, timestamp. Embedding-indexed, queryable.

## Step 2 — Write the spec

The architect (the Claude Code session) drafts a spec. In the
asymmetric-pipeline workflow, Opus wrote the spec from a README;
in production-mode that draft is a turn in *your* session.

```bash
loom spec REQ-xxxx --description "$(cat <<'SPEC'
The library is split across 9 implementation files...

### shop/errors.py
DomainError(Exception) hierarchy with subclasses ValidationError,
NotFoundError, ConflictError, InsufficientStockError,
InvalidTransitionError, ReservationError. Each subclass body is
just `pass` (no extra fields).

### shop/types/customers.py
Customer @dataclass with id, name, email, addresses=field(default_factory=list).
__post_init__ validates: id non-empty, name non-empty, email contains '@'.
Raises ValidationError on each. Address is @dataclass(frozen=True)
with street, city, postal_code.

### shop/types/products.py
Product @dataclass(frozen=True) with sku, name, price.
__post_init__ validates: sku non-empty, name non-empty, price > 0.

(...and so on for all 9 files)
SPEC
)"
```

Opus is competent at producing this kind of detailed prose spec from
a README. Inside *your* session, you'd write it as part of natural
conversation: "I'm going to build this 9-module shop library. Here's
the design..."

The spec gets a SPEC-xxxx id and is stored alongside the requirement.

## Step 3 — Decompose into atomic tasks

```bash
loom decompose SPEC-xxxx --target-dir /path/to/workspace --apply
```

`loom decompose` parses the spec and proposes one Task per
implementation file, with dependency edges (errors before types,
types before services, etc.). `--apply` writes them to the store.

Each Task carries: title, files_to_modify (list), test_to_write
(grading test path), context_reqs/specs/files (what to bundle into
the executor prompt), size_budget_loc, depends_on.

You can list them:

```bash
loom task list
```

## Step 4 — Drain the queue with loom_exec

```bash
loom_exec --next --loop --model qwen3.5:latest --target-dir /path/to/workspace
```

For each ready task, loom_exec:

1. Claims the task (`pending → claimed`).
2. Assembles the prompt: the spec text + the relevant section + the
   target file contents + the gating test.
3. Calls qwen3.5 once (temperature 0).
4. Extracts the code block.
5. Applies it to a scratch copy of the workspace.
6. Optionally runs `LOOM_EXEC_STATIC_CHECK=1` for a language-aware
   syntax/type pass *before* grading. (This catches structural errors
   like missing required getter or stripped `const` cheaply.)
7. Runs the gating test in scratch.
8. If pass: promotes the modified file back to the working tree,
   marks the task `complete`.
9. If fail: rejects the task with the error tail, marks it
   `escalated` so the architect can address it.

Output looks like:

```
[exec] task TASK-...  status=pending  title='Implement shop/errors.py...'
[exec] target_dir: /path/to/workspace  runner: pytest (append)
[exec] prompt: 26562 chars
[exec] claimed by qwen3.5:latest
[exec] calling qwen3.5:latest...
[exec] model: 5.3s  in=7355  out=82
[exec] static_check: ok
[exec] grading: 1/1
[exec] task TASK-... complete
```

## Step 5 — Architect-mode amendment when something fails

If a task fails, loom_exec emits the structured failure and stops
the chain (downstream tasks have `depends_on` and won't run).

Example failure:

```
[exec] task TASK-... status=pending  title='Implement shop/types/inventory.py...'
[exec] static_check: FAIL
[exec] static_check tail: shop/types/inventory.py:5: error: name 'sku'
       is not defined in StockLevel.__init__
```

You see this in your conversation. You as the architect amend:

```bash
# Inspect the spec section that failed
loom task show TASK-...

# The contract for shop/types/inventory.py was missing a `sku` field
# on StockLevel. Update the spec.
loom refine SPEC-xxxx --description "...corrected version..."

# Mark the failed task ready to re-run
loom task release TASK-...

# Re-drain
loom_exec --next --loop --model qwen3.5:latest --target-dir ...
```

The decision *what to amend* is yours. loom_exec's job is to
surface the failure with enough signal that you can decide
quickly. The amendment itself is a normal Loom action (`loom
refine`); the spec store carries the change forward and downstream
tasks pick up the new version.

## Step 6 — Final grading

After all 8 tasks complete, the hidden test suite runs:

```bash
pytest tests/test_shop.py -q
```

Reports `28 passed`. The combined product is end-to-end
functional, written by qwen, verified by hidden tests, with all
architectural decisions persisted in Loom for the next session to
pick up.

## Why this matters

The architect (you, in your Claude Code session) is doing what a
frontier model is good at: design, reasoning about cross-cutting
concerns, deciding when to amend a contract.

The implementer (qwen3.5 locally) is doing what a small code
model is good at: filling in concrete bodies given a tight spec
and a passing-test target.

The persistence layer (Loom) is what carries decisions across the
two — and across sessions — so neither party has to re-discover what
was already decided.

## What this exercises (and what it doesn't)

This walkthrough touches every primitive Milestone 0-1 covers
(`extract`, `spec`, `decompose`, `task`, `loom_exec`). It does
*not* exercise the pre-edit hook (Milestone 4.1, `loom_pretool.py`)
because the example is greenfield generation rather than edits to
existing code. For an in-session, editing-existing-code example
the hook is the load-bearing primitive — see Phase E findings.

## Limitations

- `loom_exec` uses qwen3.5:latest as default. For Dart at 9 files
  this is below the complexity ceiling; use a code-specialized model
  there. See `experiments/bakeoff/FINDINGS-bakeoff-v2-phaseC-inventory.md`
  for the per-language fitness map.
- Architect-mode amendment in production today is *manual*: you
  read the failure tail and decide what to change. The
  automated-amendment data plane (`Specification.contracts_json`,
  `ContractAmendment` event log) was explored experimentally and
  rolled back; if reintroduced it would let the architect's
  amendments replay across sibling tasks automatically.
- This example is greenfield. For drift-detection-on-edit see the
  Phase E + F docs.
