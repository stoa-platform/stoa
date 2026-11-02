"""Regression test for CAB-2353 — py/stack-trace-exposure in MCP GitOps sync routes.

500 responses from the sync and git-server listing endpoints used to echo the
exception text (``detail=f"Sync failed: {e!s}"``). They now log server-side and
return a generic message with the same status code.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.services.git_provider import get_git_provider


@pytest.fixture()
def mock_git_provider():
    mock = MagicMock()
    mock._project = MagicMock()
    mock.is_connected = MagicMock(return_value=True)
    mock.connect = AsyncMock()
    return mock


@pytest.fixture()
def app_with_git_provider(app_with_cpi_admin, mock_git_provider):
    app_with_cpi_admin.dependency_overrides[get_git_provider] = lambda: mock_git_provider
    yield app_with_cpi_admin


class TestMCPGitOpsNoExceptionLeak:
    """CAB-2353: 500 responses must not echo exception text to clients."""

    def test_regression_cab_2353_tenant_sync_500_hides_exception(
        self, app_with_git_provider, mock_db_session, mock_git_provider
    ):
        with patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc:
            MockSyncSvc.return_value.sync_tenant_servers = AsyncMock(side_effect=Exception("secret-internal-detail"))
            with TestClient(app_with_git_provider, raise_server_exceptions=False) as client:
                response = client.post("/v1/mcp/gitops/sync/tenant/acme")
        assert response.status_code == 500
        assert "secret-internal-detail" not in response.text

    def test_regression_cab_2353_server_sync_500_hides_exception(
        self, app_with_git_provider, mock_db_session, mock_git_provider
    ):
        with patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc:
            MockSyncSvc.return_value.sync_server = AsyncMock(side_effect=Exception("secret-internal-detail"))
            with TestClient(app_with_git_provider, raise_server_exceptions=False) as client:
                response = client.post("/v1/mcp/gitops/sync/server/acme/linear-mcp")
        assert response.status_code == 500
        assert "secret-internal-detail" not in response.text

    def test_regression_cab_2353_list_git_servers_500_hides_exception(self, app_with_git_provider, mock_git_provider):
        mock_git_provider.list_all_mcp_servers = AsyncMock(side_effect=Exception("secret-internal-detail"))
        with TestClient(app_with_git_provider, raise_server_exceptions=False) as client:
            response = client.get("/v1/mcp/gitops/git/servers")
        assert response.status_code == 500
        assert "secret-internal-detail" not in response.text
