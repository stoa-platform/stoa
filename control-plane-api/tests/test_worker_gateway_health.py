"""Tests for GatewayHealthWorker (CAB-1388)."""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.workers.gateway_health_worker import GatewayHealthWorker
from src.models.gateway_instance import GatewayInstanceStatus


def _mock_gateway(**kwargs):
    g = MagicMock()
    g.id = kwargs.get("id", "gw-001")
    g.name = kwargs.get("name", "test-gw")
    g.status = kwargs.get("status", GatewayInstanceStatus.ONLINE)
    g.last_health_check = kwargs.get("last_health_check", datetime.now(UTC) - timedelta(seconds=200))
    g.health_details = kwargs.get("health_details", {})
    return g


class TestGatewayHealthWorkerLifecycle:
    def test_initial_state(self):
        with patch("src.workers.gateway_health_worker.settings") as mock_settings:
            mock_settings.GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS = 30
            mock_settings.GATEWAY_HEARTBEAT_TIMEOUT_SECONDS = 90
            worker = GatewayHealthWorker()
            assert worker._running is False

    async def test_stop_sets_running_false(self):
        with patch("src.workers.gateway_health_worker.settings") as mock_settings:
            mock_settings.GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS = 30
            mock_settings.GATEWAY_HEARTBEAT_TIMEOUT_SECONDS = 90
            worker = GatewayHealthWorker()
            worker._running = True
            await worker.stop()
            assert worker._running is False


class TestMarkStaleGatewaysOffline:
    async def test_no_stale_gateways_returns_early(self):
        with patch("src.workers.gateway_health_worker.settings") as mock_settings:
            mock_settings.GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS = 30
            mock_settings.GATEWAY_HEARTBEAT_TIMEOUT_SECONDS = 90
            worker = GatewayHealthWorker()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        await worker._mark_stale_gateways_offline(session)
        # execute was called once (the query)
        session.execute.assert_called_once()

    async def test_marks_stale_gateways_offline(self):
        with patch("src.workers.gateway_health_worker.settings") as mock_settings:
            mock_settings.GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS = 30
            mock_settings.GATEWAY_HEARTBEAT_TIMEOUT_SECONDS = 90
            worker = GatewayHealthWorker()

        gw = _mock_gateway()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [gw]
        session.execute = AsyncMock(return_value=mock_result)

        await worker._mark_stale_gateways_offline(session)

        assert gw.status == GatewayInstanceStatus.OFFLINE
        assert gw.health_details.get("offline_reason") == "heartbeat_timeout"

    async def test_marks_multiple_stale_gateways(self):
        with patch("src.workers.gateway_health_worker.settings") as mock_settings:
            mock_settings.GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS = 30
            mock_settings.GATEWAY_HEARTBEAT_TIMEOUT_SECONDS = 90
            worker = GatewayHealthWorker()

        gw1 = _mock_gateway(name="gw-1")
        gw2 = _mock_gateway(name="gw-2", last_health_check=None)
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [gw1, gw2]
        session.execute = AsyncMock(return_value=mock_result)

        await worker._mark_stale_gateways_offline(session)

        assert gw1.status == GatewayInstanceStatus.OFFLINE
        assert gw2.status == GatewayInstanceStatus.OFFLINE


class TestCheckGatewayHealth:
    async def test_calls_mark_stale_and_commits(self):
        with patch("src.workers.gateway_health_worker.settings") as mock_settings:
            mock_settings.GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS = 30
            mock_settings.GATEWAY_HEARTBEAT_TIMEOUT_SECONDS = 90
            worker = GatewayHealthWorker()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        factory = MagicMock(return_value=mock_cm)

        with patch("src.workers.gateway_health_worker._get_session_factory", return_value=factory):
            await worker._check_gateway_health()

        session.commit.assert_called_once()
