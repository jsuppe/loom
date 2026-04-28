/// errors.dart — domain error hierarchy used by every other module.
///
/// All errors extend `DomainError`. Tests rely on the *exact* class
/// names listed here; renaming or merging breaks the contract.

class DomainError implements Exception {
  final String message;
  const DomainError(this.message);
  @override
  String toString() => '$runtimeType: $message';
}

class ValidationError extends DomainError {
  const ValidationError(super.message);
}

class NotFoundError extends DomainError {
  const NotFoundError(super.message);
}

class ConflictError extends DomainError {
  const ConflictError(super.message);
}

class InsufficientStockError extends DomainError {
  const InsufficientStockError(super.message);
}

class InvalidTransitionError extends DomainError {
  const InvalidTransitionError(super.message);
}

class ReservationError extends DomainError {
  const ReservationError(super.message);
}
