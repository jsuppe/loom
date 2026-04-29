"""Domain errors for pyschema."""


class SchemaError(Exception):
    """Base exception type for pyschema errors."""


class ValidationError(SchemaError):
    """Raised when a field value fails validation.

    Holds the field name (set by ``Schema.validate`` when raised in a
    schema context) so callers can render structured error reports.
    """

    def __init__(self, message: str, field: str = ""):
        super().__init__(message)
        self.message = message
        self.field = field

    def __str__(self) -> str:
        return f"{self.field}: {self.message}" if self.field else self.message


class CoercionError(SchemaError):
    """Raised when a value cannot be coerced to the field's target type."""


class SchemaDefinitionError(SchemaError):
    """Raised when a Schema is constructed with an invalid declaration."""
