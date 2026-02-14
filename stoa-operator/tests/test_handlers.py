"""Tests for kopf handlers — GatewayInstance and GatewayBinding."""

from unittest.mock import AsyncMock, patch

import httpx
import kopf
import pytest
from src.handlers.gateway_binding import (
    on_gwb_create,
    on_gwb_delete,
    on_gwb_resume,
    on_gwb_update,
)
from src.handlers.gateway_instance import (
    on_gwi_create,
    on_gwi_delete,
    on_gwi_resume,
    on_gwi_update,
)


class FakePatch:
    """Mimics kopf.Patch for testing status writes."""

    def __init__(self):
        self.status = {}


# --- GatewayInstance tests ---


@pytest.mark.asyncio
@patch("src.handlers.gateway_instance.cp_client")
async def test_gwi_create_registers_gateway(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.register_gateway = AsyncMock(return_value={"id": "gw-123"})
    mock_cp.health_check_gateway = AsyncMock(return_value={"status": "online"})

    patch = FakePatch()
    spec = {"gatewayType": "kong", "baseUrl": "http://kong:8001"}
    result = await on_gwi_create(spec=spec, name="kong-prod", namespace="stoa-system", patch=patch)

    assert patch.status["cpGatewayId"] == "gw-123"
    assert patch.status["phase"] == "online"
    assert patch.status["error"] == ""
    assert "registered" in result["message"]
    mock_cp.register_gateway.assert_awaited_once()


@pytest.mark.asyncio
@patch("src.handlers.gateway_instance.cp_client")
async def test_gwi_create_sets_offline_on_health_failure(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.register_gateway = AsyncMock(return_value={"id": "gw-456"})
    mock_cp.health_check_gateway = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("POST", "http://test"),
            response=httpx.Response(404),
        )
    )

    patch = FakePatch()
    spec = {"gatewayType": "stoa", "baseUrl": "http://gw:8080"}
    await on_gwi_create(spec=spec, name="stoa-gw", namespace="stoa-system", patch=patch)

    assert patch.status["cpGatewayId"] == "gw-456"
    assert patch.status["phase"] == "offline"


@pytest.mark.asyncio
@patch("src.handlers.gateway_instance.cp_client")
async def test_gwi_create_retries_on_api_error(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.register_gateway = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("POST", "http://test"),
            response=httpx.Response(500, text="Internal Server Error"),
        )
    )

    patch = FakePatch()
    spec = {"gatewayType": "kong", "baseUrl": "http://kong:8001"}
    with pytest.raises(kopf.TemporaryError):
        await on_gwi_create(spec=spec, name="kong-prod", namespace="stoa-system", patch=patch)
    assert patch.status["phase"] == "error"


@pytest.mark.asyncio
@patch("src.handlers.gateway_instance.cp_client")
async def test_gwi_update_calls_api(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.update_gateway = AsyncMock(return_value={"id": "gw-123"})
    mock_cp.health_check_gateway = AsyncMock(return_value={"status": "online"})

    patch = FakePatch()
    old_spec = {"gatewayType": "kong", "baseUrl": "http://kong:8001"}
    new_spec = {**old_spec, "baseUrl": "http://kong:8002"}
    result = await on_gwi_update(
        spec=new_spec,
        old={"spec": old_spec},
        new={"spec": new_spec},
        name="kong-prod",
        namespace="stoa-system",
        status={"cpGatewayId": "gw-123"},
        diff=[],
        patch=patch,
    )

    assert "updated" in result["message"]
    mock_cp.update_gateway.assert_awaited_once_with(
        "gw-123",
        {
            "name": "kong-prod",
            "display_name": "kong-prod",
            "gateway_type": "kong",
            "base_url": "http://kong:8002",
            "environment": "dev",
            "mode": "edge-mcp",
        },
    )


@pytest.mark.asyncio
@patch("src.handlers.gateway_instance.cp_client")
async def test_gwi_update_skips_non_spec_change(mock_cp):
    patch = FakePatch()
    spec = {"gatewayType": "kong", "baseUrl": "http://kong:8001"}
    result = await on_gwi_update(
        spec=spec,
        old={"spec": spec},
        new={"spec": spec},
        name="kong-prod",
        namespace="stoa-system",
        status={"cpGatewayId": "gw-123"},
        diff=[],
        patch=patch,
    )
    assert "skipped" in result["message"]
    mock_cp.connect.assert_not_called()


@pytest.mark.asyncio
@patch("src.handlers.gateway_instance.cp_client")
async def test_gwi_update_retries_without_id(mock_cp):
    patch = FakePatch()
    old_spec = {"gatewayType": "kong", "baseUrl": "http://kong:8001"}
    new_spec = {**old_spec, "baseUrl": "http://kong:8002"}
    with pytest.raises(kopf.TemporaryError, match="Missing cpGatewayId"):
        await on_gwi_update(
            spec=new_spec,
            old={"spec": old_spec},
            new={"spec": new_spec},
            name="kong-prod",
            namespace="stoa-system",
            status={},
            diff=[],
            patch=patch,
        )


@pytest.mark.asyncio
@patch("src.handlers.gateway_instance.cp_client")
async def test_gwi_delete_calls_api(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.delete_gateway = AsyncMock()

    spec = {"gatewayType": "stoa", "baseUrl": "http://gw:8080"}
    await on_gwi_delete(
        spec=spec,
        name="stoa-gw",
        namespace="stoa-system",
        status={"cpGatewayId": "gw-789"},
    )
    mock_cp.delete_gateway.assert_awaited_once_with("gw-789")


@pytest.mark.asyncio
@patch("src.handlers.gateway_instance.cp_client")
async def test_gwi_delete_noop_without_id(mock_cp):
    spec = {"gatewayType": "stoa", "baseUrl": "http://gw:8080"}
    await on_gwi_delete(
        spec=spec,
        name="stoa-gw",
        namespace="stoa-system",
        status={},
    )
    mock_cp.connect.assert_not_called()


@pytest.mark.asyncio
@patch("src.handlers.gateway_instance.cp_client")
async def test_gwi_resume_health_checks(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.get_gateway = AsyncMock(return_value={"id": "gw-123"})
    mock_cp.health_check_gateway = AsyncMock(return_value={"status": "online"})

    patch = FakePatch()
    spec = {"gatewayType": "stoa", "baseUrl": "http://gw:8080"}
    await on_gwi_resume(
        spec=spec,
        status={"phase": "offline", "cpGatewayId": "gw-123"},
        name="stoa-gw",
        namespace="stoa-system",
        patch=patch,
    )
    assert patch.status["phase"] == "online"
    mock_cp.health_check_gateway.assert_awaited_once()


@pytest.mark.asyncio
@patch("src.handlers.gateway_instance.cp_client")
async def test_gwi_resume_reregisters_on_404(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.get_gateway = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(404),
        )
    )
    mock_cp.register_gateway = AsyncMock(return_value={"id": "gw-new"})
    mock_cp.health_check_gateway = AsyncMock(return_value={"status": "offline"})

    patch = FakePatch()
    spec = {"gatewayType": "stoa", "baseUrl": "http://gw:8080"}
    await on_gwi_resume(
        spec=spec,
        status={"phase": "online", "cpGatewayId": "gw-old"},
        name="stoa-gw",
        namespace="stoa-system",
        patch=patch,
    )
    assert patch.status["cpGatewayId"] == "gw-new"
    mock_cp.register_gateway.assert_awaited_once()


@pytest.mark.asyncio
@patch("src.handlers.gateway_instance.cp_client")
async def test_gwi_resume_registers_when_no_id(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.register_gateway = AsyncMock(return_value={"id": "gw-fresh"})

    patch = FakePatch()
    spec = {"gatewayType": "stoa", "baseUrl": "http://gw:8080"}
    await on_gwi_resume(
        spec=spec,
        status={},
        name="stoa-gw",
        namespace="stoa-system",
        patch=patch,
    )
    assert patch.status["cpGatewayId"] == "gw-fresh"
    assert patch.status["phase"] == "offline"


# --- GatewayBinding tests ---


@pytest.mark.asyncio
@patch("src.handlers.gateway_binding.cp_client")
async def test_gwb_create_deploys_api(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.get_gateway_by_name = AsyncMock(return_value={"id": "gw-1", "name": "kong-prod"})
    mock_cp.get_catalog_entries = AsyncMock(return_value=[{"id": "cat-1", "api_name": "petstore"}])
    mock_cp.create_deployment = AsyncMock(return_value=[{"id": "dep-1"}])

    patch = FakePatch()
    spec = {"apiRef": {"name": "petstore"}, "gatewayRef": {"name": "kong-prod"}}
    result = await on_gwb_create(
        spec=spec, name="petstore-kong", namespace="stoa-system", patch=patch
    )

    assert patch.status["gatewayResourceId"] == "dep-1"
    assert patch.status["syncStatus"] == "synced"
    assert "deployed" in result["message"]
    mock_cp.create_deployment.assert_awaited_once_with("cat-1", ["gw-1"])


@pytest.mark.asyncio
@patch("src.handlers.gateway_binding.cp_client")
async def test_gwb_create_retries_when_gateway_not_found(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.get_gateway_by_name = AsyncMock(return_value=None)

    patch = FakePatch()
    spec = {"apiRef": {"name": "petstore"}, "gatewayRef": {"name": "missing-gw"}}
    with pytest.raises(kopf.TemporaryError, match="not found"):
        await on_gwb_create(
            spec=spec, name="petstore-missing", namespace="stoa-system", patch=patch
        )


@pytest.mark.asyncio
@patch("src.handlers.gateway_binding.cp_client")
async def test_gwb_create_fails_when_api_not_in_catalog(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.get_gateway_by_name = AsyncMock(return_value={"id": "gw-1", "name": "kong-prod"})
    mock_cp.get_catalog_entries = AsyncMock(return_value=[])

    patch = FakePatch()
    spec = {"apiRef": {"name": "nonexistent"}, "gatewayRef": {"name": "kong-prod"}}
    with pytest.raises(kopf.PermanentError, match="not found in catalog"):
        await on_gwb_create(
            spec=spec, name="nonexistent-kong", namespace="stoa-system", patch=patch
        )


@pytest.mark.asyncio
@patch("src.handlers.gateway_binding.cp_client")
async def test_gwb_update_triggers_sync(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.force_sync_deployment = AsyncMock(return_value={"id": "dep-1"})

    patch = FakePatch()
    old_spec = {"apiRef": {"name": "petstore"}, "gatewayRef": {"name": "kong-prod"}}
    new_spec = {"apiRef": {"name": "petstore-v2"}, "gatewayRef": {"name": "kong-prod"}}
    result = await on_gwb_update(
        spec=new_spec,
        old={"spec": old_spec},
        new={"spec": new_spec},
        name="petstore-kong",
        namespace="stoa-system",
        status={"gatewayResourceId": "dep-1", "syncAttempts": 1},
        diff=[],
        patch=patch,
    )
    assert patch.status["syncStatus"] == "synced"
    assert "re-synced" in result["message"]
    mock_cp.force_sync_deployment.assert_awaited_once_with("dep-1")


@pytest.mark.asyncio
@patch("src.handlers.gateway_binding.cp_client")
async def test_gwb_update_skips_non_spec_change(mock_cp):
    patch = FakePatch()
    spec = {"apiRef": {"name": "petstore"}, "gatewayRef": {"name": "kong-prod"}}
    result = await on_gwb_update(
        spec=spec,
        old={"spec": spec, "metadata": {"labels": {}}},
        new={"spec": spec, "metadata": {"labels": {"new": "label"}}},
        name="petstore-kong",
        namespace="stoa-system",
        status={"gatewayResourceId": "dep-1"},
        diff=[],
        patch=patch,
    )
    assert "skipped" in result["message"]
    mock_cp.connect.assert_not_called()


@pytest.mark.asyncio
@patch("src.handlers.gateway_binding.cp_client")
async def test_gwb_delete_calls_api(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.delete_deployment = AsyncMock()

    spec = {"apiRef": {"name": "petstore"}, "gatewayRef": {"name": "kong-prod"}}
    await on_gwb_delete(
        spec=spec,
        name="petstore-kong",
        namespace="stoa-system",
        status={"gatewayResourceId": "dep-1"},
    )
    mock_cp.delete_deployment.assert_awaited_once_with("dep-1")


@pytest.mark.asyncio
@patch("src.handlers.gateway_binding.cp_client")
async def test_gwb_delete_noop_without_id(mock_cp):
    spec = {"apiRef": {"name": "petstore"}, "gatewayRef": {"name": "kong-prod"}}
    await on_gwb_delete(
        spec=spec,
        name="petstore-kong",
        namespace="stoa-system",
        status={},
    )
    mock_cp.connect.assert_not_called()


@pytest.mark.asyncio
@patch("src.handlers.gateway_binding.cp_client")
async def test_gwb_resume_verifies_deployment(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.get_deployment = AsyncMock(return_value={"id": "dep-1", "sync_status": "synced"})

    patch = FakePatch()
    spec = {"apiRef": {"name": "petstore"}, "gatewayRef": {"name": "kong-prod"}}
    await on_gwb_resume(
        spec=spec,
        status={"syncStatus": "pending", "gatewayResourceId": "dep-1"},
        name="petstore-kong",
        namespace="stoa-system",
        patch=patch,
    )
    assert patch.status["syncStatus"] == "synced"
    mock_cp.get_deployment.assert_awaited_once_with("dep-1")


@pytest.mark.asyncio
@patch("src.handlers.gateway_binding.cp_client")
async def test_gwb_resume_recreates_on_404(mock_cp):
    mock_cp.connect = AsyncMock()
    mock_cp.close = AsyncMock()
    mock_cp.get_deployment = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(404),
        )
    )
    mock_cp.get_gateway_by_name = AsyncMock(return_value={"id": "gw-1", "name": "kong-prod"})
    mock_cp.get_catalog_entries = AsyncMock(return_value=[{"id": "cat-1", "api_name": "petstore"}])
    mock_cp.create_deployment = AsyncMock(return_value=[{"id": "dep-new"}])

    patch = FakePatch()
    spec = {"apiRef": {"name": "petstore"}, "gatewayRef": {"name": "kong-prod"}}
    await on_gwb_resume(
        spec=spec,
        status={"syncStatus": "synced", "gatewayResourceId": "dep-old"},
        name="petstore-kong",
        namespace="stoa-system",
        patch=patch,
    )
    assert patch.status["gatewayResourceId"] == "dep-new"
    assert patch.status["syncStatus"] == "synced"
    mock_cp.create_deployment.assert_awaited_once()
