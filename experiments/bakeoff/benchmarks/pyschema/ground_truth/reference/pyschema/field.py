"""Field types — the building blocks of a Schema.

Each Field encapsulates: a target type, a coercion strategy, a list
of validators, and an optional default. The base class wires these
together; concrete subclasses pick the coercion + default validator
set appropriate to their target type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any, List, Optional

from .coercion import coerce_bool, coerce_int, coerce_str
from .errors import ValidationError
from .validators import MaxLength, MinLength


@dataclass
class Field:
    """Base class for all field types.

    Subclasses set ``coercer`` (a callable) at class scope and may
    provide additional default validators in ``__post_init__``.
    Construction order: coerce → run validators → return value.
    """

    required: bool = True
    default: Any = None
    validators: List[Any] = dc_field(default_factory=list)

    def coerce(self, value: object) -> Any:
        raise NotImplementedError

    def validate(self, value: object) -> Any:
        if value is None:
            if self.required:
                raise ValidationError("value is required")
            return self.default
        coerced = self.coerce(value)
        for v in self.validators:
            v.check(coerced)
        return coerced


@dataclass
class IntField(Field):
    min_value: Optional[int] = None
    max_value: Optional[int] = None

    def __post_init__(self) -> None:
        from .validators import MaxValue, MinValue

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


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class EmailField(StrField):
    """Specialization of StrField — requires a basic local@domain.tld shape."""

    def validate(self, value: object) -> Any:
        result = super().validate(value)
        if result is None:
            return result
        if not _EMAIL_RE.match(result):
            raise ValidationError(f"{result!r} is not a valid email address")
        return result
