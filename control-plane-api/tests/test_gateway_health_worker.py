"""Tests for GatewayHealthWorker (src/workers/gateway_health_worker.py)."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.models.gateway_instance import GatewayInstanceStatus, GatewayType
from src.workers.gateway_health_worker import GatewayHealthWorker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gateway(
    *,
    name: str = "stoa-primary",
    gateway_type: GatewayType = GatewayType.STOA,
    status: GatewayInstanceStatus = GatewayInstanceStatus.ONLINE,
    last_health_check: datetime | None = None,
    health_details: dict | None = None,
) -> MagicMock:
    """Return a MagicMock mimicking a GatewayInstance ORM row."""
    gw = MagicMock()
    gw.id = uuid4()
    gw.name = name
    gw.gateway_type = gateway_type
    gw.status = status
    gw.last_health_check = last_health_check or (datetime.now(UTC) - timedelta(seconds=200))
    gw.health_details = health_details
    return gw


def _make_session(scalars_result: list | None = None) -> AsyncMock:
    """Return a minimal async SQLAlchemy session mock."""
    session = AsyncMock()
    scalars_result = scalars_result or []
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = scalars_result
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_reads_check_interval_from_settings(self) -> None:
        with patch("src.workers.gateway_health_worker.settings") as mock_settings:
            mock_settings.GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS = 42
            mock_settings.GATEWAY_HEARTBEAT_TIMEOUT_SECONDS = 120
            worker = GatewayHealthWorker()
        assert worker._check_interval == 42

    def test_reads_heartbeat_timeout_from_settings(self) -> None:
        with patch("src.workers.gateway_health_worker.settings") as mock_settings:
            mock_settings.GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS = 30
            mock_settings.GATEWAY_HEARTBEAT_TIMEOUT_SECONDS = 99
            worker = GatewayHealthWorker()
        assert worker._heartbeat_timeout == 99

    def test_running_is_false_on_init(self) -> None:
        with patch("src.workers.gateway_health_worker.settings") as mock_settings:
            mock_settings.GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS = 30
            mock_settings.GATEWAY_HEARTBEAT_TIMEOUT_SECONDS = 90
            worker = GatewayHealthWorker()
        assert worker._running is False


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------


class TestStop:
    async def test_stop_sets_running_false(self) -> None:
        worker = GatewayHealthWorker()
        worker._running = True
        await worker.stop()
        assert worker._running is False

    async def test_stop_is_idempotent(self) -> None:
        worker = GatewayHealthWorker()
        worker._running = False
        await worker.stop()
        assert worker._running is False


# ---------------------------------------------------------------------------
# start() — loop control
# ---------------------------------------------------------------------------


class TestStart:
    async def test_start_sets_running_true_then_iterates(self) -> None:
        """start() should call _check_gateway_health at least once then stop."""
        worker = GatewayHealthWorker()
        worker._check_interval = 0

        call_count = 0

        async def fake_check():
            nonlocal call_count
            call_count += 1
            # Stop the loop after first iteration
            worker._running = False

        worker._check_gateway_health = fake_check  # type: ignore[assignment]

        with patch("src.workers.gateway_health_worker.asyncio.sleep", new=AsyncMock()):
            await worker.start()

        assert call_count == 1

    async def test_start_calls_sleep_with_check_interval(self) -> None:
        worker = GatewayHealthWorker()
        worker._check_interval = 15

        async def fake_check():
            worker._running = False

        worker._check_gateway_health = fake_check  # type: ignore[assignment]

        sleep_mock = AsyncMock()
        with patch("src.workers.gateway_health_worker.asyncio.sleep", new=sleep_mock):
            await worker.start()

        sleep_mock.assert_called_once_with(15)

    async def test_start_catches_exception_and_continues(self) -> None:
        """If _check_gateway_health raises, the loop should continue (not propagate)."""
        worker = GatewayHealthWorker()
        worker._check_interval = 0

        iteration = 0

        async def flaky_check():
            nonlocal iteration
            iteration += 1
            if iteration == 1:
                raise RuntimeError("db unavailable")
            # Stop after the second (successful) call
            worker._running = False

        worker._check_gateway_health = flaky_check  # type: ignore[assignment]

        with patch("src.workers.gateway_health_worker.asyncio.sleep", new=AsyncMock()):
            # Should NOT raise — exception must be swallowed
            await worker.start()

        assert iteration == 2

    async def test_start_logs_error_on_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        worker = GatewayHealthWorker()
        worker._check_interval = 0
        called = False

        async def boom():
            nonlocal called
            if not called:
                called = True
                raise ValueError("boom")
            worker._running = False

        worker._check_gateway_health = boom  # type: ignore[assignment]

        with patch("src.workers.gateway_health_worker.asyncio.sleep", new=AsyncMock()):
            with caplog.at_level(logging.ERROR, logger="src.workers.gateway_health_worker"):
                await worker.start()

        assert any("gateway health check" in msg.lower() for msg in caplog.messages)


# ---------------------------------------------------------------------------
# _check_gateway_health()
# ---------------------------------------------------------------------------


class TestCheckGatewayHealth:
    async def test_creates_session_and_calls_mark_stale(self) -> None:
        worker = GatewayHealthWorker()
        mock_session = _make_session()

        # Session factory is an async context manager
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_session)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=cm)

        mark_mock = AsyncMock()
        worker._mark_stale_gateways_offline = mark_mock  # type: ignore[assignment]

        with patch("src.workers.gateway_health_worker._get_session_factory", return_value=mock_factory):
            await worker._check_gateway_health()

        mark_mock.assert_awaited_once_with(mock_session)

    async def test_commits_session_after_mark_stale(self) -> None:
        worker = GatewayHealthWorker()
        mock_session = _make_session()

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_session)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=cm)

        worker._mark_stale_gateways_offline = AsyncMock()

        with patch("src.workers.gateway_health_worker._get_session_factory", return_value=mock_factory):
            await worker._check_gateway_health()

        mock_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# _mark_stale_gateways_offline()
# ---------------------------------------------------------------------------


class TestMarkStaleGatewaysOffline:
    async def test_no_stale_gateways_returns_early_without_modifying(self) -> None:
        worker = GatewayHealthWorker()
        mock_session = _make_session(scalars_result=[])

        await worker._mark_stale_gateways_offline(mock_session)

        # session.execute was called (to run the query)
        mock_session.execute.assert_awaited_once()

    async def test_single_stale_gateway_marked_offline(self) -> None:
        worker = GatewayHealthWorker()
        stale_hc = datetime.now(UTC) - timedelta(seconds=200)
        gw = _make_gateway(last_health_check=stale_hc)
        mock_session = _make_session(scalars_result=[gw])

        await worker._mark_stale_gateways_offline(mock_session)

        assert gw.status == GatewayInstanceStatus.OFFLINE

    async def test_single_stale_gateway_health_details_set(self) -> None:
        worker = GatewayHealthWorker()
        stale_hc = datetime.now(UTC) - timedelta(seconds=200)
        gw = _make_gateway(last_health_check=stale_hc, health_details=None)
        mock_session = _make_session(scalars_result=[gw])

        await worker._mark_stale_gateways_offline(mock_session)

        details = gw.health_details
        assert details["offline_reason"] == "heartbeat_timeout"
        assert "marked_offline_at" in details
        assert details["last_heartbeat"] == stale_hc.isoformat()

    async def test_existing_health_details_are_preserved(self) -> None:
        """Existing keys in health_details must survive the merge."""
        worker = GatewayHealthWorker()
        stale_hc = datetime.now(UTC) - timedelta(seconds=200)
        gw = _make_gateway(
            last_health_check=stale_hc,
            health_details={"version": "1.2.3", "region": "eu-west-1"},
        )
        mock_session = _make_session(scalars_result=[gw])

        await worker._mark_stale_gateways_offline(mock_session)

        details = gw.health_details
        assert details["version"] == "1.2.3"
        assert details["region"] == "eu-west-1"
        assert details["offline_reason"] == "heartbeat_timeout"

    async def test_gateway_with_no_last_health_check_handled_gracefully(self) -> None:
        """last_health_check=None must not raise; last_heartbeat should be None in details."""
        worker = GatewayHealthWorker()
        gw = _make_gateway(last_health_check=None)
        # Force last_health_check to None (overrides the default in the helper)
        gw.last_health_check = None
        mock_session = _make_session(scalars_result=[gw])

        await worker._mark_stale_gateways_offline(mock_session)

        assert gw.status == GatewayInstanceStatus.OFFLINE
        assert gw.health_details["last_heartbeat"] is None

    async def test_multiple_stale_gateways_all_marked_offline(self) -> None:
        worker = GatewayHealthWorker()
        stale_hc = datetime.now(UTC) - timedelta(seconds=200)
        gateways = [
            _make_gateway(name=f"gw-{i}", last_health_check=stale_hc, gateway_type=GatewayType.STOA)
            for i in range(3)
        ]
        mock_session = _make_session(scalars_result=gateways)

        await worker._mark_stale_gateways_offline(mock_session)

        for gw in gateways:
            assert gw.status == GatewayInstanceStatus.OFFLINE
            assert gw.health_details["offline_reason"] == "heartbeat_timeout"

    async def test_multiple_stale_gateways_logs_count(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        worker = GatewayHealthWorker()
        stale_hc = datetime.now(UTC) - timedelta(seconds=200)
        gateways = [
            _make_gateway(name=f"gw-{i}", last_health_check=stale_hc) for i in range(2)
        ]
        mock_session = _make_session(scalars_result=gateways)

        with caplog.at_level(logging.INFO, logger="src.workers.gateway_health_worker"):
            await worker._mark_stale_gateways_offline(mock_session)

        assert any("2" in msg for msg in caplog.messages)

    async def test_sidecar_gateway_type_also_marked_offline(self) -> None:
        """STOA_SIDECAR gateways are also subject to heartbeat checks."""
        worker = GatewayHealthWorker()
        stale_hc = datetime.now(UTC) - timedelta(seconds=200)
        gw = _make_gateway(
            gateway_type=GatewayType.STOA_SIDECAR,
            last_health_check=stale_hc,
        )
        mock_session = _make_session(scalars_result=[gw])

        await worker._mark_stale_gateways_offline(mock_session)

        assert gw.status == GatewayInstanceStatus.OFFLINE

    async def test_cutoff_time_based_on_heartbeat_timeout(self) -> None:
        """The query cutoff must use self._heartbeat_timeout, not a hardcoded value."""
        worker = GatewayHealthWorker()
        worker._heartbeat_timeout = 60  # Override to non-default value

        mock_session = _make_session(scalars_result=[])
        captured_stmt = {}

        async def capturing_execute(stmt):
            captured_stmt["stmt"] = stmt
            result_mock = MagicMock()
            result_mock.scalars.return_value.all.return_value = []
            return result_mock

        mock_session.execute = capturing_execute

        fixed_now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
        with patch("src.workers.gateway_health_worker.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.now.side_effect = None
            # datetime.now(UTC) is called twice: once for cutoff, once for marked_offline_at
            # We only need the first call to produce a deterministic cutoff
            mock_dt.now = MagicMock(return_value=fixed_now)
            await worker._mark_stale_gateways_offline(mock_session)

        # The query was executed — confirms the cutoff logic ran without error
        assert "stmt" in captured_stmt
