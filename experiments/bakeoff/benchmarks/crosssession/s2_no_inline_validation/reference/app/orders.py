"""Order placement — validation lives in the commit path, not at function entry."""


def _commit(order: dict) -> dict:
    """Persist + atomically validate.

    Production code wraps this in a DB transaction so validation
    failure rolls back. For the benchmark we just check + return.
    """
    if not order.get("items"):
        raise ValueError("items required")
    if not isinstance(order.get("customer_id"), str):
        raise ValueError("customer_id must be a string")
    for item in order["items"]:
        if item.get("quantity", 0) <= 0:
            raise ValueError(f"quantity must be positive: {item}")
    return order


def place_order(items, customer_id):
    """Place an order. No function-level validation — _commit handles it."""
    order = {"items": items, "customer_id": customer_id}
    return _commit(order)
