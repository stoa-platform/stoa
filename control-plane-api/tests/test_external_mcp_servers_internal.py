"""Tests for external MCP servers internal endpoint — X-Gateway-Key auth."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

VALID_KEY = "test_key_123"
INTERNAL_URL = "/v1/internal/external-mcp-servers"
GW_KEY_HEADER = "X-Gateway-Key"


class TestExternalMCPServersInternal:
    """GET /v1/internal/external-mcp-servers"""

    def test_valid_key_returns_200(self, client):
        """Valid gateway key returns servers list."""
        with (
            patch("src.routers.external_mcp_servers.settings") as mock_settings,
            patch("src.routers.external_mcp_servers.ExternalMCPServerRepository") as MockRepo,
            patch("src.routers.external_mcp_servers.get_vault_client"),
        ):

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.list_enabled_with_tools = AsyncMock(return_value=[])

            resp = client.get(
                INTERNAL_URL,
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            assert resp.json()["servers"] == []

    def test_missing_header_returns_422(self, client):
        """Missing X-Gateway-Key header returns 422 validation error."""
        resp = client.get(INTERNAL_URL)
        assert resp.status_code == 422

    def test_invalid_key_returns_401(self, client):
        """Invalid gateway key is rejected with 401."""
        with patch("src.routers.external_mcp_servers.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = [VALID_KEY]

            resp = client.get(
                INTERNAL_URL,
                headers={GW_KEY_HEADER: "wrong_key"},
            )

            assert resp.status_code == 401
            assert "Invalid gateway key" in resp.json()["detail"]

    def test_no_keys_configured_returns_503(self, client):
        """Empty GATEWAY_API_KEYS returns 503."""
        with patch("src.routers.external_mcp_servers.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = []

            resp = client.get(
                INTERNAL_URL,
                headers={GW_KEY_HEADER: "any_key"},
            )

            assert resp.status_code == 503
            assert "not configured" in resp.json()["detail"].lower()

    def test_returns_servers_with_tools(self, client):
        """Valid key returns servers with their tools."""
        server_mock = MagicMock()
        server_mock.id = uuid4()
        server_mock.name = "test-server"
        server_mock.base_url = "https://mcp.example.com"
        server_mock.transport = MagicMock(value="sse")
        server_mock.auth_type = MagicMock(value="none")
        server_mock.credential_vault_path = None
        server_mock.tool_prefix = "test"
        server_mock.tenant_id = "acme"

        tool_mock = MagicMock()
        tool_mock.id = uuid4()
        tool_mock.name = "get_data"
        tool_mock.namespaced_name = "test_get_data"
        tool_mock.display_name = "Get Data"
        tool_mock.description = "Fetch data"
        tool_mock.input_schema = {"type": "object"}
        tool_mock.enabled = True
        server_mock.tools = [tool_mock]

        with (
            patch("src.routers.external_mcp_servers.settings") as mock_settings,
            patch("src.routers.external_mcp_servers.ExternalMCPServerRepository") as MockRepo,
            patch("src.routers.external_mcp_servers.get_vault_client"),
        ):

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.list_enabled_with_tools = AsyncMock(return_value=[server_mock])

            resp = client.get(
                INTERNAL_URL,
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert len(data["servers"]) == 1
            assert data["servers"][0]["name"] == "test-server"
            assert len(data["servers"][0]["tools"]) == 1
            assert data["servers"][0]["tools"][0]["name"] == "get_data"
