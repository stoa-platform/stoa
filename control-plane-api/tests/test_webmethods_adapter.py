"""Tests for WebMethods API Gateway adapter.

Covers all 16 GatewayAdapterInterface methods plus helpers. No real HTTP calls;
GatewayAdminService (self._svc) is replaced with an AsyncMock after construction.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.gateway_adapter_interface import AdapterResult
from src.adapters.webmethods.adapter import WebMethodsGatewayAdapter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_adapter() -> WebMethodsGatewayAdapter:
    """Build a WebMethodsGatewayAdapter with a mocked GatewayAdminService."""
    with patch("src.services.gateway_service.GatewayAdminService"):
        adapter = WebMethodsGatewayAdapter(config={"base_url": "http://wm:5555", "auth_config": {}})
    # Replace the real service with a pure AsyncMock so every async method works
    svc = AsyncMock()
    adapter._svc = svc
    return adapter


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestWebMethodsAdapterInit:
    def test_init_with_base_url_creates_service(self) -> None:
        with patch("src.services.gateway_service.GatewayAdminService") as mock_cls:
            WebMethodsGatewayAdapter(config={"base_url": "http://wm:5555"})
            mock_cls.assert_called_once_with(base_url="http://wm:5555", auth_config=None)

    def test_init_without_config_uses_global_settings(self) -> None:
        with patch("src.services.gateway_service.GatewayAdminService") as mock_cls:
            WebMethodsGatewayAdapter(config=None)
            mock_cls.assert_called_once_with()

    def test_init_with_auth_config(self) -> None:
        auth = {"username": "admin", "password": "manage"}
        with patch("src.services.gateway_service.GatewayAdminService") as mock_cls:
            WebMethodsGatewayAdapter(config={"base_url": "http://wm:5555", "auth_config": auth})
            mock_cls.assert_called_once_with(base_url="http://wm:5555", auth_config=auth)

    def test_init_empty_config_uses_global_settings(self) -> None:
        with patch("src.services.gateway_service.GatewayAdminService") as mock_cls:
            WebMethodsGatewayAdapter(config={})
            # no base_url → falls back to global
            mock_cls.assert_called_once_with()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestWebMethodsLifecycle:
    async def test_health_check_success(self) -> None:
        adapter = _make_adapter()
        adapter._svc.health_check = AsyncMock(return_value={"status": "OK"})

        result = await adapter.health_check()

        assert result.success is True
        assert result.data == {"status": "OK"}

    async def test_health_check_error(self) -> None:
        adapter = _make_adapter()
        adapter._svc.health_check = AsyncMock(side_effect=ConnectionError("refused"))

        result = await adapter.health_check()

        assert result.success is False
        assert "refused" in result.error

    async def test_connect_delegates_to_service(self) -> None:
        adapter = _make_adapter()
        adapter._svc.connect = AsyncMock()

        await adapter.connect()

        adapter._svc.connect.assert_awaited_once()

    async def test_disconnect_delegates_to_service(self) -> None:
        adapter = _make_adapter()
        adapter._svc.disconnect = AsyncMock()

        await adapter.disconnect()

        adapter._svc.disconnect.assert_awaited_once()


# ---------------------------------------------------------------------------
# APIs
# ---------------------------------------------------------------------------


class TestWebMethodsAPIs:
    async def test_sync_api_success(self) -> None:
        adapter = _make_adapter()
        adapter._svc.import_api = AsyncMock(
            return_value={"apiResponse": {"api": {"id": "api-abc"}}}
        )

        result = await adapter.sync_api(
            api_spec={
                "apiName": "my-api",
                "apiVersion": "1.0",
                "url": "https://api.example.com/openapi.json",
                "type": "openapi",
            },
            tenant_id="acme",
        )

        assert result.success is True
        assert result.resource_id == "api-abc"
        adapter._svc.import_api.assert_awaited_once_with(
            api_name="my-api",
            api_version="1.0",
            openapi_url="https://api.example.com/openapi.json",
            openapi_spec=None,
            api_type="openapi",
            auth_token=None,
        )

    async def test_sync_api_uses_api_definition_when_no_url(self) -> None:
        adapter = _make_adapter()
        adapter._svc.import_api = AsyncMock(
            return_value={"apiResponse": {"api": {"id": "api-def"}}}
        )
        spec_payload = {"openapi": "3.0.0"}

        result = await adapter.sync_api(
            api_spec={
                "apiName": "inline-api",
                "apiVersion": "2.0",
                "apiDefinition": spec_payload,
            },
            tenant_id="acme",
        )

        assert result.success is True
        _, kwargs = adapter._svc.import_api.call_args
        assert kwargs["openapi_spec"] == spec_payload
        assert kwargs["openapi_url"] is None

    async def test_sync_api_default_type_is_openapi(self) -> None:
        adapter = _make_adapter()
        adapter._svc.import_api = AsyncMock(return_value={"apiResponse": {"api": {"id": "x"}}})

        await adapter.sync_api(
            api_spec={"apiName": "api", "apiVersion": "1"},
            tenant_id="t",
        )

        _, kwargs = adapter._svc.import_api.call_args
        assert kwargs["api_type"] == "openapi"

    async def test_sync_api_missing_id_returns_empty_string(self) -> None:
        adapter = _make_adapter()
        adapter._svc.import_api = AsyncMock(return_value={})

        result = await adapter.sync_api({"apiName": "api", "apiVersion": "1"}, tenant_id="t")

        assert result.success is True
        assert result.resource_id == ""

    async def test_sync_api_exception(self) -> None:
        adapter = _make_adapter()
        adapter._svc.import_api = AsyncMock(side_effect=RuntimeError("import failed"))

        result = await adapter.sync_api({"apiName": "api", "apiVersion": "1"}, tenant_id="t")

        assert result.success is False
        assert "import failed" in result.error

    async def test_delete_api_success(self) -> None:
        adapter = _make_adapter()
        adapter._svc.delete_api = AsyncMock()

        result = await adapter.delete_api("api-123")

        assert result.success is True
        assert result.resource_id == "api-123"
        adapter._svc.delete_api.assert_awaited_once_with("api-123", auth_token=None)

    async def test_delete_api_propagates_auth_token(self) -> None:
        adapter = _make_adapter()
        adapter._svc.delete_api = AsyncMock()

        await adapter.delete_api("api-456", auth_token="tok")

        adapter._svc.delete_api.assert_awaited_once_with("api-456", auth_token="tok")

    async def test_delete_api_exception(self) -> None:
        adapter = _make_adapter()
        adapter._svc.delete_api = AsyncMock(side_effect=ValueError("not found"))

        result = await adapter.delete_api("bad-id")

        assert result.success is False
        assert "not found" in result.error

    async def test_list_apis_delegates(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_apis = AsyncMock(return_value=[{"id": "a1"}, {"id": "a2"}])

        apis = await adapter.list_apis()

        assert apis == [{"id": "a1"}, {"id": "a2"}]
        adapter._svc.list_apis.assert_awaited_once_with(auth_token=None)


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------


class TestWebMethodsPolicies:
    async def test_upsert_policy_creates_when_not_existing(self) -> None:
        adapter = _make_adapter()
        # list_policies via _svc._request returns empty list
        adapter._svc._request = AsyncMock(
            side_effect=[
                {"policies": []},  # list_policies call
                {"policyAction": {"id": "pol-new"}},  # POST /policyActions
            ]
        )

        result = await adapter.upsert_policy(
            {
                "name": "rate-100",
                "type": "rate_limit",
                "config": {"maxRequests": 100, "intervalSeconds": 60},
            }
        )

        assert result.success is True
        assert result.resource_id == "pol-new"
        # First call: GET /policies; second call: POST /policyActions
        assert adapter._svc._request.await_count == 2
        post_call = adapter._svc._request.call_args_list[1]
        assert post_call.args[0] == "POST"
        assert post_call.args[1] == "/policyActions"

    async def test_upsert_policy_updates_when_existing_by_policy_name(self) -> None:
        adapter = _make_adapter()
        adapter._svc._request = AsyncMock(
            side_effect=[
                {"policies": [{"policyName": "rate-100", "id": "pol-existing"}]},
                {"policyAction": {"id": "pol-existing"}},  # PUT response
            ]
        )

        result = await adapter.upsert_policy(
            {
                "name": "rate-100",
                "type": "rate_limit",
                "config": {"maxRequests": 200, "intervalSeconds": 60},
            }
        )

        assert result.success is True
        assert result.resource_id == "pol-existing"
        put_call = adapter._svc._request.call_args_list[1]
        assert put_call.args[0] == "PUT"
        assert "/policyActions/pol-existing" in put_call.args[1]

    async def test_upsert_policy_matches_by_name_field(self) -> None:
        adapter = _make_adapter()
        # "name" field (not "policyName") matches
        adapter._svc._request = AsyncMock(
            side_effect=[
                {"policies": [{"name": "rate-100", "id": "pol-by-name"}]},
                {"policyAction": {"id": "pol-by-name"}},
            ]
        )

        result = await adapter.upsert_policy(
            {"name": "rate-100", "type": "rate_limit", "config": {}}
        )

        assert result.success is True
        assert result.resource_id == "pol-by-name"

    async def test_upsert_policy_exception(self) -> None:
        adapter = _make_adapter()
        adapter._svc._request = AsyncMock(side_effect=RuntimeError("timeout"))

        result = await adapter.upsert_policy({"name": "p", "type": "rate_limit", "config": {}})

        assert result.success is False
        assert "timeout" in result.error

    async def test_delete_policy_success(self) -> None:
        adapter = _make_adapter()
        adapter._svc._request = AsyncMock(return_value={})

        result = await adapter.delete_policy("pol-99")

        assert result.success is True
        assert result.resource_id == "pol-99"
        adapter._svc._request.assert_awaited_once_with(
            "DELETE", "/policyActions/pol-99", auth_token=None
        )

    async def test_delete_policy_exception(self) -> None:
        adapter = _make_adapter()
        adapter._svc._request = AsyncMock(side_effect=RuntimeError("server error"))

        result = await adapter.delete_policy("pol-bad")

        assert result.success is False

    async def test_list_policies_returns_list(self) -> None:
        adapter = _make_adapter()
        adapter._svc._request = AsyncMock(
            return_value={"policies": [{"id": "p1"}, {"id": "p2"}]}
        )

        policies = await adapter.list_policies()

        assert len(policies) == 2
        adapter._svc._request.assert_awaited_once_with("GET", "/policies", auth_token=None)

    async def test_list_policies_empty_result(self) -> None:
        adapter = _make_adapter()
        adapter._svc._request = AsyncMock(return_value={})

        policies = await adapter.list_policies()

        assert policies == []


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


class TestWebMethodsApplications:
    async def test_provision_application_new(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_applications = AsyncMock(return_value=[])
        adapter._svc.provision_application = AsyncMock(
            return_value={"app_id": "app-new", "api_key": "key-123"}
        )

        result = await adapter.provision_application(
            {
                "application_name": "my-app",
                "subscription_id": "sub-1",
                "api_id": "api-1",
                "tenant_id": "acme",
                "subscriber_email": "user@example.com",
                "correlation_id": "corr-1",
            }
        )

        assert result.success is True
        assert result.resource_id == "app-new"
        adapter._svc.provision_application.assert_awaited_once_with(
            subscription_id="sub-1",
            application_name="my-app",
            api_id="api-1",
            tenant_id="acme",
            subscriber_email="user@example.com",
            correlation_id="corr-1",
            auth_token=None,
        )

    async def test_provision_application_returns_existing(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_applications = AsyncMock(
            return_value=[{"name": "my-app", "id": "app-existing"}]
        )
        adapter._svc.provision_application = AsyncMock()

        result = await adapter.provision_application(
            {
                "application_name": "my-app",
                "subscription_id": "sub-1",
                "api_id": "api-1",
                "tenant_id": "acme",
            }
        )

        assert result.success is True
        assert result.resource_id == "app-existing"
        # Should NOT call provision_application when already existing
        adapter._svc.provision_application.assert_not_awaited()

    async def test_provision_application_optional_fields_default(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_applications = AsyncMock(return_value=[])
        adapter._svc.provision_application = AsyncMock(
            return_value={"app_id": "app-x"}
        )

        await adapter.provision_application(
            {
                "application_name": "app",
                "subscription_id": "sub-2",
                "api_id": "api-2",
                "tenant_id": "t",
                # subscriber_email and correlation_id omitted
            }
        )

        _, kwargs = adapter._svc.provision_application.call_args
        assert kwargs["subscriber_email"] == ""
        assert kwargs["correlation_id"] == ""

    async def test_provision_application_exception(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_applications = AsyncMock(return_value=[])
        adapter._svc.provision_application = AsyncMock(side_effect=RuntimeError("svc down"))

        result = await adapter.provision_application(
            {
                "application_name": "app",
                "subscription_id": "sub",
                "api_id": "api",
                "tenant_id": "t",
            }
        )

        assert result.success is False
        assert "svc down" in result.error

    async def test_deprovision_application_success(self) -> None:
        adapter = _make_adapter()
        adapter._svc.deprovision_application = AsyncMock(return_value={"status": "deleted"})

        result = await adapter.deprovision_application("app-del")

        assert result.success is True
        assert result.resource_id == "app-del"
        adapter._svc.deprovision_application.assert_awaited_once_with(
            app_id="app-del",
            correlation_id="adapter",
            auth_token=None,
        )

    async def test_deprovision_application_exception(self) -> None:
        adapter = _make_adapter()
        adapter._svc.deprovision_application = AsyncMock(side_effect=RuntimeError("not found"))

        result = await adapter.deprovision_application("app-missing")

        assert result.success is False
        assert "not found" in result.error

    async def test_list_applications_delegates(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_applications = AsyncMock(return_value=[{"id": "a1"}, {"id": "a2"}])

        apps = await adapter.list_applications()

        assert len(apps) == 2
        adapter._svc.list_applications.assert_awaited_once_with(auth_token=None)


# ---------------------------------------------------------------------------
# Auth / OIDC
# ---------------------------------------------------------------------------


class TestWebMethodsAuthServer:
    async def test_upsert_auth_server_creates_new(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_aliases = AsyncMock(return_value=[])
        adapter._svc._request = AsyncMock(
            return_value={"alias": {"id": "alias-new"}}
        )

        result = await adapter.upsert_auth_server(
            {
                "name": "KeycloakOIDC",
                "discoveryURL": "https://auth.example.com/.well-known/openid-configuration",
                "clientId": "stoa-client",
            }
        )

        assert result.success is True
        assert result.resource_id == "alias-new"
        adapter._svc._request.assert_awaited_once()
        call_args = adapter._svc._request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/alias"
        assert call_args[1]["json"]["name"] == "KeycloakOIDC"

    async def test_upsert_auth_server_updates_existing(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_aliases = AsyncMock(
            return_value=[{"name": "KeycloakOIDC", "type": "authServerAlias", "id": "alias-existing"}]
        )
        adapter._svc._request = AsyncMock(return_value={"alias": {"id": "alias-existing"}})

        result = await adapter.upsert_auth_server(
            {
                "name": "KeycloakOIDC",
                "discoveryURL": "https://auth.example.com/.well-known/openid-configuration",
                "clientId": "stoa-client",
            }
        )

        assert result.success is True
        assert result.resource_id == "alias-existing"
        call = adapter._svc._request.call_args
        assert call.args[0] == "PUT"
        assert "/alias/alias-existing" in call.args[1]

    async def test_upsert_auth_server_skips_non_auth_server_aliases(self) -> None:
        """Aliases with different type should not match."""
        adapter = _make_adapter()
        # existing alias has type "endpoint", not "authServerAlias"
        adapter._svc.list_aliases = AsyncMock(
            return_value=[{"name": "KeycloakOIDC", "type": "endpoint", "id": "alias-endpoint"}]
        )
        adapter._svc._request = AsyncMock(return_value={"alias": {"id": "alias-new"}})

        result = await adapter.upsert_auth_server(
            {
                "name": "KeycloakOIDC",
                "discoveryURL": "https://auth.example.com/.well-known/openid-configuration",
                "clientId": "stoa-client",
            }
        )

        assert result.success is True
        # Should POST (create), not PUT
        call = adapter._svc._request.call_args
        assert call.args[0] == "POST"

    async def test_upsert_auth_server_exception(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_aliases = AsyncMock(side_effect=RuntimeError("network error"))

        result = await adapter.upsert_auth_server({"name": "k", "discoveryURL": "x", "clientId": "c"})

        assert result.success is False
        assert "network error" in result.error


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


class TestWebMethodsStrategy:
    async def test_upsert_strategy_creates_new(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_strategies = AsyncMock(return_value=[])
        adapter._svc._request = AsyncMock(
            return_value={"strategy": {"id": "strat-new"}}
        )

        result = await adapter.upsert_strategy(
            {
                "name": "OIDC-strategy",
                "type": "OAUTH2",
                "authServerAlias": "KeycloakOIDC",
                "clientId": "stoa",
            }
        )

        assert result.success is True
        assert result.resource_id == "strat-new"
        call = adapter._svc._request.call_args
        assert call.args[0] == "POST"
        assert call.args[1] == "/strategies"

    async def test_upsert_strategy_updates_existing(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_strategies = AsyncMock(
            return_value=[{"name": "OIDC-strategy", "id": "strat-existing"}]
        )
        adapter._svc._request = AsyncMock(
            return_value={"strategy": {"id": "strat-existing"}}
        )

        result = await adapter.upsert_strategy(
            {
                "name": "OIDC-strategy",
                "type": "OAUTH2",
                "authServerAlias": "KeycloakOIDC",
            }
        )

        assert result.success is True
        assert result.resource_id == "strat-existing"
        call = adapter._svc._request.call_args
        assert call.args[0] == "PUT"
        assert "/strategies/strat-existing" in call.args[1]

    async def test_upsert_strategy_builds_correct_payload(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_strategies = AsyncMock(return_value=[])
        adapter._svc._request = AsyncMock(return_value={"strategy": {"id": "s1"}})

        await adapter.upsert_strategy(
            {
                "name": "my-strat",
                "description": "desc",
                "type": "OAUTH2",
                "authServerAlias": "KeycloakOIDC",
                "clientId": "cid",
                "audience": "aud",
            }
        )

        payload = adapter._svc._request.call_args.kwargs["json"]
        assert payload["name"] == "my-strat"
        assert payload["description"] == "desc"
        assert payload["type"] == "OAUTH2"
        assert payload["authServerAlias"] == "KeycloakOIDC"
        assert payload["clientId"] == "cid"
        assert payload["audience"] == "aud"

    async def test_upsert_strategy_exception(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_strategies = AsyncMock(side_effect=RuntimeError("svc error"))

        result = await adapter.upsert_strategy(
            {"name": "s", "authServerAlias": "k", "type": "OAUTH2"}
        )

        assert result.success is False


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


class TestWebMethodsScope:
    async def test_upsert_scope_success(self) -> None:
        adapter = _make_adapter()
        adapter._svc.create_scope_mapping = AsyncMock(
            return_value={"scope": {"id": "scope-1"}}
        )

        result = await adapter.upsert_scope(
            {
                "scopeName": "openid",
                "description": "OIDC scope",
                "audience": "",
                "apiIds": ["api-1"],
                "authServerAlias": "KeycloakOIDC",
                "keycloakScope": "openid",
            }
        )

        assert result.success is True
        adapter._svc.create_scope_mapping.assert_awaited_once_with(
            scope_name="openid",
            description="OIDC scope",
            audience="",
            api_ids=["api-1"],
            auth_server_alias="KeycloakOIDC",
            keycloak_scope="openid",
            auth_token=None,
        )

    async def test_upsert_scope_uses_defaults(self) -> None:
        adapter = _make_adapter()
        adapter._svc.create_scope_mapping = AsyncMock(return_value={})

        await adapter.upsert_scope({"scopeName": "read"})

        _, kwargs = adapter._svc.create_scope_mapping.call_args
        assert kwargs["description"] == ""
        assert kwargs["audience"] == ""
        assert kwargs["api_ids"] == []
        assert kwargs["auth_server_alias"] == "KeycloakOIDC"
        assert kwargs["keycloak_scope"] == "openid"

    async def test_upsert_scope_exception(self) -> None:
        adapter = _make_adapter()
        adapter._svc.create_scope_mapping = AsyncMock(side_effect=RuntimeError("scope error"))

        result = await adapter.upsert_scope({"scopeName": "x"})

        assert result.success is False
        assert "scope error" in result.error


# ---------------------------------------------------------------------------
# Alias
# ---------------------------------------------------------------------------


class TestWebMethodsAlias:
    async def test_upsert_alias_creates_new(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_aliases = AsyncMock(return_value=[])
        adapter._svc._request = AsyncMock(
            return_value={"alias": {"id": "alias-ep-new"}}
        )

        result = await adapter.upsert_alias(
            {
                "name": "backend-api",
                "type": "endpoint",
                "endpointUri": "https://backend.example.com",
            }
        )

        assert result.success is True
        assert result.resource_id == "alias-ep-new"
        call = adapter._svc._request.call_args
        assert call.args[0] == "POST"
        assert call.args[1] == "/alias"

    async def test_upsert_alias_updates_existing(self) -> None:
        adapter = _make_adapter()
        # Existing alias with type "endpoint" (not authServerAlias)
        adapter._svc.list_aliases = AsyncMock(
            return_value=[{"name": "backend-api", "type": "endpoint", "id": "alias-ep-existing"}]
        )
        adapter._svc._request = AsyncMock(return_value={"alias": {"id": "alias-ep-existing"}})

        result = await adapter.upsert_alias(
            {
                "name": "backend-api",
                "type": "endpoint",
                "endpointUri": "https://backend.example.com",
            }
        )

        assert result.success is True
        assert result.resource_id == "alias-ep-existing"
        call = adapter._svc._request.call_args
        assert call.args[0] == "PUT"

    async def test_upsert_alias_ignores_auth_server_aliases(self) -> None:
        """An authServerAlias with same name should not match for endpoint alias upsert."""
        adapter = _make_adapter()
        adapter._svc.list_aliases = AsyncMock(
            return_value=[{"name": "backend-api", "type": "authServerAlias", "id": "auth-alias"}]
        )
        adapter._svc._request = AsyncMock(return_value={"alias": {"id": "new-ep"}})

        result = await adapter.upsert_alias(
            {
                "name": "backend-api",
                "type": "endpoint",
                "endpointUri": "https://backend.example.com",
            }
        )

        assert result.success is True
        # Should POST (create) because authServerAlias should be filtered out
        call = adapter._svc._request.call_args
        assert call.args[0] == "POST"

    async def test_upsert_alias_exception(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_aliases = AsyncMock(side_effect=RuntimeError("alias error"))

        result = await adapter.upsert_alias(
            {"name": "alias", "type": "endpoint", "endpointUri": "http://x"}
        )

        assert result.success is False
        assert "alias error" in result.error


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestWebMethodsApplyConfig:
    async def test_apply_config_single_key(self) -> None:
        adapter = _make_adapter()
        adapter._svc._request = AsyncMock(return_value={"status": "ok"})

        result = await adapter.apply_config(
            {"errorProcessing": {"mode": "strict"}}
        )

        assert result.success is True
        adapter._svc._request.assert_awaited_once_with(
            "PUT",
            "/configurations/errorProcessing",
            auth_token=None,
            json={"mode": "strict"},
        )

    async def test_apply_config_multiple_keys(self) -> None:
        adapter = _make_adapter()
        adapter._svc._request = AsyncMock(return_value={})

        result = await adapter.apply_config(
            {
                "errorProcessing": {"mode": "lenient"},
                "callbackSettings": {"timeout": 60},
                "keystore": {"alias": "cert"},
                "jwt": {"issuer": "https://auth.example.com"},
            }
        )

        assert result.success is True
        # map_config_to_webmethods remaps callbackSettings → apiCallBackSettings, jwt → jsonWebToken
        assert adapter._svc._request.await_count == 4
        endpoints_called = [call.args[1] for call in adapter._svc._request.call_args_list]
        assert "/configurations/errorProcessing" in endpoints_called
        assert "/configurations/apiCallBackSettings" in endpoints_called
        assert "/configurations/keystore" in endpoints_called
        assert "/configurations/jsonWebToken" in endpoints_called

    async def test_apply_config_empty_spec_does_nothing(self) -> None:
        adapter = _make_adapter()
        adapter._svc._request = AsyncMock(return_value={})

        result = await adapter.apply_config({})

        assert result.success is True
        adapter._svc._request.assert_not_awaited()
        assert result.data == {}

    async def test_apply_config_exception(self) -> None:
        adapter = _make_adapter()
        adapter._svc._request = AsyncMock(side_effect=RuntimeError("config error"))

        result = await adapter.apply_config({"errorProcessing": {"mode": "strict"}})

        assert result.success is False
        assert "config error" in result.error


# ---------------------------------------------------------------------------
# Archive / Backup
# ---------------------------------------------------------------------------


class TestWebMethodsExportArchive:
    async def test_export_archive_success(self) -> None:
        adapter = _make_adapter()

        mock_response = MagicMock()
        mock_response.content = b"PK\x03\x04archive-data"
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)

        @asynccontextmanager
        async def mock_get_client(auth_token=None):
            yield mock_http_client

        adapter._svc._get_client = mock_get_client

        data = await adapter.export_archive()

        assert data == b"PK\x03\x04archive-data"
        mock_http_client.request.assert_awaited_once_with(
            "GET",
            "/archive",
            params={"include": "api,application,alias,policy"},
        )
        mock_response.raise_for_status.assert_called_once()

    async def test_export_archive_raises_on_http_error(self) -> None:
        adapter = _make_adapter()

        import httpx

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock())
        )

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)

        @asynccontextmanager
        async def mock_get_client(auth_token=None):
            yield mock_http_client

        adapter._svc._get_client = mock_get_client

        with pytest.raises(Exception):
            await adapter.export_archive()


# ---------------------------------------------------------------------------
# deploy_contract (not supported)
# ---------------------------------------------------------------------------


class TestWebMethodsDeployContract:
    async def test_deploy_contract_not_supported(self) -> None:
        adapter = _make_adapter()

        result = await adapter.deploy_contract({"contract": "data"})

        assert result.success is False
        assert "Not supported" in result.error


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestWebMethodsRegistration:
    def test_webmethods_registered_in_registry(self) -> None:
        from src.adapters.registry import AdapterRegistry

        assert AdapterRegistry.has_type("webmethods") is True

    def test_webmethods_creates_correct_adapter_type(self) -> None:
        with patch("src.services.gateway_service.GatewayAdminService"):
            from src.adapters.registry import AdapterRegistry

            adapter = AdapterRegistry.create(
                "webmethods",
                config={"base_url": "http://wm:5555"},
            )
        assert isinstance(adapter, WebMethodsGatewayAdapter)
