"""types/customers.py — Customer + Address value types.

`id`, `name`, and `email` are required. `email` must contain '@'.
`addresses` is a mutable list so customer_service can append.
"""

from dataclasses import dataclass, field
from typing import List

from ..errors import ValidationError


@dataclass(frozen=True)
class Address:
    street: str
    city: str
    postal_code: str


@dataclass
class Customer:
    id: str
    name: str
    email: str
    addresses: List[Address] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValidationError("customer id must be non-empty")
        if not self.name:
            raise ValidationError("customer name must be non-empty")
        if "@" not in self.email:
            raise ValidationError("customer email must contain @")
