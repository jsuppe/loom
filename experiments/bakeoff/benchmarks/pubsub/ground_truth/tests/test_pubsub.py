"""Acceptance tests for R2 — rename Bus.subscribe → Bus.register_handler.

These tests use the POST-refactor method name (register_handler).
Against the pre-refactor library, every test fails with AttributeError
(Bus has no register_handler method). Against a correct refactor,
all tests pass.

Note: there is no separate "regression" suite for R2. A pure rename
removes the old method, so any test using the old name would fail
post-refactor by design. The functional behavior is exercised
through the renamed method here, so this single suite grades both
"did the rename happen?" (AttributeError vs not) and "does the lib
still work?" (handler dispatch produces expected events).
"""

import pytest

from pubsub.bus import Bus
from pubsub.topic import Topic
from pubsub.errors import (
    HandlerError,
    SubscriptionClosedError,
    TopicNotFoundError,
)


class TestBusRegisterHandler:
    def test_register_handler_returns_subscription(self):
        bus = Bus()
        sub = bus.register_handler("orders", lambda e: None)
        assert sub.topic_name == "orders"
        assert sub.id.startswith("sub-")

    def test_register_handler_with_topic_object(self):
        bus = Bus()
        t = Topic(name="items")
        sub = bus.register_handler(t, lambda e: None)
        assert sub.topic_name == "items"

    def test_register_handler_lazy_creates_topic(self):
        bus = Bus()
        bus.register_handler("new_topic", lambda e: None)
        assert any(t.name == "new_topic" for t in bus.topics())

    def test_register_handler_multiple_handlers_per_topic(self):
        bus = Bus()
        events = []
        bus.register_handler("orders", lambda e: events.append(("a", e)))
        bus.register_handler("orders", lambda e: events.append(("b", e)))
        bus.publish("orders", 1)
        assert ("a", 1) in events
        assert ("b", 1) in events


class TestPublish:
    def test_publish_delivers_to_handler(self):
        bus = Bus()
        seen = []
        bus.register_handler("orders", lambda e: seen.append(e))
        bus.publish("orders", {"id": 1})
        assert seen == [{"id": 1}]

    def test_publish_returns_delivery_count(self):
        bus = Bus()
        bus.register_handler("orders", lambda e: None)
        bus.register_handler("orders", lambda e: None)
        n = bus.publish("orders", "x")
        assert n == 2

    def test_publish_unknown_topic_raises(self):
        bus = Bus()
        with pytest.raises(TopicNotFoundError):
            bus.publish("ghost", "x")

    def test_publish_skips_closed_subscriptions(self):
        bus = Bus()
        seen = []
        sub = bus.register_handler("orders", lambda e: seen.append(e))
        bus.unsubscribe(sub)
        bus.publish("orders", 1)
        assert seen == []

    def test_handler_error_wrapped(self):
        bus = Bus()
        bus.register_handler("topic", lambda e: (_ for _ in ()).throw(ValueError("x")))
        with pytest.raises(HandlerError) as exc_info:
            bus.publish("topic", "evt")
        assert isinstance(exc_info.value.cause, ValueError)


class TestUnsubscribe:
    def test_unsubscribe_closes_subscription(self):
        bus = Bus()
        sub = bus.register_handler("topic", lambda e: None)
        assert not sub.closed
        bus.unsubscribe(sub)
        assert sub.closed

    def test_unsubscribe_twice_raises(self):
        bus = Bus()
        sub = bus.register_handler("topic", lambda e: None)
        bus.unsubscribe(sub)
        with pytest.raises(SubscriptionClosedError):
            bus.unsubscribe(sub)


class TestNoOldName:
    """The rename must remove the old name — tests below assert the
    pre-refactor surface is gone."""

    def test_old_subscribe_method_removed(self):
        bus = Bus()
        assert not hasattr(bus, "subscribe"), (
            "Pure rename: Bus.subscribe should not exist post-refactor "
            "(it has been renamed to register_handler)"
        )
