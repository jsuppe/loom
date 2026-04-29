"""Type coercion helpers used by Field types.

Each ``coerce_<type>`` accepts an arbitrary input and returns the
target type, or raises :class:`CoercionError` if the value cannot be
coerced. These are intentionally narrow — pyschema does not try to
be a general type-conversion library.
"""

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
