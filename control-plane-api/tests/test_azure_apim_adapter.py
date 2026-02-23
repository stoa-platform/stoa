"""Tests for Azure API Management Adapter."""

import httpx
import pytest

from src.adapters.azure import mappers
from src.adapters.azure.adapter import AzureApimAdapter

# === Mapper Tests ===


class TestMapApiSpecToAzure:
    def test_basic_mapping(self) -> None:
        spec = {
            "id": "api-1",
            "name": "weather-api",
            "description": "Provides weather data",
            "backend_url": "https://api.weather.example.com",
            "path": "/weather",
        }
        result = mappers.map_api_spec_to_azure(spec, "acme")
        assert result["_stoa_api_id"] == "stoa-acme-weather-api"
        assert result["properties"]["displayName"] == "weather-api"
        assert result["properties"]["description"] == "Provides weather data"
        assert result["properties"]["serviceUrl"] == "https://api.weather.example.com"
        assert result["properties"]["path"] == "/weather"
        assert result["properties"]["protocols"] == ["https"]
        assert result["_stoa_metadata"]["stoa-managed"] == "true"
        assert result["_stoa_metadata"]["stoa-tenant"] == "acme"
        assert result["_stoa_metadata"]["stoa-api-id"] == "api-1"

    def test_name_sanitization(self) -> None:
        spec = {"name": "My Cool API", "id": "x"}
        result = mappers.map_api_spec_to_azure(spec, "ACME Corp")
        assert " " not in result["_stoa_api_id"]
        assert result["_stoa_api_id"] == "stoa-acme-corp-my-cool-api"

    def test_defaults(self) -> None:
        result = mappers.map_api_spec_to_azure({}, "t1")
        assert result["_stoa_api_id"] == "stoa-t1-unnamed-api"
        assert result["properties"]["protocols"] == ["https"]
        assert result["properties"]["description"] == ""
        assert result["properties"]["serviceUrl"] == "https://httpbin.org"

    def test_custom_protocols(self) -> None:
        spec = {"name": "dual-api", "protocols": ["http", "https"]}
        result = mappers.map_api_spec_to_azure(spec, "t1")
        assert result["properties"]["protocols"] == ["http", "https"]

    def test_display_name_override(self) -> None:
        spec = {"name": "api-v2", "display_name": "Weather API v2"}
        result = mappers.map_api_spec_to_azure(spec, "t1")
        assert result["properties"]["displayName"] == "Weather API v2"


class TestMapAzureApiToCp:
    def test_with_properties(self) -> None:
        api = {
            "id": "/subscriptions/.../apis/stoa-acme-weather",
            "name": "stoa-acme-weather",
            "properties": {
                "displayName": "Weather API",
                "description": "Weather data",
                "path": "/weather",
                "serviceUrl": "https://api.weather.example.com",
            },
        }
        result = mappers.map_azure_api_to_cp(api)
        assert result["id"] == "stoa-acme-weather"
        assert result["name"] == "Weather API"
        assert result["display_name"] == "Weather API"
        assert result["gateway_type"] == "azure_apim"
        assert result["path"] == "/weather"
        assert result["service_url"] == "https://api.weather.example.com"

    def test_without_properties(self) -> None:
        api = {"name": "bare-api"}
        result = mappers.map_azure_api_to_cp(api)
        assert result["id"] == "bare-api"
        assert result["name"] == "bare-api"
        assert result["gateway_type"] == "azure_apim"


class TestPolicyMappers:
    def test_rate_limit_to_product(self) -> None:
        spec = {
            "id": "pol-1",
            "name": "Rate Limit 100/min",
            "type": "rate_limit",
            "config": {"max_requests": 100, "window_seconds": 60},
        }
        result = mappers.map_policy_to_azure_product(spec, "acme")
        assert result["_stoa_product_id"] == "stoa-pol-1"
        assert result["properties"]["displayName"] == "Rate Limit 100/min"
        assert result["properties"]["subscriptionRequired"] is True
        assert result["properties"]["state"] == "published"
        assert result["_stoa_rate_limit"]["calls"] == 100
        assert result["_stoa_rate_limit"]["renewal_period"] == 60
        assert result["_stoa_metadata"]["stoa-managed"] == "true"
        assert result["_stoa_metadata"]["stoa-policy-id"] == "pol-1"

    def test_product_to_policy(self) -> None:
        product = {
            "id": "/subscriptions/.../products/stoa-pol-1",
            "name": "stoa-pol-1",
            "properties": {
                "displayName": "Rate Limit 100/min",
                "description": "100 req/min",
            },
        }
        result = mappers.map_azure_product_to_policy(product)
        assert result["id"] == "pol-1"
        assert result["name"] == "Rate Limit 100/min"
        assert result["type"] == "rate_limit"
        assert result["gateway_type"] == "azure_apim"

    def test_product_id_extraction(self) -> None:
        product = {"name": "stoa-rate-limit-gold", "properties": {}}
        result = mappers.map_azure_product_to_policy(product)
        assert result["id"] == "rate-limit-gold"

    def test_product_without_stoa_prefix(self) -> None:
        product = {"name": "external-product", "properties": {}}
        result = mappers.map_azure_product_to_policy(product)
        assert result["id"] == "external-product"


class TestAppMappers:
    def test_app_spec_to_subscription(self) -> None:
        spec = {
            "id": "app-1",
            "name": "Weather Client",
            "subscription_id": "sub-42",
        }
        result = mappers.map_app_spec_to_azure_subscription(spec, "acme")
        assert result["_stoa_subscription_name"] == "stoa-acme-weather-client"
        assert result["properties"]["displayName"] == "Weather Client"
        assert result["properties"]["state"] == "active"
        assert result["_stoa_metadata"]["stoa-managed"] == "true"
        assert result["_stoa_metadata"]["stoa-app-id"] == "app-1"

    def test_subscription_to_cp(self) -> None:
        sub = {
            "id": "/subscriptions/.../subscriptions/stoa-acme-app",
            "name": "stoa-acme-app",
            "properties": {
                "displayName": "Weather Client",
                "state": "active",
                "createdDate": "2026-02-23",
            },
        }
        result = mappers.map_azure_subscription_to_cp(sub)
        assert result["id"] == "stoa-acme-app"
        assert result["name"] == "Weather Client"
        assert result["gateway_type"] == "azure_apim"
        assert result["state"] == "active"
        assert result["created_at"] == "2026-02-23"

    def test_subscription_without_properties(self) -> None:
        sub = {"name": "bare-sub"}
        result = mappers.map_azure_subscription_to_cp(sub)
        assert result["id"] == "bare-sub"
        assert result["state"] == ""


class TestBuildRateLimitPolicyXml:
    def test_basic_policy(self) -> None:
        xml = mappers.build_rate_limit_policy_xml(100, 60)
        assert '<rate-limit calls="100" renewal-period="60" />' in xml
        assert "<policies>" in xml
        assert "<inbound>" in xml
        assert "<base />" in xml


# === Adapter Tests (mock httpx) ===

_TEST_CONFIG = {
    "subscription_id": "sub-12345",
    "resource_group": "rg-stoa",
    "service_name": "stoa-apim",
    "auth_config": {"bearer_token": "test-bearer-token"},
    "base_url": "https://management.azure.com",
}


@pytest.fixture
def adapter() -> AzureApimAdapter:
    return AzureApimAdapter(config=_TEST_CONFIG)


class TestAdapterInit:
    def test_default_config(self) -> None:
        a = AzureApimAdapter()
        assert a._subscription_id == ""
        assert a._base_url == "https://management.azure.com"

    def test_custom_config(self, adapter: AzureApimAdapter) -> None:
        assert adapter._subscription_id == "sub-12345"
        assert adapter._resource_group == "rg-stoa"
        assert adapter._service_name == "stoa-apim"
        assert adapter._bearer_token == "test-bearer-token"

    def test_custom_base_url(self) -> None:
        a = AzureApimAdapter(config={"base_url": "https://management.usgovcloudapi.net"})
        assert a._base_url == "https://management.usgovcloudapi.net"

    def test_service_path(self, adapter: AzureApimAdapter) -> None:
        assert "/subscriptions/sub-12345" in adapter._service_path
        assert "/resourceGroups/rg-stoa" in adapter._service_path
        assert "/service/stoa-apim" in adapter._service_path


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self, adapter: AzureApimAdapter) -> None:
        resp_data = {
            "location": "westeurope",
            "sku": {"name": "Developer"},
        }
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=resp_data))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.health_check()
        assert result.success is True
        assert result.data is not None
        assert result.data["service_name"] == "stoa-apim"
        assert result.data["location"] == "westeurope"
        assert result.data["sku"] == "Developer"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_unhealthy(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(401, text="Unauthorized"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.health_check()
        assert result.success is False
        assert "401" in (result.error or "")
        await adapter.disconnect()


class TestSyncApi:
    @pytest.mark.asyncio
    async def test_create_or_update(self, adapter: AzureApimAdapter) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "PUT" and "/apis/" in str(req.url):
                return httpx.Response(201, json={"name": "stoa-acme-test", "properties": {"displayName": "test"}})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.sync_api({"name": "test", "id": "a1"}, "acme")
        assert result.success is True
        assert result.resource_id == "stoa-acme-test"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_api_error(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(500, text="Internal Server Error"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.sync_api({"name": "test"}, "acme")
        assert result.success is False
        assert "500" in (result.error or "")
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_request_includes_api_version(self, adapter: AzureApimAdapter) -> None:
        captured_url = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured_url["url"] = str(req.url)
            return httpx.Response(201, json={"name": "stoa-t1-test"})

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        await adapter.sync_api({"name": "test"}, "t1")
        assert "api-version=" in captured_url["url"]
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_request_includes_bearer_token(self, adapter: AzureApimAdapter) -> None:
        captured_headers: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(req.headers))
            return httpx.Response(201, json={"name": "stoa-t1-test"})

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        await adapter.sync_api({"name": "test"}, "t1")
        assert captured_headers.get("authorization") == "Bearer test-bearer-token"
        await adapter.disconnect()


class TestDeleteApi:
    @pytest.mark.asyncio
    async def test_delete_success(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(204))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_api("stoa-acme-test")
        assert result.success is True
        assert result.resource_id == "stoa-acme-test"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_idempotent_404(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(404))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_api("nonexistent")
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_sends_if_match(self, adapter: AzureApimAdapter) -> None:
        captured_headers: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(req.headers))
            return httpx.Response(204)

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        await adapter.delete_api("stoa-acme-test")
        assert captured_headers.get("if-match") == "*"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_failure(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(409, text="Conflict"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_api("api-locked")
        assert result.success is False
        assert "409" in (result.error or "")
        await adapter.disconnect()


class TestListApis:
    @pytest.mark.asyncio
    async def test_list_filters_stoa_managed(self, adapter: AzureApimAdapter) -> None:
        data = {
            "value": [
                {
                    "name": "stoa-acme-weather",
                    "properties": {
                        "displayName": "Weather API",
                        "description": "Weather",
                        "path": "/weather",
                    },
                },
                {
                    "name": "external-api",
                    "properties": {"displayName": "External"},
                },
            ]
        }
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=data))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_apis()
        assert len(result) == 1
        assert result[0]["name"] == "Weather API"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_list_empty(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json={"value": []}))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_apis()
        assert result == []
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_list_api_failure(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(500))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_apis()
        assert result == []
        await adapter.disconnect()


class TestUpsertPolicy:
    @pytest.mark.asyncio
    async def test_create_product_with_policy(self, adapter: AzureApimAdapter) -> None:
        calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            path = str(req.url)
            calls.append(path)
            if req.method == "PUT" and "/products/" in path and "/policies/" not in path:
                return httpx.Response(201, json={"name": "stoa-pol-1", "properties": {"displayName": "Rate Limit"}})
            if req.method == "PUT" and "/policies/" in path:
                return httpx.Response(200, json={"name": "policy"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.upsert_policy(
            {
                "id": "pol-1",
                "name": "Rate Limit 100/min",
                "type": "rate_limit",
                "tenant_id": "acme",
                "config": {"max_requests": 100, "window_seconds": 60},
            }
        )
        assert result.success is True
        assert result.resource_id == "stoa-pol-1"
        # Should have made 2 PUT calls: product + policy
        assert len(calls) == 2
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_product_failure(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(400, text="Bad Request"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.upsert_policy({"id": "pol-1", "type": "rate_limit", "tenant_id": "acme", "config": {}})
        assert result.success is False
        assert "400" in (result.error or "")
        await adapter.disconnect()


class TestDeletePolicy:
    @pytest.mark.asyncio
    async def test_delete_success(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(204))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_policy("stoa-pol-1")
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_idempotent(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(404))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_policy("nonexistent")
        assert result.success is True
        await adapter.disconnect()


class TestListPolicies:
    @pytest.mark.asyncio
    async def test_filters_stoa_managed(self, adapter: AzureApimAdapter) -> None:
        data = {
            "value": [
                {
                    "name": "stoa-pol-1",
                    "properties": {
                        "displayName": "Rate Limit",
                        "description": "100/min",
                    },
                },
                {
                    "name": "external-product",
                    "properties": {"displayName": "External"},
                },
            ]
        }
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=data))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_policies()
        assert len(result) == 1
        assert result[0]["id"] == "pol-1"
        await adapter.disconnect()


class TestProvisionApplication:
    @pytest.mark.asyncio
    async def test_create_subscription(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(201, json={"name": "stoa-acme-app", "properties": {"displayName": "My App"}})
        )
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.provision_application({"id": "app-1", "name": "My App", "tenant_id": "acme"})
        assert result.success is True
        assert result.resource_id == "stoa-acme-app"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_create_with_product_scope(self, adapter: AzureApimAdapter) -> None:
        captured_body: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            import json

            captured_body.update(json.loads(req.content))
            return httpx.Response(201, json={"name": "stoa-acme-app"})

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        await adapter.provision_application(
            {"id": "app-1", "name": "My App", "tenant_id": "acme", "product_id": "stoa-pol-1"}
        )
        scope = captured_body.get("properties", {}).get("scope", "")
        assert "/products/stoa-pol-1" in scope
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_create_failure(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(400, text="Bad Request"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.provision_application({"id": "app-1", "tenant_id": "acme"})
        assert result.success is False
        assert "400" in (result.error or "")
        await adapter.disconnect()


class TestDeprovisionApplication:
    @pytest.mark.asyncio
    async def test_delete_success(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(204))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.deprovision_application("stoa-acme-app")
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_idempotent(self, adapter: AzureApimAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(404))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.deprovision_application("nonexistent")
        assert result.success is True
        await adapter.disconnect()


class TestListApplications:
    @pytest.mark.asyncio
    async def test_filters_stoa_managed(self, adapter: AzureApimAdapter) -> None:
        data = {
            "value": [
                {
                    "name": "stoa-acme-app",
                    "properties": {
                        "displayName": "Weather Client",
                        "state": "active",
                    },
                },
                {
                    "name": "master",
                    "properties": {"displayName": "Built-in all-access"},
                },
            ]
        }
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=data))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_applications()
        assert len(result) == 1
        assert result[0]["id"] == "stoa-acme-app"
        await adapter.disconnect()


class TestConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_creates_client(self, adapter: AzureApimAdapter) -> None:
        assert adapter._client is None
        await adapter.connect()
        assert adapter._client is not None
        await adapter.disconnect()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_disconnect_noop_when_not_connected(self, adapter: AzureApimAdapter) -> None:
        await adapter.disconnect()  # Should not raise


class TestUnsupportedMethods:
    @pytest.mark.asyncio
    async def test_auth_server_not_supported(self, adapter: AzureApimAdapter) -> None:
        result = await adapter.upsert_auth_server({})
        assert result.success is False
        assert "Not supported" in (result.error or "")

    @pytest.mark.asyncio
    async def test_strategy_not_supported(self, adapter: AzureApimAdapter) -> None:
        result = await adapter.upsert_strategy({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_scope_not_supported(self, adapter: AzureApimAdapter) -> None:
        result = await adapter.upsert_scope({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_alias_not_supported(self, adapter: AzureApimAdapter) -> None:
        result = await adapter.upsert_alias({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_apply_config_not_supported(self, adapter: AzureApimAdapter) -> None:
        result = await adapter.apply_config({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_export_archive_empty(self, adapter: AzureApimAdapter) -> None:
        result = await adapter.export_archive()
        assert result == b""

    @pytest.mark.asyncio
    async def test_deploy_contract_not_supported(self, adapter: AzureApimAdapter) -> None:
        result = await adapter.deploy_contract({})
        assert result.success is False


class TestRegistry:
    def test_azure_registered(self) -> None:
        from src.adapters.registry import AdapterRegistry

        assert AdapterRegistry.has_type("azure_apim")
        instance = AdapterRegistry.create(
            "azure_apim",
            {"subscription_id": "sub-1", "resource_group": "rg", "service_name": "apim"},
        )
        assert isinstance(instance, AzureApimAdapter)
