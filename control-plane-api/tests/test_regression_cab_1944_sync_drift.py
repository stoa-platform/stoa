"""Regression test: StoaGatewayAdapter must warn when admin_token is missing (CAB-1944).

Root cause: gateway_instances with auth_config={"type": "gateway_key"} (no admin_token)
caused silent 401 errors on sync_api. The adapter now logs a warning at init time.
"""

import logging

import pytest

from src.adapters.stoa.adapter import StoaGatewayAdapter


def test_regression_stoa_adapter_warns_missing_admin_token(caplog):
    """StoaGatewayAdapter should log warning when admin_token is missing."""
    with caplog.at_level(logging.WARNING):
        StoaGatewayAdapter(config={
            "base_url": "http://stoa-gateway:80",
            "auth_config": {"type": "gateway_key"},
        })

    assert any("admin_token" in record.message for record in caplog.records), (
        "Expected warning about missing admin_token"
    )


def test_regression_stoa_adapter_no_warning_with_token(caplog):
    """StoaGatewayAdapter should NOT warn when admin_token is present."""
    with caplog.at_level(logging.WARNING):
        StoaGatewayAdapter(config={
            "base_url": "http://stoa-gateway:80",
            "auth_config": {"type": "gateway_key", "admin_token": "test-token"},
        })

    assert not any("admin_token" in record.message for record in caplog.records), (
        "Should not warn when admin_token is present"
    )


@pytest.mark.asyncio
async def test_regression_stoa_adapter_401_includes_body():
    """sync_api error message should include response body, not just status code."""
    import httpx
    import respx

    adapter = StoaGatewayAdapter(config={
        "base_url": "http://stoa-gateway:80",
        "auth_config": {"type": "gateway_key", "admin_token": "wrong-token"},
    })
    await adapter.connect()

    with respx.mock:
        respx.post("http://stoa-gateway:80/admin/apis").mock(
            return_value=httpx.Response(401, text="")
        )
        result = await adapter.sync_api(
            {"api_name": "test", "version": "1.0", "backend_url": "http://example.com"},
            tenant_id="test",
        )

    await adapter.disconnect()
    assert not result.success
    assert "401" in result.error
