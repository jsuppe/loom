"""types/inventory.py — Stock level + reservation token.

`StockLevel` tracks `on_hand` and `reserved` for a single sku.
`available == on_hand - reserved`. `ReservationToken` ties a stock
hold to an order_id; `committed` flips when the reservation is
applied to on_hand at ship time.
"""

from dataclasses import dataclass


@dataclass
class StockLevel:
    sku: str
    on_hand: int = 0
    reserved: int = 0

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


@dataclass
class ReservationToken:
    token_id: str
    order_id: str
    sku: str
    quantity: int
    committed: bool = False
    released: bool = False

    @property
    def is_open(self) -> bool:
        return not self.committed and not self.released
