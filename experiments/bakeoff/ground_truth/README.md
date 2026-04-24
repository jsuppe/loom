# TaskQueue — ground truth

This is the "product spec" the Product Owner (Agent A) knows. Agent B
(Engineer) sees requirements one at a time as A reveals them.

**Neither agent ever sees the test file at `tests/test_task_queue.py`.**
Only the driver runs the tests; it reports pass/total + per-test delta
to A, who then decides what to say to B.

## Goal

A small in-process priority queue for named tasks.

## Requirements

### REQ-1 — add
`queue.add(name, priority=0)` inserts a task.

- `name` is a non-empty string. Empty or non-string names raise
  `ValueError`.
- `priority` defaults to `0`. Can be any int, positive or negative.
- Returns `None`.

### REQ-2 — priority order on pop
`queue.pop()` removes and returns the next task as a
`(name, priority)` tuple.

- Higher `priority` comes first.
- Within the same priority, FIFO (first-in-first-out) by insertion
  order.
- Example:
    ```
    q.add('a', 0); q.add('b', 1); q.add('c', 0); q.add('d', 1)
    q.pop() -> ('b', 1)   # priority 1 came in first
    q.pop() -> ('d', 1)   # priority 1 came in second
    q.pop() -> ('a', 0)   # priority 0 came in first
    q.pop() -> ('c', 0)
    ```

### REQ-3 — peek
`queue.peek()` returns the same task `pop()` would return, without
removing it.

- On an empty queue, returns `None`.
- Calling peek repeatedly must never change the queue state.

### REQ-4 — cancel
`queue.cancel(name)` removes the FIRST task (by insertion order) whose
name equals `name`.

- Returns `True` if a task was removed.
- Returns `False` if no task with that name exists.
- Does not affect the priority ordering of remaining tasks.

### REQ-5 — filter
`queue.filter(predicate)` returns a `list` of tasks (as
`(name, priority)` tuples) for which `predicate(task)` is truthy.

- `predicate` is a callable taking a `(name, priority)` tuple.
- Returns the tasks in the same order `pop()` would return them.
- Does NOT modify the queue.

### REQ-6 — empty semantics
- `pop()` on an empty queue raises `IndexError`.
- `len(queue)` returns the count of tasks.
- A brand-new `TaskQueue()` has `len(q) == 0`.

## Non-requirements

To keep scope tight, these are explicitly out-of-scope:
- Thread safety.
- Serialization.
- Priority updates after insert.
- Bulk operations (`extend`, `merge`).
- Iteration (`__iter__`).

Agent A should not introduce these.

## File layout (what B produces)

```
task_queue.py     # the implementation B writes
```

Tests live at `tests/test_task_queue.py` — fixed, ground-truth, hidden
from B.
