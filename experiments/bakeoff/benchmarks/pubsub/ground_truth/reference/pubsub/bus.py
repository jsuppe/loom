"""Bus — the central pub/sub registry and dispatcher.

The Bus owns Topic registrations and handler lists. Calling code
uses :meth:`Bus.subscribe` to attach a handler to a topic and
:meth:`Bus.publish` to dispatch an event to all handlers attached
to a topic.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from .errors import HandlerError, SubscriptionClosedError, TopicNotFoundError
from .subscription import Subscription
from .topic import Topic


class Bus:
    """In-memory pub/sub registry + dispatcher.

    Topics are created on demand by ``register_topic`` or implicitly
    on the first ``subscribe`` call. ``publish(topic, event)``
    delivers the event to every active (non-closed) handler
    registered against that topic.

    Handlers that raise are wrapped in :class:`HandlerError` and
    re-raised after all other handlers have been invoked, so a
    single bad handler does not prevent dispatch to the others.
    """

    def __init__(self) -> None:
        self._topics: Dict[str, Topic] = {}
        self._subs: Dict[str, List[Subscription]] = {}
        self._next_id: int = 0

    def register_topic(self, name: str) -> Topic:
        """Idempotently create a Topic with ``name``."""
        if name not in self._topics:
            t = Topic(name=name)
            self._topics[name] = t
            self._subs.setdefault(name, [])
        return self._topics[name]

    def topics(self) -> List[Topic]:
        """All registered topics."""
        return list(self._topics.values())

    def subscribe(
        self,
        topic: str | Topic,
        handler: Callable[[object], None],
    ) -> Subscription:
        """Attach ``handler`` to ``topic``. Returns a Subscription token.

        The topic is created if it doesn't exist yet (lazy registration
        — callers don't need to call ``register_topic`` first).
        """
        name = topic.name if isinstance(topic, Topic) else topic
        self.register_topic(name)
        self._next_id += 1
        sub = Subscription(
            id=f"sub-{self._next_id:06d}",
            topic_name=name,
            handler=handler,
        )
        self._subs[name].append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        """Cancel a handler registration via its Subscription token."""
        if sub.closed:
            raise SubscriptionClosedError(
                f"Subscription {sub.id} is already closed"
            )
        sub.close()
        # Removal is lazy — close() flips the flag; dispatch skips closed.

    def publish(self, topic: str | Topic, event: object) -> int:
        """Dispatch ``event`` to all active handlers on ``topic``.

        Returns the number of handlers that received the event
        (excluding closed/unsubscribed ones). Raises
        :class:`TopicNotFoundError` if the topic was never registered.
        """
        name = topic.name if isinstance(topic, Topic) else topic
        if name not in self._subs:
            raise TopicNotFoundError(f"Topic {name!r} not registered")
        delivered = 0
        errors: list[Exception] = []
        for sub in self._subs[name]:
            if sub.closed:
                continue
            try:
                sub.handler(event)
                delivered += 1
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise HandlerError(
                f"{len(errors)} handler(s) raised on topic {name!r}",
                cause=errors[0],
            )
        return delivered
