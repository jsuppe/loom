"""Specialized string field types — EmailField, URLField, UUIDField."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..errors import ValidationError
from .primitives import StrField


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^https?://[^\s/]+(/.*)?$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


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


@dataclass
class URLField(StrField):
    """Specialization of StrField — requires an http(s) URL shape."""

    def validate(self, value: object) -> Any:
        result = super().validate(value)
        if result is None:
            return result
        if not _URL_RE.match(result):
            raise ValidationError(f"{result!r} is not a valid URL")
        return result


@dataclass
class UUIDField(StrField):
    """Specialization of StrField — requires a UUID shape (with dashes)."""

    def validate(self, value: object) -> Any:
        result = super().validate(value)
        if result is None:
            return result
        if not _UUID_RE.match(result):
            raise ValidationError(f"{result!r} is not a valid UUID")
        return result
