"""Tests for AWS API Gateway Adapter."""

import httpx
import pytest

from src.adapters.aws import mappers
from src.adapters.aws.adapter import AwsApiGatewayAdapter

# === Mapper Tests ===


class TestMapApiSpecToAws:
    def test_basic_mapping(self) -> None:
        spec = {
            "id": "api-1",
            "name": "weather-api",
            "description": "Provides weather data",
            "endpoint_type": "REGIONAL",
        }
        result = mappers.map_api_spec_to_aws(spec, "acme")
        assert result["name"] == "stoa-acme-weather-api"
        assert result["description"] == "Provides weather data"
        assert result["endpointConfiguration"]["types"] == ["REGIONAL"]
        assert result["tags"]["stoa-managed"] == "true"
        assert result["tags"]["stoa-tenant"] == "acme"
        assert result["tags"]["stoa-api-id"] == "api-1"

    def test_name_sanitization(self) -> None:
        spec = {"name": "My Cool API", "id": "x"}
        result = mappers.map_api_spec_to_aws(spec, "ACME Corp")
        assert " " not in result["name"]
        assert result["name"] == "stoa-acme-corp-my-cool-api"

    def test_defaults(self) -> None:
        result = mappers.map_api_spec_to_aws({}, "t1")
        assert result["name"] == "stoa-t1-unnamed-api"
        assert result["endpointConfiguration"]["types"] == ["REGIONAL"]
        assert result["description"] == ""

    def test_edge_endpoint_type(self) -> None:
        spec = {"name": "edge-api", "endpoint_type": "EDGE"}
        result = mappers.map_api_spec_to_aws(spec, "t1")
        assert result["endpointConfiguration"]["types"] == ["EDGE"]


class TestMapAwsApiToCp:
    def test_with_tags(self) -> None:
        api = {
            "id": "abc123",
            "name": "stoa-acme-weather-api",
            "description": "Weather data",
            "tags": {
                "stoa-api-id": "api-1",
                "stoa-tenant": "acme",
                "stoa-managed": "true",
            },
            "createdDate": "2026-01-15",
        }
        result = mappers.map_aws_api_to_cp(api)
        assert result["id"] == "api-1"
        assert result["name"] == "stoa-acme-weather-api"
        assert result["gateway_resource_id"] == "abc123"
        assert result["gateway_type"] == "aws_apigateway"
        assert result["created_at"] == "2026-01-15"

    def test_without_tags(self) -> None:
        api = {"id": "abc123", "name": "bare-api"}
        result = mappers.map_aws_api_to_cp(api)
        assert result["id"] == "abc123"
        assert result["name"] == "bare-api"
        assert result["gateway_type"] == "aws_apigateway"


class TestPolicyMappers:
    def test_rate_limit_to_usage_plan(self) -> None:
        spec = {
            "id": "pol-1",
            "name": "Rate Limit 100/min",
            "type": "rate_limit",
            "config": {"max_requests": 120, "window_seconds": 60},
        }
        result = mappers.map_policy_to_aws_usage_plan(spec, "acme")
        assert result["name"] == "stoa-pol-1"
        assert result["throttle"]["rateLimit"] == 2.0  # 120/60
        assert result["throttle"]["burstLimit"] == 4  # 2*rateLimit
        assert result["tags"]["stoa-managed"] == "true"
        assert result["tags"]["stoa-policy-id"] == "pol-1"

    def test_usage_plan_with_quota(self) -> None:
        spec = {
            "id": "pol-2",
            "type": "rate_limit",
            "config": {
                "max_requests": 60,
                "window_seconds": 60,
                "quota_limit": 10000,
                "quota_period": "MONTH",
            },
        }
        result = mappers.map_policy_to_aws_usage_plan(spec, "t1")
        assert result["quota"]["limit"] == 10000
        assert result["quota"]["period"] == "MONTH"

    def test_usage_plan_to_policy(self) -> None:
        plan = {
            "id": "up-123",
            "name": "stoa-pol-1",
            "description": "100/min rate limit",
            "throttle": {"rateLimit": 2.0, "burstLimit": 4},
            "tags": {
                "stoa-managed": "true",
                "stoa-policy-id": "pol-1",
            },
        }
        result = mappers.map_aws_usage_plan_to_policy(plan)
        assert result["id"] == "pol-1"
        assert result["type"] == "rate_limit"
        assert result["config"]["max_requests"] == 120  # 2.0 * 60
        assert result["config"]["burst_limit"] == 4
        assert result["gateway_type"] == "aws_apigateway"

    def test_usage_plan_with_quota_roundtrip(self) -> None:
        plan = {
            "id": "up-456",
            "name": "stoa-pol-2",
            "throttle": {"rateLimit": 1.0, "burstLimit": 2},
            "quota": {"limit": 5000, "period": "DAY"},
            "tags": {"stoa-policy-id": "pol-2"},
        }
        result = mappers.map_aws_usage_plan_to_policy(plan)
        assert result["config"]["quota_limit"] == 5000
        assert result["config"]["quota_period"] == "DAY"


class TestAppMappers:
    def test_app_spec_to_api_key(self) -> None:
        spec = {
            "id": "app-1",
            "name": "Weather Client",
            "description": "Weather consumer",
            "subscription_id": "sub-42",
        }
        result = mappers.map_app_spec_to_aws_api_key(spec, "acme")
        assert result["name"] == "stoa-acme-weather-client"
        assert result["enabled"] is True
        assert result["tags"]["stoa-managed"] == "true"
        assert result["tags"]["stoa-app-id"] == "app-1"
        assert result["tags"]["stoa-subscription-id"] == "sub-42"

    def test_api_key_to_cp(self) -> None:
        key = {
            "id": "key-abc",
            "name": "stoa-acme-weather-client",
            "description": "Weather consumer",
            "enabled": True,
            "tags": {
                "stoa-managed": "true",
                "stoa-app-id": "app-1",
                "stoa-subscription-id": "sub-42",
            },
            "createdDate": "2026-02-01",
        }
        result = mappers.map_aws_api_key_to_cp(key)
        assert result["id"] == "app-1"
        assert result["subscription_id"] == "sub-42"
        assert result["gateway_resource_id"] == "key-abc"
        assert result["gateway_type"] == "aws_apigateway"
        assert result["enabled"] is True

    def test_api_key_without_tags(self) -> None:
        key = {"id": "key-xyz", "name": "bare-key", "enabled": False}
        result = mappers.map_aws_api_key_to_cp(key)
        assert result["id"] == "key-xyz"
        assert result["enabled"] is False


# === Adapter Tests (mock httpx) ===


@pytest.fixture
def adapter() -> AwsApiGatewayAdapter:
    return AwsApiGatewayAdapter(
        config={
            "region": "eu-west-1",
            "auth_config": {"access_key": "AKIATEST", "secret_key": "secret123"},
        }
    )


class TestAdapterInit:
    def test_default_config(self) -> None:
        a = AwsApiGatewayAdapter()
        assert a._region == "us-east-1"
        assert "apigateway.us-east-1.amazonaws.com" in a._base_url

    def test_custom_config(self, adapter: AwsApiGatewayAdapter) -> None:
        assert adapter._region == "eu-west-1"
        assert "eu-west-1" in adapter._base_url
        assert adapter._access_key == "AKIATEST"
        assert adapter._secret_key == "secret123"

    def test_custom_base_url(self) -> None:
        a = AwsApiGatewayAdapter(config={"base_url": "http://localhost:4566"})
        assert a._base_url == "http://localhost:4566"


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json={"items": []}))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.health_check()
        assert result.success is True
        assert result.data is not None
        assert result.data["region"] == "eu-west-1"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_unhealthy(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(403, text="Forbidden"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.health_check()
        assert result.success is False
        assert "403" in (result.error or "")
        await adapter.disconnect()


class TestSyncApi:
    @pytest.mark.asyncio
    async def test_create_new(self, adapter: AwsApiGatewayAdapter) -> None:
        call_count = {"n": 0}

        def handler(req: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            if req.method == "GET" and "/restapis" in str(req.url):
                # First GET: list APIs (none found)
                return httpx.Response(200, json={"items": []})
            if req.method == "POST":
                return httpx.Response(201, json={"id": "new-api-id", "name": "stoa-acme-test"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.sync_api({"name": "test", "id": "a1"}, "acme")
        assert result.success is True
        assert result.resource_id == "new-api-id"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_update_existing(self, adapter: AwsApiGatewayAdapter) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "GET":
                return httpx.Response(
                    200,
                    json={"items": [{"id": "existing-id", "name": "stoa-acme-test"}]},
                )
            if req.method == "PATCH":
                return httpx.Response(200, json={"id": "existing-id", "name": "stoa-acme-test"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.sync_api({"name": "test", "id": "a1"}, "acme")
        assert result.success is True
        assert result.resource_id == "existing-id"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_api_error(self, adapter: AwsApiGatewayAdapter) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "GET":
                return httpx.Response(200, json={"items": []})
            return httpx.Response(500, text="Internal Server Error")

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.sync_api({"name": "test"}, "acme")
        assert result.success is False
        assert "500" in (result.error or "")
        await adapter.disconnect()


class TestDeleteApi:
    @pytest.mark.asyncio
    async def test_delete_success(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(202))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_api("api-123")
        assert result.success is True
        assert result.resource_id == "api-123"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_idempotent_404(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(404))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_api("nonexistent")
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_failure(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(409, text="Conflict"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_api("api-locked")
        assert result.success is False
        assert "409" in (result.error or "")
        await adapter.disconnect()


class TestListApis:
    @pytest.mark.asyncio
    async def test_list_filters_stoa_managed(self, adapter: AwsApiGatewayAdapter) -> None:
        data = {
            "items": [
                {
                    "id": "api-1",
                    "name": "stoa-acme-weather",
                    "description": "Weather",
                    "tags": {"stoa-managed": "true", "stoa-api-id": "w1"},
                },
                {
                    "id": "api-2",
                    "name": "external-api",
                    "description": "Not STOA",
                    "tags": {},
                },
            ]
        }
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=data))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_apis()
        assert len(result) == 1
        assert result[0]["id"] == "w1"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_list_empty(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json={"items": []}))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_apis()
        assert result == []
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_list_api_failure(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(500))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_apis()
        assert result == []
        await adapter.disconnect()


class TestUpsertPolicy:
    @pytest.mark.asyncio
    async def test_create_usage_plan(self, adapter: AwsApiGatewayAdapter) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "GET":
                return httpx.Response(200, json={"items": []})
            if req.method == "POST":
                return httpx.Response(201, json={"id": "up-new", "name": "stoa-pol-1"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.upsert_policy(
            {
                "id": "pol-1",
                "type": "rate_limit",
                "tenant_id": "acme",
                "config": {"max_requests": 60, "window_seconds": 60},
            }
        )
        assert result.success is True
        assert result.resource_id == "up-new"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_update_usage_plan(self, adapter: AwsApiGatewayAdapter) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "GET":
                return httpx.Response(
                    200,
                    json={"items": [{"id": "up-existing", "name": "stoa-pol-1"}]},
                )
            if req.method == "PATCH":
                return httpx.Response(200, json={"id": "up-existing", "name": "stoa-pol-1"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.upsert_policy(
            {
                "id": "pol-1",
                "type": "rate_limit",
                "tenant_id": "acme",
                "config": {"max_requests": 120, "window_seconds": 60},
            }
        )
        assert result.success is True
        assert result.resource_id == "up-existing"
        await adapter.disconnect()


class TestDeletePolicy:
    @pytest.mark.asyncio
    async def test_delete_success(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(202))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_policy("up-123")
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_idempotent(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(404))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.delete_policy("nonexistent")
        assert result.success is True
        await adapter.disconnect()


class TestListPolicies:
    @pytest.mark.asyncio
    async def test_filters_stoa_managed(self, adapter: AwsApiGatewayAdapter) -> None:
        data = {
            "items": [
                {
                    "id": "up-1",
                    "name": "stoa-pol-1",
                    "throttle": {"rateLimit": 1.0, "burstLimit": 2},
                    "tags": {"stoa-managed": "true", "stoa-policy-id": "pol-1"},
                },
                {
                    "id": "up-2",
                    "name": "external-plan",
                    "tags": {},
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
    async def test_create_api_key(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(201, json={"id": "key-new", "name": "stoa-acme-app"})
        )
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.provision_application(
            {
                "id": "app-1",
                "name": "My App",
                "tenant_id": "acme",
            }
        )
        assert result.success is True
        assert result.resource_id == "key-new"
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_create_with_usage_plan(self, adapter: AwsApiGatewayAdapter) -> None:
        calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            path = str(req.url.raw_path, "utf-8") if isinstance(req.url.raw_path, bytes) else str(req.url)
            calls.append(path)
            if "apikeys" in path and req.method == "POST" and "usageplans" not in path:
                return httpx.Response(201, json={"id": "key-new"})
            if "usageplans" in path and "keys" in path:
                return httpx.Response(201, json={"id": "key-new", "keyType": "API_KEY"})
            return httpx.Response(200)

        transport = httpx.MockTransport(handler)
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.provision_application(
            {
                "id": "app-1",
                "name": "My App",
                "tenant_id": "acme",
                "usage_plan_id": "up-123",
            }
        )
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_create_failure(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(400, text="Bad Request"))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.provision_application({"id": "app-1", "tenant_id": "acme"})
        assert result.success is False
        assert "400" in (result.error or "")
        await adapter.disconnect()


class TestDeprovisionApplication:
    @pytest.mark.asyncio
    async def test_delete_success(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(202))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.deprovision_application("key-abc")
        assert result.success is True
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_delete_idempotent(self, adapter: AwsApiGatewayAdapter) -> None:
        transport = httpx.MockTransport(lambda _req: httpx.Response(404))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.deprovision_application("nonexistent")
        assert result.success is True
        await adapter.disconnect()


class TestListApplications:
    @pytest.mark.asyncio
    async def test_filters_stoa_managed(self, adapter: AwsApiGatewayAdapter) -> None:
        data = {
            "items": [
                {
                    "id": "key-1",
                    "name": "stoa-acme-app",
                    "enabled": True,
                    "tags": {"stoa-managed": "true", "stoa-app-id": "app-1"},
                },
                {
                    "id": "key-2",
                    "name": "external-key",
                    "tags": {},
                },
            ]
        }
        transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=data))
        adapter._client = httpx.AsyncClient(base_url=adapter._base_url, transport=transport)
        result = await adapter.list_applications()
        assert len(result) == 1
        assert result[0]["id"] == "app-1"
        await adapter.disconnect()


class TestConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_creates_client(self, adapter: AwsApiGatewayAdapter) -> None:
        assert adapter._client is None
        await adapter.connect()
        assert adapter._client is not None
        await adapter.disconnect()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_disconnect_noop_when_not_connected(self, adapter: AwsApiGatewayAdapter) -> None:
        await adapter.disconnect()  # Should not raise


class TestUnsupportedMethods:
    @pytest.mark.asyncio
    async def test_auth_server_not_supported(self, adapter: AwsApiGatewayAdapter) -> None:
        result = await adapter.upsert_auth_server({})
        assert result.success is False
        assert "Not supported" in (result.error or "")

    @pytest.mark.asyncio
    async def test_strategy_not_supported(self, adapter: AwsApiGatewayAdapter) -> None:
        result = await adapter.upsert_strategy({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_scope_not_supported(self, adapter: AwsApiGatewayAdapter) -> None:
        result = await adapter.upsert_scope({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_alias_not_supported(self, adapter: AwsApiGatewayAdapter) -> None:
        result = await adapter.upsert_alias({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_apply_config_not_supported(self, adapter: AwsApiGatewayAdapter) -> None:
        result = await adapter.apply_config({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_export_archive_empty(self, adapter: AwsApiGatewayAdapter) -> None:
        result = await adapter.export_archive()
        assert result == b""

    @pytest.mark.asyncio
    async def test_deploy_contract_not_supported(self, adapter: AwsApiGatewayAdapter) -> None:
        result = await adapter.deploy_contract({})
        assert result.success is False


class TestRegistry:
    def test_aws_registered(self) -> None:
        from src.adapters.registry import AdapterRegistry

        assert AdapterRegistry.has_type("aws_apigateway")
        instance = AdapterRegistry.create("aws_apigateway", {"region": "eu-west-1"})
        assert isinstance(instance, AwsApiGatewayAdapter)
