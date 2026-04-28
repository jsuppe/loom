"""services/inventory_service.py — Product catalog + stock + reservations.

Reservation lifecycle (one token per (order, sku) line):
  reserve()  -> opens token, increments StockLevel.reserved
  commit()   -> closes token, decrements on_hand AND reserved
  release()  -> closes token, decrements reserved (returns to available)
A token can be committed XOR released, never both, and never twice.
"""

from ..errors import (
    ConflictError,
    InsufficientStockError,
    NotFoundError,
    ReservationError,
    ValidationError,
)
from ..persistence import Store
from ..types.inventory import ReservationToken, StockLevel
from ..types.products import Product


class InventoryService:
    def __init__(self, store: Store) -> None:
        self.store = store
        self._token_seq = 0

    def register_product(self, *, sku: str, name: str, price: float) -> Product:
        if sku in self.store.products:
            raise ConflictError(f"product with sku {sku} already exists")
        product = Product(sku=sku, name=name, price=price)
        self.store.products[sku] = product
        self.store.stock[sku] = StockLevel(sku=sku)
        return product

    def get_product(self, sku: str) -> Product:
        product = self.store.products.get(sku)
        if product is None:
            raise NotFoundError(f"product not found: {sku}")
        return product

    def stock_of(self, sku: str) -> StockLevel:
        stock = self.store.stock.get(sku)
        if stock is None:
            raise NotFoundError(f"no stock record for sku {sku}")
        return stock

    def add_stock(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValidationError("add_stock qty must be > 0")
        stock = self.stock_of(sku)
        stock.on_hand += qty

    def reserve(self, *, order_id: str, sku: str, quantity: int) -> ReservationToken:
        if quantity <= 0:
            raise ValidationError("reserve quantity must be > 0")
        stock = self.stock_of(sku)
        if stock.available < quantity:
            raise InsufficientStockError(
                f"insufficient stock for {sku}: have {stock.available}, need {quantity}"
            )
        stock.reserved += quantity
        self._token_seq += 1
        token_id = f"rsv-{self._token_seq:06d}"
        token = ReservationToken(
            token_id=token_id,
            order_id=order_id,
            sku=sku,
            quantity=quantity,
        )
        self.store.reservations[token_id] = token
        return token

    def commit(self, token_id: str) -> None:
        token = self.store.reservations.get(token_id)
        if token is None:
            raise NotFoundError(f"reservation not found: {token_id}")
        if not token.is_open:
            raise ReservationError(f"reservation {token_id} already closed")
        stock = self.stock_of(token.sku)
        stock.on_hand -= token.quantity
        stock.reserved -= token.quantity
        token.committed = True

    def release(self, token_id: str) -> None:
        token = self.store.reservations.get(token_id)
        if token is None:
            raise NotFoundError(f"reservation not found: {token_id}")
        if not token.is_open:
            raise ReservationError(f"reservation {token_id} already closed")
        stock = self.stock_of(token.sku)
        stock.reserved -= token.quantity
        token.released = True
