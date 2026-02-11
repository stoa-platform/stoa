"""Tests for Kong Gateway adapter (DB-less mode)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.kong.adapter import KongGatewayAdapter
from src.adapters.kong.mappers import map_api_spec_to_kong_service, map_kong_service_to_cp

# --- Mapper tests ---


class TestKongMappers:
    def test_map_api_spec_to_kong_service(self):
        spec = {
            "api_name": "orders-api",
            "backend_url": "https://api.example.com/orders",
            "methods": ["GET", "POST"],
        }
        result = map_api_spec_to_kong_service(spec, "acme")

        assert result["name"] == "acme-orders-api"
        assert result["url"] == "https://api.example.com/orders"
        assert result["routes"][0]["paths"] == ["/apis/acme/orders-api"]
        assert result["routes"][0]["methods"] == ["GET", "POST"]
        assert result["routes"][0]["strip_path"] is True

    def test_map_api_spec_defaults(self):
        spec = {"apiName": "default-api", "url": "http://backend:8080"}
        result = map_api_spec_to_kong_service(spec, "tenant1")

        assert result["name"] == "tenant1-default-api"
        assert result["url"] == "http://backend:8080"
        assert result["routes"][0]["methods"] == ["GET", "POST", "PUT", "DELETE"]

    def test_map_kong_service_to_cp(self):
        service = {
            "id": "abc-123",
            "name": "acme-orders-api",
            "host": "api.example.com",
            "port": 443,
            "protocol": "https",
            "enabled": True,
        }
        result = map_kong_service_to_cp(service)

        assert result["id"] == "abc-123"
        assert result["name"] == "acme-orders-api"
        assert result["host"] == "api.example.com"
        assert result["port"] == 443


# --- Adapter tests ---


class TestKongAdapterInit:
    def test_init_defaults(self):
        adapter = KongGatewayAdapter()
        assert adapter._base_url == "http://localhost:8001"
        assert adapter._api_key == ""

    def test_init_with_config(self):
        adapter = KongGatewayAdapter(
            config={
                "base_url": "http://kong:8001",
                "auth_config": {"api_key": "secret"},
            }
        )
        assert adapter._base_url == "http://kong:8001"
        assert adapter._api_key == "secret"

    def test_auth_headers_empty(self):
        adapter = KongGatewayAdapter()
        assert adapter._auth_headers() == {}

    def test_auth_headers_with_key(self):
        adapter = KongGatewayAdapter(
            config={"auth_config": {"api_key": "my-key"}},
        )
        headers = adapter._auth_headers()
        assert headers["Kong-Admin-Token"] == "my-key"


class TestKongAdapterLifecycle:
    @pytest.mark.asyncio
    async def test_connect_creates_client(self):
        adapter = KongGatewayAdapter(config={"base_url": "http://kong:8001"})
        assert adapter._client is None

        with patch("src.adapters.kong.adapter.httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            await adapter.connect()
            assert adapter._client is mock_client

    @pytest.mark.asyncio
    async def test_disconnect_closes_client(self):
        adapter = KongGatewayAdapter()
        mock_client = AsyncMock()
        adapter._client = mock_client
        await adapter.disconnect()
        mock_client.aclose.assert_awaited_once()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_disconnect_noop_when_no_client(self):
        adapter = KongGatewayAdapter()
        await adapter.disconnect()


class TestKongAdapterHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        adapter = KongGatewayAdapter(config={"base_url": "http://kong:8001"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "database": {"reachable": True},
            "server": {"connections_active": 5},
            "version": "3.9.0",
        }

        with patch("src.adapters.kong.adapter.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            result = await adapter.health_check()

        assert result.success is True
        assert result.data["database_reachable"] is True
        assert result.data["connections_active"] == 5
        assert result.data["version"] == "3.9.0"

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        adapter = KongGatewayAdapter(config={"base_url": "http://kong:8001"})
        mock_resp = MagicMock()
        mock_resp.status_code = 503

        with patch("src.adapters.kong.adapter.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            result = await adapter.health_check()

        assert result.success is False
        assert "503" in result.error

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self):
        adapter = KongGatewayAdapter(config={"base_url": "http://kong:8001"})

        with patch("src.adapters.kong.adapter.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
            mock_cls.return_value = mock_client

            result = await adapter.health_check()

        assert result.success is False


class TestKongAdapterAPIs:
    def _make_adapter(self):
        adapter = KongGatewayAdapter(config={"base_url": "http://kong:8001"})
        mock_client = AsyncMock()
        adapter._client = mock_client
        return adapter, mock_client

    @pytest.mark.asyncio
    async def test_sync_api_success(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {}
        client.post = AsyncMock(return_value=mock_resp)

        result = await adapter.sync_api(
            {"api_name": "test", "backend_url": "http://backend"},
            tenant_id="acme",
        )

        assert result.success is True
        assert result.resource_id == "acme-test"
        client.post.assert_awaited_once()
        call_args = client.post.call_args
        assert call_args[0][0] == "/config"

    @pytest.mark.asyncio
    async def test_sync_api_failure(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "bad config"
        client.post = AsyncMock(return_value=mock_resp)

        result = await adapter.sync_api(
            {"api_name": "test", "backend_url": "http://backend"},
            tenant_id="acme",
        )

        assert result.success is False
        assert "400" in result.error

    @pytest.mark.asyncio
    async def test_list_apis(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"id": "s1", "name": "svc1", "host": "h1", "port": 80, "protocol": "http", "enabled": True},
                {"id": "s2", "name": "svc2", "host": "h2", "port": 443, "protocol": "https", "enabled": True},
            ],
        }
        client.get = AsyncMock(return_value=mock_resp)

        apis = await adapter.list_apis()

        assert len(apis) == 2
        assert apis[0]["name"] == "svc1"
        assert apis[1]["port"] == 443

    @pytest.mark.asyncio
    async def test_delete_api_dbless(self):
        adapter = KongGatewayAdapter()
        result = await adapter.delete_api("some-id")
        assert result.success is True
        assert result.resource_id == "some-id"


class TestKongAdapterUnsupported:
    @pytest.mark.asyncio
    async def test_unsupported_methods(self):
        adapter = KongGatewayAdapter()

        r = await adapter.upsert_policy({})
        assert r.success is False

        r = await adapter.delete_policy("p1")
        assert r.success is False

        assert await adapter.list_policies() == []

        r = await adapter.provision_application({})
        assert r.success is False

        r = await adapter.deprovision_application("a1")
        assert r.success is False

        assert await adapter.list_applications() == []

        r = await adapter.upsert_auth_server({})
        assert r.success is False

        r = await adapter.upsert_strategy({})
        assert r.success is False

        r = await adapter.upsert_scope({})
        assert r.success is False

        r = await adapter.upsert_alias({})
        assert r.success is False

        r = await adapter.apply_config({})
        assert r.success is False

        assert await adapter.export_archive() == b""


class TestKongRegistration:
    def test_kong_registered(self):
        from src.adapters.registry import AdapterRegistry

        assert AdapterRegistry.has_type("kong") is True
        adapter = AdapterRegistry.create("kong", config={"base_url": "http://test:8001"})
        assert isinstance(adapter, KongGatewayAdapter)
