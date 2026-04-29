"""Schema — declarative grouping of Fields with validate/parse semantics."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .errors import SchemaDefinitionError, ValidationError
from .field import Field


class Schema:
    """A declarative collection of named Fields.

    Subclass and declare class-level ``Field`` attributes:

        class UserSchema(Schema):
            name = StrField(min_length=1)
            age = IntField(min_value=0)
            email = EmailField()

    Then call ``UserSchema().validate({...})`` to coerce + validate
    a dict-like input, returning a dict of cleaned values. Missing
    optional fields are filled with their default.
    """

    def __init__(self) -> None:
        self._fields: Dict[str, Field] = {}
        for name in dir(type(self)):
            if name.startswith("_"):
                continue
            attr = getattr(type(self), name, None)
            if isinstance(attr, Field):
                self._fields[name] = attr
        if not self._fields:
            raise SchemaDefinitionError(
                f"{type(self).__name__} declares no fields"
            )

    @property
    def fields(self) -> Dict[str, Field]:
        return dict(self._fields)

    def validate(self, data: Mapping[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for name, field in self._fields.items():
            try:
                out[name] = field.validate(data.get(name))
            except ValidationError as exc:
                if not exc.field:
                    exc.field = name
                raise
        return out
