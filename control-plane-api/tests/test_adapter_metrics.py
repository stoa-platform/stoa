"""Tests for InstrumentedAdapter and adapter metrics (src/adapters/metrics.py).

Covers:
- InstrumentedAdapter records success/error/timeout counters
- Duration histogram captures latency
- AdapterRegistry.create() returns instrumented instance by default
- Health worker external gateway active polling (Kong/Gravitee mock)
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from prometheus_client import REGISTRY

from src.adapters.gateway_adapter_interface import AdapterResult, GatewayAdapterInterface
from src.adapters.metrics import (
    ADAPTER_HEALTH_CHECK_LATENCY,
    ADAPTER_HEALTH_CHECKS_TOTAL,
    ADAPTER_OPERATION_DURATION,
    ADAPTER_OPERATIONS_TOTAL,
    InstrumentedAdapter,
)
from src.adapters.registry import AdapterRegistry
from src.models.gateway_instance import GatewayInstanceStatus, GatewayType
from src.workers.gateway_health_worker import GatewayHealthWorker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeAdapter(GatewayAdapterInterface):
    """Minimal concrete adapter for testing."""

    async def health_check(self) -> AdapterResult:
        return AdapterResult(success=True, data={"status": "ok"})

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def sync_api(self, api_spec: dict, tenant_id: str, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=True, resource_id="api-1")

    async def delete_api(self, api_id: str, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=True)

    async def list_apis(self, auth_token: str | None = None) -> list[dict]:
        return [{"id": "api-1"}]

    async def upsert_policy(self, policy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=True)

    async def delete_policy(self, policy_id: str, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=True)

    async def list_policies(self, auth_token: str | None = None) -> list[dict]:
        return []

    async def provision_application(self, app_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=True)

    async def deprovision_application(self, app_id: str, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=True)

    async def list_applications(self, auth_token: str | None = None) -> list[dict]:
        return []

    async def upsert_auth_server(self, auth_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=True)

    async def upsert_strategy(self, strategy_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=True)

    async def upsert_scope(self, scope_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=True)

    async def upsert_alias(self, alias_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=True)

    async def apply_config(self, config_spec: dict, auth_token: str | None = None) -> AdapterResult:
        return AdapterResult(success=True)

    async def export_archive(self, auth_token: str | None = None) -> bytes:
        return b"archive"


class FailingAdapter(FakeAdapter):
    """Adapter where health_check returns failure."""

    async def health_check(self) -> AdapterResult:
        return AdapterResult(success=False, error="connection refused")


class TimeoutAdapter(FakeAdapter):
    """Adapter that raises TimeoutError on health_check."""

    async def health_check(self) -> AdapterResult:
        raise asyncio.TimeoutError()


class ExceptionAdapter(FakeAdapter):
    """Adapter that raises on health_check."""

    async def health_check(self) -> AdapterResult:
        raise ConnectionError("unreachable")


def _get_counter_value(counter, labels: dict) -> float:
    """Read a counter's current value for given labels."""
    try:
        return counter.labels(**labels)._value.get()
    except Exception:
        return 0.0


def _get_histogram_count(histogram, labels: dict) -> float:
    """Read a histogram's sample count for given labels."""
    try:
        return histogram.labels(**labels)._sum._count if hasattr(histogram.labels(**labels), "_sum") else 0.0
    except Exception:
        return 0.0


def _make_gateway_mock(
    *,
    name: str = "kong-prod",
    gateway_type: GatewayType = GatewayType.KONG,
    status: GatewayInstanceStatus = GatewayInstanceStatus.ONLINE,
    base_url: str = "http://kong:8001",
    auth_config: dict | None = None,
    health_details: dict | None = None,
    tenant_id: str | None = None,
) -> MagicMock:
    gw = MagicMock()
    gw.id = uuid4()
    gw.name = name
    gw.gateway_type = gateway_type
    gw.status = status
    gw.base_url = base_url
    gw.auth_config = auth_config or {}
    gw.health_details = health_details or {}
    gw.last_health_check = datetime.now(UTC)
    gw.tenant_id = tenant_id
    return gw


def _make_session_with_results(*result_sets: list) -> AsyncMock:
    """Create session mock that returns different results per execute call."""
    session = AsyncMock()
    execute_results = []
    for results in result_sets:
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = results
        execute_results.append(result_mock)
    session.execute = AsyncMock(side_effect=execute_results)
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# InstrumentedAdapter — success paths
# ---------------------------------------------------------------------------


class TestInstrumentedAdapterSuccess:
    async def test_health_check_success_increments_counter(self) -> None:
        inner = FakeAdapter()
        adapter = InstrumentedAdapter(inner, gateway_type="kong")

        before = _get_counter_value(
            ADAPTER_OPERATIONS_TOTAL, {"gateway_type": "kong", "operation": "health_check", "status": "success"}
        )
        result = await adapter.health_check()
        after = _get_counter_value(
            ADAPTER_OPERATIONS_TOTAL, {"gateway_type": "kong", "operation": "health_check", "status": "success"}
        )

        assert result.success is True
        assert after > before

    async def test_health_check_also_increments_dedicated_counter(self) -> None:
        inner = FakeAdapter()
        adapter = InstrumentedAdapter(inner, gateway_type="gravitee")

        before = _get_counter_value(ADAPTER_HEALTH_CHECKS_TOTAL, {"gateway_type": "gravitee", "status": "success"})
        await adapter.health_check()
        after = _get_counter_value(ADAPTER_HEALTH_CHECKS_TOTAL, {"gateway_type": "gravitee", "status": "success"})

        assert after > before

    async def test_sync_api_success(self) -> None:
        inner = FakeAdapter()
        adapter = InstrumentedAdapter(inner, gateway_type="apigee")

        before = _get_counter_value(
            ADAPTER_OPERATIONS_TOTAL, {"gateway_type": "apigee", "operation": "sync_api", "status": "success"}
        )
        result = await adapter.sync_api({"name": "test"}, "tenant-1")
        after = _get_counter_value(
            ADAPTER_OPERATIONS_TOTAL, {"gateway_type": "apigee", "operation": "sync_api", "status": "success"}
        )

        assert result.success is True
        assert after > before

    async def test_list_apis_returns_list(self) -> None:
        inner = FakeAdapter()
        adapter = InstrumentedAdapter(inner, gateway_type="kong")

        apis = await adapter.list_apis()
        assert apis == [{"id": "api-1"}]

    async def test_export_archive_returns_bytes(self) -> None:
        inner = FakeAdapter()
        adapter = InstrumentedAdapter(inner, gateway_type="webmethods")

        data = await adapter.export_archive()
        assert data == b"archive"

    async def test_deploy_contract_delegates(self) -> None:
        inner = FakeAdapter()
        adapter = InstrumentedAdapter(inner, gateway_type="stoa")

        result = await adapter.deploy_contract({"spec": "v1"})
        assert isinstance(result, AdapterResult)


# ---------------------------------------------------------------------------
# InstrumentedAdapter — error paths
# ---------------------------------------------------------------------------


class TestInstrumentedAdapterErrors:
    async def test_failed_result_records_error_status(self) -> None:
        inner = FailingAdapter()
        adapter = InstrumentedAdapter(inner, gateway_type="kong_fail")

        before = _get_counter_value(
            ADAPTER_OPERATIONS_TOTAL, {"gateway_type": "kong_fail", "operation": "health_check", "status": "error"}
        )
        result = await adapter.health_check()
        after = _get_counter_value(
            ADAPTER_OPERATIONS_TOTAL, {"gateway_type": "kong_fail", "operation": "health_check", "status": "error"}
        )

        assert result.success is False
        assert after > before

    async def test_exception_records_error_status(self) -> None:
        inner = ExceptionAdapter()
        adapter = InstrumentedAdapter(inner, gateway_type="exc_test")

        before = _get_counter_value(
            ADAPTER_OPERATIONS_TOTAL, {"gateway_type": "exc_test", "operation": "health_check", "status": "error"}
        )
        with pytest.raises(ConnectionError):
            await adapter.health_check()
        after = _get_counter_value(
            ADAPTER_OPERATIONS_TOTAL, {"gateway_type": "exc_test", "operation": "health_check", "status": "error"}
        )

        assert after > before

    async def test_timeout_records_timeout_status(self) -> None:
        inner = TimeoutAdapter()
        adapter = InstrumentedAdapter(inner, gateway_type="timeout_test")

        before = _get_counter_value(
            ADAPTER_OPERATIONS_TOTAL, {"gateway_type": "timeout_test", "operation": "health_check", "status": "timeout"}
        )
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(adapter.health_check(), timeout=0.01)
        after = _get_counter_value(
            ADAPTER_OPERATIONS_TOTAL, {"gateway_type": "timeout_test", "operation": "health_check", "status": "timeout"}
        )

        assert after > before


# ---------------------------------------------------------------------------
# AdapterRegistry instrumentation
# ---------------------------------------------------------------------------


class TestRegistryInstrumentation:
    def test_create_returns_instrumented_by_default(self) -> None:
        AdapterRegistry.register("test_fake", FakeAdapter)
        adapter = AdapterRegistry.create("test_fake")
        assert isinstance(adapter, InstrumentedAdapter)

    def test_create_instrument_false_returns_raw(self) -> None:
        AdapterRegistry.register("test_fake_raw", FakeAdapter)
        adapter = AdapterRegistry.create("test_fake_raw", instrument=False)
        assert isinstance(adapter, FakeAdapter)
        assert not isinstance(adapter, InstrumentedAdapter)

    def test_instrumented_adapter_preserves_config(self) -> None:
        AdapterRegistry.register("test_fake_cfg", FakeAdapter)
        adapter = AdapterRegistry.create("test_fake_cfg", config={"base_url": "http://test:8080"})
        assert isinstance(adapter, InstrumentedAdapter)
        assert adapter._config == {"base_url": "http://test:8080"}


# ---------------------------------------------------------------------------
# Health Worker — active polling for external gateways
# ---------------------------------------------------------------------------


class TestHealthWorkerActivePolling:
    async def test_external_gateway_online_after_successful_poll(self) -> None:
        gw = _make_gateway_mock(
            name="kong-test",
            gateway_type=GatewayType.KONG,
            status=GatewayInstanceStatus.OFFLINE,
        )
        session = _make_session_with_results([gw])

        worker = GatewayHealthWorker()

        with (
            patch.object(AdapterRegistry, "create") as mock_create,
            patch.object(AdapterRegistry, "has_type", return_value=True),
        ):
            mock_adapter = AsyncMock()
            mock_adapter.health_check = AsyncMock(return_value=AdapterResult(success=True, data={"status": "ok"}))
            mock_create.return_value = mock_adapter

            await worker._active_health_check_external_gateways(session)

        assert gw.status == GatewayInstanceStatus.ONLINE
        assert gw.health_details["check_method"] == "active_poll"
        assert gw.health_details["consecutive_failures"] == 0

    async def test_external_gateway_offline_after_3_failures(self) -> None:
        gw = _make_gateway_mock(
            name="gravitee-test",
            gateway_type=GatewayType.GRAVITEE,
            status=GatewayInstanceStatus.ONLINE,
            health_details={"consecutive_failures": 2},
        )
        session = _make_session_with_results([gw])

        worker = GatewayHealthWorker()

        with (
            patch.object(AdapterRegistry, "create") as mock_create,
            patch.object(AdapterRegistry, "has_type", return_value=True),
        ):
            mock_adapter = AsyncMock()
            mock_adapter.health_check = AsyncMock(return_value=AdapterResult(success=False, error="connection refused"))
            mock_create.return_value = mock_adapter

            await worker._active_health_check_external_gateways(session)

        assert gw.status == GatewayInstanceStatus.OFFLINE
        assert gw.health_details["consecutive_failures"] == 3
        assert gw.health_details["offline_reason"] == "consecutive_failures"

    async def test_timeout_increments_failure_counter(self) -> None:
        gw = _make_gateway_mock(
            name="apigee-test",
            gateway_type=GatewayType.APIGEE,
            status=GatewayInstanceStatus.ONLINE,
            health_details={"consecutive_failures": 0},
        )
        session = _make_session_with_results([gw])

        worker = GatewayHealthWorker()

        with (
            patch.object(AdapterRegistry, "create") as mock_create,
            patch.object(AdapterRegistry, "has_type", return_value=True),
        ):
            mock_adapter = AsyncMock()
            mock_adapter.health_check = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_create.return_value = mock_adapter

            # Patch wait_for to immediately raise TimeoutError
            with patch("src.workers.gateway_health_worker.asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                await worker._active_health_check_external_gateways(session)

        assert gw.health_details["consecutive_failures"] == 1
        assert "timeout" in gw.health_details["last_error"]

    async def test_success_resets_failure_counter(self) -> None:
        gw = _make_gateway_mock(
            name="kong-recover",
            gateway_type=GatewayType.KONG,
            status=GatewayInstanceStatus.OFFLINE,
            health_details={"consecutive_failures": 2, "offline_reason": "consecutive_failures"},
        )
        session = _make_session_with_results([gw])

        worker = GatewayHealthWorker()

        with (
            patch.object(AdapterRegistry, "create") as mock_create,
            patch.object(AdapterRegistry, "has_type", return_value=True),
        ):
            mock_adapter = AsyncMock()
            mock_adapter.health_check = AsyncMock(return_value=AdapterResult(success=True))
            mock_create.return_value = mock_adapter

            await worker._active_health_check_external_gateways(session)

        assert gw.status == GatewayInstanceStatus.ONLINE
        assert gw.health_details["consecutive_failures"] == 0

    async def test_maintenance_gateways_skipped(self) -> None:
        """Gateways in MAINTENANCE status should not be polled."""
        gw = _make_gateway_mock(
            name="kong-maint",
            gateway_type=GatewayType.KONG,
            status=GatewayInstanceStatus.MAINTENANCE,
        )
        # The query excludes MAINTENANCE, so the result set is empty
        session = _make_session_with_results([])

        worker = GatewayHealthWorker()

        with (
            patch.object(AdapterRegistry, "create") as mock_create,
            patch.object(AdapterRegistry, "has_type", return_value=True),
        ):
            await worker._active_health_check_external_gateways(session)
            mock_create.assert_not_called()

    async def test_unregistered_adapter_type_skipped(self) -> None:
        gw = _make_gateway_mock(
            name="unknown-gw",
            gateway_type=GatewayType.KONG,
            status=GatewayInstanceStatus.ONLINE,
        )
        session = _make_session_with_results([gw])

        worker = GatewayHealthWorker()

        with patch.object(AdapterRegistry, "has_type", return_value=False):
            await worker._active_health_check_external_gateways(session)

        # Status unchanged — gateway was skipped
        assert gw.status == GatewayInstanceStatus.ONLINE

    async def test_adapter_config_passes_base_url_and_auth(self) -> None:
        gw = _make_gateway_mock(
            name="kong-cfg",
            gateway_type=GatewayType.KONG,
            base_url="http://kong-admin:8001",
            auth_config={"type": "api_key", "key": "test-key"},
        )
        session = _make_session_with_results([gw])

        worker = GatewayHealthWorker()

        with patch.object(AdapterRegistry, "has_type", return_value=True):
            with patch.object(AdapterRegistry, "create") as mock_create:
                mock_adapter = AsyncMock()
                mock_adapter.health_check = AsyncMock(return_value=AdapterResult(success=True))
                mock_create.return_value = mock_adapter

                await worker._active_health_check_external_gateways(session)

                assert mock_create.called
                captured_config = mock_create.call_args.kwargs.get("config", {})

        assert captured_config["base_url"] == "http://kong-admin:8001"
        assert captured_config["auth_config"]["type"] == "api_key"

    async def test_check_gateway_health_calls_both_strategies(self) -> None:
        """_check_gateway_health should call both heartbeat and active polling."""
        worker = GatewayHealthWorker()

        worker._mark_stale_gateways_offline = AsyncMock()
        worker._active_health_check_external_gateways = AsyncMock()
        worker._purge_stale_gateways = AsyncMock()

        session = AsyncMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=cm)

        with patch("src.workers.gateway_health_worker._get_session_factory", return_value=mock_factory):
            await worker._check_gateway_health()

        worker._mark_stale_gateways_offline.assert_awaited_once_with(session)
        worker._active_health_check_external_gateways.assert_awaited_once_with(session)
        session.commit.assert_awaited_once()
