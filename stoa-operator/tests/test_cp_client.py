"""Tests for the Control Plane API client."""

import pytest
from src.cp_client import ControlPlaneClient


@pytest.fixture
def client():
    return ControlPlaneClient(base_url="http://localhost:8000", api_key="test-key")


@pytest.mark.asyncio
async def test_connect_creates_client(client):
    await client.connect()
    assert client._client is not None
    assert client._client.headers.get("X-Operator-Key") == "test-key"
    await client.close()


@pytest.mark.asyncio
async def test_close_clears_client(client):
    await client.connect()
    await client.close()
    assert client._client is None


@pytest.mark.asyncio
async def test_client_property_raises_when_not_connected(client):
    with pytest.raises(RuntimeError, match="not connected"):
        _ = client.client


@pytest.mark.asyncio
async def test_connect_without_api_key():
    c = ControlPlaneClient(base_url="http://localhost:8000", api_key="")
    await c.connect()
    assert "X-Operator-Key" not in c._client.headers
    await c.close()


@pytest.mark.asyncio
async def test_register_gateway(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/v1/admin/gateways",
        json={"id": "123", "name": "test-gw"},
    )
    result = await client.register_gateway({"name": "test-gw"})
    assert result["id"] == "123"
    await client.close()


@pytest.mark.asyncio
async def test_get_gateway(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8000/v1/admin/gateways/123",
        json={"id": "123", "name": "test-gw"},
    )
    result = await client.get_gateway("123")
    assert result["name"] == "test-gw"
    await client.close()


@pytest.mark.asyncio
async def test_delete_gateway(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="DELETE",
        url="http://localhost:8000/v1/admin/gateways/123",
        status_code=204,
    )
    await client.delete_gateway("123")
    await client.close()


@pytest.mark.asyncio
async def test_delete_gateway_404_is_success(client, httpx_mock):
    """Deleting a gateway that's already gone should succeed."""
    await client.connect()
    httpx_mock.add_response(
        method="DELETE",
        url="http://localhost:8000/v1/admin/gateways/gone",
        status_code=404,
    )
    await client.delete_gateway("gone")
    await client.close()


@pytest.mark.asyncio
async def test_list_gateways(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8000/v1/admin/gateways",
        json={"items": [{"id": "1"}, {"id": "2"}], "total": 2},
    )
    result = await client.list_gateways()
    assert len(result) == 2
    await client.close()


@pytest.mark.asyncio
async def test_update_gateway(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="PUT",
        url="http://localhost:8000/v1/admin/gateways/123",
        json={"id": "123", "name": "updated-gw"},
    )
    result = await client.update_gateway("123", {"name": "updated-gw"})
    assert result["name"] == "updated-gw"
    await client.close()


@pytest.mark.asyncio
async def test_health_check_gateway(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/v1/admin/gateways/123/health",
        json={"status": "online", "response_time_ms": 42},
    )
    result = await client.health_check_gateway("123")
    assert result["status"] == "online"
    await client.close()


@pytest.mark.asyncio
async def test_get_gateway_by_name_found(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8000/v1/admin/gateways",
        json={"items": [{"id": "1", "name": "kong-prod"}, {"id": "2", "name": "stoa-gw"}]},
    )
    result = await client.get_gateway_by_name("stoa-gw")
    assert result is not None
    assert result["id"] == "2"
    await client.close()


@pytest.mark.asyncio
async def test_get_gateway_by_name_not_found(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8000/v1/admin/gateways",
        json={"items": [{"id": "1", "name": "kong-prod"}]},
    )
    result = await client.get_gateway_by_name("does-not-exist")
    assert result is None
    await client.close()


# --- Deployment methods ---


@pytest.mark.asyncio
async def test_create_deployment(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/v1/admin/deployments",
        json=[{"id": "dep-1", "sync_status": "pending"}],
        status_code=201,
    )
    result = await client.create_deployment("cat-1", ["gw-1"])
    assert result[0]["id"] == "dep-1"
    await client.close()


@pytest.mark.asyncio
async def test_get_deployment(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8000/v1/admin/deployments/dep-1",
        json={"id": "dep-1", "sync_status": "synced"},
    )
    result = await client.get_deployment("dep-1")
    assert result["sync_status"] == "synced"
    await client.close()


@pytest.mark.asyncio
async def test_delete_deployment(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="DELETE",
        url="http://localhost:8000/v1/admin/deployments/dep-1",
        status_code=204,
    )
    await client.delete_deployment("dep-1")
    await client.close()


@pytest.mark.asyncio
async def test_delete_deployment_404_is_success(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="DELETE",
        url="http://localhost:8000/v1/admin/deployments/gone",
        status_code=404,
    )
    await client.delete_deployment("gone")
    await client.close()


@pytest.mark.asyncio
async def test_force_sync_deployment(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/v1/admin/deployments/dep-1/sync",
        json={"id": "dep-1", "sync_status": "pending"},
    )
    result = await client.force_sync_deployment("dep-1")
    assert result["id"] == "dep-1"
    await client.close()


@pytest.mark.asyncio
async def test_get_catalog_entries(client, httpx_mock):
    await client.connect()
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8000/v1/admin/deployments/catalog-entries",
        json=[{"id": "cat-1", "api_name": "petstore", "version": "1.0"}],
    )
    result = await client.get_catalog_entries()
    assert len(result) == 1
    assert result[0]["api_name"] == "petstore"
    await client.close()
