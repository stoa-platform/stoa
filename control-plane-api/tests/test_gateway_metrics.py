"""Tests for GatewayMetricsService — health and sync aggregation."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.models.gateway_instance import GatewayInstanceStatus
from src.models.gateway_deployment import DeploymentSyncStatus


class TestGatewayMetricsService:
    """Tests for gateway metrics aggregation."""

    @pytest.mark.asyncio
    async def test_health_summary_counts(self):
        """Correct counts by gateway status."""
        from src.services.gateway_metrics_service import GatewayMetricsService

        mock_db = AsyncMock()

        # Mock the count queries — returns counts for each status
        status_counts = {
            GatewayInstanceStatus.ONLINE: 3,
            GatewayInstanceStatus.OFFLINE: 1,
            GatewayInstanceStatus.DEGRADED: 1,
            GatewayInstanceStatus.MAINTENANCE: 0,
        }
        call_index = [0]
        statuses = list(GatewayInstanceStatus)

        async def mock_execute(query):
            result = MagicMock()
            status = statuses[call_index[0]]
            result.scalar_one.return_value = status_counts.get(status, 0)
            call_index[0] += 1
            return result

        mock_db.execute = mock_execute

        svc = GatewayMetricsService(mock_db)
        result = await svc.get_health_summary()

        assert result["online"] == 3
        assert result["offline"] == 1
        assert result["degraded"] == 1
        assert result["maintenance"] == 0
        assert result["total_gateways"] == 5
        assert result["health_percentage"] == 60.0

    @pytest.mark.asyncio
    async def test_sync_status_summary(self):
        """Correct counts by deployment sync_status."""
        from src.services.gateway_metrics_service import GatewayMetricsService

        mock_db = AsyncMock()

        status_counts = {
            DeploymentSyncStatus.PENDING: 2,
            DeploymentSyncStatus.SYNCING: 1,
            DeploymentSyncStatus.SYNCED: 10,
            DeploymentSyncStatus.DRIFTED: 1,
            DeploymentSyncStatus.ERROR: 1,
            DeploymentSyncStatus.DELETING: 0,
        }
        call_index = [0]
        statuses = list(DeploymentSyncStatus)

        async def mock_execute(query):
            result = MagicMock()
            status = statuses[call_index[0]]
            result.scalar_one.return_value = status_counts.get(status, 0)
            call_index[0] += 1
            return result

        mock_db.execute = mock_execute

        svc = GatewayMetricsService(mock_db)
        result = await svc.get_sync_status_summary()

        assert result["synced"] == 10
        assert result["pending"] == 2
        assert result["error"] == 1
        assert result["total_deployments"] == 15
        assert result["sync_percentage"] == pytest.approx(66.7, abs=0.1)

    @pytest.mark.asyncio
    async def test_gateway_metrics_with_errors(self):
        """Includes recent errors list for a specific gateway."""
        from src.services.gateway_metrics_service import GatewayMetricsService

        gateway_id = uuid4()
        mock_db = AsyncMock()

        # First call: get gateway
        mock_gateway = MagicMock()
        mock_gateway.id = gateway_id
        mock_gateway.name = "webmethods-prod"
        mock_gateway.display_name = "webMethods Production"
        mock_gateway.gateway_type = MagicMock(value="webmethods")
        mock_gateway.status = MagicMock(value="online")
        mock_gateway.last_health_check = None

        # Track execute calls
        execute_calls = []

        async def mock_execute(query):
            execute_calls.append(query)
            result = MagicMock()

            if len(execute_calls) == 1:
                # Gateway lookup
                result.scalar_one_or_none.return_value = mock_gateway
            elif len(execute_calls) <= 1 + len(list(DeploymentSyncStatus)):
                # Sync status counts
                result.scalar_one.return_value = 0
            else:
                # Recent errors query
                mock_error = MagicMock()
                mock_error.id = uuid4()
                mock_error.api_catalog_id = uuid4()
                mock_error.sync_error = "Connection timeout"
                mock_error.sync_attempts = 2
                mock_error.last_sync_attempt = None
                result.scalars.return_value.all.return_value = [mock_error]

            return result

        mock_db.execute = mock_execute

        svc = GatewayMetricsService(mock_db)
        result = await svc.get_gateway_metrics(gateway_id)

        assert result is not None
        assert result["name"] == "webmethods-prod"
        assert result["gateway_type"] == "webmethods"
        assert "recent_errors" in result
        assert len(result["recent_errors"]) == 1
        assert result["recent_errors"][0]["error"] == "Connection timeout"

    @pytest.mark.asyncio
    async def test_aggregated_metrics_overall_status(self):
        """overall_status = 'healthy' when all gateways online and no errors/drift."""
        from src.services.gateway_metrics_service import GatewayMetricsService

        svc = GatewayMetricsService(AsyncMock())

        # Mock health and sync summaries
        svc.get_health_summary = AsyncMock(return_value={
            "online": 3, "offline": 0, "degraded": 0, "maintenance": 0,
            "total_gateways": 3, "health_percentage": 100.0,
        })
        svc.get_sync_status_summary = AsyncMock(return_value={
            "pending": 0, "syncing": 0, "synced": 10, "drifted": 0, "error": 0, "deleting": 0,
            "total_deployments": 10, "sync_percentage": 100.0,
        })

        result = await svc.get_aggregated_metrics()

        assert result["overall_status"] == "healthy"
        assert result["health"]["total_gateways"] == 3
        assert result["sync"]["total_deployments"] == 10
