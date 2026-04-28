"""errors.py — domain error hierarchy used by every other module.

All errors derive from DomainError. Tests rely on the *exact* class
names listed here; renaming or merging breaks the contract.
"""


class DomainError(Exception):
    """Root of the domain error hierarchy."""


class ValidationError(DomainError):
    """Input did not meet a precondition."""


class NotFoundError(DomainError):
    """Id/sku not in the store."""


class ConflictError(DomainError):
    """Duplicate id/sku."""


class InsufficientStockError(DomainError):
    """available < requested."""


class InvalidTransitionError(DomainError):
    """Status transition not allowed."""


class ReservationError(DomainError):
    """Operation on a closed reservation token."""
