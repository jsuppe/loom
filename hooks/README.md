# Loom hooks

Harness-level integration for Claude Code. These hooks run automatically on
tool events so an agent gets Loom context without having to remember to call
`loom check` / `loom trace` / `loom status` every time.

## loom_pretool.py

A `PreToolUse` hook that intercepts `Edit` / `Write` / `MultiEdit` /
`NotebookEdit` tool calls, runs `loom context <file>`, and injects the
briefing (linked requirements, specs, drift) into the agent's context
as a system-reminder. Non-blocking by default.

Why this exists: `loom` only helps when it's consulted at the right moment.
Putting that call in a hook makes it automatic — the harness executes the
hook, not the agent, so it can't be forgotten.

### Install (project-local)

Add to `.claude/settings.json` in this repo (or the repo you're editing
with Loom tracking enabled):

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

### Install (user-global)

Add the same block to `~/.claude/settings.json`, pointing at an absolute
path (since `CLAUDE_PROJECT_DIR` expands per-project):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/loom/hooks/loom_pretool.py"
          }
        ]
      }
    ]
  }
}
```

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LOOM_BIN` | `loom` on PATH (registered by `pip install loom-cli`), else sibling `scripts/loom` shim | Loom CLI path |
| `LOOM_PROJECT` | auto-detected from git | Override project name |
| `LOOM_HOOK_BLOCK_ON_DRIFT` | `0` | Set to `1` to fail the tool call on drift |
| `LOOM_HOOK_DEBUG` | `0` | Set to `1` to log hook activity to stderr |
| `LOOM_HOOK_LOG` | `~/.openclaw/loom/<project>/.hook-log.jsonl` | JSONL activity log. Set to empty string to disable. |

### Measuring cost

Every fire appends a JSONL line with `{ts, tool, file, latency_ms, bytes,
reqs, specs, drift, fired, skipped}`. Read it back with `loom cost`:

```
$ loom cost
Fires:         127
  injected:    45 (35.4%)
  empty:       82 (64.6% overhead)
Latency (ms):  p50=1.4  p95=5.1  p99=12.0  max=61.0
Injected:      7823 bytes total, 61.6 avg  (~1955 tokens total, ~15.4 avg)
```

Use `loom cost --json` for machine output and `--tail N` for a recent
window. `overhead_pct` = fires where the hook ran but had nothing to inject
(the file isn't linked to any requirement). High overhead means either the
file-to-req coverage is low, or the hook should narrow its matcher.

### What the agent sees

On an `Edit` to a tracked file, before the edit runs, Claude receives a
system-reminder like:

```
Loom: src/auth/login.py linked to 2 req(s) — DRIFT on REQ-abc12345
  - REQ-abc12345 [behavior] [SUPERSEDED]: users must confirm via email
    Rationale: legal review 2025-08-12 mandated double opt-in
  - REQ-def67890 [behavior]: session cookies rotate every 24h
```

The `Rationale:` line shows up when the requirement was extracted with
`--rationale`. This is the cross-session memory channel — a future
agent reading it gets the *why*, not just the *what*. Phase G (in
`experiments/bakeoff/FINDINGS-bakeoff-v2-phaseG.md`) showed Haiku's
compliance rises from 67% to 93% and citation rate from 0% to 100%
when the rationale is delivered alongside the rule.

If `LOOM_HOOK_BLOCK_ON_DRIFT=1` is set and any linked requirement is
superseded, the edit is rejected and the message is returned as the
block reason — forcing the agent to either update the link (via
`loom supersede` / `loom link`) or explicitly override.

### Failure modes

The hook is designed to never block unrelated work:

- Loom CLI missing → exit 0, tool proceeds.
- `loom context` errors → exit 0, tool proceeds.
- Stdin JSON malformed → exit 0, tool proceeds.
- No linked requirements → exit 0 silently.

Set `LOOM_HOOK_DEBUG=1` to trace why the hook stayed quiet.

---

## loom_intake.py (M11.5)

A `UserPromptSubmit` hook that intercepts the user's chat message
*before* the agent sees it, classifies whether the message contains
a requirement-shape statement, runs `services.find_related_requirements`
to find prior decisions it might cite, and routes through six
branches: auto-link to existing decisions, propose candidates,
capture with prose rationale, flag as `rationale_needed`, recognize
duplicates, or no-op.

**Empirical motivation:** the M10.3 series (phQ3-phQ7) established
that **rationale is the load-bearing signal** for compliance on
contrarian specs — bare rule alone never works, rule + rationale
saturates. The M10 indexer amplifies rationale, doesn't manufacture
it. So rationale capture is the discipline that matters most, and
the discipline users skip most often. This hook shifts capture
from "user remembers to type `loom extract --rationale`" to "harness
intercepts and either captures or surfaces the gap."

The classifier was validated in M11.5 P0
(`experiments/pilot/FINDINGS-intake-classifier-pilot.md`):
**precision 95.2%, recall 100%, p50 latency 454 ms** on 40
hand-labeled chat utterances with `qwen3.5:latest`.

### Install (project-local)

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PROJECT_DIR}/hooks/loom_intake.py"
          }
        ]
      }
    ]
  }
}
```

### Manual testing (no registration)

Before enabling the hook on every chat session, you can drive the
exact same logic from the CLI:

```
$ loom intake --text "We should rate-limit refunds at 10/min — incident on 9/12."
$ loom intake --text "Can you fix the bug?"
$ loom intake --json --text "..." | jq .
```

This calls `loom.intake.process_message` directly, with the same
classifier + branch logic the hook uses. Useful for evaluating
behavior before wiring up the hook.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LOOM_PROJECT` | auto-detected from git | Override project name |
| `LOOM_INTAKE_MODEL` | `anthropic:claude-haiku-4-5-20251001` if `ANTHROPIC_API_KEY` set, else `ollama:qwen3.5:latest` | Classifier model |
| `LOOM_INTAKE_DAILY_BUDGET` | `30` | Cap on auto-link captures per day; downgrades to propose when exceeded |
| `LOOM_INTAKE_DEBUG` | `0` | Set to `1` to log hook activity to stderr |

### Six branches

| Branch | When | What it does |
|---|---|---|
| `noop` | Not requirement-shape, parse failure, or classifier error | Nothing — message passes through |
| `duplicate` | Predicted req_id collides with top candidate | Reminder: "this is a duplicate of REQ-X, use `loom refine` to update" |
| `auto_link` | Top-1 score ≥ 0.80 and no guardrails tripped | Persists with `rationale_links=[REQ-X]` (top-2 if both ≥ 0.78); reminder confirms capture |
| `captured_with_rationale` | No candidates above 0.66 but classifier extracted a verbatim rationale | Persists with prose rationale |
| `propose` | Candidates above 0.66 but below auto-link threshold OR a guardrail tripped | Returns top-2 candidates as a reminder; user picks; nothing persisted |
| `rationale_needed` | No candidates, no rationale | Persists nothing; reminder asks the agent to ask the user *why* |

### Three guardrails

1. **Softener detection.** If the classified value contains hedging
   language (`if possible`, `try to`, `would be nice`, `maybe`,
   `perhaps`, `consider`, `ideally`, `someday`, `nice to have`),
   downgrade auto-link to propose. Calibrated against the M11.5
   P0 false positive ("Make this faster if possible.").
2. **Domain whitelist.** Only `behavior`, `data`, and `architecture`
   trigger auto-capture. `ui`, `terminology`, and out-of-enum
   inventions like `security` (observed in P0) get downgraded to
   propose so the user can correct.
3. **Daily budget.** After `LOOM_INTAKE_DAILY_BUDGET` (default 30)
   auto-link captures in a project's intake log, the rest of the
   day's hits downgrade to propose. Prevents runaway capture.

### Logging

Every fire appends a JSONL line to
`~/.openclaw/loom/<project>/.intake-log.jsonl` with `{ts, branch,
captured_req_id, classifier_latency_ms, candidates_top_score,
candidates_count, rationale_source, ...}`. The M11.5 P3 phase will
add `loom intake-stats` to aggregate this log.

### What the agent sees

On a chat message that looks like a requirement, before the agent
responds, Claude receives a system-reminder like:

```
<system-reminder source="loom-intake">
Loom captured this as REQ-abc12345 derived from REQ-payment-rate-limit.
If that's wrong, archive with `loom set-status REQ-abc12345 archived`
and re-extract.
</system-reminder>
```

For a propose-branch case, the reminder lists candidates:

```
<system-reminder source="loom-intake">
Loom thinks this might be a requirement. Possible linkages:
  - REQ-payment-rate-limit: Rate-limit on every payment-path endpoint... (score 0.74)
  - REQ-abuse-detection: Detect rapid retries from a single IP... (score 0.69)
If one applies, run `loom extract --derives-from REQ-X --rationale "..."`.
If none, ask the user why this is needed and capture the rationale.
</system-reminder>
```

### Failure modes

The hook never blocks the user's prompt:

- Classifier LLM unavailable → exit 0, no reminder, log entry.
- Classifier returns malformed JSON → treat as "not a requirement,"
  no-op.
- `find_related_requirements` raises → fall through to no-candidates
  branch.
- `services.extract` raises (e.g. cycle) → reminder explains the
  rejection.
- Daily budget exceeded → downgrade to propose, log.
- Hook latency exceeds Claude Code's hook timeout → user prompt
  passes through unchanged.

Set `LOOM_INTAKE_DEBUG=1` to trace branch decisions.
