"""Tests for Apigee X Gateway Adapter."""

import httpx
import pytest

from src.adapters.apigee import mappers
from src.adapters.apigee.adapter import ApigeeGatewayAdapter

# === Mapper Tests ===


class TestMapApiSpecToApigeeProxy:
    def test_basic_mapping(self) -> None:
        spec = {
            "id": "api-1",
            "name": "weather-api",
            "display_name": "Weather API",
            "description": "Provides weather data",
            "base_path": "/weather",
            "target_url": "https://api.weather.com",
        }
        result = mappers.map_api_spec_to_apigee_proxy(spec, "acme")
        assert result["name"] == "stoa-acme-weather-api"
        assert result["displayName"] == "Weather API"
        assert result["basePath"] == "/weather"
        assert result["targetUrl"] == "https://api.weather.com"
        assert result["labels"]["stoa-managed"] == "true"
        assert result["labels"]["stoa-tenant"] == "acme"
        assert result["labels"]["stoa-api-id"] == "api-1"

    def test_name_sanitization(self) -> None:
        spec = {"name": "My Cool API", "id": "x"}
        result = mappers.map_api_spec_to_apigee_proxy(spec, "ACME Corp")
        assert " " not in result["name"]
        assert result["name"] == "stoa-acme-corp-my-cool-api"  # lowered + spaces replaced

    def test_defaults(self) -> None:
        result = mappers.map_api_spec_to_apigee_proxy({}, "t1")
        assert result["name"] == "stoa-t1-unnamed-api"
        assert result["basePath"] == "/unnamed-api"


class TestMapApigeeProxyToCp:
    def test_with_labels(self) -> None:
        proxy = {
            "name": "stoa-acme-weather",
            "displayName": "Weather API",
            "description": "Weather data",
            "basePath": "/weather",
            "labels": {
                "stoa-api-id": "api-1",
                "stoa-tenant": "acme",
            },
            "metaData": {
                "createdAt": "2026-01-01",
                "lastModifiedAt": "2026-02-01",
            },
        }
        result = mappers.map_apigee_proxy_to_cp(proxy)
        assert result["id"] == "api-1"
        assert result["display_name"] == "Weather API"
        assert result["gateway_type"] == "apigee"
        assert result["created_at"] == "2026-01-01"

    def test_without_labels(self) -> None:
        proxy = {"name": "bare-proxy"}
        result = mappers.map_apigee_proxy_to_cp(proxy)
        assert result["id"] == "bare-proxy"
        assert result["name"] == "bare-proxy"


class TestPolicyMappers:
    def test_rate_limit_to_product(self) -> None:
        spec = {
            "id": "pol-1",
            "name": "Rate Limit 100/min",
            "type": "rate_limit",
            "config": {"max_requests": 100, "window_seconds": 60},
        }
        result = mappers.map_policy_to_apigee_product(spec, "acme")
        assert result["name"] == "stoa-rate_limit-pol-1"
        assert result["quota"] == "100"
        assert result["quotaInterval"] == "60"
        assert result["quotaTimeUnit"] == "minute"
        attrs = {a["name"]: a["value"] for a in result["attributes"]}
        assert attrs["stoa-managed"] == "true"
        assert attrs["stoa-policy-id"] == "pol-1"

    def test_product_to_policy(self) -> None:
        product = {
            "name": "stoa-rate_limit-pol-1",
            "displayName": "Rate Limit",
            "description": "100/min",
            "quota": "100",
            "quotaInterval": "60",
            "attributes": [
                {"name": "stoa-managed", "value": "true"},
                {"name": "stoa-policy-id", "value": "pol-1"},
            ],
        }
        result = mappers.map_apigee_product_to_policy(product)
        assert result["id"] == "pol-1"
        assert result["config"]["max_requests"] == 100
        assert result["gateway_type"] == "apigee"


# === Adapter Tests (mock httpx) ===


@pytest.fixture
def adapter() -> ApigeeGatewayAdapter:
    return ApigeeGatewayAdapter(
        config={
            "organization": "my-org",
            "base_url": "https://apigee.googleapis.com",
            "auth_config": {"bearer_token": "test-token"},
        }
    )


class TestAdapterInit:
    def test_default_config(self) -> None:
        a = ApigeeGatewayAdapter()
        assert a._org == ""
        assert "apigee.googleapis.com" in a._base_url

    def test_custom_config(self, adapter: ApigeeGatewayAdapter) -> None:
        assert adapter._org == "my-org"
        assert "my-org" in adapter._base_url
        assert adapter._bearer_token == "test-token"

    def test_auth_headers(self, adapter: ApigeeGatewayAdapter) -> None:
        headers = adapter._auth_headers()
        assert headers["Authorization"] == "Bearer test-token"


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=["env-1", "env-2"]))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.health_check()
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_unhealthy(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(401, text="Unauthorized"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.health_check()
        assert result.success is False
        assert "401" in (result.error or "")
        await adapter.disconnect()


class TestSyncApi:
    @pytest.mark.asyncio
    async def test_create_new(self, adapter: ApigeeGatewayAdapter) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "GET":
                return httpx.Response(404)
            return httpx.Response(201, json={"name": "stoa-acme-test"})

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.sync_api({"name": "test", "id": "a1"}, "acme")
        assert result.success is True
        assert result.resource_id == "stoa-acme-test"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_not_connected(self, adapter: ApigeeGatewayAdapter) -> None:
        result = await adapter.sync_api({"name": "test"}, "acme")
        assert result.success is False
        assert "Not connected" in (result.error or "")


class TestDeleteApi:
    @pytest.mark.asyncio
    async def test_delete_success(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(200))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_api("stoa-acme-test")
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_idempotent_404(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(404))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_api("nonexistent")
        assert result.success is True
        await adapter.disconnect()


class TestListApis:
    @pytest.mark.asyncio
    async def test_list(self, adapter: ApigeeGatewayAdapter) -> None:
        proxies = {
            "proxies": [
                {"name": "api-1", "displayName": "API 1", "labels": {}},
                {"name": "api-2", "displayName": "API 2", "labels": {}},
            ]
        }
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=proxies))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_apis()
        assert len(result) == 2
        assert result[0]["name"] == "api-1"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_list_empty(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json={"proxies": []}))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_apis()
        assert result == []
        await adapter.disconnect()


class TestUpsertPolicy:
    @pytest.mark.asyncio
    async def test_create_product(self, adapter: ApigeeGatewayAdapter) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "GET":
                return httpx.Response(404)
            return httpx.Response(201, json={"name": "stoa-rate_limit-p1"})

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.upsert_policy(
            {
                "id": "p1",
                "type": "rate_limit",
                "tenant_id": "acme",
                "config": {"max_requests": 50, "window_seconds": 60},
            }
        )
        assert result.success is True
        assert result.resource_id == "stoa-rate_limit-p1"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_update_product(self, adapter: ApigeeGatewayAdapter) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "GET":
                return httpx.Response(200, json={"name": "existing"})
            return httpx.Response(200, json={"name": "stoa-rate_limit-p1"})

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.upsert_policy({"id": "p1", "type": "rate_limit", "tenant_id": "acme"})
        assert result.success is True
        await adapter.disconnect()


class TestListPolicies:
    @pytest.mark.asyncio
    async def test_filters_stoa_managed(self, adapter: ApigeeGatewayAdapter) -> None:
        data = {
            "apiProduct": [
                {
                    "name": "stoa-rate_limit-p1",
                    "displayName": "Rate 100",
                    "description": "",
                    "quota": "100",
                    "quotaInterval": "60",
                    "attributes": [
                        {"name": "stoa-managed", "value": "true"},
                        {"name": "stoa-policy-id", "value": "p1"},
                    ],
                },
                {
                    "name": "external-product",
                    "attributes": [{"name": "vendor", "value": "other"}],
                },
            ]
        }
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=data))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_policies()
        assert len(result) == 1
        assert result[0]["id"] == "p1"
        await adapter.disconnect()


class TestConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_creates_client(self, adapter: ApigeeGatewayAdapter) -> None:
        assert adapter._client is None
        await adapter.connect()
        assert adapter._client is not None
        await adapter.disconnect()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_disconnect_noop_when_not_connected(self, adapter: ApigeeGatewayAdapter) -> None:
        await adapter.disconnect()  # Should not raise


class TestRegistry:
    def test_apigee_registered(self) -> None:
        from src.adapters.registry import AdapterRegistry

        assert AdapterRegistry.has_type("apigee")
        instance = AdapterRegistry.create("apigee", {"organization": "test"})
        assert isinstance(instance, ApigeeGatewayAdapter)
