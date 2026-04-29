"""Constraint validators applied by Field.validate.

Each validator is a small callable-style class with a ``check(value)``
method that raises :class:`ValidationError` on failure. Field types
own a list of validators applied in declaration order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .errors import ValidationError


@dataclass(frozen=True)
class MinLength:
    n: int

    def check(self, value: str) -> None:
        if len(value) < self.n:
            raise ValidationError(f"length {len(value)} below minimum {self.n}")


@dataclass(frozen=True)
class MaxLength:
    n: int

    def check(self, value: str) -> None:
        if len(value) > self.n:
            raise ValidationError(f"length {len(value)} above maximum {self.n}")


@dataclass(frozen=True)
class MinValue:
    n: int | float

    def check(self, value: int | float) -> None:
        if value < self.n:
            raise ValidationError(f"value {value} below minimum {self.n}")


@dataclass(frozen=True)
class MaxValue:
    n: int | float

    def check(self, value: int | float) -> None:
        if value > self.n:
            raise ValidationError(f"value {value} above maximum {self.n}")


@dataclass(frozen=True)
class Choice:
    options: tuple[object, ...]

    def __init__(self, options: Sequence[object]):
        # Cast to tuple so the dataclass remains hashable/frozen.
        object.__setattr__(self, "options", tuple(options))

    def check(self, value: object) -> None:
        if value not in self.options:
            raise ValidationError(
                f"value {value!r} not in allowed options {self.options}"
            )
