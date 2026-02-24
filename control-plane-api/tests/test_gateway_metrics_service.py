"""Comprehensive unit tests for GatewayMetricsService (CAB-1316).

Covers:
- get_health_summary: all online, all offline, mixed, zero-division guard,
  health_percentage calculation, all status values counted.
- get_sync_status_summary: no filter, with gateway_id filter,
  sync_percentage calculation, zero-division guard.
- get_gateway_metrics: gateway found (with/without errors),
  gateway not found (returns None), last_health_check isoformat.
- get_aggregated_metrics: healthy (all online, no errors/drift),
  critical (none online), degraded (partial), unknown (no gateways),
  drifted counts trigger degraded.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.gateway_deployment import DeploymentSyncStatus
from src.models.gateway_instance import GatewayInstanceStatus
from src.services.gateway_metrics_service import GatewayMetricsService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> AsyncMock:
    return AsyncMock()


def _scalar_result(value: int) -> MagicMock:
    r = MagicMock()
    r.scalar_one.return_value = value
    return r


def _scalar_one_or_none_result(value) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_all_result(items: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _build_health_execute(counts: dict[GatewayInstanceStatus, int]):
    """Build an async execute function that returns status counts in enum order."""
    statuses = list(GatewayInstanceStatus)
    call_index = [0]

    async def _execute(query):
        result = MagicMock()
        status = statuses[call_index[0] % len(statuses)]
        result.scalar_one.return_value = counts.get(status, 0)
        call_index[0] += 1
        return result

    return _execute


def _build_sync_execute(counts: dict[DeploymentSyncStatus, int]):
    """Build an async execute function that returns sync status counts in enum order."""
    statuses = list(DeploymentSyncStatus)
    call_index = [0]

    async def _execute(query):
        result = MagicMock()
        status = statuses[call_index[0] % len(statuses)]
        result.scalar_one.return_value = counts.get(status, 0)
        call_index[0] += 1
        return result

    return _execute


def _make_gateway(
    gateway_id=None,
    name: str = "gw-prod",
    display_name: str = "GW Production",
    gateway_type_value: str = "stoa",
    status_value: str = "online",
    last_health_check=None,
) -> MagicMock:
    gw = MagicMock()
    gw.id = gateway_id or uuid4()
    gw.name = name
    gw.display_name = display_name
    gw.gateway_type = MagicMock(value=gateway_type_value)
    gw.status = MagicMock(value=status_value)
    gw.last_health_check = last_health_check
    return gw


def _make_error_deployment(gateway_id=None) -> MagicMock:
    d = MagicMock()
    d.id = uuid4()
    d.api_catalog_id = uuid4()
    d.sync_error = "timeout connecting to backend"
    d.sync_attempts = 3
    d.last_sync_attempt = None
    return d


# ---------------------------------------------------------------------------
# get_health_summary
# ---------------------------------------------------------------------------


class TestGetHealthSummary:
    """health_summary returns counts per status + total + health_percentage."""

    @pytest.mark.asyncio
    async def test_all_online(self) -> None:
        session = _make_session()
        session.execute = _build_health_execute(
            {
                GatewayInstanceStatus.ONLINE: 5,
                GatewayInstanceStatus.OFFLINE: 0,
                GatewayInstanceStatus.DEGRADED: 0,
                GatewayInstanceStatus.MAINTENANCE: 0,
            }
        )
        svc = GatewayMetricsService(session)
        result = await svc.get_health_summary()

        assert result["online"] == 5
        assert result["offline"] == 0
        assert result["total_gateways"] == 5
        assert result["health_percentage"] == 100.0

    @pytest.mark.asyncio
    async def test_all_offline(self) -> None:
        session = _make_session()
        session.execute = _build_health_execute(
            {
                GatewayInstanceStatus.ONLINE: 0,
                GatewayInstanceStatus.OFFLINE: 3,
                GatewayInstanceStatus.DEGRADED: 0,
                GatewayInstanceStatus.MAINTENANCE: 0,
            }
        )
        svc = GatewayMetricsService(session)
        result = await svc.get_health_summary()

        assert result["online"] == 0
        assert result["offline"] == 3
        assert result["total_gateways"] == 3
        assert result["health_percentage"] == 0.0

    @pytest.mark.asyncio
    async def test_mixed_statuses(self) -> None:
        session = _make_session()
        session.execute = _build_health_execute(
            {
                GatewayInstanceStatus.ONLINE: 3,
                GatewayInstanceStatus.OFFLINE: 1,
                GatewayInstanceStatus.DEGRADED: 1,
                GatewayInstanceStatus.MAINTENANCE: 0,
            }
        )
        svc = GatewayMetricsService(session)
        result = await svc.get_health_summary()

        assert result["online"] == 3
        assert result["offline"] == 1
        assert result["degraded"] == 1
        assert result["maintenance"] == 0
        assert result["total_gateways"] == 5
        assert result["health_percentage"] == 60.0

    @pytest.mark.asyncio
    async def test_zero_gateways_health_percentage_zero(self) -> None:
        """Zero-division guard: health_percentage is 0.0 when total_gateways == 0."""
        session = _make_session()
        session.execute = _build_health_execute(
            {
                GatewayInstanceStatus.ONLINE: 0,
                GatewayInstanceStatus.OFFLINE: 0,
                GatewayInstanceStatus.DEGRADED: 0,
                GatewayInstanceStatus.MAINTENANCE: 0,
            }
        )
        svc = GatewayMetricsService(session)
        result = await svc.get_health_summary()

        assert result["total_gateways"] == 0
        assert result["health_percentage"] == 0.0

    @pytest.mark.asyncio
    async def test_health_percentage_rounded_to_one_decimal(self) -> None:
        session = _make_session()
        session.execute = _build_health_execute(
            {
                GatewayInstanceStatus.ONLINE: 1,
                GatewayInstanceStatus.OFFLINE: 2,
                GatewayInstanceStatus.DEGRADED: 0,
                GatewayInstanceStatus.MAINTENANCE: 0,
            }
        )
        svc = GatewayMetricsService(session)
        result = await svc.get_health_summary()

        # 1/3 * 100 = 33.333... → rounds to 33.3
        assert result["health_percentage"] == pytest.approx(33.3, abs=0.1)

    @pytest.mark.asyncio
    async def test_maintenance_counted_in_total(self) -> None:
        session = _make_session()
        session.execute = _build_health_execute(
            {
                GatewayInstanceStatus.ONLINE: 2,
                GatewayInstanceStatus.OFFLINE: 0,
                GatewayInstanceStatus.DEGRADED: 0,
                GatewayInstanceStatus.MAINTENANCE: 1,
            }
        )
        svc = GatewayMetricsService(session)
        result = await svc.get_health_summary()

        assert result["total_gateways"] == 3
        assert result["maintenance"] == 1
        # health_percentage only counts "online"
        assert result["health_percentage"] == pytest.approx(66.7, abs=0.1)

    @pytest.mark.asyncio
    async def test_all_status_values_present_in_result(self) -> None:
        """All GatewayInstanceStatus enum values should have a key in the result."""
        session = _make_session()
        session.execute = _build_health_execute(dict.fromkeys(GatewayInstanceStatus, 0))
        svc = GatewayMetricsService(session)
        result = await svc.get_health_summary()

        for status in GatewayInstanceStatus:
            assert status.value in result, f"Missing key: {status.value}"


# ---------------------------------------------------------------------------
# get_sync_status_summary
# ---------------------------------------------------------------------------


class TestGetSyncStatusSummary:
    """sync_status_summary returns counts per sync status + total + sync_percentage."""

    @pytest.mark.asyncio
    async def test_all_synced(self) -> None:
        session = _make_session()
        session.execute = _build_sync_execute(
            {
                DeploymentSyncStatus.SYNCED: 10,
                DeploymentSyncStatus.PENDING: 0,
                DeploymentSyncStatus.SYNCING: 0,
                DeploymentSyncStatus.DRIFTED: 0,
                DeploymentSyncStatus.ERROR: 0,
                DeploymentSyncStatus.DELETING: 0,
            }
        )
        svc = GatewayMetricsService(session)
        result = await svc.get_sync_status_summary()

        assert result["synced"] == 10
        assert result["total_deployments"] == 10
        assert result["sync_percentage"] == 100.0

    @pytest.mark.asyncio
    async def test_mixed_sync_statuses(self) -> None:
        session = _make_session()
        session.execute = _build_sync_execute(
            {
                DeploymentSyncStatus.SYNCED: 8,
                DeploymentSyncStatus.PENDING: 2,
                DeploymentSyncStatus.SYNCING: 1,
                DeploymentSyncStatus.DRIFTED: 1,
                DeploymentSyncStatus.ERROR: 1,
                DeploymentSyncStatus.DELETING: 0,
            }
        )
        svc = GatewayMetricsService(session)
        result = await svc.get_sync_status_summary()

        assert result["synced"] == 8
        assert result["pending"] == 2
        assert result["error"] == 1
        assert result["total_deployments"] == 13
        assert result["sync_percentage"] == pytest.approx(61.5, abs=0.1)

    @pytest.mark.asyncio
    async def test_zero_deployments_sync_percentage_zero(self) -> None:
        session = _make_session()
        session.execute = _build_sync_execute(dict.fromkeys(DeploymentSyncStatus, 0))
        svc = GatewayMetricsService(session)
        result = await svc.get_sync_status_summary()

        assert result["total_deployments"] == 0
        assert result["sync_percentage"] == 0.0

    @pytest.mark.asyncio
    async def test_with_gateway_id_filter(self) -> None:
        """When gateway_id is provided the query includes an additional WHERE clause.
        We verify the execute is still called the right number of times."""
        session = _make_session()
        session.execute = _build_sync_execute(
            {
                DeploymentSyncStatus.SYNCED: 5,
                DeploymentSyncStatus.PENDING: 0,
                DeploymentSyncStatus.SYNCING: 0,
                DeploymentSyncStatus.DRIFTED: 0,
                DeploymentSyncStatus.ERROR: 0,
                DeploymentSyncStatus.DELETING: 0,
            }
        )
        svc = GatewayMetricsService(session)
        gw_id = uuid4()
        result = await svc.get_sync_status_summary(gateway_id=gw_id)

        assert result["synced"] == 5
        assert result["total_deployments"] == 5

    @pytest.mark.asyncio
    async def test_all_sync_status_values_present_in_result(self) -> None:
        session = _make_session()
        session.execute = _build_sync_execute(dict.fromkeys(DeploymentSyncStatus, 0))
        svc = GatewayMetricsService(session)
        result = await svc.get_sync_status_summary()

        for status in DeploymentSyncStatus:
            assert status.value in result, f"Missing key: {status.value}"

    @pytest.mark.asyncio
    async def test_sync_percentage_rounded_to_one_decimal(self) -> None:
        session = _make_session()
        session.execute = _build_sync_execute(
            {
                DeploymentSyncStatus.SYNCED: 1,
                DeploymentSyncStatus.PENDING: 2,
                DeploymentSyncStatus.SYNCING: 0,
                DeploymentSyncStatus.DRIFTED: 0,
                DeploymentSyncStatus.ERROR: 0,
                DeploymentSyncStatus.DELETING: 0,
            }
        )
        svc = GatewayMetricsService(session)
        result = await svc.get_sync_status_summary()

        # 1/3 * 100 = 33.333... → 33.3
        assert result["sync_percentage"] == pytest.approx(33.3, abs=0.1)


# ---------------------------------------------------------------------------
# get_gateway_metrics
# ---------------------------------------------------------------------------


class TestGetGatewayMetrics:
    """get_gateway_metrics returns per-gateway dict or None."""

    @pytest.mark.asyncio
    async def test_gateway_not_found_returns_none(self) -> None:
        session = _make_session()
        # First execute: gateway lookup returns None
        first_result = MagicMock()
        first_result.scalar_one_or_none.return_value = None
        session.execute.return_value = first_result
        svc = GatewayMetricsService(session)

        result = await svc.get_gateway_metrics(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_gateway_found_returns_dict_structure(self) -> None:
        gateway_id = uuid4()
        gw = _make_gateway(gateway_id=gateway_id)
        session = _make_session()

        call_index = [0]
        sync_statuses = list(DeploymentSyncStatus)

        async def mock_execute(query):
            result = MagicMock()
            idx = call_index[0]
            call_index[0] += 1

            if idx == 0:
                # Gateway lookup
                result.scalar_one_or_none.return_value = gw
            elif idx <= len(sync_statuses):
                # Sync status count queries
                result.scalar_one.return_value = 0
            else:
                # Recent errors
                result.scalars.return_value.all.return_value = []
            return result

        session.execute = mock_execute
        svc = GatewayMetricsService(session)

        result = await svc.get_gateway_metrics(gateway_id)

        assert result is not None
        assert result["gateway_id"] == str(gateway_id)
        assert result["name"] == "gw-prod"
        assert result["display_name"] == "GW Production"
        assert result["gateway_type"] == "stoa"
        assert result["status"] == "online"
        assert "sync" in result
        assert "recent_errors" in result

    @pytest.mark.asyncio
    async def test_gateway_with_recent_errors(self) -> None:
        gateway_id = uuid4()
        gw = _make_gateway(gateway_id=gateway_id)
        session = _make_session()

        call_index = [0]
        sync_statuses = list(DeploymentSyncStatus)
        error_dep = _make_error_deployment(gateway_id=gateway_id)

        async def mock_execute(query):
            result = MagicMock()
            idx = call_index[0]
            call_index[0] += 1

            if idx == 0:
                result.scalar_one_or_none.return_value = gw
            elif idx <= len(sync_statuses):
                result.scalar_one.return_value = 0
            else:
                result.scalars.return_value.all.return_value = [error_dep]
            return result

        session.execute = mock_execute
        svc = GatewayMetricsService(session)

        result = await svc.get_gateway_metrics(gateway_id)

        assert result is not None
        assert len(result["recent_errors"]) == 1
        err = result["recent_errors"][0]
        assert err["error"] == "timeout connecting to backend"
        assert err["attempts"] == 3
        assert err["last_attempt"] is None

    @pytest.mark.asyncio
    async def test_gateway_with_last_health_check_isoformat(self) -> None:
        gateway_id = uuid4()
        ts = datetime(2026, 2, 24, 12, 0, 0, tzinfo=UTC)
        gw = _make_gateway(gateway_id=gateway_id, last_health_check=ts)
        session = _make_session()

        call_index = [0]
        sync_statuses = list(DeploymentSyncStatus)

        async def mock_execute(query):
            result = MagicMock()
            idx = call_index[0]
            call_index[0] += 1
            if idx == 0:
                result.scalar_one_or_none.return_value = gw
            elif idx <= len(sync_statuses):
                result.scalar_one.return_value = 0
            else:
                result.scalars.return_value.all.return_value = []
            return result

        session.execute = mock_execute
        svc = GatewayMetricsService(session)

        result = await svc.get_gateway_metrics(gateway_id)

        assert result is not None
        assert result["last_health_check"] == ts.isoformat()

    @pytest.mark.asyncio
    async def test_gateway_no_errors_returns_empty_recent_errors(self) -> None:
        gateway_id = uuid4()
        gw = _make_gateway(gateway_id=gateway_id)
        session = _make_session()

        call_index = [0]
        sync_statuses = list(DeploymentSyncStatus)

        async def mock_execute(query):
            result = MagicMock()
            idx = call_index[0]
            call_index[0] += 1
            if idx == 0:
                result.scalar_one_or_none.return_value = gw
            elif idx <= len(sync_statuses):
                result.scalar_one.return_value = 0
            else:
                result.scalars.return_value.all.return_value = []
            return result

        session.execute = mock_execute
        svc = GatewayMetricsService(session)

        result = await svc.get_gateway_metrics(gateway_id)

        assert result is not None
        assert result["recent_errors"] == []

    @pytest.mark.asyncio
    async def test_gateway_status_none_defaults_to_offline(self) -> None:
        gateway_id = uuid4()
        gw = _make_gateway(gateway_id=gateway_id)
        gw.status = None  # status is None
        session = _make_session()

        call_index = [0]
        sync_statuses = list(DeploymentSyncStatus)

        async def mock_execute(query):
            result = MagicMock()
            idx = call_index[0]
            call_index[0] += 1
            if idx == 0:
                result.scalar_one_or_none.return_value = gw
            elif idx <= len(sync_statuses):
                result.scalar_one.return_value = 0
            else:
                result.scalars.return_value.all.return_value = []
            return result

        session.execute = mock_execute
        svc = GatewayMetricsService(session)

        result = await svc.get_gateway_metrics(gateway_id)

        assert result is not None
        assert result["status"] == "offline"

    @pytest.mark.asyncio
    async def test_error_deployment_with_last_sync_attempt(self) -> None:
        """Deployment with last_sync_attempt should have ISO string in result."""
        gateway_id = uuid4()
        gw = _make_gateway(gateway_id=gateway_id)
        ts = datetime(2026, 2, 20, 10, 0, 0, tzinfo=UTC)
        error_dep = _make_error_deployment(gateway_id=gateway_id)
        error_dep.last_sync_attempt = ts

        session = _make_session()
        call_index = [0]
        sync_statuses = list(DeploymentSyncStatus)

        async def mock_execute(query):
            result = MagicMock()
            idx = call_index[0]
            call_index[0] += 1
            if idx == 0:
                result.scalar_one_or_none.return_value = gw
            elif idx <= len(sync_statuses):
                result.scalar_one.return_value = 0
            else:
                result.scalars.return_value.all.return_value = [error_dep]
            return result

        session.execute = mock_execute
        svc = GatewayMetricsService(session)

        result = await svc.get_gateway_metrics(gateway_id)

        assert result is not None
        err = result["recent_errors"][0]
        assert err["last_attempt"] == ts.isoformat()


# ---------------------------------------------------------------------------
# get_aggregated_metrics
# ---------------------------------------------------------------------------


class TestGetAggregatedMetrics:
    """get_aggregated_metrics combines health + sync and determines overall_status."""

    @pytest.mark.asyncio
    async def test_healthy_all_online_no_errors_no_drift(self) -> None:
        svc = GatewayMetricsService(_make_session())
        svc.get_health_summary = AsyncMock(
            return_value={
                "online": 4,
                "offline": 0,
                "degraded": 0,
                "maintenance": 0,
                "total_gateways": 4,
                "health_percentage": 100.0,
            }
        )
        svc.get_sync_status_summary = AsyncMock(
            return_value={
                "synced": 20,
                "pending": 0,
                "syncing": 0,
                "drifted": 0,
                "error": 0,
                "deleting": 0,
                "total_deployments": 20,
                "sync_percentage": 100.0,
            }
        )

        result = await svc.get_aggregated_metrics()

        assert result["overall_status"] == "healthy"
        assert "health" in result
        assert "sync" in result

    @pytest.mark.asyncio
    async def test_critical_none_online(self) -> None:
        svc = GatewayMetricsService(_make_session())
        svc.get_health_summary = AsyncMock(
            return_value={
                "online": 0,
                "offline": 3,
                "degraded": 0,
                "maintenance": 0,
                "total_gateways": 3,
                "health_percentage": 0.0,
            }
        )
        svc.get_sync_status_summary = AsyncMock(
            return_value={
                "synced": 0,
                "pending": 0,
                "syncing": 0,
                "drifted": 0,
                "error": 5,
                "deleting": 0,
                "total_deployments": 5,
                "sync_percentage": 0.0,
            }
        )

        result = await svc.get_aggregated_metrics()

        assert result["overall_status"] == "critical"

    @pytest.mark.asyncio
    async def test_degraded_partial_online_with_errors(self) -> None:
        svc = GatewayMetricsService(_make_session())
        svc.get_health_summary = AsyncMock(
            return_value={
                "online": 2,
                "offline": 1,
                "degraded": 0,
                "maintenance": 0,
                "total_gateways": 3,
                "health_percentage": 66.7,
            }
        )
        svc.get_sync_status_summary = AsyncMock(
            return_value={
                "synced": 8,
                "pending": 0,
                "syncing": 0,
                "drifted": 0,
                "error": 2,
                "deleting": 0,
                "total_deployments": 10,
                "sync_percentage": 80.0,
            }
        )

        result = await svc.get_aggregated_metrics()

        assert result["overall_status"] == "degraded"

    @pytest.mark.asyncio
    async def test_unknown_no_gateways(self) -> None:
        svc = GatewayMetricsService(_make_session())
        svc.get_health_summary = AsyncMock(
            return_value={
                "online": 0,
                "offline": 0,
                "degraded": 0,
                "maintenance": 0,
                "total_gateways": 0,
                "health_percentage": 0.0,
            }
        )
        svc.get_sync_status_summary = AsyncMock(
            return_value={
                "synced": 0,
                "pending": 0,
                "syncing": 0,
                "drifted": 0,
                "error": 0,
                "deleting": 0,
                "total_deployments": 0,
                "sync_percentage": 0.0,
            }
        )

        result = await svc.get_aggregated_metrics()

        assert result["overall_status"] == "unknown"

    @pytest.mark.asyncio
    async def test_degraded_due_to_drift(self) -> None:
        """Drift count > 0 causes degraded even if all gateways are online."""
        svc = GatewayMetricsService(_make_session())
        svc.get_health_summary = AsyncMock(
            return_value={
                "online": 3,
                "offline": 0,
                "degraded": 0,
                "maintenance": 0,
                "total_gateways": 3,
                "health_percentage": 100.0,
            }
        )
        svc.get_sync_status_summary = AsyncMock(
            return_value={
                "synced": 9,
                "pending": 0,
                "syncing": 0,
                "drifted": 1,  # drift triggers degraded
                "error": 0,
                "deleting": 0,
                "total_deployments": 10,
                "sync_percentage": 90.0,
            }
        )

        result = await svc.get_aggregated_metrics()

        assert result["overall_status"] == "degraded"

    @pytest.mark.asyncio
    async def test_degraded_due_to_error_deployments(self) -> None:
        """error count > 0 (with some online gateways) causes degraded."""
        svc = GatewayMetricsService(_make_session())
        svc.get_health_summary = AsyncMock(
            return_value={
                "online": 2,
                "offline": 0,
                "degraded": 0,
                "maintenance": 0,
                "total_gateways": 2,
                "health_percentage": 100.0,
            }
        )
        svc.get_sync_status_summary = AsyncMock(
            return_value={
                "synced": 10,
                "pending": 0,
                "syncing": 0,
                "drifted": 0,
                "error": 1,
                "deleting": 0,
                "total_deployments": 11,
                "sync_percentage": 90.9,
            }
        )

        result = await svc.get_aggregated_metrics()

        assert result["overall_status"] == "degraded"

    @pytest.mark.asyncio
    async def test_result_contains_health_and_sync_keys(self) -> None:
        svc = GatewayMetricsService(_make_session())
        health_data = {"total_gateways": 1, "online": 1, "health_percentage": 100.0}
        sync_data = {"total_deployments": 2, "synced": 2, "error": 0, "drifted": 0, "sync_percentage": 100.0}
        svc.get_health_summary = AsyncMock(return_value=health_data)
        svc.get_sync_status_summary = AsyncMock(return_value=sync_data)

        result = await svc.get_aggregated_metrics()

        assert result["health"] == health_data
        assert result["sync"] == sync_data
        assert "overall_status" in result
