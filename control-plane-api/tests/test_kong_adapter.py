"""Tests for Kong Gateway adapter (DB-less mode)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.kong.adapter import KongGatewayAdapter
from src.adapters.kong.mappers import (
    map_api_spec_to_kong_service,
    map_app_spec_to_kong_consumer,
    map_kong_consumer_to_cp,
    map_kong_plugin_to_policy,
    map_kong_service_to_cp,
    map_policy_to_kong_plugin,
)

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

    def test_map_policy_to_kong_plugin_rate_limit(self):
        policy = {
            "id": "pol-1",
            "type": "rate_limit",
            "config": {"maxRequests": 100, "intervalSeconds": 60},
        }
        result = map_policy_to_kong_plugin(policy, "acme-api")

        assert result["name"] == "rate-limiting"
        assert result["service"] == "acme-api"
        assert result["config"]["minute"] == 100
        assert "stoa-policy-pol-1" in result["tags"]

    def test_map_policy_to_kong_plugin_rate_limit_per_second(self):
        policy = {
            "id": "pol-2",
            "type": "rate_limit",
            "config": {"maxRequests": 10, "intervalSeconds": 1},
        }
        result = map_policy_to_kong_plugin(policy, "svc")

        assert result["config"]["second"] == 10

    def test_map_policy_to_kong_plugin_cors(self):
        policy = {
            "id": "pol-cors",
            "type": "cors",
            "config": {"origins": ["https://example.com"]},
        }
        result = map_policy_to_kong_plugin(policy, "svc")

        assert result["name"] == "cors"
        assert result["config"]["origins"] == ["https://example.com"]

    def test_map_policy_to_kong_plugin_generic(self):
        policy = {
            "id": "pol-custom",
            "type": "ip_restriction",
            "config": {"allow": ["10.0.0.0/8"]},
        }
        result = map_policy_to_kong_plugin(policy, "svc")

        assert result["name"] == "ip-restriction"
        assert result["config"]["allow"] == ["10.0.0.0/8"]

    def test_map_kong_plugin_to_policy_rate_limit(self):
        plugin = {
            "id": "k-plugin-1",
            "name": "rate-limiting",
            "config": {"minute": 200},
            "service": "acme-api",
            "tags": ["stoa-policy-pol-1"],
        }
        result = map_kong_plugin_to_policy(plugin)

        assert result["id"] == "pol-1"
        assert result["type"] == "rate_limit"
        assert result["config"]["maxRequests"] == 200
        assert result["config"]["intervalSeconds"] == 60

    def test_map_kong_plugin_to_policy_cors(self):
        plugin = {
            "name": "cors",
            "config": {"origins": ["*"], "methods": ["GET"]},
            "tags": [],
        }
        result = map_kong_plugin_to_policy(plugin)
        assert result["type"] == "cors"

    def test_map_app_spec_to_kong_consumer(self):
        spec = {
            "consumer_external_id": "consumer-42",
            "api_key": "my-secret-key",
            "subscription_id": "sub-1",
            "rate_limit_per_minute": 500,
        }
        result = map_app_spec_to_kong_consumer(spec)

        assert result["username"] == "consumer-42"
        assert result["keyauth_credentials"][0]["key"] == "my-secret-key"
        assert "stoa-consumer-sub-1" in result["tags"]
        assert result["plugins"][0]["config"]["minute"] == 500

    def test_map_app_spec_to_kong_consumer_no_rate_limit(self):
        spec = {"consumer_external_id": "consumer-no-rl", "subscription_id": "sub-2"}
        result = map_app_spec_to_kong_consumer(spec)

        assert result["username"] == "consumer-no-rl"
        assert "plugins" not in result

    def test_map_kong_consumer_to_cp(self):
        consumer = {
            "id": "k-consumer-1",
            "username": "consumer-42",
            "tags": ["stoa-consumer-sub-1"],
            "created_at": 1234567890,
        }
        result = map_kong_consumer_to_cp(consumer)

        assert result["id"] == "k-consumer-1"
        assert result["username"] == "consumer-42"
        assert result["subscription_id"] == "sub-1"


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

    def _mock_empty_state(self, client):
        """Mock GET endpoints to return empty state."""
        empty_resp = MagicMock()
        empty_resp.status_code = 200
        empty_resp.json.return_value = {"data": []}
        client.get = AsyncMock(return_value=empty_resp)

    @pytest.mark.asyncio
    async def test_sync_api_with_state_management(self):
        adapter, client = self._make_adapter()
        self._mock_empty_state(client)

        # POST /config succeeds
        config_resp = MagicMock()
        config_resp.status_code = 200
        client.post = AsyncMock(return_value=config_resp)

        result = await adapter.sync_api(
            {"api_name": "test", "backend_url": "http://backend"},
            tenant_id="acme",
        )

        assert result.success is True
        assert result.resource_id == "acme-test"
        # Verify POST /config was called
        client.post.assert_awaited_once()
        call_args = client.post.call_args
        assert call_args[0][0] == "/config"
        config = call_args[1]["json"]
        assert config["_format_version"] == "3.0"
        assert len(config["services"]) == 1
        assert config["services"][0]["name"] == "acme-test"

    @pytest.mark.asyncio
    async def test_sync_api_upserts_existing(self):
        adapter, client = self._make_adapter()

        # Mock existing service in state
        svc_resp = MagicMock()
        svc_resp.status_code = 200
        svc_resp.json.return_value = {
            "data": [{"id": "s1", "name": "acme-test", "host": "old", "port": 80, "protocol": "http", "path": ""}]
        }
        routes_resp = MagicMock()
        routes_resp.status_code = 200
        routes_resp.json.return_value = {"data": []}
        empty_resp = MagicMock()
        empty_resp.status_code = 200
        empty_resp.json.return_value = {"data": []}

        client.get = AsyncMock(side_effect=[svc_resp, routes_resp, empty_resp, empty_resp])

        config_resp = MagicMock()
        config_resp.status_code = 200
        client.post = AsyncMock(return_value=config_resp)

        result = await adapter.sync_api(
            {"api_name": "test", "backend_url": "http://new-backend"},
            tenant_id="acme",
        )

        assert result.success is True
        config = client.post.call_args[1]["json"]
        # Should have exactly 1 service (replaced, not duplicated)
        assert len(config["services"]) == 1
        assert config["services"][0]["url"] == "http://new-backend"

    @pytest.mark.asyncio
    async def test_sync_api_failure(self):
        adapter, client = self._make_adapter()
        self._mock_empty_state(client)

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
    async def test_delete_api_with_state_management(self):
        adapter, client = self._make_adapter()

        # Mock existing service
        svc_resp = MagicMock()
        svc_resp.status_code = 200
        svc_resp.json.return_value = {
            "data": [
                {"id": "s1", "name": "acme-test", "host": "h", "port": 80, "protocol": "http", "path": ""},
                {"id": "s2", "name": "acme-other", "host": "h2", "port": 80, "protocol": "http", "path": ""},
            ]
        }
        routes_resp = MagicMock()
        routes_resp.status_code = 200
        routes_resp.json.return_value = {"data": []}
        empty_resp = MagicMock()
        empty_resp.status_code = 200
        empty_resp.json.return_value = {"data": []}

        client.get = AsyncMock(side_effect=[svc_resp, routes_resp, routes_resp, empty_resp, empty_resp])

        config_resp = MagicMock()
        config_resp.status_code = 200
        client.post = AsyncMock(return_value=config_resp)

        result = await adapter.delete_api("acme-test")

        assert result.success is True
        assert result.resource_id == "acme-test"
        config = client.post.call_args[1]["json"]
        # Should have only 1 service remaining
        assert len(config["services"]) == 1
        assert config["services"][0]["name"] == "acme-other"

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


class TestKongAdapterPolicies:
    def _make_adapter(self):
        adapter = KongGatewayAdapter(config={"base_url": "http://kong:8001"})
        mock_client = AsyncMock()
        adapter._client = mock_client
        return adapter, mock_client

    def _mock_empty_state(self, client):
        empty_resp = MagicMock()
        empty_resp.status_code = 200
        empty_resp.json.return_value = {"data": []}
        client.get = AsyncMock(return_value=empty_resp)

    @pytest.mark.asyncio
    async def test_upsert_policy(self):
        adapter, client = self._make_adapter()
        self._mock_empty_state(client)

        config_resp = MagicMock()
        config_resp.status_code = 200
        client.post = AsyncMock(return_value=config_resp)

        result = await adapter.upsert_policy(
            {
                "id": "pol-1",
                "type": "rate_limit",
                "config": {"maxRequests": 100, "intervalSeconds": 60},
                "api_id": "acme-api",
            }
        )

        assert result.success is True
        assert result.resource_id == "pol-1"
        config = client.post.call_args[1]["json"]
        assert len(config["plugins"]) == 1
        assert config["plugins"][0]["name"] == "rate-limiting"

    @pytest.mark.asyncio
    async def test_upsert_policy_replaces_existing(self):
        adapter, client = self._make_adapter()

        # Mock existing plugin with same tag
        svc_resp = MagicMock()
        svc_resp.status_code = 200
        svc_resp.json.return_value = {"data": []}
        plugin_resp = MagicMock()
        plugin_resp.status_code = 200
        plugin_resp.json.return_value = {
            "data": [
                {
                    "name": "rate-limiting",
                    "service": "acme-api",
                    "config": {"minute": 50},
                    "tags": ["stoa-policy-pol-1"],
                }
            ]
        }
        consumer_resp = MagicMock()
        consumer_resp.status_code = 200
        consumer_resp.json.return_value = {"data": []}

        client.get = AsyncMock(side_effect=[svc_resp, plugin_resp, consumer_resp])

        config_resp = MagicMock()
        config_resp.status_code = 200
        client.post = AsyncMock(return_value=config_resp)

        result = await adapter.upsert_policy(
            {
                "id": "pol-1",
                "type": "rate_limit",
                "config": {"maxRequests": 200, "intervalSeconds": 60},
                "api_id": "acme-api",
            }
        )

        assert result.success is True
        config = client.post.call_args[1]["json"]
        # Should have exactly 1 plugin (replaced)
        assert len(config["plugins"]) == 1
        assert config["plugins"][0]["config"]["minute"] == 200

    @pytest.mark.asyncio
    async def test_delete_policy(self):
        adapter, client = self._make_adapter()

        svc_resp = MagicMock()
        svc_resp.status_code = 200
        svc_resp.json.return_value = {"data": []}
        plugin_resp = MagicMock()
        plugin_resp.status_code = 200
        plugin_resp.json.return_value = {
            "data": [
                {"name": "rate-limiting", "tags": ["stoa-policy-pol-1"], "config": {}, "service": ""},
                {"name": "cors", "tags": ["stoa-policy-pol-2"], "config": {}, "service": ""},
            ]
        }
        consumer_resp = MagicMock()
        consumer_resp.status_code = 200
        consumer_resp.json.return_value = {"data": []}

        client.get = AsyncMock(side_effect=[svc_resp, plugin_resp, consumer_resp])

        config_resp = MagicMock()
        config_resp.status_code = 200
        client.post = AsyncMock(return_value=config_resp)

        result = await adapter.delete_policy("pol-1")

        assert result.success is True
        config = client.post.call_args[1]["json"]
        # Should have only 1 plugin remaining (cors)
        assert len(config["plugins"]) == 1
        assert config["plugins"][0]["name"] == "cors"

    @pytest.mark.asyncio
    async def test_list_policies(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"name": "rate-limiting", "config": {"minute": 100}, "tags": ["stoa-policy-pol-1"], "service": "svc"},
                {"name": "cors", "config": {}, "tags": ["some-other-tag"]},  # Not STOA-managed
                {"name": "cors", "config": {}, "tags": ["stoa-policy-pol-2"], "service": "svc2"},
            ]
        }
        client.get = AsyncMock(return_value=mock_resp)

        policies = await adapter.list_policies()

        assert len(policies) == 2
        assert policies[0]["type"] == "rate_limit"
        assert policies[1]["type"] == "cors"


class TestKongAdapterApplications:
    def _make_adapter(self):
        adapter = KongGatewayAdapter(config={"base_url": "http://kong:8001"})
        mock_client = AsyncMock()
        adapter._client = mock_client
        return adapter, mock_client

    def _mock_empty_state(self, client):
        empty_resp = MagicMock()
        empty_resp.status_code = 200
        empty_resp.json.return_value = {"data": []}
        client.get = AsyncMock(return_value=empty_resp)

    @pytest.mark.asyncio
    async def test_provision_application(self):
        adapter, client = self._make_adapter()
        self._mock_empty_state(client)

        config_resp = MagicMock()
        config_resp.status_code = 200
        client.post = AsyncMock(return_value=config_resp)

        result = await adapter.provision_application(
            {
                "consumer_external_id": "consumer-42",
                "api_key": "secret-key",
                "subscription_id": "sub-1",
                "rate_limit_per_minute": 500,
            }
        )

        assert result.success is True
        assert result.resource_id == "consumer-42"
        config = client.post.call_args[1]["json"]
        assert len(config["consumers"]) == 1
        assert config["consumers"][0]["username"] == "consumer-42"

    @pytest.mark.asyncio
    async def test_deprovision_application(self):
        adapter, client = self._make_adapter()

        svc_resp = MagicMock()
        svc_resp.status_code = 200
        svc_resp.json.return_value = {"data": []}
        plugin_resp = MagicMock()
        plugin_resp.status_code = 200
        plugin_resp.json.return_value = {"data": []}
        consumer_resp = MagicMock()
        consumer_resp.status_code = 200
        consumer_resp.json.return_value = {
            "data": [
                {"username": "consumer-42", "tags": ["stoa-consumer-sub-1"]},
                {"username": "consumer-99", "tags": ["stoa-consumer-sub-2"]},
            ]
        }

        client.get = AsyncMock(side_effect=[svc_resp, plugin_resp, consumer_resp])

        config_resp = MagicMock()
        config_resp.status_code = 200
        client.post = AsyncMock(return_value=config_resp)

        result = await adapter.deprovision_application("consumer-42")

        assert result.success is True
        config = client.post.call_args[1]["json"]
        assert len(config["consumers"]) == 1
        assert config["consumers"][0]["username"] == "consumer-99"

    @pytest.mark.asyncio
    async def test_list_applications(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"id": "c1", "username": "consumer-42", "tags": ["stoa-consumer-sub-1"]},
                {"id": "c2", "username": "non-stoa-consumer", "tags": []},
                {"id": "c3", "username": "consumer-99", "tags": ["stoa-consumer-sub-2"]},
            ]
        }
        client.get = AsyncMock(return_value=mock_resp)

        apps = await adapter.list_applications()

        assert len(apps) == 2
        assert apps[0]["username"] == "consumer-42"
        assert apps[1]["username"] == "consumer-99"


class TestKongAdapterUnsupported:
    @pytest.mark.asyncio
    async def test_unsupported_methods(self):
        adapter = KongGatewayAdapter()

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


class TestKongBuildConfig:
    def test_build_config_all_entities(self):
        config = KongGatewayAdapter._build_config(
            services=[{"name": "svc"}],
            plugins=[{"name": "rate-limiting"}],
            consumers=[{"username": "user1"}],
        )
        assert config["_format_version"] == "3.0"
        assert len(config["services"]) == 1
        assert len(config["plugins"]) == 1
        assert len(config["consumers"]) == 1

    def test_build_config_empty_optional(self):
        config = KongGatewayAdapter._build_config(
            services=[{"name": "svc"}],
            plugins=[],
            consumers=[],
        )
        assert "plugins" not in config
        assert "consumers" not in config
