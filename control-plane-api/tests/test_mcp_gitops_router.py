"""Tests for MCP GitOps Router — CAB-1378 / CAB-1890

Endpoints:
- POST /v1/mcp/gitops/sync (full sync)
- POST /v1/mcp/gitops/sync/tenant/{tenant_id}
- POST /v1/mcp/gitops/sync/server/{tenant_id}/{server_name}
- GET /v1/mcp/gitops/status
- GET /v1/mcp/gitops/git/health
- GET /v1/mcp/gitops/git/servers

Auth: require_admin (cpi-admin only, inline check).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.services.git_provider import get_git_provider


@pytest.fixture()
def mock_git_provider():
    """Create a mock GitProvider with _project attribute."""
    mock = MagicMock()
    mock._project = MagicMock()
    mock.is_connected = MagicMock(return_value=True)
    mock.connect = AsyncMock()
    mock.get_repo_info = AsyncMock(
        return_value={
            "name": "stoa-mcp-servers",
            "default_branch": "main",
            "url": "https://github.com/stoa-platform/stoa-catalog",
            "visibility": "private",
        }
    )
    mock.list_all_mcp_servers = AsyncMock(return_value=[])
    return mock


@pytest.fixture()
def app_with_git_provider(app_with_cpi_admin, mock_git_provider):
    """App with cpi-admin auth and git provider DI override."""
    app_with_cpi_admin.dependency_overrides[get_git_provider] = lambda: mock_git_provider
    yield app_with_cpi_admin
    # dependency_overrides.clear() is already called by app_with_cpi_admin teardown


class TestMCPGitOpsRouter:
    """Test suite for MCP GitOps endpoints."""

    def _mock_sync_result(self, **overrides):
        """Create a mock sync result matching SyncResponse fields."""
        mock = MagicMock()
        defaults = {
            "success": True,
            "servers_synced": 3,
            "servers_created": 1,
            "servers_updated": 2,
            "servers_orphaned": 0,
            "errors": [],
        }
        for k, v in {**defaults, **overrides}.items():
            setattr(mock, k, v)
        return mock

    # ============== POST /sync (full sync) ==============

    def test_full_sync_success(self, app_with_git_provider, mock_db_session, mock_git_provider):
        """POST /sync triggers full GitOps sync (cpi-admin)."""
        mock_result = self._mock_sync_result()

        with patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc:
            MockSyncSvc.return_value.sync_all_servers = AsyncMock(return_value=mock_result)

            with TestClient(app_with_git_provider) as client:
                response = client.post("/v1/mcp/gitops/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["servers_synced"] == 3

    def test_full_sync_connects_if_needed(self, app_with_git_provider, mock_db_session, mock_git_provider):
        """POST /sync connects to git provider if not already connected."""
        mock_result = self._mock_sync_result()
        mock_git_provider._project = None
        mock_git_provider.is_connected.return_value = False

        with patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc:
            MockSyncSvc.return_value.sync_all_servers = AsyncMock(return_value=mock_result)

            with TestClient(app_with_git_provider) as client:
                response = client.post("/v1/mcp/gitops/sync")

        assert response.status_code == 200
        mock_git_provider.connect.assert_awaited_once()

    def test_full_sync_500_on_error(self, app_with_git_provider, mock_db_session, mock_git_provider):
        """POST /sync returns 500 when sync fails."""
        with patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc:
            MockSyncSvc.return_value.sync_all_servers = AsyncMock(
                side_effect=Exception("Git provider connection failed")
            )

            with TestClient(app_with_git_provider, raise_server_exceptions=False) as client:
                response = client.post("/v1/mcp/gitops/sync")

        assert response.status_code == 500

    # ============== POST /sync/tenant/{tenant_id} ==============

    def test_tenant_sync_success(self, app_with_git_provider, mock_db_session, mock_git_provider):
        """POST /sync/tenant/{id} syncs tenant-specific servers."""
        mock_result = self._mock_sync_result(servers_synced=1, servers_created=0, servers_updated=1)

        with patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc:
            MockSyncSvc.return_value.sync_tenant_servers = AsyncMock(return_value=mock_result)

            with TestClient(app_with_git_provider) as client:
                response = client.post("/v1/mcp/gitops/sync/tenant/acme")

        assert response.status_code == 200
        data = response.json()
        assert data["servers_updated"] == 1

    # ============== POST /sync/server/{tenant_id}/{server_name} ==============

    def test_server_sync_success(self, app_with_git_provider, mock_db_session, mock_git_provider):
        """POST /sync/server/{t}/{s} syncs a specific server."""
        mock_server = MagicMock()

        with patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc:
            MockSyncSvc.return_value.sync_server = AsyncMock(return_value=mock_server)

            with TestClient(app_with_git_provider) as client:
                response = client.post("/v1/mcp/gitops/sync/server/acme/linear-mcp")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["servers_synced"] == 1

    def test_server_sync_not_found(self, app_with_git_provider, mock_db_session, mock_git_provider):
        """POST /sync/server/{t}/{s} returns failure when server not in git."""
        with patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc:
            MockSyncSvc.return_value.sync_server = AsyncMock(return_value=None)

            with TestClient(app_with_git_provider) as client:
                response = client.post("/v1/mcp/gitops/sync/server/acme/nonexistent")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    # ============== GET /status ==============

    def test_get_sync_status_success(self, app_with_git_provider, mock_db_session, mock_git_provider):
        """GET /status returns sync status summary."""
        mock_status = {
            "total_servers": 10,
            "synced": 8,
            "pending": 1,
            "error": 1,
            "orphan": 0,
            "untracked": 0,
            "last_sync_at": "2026-02-18T14:00:00",
            "errors": [],
        }

        with patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc:
            MockSyncSvc.return_value.get_sync_status = AsyncMock(return_value=mock_status)

            with TestClient(app_with_git_provider) as client:
                response = client.get("/v1/mcp/gitops/status")

        assert response.status_code == 200
        data = response.json()
        assert data["total_servers"] == 10
        assert data["synced"] == 8

    # ============== GET /git/health ==============

    def test_git_health_success(self, app_with_git_provider, mock_git_provider):
        """GET /git/health returns healthy status."""
        with TestClient(app_with_git_provider) as client:
            response = client.get("/v1/mcp/gitops/git/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["project"] == "stoa-mcp-servers"

    def test_git_health_unhealthy(self, app_with_git_provider, mock_git_provider):
        """GET /git/health returns unhealthy when provider is down."""
        mock_git_provider._project = None
        mock_git_provider.is_connected.return_value = False
        mock_git_provider.connect = AsyncMock(side_effect=Exception("Connection refused"))

        with TestClient(app_with_git_provider, raise_server_exceptions=False) as client:
            response = client.get("/v1/mcp/gitops/git/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"

    # ============== GET /git/servers ==============

    def test_list_git_servers_success(self, app_with_git_provider, mock_git_provider):
        """GET /git/servers lists servers from git provider."""
        mock_servers = [
            {
                "name": "linear-mcp",
                "tenant_id": "_platform",
                "display_name": "Linear",
                "category": "project-management",
                "status": "active",
                "tools": [{"name": "create_issue"}],
                "git_path": "platform/linear-mcp/config.yaml",
            },
        ]
        mock_git_provider.list_all_mcp_servers = AsyncMock(return_value=mock_servers)

        with TestClient(app_with_git_provider) as client:
            response = client.get("/v1/mcp/gitops/git/servers")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["servers"][0]["name"] == "linear-mcp"
        assert data["servers"][0]["tools_count"] == 1

    # ============== RBAC ==============

    def test_sync_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """POST /sync returns 403 for tenant-admin (admin only)."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post("/v1/mcp/gitops/sync")

        assert response.status_code == 403

    def test_status_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """GET /status returns 403 for tenant-admin."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/mcp/gitops/status")

        assert response.status_code == 403
