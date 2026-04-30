"""SchemaRegistry — register and look up Schema subclasses by name."""

from __future__ import annotations

from typing import Dict, Type

from .errors import SchemaNotRegisteredError
from .schema import Schema


class SchemaRegistry:
    """Process-local registry mapping name → Schema subclass.

    Use to allow late binding (e.g. validating "user" payloads where
    the caller supplies the schema name as a string from config).
    """

    def __init__(self) -> None:
        self._schemas: Dict[str, Type[Schema]] = {}

    def register(self, name: str, schema_cls: Type[Schema]) -> None:
        """Register a Schema subclass under ``name``."""
        if not issubclass(schema_cls, Schema):
            raise TypeError(
                f"{schema_cls!r} is not a Schema subclass"
            )
        self._schemas[name] = schema_cls

    def get(self, name: str) -> Type[Schema]:
        """Look up a registered Schema. Raises if not registered."""
        if name not in self._schemas:
            raise SchemaNotRegisteredError(
                f"no schema registered under name {name!r}"
            )
        return self._schemas[name]

    def names(self) -> list[str]:
        return sorted(self._schemas)
