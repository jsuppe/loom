# pubsub benchmark

A small in-memory pub/sub library — `Bus` registers Topics and
dispatches events to attached handlers. Used as the substrate for
the R2 refactor task (rename `Bus.subscribe` → `Bus.register_handler`).

## Public API (pre-refactor state)

```python
from pubsub import Bus, Topic, HandlerError, TopicNotFoundError

bus = Bus()

# Lazy topic creation — calling subscribe with an unknown topic registers it.
sub = bus.subscribe("orders", lambda event: print(f"got: {event}"))
bus.publish("orders", {"id": 1})
bus.unsubscribe(sub)
```

## Files (4 executor tasks + 1 pre-written barrel for greenfield)

```
pubsub/
├── __init__.py             (barrel — pre-written by harness in greenfield mode)
├── errors.py               [task 1]   PubSubError + 3 subclasses
├── topic.py                [task 2]   Topic value type
├── subscription.py         [task 3]   Subscription token
└── bus.py                  [task 4]   Bus — register_topic / subscribe / publish / unsubscribe
```

For the **D refactor smoke**, the executor receives the library
pre-written and must apply the R2 refactor described below.

## Domain model

### REQ-1: Errors (`errors.py`)

A small hierarchy:

- `PubSubError(Exception)` — base
- `TopicNotFoundError(PubSubError)` — raised by publish on unknown topic
- `SubscriptionClosedError(PubSubError)` — raised on operations on a closed Subscription
- `HandlerError(PubSubError)` — wraps original exception in `.cause` when a handler raises

### REQ-2: Topic (`topic.py`)

`@dataclass(frozen=True)` with a single field `name: str`. Hashable
so it can be used as a dict key. `__post_init__` validates that
`name` is a non-empty str.

### REQ-3: Subscription (`subscription.py`)

`@dataclass` with fields:
- `id: str` (e.g., `"sub-000001"`)
- `topic_name: str`
- `handler: Callable[[object], None]`
- `_closed: bool = False` (private, repr-suppressed)

Methods: `closed` property, `close()` method that sets `_closed=True`.

### REQ-4: Bus (`bus.py`)

Central class. Holds:
- `_topics: Dict[str, Topic]`
- `_subs: Dict[str, List[Subscription]]`
- `_next_id: int`

Public API (pre-refactor):
- `register_topic(name) -> Topic` — idempotent topic registration
- `topics() -> List[Topic]` — list all registered topics
- `subscribe(topic, handler) -> Subscription` — attach handler, returns token. Lazy-creates the topic if not registered. Topic arg can be `str` or `Topic`.
- `unsubscribe(sub: Subscription) -> None` — close the Subscription. Raises `SubscriptionClosedError` if already closed.
- `publish(topic, event) -> int` — dispatch to all active handlers. Returns delivery count. Raises `TopicNotFoundError` for unknown topics. Wraps handler exceptions in `HandlerError` (delivers to remaining handlers first).

## R2 refactor task (D smoke target)

**Rename `Bus.subscribe` to `Bus.register_handler`.** This is a
pure rename:
- The method's signature, behavior, and return type stay identical.
- The old name `subscribe` must NOT exist post-refactor (the
  acceptance test asserts `not hasattr(bus, "subscribe")`).
- All internal callers (none in the reference, but defensive) must
  use the new name.
- File scope: `pubsub/bus.py` only. The barrel and other files do
  not need changes.

The acceptance test suite is `tests/test_pubsub.py`. A correct
refactor brings the suite from 1/12 (only the topic-not-found test
passes pre-refactor, since it doesn't use the renamed method) to
12/12.
