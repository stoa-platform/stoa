"""Tests for Gravitee APIM adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.gravitee.adapter import GraviteeGatewayAdapter
from src.adapters.gravitee.mappers import map_api_spec_to_gravitee_v4, map_gravitee_api_to_cp

# --- Mapper tests ---


class TestGraviteeMappers:
    def test_map_api_spec_to_gravitee_v4(self):
        spec = {
            "api_name": "payments-api",
            "backend_url": "https://payments.example.com",
        }
        result = map_api_spec_to_gravitee_v4(spec, "acme")

        assert result["name"] == "acme-payments-api"
        assert result["definitionVersion"] == "V4"
        assert result["type"] == "PROXY"
        assert result["listeners"][0]["paths"][0]["path"] == "/apis/acme/payments-api"
        target = result["endpointGroups"][0]["endpoints"][0]["configuration"]["target"]
        assert target == "https://payments.example.com"

    def test_map_gravitee_api_to_cp(self):
        api = {
            "id": "grav-123",
            "name": "acme-api",
            "state": "STARTED",
            "visibility": "PUBLIC",
            "definitionVersion": "V4",
            "deployedAt": "2026-02-11T10:00:00Z",
        }
        result = map_gravitee_api_to_cp(api)

        assert result["id"] == "grav-123"
        assert result["name"] == "acme-api"
        assert result["state"] == "STARTED"
        assert result["definition_version"] == "V4"


# --- Adapter tests ---


class TestGraviteeAdapterInit:
    def test_init_defaults(self):
        adapter = GraviteeGatewayAdapter()
        assert adapter._base_url == "http://localhost:8083"
        assert adapter._username == "admin"
        assert adapter._password == "admin"

    def test_init_with_config(self):
        adapter = GraviteeGatewayAdapter(
            config={
                "base_url": "http://gravitee:8083",
                "auth_config": {"username": "user", "password": "pass"},
            }
        )
        assert adapter._base_url == "http://gravitee:8083"
        assert adapter._username == "user"
        assert adapter._password == "pass"

    def test_auth_headers_basic(self):
        adapter = GraviteeGatewayAdapter(
            config={"auth_config": {"username": "admin", "password": "admin"}},
        )
        headers = adapter._auth_headers()
        assert headers["Authorization"].startswith("Basic ")
        assert headers["Content-Type"] == "application/json"


class TestGraviteeAdapterLifecycle:
    @pytest.mark.asyncio
    async def test_connect_creates_client(self):
        adapter = GraviteeGatewayAdapter(config={"base_url": "http://gravitee:8083"})
        assert adapter._client is None

        with patch("src.adapters.gravitee.adapter.httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            await adapter.connect()
            assert adapter._client is mock_client

    @pytest.mark.asyncio
    async def test_disconnect_closes_client(self):
        adapter = GraviteeGatewayAdapter()
        mock_client = AsyncMock()
        adapter._client = mock_client
        await adapter.disconnect()
        mock_client.aclose.assert_awaited_once()
        assert adapter._client is None


class TestGraviteeAdapterHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        adapter = GraviteeGatewayAdapter(config={"base_url": "http://gravitee:8083"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "name": "DEFAULT",
            "organizationId": "DEFAULT",
        }

        with patch("src.adapters.gravitee.adapter.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            result = await adapter.health_check()

        assert result.success is True
        assert result.data["environment"] == "DEFAULT"

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        adapter = GraviteeGatewayAdapter(config={"base_url": "http://gravitee:8083"})
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("src.adapters.gravitee.adapter.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            result = await adapter.health_check()

        assert result.success is False
        assert "500" in result.error

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self):
        adapter = GraviteeGatewayAdapter(config={"base_url": "http://gravitee:8083"})

        with patch("src.adapters.gravitee.adapter.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
            mock_cls.return_value = mock_client

            result = await adapter.health_check()

        assert result.success is False


class TestGraviteeAdapterAPIs:
    def _make_adapter(self):
        adapter = GraviteeGatewayAdapter(config={"base_url": "http://gravitee:8083"})
        mock_client = AsyncMock()
        adapter._client = mock_client
        return adapter, mock_client

    @pytest.mark.asyncio
    async def test_sync_api_success(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "new-api-id", "name": "acme-test"}
        client.post = AsyncMock(return_value=mock_resp)

        result = await adapter.sync_api(
            {"api_name": "test", "backend_url": "http://backend"},
            tenant_id="acme",
        )

        assert result.success is True
        assert result.resource_id == "new-api-id"
        client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sync_api_failure(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "bad request"
        client.post = AsyncMock(return_value=mock_resp)

        result = await adapter.sync_api(
            {"api_name": "test", "backend_url": "http://backend"},
            tenant_id="acme",
        )

        assert result.success is False
        assert "400" in result.error

    @pytest.mark.asyncio
    async def test_delete_api_success(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        client.delete = AsyncMock(return_value=mock_resp)

        result = await adapter.delete_api("api-123")

        assert result.success is True
        assert result.resource_id == "api-123"

    @pytest.mark.asyncio
    async def test_delete_api_not_found_idempotent(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client.delete = AsyncMock(return_value=mock_resp)

        result = await adapter.delete_api("gone")

        assert result.success is True

    @pytest.mark.asyncio
    async def test_list_apis(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": "a1",
                    "name": "api1",
                    "state": "STARTED",
                    "visibility": "PUBLIC",
                    "definitionVersion": "V4",
                },
            ]
        }
        client.get = AsyncMock(return_value=mock_resp)

        apis = await adapter.list_apis()

        assert len(apis) == 1
        assert apis[0]["name"] == "api1"

    @pytest.mark.asyncio
    async def test_list_apis_empty(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}
        client.get = AsyncMock(return_value=mock_resp)

        apis = await adapter.list_apis()
        assert apis == []


class TestGraviteeAdapterUnsupported:
    @pytest.mark.asyncio
    async def test_unsupported_methods(self):
        adapter = GraviteeGatewayAdapter()

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


class TestGraviteeRegistration:
    def test_gravitee_registered(self):
        from src.adapters.registry import AdapterRegistry

        assert AdapterRegistry.has_type("gravitee") is True
        adapter = AdapterRegistry.create("gravitee", config={"base_url": "http://test:8083"})
        assert isinstance(adapter, GraviteeGatewayAdapter)
