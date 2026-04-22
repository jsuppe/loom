# TASK-gaps-1

Implement a new function `gaps` in `src/services.py`:

```python
def gaps(store, types=None, limit=None) -> list[dict]:
    """Surface outstanding gaps in a Loom project."""
```

## Requirements

Each returned dict has the uniform shape:

```
{
  "type": str,             # one of: missing_criteria, missing_elaboration, orphan_impl
  "entity_id": str,        # REQ-xxx or IMPL-xxx
  "description": str,      # short human-readable
  "blocks": list[str],     # entity_ids this gap blocks (may be empty list)
  "suggested_action": str  # a single runnable command, e.g., "loom refine REQ-abc"
}
```

Implement these three gap types only:

- **`missing_criteria`** — active (non-superseded) requirement with empty `acceptance_criteria` (where empty means `[]` or the `["TBD"]` sentinel ChromaDB uses for unset list metadata).
- **`missing_elaboration`** — active requirement with empty `elaboration`.
- **`orphan_impl`** — implementation whose every `satisfies[*].req_id` either doesn't exist in the store or is superseded.

## Sort order

Sort by this priority (higher priority first), ties by `entity_id` ascending:

```
priority 3: missing_criteria
priority 4: missing_spec              # reserve slot, not implemented this task
priority 5: missing_elaboration
priority 6: orphan_impl
```

## Parameters

- `store: LoomStore` — required
- `types: list[str] | None` — if provided, only return gaps whose `type` is in the list
- `limit: int | None` — if provided, cap the returned list at `limit` entries (after sorting)

## Superseded reqs

Do not emit `missing_criteria` or `missing_elaboration` gaps for superseded requirements. They can still appear in `orphan_impl` detection (an impl pointing at a superseded req is orphan-adjacent).

## Testing

Add unit tests at `tests/test_services.py::TestGaps` covering:

- Each of the three gap types surfacing correctly
- The uniform shape (every gap has all five fields)
- Ordering by priority
- `types` filter
- `limit` cap
- Superseded reqs excluded from `missing_criteria` / `missing_elaboration`

## Scope constraints

- Modify only `src/services.py` and `tests/test_services.py`. Do not touch `scripts/loom`, the MCP server, or any other file.
- Do not implement `drift` or `unresolved_conflict` — those are later tasks.
- Do not change existing function signatures or exported API.

## How you're graded

Success = the grading test at `experiments/gaps/test_gaps_task1.py` passes.

Run it in your worktree:

```
python -m pytest experiments/gaps/test_gaps_task1.py -v
```

Additionally, your own tests at `tests/test_services.py::TestGaps` should pass:

```
python -m pytest tests/test_services.py::TestGaps -v
```

## Stop tokens

- If the task is too large or mixes concerns that should be split, reply with `TASK_REJECT: <one-line reason>` and stop. Do not attempt partial implementation.
- If you need information that isn't in the repo or the provided context, reply with `NEED_CONTEXT: <what you need>` and stop.
- When complete and the grading test passes, reply with `DONE: <one-line summary>` and stop.
