# CAB-2225 SUB-1 deprovision retry regression tests.
# Guards the retry loop for gateway route removal.
#
# regression for CAB-2225
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.adapters.gateway_adapter_interface import AdapterResult
from src.models.subscription import ProvisioningStatus
from src.services.provisioning_service import MAX_RETRIES, _deprovision_with_session, deprovision_on_revocation


class _Subscription:
    def __init__(self, *, gateway_app_id: str | None = "gw-app-1") -> None:
        object.__setattr__(self, "provisioning_status_writes", [])
        self.id = uuid4()
        self.api_id = "api-weather"
        self.tenant_id = "tenant-acme"
        self.gateway_app_id = gateway_app_id
        self.provisioning_error = None
        self.provisioning_status = ProvisioningStatus.READY
        self.provisioning_status_writes.clear()

    def __setattr__(self, name: str, value: object) -> None:
        if name == "provisioning_status":
            self.provisioning_status_writes.append(value)
        object.__setattr__(self, name, value)


def _adapter_with_deprovision(*results: AdapterResult) -> AsyncMock:
    adapter = AsyncMock()
    adapter.delete_policy = AsyncMock(return_value=AdapterResult(success=True))
    adapter.deprovision_application = AsyncMock(side_effect=list(results))
    return adapter


@pytest.mark.asyncio
async def test_deprovision_retries_then_succeeds(mock_db_session) -> None:
    sub = _Subscription()
    adapter = _adapter_with_deprovision(
        AdapterResult(success=False, error="transient"),
        AdapterResult(success=False, error="transient"),
        AdapterResult(success=True, resource_id="gw-app-1"),
    )

    with (
        patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
        patch("src.services.provisioning_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        await _deprovision_with_session(mock_db_session, sub, "token", "corr-sub-1")

    assert sub.provisioning_status == ProvisioningStatus.DEPROVISIONED
    assert adapter.deprovision_application.await_count == 3
    assert ProvisioningStatus.DEPROVISIONING_FAILED not in sub.provisioning_status_writes


@pytest.mark.asyncio
async def test_deprovision_retries_exhausted_marks_deprovisioning_failed(mock_db_session) -> None:
    sub = _Subscription()
    adapter = _adapter_with_deprovision(*[AdapterResult(success=False, error="transient") for _ in range(MAX_RETRIES)])

    with (
        patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
        patch("src.services.provisioning_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        await _deprovision_with_session(mock_db_session, sub, "token", "corr-sub-1")

    assert sub.provisioning_status == ProvisioningStatus.DEPROVISIONING_FAILED
    assert f"Deprovision failed after {MAX_RETRIES} attempts" in sub.provisioning_error
    assert adapter.deprovision_application.await_count == MAX_RETRIES


@pytest.mark.asyncio
async def test_deprovision_logs_ops_alert_on_exhaustion(mock_db_session, caplog) -> None:
    sub = _Subscription()
    adapter = _adapter_with_deprovision(*[AdapterResult(success=False, error="transient") for _ in range(MAX_RETRIES)])
    caplog.set_level(logging.ERROR, logger="src.services.provisioning_service")

    with (
        patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
        patch("src.services.provisioning_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        await _deprovision_with_session(mock_db_session, sub, "token", "corr-sub-1")

    record = next(record for record in caplog.records if getattr(record, "ops_alert", None) == "deprovision_failed")
    assert record.correlation_id == "corr-sub-1"
    assert record.tenant_id == "tenant-acme"
    assert record.subscription_id == str(sub.id)
    assert record.ops_alert == "deprovision_failed"


@pytest.mark.asyncio
async def test_deprovision_no_gateway_app_id_is_noop(mock_db_session) -> None:
    sub = _Subscription(gateway_app_id=None)

    with patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock) as resolve_adapter:
        await deprovision_on_revocation(mock_db_session, sub, "token", "corr-sub-1")

    resolve_adapter.assert_not_awaited()
    mock_db_session.commit.assert_not_awaited()
    assert sub.provisioning_status == ProvisioningStatus.READY
