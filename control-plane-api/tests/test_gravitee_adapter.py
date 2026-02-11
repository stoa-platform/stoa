"""Tests for Gravitee APIM adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.gravitee.adapter import GraviteeGatewayAdapter
from src.adapters.gravitee.mappers import (
    map_api_spec_to_gravitee_v4,
    map_app_spec_to_gravitee_app,
    map_gravitee_api_to_cp,
    map_gravitee_app_to_cp,
    map_gravitee_plan_to_policy,
    map_policy_to_gravitee_plan,
)

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

    def test_map_api_spec_includes_methods(self):
        spec = {
            "api_name": "orders",
            "backend_url": "http://backend",
            "methods": ["GET", "POST"],
        }
        result = map_api_spec_to_gravitee_v4(spec, "t1")
        assert result["listeners"][0]["methods"] == ["GET", "POST"]

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

    def test_map_policy_to_gravitee_plan_rate_limit(self):
        policy = {
            "id": "pol-1",
            "type": "rate_limit",
            "config": {"maxRequests": 100, "intervalSeconds": 60},
        }
        result = map_policy_to_gravitee_plan(policy, "acme-api")

        assert result["name"] == "stoa-rate-limit-pol-1"
        assert result["definitionVersion"] == "V4"
        assert result["mode"] == "STANDARD"
        assert result["security"]["type"] == "KEY_LESS"
        flow = result["flows"][0]
        assert flow["request"][0]["policy"] == "rate-limit"
        rate_config = flow["request"][0]["configuration"]["rate"]
        assert rate_config["limit"] == 100
        assert rate_config["periodTimeUnit"] == "MINUTES"
        assert result["definitionVersion"] == "V4"
        assert result["mode"] == "STANDARD"

    def test_map_policy_to_gravitee_plan_per_second(self):
        policy = {
            "id": "pol-2",
            "type": "rate_limit",
            "config": {"maxRequests": 10, "intervalSeconds": 1},
        }
        result = map_policy_to_gravitee_plan(policy, "api")
        rate_config = result["flows"][0]["request"][0]["configuration"]["rate"]
        assert rate_config["periodTimeUnit"] == "SECONDS"

    def test_map_policy_to_gravitee_plan_generic(self):
        policy = {
            "id": "pol-gen",
            "type": "ip_restriction",
            "config": {"allow": ["10.0.0.0/8"]},
        }
        result = map_policy_to_gravitee_plan(policy, "api")

        assert result["name"] == "stoa-ip_restriction-pol-gen"
        assert result["flows"][0]["request"][0]["policy"] == "ip-restriction"

    def test_map_gravitee_plan_to_policy(self):
        plan = {
            "id": "plan-123",
            "name": "stoa-rate-limit-pol-1",
            "flows": [
                {
                    "request": [
                        {
                            "policy": "rate-limit",
                            "configuration": {
                                "rate": {
                                    "limit": 200,
                                    "periodTime": 1,
                                    "periodTimeUnit": "MINUTES",
                                }
                            },
                        }
                    ]
                }
            ],
        }
        result = map_gravitee_plan_to_policy(plan)

        assert result["id"] == "pol-1"
        assert result["type"] == "rate_limit"
        assert result["config"]["maxRequests"] == 200
        assert result["config"]["intervalSeconds"] == 60
        assert result["plan_id"] == "plan-123"

    def test_map_app_spec_to_gravitee_app(self):
        spec = {
            "consumer_external_id": "consumer-42",
        }
        result = map_app_spec_to_gravitee_app(spec)
        assert result["name"] == "consumer-42"
        assert result["settings"]["app"]["type"] == "SIMPLE"

    def test_map_gravitee_app_to_cp(self):
        app = {"id": "app-1", "name": "consumer-42", "status": "ACTIVE"}
        result = map_gravitee_app_to_cp(app)
        assert result["id"] == "app-1"
        assert result["name"] == "consumer-42"
        assert result["status"] == "ACTIVE"


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
    async def test_sync_api_creates_new(self):
        adapter, client = self._make_adapter()

        # _find_api_by_name returns None (new API)
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.json.return_value = {"data": []}

        create_resp = MagicMock()
        create_resp.status_code = 201
        create_resp.json.return_value = {"id": "new-api-id", "name": "acme-test"}

        start_resp = MagicMock()
        start_resp.status_code = 200

        deploy_resp = MagicMock()
        deploy_resp.status_code = 202

        client.get = AsyncMock(return_value=search_resp)
        client.post = AsyncMock(side_effect=[create_resp, start_resp, deploy_resp])

        result = await adapter.sync_api(
            {"api_name": "test", "backend_url": "http://backend"},
            tenant_id="acme",
        )

        assert result.success is True
        assert result.resource_id == "new-api-id"
        assert result.data["started"] is True
        # Verify lifecycle: POST (create) + POST (_start) + POST (deploy)
        assert client.post.await_count == 3

    @pytest.mark.asyncio
    async def test_sync_api_updates_existing(self):
        adapter, client = self._make_adapter()

        # _find_api_by_name returns an existing ID
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.json.return_value = {"data": [{"id": "existing-id", "name": "acme-test"}]}

        update_resp = MagicMock()
        update_resp.status_code = 200

        start_resp = MagicMock()
        start_resp.status_code = 409  # Already started

        deploy_resp = MagicMock()
        deploy_resp.status_code = 200

        client.get = AsyncMock(return_value=search_resp)
        client.put = AsyncMock(return_value=update_resp)
        client.post = AsyncMock(side_effect=[start_resp, deploy_resp])

        result = await adapter.sync_api(
            {"api_name": "test", "backend_url": "http://backend"},
            tenant_id="acme",
        )

        assert result.success is True
        assert result.resource_id == "existing-id"
        client.put.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sync_api_failure(self):
        adapter, client = self._make_adapter()

        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.json.return_value = {"data": []}

        create_resp = MagicMock()
        create_resp.status_code = 400
        create_resp.text = "bad request"

        client.get = AsyncMock(return_value=search_resp)
        client.post = AsyncMock(return_value=create_resp)

        result = await adapter.sync_api(
            {"api_name": "test", "backend_url": "http://backend"},
            tenant_id="acme",
        )

        assert result.success is False
        assert "400" in result.error

    @pytest.mark.asyncio
    async def test_delete_api_with_lifecycle(self):
        adapter, client = self._make_adapter()

        stop_resp = MagicMock()
        stop_resp.status_code = 200

        # Plans list for _close_all_plans
        plans_resp = MagicMock()
        plans_resp.status_code = 200
        plans_resp.json.return_value = {"data": [{"id": "plan-1", "status": "PUBLISHED"}]}

        close_resp = MagicMock()
        close_resp.status_code = 200

        delete_resp = MagicMock()
        delete_resp.status_code = 204

        client.post = AsyncMock(side_effect=[stop_resp, close_resp])
        client.get = AsyncMock(return_value=plans_resp)
        client.delete = AsyncMock(return_value=delete_resp)

        result = await adapter.delete_api("api-123")

        assert result.success is True
        assert result.resource_id == "api-123"
        # Verify lifecycle: POST _stop + POST _close(plan) + DELETE
        assert client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_delete_api_not_found_idempotent(self):
        adapter, client = self._make_adapter()

        stop_resp = MagicMock()
        stop_resp.status_code = 404

        plans_resp = MagicMock()
        plans_resp.status_code = 200
        plans_resp.json.return_value = {"data": []}

        delete_resp = MagicMock()
        delete_resp.status_code = 404

        client.post = AsyncMock(return_value=stop_resp)
        client.get = AsyncMock(return_value=plans_resp)
        client.delete = AsyncMock(return_value=delete_resp)

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


class TestGraviteeAdapterPolicies:
    def _make_adapter(self):
        adapter = GraviteeGatewayAdapter(config={"base_url": "http://gravitee:8083"})
        mock_client = AsyncMock()
        adapter._client = mock_client
        return adapter, mock_client

    @pytest.mark.asyncio
    async def test_upsert_policy_creates_plan(self):
        adapter, client = self._make_adapter()

        # _find_plan_by_stoa_id returns None (new plan)
        plans_resp = MagicMock()
        plans_resp.status_code = 200
        plans_resp.json.return_value = {"data": []}

        create_resp = MagicMock()
        create_resp.status_code = 201
        create_resp.json.return_value = {"id": "plan-new"}

        publish_resp = MagicMock()
        publish_resp.status_code = 200

        client.get = AsyncMock(return_value=plans_resp)
        client.post = AsyncMock(side_effect=[create_resp, publish_resp])

        result = await adapter.upsert_policy(
            {
                "id": "pol-1",
                "type": "rate_limit",
                "config": {"maxRequests": 100, "intervalSeconds": 60},
                "api_id": "api-123",
            }
        )

        assert result.success is True
        assert result.resource_id == "pol-1"
        assert result.data["plan_id"] == "plan-new"

    @pytest.mark.asyncio
    async def test_upsert_policy_updates_existing(self):
        adapter, client = self._make_adapter()

        # _find_plan_by_stoa_id returns existing plan
        plans_resp = MagicMock()
        plans_resp.status_code = 200
        plans_resp.json.return_value = {"data": [{"id": "plan-existing", "name": "stoa-rate-limit-pol-1"}]}

        update_resp = MagicMock()
        update_resp.status_code = 200
        update_resp.json.return_value = {"id": "plan-existing"}

        publish_resp = MagicMock()
        publish_resp.status_code = 200

        client.get = AsyncMock(return_value=plans_resp)
        client.put = AsyncMock(return_value=update_resp)
        client.post = AsyncMock(return_value=publish_resp)

        result = await adapter.upsert_policy(
            {
                "id": "pol-1",
                "type": "rate_limit",
                "config": {"maxRequests": 200, "intervalSeconds": 60},
                "api_id": "api-123",
            }
        )

        assert result.success is True
        client.put.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_policy_requires_api_id(self):
        adapter, _client = self._make_adapter()

        result = await adapter.upsert_policy(
            {
                "id": "pol-1",
                "type": "rate_limit",
                "config": {},
            }
        )

        assert result.success is False
        assert "api_id" in result.error

    @pytest.mark.asyncio
    async def test_delete_policy_with_api_id(self):
        adapter, client = self._make_adapter()

        # _find_plan_by_stoa_id returns a plan
        plans_resp = MagicMock()
        plans_resp.status_code = 200
        plans_resp.json.return_value = {"data": [{"id": "plan-1", "name": "stoa-rate-limit-pol-1"}]}

        close_resp = MagicMock()
        close_resp.status_code = 200

        delete_resp = MagicMock()
        delete_resp.status_code = 204

        client.get = AsyncMock(return_value=plans_resp)
        client.post = AsyncMock(return_value=close_resp)
        client.delete = AsyncMock(return_value=delete_resp)

        result = await adapter.delete_policy("api-123:pol-1")

        assert result.success is True
        assert result.resource_id == "api-123:pol-1"

    @pytest.mark.asyncio
    async def test_list_policies(self):
        adapter, client = self._make_adapter()

        # Mock list_apis
        apis_resp = MagicMock()
        apis_resp.status_code = 200
        apis_resp.json.return_value = {
            "data": [{"id": "api-1", "name": "test", "state": "STARTED", "visibility": "", "definitionVersion": "V4"}]
        }

        plans_resp = MagicMock()
        plans_resp.status_code = 200
        plans_resp.json.return_value = {
            "data": [
                {
                    "id": "plan-1",
                    "name": "stoa-rate-limit-pol-1",
                    "flows": [
                        {
                            "request": [
                                {
                                    "policy": "rate-limit",
                                    "configuration": {
                                        "rate": {"limit": 100, "periodTime": 1, "periodTimeUnit": "MINUTES"}
                                    },
                                }
                            ]
                        }
                    ],
                },
                {
                    "id": "plan-2",
                    "name": "non-stoa-plan",
                    "flows": [],
                },
            ]
        }

        client.get = AsyncMock(side_effect=[apis_resp, plans_resp])

        policies = await adapter.list_policies()

        assert len(policies) == 1
        assert policies[0]["type"] == "rate_limit"
        assert policies[0]["id"] == "pol-1"


class TestGraviteeAdapterApplications:
    def _make_adapter(self):
        adapter = GraviteeGatewayAdapter(config={"base_url": "http://gravitee:8083"})
        mock_client = AsyncMock()
        adapter._client = mock_client
        return adapter, mock_client

    @pytest.mark.asyncio
    async def test_provision_application(self):
        adapter, client = self._make_adapter()

        # Create app
        create_resp = MagicMock()
        create_resp.status_code = 201
        create_resp.json.return_value = {"id": "app-new"}

        # _ensure_rate_limit_plan: list plans returns empty, then upsert creates
        plans_resp = MagicMock()
        plans_resp.status_code = 200
        plans_resp.json.return_value = {"data": []}

        plan_create_resp = MagicMock()
        plan_create_resp.status_code = 201
        plan_create_resp.json.return_value = {"id": "plan-rl"}

        publish_resp = MagicMock()
        publish_resp.status_code = 200

        sub_resp = MagicMock()
        sub_resp.status_code = 201
        sub_resp.json.return_value = {"id": "sub-1"}

        client.get = AsyncMock(return_value=plans_resp)
        client.post = AsyncMock(side_effect=[create_resp, plan_create_resp, publish_resp, sub_resp])

        result = await adapter.provision_application(
            {
                "consumer_external_id": "consumer-42",
                "api_id": "api-123",
                "subscription_id": "sub-1",
                "rate_limit_per_minute": 100,
            }
        )

        assert result.success is True
        assert result.resource_id == "app-new"
        assert result.data["subscription_id"] == "sub-1"

    @pytest.mark.asyncio
    async def test_provision_application_no_api_id(self):
        adapter, client = self._make_adapter()

        create_resp = MagicMock()
        create_resp.status_code = 201
        create_resp.json.return_value = {"id": "app-new"}

        client.post = AsyncMock(return_value=create_resp)

        result = await adapter.provision_application(
            {
                "consumer_external_id": "consumer-42",
            }
        )

        assert result.success is True
        assert result.data["application_id"] == "app-new"

    @pytest.mark.asyncio
    async def test_deprovision_application(self):
        adapter, client = self._make_adapter()

        # List subscriptions
        subs_resp = MagicMock()
        subs_resp.status_code = 200
        subs_resp.json.return_value = {"data": [{"id": "sub-1"}, {"id": "sub-2"}]}

        close_resp = MagicMock()
        close_resp.status_code = 200

        delete_resp = MagicMock()
        delete_resp.status_code = 204

        client.get = AsyncMock(return_value=subs_resp)
        client.post = AsyncMock(return_value=close_resp)
        client.delete = AsyncMock(return_value=delete_resp)

        result = await adapter.deprovision_application("app-1")

        assert result.success is True
        assert result.resource_id == "app-1"
        # Should close 2 subscriptions
        assert client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_list_applications(self):
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"id": "app-1", "name": "consumer-42", "status": "ACTIVE"},
                {"id": "app-2", "name": "consumer-99", "status": "ACTIVE"},
            ]
        }
        client.get = AsyncMock(return_value=mock_resp)

        apps = await adapter.list_applications()

        assert len(apps) == 2
        assert apps[0]["name"] == "consumer-42"
        assert apps[1]["name"] == "consumer-99"


class TestGraviteeAdapterUnsupported:
    @pytest.mark.asyncio
    async def test_unsupported_methods(self):
        adapter = GraviteeGatewayAdapter()

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
