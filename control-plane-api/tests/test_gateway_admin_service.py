"""Tests for GatewayAdminService (CAB-1291)"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.gateway_service import GatewayAdminService


def _mock_settings(**overrides):
    s = MagicMock()
    s.GATEWAY_URL = overrides.get("GATEWAY_URL", "http://localhost:5555")
    s.GATEWAY_ADMIN_USER = overrides.get("GATEWAY_ADMIN_USER", "admin")
    s.GATEWAY_ADMIN_PASSWORD = overrides.get("GATEWAY_ADMIN_PASSWORD", "manage")
    s.GATEWAY_USE_OIDC_PROXY = overrides.get("GATEWAY_USE_OIDC_PROXY", False)
    s.GATEWAY_ADMIN_PROXY_URL = overrides.get("GATEWAY_ADMIN_PROXY_URL", "http://proxy:8080")
    return s


# ── Init ──


class TestInit:
    def test_defaults(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
        assert svc._client is None
        assert svc._use_proxy is False

    def test_explicit_proxy(self):
        svc = GatewayAdminService(auth_config={"type": "oidc_proxy", "proxy_url": "http://proxy"})
        assert svc._use_proxy is True

    def test_explicit_basic(self):
        svc = GatewayAdminService(auth_config={"type": "basic"})
        assert svc._use_proxy is False

    def test_custom_base_url(self):
        svc = GatewayAdminService(base_url="http://custom:5555")
        assert svc._base_url == "http://custom:5555"


# ── connect / disconnect ──


class TestConnect:
    async def test_basic_auth(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            await svc.connect()
        assert svc._client is not None
        await svc.disconnect()
        assert svc._client is None

    async def test_proxy_noop(self):
        svc = GatewayAdminService(auth_config={"type": "oidc_proxy", "proxy_url": "http://proxy"})
        await svc.connect()
        assert svc._client is None


class TestDisconnect:
    async def test_no_client(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            await svc.disconnect()
        assert svc._client is None


# ── _get_client ──


class TestGetClient:
    async def test_proxy_requires_token(self):
        svc = GatewayAdminService(auth_config={"type": "oidc_proxy", "proxy_url": "http://proxy"})
        with pytest.raises(ValueError, match="JWT token required"):
            async with svc._get_client():
                pass

    async def test_proxy_with_token(self):
        svc = GatewayAdminService(auth_config={"type": "oidc_proxy", "proxy_url": "http://proxy"})
        async with svc._get_client(auth_token="test-jwt") as client:
            assert client is not None

    async def test_basic_auth_not_connected(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
        with pytest.raises(RuntimeError, match="not connected"):
            async with svc._get_client():
                pass

    async def test_basic_auth_connected(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            await svc.connect()
            async with svc._get_client() as client:
                assert client is svc._client
            await svc.disconnect()


# ── _request ──


class TestRequest:
    async def test_json_response(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b'{"key": "value"}'
            mock_response.json.return_value = {"key": "value"}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)

            with patch.object(svc, "_get_client") as mock_get:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_get.return_value = mock_ctx
                result = await svc._request("GET", "/test")
            assert result == {"key": "value"}

    async def test_empty_response(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            mock_response = MagicMock()
            mock_response.status_code = 204
            mock_response.content = b""
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)

            with patch.object(svc, "_get_client") as mock_get:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_get.return_value = mock_ctx
                result = await svc._request("DELETE", "/test")
            assert result == {}


# ── API Operations ──


class TestAPIOperations:
    async def test_list_apis(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"apiResponse": [{"id": "1"}]})
            result = await svc.list_apis()
            assert result == [{"id": "1"}]

    async def test_get_api(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"apiResponse": {"api": {"id": "1"}}})
            result = await svc.get_api("1")
            assert result == {"id": "1"}

    async def test_activate_api(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={})
            result = await svc.activate_api("api-1")
            svc._request.assert_awaited_once_with("PUT", "/apis/api-1/activate", auth_token=None)

    async def test_deactivate_api(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={})
            result = await svc.deactivate_api("api-1")
            svc._request.assert_awaited_once_with("PUT", "/apis/api-1/deactivate", auth_token=None)

    async def test_delete_api(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={})
            result = await svc.delete_api("api-1")
            assert result is True

    async def test_import_api_url(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"apiResponse": {"api": {"id": "new-1"}}})
            result = await svc.import_api("Test", "1.0", openapi_url="http://example.com/spec.json")
            assert "apiResponse" in result

    async def test_import_api_spec(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"apiResponse": {"api": {"id": "new-2"}}})
            result = await svc.import_api("Test", "1.0", openapi_spec={"openapi": "3.0.0"})
            assert "apiResponse" in result

    async def test_import_api_no_source(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            with pytest.raises(ValueError, match="Either openapi_url or openapi_spec"):
                await svc.import_api("Test", "1.0")


# ── Application Operations ──


class TestApplicationOperations:
    async def test_list_applications(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"applications": [{"id": "app-1"}]})
            result = await svc.list_applications()
            assert result == [{"id": "app-1"}]

    async def test_get_application(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"id": "app-1"})
            result = await svc.get_application("app-1")
            assert result["id"] == "app-1"

    async def test_create_application(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"id": "app-new"})
            result = await svc.create_application("test-app")
            assert result["id"] == "app-new"

    async def test_provision_application(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc.create_application = AsyncMock(return_value={"id": "app-new"})
            svc._request = AsyncMock(return_value={})
            result = await svc.provision_application(
                "sub-1", "my-app", "api-1", "acme", "user@example.com", "corr-1"
            )
            assert result["app_id"] == "app-new"

    async def test_provision_nested_response(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc.create_application = AsyncMock(return_value={"applications": [{"id": "app-nest"}]})
            svc._request = AsyncMock(return_value={})
            result = await svc.provision_application(
                "sub-1", "my-app", "api-1", "acme", "user@example.com", "corr-1"
            )
            assert result["app_id"] == "app-nest"

    async def test_provision_no_id_raises(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc.create_application = AsyncMock(return_value={})
            with pytest.raises(RuntimeError, match="Failed to extract app_id"):
                await svc.provision_application(
                    "sub-1", "my-app", "api-1", "acme", "user@example.com", "corr-1"
                )

    async def test_provision_associate_fails_cleanup(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc.create_application = AsyncMock(return_value={"id": "app-fail"})
            svc._request = AsyncMock(side_effect=Exception("associate failed"))
            with pytest.raises(Exception, match="associate failed"):
                await svc.provision_application(
                    "sub-1", "my-app", "api-1", "acme", "user@example.com", "corr-1"
                )

    async def test_deprovision(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={})
            result = await svc.deprovision_application("app-1", "corr-1")
            assert result is True


# ── Alias Operations ──


class TestAliasOperations:
    async def test_list_aliases(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"alias": [{"name": "ep1"}]})
            result = await svc.list_aliases()
            assert result == [{"name": "ep1"}]

    async def test_create_endpoint_alias(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"name": "ep1"})
            result = await svc.create_endpoint_alias("ep1", "http://backend:8080")
            assert result["name"] == "ep1"


# ── Scope Operations ──


class TestScopeOperations:
    async def test_list_scopes(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"scopes": [{"name": "openid"}]})
            result = await svc.list_scopes()
            assert result == [{"name": "openid"}]

    async def test_create_scope_mapping(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"scopeName": "test"})
            result = await svc.create_scope_mapping("test", "desc", "", ["api-1"])
            assert result["scopeName"] == "test"


# ── Strategy Operations ──


class TestStrategyOperations:
    async def test_list_strategies(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"strategies": [{"name": "s1"}]})
            result = await svc.list_strategies()
            assert result == [{"name": "s1"}]

    async def test_create_oauth_strategy(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"name": "s1"})
            result = await svc.create_oauth_strategy("s1", "KC", "client-1", "aud")
            assert result["name"] == "s1"


# ── Health Check ──


class TestHealthCheck:
    async def test_health(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc._request = AsyncMock(return_value={"status": "ok"})
            result = await svc.health_check()
            assert result["status"] == "ok"


# ── configure_api_oidc ──


class TestConfigureApiOidc:
    async def test_full_config(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc.create_oauth_strategy = AsyncMock(return_value={"name": "strat"})
            svc.create_application = AsyncMock(return_value={"id": "app-1"})
            svc.create_scope_mapping = AsyncMock(return_value={"scopeName": "scope"})

            result = await svc.configure_api_oidc(
                "acme", "Weather", "1.0", "api-1", "client-1"
            )
            assert result["strategy"] is not None
            assert result["application"] is not None
            assert len(result["scopes"]) == 4  # openid, profile, email, roles

    async def test_strategy_already_exists(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            mock_response = MagicMock()
            mock_response.status_code = 409
            svc.create_oauth_strategy = AsyncMock(
                side_effect=httpx.HTTPStatusError("409", request=MagicMock(), response=mock_response)
            )
            svc.create_application = AsyncMock(return_value={"id": "app-1"})
            svc.create_scope_mapping = AsyncMock(return_value={"scopeName": "s"})

            result = await svc.configure_api_oidc(
                "acme", "Weather", "1.0", "api-1", "client-1"
            )
            assert result["strategy"] is None
            assert result["application"] is not None

    async def test_app_already_exists(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc.create_oauth_strategy = AsyncMock(return_value={"name": "s"})
            mock_response = MagicMock()
            mock_response.status_code = 409
            svc.create_application = AsyncMock(
                side_effect=httpx.HTTPStatusError("409", request=MagicMock(), response=mock_response)
            )
            svc.create_scope_mapping = AsyncMock(return_value={"scopeName": "s"})

            result = await svc.configure_api_oidc(
                "acme", "Weather", "1.0", "api-1", "client-1"
            )
            assert result["application"] is None

    async def test_scope_already_exists(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            svc.create_oauth_strategy = AsyncMock(return_value={"name": "s"})
            svc.create_application = AsyncMock(return_value={"id": "app-1"})
            mock_response = MagicMock()
            mock_response.status_code = 409
            svc.create_scope_mapping = AsyncMock(
                side_effect=httpx.HTTPStatusError("409", request=MagicMock(), response=mock_response)
            )

            result = await svc.configure_api_oidc(
                "acme", "Weather", "1.0", "api-1", "client-1"
            )
            assert result["scopes"] == []

    async def test_non_409_raises(self):
        with patch("src.services.gateway_service.settings", _mock_settings()):
            svc = GatewayAdminService()
            mock_response = MagicMock()
            mock_response.status_code = 500
            svc.create_oauth_strategy = AsyncMock(
                side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)
            )

            with pytest.raises(httpx.HTTPStatusError):
                await svc.configure_api_oidc(
                    "acme", "Weather", "1.0", "api-1", "client-1"
                )
