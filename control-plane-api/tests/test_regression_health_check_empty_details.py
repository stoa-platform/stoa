"""Regression test — health check degraded response must include error details.

When adapter.health_check() returns success=False, the error message was lost
because the service only passed result.data (empty {}) to health_details,
ignoring result.error. This caused the Console to show:
  {"status": "degraded", "details": {}}
with no explanation of what went wrong.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.adapters.gateway_adapter_interface import AdapterResult
from src.models.gateway_instance import GatewayInstanceStatus
from src.services.gateway_instance_service import GatewayInstanceService


class TestRegressionHealthCheckEmptyDetails:
    """Degraded health check must surface error in details, not return {}."""

    @pytest.fixture
    def mock_instance(self):
        instance = MagicMock()
        instance.id = uuid4()
        instance.name = "connect-webmethods-connect-production"
        instance.gateway_type.value = "stoa"
        instance.base_url = "http://gateway:8080"
        instance.auth_config = {"api_key": "test"}
        return instance

    async def test_regression_degraded_includes_error_in_details(self, mock_instance):
        """When health_check fails, details dict must contain the error message."""
        failed_result = AdapterResult(
            success=False,
            error="Health check failed: HTTP 401 — (empty response)",
            data={},
        )
        mock_adapter = AsyncMock()
        mock_adapter.health_check.return_value = failed_result

        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = mock_instance

        svc = GatewayInstanceService.__new__(GatewayInstanceService)
        svc.repo = mock_repo

        with patch(
            "src.services.credential_resolver.create_adapter_with_credentials",
            return_value=mock_adapter,
        ):
            result = await svc.health_check(mock_instance.id)

        assert result["status"] == GatewayInstanceStatus.DEGRADED.value
        assert "error" in result["details"], "details must contain 'error' key when health check fails"
        assert "401" in result["details"]["error"]

    async def test_regression_healthy_has_no_error_in_details(self, mock_instance):
        """When health_check succeeds, details must NOT contain an error key."""
        ok_result = AdapterResult(
            success=True,
            data={"status": "ok", "version": "0.9.1", "routes_count": 3, "policies_count": 1},
        )
        mock_adapter = AsyncMock()
        mock_adapter.health_check.return_value = ok_result

        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = mock_instance

        svc = GatewayInstanceService.__new__(GatewayInstanceService)
        svc.repo = mock_repo

        with patch(
            "src.services.credential_resolver.create_adapter_with_credentials",
            return_value=mock_adapter,
        ):
            result = await svc.health_check(mock_instance.id)

        assert result["status"] == GatewayInstanceStatus.ONLINE.value
        assert "error" not in result["details"]
