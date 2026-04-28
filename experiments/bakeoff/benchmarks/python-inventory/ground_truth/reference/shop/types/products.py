"""types/products.py — Product catalog entry.

Immutable. `sku` is the unique product identifier; `price` must be > 0.
"""

from dataclasses import dataclass

from ..errors import ValidationError


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price: float

    def __post_init__(self) -> None:
        if not self.sku:
            raise ValidationError("product sku must be non-empty")
        if not self.name:
            raise ValidationError("product name must be non-empty")
        if self.price <= 0:
            raise ValidationError("product price must be > 0")
