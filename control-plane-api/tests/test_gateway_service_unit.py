"""Unit tests for GatewayAdminService — CAB-1378 + CAB-1526

Tests the webMethods Gateway admin service HTTP wrapper.
Covers both OIDC proxy and Basic Auth modes.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.gateway_service import GatewayAdminService


def _make_svc_with_mock_client(json_response=None, status_code=200, content=b"{}"):
    """Helper: return a GatewayAdminService with a mock httpx client pre-wired."""
    svc = GatewayAdminService()
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.content = content
    mock_response.json.return_value = json_response or {}
    mock_response.raise_for_status = MagicMock()

    svc._client = AsyncMock()
    svc._client.request = AsyncMock(return_value=mock_response)
    svc._use_proxy = False
    return svc, mock_response


class TestConnect:
    """GatewayAdminService.connect"""

    @patch("src.services.gateway_service.settings")
    def test_connect_basic_auth(self, mock_settings):
        """Basic Auth mode creates a persistent client."""
        mock_settings.GATEWAY_USE_OIDC_PROXY = False
        mock_settings.GATEWAY_URL = "http://gateway:5555"
        mock_settings.GATEWAY_ADMIN_USER = "admin"
        mock_settings.GATEWAY_ADMIN_PASSWORD = "manage"

        svc = GatewayAdminService()
        asyncio.get_event_loop().run_until_complete(svc.connect())

        assert svc._client is not None
        # Cleanup
        asyncio.get_event_loop().run_until_complete(svc.disconnect())

    @patch("src.services.gateway_service.settings")
    def test_connect_oidc_proxy(self, mock_settings):
        """OIDC proxy mode does NOT create persistent client."""
        mock_settings.GATEWAY_USE_OIDC_PROXY = True
        mock_settings.GATEWAY_ADMIN_PROXY_URL = "http://proxy:8080"

        svc = GatewayAdminService()
        asyncio.get_event_loop().run_until_complete(svc.connect())

        assert svc._client is None


class TestDisconnect:
    """GatewayAdminService.disconnect"""

    def test_disconnect_closes_client(self):
        """Disconnect closes the httpx client."""
        svc = GatewayAdminService()
        mock_client = AsyncMock()
        svc._client = mock_client

        asyncio.get_event_loop().run_until_complete(svc.disconnect())

        mock_client.aclose.assert_awaited_once()
        assert svc._client is None

    def test_disconnect_noop_when_no_client(self):
        """Disconnect is safe when no client exists."""
        svc = GatewayAdminService()
        svc._client = None

        asyncio.get_event_loop().run_until_complete(svc.disconnect())
        # No error


class TestRequest:
    """GatewayAdminService._request"""

    def test_request_returns_json(self):
        """_request returns parsed JSON response."""
        svc, _ = _make_svc_with_mock_client(json_response={"ok": True})
        result = asyncio.get_event_loop().run_until_complete(svc._request("GET", "/test"))
        assert result == {"ok": True}

    def test_request_empty_204_response(self):
        """_request returns {} on 204 No Content."""
        svc, _mock_resp = _make_svc_with_mock_client(status_code=204, content=b"")
        result = asyncio.get_event_loop().run_until_complete(svc._request("GET", "/test"))
        assert result == {}

    def test_request_empty_body(self):
        """_request returns {} when response body is empty."""
        svc, _ = _make_svc_with_mock_client(status_code=200, content=b"")
        result = asyncio.get_event_loop().run_until_complete(svc._request("GET", "/test"))
        assert result == {}


class TestListApis:
    """GatewayAdminService.list_apis"""

    def test_list_apis_returns_api_list(self):
        """list_apis extracts apiResponse from response."""
        svc, _ = _make_svc_with_mock_client(
            json_response={"apiResponse": [{"id": "1", "apiName": "test"}]},
            content=b'{"apiResponse": [{"id": "1", "apiName": "test"}]}',
        )

        result = asyncio.get_event_loop().run_until_complete(svc.list_apis())

        assert len(result) == 1
        assert result[0]["apiName"] == "test"


class TestGetApi:
    """GatewayAdminService.get_api"""

    def test_get_api_extracts_nested_response(self):
        """get_api extracts api from apiResponse.api."""
        svc, _ = _make_svc_with_mock_client(
            json_response={"apiResponse": {"api": {"id": "api-1", "apiName": "Petstore"}}}
        )
        result = asyncio.get_event_loop().run_until_complete(svc.get_api("api-1"))
        assert result["id"] == "api-1"
        assert result["apiName"] == "Petstore"


class TestActivateApi:
    """GatewayAdminService.activate_api"""

    def test_activate_api_calls_put(self):
        """activate_api uses PUT on /apis/{id}/activate."""
        svc, _ = _make_svc_with_mock_client(json_response={"status": "activated"})
        result = asyncio.get_event_loop().run_until_complete(svc.activate_api("api-1"))
        assert result == {"status": "activated"}
        svc._client.request.assert_awaited_once()
        call_args = svc._client.request.call_args
        assert call_args[0] == ("PUT", "/apis/api-1/activate")


class TestDeactivateApi:
    """GatewayAdminService.deactivate_api"""

    def test_deactivate_api_calls_put(self):
        """deactivate_api uses PUT on /apis/{id}/deactivate."""
        svc, _ = _make_svc_with_mock_client(json_response={"status": "deactivated"})
        result = asyncio.get_event_loop().run_until_complete(svc.deactivate_api("api-1"))
        assert result == {"status": "deactivated"}


class TestDeleteApi:
    """GatewayAdminService.delete_api"""

    def test_delete_api_returns_true(self):
        """delete_api returns True on success."""
        svc, _ = _make_svc_with_mock_client(status_code=204, content=b"")
        result = asyncio.get_event_loop().run_until_complete(svc.delete_api("api-1"))
        assert result is True


class TestImportApi:
    """GatewayAdminService.import_api"""

    def test_import_requires_url_or_spec(self):
        """import_api raises when neither url nor spec provided."""
        svc = GatewayAdminService()

        with pytest.raises(ValueError, match="Either openapi_url or openapi_spec"):
            asyncio.get_event_loop().run_until_complete(
                svc.import_api("test-api", "1.0")
            )

    def test_import_with_url(self):
        """import_api sends url in payload."""
        svc, _ = _make_svc_with_mock_client(
            json_response={"apiResponse": {"api": {"id": "new-api"}}}
        )
        result = asyncio.get_event_loop().run_until_complete(
            svc.import_api("test-api", "1.0", openapi_url="http://spec.example.com/api.yaml")
        )
        assert result["apiResponse"]["api"]["id"] == "new-api"
        call_kwargs = svc._client.request.call_args[1]
        assert call_kwargs["json"]["url"] == "http://spec.example.com/api.yaml"

    def test_import_with_spec(self):
        """import_api sends apiDefinition in payload."""
        spec = {"openapi": "3.0.3", "info": {"title": "Test"}}
        svc, _ = _make_svc_with_mock_client(
            json_response={"apiResponse": {"api": {"id": "new-api"}}}
        )
        result = asyncio.get_event_loop().run_until_complete(
            svc.import_api("test-api", "1.0", openapi_spec=spec)
        )
        assert result["apiResponse"]["api"]["id"] == "new-api"
        call_kwargs = svc._client.request.call_args[1]
        assert call_kwargs["json"]["apiDefinition"] == spec


class TestListApplications:
    """GatewayAdminService.list_applications"""

    def test_list_applications_extracts_list(self):
        """list_applications extracts applications key."""
        svc, _ = _make_svc_with_mock_client(
            json_response={"applications": [{"id": "app-1", "name": "test"}]}
        )
        result = asyncio.get_event_loop().run_until_complete(svc.list_applications())
        assert len(result) == 1
        assert result[0]["name"] == "test"


class TestGetApplication:
    """GatewayAdminService.get_application"""

    def test_get_application_returns_full_response(self):
        """get_application returns the full response dict."""
        svc, _ = _make_svc_with_mock_client(
            json_response={"id": "app-1", "name": "myapp"}
        )
        result = asyncio.get_event_loop().run_until_complete(svc.get_application("app-1"))
        assert result["name"] == "myapp"


class TestCreateApplication:
    """GatewayAdminService.create_application"""

    def test_create_application_sends_payload(self):
        """create_application sends correct payload."""
        svc, _ = _make_svc_with_mock_client(json_response={"id": "app-new"})
        result = asyncio.get_event_loop().run_until_complete(
            svc.create_application("myapp", description="test app")
        )
        assert result["id"] == "app-new"
        call_kwargs = svc._client.request.call_args[1]
        assert call_kwargs["json"]["name"] == "myapp"
        assert call_kwargs["json"]["description"] == "test app"

    def test_create_application_default_contact(self):
        """create_application uses default contact email."""
        svc, _ = _make_svc_with_mock_client(json_response={"id": "app-new"})
        asyncio.get_event_loop().run_until_complete(svc.create_application("myapp"))
        call_kwargs = svc._client.request.call_args[1]
        assert call_kwargs["json"]["contactEmails"] == ["admin@gostoa.dev"]


class TestProvisionApplication:
    """GatewayAdminService.provision_application"""

    def test_provision_creates_and_associates(self):
        """provision_application creates app then associates API."""
        svc = GatewayAdminService()
        svc._use_proxy = False
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.content = b'{"id": "gw-app-1"}'
        create_resp.json.return_value = {"id": "gw-app-1"}
        create_resp.raise_for_status = MagicMock()

        assoc_resp = MagicMock()
        assoc_resp.status_code = 200
        assoc_resp.content = b"{}"
        assoc_resp.json.return_value = {}
        assoc_resp.raise_for_status = MagicMock()

        svc._client = AsyncMock()
        svc._client.request = AsyncMock(side_effect=[create_resp, assoc_resp])

        result = asyncio.get_event_loop().run_until_complete(
            svc.provision_application(
                subscription_id="sub-001",
                application_name="billing",
                api_id="api-42",
                tenant_id="acme",
                subscriber_email="dev@acme.com",
                correlation_id="corr-1",
            )
        )
        assert result["app_id"] == "gw-app-1"
        assert svc._client.request.await_count == 2

    def test_provision_nested_app_id(self):
        """provision_application extracts app_id from nested structure."""
        svc = GatewayAdminService()
        svc._use_proxy = False

        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.content = b'{"applications": [{"id": "nested-1"}]}'
        create_resp.json.return_value = {"applications": [{"id": "nested-1"}]}
        create_resp.raise_for_status = MagicMock()

        assoc_resp = MagicMock()
        assoc_resp.status_code = 200
        assoc_resp.content = b"{}"
        assoc_resp.json.return_value = {}
        assoc_resp.raise_for_status = MagicMock()

        svc._client = AsyncMock()
        svc._client.request = AsyncMock(side_effect=[create_resp, assoc_resp])

        result = asyncio.get_event_loop().run_until_complete(
            svc.provision_application(
                subscription_id="sub-002",
                application_name="pay",
                api_id="api-99",
                tenant_id="acme",
                subscriber_email="dev@acme.com",
                correlation_id="corr-2",
            )
        )
        assert result["app_id"] == "nested-1"

    def test_provision_no_app_id_raises(self):
        """provision_application raises when no app_id extracted."""
        svc, _ = _make_svc_with_mock_client(json_response={"nothing": "here"})
        with pytest.raises(RuntimeError, match="Failed to extract app_id"):
            asyncio.get_event_loop().run_until_complete(
                svc.provision_application(
                    subscription_id="sub-003",
                    application_name="broken",
                    api_id="api-1",
                    tenant_id="acme",
                    subscriber_email="dev@acme.com",
                    correlation_id="corr-3",
                )
            )

    def test_provision_cleanup_on_association_failure(self):
        """provision_application deletes app if association fails."""
        svc = GatewayAdminService()
        svc._use_proxy = False

        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.content = b'{"id": "cleanup-app"}'
        create_resp.json.return_value = {"id": "cleanup-app"}
        create_resp.raise_for_status = MagicMock()

        assoc_resp = MagicMock()
        assoc_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("fail", request=MagicMock(), response=MagicMock())
        )

        delete_resp = MagicMock()
        delete_resp.status_code = 204
        delete_resp.content = b""
        delete_resp.json.return_value = {}
        delete_resp.raise_for_status = MagicMock()

        svc._client = AsyncMock()
        svc._client.request = AsyncMock(side_effect=[create_resp, assoc_resp, delete_resp])

        with pytest.raises(httpx.HTTPStatusError):
            asyncio.get_event_loop().run_until_complete(
                svc.provision_application(
                    subscription_id="sub-004",
                    application_name="fail",
                    api_id="api-1",
                    tenant_id="acme",
                    subscriber_email="dev@acme.com",
                    correlation_id="corr-4",
                )
            )
        assert svc._client.request.await_count == 3


class TestDeprovisionApplication:
    """GatewayAdminService.deprovision_application"""

    def test_deprovision_returns_true(self):
        """deprovision_application returns True."""
        svc, _ = _make_svc_with_mock_client(status_code=204, content=b"")
        result = asyncio.get_event_loop().run_until_complete(
            svc.deprovision_application("app-1", correlation_id="corr-5")
        )
        assert result is True


class TestListAliases:
    """GatewayAdminService.list_aliases"""

    def test_list_aliases_extracts_list(self):
        """list_aliases extracts alias key."""
        svc, _ = _make_svc_with_mock_client(
            json_response={"alias": [{"name": "my-alias"}]}
        )
        result = asyncio.get_event_loop().run_until_complete(svc.list_aliases())
        assert len(result) == 1
        assert result[0]["name"] == "my-alias"


class TestCreateEndpointAlias:
    """GatewayAdminService.create_endpoint_alias"""

    def test_create_alias_sends_payload(self):
        """create_endpoint_alias sends correct payload."""
        svc, _ = _make_svc_with_mock_client(json_response={"name": "backend-alias"})
        result = asyncio.get_event_loop().run_until_complete(
            svc.create_endpoint_alias("backend-alias", "http://backend:8080")
        )
        assert result["name"] == "backend-alias"
        call_kwargs = svc._client.request.call_args[1]
        assert call_kwargs["json"]["endPointURI"] == "http://backend:8080"
        assert call_kwargs["json"]["type"] == "endpoint"


class TestListScopes:
    """GatewayAdminService.list_scopes"""

    def test_list_scopes_extracts_list(self):
        """list_scopes extracts scopes key."""
        svc, _ = _make_svc_with_mock_client(
            json_response={"scopes": [{"scopeName": "openid"}]}
        )
        result = asyncio.get_event_loop().run_until_complete(svc.list_scopes())
        assert len(result) == 1
        assert result[0]["scopeName"] == "openid"


class TestCreateScopeMapping:
    """GatewayAdminService.create_scope_mapping"""

    def test_create_scope_sends_payload(self):
        """create_scope_mapping sends correct payload."""
        svc, _ = _make_svc_with_mock_client(json_response={"scopeName": "KC:tenant:api:v1:openid"})
        result = asyncio.get_event_loop().run_until_complete(
            svc.create_scope_mapping(
                scope_name="KC:tenant:api:v1:openid",
                description="OpenID scope",
                audience="cp-api",
                api_ids=["api-1"],
            )
        )
        assert result["scopeName"] == "KC:tenant:api:v1:openid"
        call_kwargs = svc._client.request.call_args[1]
        assert call_kwargs["json"]["audience"] == "cp-api"
        assert call_kwargs["json"]["apiScopes"] == ["api-1"]


class TestListStrategies:
    """GatewayAdminService.list_strategies"""

    def test_list_strategies_extracts_list(self):
        """list_strategies extracts strategies key."""
        svc, _ = _make_svc_with_mock_client(
            json_response={"strategies": [{"name": "OIDC-acme"}]}
        )
        result = asyncio.get_event_loop().run_until_complete(svc.list_strategies())
        assert len(result) == 1
        assert result[0]["name"] == "OIDC-acme"


class TestCreateOAuthStrategy:
    """GatewayAdminService.create_oauth_strategy"""

    def test_create_strategy_sends_payload(self):
        """create_oauth_strategy sends correct payload."""
        svc, _ = _make_svc_with_mock_client(json_response={"name": "OIDC-acme-billing"})
        result = asyncio.get_event_loop().run_until_complete(
            svc.create_oauth_strategy(
                name="OIDC-acme-billing",
                auth_server_alias="KeycloakOIDC",
                client_id="my-client",
                audience="cp-api",
            )
        )
        assert result["name"] == "OIDC-acme-billing"
        call_kwargs = svc._client.request.call_args[1]
        assert call_kwargs["json"]["type"] == "OAUTH2"
        assert call_kwargs["json"]["clientId"] == "my-client"


class TestHealthCheck:
    """GatewayAdminService.health_check"""

    def test_health_check_returns_status(self):
        """health_check returns the full response."""
        svc, _ = _make_svc_with_mock_client(json_response={"status": "healthy"})
        result = asyncio.get_event_loop().run_until_complete(svc.health_check())
        assert result["status"] == "healthy"


class TestConfigureApiOidc:
    """GatewayAdminService.configure_api_oidc"""

    def test_configure_oidc_full_flow(self):
        """configure_api_oidc creates strategy, app, and 4 scopes."""
        svc = GatewayAdminService()
        svc._use_proxy = False

        responses = []
        for _i in range(6):
            resp = MagicMock()
            resp.status_code = 200
            resp.content = b'{"ok": true}'
            resp.json.return_value = {"ok": True}
            resp.raise_for_status = MagicMock()
            responses.append(resp)

        svc._client = AsyncMock()
        svc._client.request = AsyncMock(side_effect=responses)

        result = asyncio.get_event_loop().run_until_complete(
            svc.configure_api_oidc(
                tenant_id="acme",
                api_name="billing",
                api_version="1.0",
                api_id="api-42",
                client_id="kc-client",
            )
        )
        assert result["strategy"] is not None
        assert result["application"] is not None
        assert len(result["scopes"]) == 4
        assert svc._client.request.await_count == 6

    def test_configure_oidc_handles_409_conflict(self):
        """configure_api_oidc handles 409 Conflict (resource exists)."""
        svc = GatewayAdminService()
        svc._use_proxy = False

        responses = []
        for _ in range(6):
            resp = MagicMock()
            resp.status_code = 409
            resp.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "Conflict",
                    request=MagicMock(),
                    response=MagicMock(status_code=409),
                )
            )
            responses.append(resp)

        svc._client = AsyncMock()
        svc._client.request = AsyncMock(side_effect=responses)

        result = asyncio.get_event_loop().run_until_complete(
            svc.configure_api_oidc(
                tenant_id="acme",
                api_name="billing",
                api_version="1.0",
                api_id="api-42",
                client_id="kc-client",
            )
        )
        assert result["strategy"] is None
        assert result["application"] is None
        assert result["scopes"] == []


class TestGetClient:
    """GatewayAdminService._get_client context manager"""

    @patch("src.services.gateway_service.settings")
    def test_proxy_requires_token(self, mock_settings):
        """OIDC proxy mode raises without JWT token."""
        mock_settings.GATEWAY_USE_OIDC_PROXY = True
        mock_settings.GATEWAY_ADMIN_PROXY_URL = "http://proxy:8080"

        svc = GatewayAdminService()

        with pytest.raises(ValueError, match="JWT token required"):
            asyncio.get_event_loop().run_until_complete(svc._request("GET", "/apis"))

    @patch("src.services.gateway_service.settings")
    def test_basic_auth_requires_connect(self, mock_settings):
        """Basic Auth mode raises if not connected."""
        mock_settings.GATEWAY_USE_OIDC_PROXY = False

        svc = GatewayAdminService()
        svc._client = None

        with pytest.raises(RuntimeError, match="not connected"):
            asyncio.get_event_loop().run_until_complete(svc._request("GET", "/apis"))


class TestInit:
    """GatewayAdminService.__init__"""

    @patch("src.services.gateway_service.settings")
    def test_init_defaults(self, mock_settings):
        """Default init uses settings.GATEWAY_USE_OIDC_PROXY."""
        mock_settings.GATEWAY_USE_OIDC_PROXY = False
        svc = GatewayAdminService()
        assert svc._use_proxy is False
        assert svc._client is None
        assert svc._base_url is None

    @patch("src.services.gateway_service.settings")
    def test_init_custom_base_url(self, mock_settings):
        """Custom base_url is stored."""
        mock_settings.GATEWAY_USE_OIDC_PROXY = False
        svc = GatewayAdminService(base_url="http://custom:9999")
        assert svc._base_url == "http://custom:9999"

    @patch("src.services.gateway_service.settings")
    def test_init_auth_config_overrides_proxy(self, mock_settings):
        """auth_config type overrides settings.GATEWAY_USE_OIDC_PROXY."""
        mock_settings.GATEWAY_USE_OIDC_PROXY = False
        svc = GatewayAdminService(auth_config={"type": "oidc_proxy", "proxy_url": "http://proxy:8080"})
        assert svc._use_proxy is True
