"""Tests for Portal Executions feature (CAB-432).

Covers: classifier, service, router, and security constraints.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.features.portal_executions.classifier import classify_error
from src.features.portal_executions.models import (
    ErrorCategory,
    ErrorSource,
    ExecutionError,
    ExecutionStats,
    ExecutionSummary,
)
from src.features.portal_executions.service import (
    PortalExecutionsService,
    _mask_api_key,
    _verify_app_ownership,
)
from src.features.portal_executions.config import PortalExecutionsSettings


# ============================================================================
# Classifier Tests
# ============================================================================


class TestClassifier:
    """Test error classification logic."""

    def test_classify_401_returns_gateway_auth_failed(self):
        result = classify_error(status_code=401)
        assert result["error_source"] == ErrorSource.GATEWAY
        assert result["error_category"] == ErrorCategory.AUTH_FAILED
        assert result["help_text"]
        assert result["suggested_action"]

    def test_classify_403_returns_gateway_forbidden(self):
        result = classify_error(status_code=403)
        assert result["error_source"] == ErrorSource.GATEWAY
        assert result["error_category"] == ErrorCategory.FORBIDDEN

    def test_classify_429_returns_gateway_rate_limit(self):
        result = classify_error(status_code=429)
        assert result["error_source"] == ErrorSource.GATEWAY
        assert result["error_category"] == ErrorCategory.RATE_LIMIT

    def test_classify_502_returns_backend_bad_gateway(self):
        result = classify_error(status_code=502)
        assert result["error_source"] == ErrorSource.BACKEND
        assert result["error_category"] == ErrorCategory.BAD_GATEWAY

    def test_classify_503_returns_backend_unavailable(self):
        result = classify_error(status_code=503)
        assert result["error_source"] == ErrorSource.BACKEND
        assert result["error_category"] == ErrorCategory.UNAVAILABLE

    def test_classify_504_returns_backend_timeout(self):
        result = classify_error(status_code=504)
        assert result["error_source"] == ErrorSource.BACKEND
        assert result["error_category"] == ErrorCategory.TIMEOUT

    def test_classify_500_mcp_returns_tool_error(self):
        result = classify_error(status_code=500, is_mcp_tool=True)
        assert result["error_source"] == ErrorSource.TOOL
        assert result["error_category"] == ErrorCategory.TOOL_ERROR

    def test_classify_500_async_returns_kafka_error(self):
        result = classify_error(status_code=500, is_async=True)
        assert result["error_source"] == ErrorSource.KAFKA
        assert result["error_category"] == ErrorCategory.KAFKA_ERROR

    def test_classify_500_mcp_and_async_prefers_tool(self):
        """Edge case: MCP tool takes priority over async."""
        result = classify_error(status_code=500, is_mcp_tool=True, is_async=True)
        assert result["error_source"] == ErrorSource.TOOL
        assert result["error_category"] == ErrorCategory.TOOL_ERROR

    def test_classify_500_plain_returns_backend_unavailable(self):
        result = classify_error(status_code=500)
        assert result["error_source"] == ErrorSource.BACKEND
        assert result["error_category"] == ErrorCategory.UNAVAILABLE

    def test_classify_400_returns_client_bad_request(self):
        result = classify_error(status_code=400)
        assert result["error_source"] == ErrorSource.CLIENT
        assert result["error_category"] == ErrorCategory.BAD_REQUEST

    def test_classify_404_returns_client_not_found(self):
        result = classify_error(status_code=404)
        assert result["error_source"] == ErrorSource.CLIENT
        assert result["error_category"] == ErrorCategory.NOT_FOUND

    def test_classify_422_returns_client_bad_request(self):
        result = classify_error(status_code=422)
        assert result["error_source"] == ErrorSource.CLIENT
        assert result["error_category"] == ErrorCategory.BAD_REQUEST

    def test_classify_unknown_returns_client_bad_request(self):
        result = classify_error(status_code=418)
        assert result["error_source"] == ErrorSource.CLIENT
        assert result["error_category"] == ErrorCategory.BAD_REQUEST

    def test_all_classifications_have_required_fields(self):
        """Every classification must include all consumer-facing fields."""
        for code in [400, 401, 403, 404, 422, 429, 500, 502, 503, 504]:
            result = classify_error(status_code=code)
            assert "error_source" in result
            assert "error_category" in result
            assert "summary" in result
            assert "help_text" in result
            assert "suggested_action" in result
            assert len(result["help_text"]) > 10
            assert len(result["suggested_action"]) > 10


# ============================================================================
# API Key Masking Tests
# ============================================================================


class TestMasking:
    def test_mask_normal_key(self):
        assert _mask_api_key("sk-abc123xyz") == "sk-***xyz"

    def test_mask_short_key(self):
        assert _mask_api_key("short") == "***"

    def test_mask_none_key(self):
        assert _mask_api_key(None) == "***"

    def test_mask_empty_key(self):
        assert _mask_api_key("") == "***"


# ============================================================================
# Service Tests
# ============================================================================


def _make_user(user_id="user-1", username="testuser", tenant_id="tenant-1"):
    from src.auth.dependencies import User

    return User(
        id=user_id,
        email="test@example.com",
        username=username,
        roles=["viewer"],
        tenant_id=tenant_id,
    )


def _make_app(app_id="app-1", owner_id="user-1", name="Test App"):
    return {
        "id": app_id,
        "name": name,
        "display_name": name,
        "client_id": "app-abc123def456",
        "owner_id": owner_id,
        "status": "active",
        "created_at": "2025-01-01T00:00:00Z",
    }


class TestService:
    @pytest.fixture
    def settings(self):
        return PortalExecutionsSettings(
            enabled=True,
            error_window_hours=24,
            max_errors=50,
        )

    @pytest.fixture
    def service(self, settings):
        return PortalExecutionsService(settings)

    @pytest.mark.asyncio
    async def test_get_execution_summary_returns_stats(self, service):
        user = _make_user()
        app = _make_app(owner_id=user.id)

        mock_summary = MagicMock()
        mock_summary.today.total_calls = 100
        mock_summary.today.success_rate = 95.0
        mock_summary.today.avg_latency_ms = 150.0
        mock_summary.today.error_count = 5

        with (
            patch(
                "src.features.portal_executions.service._verify_app_ownership",
                return_value=app,
            ),
            patch(
                "src.features.portal_executions.service.metrics_service"
            ) as mock_metrics,
            patch(
                "src.features.portal_executions.service.loki_client"
            ) as mock_loki,
        ):
            mock_metrics.get_usage_summary = AsyncMock(return_value=mock_summary)
            mock_loki.get_recent_calls = AsyncMock(return_value=[])

            result = await service.get_execution_summary("app-1", user)

        assert result.app_id == "app-1"
        assert result.stats.total_calls_24h == 100
        assert result.stats.success_rate == 95.0
        assert not result.degraded

    @pytest.mark.asyncio
    async def test_get_execution_summary_masks_api_key(self, service):
        user = _make_user()
        app = _make_app(owner_id=user.id)

        mock_summary = MagicMock()
        mock_summary.today.total_calls = 0
        mock_summary.today.success_rate = 100.0
        mock_summary.today.avg_latency_ms = 0.0
        mock_summary.today.error_count = 0

        with (
            patch(
                "src.features.portal_executions.service._verify_app_ownership",
                return_value=app,
            ),
            patch(
                "src.features.portal_executions.service.metrics_service"
            ) as mock_metrics,
            patch(
                "src.features.portal_executions.service.loki_client"
            ) as mock_loki,
        ):
            mock_metrics.get_usage_summary = AsyncMock(return_value=mock_summary)
            mock_loki.get_recent_calls = AsyncMock(return_value=[])

            result = await service.get_execution_summary("app-1", user)

        assert "***" in result.api_key_hint
        assert "abc123def456" not in result.api_key_hint

    @pytest.mark.asyncio
    async def test_get_execution_summary_degraded_when_prometheus_down(self, service):
        user = _make_user()
        app = _make_app(owner_id=user.id)

        with (
            patch(
                "src.features.portal_executions.service._verify_app_ownership",
                return_value=app,
            ),
            patch(
                "src.features.portal_executions.service.metrics_service"
            ) as mock_metrics,
            patch(
                "src.features.portal_executions.service.loki_client"
            ) as mock_loki,
        ):
            mock_metrics.get_usage_summary = AsyncMock(
                side_effect=Exception("Prometheus down")
            )
            mock_loki.get_recent_calls = AsyncMock(return_value=[])

            result = await service.get_execution_summary("app-1", user)

        assert result.degraded is True
        assert "metrics" in result.degraded_services

    @pytest.mark.asyncio
    async def test_get_execution_summary_degraded_when_loki_down(self, service):
        user = _make_user()
        app = _make_app(owner_id=user.id)

        mock_summary = MagicMock()
        mock_summary.today.total_calls = 10
        mock_summary.today.success_rate = 90.0
        mock_summary.today.avg_latency_ms = 100.0
        mock_summary.today.error_count = 1

        with (
            patch(
                "src.features.portal_executions.service._verify_app_ownership",
                return_value=app,
            ),
            patch(
                "src.features.portal_executions.service.metrics_service"
            ) as mock_metrics,
            patch(
                "src.features.portal_executions.service.loki_client"
            ) as mock_loki,
        ):
            mock_metrics.get_usage_summary = AsyncMock(return_value=mock_summary)
            mock_loki.get_recent_calls = AsyncMock(
                side_effect=Exception("Loki down")
            )

            result = await service.get_execution_summary("app-1", user)

        assert result.degraded is True
        assert "logs" in result.degraded_services

    @pytest.mark.asyncio
    async def test_get_execution_summary_app_not_found(self, service):
        user = _make_user()

        with patch(
            "src.features.portal_executions.service._verify_app_ownership",
            return_value=None,
        ), patch(
            "src.routers.portal_applications._applications", {}
        ):
            with pytest.raises(ValueError, match="not found"):
                await service.get_execution_summary("nonexistent", user)

    @pytest.mark.asyncio
    async def test_get_execution_summary_access_denied(self, service):
        user = _make_user(user_id="other-user")

        with patch(
            "src.features.portal_executions.service._verify_app_ownership",
            return_value=None,
        ), patch(
            "src.routers.portal_applications._applications",
            {"app-1": _make_app()},
        ):
            with pytest.raises(PermissionError, match="Access denied"):
                await service.get_execution_summary("app-1", user)


# ============================================================================
# Security Tests — Black-Box Verification
# ============================================================================


class TestSecurity:
    """Verify that consumer responses NEVER leak internal data."""

    def _make_execution_error(self, **overrides) -> ExecutionError:
        defaults = {
            "id": "err-001",
            "timestamp": datetime.now(timezone.utc),
            "method": "POST",
            "path": "/v1/tools/call",
            "status_code": 500,
            "duration_ms": 1500,
            "error_source": ErrorSource.BACKEND,
            "error_category": ErrorCategory.UNAVAILABLE,
            "summary": "Unexpected error",
            "help_text": "An error occurred",
            "suggested_action": "Retry the request",
            "trace_id": "trace-abc",
        }
        defaults.update(overrides)
        return ExecutionError(**defaults)

    def test_response_never_contains_stack_trace(self):
        error = self._make_execution_error()
        data = error.model_dump_json()
        assert "Traceback" not in data
        assert "stack" not in data.lower() or "stack_trace" not in data

    def test_response_never_contains_request_body(self):
        error = self._make_execution_error()
        fields = set(error.model_fields.keys())
        assert "request_body" not in fields
        assert "body" not in fields

    def test_response_never_contains_response_body(self):
        error = self._make_execution_error()
        fields = set(error.model_fields.keys())
        assert "response_body" not in fields

    def test_response_never_contains_internal_logs(self):
        error = self._make_execution_error()
        fields = set(error.model_fields.keys())
        assert "logs" not in fields
        assert "internal_logs" not in fields

    def test_response_never_contains_backend_details(self):
        error = self._make_execution_error()
        fields = set(error.model_fields.keys())
        assert "headers" not in fields
        assert "pod" not in fields
        assert "node" not in fields
        assert "environment" not in fields

    def test_execution_summary_model_has_no_internal_fields(self):
        fields = set(ExecutionSummary.model_fields.keys())
        forbidden = {
            "stack_trace", "request_body", "response_body",
            "internal_logs", "headers", "pod", "node",
        }
        assert fields.isdisjoint(forbidden)
