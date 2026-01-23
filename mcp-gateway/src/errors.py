"""CAB-659: STOA Standard Error Code System.

Standardized error codes and exception classes for the MCP Gateway.
These errors provide consistent, machine-readable error responses with
helpful suggestions for LLM-assisted remediation.

Error Response Schema:
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Subscription sub-123 has exceeded its hourly quota",
    "details": {"used": 1000, "limit": 1000, "resets_in_minutes": 45},
    "suggestion": "Wait for quota reset or check usage with stoa_metrics quota"
  }
}
```
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class STOAErrorCode(str, Enum):
    """Standard STOA error codes.
    
    Each code maps to a specific HTTP status and has a default message template.
    """
    
    # 400 Bad Request
    INVALID_ACTION = "INVALID_ACTION"
    INVALID_PARAMS = "INVALID_PARAMS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    
    # 401 Unauthorized
    AUTH_REQUIRED = "AUTH_REQUIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    
    # 403 Forbidden
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    SCOPE_INSUFFICIENT = "SCOPE_INSUFFICIENT"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    
    # 404 Not Found
    TENANT_NOT_FOUND = "TENANT_NOT_FOUND"
    API_NOT_FOUND = "API_NOT_FOUND"
    SUBSCRIPTION_NOT_FOUND = "SUBSCRIPTION_NOT_FOUND"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    CONTRACT_NOT_FOUND = "CONTRACT_NOT_FOUND"
    
    # 409 Conflict
    ALREADY_EXISTS = "ALREADY_EXISTS"
    SUBSCRIPTION_CONFLICT = "SUBSCRIPTION_CONFLICT"
    
    # 429 Too Many Requests
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    
    # 500 Internal Server Error
    INTERNAL_ERROR = "INTERNAL_ERROR"
    
    # 502 Bad Gateway
    BACKEND_ERROR = "BACKEND_ERROR"
    
    # 503 Service Unavailable
    API_UNAVAILABLE = "API_UNAVAILABLE"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    
    # 504 Gateway Timeout
    BACKEND_TIMEOUT = "BACKEND_TIMEOUT"
    
    # Feature-specific
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


# HTTP status code mapping
ERROR_CODE_TO_HTTP_STATUS: dict[STOAErrorCode, int] = {
    # 400
    STOAErrorCode.INVALID_ACTION: 400,
    STOAErrorCode.INVALID_PARAMS: 400,
    STOAErrorCode.VALIDATION_ERROR: 400,
    # 401
    STOAErrorCode.AUTH_REQUIRED: 401,
    STOAErrorCode.INVALID_TOKEN: 401,
    STOAErrorCode.TOKEN_EXPIRED: 401,
    # 403
    STOAErrorCode.PERMISSION_DENIED: 403,
    STOAErrorCode.TENANT_MISMATCH: 403,
    STOAErrorCode.SCOPE_INSUFFICIENT: 403,
    STOAErrorCode.POLICY_VIOLATION: 403,
    # 404
    STOAErrorCode.TENANT_NOT_FOUND: 404,
    STOAErrorCode.API_NOT_FOUND: 404,
    STOAErrorCode.SUBSCRIPTION_NOT_FOUND: 404,
    STOAErrorCode.TOOL_NOT_FOUND: 404,
    STOAErrorCode.RESOURCE_NOT_FOUND: 404,
    STOAErrorCode.CONTRACT_NOT_FOUND: 404,
    # 409
    STOAErrorCode.ALREADY_EXISTS: 409,
    STOAErrorCode.SUBSCRIPTION_CONFLICT: 409,
    # 429
    STOAErrorCode.RATE_LIMITED: 429,
    STOAErrorCode.QUOTA_EXCEEDED: 429,
    # 500
    STOAErrorCode.INTERNAL_ERROR: 500,
    # 502
    STOAErrorCode.BACKEND_ERROR: 502,
    # 503
    STOAErrorCode.API_UNAVAILABLE: 503,
    STOAErrorCode.SERVICE_UNAVAILABLE: 503,
    # 504
    STOAErrorCode.BACKEND_TIMEOUT: 504,
    # Feature
    STOAErrorCode.NOT_IMPLEMENTED: 501,
}


# Default suggestions for each error code (helps LLMs guide users)
ERROR_CODE_SUGGESTIONS: dict[STOAErrorCode, str] = {
    STOAErrorCode.INVALID_ACTION: "Check the 'action' parameter against allowed values in the tool schema",
    STOAErrorCode.INVALID_PARAMS: "Verify required parameters are provided and have correct types",
    STOAErrorCode.VALIDATION_ERROR: "Check input against the tool's JSON schema",
    STOAErrorCode.AUTH_REQUIRED: "Provide a valid JWT token via Authorization header",
    STOAErrorCode.INVALID_TOKEN: "Refresh your authentication token and retry",
    STOAErrorCode.TOKEN_EXPIRED: "Obtain a new token from Keycloak and retry",
    STOAErrorCode.PERMISSION_DENIED: "Contact your tenant admin to request access",
    STOAErrorCode.TENANT_MISMATCH: "Verify you're accessing resources within your tenant",
    STOAErrorCode.SCOPE_INSUFFICIENT: "Request additional OAuth scopes for this operation",
    STOAErrorCode.POLICY_VIOLATION: "Review the policy requirements and adjust your request parameters",
    STOAErrorCode.TENANT_NOT_FOUND: "Use stoa_tenants to list available tenants",
    STOAErrorCode.API_NOT_FOUND: "Use stoa_catalog action='list' to find available APIs",
    STOAErrorCode.SUBSCRIPTION_NOT_FOUND: "Use stoa_subscription action='list' to find your subscriptions",
    STOAErrorCode.TOOL_NOT_FOUND: "Use stoa_tools action='list' to discover available tools",
    STOAErrorCode.RESOURCE_NOT_FOUND: "Verify the resource ID exists and you have access",
    STOAErrorCode.CONTRACT_NOT_FOUND: "Use stoa_uac action='list' to find available contracts",
    STOAErrorCode.ALREADY_EXISTS: "The resource already exists; use update instead of create",
    STOAErrorCode.SUBSCRIPTION_CONFLICT: "Cancel existing subscription before creating a new one",
    STOAErrorCode.RATE_LIMITED: "Wait for rate limit window to reset or reduce request frequency",
    STOAErrorCode.QUOTA_EXCEEDED: "Check quota status with stoa_metrics action='quota'",
    STOAErrorCode.INTERNAL_ERROR: "Retry the request; if persistent, contact support",
    STOAErrorCode.BACKEND_ERROR: "The backend API returned an error; check API status",
    STOAErrorCode.API_UNAVAILABLE: "The API is temporarily unavailable; retry later",
    STOAErrorCode.SERVICE_UNAVAILABLE: "Platform services are starting up; retry in a few seconds",
    STOAErrorCode.BACKEND_TIMEOUT: "The backend took too long; retry or contact API owner",
    STOAErrorCode.NOT_IMPLEMENTED: "This feature is not yet available",
}


class STOAErrorDetail(BaseModel):
    """Standard STOA error response body.
    
    This schema is returned in tool results when errors occur,
    providing machine-readable error codes with human-friendly messages
    and LLM-optimized suggestions.
    """
    
    code: str = Field(
        ...,
        description="Machine-readable error code (e.g., 'TENANT_NOT_FOUND')",
        examples=["RATE_LIMITED", "API_NOT_FOUND", "PERMISSION_DENIED"],
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["Subscription sub-123 has exceeded its hourly quota"],
    )
    details: dict[str, Any] | None = Field(
        None,
        description="Additional context for debugging",
        examples=[{"used": 1000, "limit": 1000, "resets_in_minutes": 45}],
    )
    suggestion: str | None = Field(
        None,
        description="Remediation hint for LLM-assisted recovery",
        examples=["Wait for quota reset or check usage with stoa_metrics quota"],
    )


class STOAErrorResponse(BaseModel):
    """Wrapper for error responses."""
    
    error: STOAErrorDetail


class STOAError(Exception):
    """Base exception for STOA errors.
    
    All STOA errors inherit from this class, providing consistent
    error handling and response generation.
    
    Usage:
        raise STOAError(
            code=STOAErrorCode.API_NOT_FOUND,
            message=f"API '{api_id}' not found in catalog",
            details={"api_id": api_id, "searched_tenant": tenant_id}
        )
    """
    
    def __init__(
        self,
        code: STOAErrorCode | str,
        message: str,
        details: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        """Initialize STOA error.
        
        Args:
            code: Error code (STOAErrorCode enum or string)
            message: Human-readable error message
            details: Additional context for debugging
            suggestion: Override default suggestion (optional)
        """
        self.code = code if isinstance(code, STOAErrorCode) else STOAErrorCode(code)
        self.message = message
        self.details = details
        self.suggestion = suggestion or ERROR_CODE_SUGGESTIONS.get(self.code)
        super().__init__(message)
    
    @property
    def http_status(self) -> int:
        """Get HTTP status code for this error."""
        return ERROR_CODE_TO_HTTP_STATUS.get(self.code, 500)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.
        
        Returns the error in tool result format (flat dict with 'error' key).
        """
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
                "suggestion": self.suggestion,
            }
        }
    
    def to_tool_result(self) -> dict[str, Any]:
        """Convert to tool result format for MCP responses.
        
        This is the format returned by tool handlers when errors occur.
        """
        result = {
            "error": self.code.value,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result
    
    def to_response(self) -> STOAErrorResponse:
        """Convert to Pydantic response model."""
        return STOAErrorResponse(
            error=STOAErrorDetail(
                code=self.code.value,
                message=self.message,
                details=self.details,
                suggestion=self.suggestion,
            )
        )


# =============================================================================
# Specific Error Classes (Convenience)
# =============================================================================


class TenantNotFoundError(STOAError):
    """Raised when a tenant is not found."""
    
    def __init__(
        self,
        tenant_id: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code=STOAErrorCode.TENANT_NOT_FOUND,
            message=message or f"Tenant '{tenant_id}' not found",
            details=details or {"tenant_id": tenant_id},
        )


class APINotFoundError(STOAError):
    """Raised when an API is not found."""
    
    def __init__(
        self,
        api_id: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code=STOAErrorCode.API_NOT_FOUND,
            message=message or f"API '{api_id}' not found",
            details=details or {"api_id": api_id},
        )


class SubscriptionNotFoundError(STOAError):
    """Raised when a subscription is not found."""
    
    def __init__(
        self,
        subscription_id: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code=STOAErrorCode.SUBSCRIPTION_NOT_FOUND,
            message=message or f"Subscription '{subscription_id}' not found",
            details=details or {"subscription_id": subscription_id},
        )


class PermissionDeniedError(STOAError):
    """Raised when user lacks permission."""

    def __init__(
        self,
        resource: str,
        action: str | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        default_msg = f"Permission denied for resource '{resource}'"
        if action:
            default_msg = f"Permission denied: cannot {action} on '{resource}'"
        super().__init__(
            code=STOAErrorCode.PERMISSION_DENIED,
            message=message or default_msg,
            details=details or {"resource": resource, "action": action},
        )


class PolicyViolationError(STOAError):
    """Raised when argument policy validation fails.

    CAB-876: This error is raised when tool arguments violate
    business rules defined in YAML policy files.
    """

    def __init__(
        self,
        policy_name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code=STOAErrorCode.POLICY_VIOLATION,
            message=message,
            details={"policy": policy_name, **(details or {})},
        )
        self.policy_name = policy_name


class RateLimitedError(STOAError):
    """Raised when rate limit is exceeded."""
    
    def __init__(
        self,
        limit: int,
        used: int,
        resets_in_seconds: int | None = None,
        message: str | None = None,
    ):
        details = {"limit": limit, "used": used}
        if resets_in_seconds:
            details["resets_in_seconds"] = resets_in_seconds
            details["resets_in_minutes"] = resets_in_seconds // 60
        
        super().__init__(
            code=STOAErrorCode.RATE_LIMITED,
            message=message or f"Rate limit exceeded: {used}/{limit} requests",
            details=details,
        )


class InvalidActionError(STOAError):
    """Raised when an invalid action is provided."""
    
    def __init__(
        self,
        action: str,
        valid_actions: list[str] | None = None,
        message: str | None = None,
    ):
        details: dict[str, Any] = {"action": action}
        if valid_actions:
            details["valid_actions"] = valid_actions
        
        super().__init__(
            code=STOAErrorCode.INVALID_ACTION,
            message=message or f"Unknown action: '{action}'",
            details=details,
            suggestion=f"Valid actions are: {', '.join(valid_actions)}" if valid_actions else None,
        )


class InvalidParamsError(STOAError):
    """Raised when required parameters are missing or invalid."""
    
    def __init__(
        self,
        param: str,
        reason: str = "is required",
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code=STOAErrorCode.INVALID_PARAMS,
            message=message or f"Parameter '{param}' {reason}",
            details=details or {"parameter": param, "reason": reason},
        )


class AuthRequiredError(STOAError):
    """Raised when authentication is required but not provided."""
    
    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code=STOAErrorCode.AUTH_REQUIRED,
            message=message or "Authentication required",
            details=details,
        )


class BackendError(STOAError):
    """Raised when a backend API call fails."""
    
    def __init__(
        self,
        backend: str,
        status_code: int | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        error_details = details or {}
        error_details["backend"] = backend
        if status_code:
            error_details["status_code"] = status_code
        
        super().__init__(
            code=STOAErrorCode.BACKEND_ERROR,
            message=message or f"Backend '{backend}' returned an error",
            details=error_details,
        )


class ServiceUnavailableError(STOAError):
    """Raised when a required service is unavailable."""
    
    def __init__(
        self,
        service: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code=STOAErrorCode.SERVICE_UNAVAILABLE,
            message=message or f"Service '{service}' is temporarily unavailable",
            details=details or {"service": service},
        )


# =============================================================================
# Helper Functions
# =============================================================================


def error_result(
    code: STOAErrorCode | str,
    message: str,
    details: dict[str, Any] | None = None,
    suggestion: str | None = None,
) -> dict[str, Any]:
    """Create a standardized error result dict for tool handlers.
    
    This is a convenience function for returning errors from handlers
    without raising exceptions.
    
    Args:
        code: Error code
        message: Human-readable message
        details: Additional context
        suggestion: Override default suggestion
        
    Returns:
        Dict suitable for tool handler return value
        
    Example:
        return error_result(
            STOAErrorCode.API_NOT_FOUND,
            f"API '{api_id}' not found",
            details={"api_id": api_id}
        )
    """
    error_code = code if isinstance(code, STOAErrorCode) else STOAErrorCode(code)
    result: dict[str, Any] = {
        "error": error_code.value,
        "message": message,
    }
    if details:
        result["details"] = details
    result["suggestion"] = suggestion or ERROR_CODE_SUGGESTIONS.get(error_code)
    return result
