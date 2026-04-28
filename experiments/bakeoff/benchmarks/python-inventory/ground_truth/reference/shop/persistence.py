"""persistence.py — In-memory store shared by all services.

Holds dicts keyed by id/sku/order_id/token_id. `snapshot()` returns a
deep-enough copy for round-trip restore in tests. `restore()`
replaces all current state with a snapshot.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict

from .types.customers import Customer
from .types.inventory import ReservationToken, StockLevel
from .types.orders import Order
from .types.products import Product


@dataclass
class Snapshot:
    customers: Dict[str, Customer] = field(default_factory=dict)
    products: Dict[str, Product] = field(default_factory=dict)
    stock: Dict[str, StockLevel] = field(default_factory=dict)
    orders: Dict[str, Order] = field(default_factory=dict)
    reservations: Dict[str, ReservationToken] = field(default_factory=dict)


@dataclass
class Store:
    customers: Dict[str, Customer] = field(default_factory=dict)
    products: Dict[str, Product] = field(default_factory=dict)
    stock: Dict[str, StockLevel] = field(default_factory=dict)
    orders: Dict[str, Order] = field(default_factory=dict)
    reservations: Dict[str, ReservationToken] = field(default_factory=dict)

    def snapshot(self) -> Snapshot:
        return Snapshot(
            customers=dict(self.customers),
            products=dict(self.products),
            stock={k: deepcopy(v) for k, v in self.stock.items()},
            orders={k: deepcopy(v) for k, v in self.orders.items()},
            reservations={k: deepcopy(v) for k, v in self.reservations.items()},
        )

    def restore(self, snap: Snapshot) -> None:
        self.customers.clear()
        self.customers.update(snap.customers)
        self.products.clear()
        self.products.update(snap.products)
        self.stock.clear()
        self.stock.update(snap.stock)
        self.orders.clear()
        self.orders.update(snap.orders)
        self.reservations.clear()
        self.reservations.update(snap.reservations)
