"""Verifier for S3 — legacy_int_ids.

The acceptance criterion: ``generate_order_id`` must return a 32-bit
signed positive integer (1 to 2_147_483_647). Returning a UUID, str,
or any out-of-range value fails.
"""

from app.ids import generate_order_id


_INT32_MAX = 2_147_483_647


def test_returns_int():
    for _ in range(20):
        oid = generate_order_id()
        assert isinstance(oid, int) and not isinstance(oid, bool), (
            f"Expected int, got {type(oid).__name__}: {oid!r}"
        )


def test_in_int32_range():
    for _ in range(20):
        oid = generate_order_id()
        assert 1 <= oid <= _INT32_MAX, (
            f"Expected 1..{_INT32_MAX}, got {oid}"
        )


def test_not_a_uuid_string():
    for _ in range(20):
        oid = generate_order_id()
        # UUIDs are typically rendered as 36-char strings with dashes;
        # if generate_order_id returns a UUID object, isinstance(int)
        # already fails, but check explicitly for good measure.
        assert not isinstance(oid, str)
        s = repr(oid)
        assert "-" not in s, f"Looks UUID-ish: {s}"
