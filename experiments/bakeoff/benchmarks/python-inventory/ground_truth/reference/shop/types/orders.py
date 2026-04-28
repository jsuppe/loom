"""types/orders.py — Order + Item types and OrderStatus enum.

`Item` snapshots `unit_price` at order time so later product price
changes don't retroactively affect totals. `Order.total` is computed
from items, not stored. `Order.history` records every status change.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from ..errors import ValidationError


class OrderStatus(Enum):
    NEW = "new"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Item:
    sku: str
    quantity: int
    unit_price: float

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValidationError("item quantity must be > 0")
        if self.unit_price < 0:
            raise ValidationError("item unit_price must be >= 0")

    @property
    def line_total(self) -> float:
        return self.quantity * self.unit_price


@dataclass(frozen=True)
class Transition:
    from_status: Optional[OrderStatus]
    to_status: OrderStatus
    timestamp: datetime


@dataclass
class Order:
    id: str
    customer_id: str
    items: List[Item]
    status: OrderStatus = OrderStatus.NEW
    history: List[Transition] = field(default_factory=list)
    reservation_tokens: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValidationError("order id must be non-empty")
        if not self.customer_id:
            raise ValidationError("order customer_id must be non-empty")
        if not self.items:
            raise ValidationError("order must have at least one item")

    @property
    def total(self) -> float:
        return sum(it.line_total for it in self.items)
