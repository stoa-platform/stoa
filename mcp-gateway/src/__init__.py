"""STOA MCP Gateway - Model Context Protocol Gateway for AI-Native API Management."""

__version__ = "0.1.0"

# CAB-659: Export standardized error codes
from .errors import (
    STOAErrorCode,
    STOAError,
    STOAErrorDetail,
    STOAErrorResponse,
    error_result,
    TenantNotFoundError,
    APINotFoundError,
    SubscriptionNotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    InvalidActionError,
    InvalidParamsError,
    AuthRequiredError,
    BackendError,
    ServiceUnavailableError,
)

__all__ = [
    "STOAErrorCode",
    "STOAError",
    "STOAErrorDetail",
    "STOAErrorResponse",
    "error_result",
    "TenantNotFoundError",
    "APINotFoundError",
    "SubscriptionNotFoundError",
    "PermissionDeniedError",
    "RateLimitedError",
    "InvalidActionError",
    "InvalidParamsError",
    "AuthRequiredError",
    "BackendError",
    "ServiceUnavailableError",
]
