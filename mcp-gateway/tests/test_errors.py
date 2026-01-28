# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""CAB-659: Tests for STOA Standard Error Code System."""

import pytest
from src.errors import (
    STOAErrorCode,
    STOAError,
    STOAErrorDetail,
    STOAErrorResponse,
    error_result,
    ERROR_CODE_TO_HTTP_STATUS,
    ERROR_CODE_SUGGESTIONS,
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


class TestSTOAErrorCode:
    """Test STOAErrorCode enum."""

    def test_error_codes_are_strings(self):
        """All error codes should be string values."""
        for code in STOAErrorCode:
            assert isinstance(code.value, str)
            assert code.value == code.name  # Enum value matches name

    def test_all_codes_have_http_status(self):
        """All error codes should have an HTTP status mapping."""
        for code in STOAErrorCode:
            assert code in ERROR_CODE_TO_HTTP_STATUS, f"Missing HTTP status for {code}"

    def test_all_codes_have_suggestions(self):
        """All error codes should have default suggestions."""
        for code in STOAErrorCode:
            assert code in ERROR_CODE_SUGGESTIONS, f"Missing suggestion for {code}"

    def test_http_status_ranges(self):
        """HTTP status codes should be in valid ranges."""
        for code, status in ERROR_CODE_TO_HTTP_STATUS.items():
            assert 400 <= status < 600, f"Invalid HTTP status {status} for {code}"


class TestSTOAError:
    """Test STOAError exception class."""

    def test_basic_error(self):
        """Test creating a basic error."""
        error = STOAError(
            code=STOAErrorCode.API_NOT_FOUND,
            message="API 'test-api' not found",
        )
        assert error.code == STOAErrorCode.API_NOT_FOUND
        assert error.message == "API 'test-api' not found"
        assert error.details is None
        assert error.suggestion is not None  # Default suggestion

    def test_error_with_details(self):
        """Test error with details."""
        error = STOAError(
            code=STOAErrorCode.RATE_LIMITED,
            message="Rate limit exceeded",
            details={"limit": 1000, "used": 1500},
        )
        assert error.details == {"limit": 1000, "used": 1500}

    def test_error_with_custom_suggestion(self):
        """Test error with custom suggestion overriding default."""
        error = STOAError(
            code=STOAErrorCode.INTERNAL_ERROR,
            message="Something went wrong",
            suggestion="Please contact your administrator",
        )
        assert error.suggestion == "Please contact your administrator"

    def test_http_status_property(self):
        """Test http_status property."""
        error = STOAError(STOAErrorCode.API_NOT_FOUND, "Not found")
        assert error.http_status == 404

        error = STOAError(STOAErrorCode.RATE_LIMITED, "Too many requests")
        assert error.http_status == 429

        error = STOAError(STOAErrorCode.PERMISSION_DENIED, "Forbidden")
        assert error.http_status == 403

    def test_to_dict(self):
        """Test converting error to dict."""
        error = STOAError(
            code=STOAErrorCode.API_NOT_FOUND,
            message="API 'billing-api' not found",
            details={"api_id": "billing-api"},
        )
        result = error.to_dict()
        
        assert "error" in result
        assert result["error"]["code"] == "API_NOT_FOUND"
        assert result["error"]["message"] == "API 'billing-api' not found"
        assert result["error"]["details"] == {"api_id": "billing-api"}
        assert result["error"]["suggestion"] is not None

    def test_to_tool_result(self):
        """Test converting error to tool result format."""
        error = STOAError(
            code=STOAErrorCode.INVALID_ACTION,
            message="Unknown action: 'delete'",
            details={"action": "delete"},
        )
        result = error.to_tool_result()
        
        assert result["error"] == "INVALID_ACTION"
        assert result["message"] == "Unknown action: 'delete'"
        assert result["details"] == {"action": "delete"}

    def test_to_response(self):
        """Test converting error to Pydantic response."""
        error = STOAError(
            code=STOAErrorCode.AUTH_REQUIRED,
            message="Authentication required",
        )
        response = error.to_response()
        
        assert isinstance(response, STOAErrorResponse)
        assert response.error.code == "AUTH_REQUIRED"
        assert response.error.message == "Authentication required"

    def test_string_code_conversion(self):
        """Test creating error with string code."""
        error = STOAError(
            code="API_NOT_FOUND",  # String instead of enum
            message="Not found",
        )
        assert error.code == STOAErrorCode.API_NOT_FOUND


class TestSpecificErrorClasses:
    """Test convenience error classes."""

    def test_tenant_not_found_error(self):
        """Test TenantNotFoundError."""
        error = TenantNotFoundError("high-five")
        assert error.code == STOAErrorCode.TENANT_NOT_FOUND
        assert "high-five" in error.message
        assert error.details["tenant_id"] == "high-five"

    def test_api_not_found_error(self):
        """Test APINotFoundError."""
        error = APINotFoundError("billing-api")
        assert error.code == STOAErrorCode.API_NOT_FOUND
        assert "billing-api" in error.message
        assert error.details["api_id"] == "billing-api"

    def test_subscription_not_found_error(self):
        """Test SubscriptionNotFoundError."""
        error = SubscriptionNotFoundError("sub-123")
        assert error.code == STOAErrorCode.SUBSCRIPTION_NOT_FOUND
        assert "sub-123" in error.message
        assert error.details["subscription_id"] == "sub-123"

    def test_permission_denied_error(self):
        """Test PermissionDeniedError."""
        error = PermissionDeniedError("billing-api", "write")
        assert error.code == STOAErrorCode.PERMISSION_DENIED
        assert "write" in error.message
        assert error.details["action"] == "write"

    def test_rate_limited_error(self):
        """Test RateLimitedError."""
        error = RateLimitedError(limit=1000, used=1500, resets_in_seconds=3600)
        assert error.code == STOAErrorCode.RATE_LIMITED
        assert error.details["limit"] == 1000
        assert error.details["used"] == 1500
        assert error.details["resets_in_seconds"] == 3600
        assert error.details["resets_in_minutes"] == 60

    def test_invalid_action_error(self):
        """Test InvalidActionError with valid actions hint."""
        error = InvalidActionError("delete", valid_actions=["list", "get", "create"])
        assert error.code == STOAErrorCode.INVALID_ACTION
        assert "delete" in error.message
        assert error.details["valid_actions"] == ["list", "get", "create"]
        assert "list" in error.suggestion

    def test_invalid_params_error(self):
        """Test InvalidParamsError."""
        error = InvalidParamsError("api_id", reason="is required")
        assert error.code == STOAErrorCode.INVALID_PARAMS
        assert "api_id" in error.message
        assert "is required" in error.message

    def test_auth_required_error(self):
        """Test AuthRequiredError."""
        error = AuthRequiredError()
        assert error.code == STOAErrorCode.AUTH_REQUIRED
        assert "Authentication" in error.message

    def test_backend_error(self):
        """Test BackendError."""
        error = BackendError("control-plane-api", status_code=500)
        assert error.code == STOAErrorCode.BACKEND_ERROR
        assert error.details["backend"] == "control-plane-api"
        assert error.details["status_code"] == 500

    def test_service_unavailable_error(self):
        """Test ServiceUnavailableError."""
        error = ServiceUnavailableError("database")
        assert error.code == STOAErrorCode.SERVICE_UNAVAILABLE
        assert "database" in error.message


class TestErrorResultHelper:
    """Test error_result helper function."""

    def test_basic_error_result(self):
        """Test creating basic error result."""
        result = error_result(
            STOAErrorCode.API_NOT_FOUND,
            "API not found",
        )
        assert result["error"] == "API_NOT_FOUND"
        assert result["message"] == "API not found"
        assert "suggestion" in result

    def test_error_result_with_details(self):
        """Test error result with details."""
        result = error_result(
            STOAErrorCode.RATE_LIMITED,
            "Rate limit exceeded",
            details={"limit": 100, "used": 150},
        )
        assert result["details"] == {"limit": 100, "used": 150}

    def test_error_result_with_custom_suggestion(self):
        """Test error result with custom suggestion."""
        result = error_result(
            STOAErrorCode.INTERNAL_ERROR,
            "Server error",
            suggestion="Try again in 5 minutes",
        )
        assert result["suggestion"] == "Try again in 5 minutes"

    def test_error_result_string_code(self):
        """Test error result with string code."""
        result = error_result("INVALID_ACTION", "Unknown action")
        assert result["error"] == "INVALID_ACTION"


class TestSTOAErrorDetail:
    """Test STOAErrorDetail Pydantic model."""

    def test_validation(self):
        """Test model validation."""
        detail = STOAErrorDetail(
            code="API_NOT_FOUND",
            message="API not found",
            details={"api_id": "test"},
            suggestion="Use stoa_catalog to find APIs",
        )
        assert detail.code == "API_NOT_FOUND"
        assert detail.message == "API not found"

    def test_optional_fields(self):
        """Test optional fields."""
        detail = STOAErrorDetail(
            code="INTERNAL_ERROR",
            message="Something went wrong",
        )
        assert detail.details is None
        assert detail.suggestion is None

    def test_json_serialization(self):
        """Test JSON serialization."""
        detail = STOAErrorDetail(
            code="RATE_LIMITED",
            message="Too many requests",
            details={"limit": 1000},
            suggestion="Wait and retry",
        )
        json_dict = detail.model_dump()
        assert json_dict["code"] == "RATE_LIMITED"
        assert json_dict["details"]["limit"] == 1000
