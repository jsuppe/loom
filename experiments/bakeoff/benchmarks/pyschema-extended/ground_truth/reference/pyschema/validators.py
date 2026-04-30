"""Constraint validators applied by Field.validate.

Each validator is a frozen dataclass with a ``check(value)`` method
that raises :class:`ValidationError` on failure. Field types own a
list of validators applied in declaration order.
"""

from __future__ import annotations

import re
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
        object.__setattr__(self, "options", tuple(options))

    def check(self, value: object) -> None:
        if value not in self.options:
            raise ValidationError(
                f"value {value!r} not in allowed options {self.options}"
            )


@dataclass(frozen=True)
class NonEmpty:
    """Reject empty strings (length 0). Useful as a non-blank guard."""

    def check(self, value: str) -> None:
        if len(value) == 0:
            raise ValidationError("value is empty")


@dataclass(frozen=True)
class Pattern:
    """Validate a string matches a regex pattern."""

    pattern: str

    def check(self, value: str) -> None:
        if not re.match(self.pattern, value):
            raise ValidationError(f"{value!r} does not match {self.pattern!r}")
