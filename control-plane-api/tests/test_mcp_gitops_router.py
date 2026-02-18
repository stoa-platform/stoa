"""Tests for MCP GitOps Router — CAB-1378

Endpoints:
- POST /v1/mcp/gitops/sync (full sync)
- POST /v1/mcp/gitops/sync/tenant/{tenant_id}
- POST /v1/mcp/gitops/sync/server/{tenant_id}/{server_name}
- GET /v1/mcp/gitops/status
- GET /v1/mcp/gitops/gitlab/health
- GET /v1/mcp/gitops/gitlab/servers

Auth: require_admin (cpi-admin only, inline check).
"""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from fastapi.testclient import TestClient


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

    def test_full_sync_success(self, app_with_cpi_admin, mock_db_session):
        """POST /sync triggers full GitOps sync (cpi-admin)."""
        mock_result = self._mock_sync_result()

        with (
            patch("src.routers.mcp_gitops.git_service") as mock_git,
            patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc,
        ):
            mock_git._project = MagicMock()
            MockSyncSvc.return_value.sync_all_servers = AsyncMock(return_value=mock_result)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post("/v1/mcp/gitops/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["servers_synced"] == 3

    def test_full_sync_connects_gitlab(self, app_with_cpi_admin, mock_db_session):
        """POST /sync connects to GitLab if not already connected."""
        mock_result = self._mock_sync_result()

        with (
            patch("src.routers.mcp_gitops.git_service") as mock_git,
            patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc,
        ):
            mock_git._project = None
            mock_git.connect = AsyncMock()
            MockSyncSvc.return_value.sync_all_servers = AsyncMock(return_value=mock_result)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post("/v1/mcp/gitops/sync")

        assert response.status_code == 200
        mock_git.connect.assert_awaited_once()

    def test_full_sync_500_on_error(self, app_with_cpi_admin, mock_db_session):
        """POST /sync returns 500 when sync fails."""
        with (
            patch("src.routers.mcp_gitops.git_service") as mock_git,
            patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc,
        ):
            mock_git._project = MagicMock()
            MockSyncSvc.return_value.sync_all_servers = AsyncMock(
                side_effect=Exception("GitLab connection failed")
            )

            with TestClient(app_with_cpi_admin, raise_server_exceptions=False) as client:
                response = client.post("/v1/mcp/gitops/sync")

        assert response.status_code == 500

    # ============== POST /sync/tenant/{tenant_id} ==============

    def test_tenant_sync_success(self, app_with_cpi_admin, mock_db_session):
        """POST /sync/tenant/{id} syncs tenant-specific servers."""
        mock_result = self._mock_sync_result(servers_synced=1, servers_created=0, servers_updated=1)

        with (
            patch("src.routers.mcp_gitops.git_service") as mock_git,
            patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc,
        ):
            mock_git._project = MagicMock()
            MockSyncSvc.return_value.sync_tenant_servers = AsyncMock(return_value=mock_result)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post("/v1/mcp/gitops/sync/tenant/acme")

        assert response.status_code == 200
        data = response.json()
        assert data["servers_updated"] == 1

    # ============== POST /sync/server/{tenant_id}/{server_name} ==============

    def test_server_sync_success(self, app_with_cpi_admin, mock_db_session):
        """POST /sync/server/{t}/{s} syncs a specific server."""
        mock_server = MagicMock()

        with (
            patch("src.routers.mcp_gitops.git_service") as mock_git,
            patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc,
        ):
            mock_git._project = MagicMock()
            MockSyncSvc.return_value.sync_server = AsyncMock(return_value=mock_server)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post("/v1/mcp/gitops/sync/server/acme/linear-mcp")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["servers_synced"] == 1

    def test_server_sync_not_found(self, app_with_cpi_admin, mock_db_session):
        """POST /sync/server/{t}/{s} returns failure when server not in GitLab."""
        with (
            patch("src.routers.mcp_gitops.git_service") as mock_git,
            patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc,
        ):
            mock_git._project = MagicMock()
            MockSyncSvc.return_value.sync_server = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post("/v1/mcp/gitops/sync/server/acme/nonexistent")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    # ============== GET /status ==============

    def test_get_sync_status_success(self, app_with_cpi_admin, mock_db_session):
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

        with (
            patch("src.routers.mcp_gitops.git_service"),
            patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc,
        ):
            MockSyncSvc.return_value.get_sync_status = AsyncMock(return_value=mock_status)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/mcp/gitops/status")

        assert response.status_code == 200
        data = response.json()
        assert data["total_servers"] == 10
        assert data["synced"] == 8

    # ============== GET /gitlab/health ==============

    def test_gitlab_health_success(self, app_with_cpi_admin):
        """GET /gitlab/health returns healthy status."""
        with patch("src.routers.mcp_gitops.git_service") as mock_git:
            mock_project = MagicMock()
            mock_project.name = "stoa-mcp-servers"
            mock_project.id = 42
            mock_project.repository_tree.return_value = []
            mock_git._project = mock_project

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/mcp/gitops/gitlab/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["project"] == "stoa-mcp-servers"

    def test_gitlab_health_unhealthy(self, app_with_cpi_admin):
        """GET /gitlab/health returns unhealthy when GitLab is down."""
        with patch("src.routers.mcp_gitops.git_service") as mock_git:
            mock_git._project = None
            mock_git.connect = AsyncMock(side_effect=Exception("Connection refused"))

            with TestClient(app_with_cpi_admin, raise_server_exceptions=False) as client:
                response = client.get("/v1/mcp/gitops/gitlab/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"

    # ============== GET /gitlab/servers ==============

    def test_list_gitlab_servers_success(self, app_with_cpi_admin):
        """GET /gitlab/servers lists servers from GitLab."""
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

        with patch("src.routers.mcp_gitops.git_service") as mock_git:
            mock_git._project = MagicMock()
            mock_git.list_all_mcp_servers = AsyncMock(return_value=mock_servers)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/mcp/gitops/gitlab/servers")

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
