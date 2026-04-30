"""Primitive field types — IntField, StrField, BoolField."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..coercion import coerce_bool, coerce_int, coerce_str
from ..validators import MaxLength, MaxValue, MinLength, MinValue
from .base import Field


@dataclass
class IntField(Field):
    min_value: Optional[int] = None
    max_value: Optional[int] = None

    def __post_init__(self) -> None:
        if self.min_value is not None:
            self.validators.append(MinValue(self.min_value))
        if self.max_value is not None:
            self.validators.append(MaxValue(self.max_value))

    def coerce(self, value: object) -> int:
        return coerce_int(value)


@dataclass
class StrField(Field):
    min_length: Optional[int] = None
    max_length: Optional[int] = None

    def __post_init__(self) -> None:
        if self.min_length is not None:
            self.validators.append(MinLength(self.min_length))
        if self.max_length is not None:
            self.validators.append(MaxLength(self.max_length))

    def coerce(self, value: object) -> str:
        return coerce_str(value)


@dataclass
class BoolField(Field):
    def coerce(self, value: object) -> bool:
        return coerce_bool(value)
