"""Field base class — every field type inherits from this."""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, List

from ..errors import ValidationError


@dataclass
class Field:
    """Base class for all field types.

    Subclasses set the coercion strategy by overriding ``coerce()``,
    and may register additional validators in ``__post_init__``.
    Construction order: ``coerce`` → run validators → return value.
    """

    required: bool = True
    default: Any = None
    validators: List[Any] = dc_field(default_factory=list)

    def coerce(self, value: object) -> Any:
        """Override in subclasses to convert ``value`` to the target type."""
        raise NotImplementedError

    def validate(self, value: object) -> Any:
        """Coerce + run validators. Returns the cleaned value, or
        ``self.default`` when ``value is None`` and the field is optional."""
        if value is None:
            if self.required:
                raise ValidationError("value is required")
            return self.default
        coerced = self.coerce(value)
        for v in self.validators:
            v.check(coerced)
        return coerced
