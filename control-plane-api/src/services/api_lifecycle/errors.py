"""Errors raised by the API lifecycle domain service."""


class ApiLifecycleError(Exception):
    """Base error for lifecycle operations."""


class ApiLifecycleValidationError(ApiLifecycleError):
    """Input or transition is invalid for the requested lifecycle operation."""


class ApiLifecycleSpecValidationError(ApiLifecycleValidationError):
    """OpenAPI contract validation failed."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class ApiLifecycleTransitionError(ApiLifecycleError):
    """Requested lifecycle transition is not allowed."""


class ApiLifecycleGatewayNotFoundError(ApiLifecycleError):
    """Requested gateway target does not exist or is not visible to the tenant."""


class ApiLifecycleGatewayAmbiguousError(ApiLifecycleError):
    """More than one gateway target matches the requested deployment."""


class ApiLifecycleConflictError(ApiLifecycleError):
    """Requested operation conflicts with an existing lifecycle resource."""


class ApiLifecycleNotFoundError(ApiLifecycleError):
    """Requested lifecycle resource does not exist."""
