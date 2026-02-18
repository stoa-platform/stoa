"""Unit tests for GatewayAdminService — CAB-1378

Tests the webMethods Gateway admin service HTTP wrapper.
Covers both OIDC proxy and Basic Auth modes.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.gateway_service import GatewayAdminService


class TestConnect:
    """GatewayAdminService.connect"""

    @patch("src.services.gateway_service.settings")
    def test_connect_basic_auth(self, mock_settings):
        """Basic Auth mode creates a persistent client."""
        mock_settings.GATEWAY_USE_OIDC_PROXY = False
        mock_settings.GATEWAY_URL = "http://gateway:5555"
        mock_settings.GATEWAY_ADMIN_USER = "admin"
        mock_settings.GATEWAY_ADMIN_PASSWORD = "manage"

        import asyncio

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

        import asyncio

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

        import asyncio

        asyncio.get_event_loop().run_until_complete(svc.disconnect())

        mock_client.aclose.assert_awaited_once()
        assert svc._client is None

    def test_disconnect_noop_when_no_client(self):
        """Disconnect is safe when no client exists."""
        svc = GatewayAdminService()
        svc._client = None

        import asyncio

        asyncio.get_event_loop().run_until_complete(svc.disconnect())
        # No error


class TestListApis:
    """GatewayAdminService.list_apis"""

    def test_list_apis_returns_api_list(self):
        """list_apis extracts apiResponse from response."""
        svc = GatewayAdminService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"apiResponse": [{"id": "1", "apiName": "test"}]}'
        mock_response.json.return_value = {"apiResponse": [{"id": "1", "apiName": "test"}]}
        mock_response.raise_for_status = MagicMock()

        svc._client = AsyncMock()
        svc._client.request = AsyncMock(return_value=mock_response)
        svc._use_proxy = False

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(svc.list_apis())

        assert len(result) == 1
        assert result[0]["apiName"] == "test"


class TestImportApi:
    """GatewayAdminService.import_api"""

    def test_import_requires_url_or_spec(self):
        """import_api raises when neither url nor spec provided."""
        svc = GatewayAdminService()

        import asyncio

        with pytest.raises(ValueError, match="Either openapi_url or openapi_spec"):
            asyncio.get_event_loop().run_until_complete(
                svc.import_api("test-api", "1.0")
            )


class TestGetClient:
    """GatewayAdminService._get_client context manager"""

    @patch("src.services.gateway_service.settings")
    def test_proxy_requires_token(self, mock_settings):
        """OIDC proxy mode raises without JWT token."""
        mock_settings.GATEWAY_USE_OIDC_PROXY = True
        mock_settings.GATEWAY_ADMIN_PROXY_URL = "http://proxy:8080"

        svc = GatewayAdminService()

        import asyncio

        with pytest.raises(ValueError, match="JWT token required"):
            asyncio.get_event_loop().run_until_complete(svc._request("GET", "/apis"))

    @patch("src.services.gateway_service.settings")
    def test_basic_auth_requires_connect(self, mock_settings):
        """Basic Auth mode raises if not connected."""
        mock_settings.GATEWAY_USE_OIDC_PROXY = False

        svc = GatewayAdminService()
        svc._client = None

        import asyncio

        with pytest.raises(RuntimeError, match="not connected"):
            asyncio.get_event_loop().run_until_complete(svc._request("GET", "/apis"))
