"""Tests for External MCP Servers Admin Router — CAB-1378

Endpoints:
- GET /v1/admin/external-mcp-servers (list)
- POST /v1/admin/external-mcp-servers (create, 201)
- GET /v1/admin/external-mcp-servers/{server_id} (detail + tools)
- PUT /v1/admin/external-mcp-servers/{server_id} (update)
- DELETE /v1/admin/external-mcp-servers/{server_id} (204)
- POST /v1/admin/external-mcp-servers/{server_id}/test-connection
- POST /v1/admin/external-mcp-servers/{server_id}/sync-tools
- PATCH /v1/admin/external-mcp-servers/{server_id}/tools/{tool_id}
- GET /v1/internal/external-mcp-servers (gateway internal)

Auth: get_current_user + _require_admin (cpi-admin or tenant-admin).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

REPO_PATH = "src.routers.external_mcp_servers.ExternalMCPServerRepository"
TOOL_REPO_PATH = "src.routers.external_mcp_servers.ExternalMCPServerToolRepository"
VAULT_PATH = "src.routers.external_mcp_servers.get_vault_client"
MCP_CLIENT_PATH = "src.routers.external_mcp_servers.get_mcp_client_service"

BASE = "/v1/admin/external-mcp-servers"
INTERNAL_BASE = "/v1/internal/external-mcp-servers"


def _mock_server(**overrides):
    """Create a mock ExternalMCPServer matching _convert_server_to_response fields."""
    mock = MagicMock()
    transport_mock = MagicMock()
    transport_mock.value = "sse"
    auth_mock = MagicMock()
    auth_mock.value = "none"
    health_mock = MagicMock()
    health_mock.value = "unknown"

    defaults = {
        "id": uuid4(),
        "name": "linear-mcp",
        "display_name": "Linear",
        "description": "Linear issue tracking",
        "icon": None,
        "base_url": "https://mcp.linear.app/sse",
        "transport": transport_mock,
        "auth_type": auth_mock,
        "tool_prefix": "linear",
        "enabled": True,
        "health_status": health_mock,
        "last_health_check": None,
        "last_sync_at": None,
        "sync_error": None,
        "tenant_id": "acme",
        "tools": [],
        "credential_vault_path": None,
        "created_at": datetime(2026, 2, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 2, 1, tzinfo=UTC),
        "created_by": "admin-user-id",
    }
    for k, v in {**defaults, **overrides}.items():
        setattr(mock, k, v)
    return mock


def _mock_tool(**overrides):
    """Create a mock ExternalMCPServerTool."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "name": "create_issue",
        "namespaced_name": "linear__create_issue",
        "display_name": "Create Issue",
        "description": "Create a Linear issue",
        "input_schema": {"type": "object"},
        "enabled": True,
        "synced_at": datetime(2026, 2, 1, tzinfo=UTC),
    }
    for k, v in {**defaults, **overrides}.items():
        setattr(mock, k, v)
    return mock


class TestListServers:
    """GET /v1/admin/external-mcp-servers"""

    def test_list_servers_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        """CPI admin sees all servers."""
        items = [_mock_server()]

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.list_all = AsyncMock(return_value=(items, 1))

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(BASE)

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["servers"]) == 1

    def test_list_servers_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin sees own + platform servers."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.list_all = AsyncMock(return_value=([], 0))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(BASE)

        assert response.status_code == 200

    def test_list_servers_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        """Viewer gets 403 (not cpi-admin or tenant-admin)."""
        with TestClient(app_with_no_tenant_user) as client:
            response = client.get(BASE)

        assert response.status_code == 403


class TestCreateServer:
    """POST /v1/admin/external-mcp-servers"""

    def test_create_server_success(self, app_with_cpi_admin, mock_db_session):
        """CPI admin creates a new server (201)."""
        mock_srv = _mock_server()

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_name = AsyncMock(return_value=None)
            MockRepo.return_value.create = AsyncMock(return_value=mock_srv)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    BASE,
                    json={
                        "name": "linear-mcp",
                        "display_name": "Linear",
                        "base_url": "https://mcp.linear.app/sse",
                    },
                )

        assert response.status_code == 201

    def test_create_server_409_duplicate(self, app_with_cpi_admin, mock_db_session):
        """Returns 409 when name already exists."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_name = AsyncMock(return_value=_mock_server())

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    BASE,
                    json={
                        "name": "linear-mcp",
                        "display_name": "Linear",
                        "base_url": "https://mcp.linear.app/sse",
                    },
                )

        assert response.status_code == 409


class TestGetServer:
    """GET /v1/admin/external-mcp-servers/{server_id}"""

    def test_get_server_detail(self, app_with_cpi_admin, mock_db_session):
        """Returns server detail with tools."""
        server_id = uuid4()
        tool = _mock_tool()
        mock_srv = _mock_server(id=server_id, tools=[tool])

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"{BASE}/{server_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data["tools"]) == 1
        assert data["tools"][0]["name"] == "create_issue"

    def test_get_server_404(self, app_with_cpi_admin, mock_db_session):
        """Returns 404 when not found."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"{BASE}/{uuid4()}")

        assert response.status_code == 404


class TestUpdateServer:
    """PUT /v1/admin/external-mcp-servers/{server_id}"""

    def test_update_server_success(self, app_with_cpi_admin, mock_db_session):
        """Updates server fields."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockRepo.return_value.update = AsyncMock(return_value=mock_srv)

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    f"{BASE}/{server_id}",
                    json={"display_name": "Updated Linear"},
                )

        assert response.status_code == 200


class TestDeleteServer:
    """DELETE /v1/admin/external-mcp-servers/{server_id}"""

    def test_delete_server_success(self, app_with_cpi_admin, mock_db_session):
        """Deletes server (204)."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockRepo.return_value.delete = AsyncMock()

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"{BASE}/{server_id}")

        assert response.status_code == 204

    def test_delete_server_404(self, app_with_cpi_admin, mock_db_session):
        """Returns 404 when not found."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"{BASE}/{uuid4()}")

        assert response.status_code == 404


class TestTestConnection:
    """POST /v1/admin/external-mcp-servers/{server_id}/test-connection"""

    def test_test_connection_success(self, app_with_cpi_admin, mock_db_session):
        """Successful connection test updates health."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 42
        mock_result.error = None
        mock_result.server_info = {"version": "1.0"}
        mock_result.tools_discovered = 5

        with (
            patch(REPO_PATH) as MockRepo,
            patch(MCP_CLIENT_PATH) as MockMCPClient,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockRepo.return_value.update_health_status = AsyncMock()
            MockMCPClient.return_value.test_connection = AsyncMock(return_value=mock_result)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"{BASE}/{server_id}/test-connection")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["latency_ms"] == 42


class TestSyncTools:
    """POST /v1/admin/external-mcp-servers/{server_id}/sync-tools"""

    def test_sync_tools_success(self, app_with_cpi_admin, mock_db_session):
        """Discovers and syncs tools from external server."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id, tools=[_mock_tool()])
        # Second call after sync returns server with tools
        mock_srv_refreshed = _mock_server(id=server_id, tools=[_mock_tool()])

        mock_discovered = MagicMock()
        mock_discovered.name = "create_issue"
        mock_discovered.description = "Create issue"
        mock_discovered.input_schema = {"type": "object"}

        with (
            patch(REPO_PATH) as MockRepo,
            patch(MCP_CLIENT_PATH) as MockMCPClient,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(side_effect=[mock_srv, mock_srv_refreshed])
            MockRepo.return_value.sync_tools = AsyncMock(return_value=(1, 0))
            MockMCPClient.return_value.list_tools = AsyncMock(return_value=[mock_discovered])

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"{BASE}/{server_id}/sync-tools")

        assert response.status_code == 200
        data = response.json()
        assert data["synced_count"] == 1
        assert data["removed_count"] == 0


class TestUpdateTool:
    """PATCH /v1/admin/external-mcp-servers/{server_id}/tools/{tool_id}"""

    def test_update_tool_enabled(self, app_with_cpi_admin, mock_db_session):
        """Enables/disables a tool."""
        server_id = uuid4()
        tool_id = uuid4()
        mock_srv = _mock_server(id=server_id)
        mock_t = _mock_tool(id=tool_id, enabled=False)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(TOOL_REPO_PATH) as MockToolRepo,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockToolRepo.return_value.update_enabled = AsyncMock(return_value=mock_t)

            with TestClient(app_with_cpi_admin) as client:
                response = client.patch(
                    f"{BASE}/{server_id}/tools/{tool_id}",
                    json={"enabled": False},
                )

        assert response.status_code == 200

    def test_update_tool_404(self, app_with_cpi_admin, mock_db_session):
        """Returns 404 when tool not found."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(TOOL_REPO_PATH) as MockToolRepo,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockToolRepo.return_value.update_enabled = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.patch(
                    f"{BASE}/{server_id}/tools/{uuid4()}",
                    json={"enabled": True},
                )

        assert response.status_code == 404


class TestInternalGatewayEndpoint:
    """GET /v1/internal/external-mcp-servers"""

    def test_list_for_gateway_success(self, app_with_cpi_admin, mock_db_session):
        """Internal endpoint returns enabled servers with credentials."""
        tool = _mock_tool()
        mock_srv = _mock_server(tools=[tool])

        with (
            patch(REPO_PATH) as MockRepo,
            patch(VAULT_PATH) as MockVault,
            patch("src.routers.external_mcp_servers.settings") as mock_settings,
        ):
            mock_settings.gateway_api_keys_list = ["test_key"]
            MockRepo.return_value.list_enabled_with_tools = AsyncMock(return_value=[mock_srv])
            MockVault.return_value.retrieve_credential = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(
                    INTERNAL_BASE,
                    headers={"X-Gateway-Key": "test_key"},
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data["servers"]) == 1

    def test_internal_endpoint_invalid_key_401(self, app_with_cpi_admin, mock_db_session):
        """Returns 401 for invalid gateway key."""
        with patch("src.routers.external_mcp_servers.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = ["valid_key"]

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(
                    INTERNAL_BASE,
                    headers={"X-Gateway-Key": "wrong_key"},
                )

        assert response.status_code == 401

    def test_internal_endpoint_no_keys_configured_503(self, app_with_cpi_admin, mock_db_session):
        """Returns 503 when gateway_api_keys_list is empty."""
        with patch("src.routers.external_mcp_servers.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = []

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(
                    INTERNAL_BASE,
                    headers={"X-Gateway-Key": "any"},
                )

        assert response.status_code == 503

    def test_internal_endpoint_vault_failure_still_returns(self, app_with_cpi_admin, mock_db_session):
        """Vault failure for credentials doesn't block gateway list."""
        auth_mock = MagicMock()
        auth_mock.value = "bearer_token"
        mock_srv = _mock_server(
            credential_vault_path="/v1/secret/data/srv-1",
            auth_type=auth_mock,
        )

        with (
            patch(REPO_PATH) as MockRepo,
            patch(VAULT_PATH) as MockVault,
            patch("src.routers.external_mcp_servers.settings") as mock_settings,
        ):
            mock_settings.gateway_api_keys_list = ["test_key"]
            MockRepo.return_value.list_enabled_with_tools = AsyncMock(return_value=[mock_srv])
            MockVault.return_value.retrieve_credential = AsyncMock(side_effect=Exception("vault down"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(
                    INTERNAL_BASE,
                    headers={"X-Gateway-Key": "test_key"},
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data["servers"]) == 1
        assert data["servers"][0]["credentials"] is None


# ============ Vault Credential Paths ============


class TestVaultCredentials:
    """Tests for vault credential storage/retrieval across endpoints."""

    def test_create_server_with_vault_credentials(self, app_with_cpi_admin, mock_db_session):
        """Create server stores credentials in vault."""
        mock_srv = _mock_server()

        with (
            patch(REPO_PATH) as MockRepo,
            patch(VAULT_PATH) as MockVault,
        ):
            MockRepo.return_value.get_by_name = AsyncMock(return_value=None)
            MockRepo.return_value.create = AsyncMock(return_value=mock_srv)
            MockVault.return_value.store_credential = AsyncMock(return_value="/v1/secret/data/srv-1")

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    BASE,
                    json={
                        "name": "secure-mcp",
                        "display_name": "Secure MCP",
                        "base_url": "https://mcp.secure.dev/sse",
                        "auth_type": "bearer_token",
                        "credentials": {"bearer_token": "secret-token"},
                    },
                )

        assert response.status_code == 201

    def test_create_server_vault_failure_500(self, app_with_cpi_admin, mock_db_session):
        """Vault failure during create returns 500."""
        with (
            patch(REPO_PATH) as MockRepo,
            patch(VAULT_PATH) as MockVault,
        ):
            MockRepo.return_value.get_by_name = AsyncMock(return_value=None)
            MockVault.return_value.store_credential = AsyncMock(side_effect=Exception("vault unavailable"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    BASE,
                    json={
                        "name": "secure-mcp",
                        "display_name": "Secure MCP",
                        "base_url": "https://mcp.secure.dev/sse",
                        "auth_type": "bearer_token",
                        "credentials": {"bearer_token": "secret-token"},
                    },
                )

        assert response.status_code == 500
        assert "credentials" in response.json()["detail"].lower()

    def test_update_server_with_vault_credentials(self, app_with_cpi_admin, mock_db_session):
        """Update server stores new credentials in vault."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(VAULT_PATH) as MockVault,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockRepo.return_value.update = AsyncMock(return_value=mock_srv)
            MockVault.return_value.store_credential = AsyncMock(return_value="/v1/secret/data/srv")

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    f"{BASE}/{server_id}",
                    json={"credentials": {"bearer_token": "new-secret"}},
                )

        assert response.status_code == 200

    def test_update_server_vault_failure_500(self, app_with_cpi_admin, mock_db_session):
        """Vault failure during update returns 500."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(VAULT_PATH) as MockVault,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockVault.return_value.store_credential = AsyncMock(side_effect=Exception("vault down"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    f"{BASE}/{server_id}",
                    json={"credentials": {"bearer_token": "secret"}},
                )

        assert response.status_code == 500
        assert "credentials" in response.json()["detail"].lower()

    def test_delete_server_with_vault_cleanup(self, app_with_cpi_admin, mock_db_session):
        """Delete server cleans up vault credentials."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id, credential_vault_path="/v1/secret/data/srv")

        with (
            patch(REPO_PATH) as MockRepo,
            patch(VAULT_PATH) as MockVault,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockRepo.return_value.delete = AsyncMock()
            MockVault.return_value.delete_credential = AsyncMock()

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"{BASE}/{server_id}")

        assert response.status_code == 204
        MockVault.return_value.delete_credential.assert_awaited_once()

    def test_delete_server_vault_failure_still_deletes(self, app_with_cpi_admin, mock_db_session):
        """Vault cleanup failure does not block server deletion."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id, credential_vault_path="/v1/secret/data/srv")

        with (
            patch(REPO_PATH) as MockRepo,
            patch(VAULT_PATH) as MockVault,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockRepo.return_value.delete = AsyncMock()
            MockVault.return_value.delete_credential = AsyncMock(side_effect=Exception("vault error"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"{BASE}/{server_id}")

        assert response.status_code == 204

    def test_test_connection_with_vault_creds(self, app_with_cpi_admin, mock_db_session):
        """Test connection retrieves credentials from vault."""
        server_id = uuid4()
        auth_mock = MagicMock()
        auth_mock.value = "bearer_token"
        mock_srv = _mock_server(
            id=server_id,
            credential_vault_path="/v1/secret/data/srv",
            auth_type=auth_mock,
        )

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 30
        mock_result.error = None
        mock_result.server_info = {}
        mock_result.tools_discovered = 3

        with (
            patch(REPO_PATH) as MockRepo,
            patch(VAULT_PATH) as MockVault,
            patch(MCP_CLIENT_PATH) as MockMCPClient,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockRepo.return_value.update_health_status = AsyncMock()
            MockVault.return_value.retrieve_credential = AsyncMock(return_value={"token": "secret"})
            MockMCPClient.return_value.test_connection = AsyncMock(return_value=mock_result)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"{BASE}/{server_id}/test-connection")

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_test_connection_vault_failure_returns_error(self, app_with_cpi_admin, mock_db_session):
        """Vault failure during test-connection returns error without 500."""
        server_id = uuid4()
        auth_mock = MagicMock()
        auth_mock.value = "bearer_token"
        mock_srv = _mock_server(
            id=server_id,
            credential_vault_path="/v1/secret/data/srv",
            auth_type=auth_mock,
        )

        with (
            patch(REPO_PATH) as MockRepo,
            patch(VAULT_PATH) as MockVault,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockVault.return_value.retrieve_credential = AsyncMock(side_effect=Exception("vault down"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"{BASE}/{server_id}/test-connection")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "credentials" in data["error"].lower()

    def test_sync_tools_vault_failure_500(self, app_with_cpi_admin, mock_db_session):
        """Vault failure during sync-tools returns 500."""
        server_id = uuid4()
        auth_mock = MagicMock()
        auth_mock.value = "bearer_token"
        mock_srv = _mock_server(
            id=server_id,
            credential_vault_path="/v1/secret/data/srv",
            auth_type=auth_mock,
        )

        with (
            patch(REPO_PATH) as MockRepo,
            patch(VAULT_PATH) as MockVault,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockVault.return_value.retrieve_credential = AsyncMock(side_effect=Exception("vault down"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"{BASE}/{server_id}/sync-tools")

        assert response.status_code == 500


# ============ Tenant Access Denied ============


class TestTenantAccessDenied:
    """Tests for tenant access control via _has_tenant_access."""

    def test_get_server_access_denied_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot access platform-wide server (tenant_id=None)."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id, tenant_id=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"{BASE}/{server_id}")

        assert response.status_code == 403

    def test_update_server_access_denied(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot update platform-wide server."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id, tenant_id=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)

            with TestClient(app_with_tenant_admin) as client:
                response = client.put(f"{BASE}/{server_id}", json={"display_name": "New"})

        assert response.status_code == 403

    def test_delete_server_access_denied(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot delete platform-wide server."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id, tenant_id=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"{BASE}/{server_id}")

        assert response.status_code == 403

    def test_create_server_platform_wide_denied_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot create platform-wide server (tenant_id=null)."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                BASE,
                json={
                    "name": "platform-mcp",
                    "display_name": "Platform",
                    "base_url": "https://mcp.example.com/sse",
                    "tenant_id": None,
                },
            )

        assert response.status_code == 403

    def test_test_connection_access_denied(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot test-connection on platform-wide server."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id, tenant_id=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(f"{BASE}/{server_id}/test-connection")

        assert response.status_code == 403

    def test_sync_tools_access_denied(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot sync-tools on platform-wide server."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id, tenant_id=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(f"{BASE}/{server_id}/sync-tools")

        assert response.status_code == 403

    def test_update_tool_access_denied(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot update tool on platform-wide server."""
        server_id = uuid4()
        tool_id = uuid4()
        mock_srv = _mock_server(id=server_id, tenant_id=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"{BASE}/{server_id}/tools/{tool_id}",
                    json={"enabled": True},
                )

        assert response.status_code == 403


# ============ Error Paths ============


class TestErrorPaths:
    """Tests for database and service error handling."""

    def test_create_server_db_failure_500(self, app_with_cpi_admin, mock_db_session):
        """Database failure during create returns 500."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_name = AsyncMock(return_value=None)
            MockRepo.return_value.create = AsyncMock(side_effect=Exception("db error"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    BASE,
                    json={
                        "name": "test-mcp",
                        "display_name": "Test",
                        "base_url": "https://mcp.test.dev/sse",
                    },
                )

        assert response.status_code == 500

    def test_update_server_db_failure_500(self, app_with_cpi_admin, mock_db_session):
        """Database failure during update returns 500."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockRepo.return_value.update = AsyncMock(side_effect=Exception("db error"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    f"{BASE}/{server_id}",
                    json={"display_name": "Updated"},
                )

        assert response.status_code == 500

    def test_delete_server_db_failure_500(self, app_with_cpi_admin, mock_db_session):
        """Database failure during delete returns 500."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockRepo.return_value.delete = AsyncMock(side_effect=Exception("db error"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"{BASE}/{server_id}")

        assert response.status_code == 500

    def test_sync_tools_discovery_failure_sets_error(self, app_with_cpi_admin, mock_db_session):
        """Failed tool discovery sets sync_error on server."""
        server_id = uuid4()
        mock_srv = _mock_server(id=server_id)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(MCP_CLIENT_PATH) as MockMCPClient,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_srv)
            MockRepo.return_value.set_sync_error = AsyncMock()
            MockMCPClient.return_value.list_tools = AsyncMock(side_effect=Exception("connection refused"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"{BASE}/{server_id}/sync-tools")

        assert response.status_code == 500
        MockRepo.return_value.set_sync_error.assert_awaited_once()

    def test_test_connection_404(self, app_with_cpi_admin, mock_db_session):
        """Test connection on non-existent server returns 404."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"{BASE}/{uuid4()}/test-connection")

        assert response.status_code == 404

    def test_sync_tools_404(self, app_with_cpi_admin, mock_db_session):
        """Sync tools on non-existent server returns 404."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"{BASE}/{uuid4()}/sync-tools")

        assert response.status_code == 404

    def test_update_server_404(self, app_with_cpi_admin, mock_db_session):
        """Update non-existent server returns 404."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(f"{BASE}/{uuid4()}", json={"display_name": "New"})

        assert response.status_code == 404

    def test_update_tool_server_404(self, app_with_cpi_admin, mock_db_session):
        """Update tool on non-existent server returns 404."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.patch(
                    f"{BASE}/{uuid4()}/tools/{uuid4()}",
                    json={"enabled": True},
                )

        assert response.status_code == 404
