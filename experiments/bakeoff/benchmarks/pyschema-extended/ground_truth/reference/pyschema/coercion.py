"""Type coercion helpers used by Field types."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .errors import CoercionError


def coerce_int(value: object) -> int:
    if isinstance(value, bool):
        raise CoercionError(f"refusing to coerce bool {value!r} to int")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise CoercionError(f"cannot coerce {value!r} to int") from exc
    raise CoercionError(f"cannot coerce {type(value).__name__} to int")


def coerce_str(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    raise CoercionError(f"cannot coerce {type(value).__name__} to str")


def coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise CoercionError(f"cannot coerce {value!r} to bool")
    raise CoercionError(f"cannot coerce {type(value).__name__} to bool")


def coerce_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, str)) and not isinstance(value, bool):
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise CoercionError(f"cannot coerce {value!r} to Decimal") from exc
    raise CoercionError(f"cannot coerce {type(value).__name__} to Decimal")


def coerce_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise CoercionError(f"cannot coerce {value!r} to date") from exc
    raise CoercionError(f"cannot coerce {type(value).__name__} to date")
