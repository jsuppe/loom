"""services/order_service.py — Order placement + lifecycle.

Coordinates customer + inventory services. On `place`, validates
customer exists, products exist, then reserves stock for each item.
On reservation failure mid-loop, releases everything reserved so
far (atomic-ish across the call). On `ship`, commits all open
reservations. On `cancel` (only valid pre-ship), releases them.
"""

from datetime import datetime
from typing import List

from ..errors import (
    InvalidTransitionError,
    NotFoundError,
    ValidationError,
)
from ..persistence import Store
from ..types.orders import Item, Order, OrderStatus, Transition
from .customer_service import CustomerService
from .inventory_service import InventoryService


class OrderService:
    def __init__(
        self,
        store: Store,
        customers: CustomerService,
        inventory: InventoryService,
    ) -> None:
        self.store = store
        self.customers = customers
        self.inventory = inventory
        self._order_seq = 0

    def place(self, *, customer_id: str, lines: List[dict]) -> Order:
        """`lines` is a list of dicts with keys 'sku' and 'quantity'."""
        self.customers.get(customer_id)
        if not lines:
            raise ValidationError("order must have at least one line")
        for line in lines:
            self.inventory.get_product(line["sku"])

        self._order_seq += 1
        order_id = f"ord-{self._order_seq:06d}"
        reserved_tokens: List[str] = []
        items: List[Item] = []
        try:
            for line in lines:
                product = self.inventory.get_product(line["sku"])
                token = self.inventory.reserve(
                    order_id=order_id,
                    sku=line["sku"],
                    quantity=line["quantity"],
                )
                reserved_tokens.append(token.token_id)
                items.append(
                    Item(
                        sku=line["sku"],
                        quantity=line["quantity"],
                        unit_price=product.price,
                    )
                )
        except Exception:
            for tid in reserved_tokens:
                self.inventory.release(tid)
            raise

        order = Order(
            id=order_id,
            customer_id=customer_id,
            items=items,
            reservation_tokens=reserved_tokens,
        )
        order.history.append(
            Transition(
                from_status=None,
                to_status=OrderStatus.NEW,
                timestamp=datetime.now(),
            )
        )
        self.store.orders[order_id] = order
        return order

    def get(self, order_id: str) -> Order:
        order = self.store.orders.get(order_id)
        if order is None:
            raise NotFoundError(f"order not found: {order_id}")
        return order

    def _transition(self, order: Order, next_status: OrderStatus) -> None:
        order.history.append(
            Transition(
                from_status=order.status,
                to_status=next_status,
                timestamp=datetime.now(),
            )
        )
        order.status = next_status

    def mark_paid(self, order_id: str) -> None:
        order = self.get(order_id)
        if order.status != OrderStatus.NEW:
            raise InvalidTransitionError(
                f"cannot mark paid from {order.status}"
            )
        self._transition(order, OrderStatus.PAID)

    def ship(self, order_id: str) -> None:
        order = self.get(order_id)
        if order.status != OrderStatus.PAID:
            raise InvalidTransitionError(f"cannot ship from {order.status}")
        for tid in order.reservation_tokens:
            self.inventory.commit(tid)
        self._transition(order, OrderStatus.SHIPPED)

    def deliver(self, order_id: str) -> None:
        order = self.get(order_id)
        if order.status != OrderStatus.SHIPPED:
            raise InvalidTransitionError(f"cannot deliver from {order.status}")
        self._transition(order, OrderStatus.DELIVERED)

    def cancel(self, order_id: str) -> None:
        order = self.get(order_id)
        if order.status in (
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
        ):
            raise InvalidTransitionError(f"cannot cancel from {order.status}")
        for tid in order.reservation_tokens:
            token = self.store.reservations.get(tid)
            if token is not None and token.is_open:
                self.inventory.release(tid)
        self._transition(order, OrderStatus.CANCELLED)
