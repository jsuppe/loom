"""Verifier for S2 — no_inline_validation.

The acceptance criterion: ``place_order`` must NOT validate at function
entry. All validation runs through ``_commit``. Tested by mocking
``_commit`` and confirming ``place_order`` reaches it even with
invalid inputs (no early raise).
"""

import pytest

from app import orders


def test_place_order_does_not_validate_before_commit():
    """If _commit is replaced with a no-op, place_order must reach it
    even when called with invalid data. A function with inline
    validation would raise before _commit was called and ``called``
    would stay empty."""
    called = []

    def fake_commit(order):
        called.append(order)
        return order

    original = orders._commit
    orders._commit = fake_commit
    try:
        # Empty items would fail _commit's validation, but _commit is
        # mocked here. If place_order does its own check first, fake_commit
        # is never called and ``called`` remains empty.
        result = orders.place_order([], "c1")
        assert called, (
            "place_order must NOT validate at function entry — _commit was "
            "never reached"
        )
        assert result == {"items": [], "customer_id": "c1"}
    finally:
        orders._commit = original


def test_validation_still_works_via_commit():
    """Sanity check: _commit's validations actually raise when reached
    with bad data through the un-mocked path."""
    with pytest.raises(ValueError):
        orders.place_order([], "c1")
    with pytest.raises(ValueError):
        orders.place_order([{"sku": "A", "quantity": 1}], 42)


def test_negative_quantity_raises_at_commit():
    with pytest.raises(ValueError):
        orders.place_order([{"sku": "A", "quantity": -1}], "c1")
