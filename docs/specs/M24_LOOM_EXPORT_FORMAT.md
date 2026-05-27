# M24 — `.loom/` Export Format Spec

**Locked:** 2026-05-26
**Status:** Locked before implementation.
**Scope:** the on-disk format `loom export` writes and `loom import` reads.

## Why this format exists

The SQLite store at `~/.openclaw/loom/<project>/loom.db` is the
per-developer source of truth. It contains embeddings (binary, 768-
float vectors), event logs, and other state that doesn't merge cleanly
across developers and isn't appropriate for git.

`.loom/` is the **team-shareable text-format snapshot** of the parts of
the store that DO belong in version control: requirements, specs,
patterns, impl links, and test specs. Each developer keeps their own
SQLite cache; the repo carries the canonical text.

## Layout

A `.loom/` directory at the repo root, with one JSONL file per
entity kind:

```
.loom/
├── manifest.json              # schema version + export metadata
├── requirements.jsonl         # all kinds: requirement/finding/methodology/hypothesis/process_rule
├── specifications.jsonl
├── patterns.jsonl
├── implementations.jsonl      # file links only — no content bodies, no embeddings
└── test_specs.jsonl
```

### `.loom/manifest.json`

```json
{
  "version": "m24-export-v1",
  "exported_at": "2026-05-26T12:34:56+00:00",
  "project": "loom",
  "loom_version": "1.0.0",
  "git_head": "abc123def",
  "entity_counts": {
    "requirements": 75,
    "specifications": 0,
    "patterns": 0,
    "implementations": 20,
    "test_specs": 0
  }
}
```

Manifest is regenerated each export. `git_head` records where the
export was taken from for traceability.

## Per-line entity shape

Each entity is one line of compact JSON, **sorted by id** within the
file. Field order is canonical (alphabetical within an entity). This
makes diffs minimal and git auto-merge work on disjoint changes.

### `requirements.jsonl` (one line per requirement)

```json
{"acceptance_criteria": [], "domain": "behavior", "elaboration": null, "id": "REQ-01d60fae", "kind": "requirement", "rationale": null, "rationale_links": [], "source_msg_id": null, "source_session": null, "status": "pending", "superseded_at": null, "timestamp": "2026-05-04T14:23:01+00:00", "value": "The system must support six distinct modes..."}
```

Notes:
- `last_referenced` is **excluded** — it's per-developer usage telemetry, not a property of the requirement.
- `kind` is always present (defaults to `"requirement"` if the source store predates M12.1).
- `rationale_links` preserved as a sorted list of REQ-ids for derivation-chain reconstruction.
- Nullable fields use JSON `null` not omitted-key, to keep the schema stable.

### `specifications.jsonl`

```json
{"elaboration": null, "id": "SPEC-43a53443", "parent_req": "REQ-2fc569f0", "status": "draft", "timestamp": "2026-04-22T09:00:00+00:00", "value": "..."}
```

### `patterns.jsonl`

```json
{"applies_to": ["REQ-2a621c40", "REQ-65f50316"], "id": "PAT-...", "name": "...", "rationale": "...", "timestamp": "2026-...", "value": "..."}
```

### `implementations.jsonl`

```json
{"content_hash": "65b3ad95c5496023911e83991845329a5bd7809c60833a0f6a0756400ddc7950", "file": "src/loom/intake.py", "id": "ea3d725dc6bba48b", "lines": "all", "satisfies": [{"link_type": "implementation", "req_id": "REQ-ec36bd89", "req_version": "2026-05-11T20:02:21+00:00"}], "satisfies_patterns": [], "satisfies_specs": [], "symbol_signature_hash": null, "symbol_ticket": null, "timestamp": "2026-05-26T10:00:00+00:00"}
```

Notes:
- `content` (the cached file body) is **excluded** — caller re-reads
  from the file on import.
- `content_hash` IS included so drift detection can sync across
  developers without each re-importing developer having to re-read
  every linked file at import time.
- `symbol_ticket` / `symbol_signature_hash` preserved for structural-
  drift continuity (M10.1).

### `test_specs.jsonl`

Mirrors `.loom-specs.json` shape — automated flag, steps, expected
outcomes — one TestSpec per line.

## What is NOT in `.loom/`

* **Embeddings** — regenerable on import; embedding-model-version-
  dependent (M3.2 dimension pinning). Each developer's local store
  re-embeds at import time using their configured provider/model.
* **Events log** (`.loom-events.jsonl`) — per-developer audit; not
  team-shareable signal.
* **Hook logs** (`.hook-log.jsonl`, `.intake-log.jsonl`,
  `.exec-log.jsonl`) — per-developer metrics.
* **chat_messages** — noisy + privacy-sensitive.
* **last_referenced timestamps** — per-developer usage telemetry.
* **`_loom_meta.embedding_dim`** — set by first vector write on the
  importing developer's store; not portable across embedding models.

## Determinism rules (LOCKED)

For round-trip integrity (M24.3):

1. **Entities sorted by id** within each file.
2. **Field order alphabetical** within each entity (using
   `json.dumps(..., sort_keys=True, ensure_ascii=False)`).
3. **No trailing whitespace.** One `\n` per line.
4. **UTF-8 encoding, LF newlines** (not CRLF, even on Windows).
5. **Timestamps in canonical ISO-8601 with `+00:00` zone** (not `Z`).
6. **Empty collections are `[]` or `{}` not omitted** (keeps schema stable).
7. **Manifest excludes `exported_at`** from any round-trip equality
   check (it's metadata, not content).

A round-trip is: `import → export` should produce byte-identical files
to the original `.loom/` (modulo the manifest's `exported_at` field).

## Conflict-resolution policy (LOCKED, per user)

`loom import` policy on conflicts (local store has data not in
`.loom/`):

* **Default (no flag):** error and refuse to import. Print the
  divergence summary: how many entities exist locally that are not
  in the export, and vice versa. User explicitly opts in.
* **`--force`:** drop local-only entities; trust the export
  completely. Equivalent to "git reset" semantics.
* **`--merge`:** keep local-only entities; for same-id conflicts,
  repo wins (export overwrites local). Approximates "git pull —
  prefer remote, keep our untracked."

No three-way merge in v1 (would require tracking the previous
imported state per entity, complexity not worth it for v1).

## Embedding rebuild on import (LOCKED, per user)

After `loom import` materializes the rows, regenerate embeddings via
the configured provider:

* Show progress per kind: "Embedding requirements [25/75]…"
* Skip-on-existing: rows that already had an embedding in the local
  store (e.g. after `--merge`) and whose text is unchanged retain
  their existing vectors.
* `--skip-embeddings` flag: skip the regen pass. Search and drift
  detection won't work until `loom rebuild-embeddings` (provided by
  M24.4) is run.

Expected timing on Ollama at ~1s/req: a 75-req store rebuilds in
~75s. A 300-req store ~5min. Worth surfacing in the UX.

## Trigger (LOCKED, per user)

Manual `loom export` only. Not auto-coupled to `loom sync` or any
PostToolUse hook. The user runs `loom export` when they're ready to
commit a snapshot.

## Sub-milestone status

| sub | status |
|---|---|
| M24.0 — format spec (this doc) | ✅ complete |
| M24.1 — `loom export` + writers | ⏳ next |
| M24.2 — `loom import` + merge | pending |
| M24.3 — round-trip integrity test | pending |
| M24.4 — auto-rebuild embeddings | pending |
| M24.5 — docs + smoke on loom-self | pending |
