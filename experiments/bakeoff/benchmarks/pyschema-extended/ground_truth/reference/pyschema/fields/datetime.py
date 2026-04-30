"""Date / datetime field types — DateField, DateTimeField."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from ..coercion import coerce_date
from ..errors import ValidationError
from .base import Field


@dataclass
class DateField(Field):
    min_date: Optional[date] = None
    max_date: Optional[date] = None

    def coerce(self, value: object) -> date:
        return coerce_date(value)

    def validate(self, value: object) -> Any:
        result = super().validate(value)
        if result is None:
            return result
        if self.min_date is not None and result < self.min_date:
            raise ValidationError(f"date {result} below min {self.min_date}")
        if self.max_date is not None and result > self.max_date:
            raise ValidationError(f"date {result} above max {self.max_date}")
        return result


@dataclass
class DateTimeField(Field):
    """Datetime parsed from ISO strings or accepted as datetime instances."""

    def coerce(self, value: object) -> datetime:
        from ..errors import CoercionError

        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError as exc:
                raise CoercionError(
                    f"cannot coerce {value!r} to datetime"
                ) from exc
        raise CoercionError(
            f"cannot coerce {type(value).__name__} to datetime"
        )
