"""
Tests for MCP Visibility RBAC - CAB-1300

Tests the _is_visible_to_user helper and get_server visibility enforcement.
Also tests list_visible_for_user Python-side filtering in the repository.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.models.mcp_subscription import MCPServerCategory, MCPServerStatus


def _make_server(
    server_id=None,
    visibility=None,
    tenant_id=None,
    status_value="active",
):
    """Create a mock MCPServer with visibility config."""
    server = MagicMock()
    server.id = server_id or uuid4()
    server.name = "test-server"
    server.display_name = "Test Server"
    server.description = "A test server"
    server.icon = "server"
    server.category = MCPServerCategory("public")
    server.tenant_id = tenant_id
    server.visibility = visibility if visibility is not None else {"public": True}
    server.requires_approval = False
    server.auto_approve_roles = []
    server.status = MCPServerStatus(status_value)
    server.version = "1.0.0"
    server.documentation_url = None
    server.tools = []
    server.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    server.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return server


class TestIsVisibleToUser:
    """Test the _is_visible_to_user helper function."""

    def test_public_server_visible_to_all(self):
        """Public servers are visible to all roles."""
        from src.routers.mcp import _is_visible_to_user

        server = _make_server(visibility={"public": True})
        assert _is_visible_to_user(server, ["viewer"], "acme") is True
        assert _is_visible_to_user(server, ["tenant-admin"], "acme") is True

    def test_cpi_admin_always_has_access(self):
        """cpi-admin can see any server regardless of visibility config."""
        from src.routers.mcp import _is_visible_to_user

        server = _make_server(visibility={"public": False, "roles": ["tenant-admin"]})
        assert _is_visible_to_user(server, ["cpi-admin"], None) is True

    def test_role_restricted_server_allowed(self):
        """Server with roles restriction allows matching role."""
        from src.routers.mcp import _is_visible_to_user

        server = _make_server(visibility={"public": False, "roles": ["tenant-admin", "devops"]})
        assert _is_visible_to_user(server, ["tenant-admin"], "acme") is True
        assert _is_visible_to_user(server, ["devops"], "acme") is True

    def test_role_restricted_server_denied(self):
        """Server with roles restriction denies non-matching role."""
        from src.routers.mcp import _is_visible_to_user

        server = _make_server(visibility={"public": False, "roles": ["tenant-admin"]})
        assert _is_visible_to_user(server, ["viewer"], "acme") is False

    def test_exclude_roles_denies_matching(self):
        """Server with exclude_roles denies matching role."""
        from src.routers.mcp import _is_visible_to_user

        server = _make_server(visibility={"public": True, "exclude_roles": ["devops"]})
        assert _is_visible_to_user(server, ["devops"], "acme") is False

    def test_exclude_roles_allows_non_matching(self):
        """Server with exclude_roles allows non-matching role."""
        from src.routers.mcp import _is_visible_to_user

        server = _make_server(visibility={"public": True, "exclude_roles": ["devops"]})
        assert _is_visible_to_user(server, ["viewer"], "acme") is True

    def test_tenant_specific_server_same_tenant(self):
        """Tenant-specific server visible to same-tenant user."""
        from src.routers.mcp import _is_visible_to_user

        server = _make_server(visibility={"public": True}, tenant_id="acme")
        assert _is_visible_to_user(server, ["viewer"], "acme") is True

    def test_tenant_specific_server_different_tenant(self):
        """Tenant-specific server hidden from different-tenant user."""
        from src.routers.mcp import _is_visible_to_user

        server = _make_server(visibility={"public": True}, tenant_id="acme")
        assert _is_visible_to_user(server, ["viewer"], "other-tenant") is False

    def test_none_visibility_defaults_to_public(self):
        """Server with None visibility defaults to public."""
        from src.routers.mcp import _is_visible_to_user

        server = _make_server(visibility=None)
        assert _is_visible_to_user(server, ["viewer"], "acme") is True

    def test_non_public_no_roles_denies(self):
        """Non-public server with empty roles list denies access."""
        from src.routers.mcp import _is_visible_to_user

        server = _make_server(visibility={"public": False})
        assert _is_visible_to_user(server, ["viewer"], "acme") is False


class TestGetServerVisibility:
    """Test get_server endpoint enforces visibility."""

    def test_get_server_public_allowed(self, app_with_tenant_admin, mock_db_session):
        """Public server accessible to tenant-admin."""
        server = _make_server(visibility={"public": True})

        with patch("src.routers.mcp.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=server)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/mcp/servers/{server.id}")

        assert response.status_code == 200

    def test_get_server_role_denied(self, app_with_tenant_admin, mock_db_session):
        """Role-restricted server denies non-matching role."""
        server = _make_server(visibility={"public": False, "roles": ["cpi-admin"]})

        with patch("src.routers.mcp.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=server)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/mcp/servers/{server.id}")

        assert response.status_code == 403

    def test_get_server_exclude_role_denied(self, app_with_tenant_admin, mock_db_session):
        """Server with exclude_roles blocks matching user."""
        server = _make_server(visibility={"public": True, "exclude_roles": ["tenant-admin"]})

        with patch("src.routers.mcp.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=server)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/mcp/servers/{server.id}")

        assert response.status_code == 403

    def test_get_server_cpi_admin_bypasses(self, app_with_cpi_admin, mock_db_session):
        """cpi-admin can access any server."""
        server = _make_server(visibility={"public": False, "roles": ["tenant-admin"]})

        with patch("src.routers.mcp.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=server)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"/v1/mcp/servers/{server.id}")

        assert response.status_code == 200

    def test_get_server_tenant_mismatch_denied(self, app_with_tenant_admin, mock_db_session):
        """Tenant-specific server from another tenant is denied."""
        server = _make_server(visibility={"public": True}, tenant_id="other-tenant")

        with patch("src.routers.mcp.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=server)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/mcp/servers/{server.id}")

        assert response.status_code == 403


class TestRepositoryVisibilityFilter:
    """Test _is_visible helper in repository module."""

    def test_public_visible(self):
        """Public server passes filter."""
        from src.repositories.mcp_subscription import _is_visible

        server = _make_server(visibility={"public": True})
        assert _is_visible(server, ["viewer"]) is True

    def test_exclude_roles_filtered(self):
        """Server with exclude_roles filters matching role."""
        from src.repositories.mcp_subscription import _is_visible

        server = _make_server(visibility={"public": True, "exclude_roles": ["viewer"]})
        assert _is_visible(server, ["viewer"]) is False

    def test_non_public_no_roles_filtered(self):
        """Non-public server without matching roles is filtered out."""
        from src.repositories.mcp_subscription import _is_visible

        server = _make_server(visibility={"public": False, "roles": ["devops"]})
        assert _is_visible(server, ["viewer"]) is False

    def test_admin_bypasses_filter(self):
        """cpi-admin always passes filter."""
        from src.repositories.mcp_subscription import _is_visible

        server = _make_server(visibility={"public": False})
        assert _is_visible(server, ["cpi-admin"]) is True
