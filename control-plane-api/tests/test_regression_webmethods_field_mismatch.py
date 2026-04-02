"""Regression test: webMethods adapter sync_api must accept snake_case fields.

The deployment orchestration service (build_desired_state) produces snake_case
field names (api_name, version, openapi_spec) while the webMethods adapter
originally expected camelCase (apiName, apiVersion, apiDefinition). This caused
a KeyError on every deployment attempt through the webMethods adapter.

All other adapters (Kong, STOA, Gravitee, Apigee, AWS, Azure) already handled
both formats via their mappers.
"""

import pytest
from unittest.mock import AsyncMock

from src.adapters.webmethods.adapter import WebMethodsGatewayAdapter


def _make_adapter() -> WebMethodsGatewayAdapter:
    adapter = WebMethodsGatewayAdapter.__new__(WebMethodsGatewayAdapter)
    adapter._config = {"base_url": "http://test:5555"}
    adapter._svc = AsyncMock()
    return adapter


@pytest.mark.asyncio
async def test_regression_webmethods_sync_api_snake_case_desired_state():
    """sync_api must not KeyError when given snake_case fields from build_desired_state."""
    adapter = _make_adapter()
    adapter._svc.list_apis = AsyncMock(return_value=[])
    adapter._svc.import_api = AsyncMock(
        return_value={"apiResponse": {"api": {"id": "api-123"}}}
    )

    # This is the exact shape produced by GatewayDeploymentService.build_desired_state()
    desired_state = {
        "spec_hash": "abc123",
        "version": "1.0.7",
        "api_name": "api-test-swagger-petstore",
        "api_id": "api-test-swagger-petstore",
        "api_catalog_id": "6a832576-507f-4a15-9ad7-9901bdcb643a",
        "tenant_id": "free-aech",
        "backend_url": "https://petstore.swagger.io/v2",
        "methods": ["DELETE", "GET", "POST", "PUT"],
        "activated": True,
        "openapi_spec": {"openapi": "3.0.0", "info": {"title": "Petstore"}},
    }

    result = await adapter.sync_api(desired_state, tenant_id="free-aech")

    assert result.success is True
    assert result.resource_id == "api-123"
    adapter._svc.import_api.assert_awaited_once()
    call_kwargs = adapter._svc.import_api.call_args[1]
    assert call_kwargs["api_name"] == "api-test-swagger-petstore"
    assert call_kwargs["api_version"] == "1.0.7"
    assert call_kwargs["openapi_spec"] == desired_state["openapi_spec"]
    assert call_kwargs["openapi_url"] is None  # spec takes precedence over URL
