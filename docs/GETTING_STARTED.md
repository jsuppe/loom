# Getting Started with Loom

A focused walk-through to take you from `pip install` to your first
Loom-driven workflow on a real project. Every step has a **success
indicator** so you know it worked before moving on.

This guide is deliberately scoped: enough to feel productive in 30
minutes, no more. For the deeper end-to-end pipeline (decompose →
small-model execution → drift detection), see
[`WORKED_EXAMPLE.md`](WORKED_EXAMPLE.md). For the underlying validated
claims, see [`../README.md`](../README.md#validation--whats-been-measured-830-trials).

---

## What you'll have at the end

A target repo with:
- A populated Loom store: requirements (with rationale), one spec, one
  link from a code file.
- `loom doctor` reporting green.
- A `.loom-config.json` pinning your project name and runtime.
- The PreToolUse hook firing on edits and injecting requirement context
  into your Claude Code session.
- `loom metrics` and `loom health-score` returning real numbers.

---

## 1. Install

### Prerequisites

| Required | Version | Why |
|---|---|---|
| Python | 3.10+ | The package targets modern Python |
| Ollama | any recent | Default embedding provider + recommended local executor |

### Pick an embedding provider

Loom needs to embed text. Three options, in order of effort:

1. **Ollama** (default) — `ollama serve` running on localhost, with
   `nomic-embed-text` pulled. Free, local, private, deterministic.
2. **OpenAI** — set `OPENAI_API_KEY`, run with
   `--embedding-provider openai`. Costs ~$0.02 / 1M tokens; remote.
3. **`hash`** — deterministic SHA-256 pseudo-embedding, useful for
   tests / offline / "I don't care about semantic search yet."
   `--embedding-provider hash`.

We'll use Ollama in this guide.

### Install Loom

```bash
# From PyPI:
pip install loom-cli

# Or, from a clone (dev mode):
git clone https://github.com/jsuppe/loom.git
cd loom
python3 -m venv .venv
. .venv/bin/activate          # or .venv/Scripts/activate on Windows
pip install -e '.[dev]'
```

### Pull Ollama models

```bash
ollama pull nomic-embed-text   # 274 MB — embeddings
ollama pull qwen3.5:latest     # 5.6 GB — local executor for loom_exec
ollama serve &                  # background, must be running on localhost:11434
```

### Success indicator

```bash
loom --help
```

Should print the usage banner with subcommands listed
(`extract`, `check`, `link`, `status`, `query`, `list`, …,
`archive`, `stale`, `metrics`, `health-score`, `task`, `decompose`).

If `loom: command not found`: confirm the install put scripts on
PATH (`pip show loom-cli` to find the install location), or use
`python -m loom.cli` instead.

---

## 2. Onboard your project

Pick any repo you'd like to track requirements for. (For this guide,
a small Python repo with a `tests/` directory is ideal — Loom will
auto-detect pytest as the runner.)

```bash
cd ~/path/to/my-project
loom init
```

`loom init` writes a `.loom-config.json` at the repo root pinning
defaults: project name (defaults to git repo name), runtime, test
directory, ignore list. It also runs a health check — Ollama
reachable, required models pulled, pytest declared, `tests/` directory
present.

### Success indicator

```bash
loom doctor
```

Should print green checks for: Ollama connectivity, embedding model
loaded, store readable, store directory writable.

If `loom doctor` complains about Ollama: confirm `ollama serve` is
running and `curl http://localhost:11434/api/tags` returns JSON.

---

## 3. Capture your first requirement

Loom's primary unit is a **requirement** — a decision about how
something should work, captured with its *rationale* (the why).

```bash
echo "REQUIREMENT: behavior | Users must confirm before deleting any record" \
  | loom extract --rationale "Prevent accidental data loss; restoring deletes is expensive."
```

You'll see something like:

```
✓ REQ-abc12345: [behavior] Users must confirm before deleting any record
```

Pin that ID — we'll use it.

### Success indicator

```bash
loom list --json | jq '.[0] | {id, domain, rationale}'
```

```json
{
  "id": "REQ-abc12345",
  "domain": "behavior",
  "rationale": "Prevent accidental data loss; restoring deletes is expensive."
}
```

`rationale` is the bit that lets a future agent — running in a fresh
session, with no in-context memory of you — understand *why* the rule
exists. Phase G validated this empirically: agents respect a
contrarian-looking rule 93% of the time when the rationale is
delivered (vs 67% with rule alone).

---

## 4. Expand the requirement into a spec

Specs are the *how*. They're the anchor for tasks and implementations.

```bash
loom spec REQ-abc12345 \
  -d "Confirmation modal: show modal on delete-button click; require Type-to-confirm input when deleting more than 10 items at once." \
  -c "Modal appears on delete click" \
  -c "Type-to-confirm required for batch deletes >10 items" \
  -c "Cancel button closes the modal without action"
```

### Success indicator

```bash
loom specs --json | jq '.[0] | {id, parent_req, description}'
```

You should see your SPEC-id, parent_req pointing back at REQ-abc12345,
and the description.

---

## 5. Link your first code file

Pick any source file in your repo that's relevant to this requirement
(or create one as a stub for the walkthrough). Then:

```bash
loom link src/storage.py --req REQ-abc12345
```

This stamps an `Implementation` record with a content hash; if the
file changes later and the requirement gets superseded,
`loom check src/storage.py` will flag the drift.

### Success indicator

```bash
loom trace REQ-abc12345 --json
```

Should show your file under `implementations`. And:

```bash
loom check src/storage.py --json | jq '.linked, .drift_detected'
```

`true`, `false`. Linked, no drift.

---

## 6. Wire up the PreToolUse hook (optional but recommended)

The hook makes Loom *automatic* — every time Claude Code edits a
tracked file, it sees the linked requirements + rationale + drift
warnings injected as a system-reminder. No agent action required.

Add to `.claude/settings.json` in your repo:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PROJECT_DIR}/hooks/loom_pretool.py"
          }
        ]
      }
    ]
  }
}
```

(Adjust the `command` path to wherever you cloned Loom.)

Restart Claude Code (or run `/hooks` to reload). On the next Edit to
a linked file, you should see something like:

```
Loom: src/storage.py linked to 1 req(s)
  - REQ-abc12345 [behavior]: Users must confirm before deleting any record
    Rationale: Prevent accidental data loss; restoring deletes is expensive.
```

### Success indicator

```bash
loom cost
```

Should report at least one `fired: true` entry. If `overhead_pct` is
high, that means most of your edits are on files Loom doesn't track
yet — keep linking.

---

## 7. Telemetry: are we actually getting value?

Loom logs every meaningful operation. Two commands roll the log up:

```bash
loom metrics --since 30
```

```
Requirements:  1 total — 1 active, 0 archived, 0 superseded
Coverage:      1/1 have linked code (100.0%); 0/1 have test specs (0.0%)
Activity:      1 extracted, 1 linked
Staleness:     never=0  >30d=0  >60d=0  >90d=0
```

```bash
loom health-score --json
```

```json
{
  "score": 75,
  "components": {
    "impl_coverage": 100.0,
    "test_coverage": 0.0,
    "freshness": 100.0,
    "non_drift": 100.0
  },
  "active_requirements": 1
}
```

`75/100`, dragged down because we haven't added a test spec. Perfect —
that's the signal working.

```bash
loom test add REQ-abc12345 \
  -d "User clicks delete; modal appears; clicks confirm; row removed." \
  --automated
```

Re-run `loom health-score` — now `100`.

---

## 8. (Optional) Bigger workflow: decompose + executor

For larger work, Loom can ask a frontier model to **decompose** a spec
into atomic tasks, then drain those tasks through a small local model.
That's beyond the "getting started" scope; the full walkthrough is in
[`WORKED_EXAMPLE.md`](WORKED_EXAMPLE.md).

Quick taste:

```bash
# Decompose (uses Anthropic Opus if ANTHROPIC_API_KEY is set;
# falls back to ollama:qwen2.5-coder:32b otherwise)
loom decompose SPEC-xxx --apply

# Drain the queue against your local executor
loom_exec --loop
```

Each task gets ≤2 files / ≤80 LoC, a single grading test, and a
context bundle assembled from the spec + linked patterns. The executor
runs in a scratch copy and only promotes on test pass.

---

## What to do next

- **Hygiene as you go.** `loom stale --older-than 90 --json` to find
  cold or unlinked requirements; `loom archive REQ-xxx` to retire ones
  no longer relevant. See [`../README.md`](../README.md) for the full
  command reference.
- **Living docs.** `loom sync` regenerates `docs/REQUIREMENTS.md` and
  `docs/TEST_SPEC.md` from the store with a traceability matrix.
  Don't edit those files directly — they're regenerated.
- **CI gating.** Wire `loom health-score --json | jq .score` into your
  CI pipeline. Fail the build if it drops below your threshold.
- **Agent integration.** See
  [`../agents.d/loom-integration.md`](../agents.d/loom-integration.md)
  for the AGENTS.md snippet — the agent will then invoke Loom at the
  right moments without prompting.
- **MCP server.** Wire Loom into Claude Code as typed tools instead of
  shelling out: see [`../mcp_server/README.md`](../mcp_server/README.md).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `loom: command not found` after install | Confirm `pip show loom-cli`; activate the venv if you installed there. Or use `python -m loom.cli`. |
| `Ollama unavailable` warning on every call | Either start Ollama (`ollama serve`) or switch to `--embedding-provider hash` for offline mode. |
| `loom check` always says drift_detected | The file's linked requirement was superseded. Use `loom trace` to see which one and decide whether to re-link or update. |
| Hook never fires | Run `/hooks` in Claude Code to reload. Confirm the matcher pattern actually matches your tool name (`Edit\|Write\|MultiEdit\|NotebookEdit` — pipe-separated). |
| `loom metrics` shows zero activity | The event log lives at `~/.openclaw/loom/<project>/.loom-events.jsonl`. Confirm the file exists and you've used `extract`/`link`/`check` since installing the M5 release. |
| `EmbeddingDimensionMismatch` | You changed `LOOM_EMBEDDING_PROVIDER` on a populated store. Either revert, use a fresh `-p` project, or re-embed (a `loom migrate` command may land in v1.x). |

---

## Where to go for more

- [`../README.md`](../README.md) — overview, validation findings, full command reference.
- [`WORKED_EXAMPLE.md`](WORKED_EXAMPLE.md) — end-to-end walkthrough on a real benchmark with `loom_exec`.
- [`../ROADMAP.md`](../ROADMAP.md) — milestones, what's shipped, what's next.
- [`../experiments/bakeoff/`](../experiments/bakeoff/) — ~830 trials of empirical evidence across 9 languages.
