// errors.hpp — domain error hierarchy.
//
// All errors derive from DomainError. Tests rely on the *exact* class
// names listed here; renaming or merging breaks the contract.
#pragma once

#include <stdexcept>
#include <string>

class DomainError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ValidationError : public DomainError {
public:
    using DomainError::DomainError;
};

class NotFoundError : public DomainError {
public:
    using DomainError::DomainError;
};

class ConflictError : public DomainError {
public:
    using DomainError::DomainError;
};

class InsufficientStockError : public DomainError {
public:
    using DomainError::DomainError;
};

class InvalidTransitionError : public DomainError {
public:
    using DomainError::DomainError;
};

class ReservationError : public DomainError {
public:
    using DomainError::DomainError;
};
