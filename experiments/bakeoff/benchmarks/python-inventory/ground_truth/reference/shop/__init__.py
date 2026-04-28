"""shop — multi-service domain (customers + products + inventory + orders).

Pre-written by the Phase C python-inventory driver; not a qwen task.
This barrel re-exports the public API so tests can import everything
from `shop`.
"""

from .errors import (
    ConflictError,
    DomainError,
    InsufficientStockError,
    InvalidTransitionError,
    NotFoundError,
    ReservationError,
    ValidationError,
)
from .persistence import Snapshot, Store
from .services.customer_service import CustomerService
from .services.inventory_service import InventoryService
from .services.order_service import OrderService
from .types.customers import Address, Customer
from .types.inventory import ReservationToken, StockLevel
from .types.orders import Item, Order, OrderStatus, Transition
from .types.products import Product

__all__ = [
    "Address",
    "ConflictError",
    "Customer",
    "CustomerService",
    "DomainError",
    "InsufficientStockError",
    "InvalidTransitionError",
    "InventoryService",
    "Item",
    "NotFoundError",
    "Order",
    "OrderService",
    "OrderStatus",
    "Product",
    "ReservationError",
    "ReservationToken",
    "Snapshot",
    "StockLevel",
    "Store",
    "Transition",
    "ValidationError",
]
