"""Regression test: webMethods sync_api must be idempotent (CAB-1938).

When an API with the same name + version already exists on the gateway,
sync_api must return the existing resource instead of calling import_api
again (which causes a 500 on webMethods due to duplicate creation).

Root cause: sync_api was the only adapter method without an existence check.
All other methods (upsert_policy, provision_application, upsert_strategy,
upsert_alias) already had this pattern.
"""

from unittest.mock import AsyncMock

import pytest

from src.adapters.webmethods.adapter import WebMethodsGatewayAdapter


def _make_adapter() -> WebMethodsGatewayAdapter:
    adapter = WebMethodsGatewayAdapter.__new__(WebMethodsGatewayAdapter)
    adapter._config = {"base_url": "http://test:5555"}
    adapter._svc = AsyncMock()
    return adapter


@pytest.mark.asyncio
async def test_regression_sync_api_returns_existing_when_api_exists():
    """sync_api must NOT call import_api when an API with same name+version exists."""
    adapter = _make_adapter()
    existing_api = {"id": "wm-api-999", "apiName": "api-beta", "apiVersion": "1.0.0"}
    adapter._svc.list_apis = AsyncMock(return_value=[existing_api])
    adapter._svc.import_api = AsyncMock()

    result = await adapter.sync_api(
        api_spec={"api_name": "api-beta", "version": "1.0.0"},
        tenant_id="free-aech",
    )

    assert result.success is True
    assert result.resource_id == "wm-api-999"
    assert result.data == existing_api
    adapter._svc.import_api.assert_not_awaited()


@pytest.mark.asyncio
async def test_regression_sync_api_creates_when_no_match():
    """sync_api must call import_api when no API with matching name+version exists."""
    adapter = _make_adapter()
    adapter._svc.list_apis = AsyncMock(return_value=[])
    adapter._svc.import_api = AsyncMock(
        return_value={"apiResponse": {"api": {"id": "new-api-1"}}}
    )

    result = await adapter.sync_api(
        api_spec={"apiName": "api-beta", "apiVersion": "1.0.0"},
        tenant_id="free-aech",
    )

    assert result.success is True
    assert result.resource_id == "new-api-1"
    adapter._svc.import_api.assert_awaited_once()


@pytest.mark.asyncio
async def test_regression_sync_api_creates_when_different_version():
    """sync_api must create when same name exists but with a different version."""
    adapter = _make_adapter()
    existing_api = {"id": "wm-old", "apiName": "api-beta", "apiVersion": "0.9.0"}
    adapter._svc.list_apis = AsyncMock(return_value=[existing_api])
    adapter._svc.import_api = AsyncMock(
        return_value={"apiResponse": {"api": {"id": "wm-new"}}}
    )

    result = await adapter.sync_api(
        api_spec={"apiName": "api-beta", "apiVersion": "1.0.0"},
        tenant_id="free-aech",
    )

    assert result.success is True
    assert result.resource_id == "wm-new"
    adapter._svc.import_api.assert_awaited_once()
