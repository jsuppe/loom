"""Order ID generation — must stay 32-bit signed positive integer."""

import random


_INT32_MAX = 2_147_483_647


def generate_order_id() -> int:
    """Return a fresh 32-bit signed positive integer ID.

    Range: 1 to 2_147_483_647 inclusive. Uniqueness within a single
    process is not enforced here (the production database has a
    UNIQUE constraint that surfaces collisions).
    """
    return random.randint(1, _INT32_MAX)
