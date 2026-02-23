"""Tests for tenant-scoped MCP servers router (CAB-1319).

Covers RBAC, CRUD, tenant isolation, test-connection, sync-tools, and tool toggle.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


# ============== Helpers ==============


def _mock_server(**kwargs):
    """Create a mock ExternalMCPServer."""
    srv = MagicMock()
    srv.id = kwargs.get("id", uuid4())
    srv.name = kwargs.get("name", "acme--my-linear")
    srv.display_name = kwargs.get("display_name", "My Linear")
    srv.description = kwargs.get("description", "Linear integration")
    srv.icon = kwargs.get("icon", None)
    srv.base_url = kwargs.get("base_url", "https://mcp.linear.app/sse")
    srv.transport = MagicMock(value=kwargs.get("transport", "sse"))
    srv.auth_type = MagicMock(value=kwargs.get("auth_type", "bearer_token"))
    srv.credential_vault_path = kwargs.get("credential_vault_path", "secret/data/external-mcp-servers/test")
    srv.tool_prefix = kwargs.get("tool_prefix", "linear")
    srv.enabled = kwargs.get("enabled", True)
    srv.health_status = MagicMock(value=kwargs.get("health_status", "unknown"))
    srv.last_health_check = kwargs.get("last_health_check", None)
    srv.last_sync_at = kwargs.get("last_sync_at", None)
    srv.sync_error = kwargs.get("sync_error", None)
    srv.tenant_id = kwargs.get("tenant_id", "acme")
    srv.created_at = kwargs.get("created_at", datetime.utcnow())
    srv.updated_at = kwargs.get("updated_at", datetime.utcnow())
    srv.created_by = kwargs.get("created_by", "tenant-admin-user-id")
    srv.tools = kwargs.get("tools", [])
    return srv


def _mock_tool(**kwargs):
    """Create a mock ExternalMCPServerTool."""
    tool = MagicMock()
    tool.id = kwargs.get("id", uuid4())
    tool.name = kwargs.get("name", "create_issue")
    tool.namespaced_name = kwargs.get("namespaced_name", "linear__create_issue")
    tool.display_name = kwargs.get("display_name", "Create Issue")
    tool.description = kwargs.get("description", "Creates a Linear issue")
    tool.input_schema = kwargs.get("input_schema", {"type": "object"})
    tool.enabled = kwargs.get("enabled", True)
    tool.synced_at = kwargs.get("synced_at", datetime.utcnow())
    return tool


# ============== Fixtures ==============


@pytest.fixture
def app_with_devops(app, mock_db_session):
    """App with devops user auth for tenant 'acme'."""
    from src.auth.dependencies import get_current_user
    from src.database import get_db

    from tests.conftest import User

    devops_user = User(
        id="devops-user-id",
        email="devops@acme.com",
        username="devops-user",
        roles=["devops"],
        tenant_id="acme",
    )

    async def override_get_current_user():
        return devops_user

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
def app_with_viewer(app, mock_db_session):
    """App with viewer user auth for tenant 'acme'."""
    from src.auth.dependencies import get_current_user
    from src.database import get_db

    from tests.conftest import User

    viewer_user = User(
        id="viewer-user-id",
        email="viewer@acme.com",
        username="viewer-user",
        roles=["viewer"],
        tenant_id="acme",
    )

    async def override_get_current_user():
        return viewer_user

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    yield app

    app.dependency_overrides.clear()


# ============== Tests: List Servers ==============


class TestListTenantMCPServers:
    """Tests for GET /v1/tenants/{tenant_id}/mcp-servers."""

    def test_tenant_admin_can_list(self, app_with_tenant_admin, mock_db_session):
        server = _mock_server()
        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.list_by_tenant = AsyncMock(return_value=([server], 1))

            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/tenants/acme/mcp-servers")

            assert resp.status_code == 200
            data = resp.json()
            assert data["total_count"] == 1
            assert len(data["servers"]) == 1
            # Name should be stripped of tenant prefix
            assert data["servers"][0]["name"] == "my-linear"

    def test_viewer_can_list(self, app_with_viewer, mock_db_session):
        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

            with TestClient(app_with_viewer) as client:
                resp = client.get("/v1/tenants/acme/mcp-servers")

            assert resp.status_code == 200

    def test_devops_can_list(self, app_with_devops, mock_db_session):
        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

            with TestClient(app_with_devops) as client:
                resp = client.get("/v1/tenants/acme/mcp-servers")

            assert resp.status_code == 200

    def test_other_tenant_denied(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get("/v1/tenants/acme/mcp-servers")
        assert resp.status_code == 403

    def test_cpi_admin_can_list_any_tenant(self, app_with_cpi_admin, mock_db_session):
        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/tenants/acme/mcp-servers")

            assert resp.status_code == 200

    def test_pagination(self, app_with_tenant_admin, mock_db_session):
        servers = [_mock_server(name=f"acme--srv-{i}") for i in range(3)]
        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.list_by_tenant = AsyncMock(return_value=(servers, 10))

            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/tenants/acme/mcp-servers?page=2&page_size=3")

            assert resp.status_code == 200
            data = resp.json()
            assert data["page"] == 2
            assert data["page_size"] == 3
            assert data["total_count"] == 10


# ============== Tests: Get Server ==============


class TestGetTenantMCPServer:
    """Tests for GET /v1/tenants/{tenant_id}/mcp-servers/{server_id}."""

    def test_get_server_with_tools(self, app_with_tenant_admin, mock_db_session):
        tool = _mock_tool()
        server = _mock_server(tools=[tool])

        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.get(f"/v1/tenants/acme/mcp-servers/{server.id}")

            assert resp.status_code == 200
            data = resp.json()
            assert data["display_name"] == "My Linear"
            assert len(data["tools"]) == 1
            assert data["has_credentials"] is True

    def test_get_server_not_found(self, app_with_tenant_admin, mock_db_session):
        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.get(f"/v1/tenants/acme/mcp-servers/{uuid4()}")

            assert resp.status_code == 404

    def test_server_from_other_tenant_returns_404(self, app_with_tenant_admin, mock_db_session):
        """Tenant isolation: server belonging to other-tenant returns 404, not 403."""
        server = _mock_server(tenant_id="other-tenant")

        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.get(f"/v1/tenants/acme/mcp-servers/{server.id}")

            assert resp.status_code == 404

    def test_no_credentials_has_credentials_false(self, app_with_tenant_admin, mock_db_session):
        server = _mock_server(credential_vault_path=None)

        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.get(f"/v1/tenants/acme/mcp-servers/{server.id}")

            assert resp.status_code == 200
            assert resp.json()["has_credentials"] is False


# ============== Tests: Create Server ==============


class TestCreateTenantMCPServer:
    """Tests for POST /v1/tenants/{tenant_id}/mcp-servers."""

    def test_tenant_admin_can_create(self, app_with_tenant_admin, mock_db_session):
        server = _mock_server()

        with (
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo,
            patch("src.routers.tenant_mcp_servers.get_vault_client") as mock_vault_fn,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_tenant_and_name = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=server)
            mock_vault = MagicMock()
            mock_vault.store_credential = AsyncMock(return_value="secret/data/...")
            mock_vault_fn.return_value = mock_vault

            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(
                    "/v1/tenants/acme/mcp-servers",
                    json={
                        "display_name": "My Linear",
                        "base_url": "https://mcp.linear.app/sse",
                        "transport": "sse",
                        "auth_type": "bearer_token",
                        "credentials": {"bearer_token": "lin_api_xxx"},
                        "tool_prefix": "linear",
                    },
                )

            assert resp.status_code == 201
            mock_repo.create.assert_awaited_once()

    def test_viewer_cannot_create(self, app_with_viewer, mock_db_session):
        with TestClient(app_with_viewer) as client:
            resp = client.post(
                "/v1/tenants/acme/mcp-servers",
                json={
                    "display_name": "My Linear",
                    "base_url": "https://mcp.linear.app/sse",
                },
            )
        assert resp.status_code == 403

    def test_devops_cannot_create(self, app_with_devops, mock_db_session):
        with TestClient(app_with_devops) as client:
            resp = client.post(
                "/v1/tenants/acme/mcp-servers",
                json={
                    "display_name": "My Linear",
                    "base_url": "https://mcp.linear.app/sse",
                },
            )
        assert resp.status_code == 403

    def test_duplicate_name_returns_409(self, app_with_tenant_admin, mock_db_session):
        existing = _mock_server()

        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_tenant_and_name = AsyncMock(return_value=existing)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(
                    "/v1/tenants/acme/mcp-servers",
                    json={
                        "display_name": "My Linear",
                        "base_url": "https://mcp.linear.app/sse",
                    },
                )

            assert resp.status_code == 409

    def test_create_without_credentials(self, app_with_tenant_admin, mock_db_session):
        server = _mock_server(auth_type="none", credential_vault_path=None)

        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_tenant_and_name = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=server)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(
                    "/v1/tenants/acme/mcp-servers",
                    json={
                        "display_name": "Public Server",
                        "base_url": "https://public-mcp.example.com",
                        "auth_type": "none",
                    },
                )

            assert resp.status_code == 201

    def test_other_tenant_cannot_create(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.post(
                "/v1/tenants/acme/mcp-servers",
                json={
                    "display_name": "My Linear",
                    "base_url": "https://mcp.linear.app/sse",
                },
            )
        assert resp.status_code == 403


# ============== Tests: Update Server ==============


class TestUpdateTenantMCPServer:
    """Tests for PUT /v1/tenants/{tenant_id}/mcp-servers/{server_id}."""

    def test_tenant_admin_can_update(self, app_with_tenant_admin, mock_db_session):
        server = _mock_server()

        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)
            mock_repo.update = AsyncMock(return_value=server)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.put(
                    f"/v1/tenants/acme/mcp-servers/{server.id}",
                    json={"display_name": "Updated Linear"},
                )

            assert resp.status_code == 200

    def test_viewer_cannot_update(self, app_with_viewer, mock_db_session):
        with TestClient(app_with_viewer) as client:
            resp = client.put(
                f"/v1/tenants/acme/mcp-servers/{uuid4()}",
                json={"display_name": "Updated"},
            )
        assert resp.status_code == 403

    def test_update_not_found(self, app_with_tenant_admin, mock_db_session):
        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.put(
                    f"/v1/tenants/acme/mcp-servers/{uuid4()}",
                    json={"display_name": "Updated"},
                )

            assert resp.status_code == 404

    def test_update_with_credentials(self, app_with_tenant_admin, mock_db_session):
        server = _mock_server()

        with (
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo,
            patch("src.routers.tenant_mcp_servers.get_vault_client") as mock_vault_fn,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)
            mock_repo.update = AsyncMock(return_value=server)
            mock_vault = MagicMock()
            mock_vault.store_credential = AsyncMock(return_value="secret/data/...")
            mock_vault_fn.return_value = mock_vault

            with TestClient(app_with_tenant_admin) as client:
                resp = client.put(
                    f"/v1/tenants/acme/mcp-servers/{server.id}",
                    json={
                        "credentials": {"bearer_token": "new_token"},
                    },
                )

            assert resp.status_code == 200
            mock_vault.store_credential.assert_awaited_once()


# ============== Tests: Delete Server ==============


class TestDeleteTenantMCPServer:
    """Tests for DELETE /v1/tenants/{tenant_id}/mcp-servers/{server_id}."""

    def test_tenant_admin_can_delete(self, app_with_tenant_admin, mock_db_session):
        server = _mock_server()

        with (
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo,
            patch("src.routers.tenant_mcp_servers.get_vault_client") as mock_vault_fn,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)
            mock_repo.delete = AsyncMock()
            mock_vault = MagicMock()
            mock_vault.delete_credential = AsyncMock(return_value=True)
            mock_vault_fn.return_value = mock_vault

            with TestClient(app_with_tenant_admin) as client:
                resp = client.delete(f"/v1/tenants/acme/mcp-servers/{server.id}")

            assert resp.status_code == 204
            mock_repo.delete.assert_awaited_once()
            mock_vault.delete_credential.assert_awaited_once()

    def test_viewer_cannot_delete(self, app_with_viewer, mock_db_session):
        with TestClient(app_with_viewer) as client:
            resp = client.delete(f"/v1/tenants/acme/mcp-servers/{uuid4()}")
        assert resp.status_code == 403

    def test_delete_not_found(self, app_with_tenant_admin, mock_db_session):
        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.delete(f"/v1/tenants/acme/mcp-servers/{uuid4()}")

            assert resp.status_code == 404

    def test_delete_vault_failure_continues(self, app_with_tenant_admin, mock_db_session):
        """Vault cleanup failure should not prevent server deletion."""
        server = _mock_server()

        with (
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo,
            patch("src.routers.tenant_mcp_servers.get_vault_client") as mock_vault_fn,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)
            mock_repo.delete = AsyncMock()
            mock_vault = MagicMock()
            mock_vault.delete_credential = AsyncMock(side_effect=Exception("Vault down"))
            mock_vault_fn.return_value = mock_vault

            with TestClient(app_with_tenant_admin) as client:
                resp = client.delete(f"/v1/tenants/acme/mcp-servers/{server.id}")

            assert resp.status_code == 204
            mock_repo.delete.assert_awaited_once()


# ============== Tests: Test Connection ==============


class TestTestConnection:
    """Tests for POST /v1/tenants/{tenant_id}/mcp-servers/{server_id}/test-connection."""

    def test_tenant_admin_can_test(self, app_with_tenant_admin, mock_db_session):
        server = _mock_server()
        mock_result = MagicMock(
            success=True, latency_ms=42, error=None, server_info={"name": "linear"}, tools_discovered=5,
        )

        with (
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo,
            patch("src.routers.tenant_mcp_servers.get_vault_client") as mock_vault_fn,
            patch("src.routers.tenant_mcp_servers.get_mcp_client_service") as mock_mcp_fn,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)
            mock_repo.update_health_status = AsyncMock(return_value=server)
            mock_vault = MagicMock()
            mock_vault.retrieve_credential = AsyncMock(return_value={"bearer_token": "test"})
            mock_vault_fn.return_value = mock_vault
            mock_mcp = MagicMock()
            mock_mcp.test_connection = AsyncMock(return_value=mock_result)
            mock_mcp_fn.return_value = mock_mcp

            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/tenants/acme/mcp-servers/{server.id}/test-connection")

            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["latency_ms"] == 42

    def test_devops_can_test(self, app_with_devops, mock_db_session):
        server = _mock_server()
        mock_result = MagicMock(
            success=True, latency_ms=10, error=None, server_info=None, tools_discovered=0,
        )

        with (
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo,
            patch("src.routers.tenant_mcp_servers.get_vault_client") as mock_vault_fn,
            patch("src.routers.tenant_mcp_servers.get_mcp_client_service") as mock_mcp_fn,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)
            mock_repo.update_health_status = AsyncMock(return_value=server)
            mock_vault = MagicMock()
            mock_vault.retrieve_credential = AsyncMock(return_value={"bearer_token": "test"})
            mock_vault_fn.return_value = mock_vault
            mock_mcp = MagicMock()
            mock_mcp.test_connection = AsyncMock(return_value=mock_result)
            mock_mcp_fn.return_value = mock_mcp

            with TestClient(app_with_devops) as client:
                resp = client.post(f"/v1/tenants/acme/mcp-servers/{server.id}/test-connection")

            assert resp.status_code == 200

    def test_viewer_cannot_test(self, app_with_viewer, mock_db_session):
        server = _mock_server()

        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)

            with TestClient(app_with_viewer) as client:
                resp = client.post(f"/v1/tenants/acme/mcp-servers/{server.id}/test-connection")

            assert resp.status_code == 403

    def test_connection_failure(self, app_with_tenant_admin, mock_db_session):
        server = _mock_server(credential_vault_path=None, auth_type="none")
        mock_result = MagicMock(
            success=False, latency_ms=None, error="Connection refused", server_info=None, tools_discovered=None,
        )

        with (
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo,
            patch("src.routers.tenant_mcp_servers.get_mcp_client_service") as mock_mcp_fn,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)
            mock_repo.update_health_status = AsyncMock(return_value=server)
            mock_mcp = MagicMock()
            mock_mcp.test_connection = AsyncMock(return_value=mock_result)
            mock_mcp_fn.return_value = mock_mcp

            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/tenants/acme/mcp-servers/{server.id}/test-connection")

            assert resp.status_code == 200
            assert resp.json()["success"] is False
            assert resp.json()["error"] == "Connection refused"


# ============== Tests: Sync Tools ==============


class TestSyncTools:
    """Tests for POST /v1/tenants/{tenant_id}/mcp-servers/{server_id}/sync-tools."""

    def test_tenant_admin_can_sync(self, app_with_tenant_admin, mock_db_session):
        tool = _mock_tool()
        server = _mock_server(tools=[tool])
        mock_discovered = MagicMock(name="create_issue", description="Creates an issue", input_schema={})

        with (
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo,
            patch("src.routers.tenant_mcp_servers.get_vault_client") as mock_vault_fn,
            patch("src.routers.tenant_mcp_servers.get_mcp_client_service") as mock_mcp_fn,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=server)
            mock_repo.sync_tools = AsyncMock(return_value=(1, 0))
            mock_vault = MagicMock()
            mock_vault.retrieve_credential = AsyncMock(return_value={"bearer_token": "test"})
            mock_vault_fn.return_value = mock_vault
            mock_mcp = MagicMock()
            mock_mcp.list_tools = AsyncMock(return_value=[mock_discovered])
            mock_mcp_fn.return_value = mock_mcp

            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/tenants/acme/mcp-servers/{server.id}/sync-tools")

            assert resp.status_code == 200
            data = resp.json()
            assert data["synced_count"] == 1
            assert data["removed_count"] == 0

    def test_viewer_cannot_sync(self, app_with_viewer, mock_db_session):
        with TestClient(app_with_viewer) as client:
            resp = client.post(f"/v1/tenants/acme/mcp-servers/{uuid4()}/sync-tools")
        assert resp.status_code == 403

    def test_devops_cannot_sync(self, app_with_devops, mock_db_session):
        with TestClient(app_with_devops) as client:
            resp = client.post(f"/v1/tenants/acme/mcp-servers/{uuid4()}/sync-tools")
        assert resp.status_code == 403

    def test_sync_server_not_found(self, app_with_tenant_admin, mock_db_session):
        with patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/tenants/acme/mcp-servers/{uuid4()}/sync-tools")

            assert resp.status_code == 404


# ============== Tests: Toggle Tool ==============


class TestToggleTool:
    """Tests for PATCH /v1/tenants/{tenant_id}/mcp-servers/{server_id}/tools/{tool_id}."""

    def test_tenant_admin_can_toggle(self, app_with_tenant_admin, mock_db_session):
        server = _mock_server()
        tool = _mock_tool(enabled=False)

        with (
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockServerRepo,
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerToolRepository") as MockToolRepo,
        ):
            mock_server_repo = MockServerRepo.return_value
            mock_server_repo.get_by_id = AsyncMock(return_value=server)
            mock_tool_repo = MockToolRepo.return_value
            mock_tool_repo.update_enabled = AsyncMock(return_value=tool)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.patch(
                    f"/v1/tenants/acme/mcp-servers/{server.id}/tools/{tool.id}",
                    json={"enabled": False},
                )

            assert resp.status_code == 200
            assert resp.json()["enabled"] is False

    def test_viewer_cannot_toggle(self, app_with_viewer, mock_db_session):
        with TestClient(app_with_viewer) as client:
            resp = client.patch(
                f"/v1/tenants/acme/mcp-servers/{uuid4()}/tools/{uuid4()}",
                json={"enabled": True},
            )
        assert resp.status_code == 403

    def test_toggle_tool_not_found(self, app_with_tenant_admin, mock_db_session):
        server = _mock_server()

        with (
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerRepository") as MockServerRepo,
            patch("src.routers.tenant_mcp_servers.ExternalMCPServerToolRepository") as MockToolRepo,
        ):
            mock_server_repo = MockServerRepo.return_value
            mock_server_repo.get_by_id = AsyncMock(return_value=server)
            mock_tool_repo = MockToolRepo.return_value
            mock_tool_repo.update_enabled = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                resp = client.patch(
                    f"/v1/tenants/acme/mcp-servers/{server.id}/tools/{uuid4()}",
                    json={"enabled": True},
                )

            assert resp.status_code == 404


# ============== Tests: Name Scoping ==============


class TestNameScoping:
    """Tests for the name scoping helper functions."""

    def test_make_scoped_name(self):
        from src.routers.tenant_mcp_servers import _make_scoped_name

        assert _make_scoped_name("acme", "My Linear") == "acme--my-linear"
        assert _make_scoped_name("tenant-x", "GitHub MCP") == "tenant-x--github-mcp"
        assert _make_scoped_name("acme", "  Spaces  ") == "acme--spaces"
        assert _make_scoped_name("acme", "Special!@#Chars") == "acme--special-chars"

    def test_strip_scoped_name(self):
        from src.routers.tenant_mcp_servers import _strip_scoped_name

        assert _strip_scoped_name("acme--my-linear", "acme") == "my-linear"
        assert _strip_scoped_name("other--my-linear", "acme") == "other--my-linear"
        assert _strip_scoped_name("acme--", "acme") == ""
