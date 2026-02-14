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
    assert client._client.headers.get("X-Gateway-Key") == "test-key"
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
    assert "X-Gateway-Key" not in c._client.headers
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
