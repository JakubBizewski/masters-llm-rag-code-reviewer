"""Domain exceptions for ACR system."""


class DomainException(Exception):
    """Base exception for domain layer."""
    pass


class EntityNotFoundError(DomainException):
    """Entity not found in repository."""
    pass


class ValidationError(DomainException):
    """Validation error in domain logic."""
    pass


class InvalidConfigurationError(DomainException):
    """Invalid configuration error."""
    pass
