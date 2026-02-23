"""Tests for Apigee X Gateway Adapter.

Covers: mappers (proxy, product, developer app), adapter lifecycle,
API proxy CRUD, policy CRUD, application CRUD, error paths, registry.
"""

import httpx
import pytest

from src.adapters.apigee import mappers
from src.adapters.apigee.adapter import ApigeeGatewayAdapter

# ────────────────────────────────────────────────────────────────
# Mapper Tests
# ────────────────────────────────────────────────────────────────


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
        assert result["name"] == "stoa-acme-corp-my-cool-api"

    def test_defaults(self) -> None:
        result = mappers.map_api_spec_to_apigee_proxy({}, "t1")
        assert result["name"] == "stoa-t1-unnamed-api"
        assert result["basePath"] == "/unnamed-api"
        assert result["targetUrl"] == ""
        assert result["description"] == ""


class TestMapApigeeProxyToCp:
    def test_with_labels(self) -> None:
        proxy = {
            "name": "stoa-acme-weather",
            "displayName": "Weather API",
            "description": "Weather data",
            "basePath": "/weather",
            "labels": {"stoa-api-id": "api-1", "stoa-tenant": "acme"},
            "metaData": {"createdAt": "2026-01-01", "lastModifiedAt": "2026-02-01"},
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

    def test_second_time_unit(self) -> None:
        spec = {"id": "p2", "type": "rate_limit", "config": {"max_requests": 10, "window_seconds": 1}}
        result = mappers.map_policy_to_apigee_product(spec, "t1")
        assert result["quotaTimeUnit"] == "second"

    def test_non_rate_limit_policy(self) -> None:
        spec = {"id": "p3", "type": "cors", "name": "CORS Policy"}
        result = mappers.map_policy_to_apigee_product(spec, "t1")
        assert result["name"] == "stoa-cors-p3"
        assert "quota" not in result

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

    def test_product_without_quota(self) -> None:
        product = {
            "name": "some-product",
            "displayName": "No Quota",
            "attributes": [],
        }
        result = mappers.map_apigee_product_to_policy(product)
        assert "config" not in result


class TestApplicationMappers:
    def test_app_spec_to_developer_app(self) -> None:
        spec = {
            "id": "app-1",
            "name": "My App",
            "api_products": ["stoa-rate_limit-p1"],
        }
        result = mappers.map_app_spec_to_apigee_developer_app(spec, "acme")
        assert result["name"] == "stoa-acme-app-1"
        assert result["apiProducts"] == ["stoa-rate_limit-p1"]
        attrs = {a["name"]: a["value"] for a in result["attributes"]}
        assert attrs["stoa-managed"] == "true"
        assert attrs["stoa-tenant"] == "acme"
        assert attrs["stoa-app-id"] == "app-1"
        assert attrs["DisplayName"] == "My App"

    def test_app_spec_defaults(self) -> None:
        result = mappers.map_app_spec_to_apigee_developer_app({}, "t1")
        assert result["name"] == "stoa-t1-"
        assert "apiProducts" not in result

    def test_app_spec_name_sanitization(self) -> None:
        spec = {"id": "My App ID"}
        result = mappers.map_app_spec_to_apigee_developer_app(spec, "ACME Corp")
        assert " " not in result["name"]

    def test_developer_app_to_cp(self) -> None:
        app = {
            "name": "stoa-acme-app-1",
            "appId": "uuid-123",
            "status": "approved",
            "createdAt": "1709000000",
            "lastModifiedAt": "1709100000",
            "credentials": [{"consumerKey": "key-abc", "consumerSecret": "secret-xyz"}],
            "attributes": [
                {"name": "stoa-managed", "value": "true"},
                {"name": "stoa-tenant", "value": "acme"},
                {"name": "stoa-app-id", "value": "app-1"},
                {"name": "DisplayName", "value": "My App"},
            ],
        }
        result = mappers.map_apigee_developer_app_to_cp(app)
        assert result["id"] == "app-1"
        assert result["name"] == "My App"
        assert result["gateway_app_id"] == "stoa-acme-app-1"
        assert result["api_key"] == "key-abc"
        assert result["tenant_id"] == "acme"
        assert result["gateway_type"] == "apigee"
        assert result["status"] == "approved"

    def test_developer_app_no_credentials(self) -> None:
        app = {"name": "bare-app", "appId": "x", "attributes": []}
        result = mappers.map_apigee_developer_app_to_cp(app)
        assert result["api_key"] == ""
        assert result["id"] == "x"

    def test_developer_app_empty_credentials_list(self) -> None:
        app = {"name": "app-empty", "credentials": [], "attributes": []}
        result = mappers.map_apigee_developer_app_to_cp(app)
        assert result["api_key"] == ""


# ────────────────────────────────────────────────────────────────
# Adapter Tests (mock httpx)
# ────────────────────────────────────────────────────────────────


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
        assert headers["Content-Type"] == "application/json"

    def test_auth_headers_no_token(self) -> None:
        a = ApigeeGatewayAdapter(config={"organization": "org"})
        headers = a._auth_headers()
        assert "Authorization" not in headers

    def test_non_dict_auth_config(self) -> None:
        a = ApigeeGatewayAdapter(config={"auth_config": "invalid"})
        assert a._bearer_token == ""


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

    @pytest.mark.asyncio
    async def test_get_client_persistent(self, adapter: ApigeeGatewayAdapter) -> None:
        await adapter.connect()
        client, close_after = adapter._get_client()
        assert client is adapter._client
        assert close_after is False
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_get_client_ephemeral(self, adapter: ApigeeGatewayAdapter) -> None:
        client, close_after = adapter._get_client()
        assert close_after is True
        await client.aclose()


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=["env-1", "env-2"]))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.health_check()
        assert result.success is True
        assert result.data["organization"] == "my-org"
        assert result.data["environments"] == ["env-1", "env-2"]
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_unhealthy(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(401, text="Unauthorized"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.health_check()
        assert result.success is False
        assert "401" in (result.error or "")
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_connection_error(self, adapter: ApigeeGatewayAdapter) -> None:
        def raise_err(_req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(raise_err)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.health_check()
        assert result.success is False
        assert "Connection" in (result.error or "")
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_non_list_response(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json={"envs": ["a"]}))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.health_check()
        assert result.success is True
        assert result.data["environments"] == []  # not a list → default empty
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
    async def test_update_existing(self, adapter: ApigeeGatewayAdapter) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "GET":
                return httpx.Response(200, json={"name": "existing"})
            return httpx.Response(200, json={"name": "stoa-acme-test"})

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.sync_api({"name": "test"}, "acme")
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_api_error_response(self, adapter: ApigeeGatewayAdapter) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "GET":
                return httpx.Response(404)
            return httpx.Response(400, text="Bad request")

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.sync_api({"name": "bad"}, "t1")
        assert result.success is False
        assert "400" in (result.error or "")
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_exception_handling(self, adapter: ApigeeGatewayAdapter) -> None:
        def raise_err(_req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("timeout")

        transport = httpx.MockTransport(raise_err)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.sync_api({"name": "test"}, "t1")
        assert result.success is False
        await adapter.disconnect()


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

    @pytest.mark.asyncio
    async def test_delete_server_error(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(500, text="Internal error"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_api("api-x")
        assert result.success is False
        assert "500" in (result.error or "")
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

    @pytest.mark.asyncio
    async def test_list_error_returns_empty(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(500))
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

    @pytest.mark.asyncio
    async def test_upsert_error(self, adapter: ApigeeGatewayAdapter) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "GET":
                return httpx.Response(404)
            return httpx.Response(422, text="Unprocessable")

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.upsert_policy({"id": "bad", "type": "rate_limit"})
        assert result.success is False
        await adapter.disconnect()


class TestDeletePolicy:
    @pytest.mark.asyncio
    async def test_delete_success(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(204))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_policy("pol-1")
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_idempotent(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(404))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_policy("nonexistent")
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

    @pytest.mark.asyncio
    async def test_list_policies_error(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(403))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_policies()
        assert result == []
        await adapter.disconnect()


class TestEnsureDeveloper:
    @pytest.mark.asyncio
    async def test_developer_exists(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json={"email": "stoa-platform@gostoa.dev"}))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        ok = await adapter._ensure_developer(adapter._client)
        assert ok is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_developer_created(self, adapter: ApigeeGatewayAdapter) -> None:
        call_count = 0

        def handler(_req: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(404)  # GET → not found
            return httpx.Response(201, json={"email": "stoa-platform@gostoa.dev"})  # POST → created

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        ok = await adapter._ensure_developer(adapter._client)
        assert ok is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_developer_race_409(self, adapter: ApigeeGatewayAdapter) -> None:
        call_count = 0

        def handler(_req: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(404)
            return httpx.Response(409, text="Conflict")  # race condition

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        ok = await adapter._ensure_developer(adapter._client)
        assert ok is True  # 409 is treated as success
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_developer_create_fails(self, adapter: ApigeeGatewayAdapter) -> None:
        call_count = 0

        def handler(_req: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(404)
            return httpx.Response(500, text="Server error")

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        ok = await adapter._ensure_developer(adapter._client)
        assert ok is False
        await adapter.disconnect()


class TestProvisionApplication:
    @pytest.mark.asyncio
    async def test_create_app(self, adapter: ApigeeGatewayAdapter) -> None:
        call_count = 0

        def handler(_req: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"email": "dev"})  # ensure developer
            return httpx.Response(
                201,
                json={"name": "stoa-acme-app-1", "credentials": [{"consumerKey": "key-1"}]},
            )

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.provision_application({"id": "app-1", "name": "My App", "tenant_id": "acme"})
        assert result.success is True
        assert result.resource_id == "stoa-acme-app-1"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_create_app_developer_fails(self, adapter: ApigeeGatewayAdapter) -> None:
        call_count = 0

        def handler(_req: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(404)  # GET developer
            return httpx.Response(500)  # POST developer fails

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.provision_application({"id": "app-1", "tenant_id": "acme"})
        assert result.success is False
        assert "STOA developer" in (result.error or "")
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_create_app_api_error(self, adapter: ApigeeGatewayAdapter) -> None:
        call_count = 0

        def handler(_req: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"email": "dev"})  # developer OK
            return httpx.Response(409, text="App exists")

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.provision_application({"id": "dup", "tenant_id": "t1"})
        assert result.success is False
        assert "409" in (result.error or "")
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_create_app_exception(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: (_ for _ in ()).throw(httpx.ConnectError("fail")))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.provision_application({"id": "x", "tenant_id": "t1"})
        assert result.success is False
        await adapter.disconnect()


class TestDeprovisionApplication:
    @pytest.mark.asyncio
    async def test_delete_app(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(200))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.deprovision_application("stoa-acme-app-1")
        assert result.success is True
        assert result.resource_id == "stoa-acme-app-1"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_app_idempotent(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(404))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.deprovision_application("missing")
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_app_error(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(500, text="Server error"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.deprovision_application("app-x")
        assert result.success is False
        await adapter.disconnect()


class TestListApplications:
    @pytest.mark.asyncio
    async def test_list_apps(self, adapter: ApigeeGatewayAdapter) -> None:
        data = {
            "app": [
                {
                    "name": "stoa-acme-app-1",
                    "appId": "uuid-1",
                    "status": "approved",
                    "credentials": [{"consumerKey": "key-a"}],
                    "attributes": [
                        {"name": "stoa-managed", "value": "true"},
                        {"name": "stoa-app-id", "value": "app-1"},
                        {"name": "stoa-tenant", "value": "acme"},
                        {"name": "DisplayName", "value": "My App"},
                    ],
                }
            ]
        }
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=data))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_applications()
        assert len(result) == 1
        assert result[0]["id"] == "app-1"
        assert result[0]["api_key"] == "key-a"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_list_apps_empty(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json={"app": []}))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_applications()
        assert result == []
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_list_apps_error(self, adapter: ApigeeGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(401))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_applications()
        assert result == []
        await adapter.disconnect()


class TestUnsupportedMethods:
    @pytest.mark.asyncio
    async def test_unsupported_methods(self, adapter: ApigeeGatewayAdapter) -> None:
        r1 = await adapter.upsert_auth_server({})
        assert r1.success is False and "Not supported" in (r1.error or "")

        r2 = await adapter.upsert_strategy({})
        assert r2.success is False

        r3 = await adapter.upsert_scope({})
        assert r3.success is False

        r4 = await adapter.upsert_alias({})
        assert r4.success is False

        r5 = await adapter.apply_config({})
        assert r5.success is False

        r6 = await adapter.deploy_contract({})
        assert r6.success is False

    @pytest.mark.asyncio
    async def test_export_archive_empty(self, adapter: ApigeeGatewayAdapter) -> None:
        result = await adapter.export_archive()
        assert result == b""


class TestRegistry:
    def test_apigee_registered(self) -> None:
        from src.adapters.registry import AdapterRegistry

        assert AdapterRegistry.has_type("apigee")
        instance = AdapterRegistry.create("apigee", {"organization": "test"})
        assert isinstance(instance, ApigeeGatewayAdapter)
