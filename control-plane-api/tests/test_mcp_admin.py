"""
Tests for MCP Admin Router - CAB-1116 Phase 2B

Target: Coverage of src/routers/mcp_admin.py
Tests: 25 test cases covering subscription approval workflow, server CRUD, stats, and RBAC.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


def _make_server(
    server_id=None,
    name="test-server",
    display_name="Test Server",
    category_value="public",
    tenant_id="acme",
    status_value="active",
):
    """Create a mock MCPServer."""
    from src.models.mcp_subscription import MCPServerCategory, MCPServerStatus

    server = MagicMock()
    server.id = server_id or uuid4()
    server.name = name
    server.display_name = display_name
    server.description = "A test server"
    server.icon = "server"
    server.category = MCPServerCategory(category_value)
    server.tenant_id = tenant_id
    server.visibility = {"public": True}
    server.requires_approval = False
    server.auto_approve_roles = []
    server.status = MCPServerStatus(status_value)
    server.version = "1.0.0"
    server.documentation_url = None
    server.tools = []
    server.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    server.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return server


def _make_subscription(
    sub_id=None,
    server=None,
    status_value="pending",
    tenant_id="acme",
):
    """Create a mock MCPServerSubscription."""
    from src.models.mcp_subscription import MCPSubscriptionStatus

    sub = MagicMock()
    sub.id = sub_id or uuid4()
    sub.server_id = (server.id if server else uuid4())
    sub.server = server or _make_server()
    sub.subscriber_id = "user-001"
    sub.subscriber_email = "user@acme.com"
    sub.tenant_id = tenant_id
    sub.plan = "basic"
    sub.api_key_prefix = "stoa_mcp_"
    sub.api_key_hash = None
    sub.status = MCPSubscriptionStatus(status_value)
    sub.status_reason = None
    sub.tool_access = []
    sub.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    sub.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    sub.approved_at = None
    sub.expires_at = None
    sub.previous_key_expires_at = None
    sub.last_rotated_at = None
    sub.rotation_count = 0
    sub.last_used_at = None
    sub.usage_count = 0
    return sub


class TestMCPAdminSubscriptionsPending:
    """Test pending subscriptions listing."""

    def test_list_pending_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        """CPI admin can list all pending subscriptions."""
        sub = _make_subscription()

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.list_pending = AsyncMock(return_value=([sub], 1))

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/mcp/subscriptions/pending")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_list_pending_tenant_admin_scoped(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin only sees their own tenant's pending."""
        sub = _make_subscription(tenant_id="acme")

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.list_pending = AsyncMock(return_value=([sub], 1))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/admin/mcp/subscriptions/pending")

        assert response.status_code == 200
        # Verify repo was called with tenant_id="acme" (scoped)
        call_args = MockRepo.return_value.list_pending.call_args
        assert call_args[1]["tenant_id"] == "acme"


class TestMCPAdminSubscriptionsTenant:
    """Test tenant subscriptions listing."""

    def test_list_tenant_subscriptions(self, app_with_cpi_admin, mock_db_session):
        """CPI admin can list any tenant's subscriptions."""
        sub = _make_subscription(tenant_id="acme")

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.list_by_tenant = AsyncMock(return_value=([sub], 1))

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/mcp/subscriptions/tenant/acme")

        assert response.status_code == 200

    def test_list_tenant_subscriptions_cross_tenant_forbidden(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot list another tenant's subscriptions."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/admin/mcp/subscriptions/tenant/other-tenant")

        assert response.status_code == 403


class TestMCPAdminApprove:
    """Test subscription approval workflow."""

    def test_approve_subscription_success(self, app_with_cpi_admin, mock_db_session):
        """Approve a pending subscription generates API key."""
        sub_id = uuid4()
        sub = _make_subscription(sub_id=sub_id, status_value="pending")

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockSubRepo, \
             patch("src.routers.mcp_admin.MCPToolAccessRepository"), \
             patch("src.routers.mcp_admin.APIKeyService") as MockKeyService:
            sub_repo = MockSubRepo.return_value
            sub_repo.get_by_id = AsyncMock(side_effect=[sub, sub])
            sub_repo.set_api_key = AsyncMock()
            sub_repo.update_status = AsyncMock(return_value=sub)
            MockKeyService.generate_key = MagicMock(
                return_value=("stoa_mcp_abc123", "hashed", "stoa_mcp_")
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/mcp/subscriptions/{sub_id}/approve")

        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data

    def test_approve_subscription_404(self, app_with_cpi_admin, mock_db_session):
        """Approve non-existent subscription returns 404."""
        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/mcp/subscriptions/{uuid4()}/approve")

        assert response.status_code == 404

    def test_approve_subscription_wrong_status(self, app_with_cpi_admin, mock_db_session):
        """Cannot approve subscription that is not pending."""
        sub = _make_subscription(status_value="active")

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/mcp/subscriptions/{sub.id}/approve")

        assert response.status_code == 400

    def test_approve_subscription_cross_tenant_forbidden(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot approve subscription for another tenant."""
        sub = _make_subscription(tenant_id="other-tenant")

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(f"/v1/admin/mcp/subscriptions/{sub.id}/approve")

        assert response.status_code == 403


class TestMCPAdminRevoke:
    """Test subscription revocation."""

    def test_revoke_subscription_success(self, app_with_cpi_admin, mock_db_session):
        """Revoke an active subscription."""
        sub = _make_subscription(status_value="active")

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)
            repo.update_status = AsyncMock(return_value=sub)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    f"/v1/admin/mcp/subscriptions/{sub.id}/revoke",
                    json={"reason": "Policy violation"},
                )

        assert response.status_code == 200

    def test_revoke_already_revoked(self, app_with_cpi_admin, mock_db_session):
        """Cannot revoke already revoked subscription."""
        sub = _make_subscription(status_value="revoked")

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    f"/v1/admin/mcp/subscriptions/{sub.id}/revoke",
                    json={"reason": "Test"},
                )

        assert response.status_code == 400


class TestMCPAdminSuspendReactivate:
    """Test suspend and reactivate workflows."""

    def test_suspend_active_subscription(self, app_with_cpi_admin, mock_db_session):
        """Suspend an active subscription."""
        sub = _make_subscription(status_value="active")

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)
            repo.update_status = AsyncMock(return_value=sub)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/mcp/subscriptions/{sub.id}/suspend")

        assert response.status_code == 200

    def test_suspend_non_active_fails(self, app_with_cpi_admin, mock_db_session):
        """Cannot suspend non-active subscription."""
        sub = _make_subscription(status_value="pending")

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/mcp/subscriptions/{sub.id}/suspend")

        assert response.status_code == 400

    def test_reactivate_suspended_subscription(self, app_with_cpi_admin, mock_db_session):
        """Reactivate a suspended subscription."""
        sub = _make_subscription(status_value="suspended")

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)
            repo.update_status = AsyncMock(return_value=sub)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/mcp/subscriptions/{sub.id}/reactivate")

        assert response.status_code == 200

    def test_reactivate_non_suspended_fails(self, app_with_cpi_admin, mock_db_session):
        """Cannot reactivate non-suspended subscription."""
        sub = _make_subscription(status_value="active")

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/mcp/subscriptions/{sub.id}/reactivate")

        assert response.status_code == 400


class TestMCPAdminStats:
    """Test subscription stats endpoint."""

    def test_get_stats_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        """CPI admin gets global stats."""
        stats = {
            "total_subscriptions": 50,
            "by_status": {"active": 30, "pending": 10, "suspended": 10},
            "by_server": {"server-1": 25, "server-2": 25},
            "recent_24h": 5,
        }

        with patch("src.routers.mcp_admin.MCPSubscriptionRepository") as MockSubRepo, \
             patch("src.routers.mcp_admin.MCPServerRepository") as MockServerRepo:
            sub_repo = MockSubRepo.return_value
            sub_repo.get_stats = AsyncMock(return_value=stats)
            server_repo = MockServerRepo.return_value
            server_repo.list_all = AsyncMock(return_value=([], 10))

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/mcp/subscriptions/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_servers"] == 10
        assert data["total_subscriptions"] == 50


class TestMCPAdminServers:
    """Test server management endpoints."""

    def test_list_servers(self, app_with_cpi_admin, mock_db_session):
        """CPI admin can list all servers."""
        server = _make_server()

        with patch("src.routers.mcp_admin.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.list_all = AsyncMock(return_value=([server], 1))

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/mcp/servers")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1

    def test_create_server_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        """CPI admin can create server of any category."""
        server = _make_server()

        with patch("src.routers.mcp_admin.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_name = AsyncMock(return_value=None)
            repo.create = AsyncMock(return_value=server)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/v1/admin/mcp/servers",
                    json={
                        "name": "new-server",
                        "display_name": "New Server",
                        "description": "A new server",
                        "category": "public",
                        "visibility": {"public": True},
                        "version": "1.0.0",
                    },
                )

        assert response.status_code == 201

    def test_create_server_duplicate_name(self, app_with_cpi_admin, mock_db_session):
        """Cannot create server with duplicate name."""
        existing = _make_server()

        with patch("src.routers.mcp_admin.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_name = AsyncMock(return_value=existing)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/v1/admin/mcp/servers",
                    json={
                        "name": "test-server",
                        "display_name": "Test",
                        "description": "Dup",
                        "category": "public",
                        "visibility": {"public": True},
                        "version": "1.0.0",
                    },
                )

        assert response.status_code == 409

    def test_create_server_tenant_admin_only_tenant_category(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin can only create tenant-category servers."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/admin/mcp/servers",
                json={
                    "name": "platform-server",
                    "display_name": "Platform",
                    "description": "Not allowed",
                    "category": "platform",
                    "visibility": {"public": True},
                    "version": "1.0.0",
                },
            )

        assert response.status_code == 403

    def test_delete_server_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        """CPI admin can delete a server."""
        server = _make_server()

        with patch("src.routers.mcp_admin.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=server)
            repo.delete = AsyncMock()

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"/v1/admin/mcp/servers/{server.id}")

        assert response.status_code == 204

    def test_delete_server_tenant_admin_forbidden(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot delete servers."""
        server = _make_server()

        with patch("src.routers.mcp_admin.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=server)

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"/v1/admin/mcp/servers/{server.id}")

        assert response.status_code == 403

    def test_delete_server_404(self, app_with_cpi_admin, mock_db_session):
        """Delete non-existent server returns 404."""
        with patch("src.routers.mcp_admin.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"/v1/admin/mcp/servers/{uuid4()}")

        assert response.status_code == 404

    def test_update_server_status(self, app_with_cpi_admin, mock_db_session):
        """Update server status."""
        server = _make_server()

        with patch("src.routers.mcp_admin.MCPServerRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=server)
            repo.update = AsyncMock(return_value=server)

            with TestClient(app_with_cpi_admin) as client:
                response = client.patch(
                    f"/v1/admin/mcp/servers/{server.id}/status?status=maintenance"
                )

        assert response.status_code == 200


class TestMCPAdminRBAC:
    """Test RBAC enforcement across endpoints."""

    def test_viewer_cannot_access_admin(self, app, mock_db_session):
        """Viewer role cannot access admin endpoints."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db
        from tests.conftest import User

        async def override_user():
            return User(
                id="viewer-id",
                email="viewer@acme.com",
                username="viewer",
                roles=["viewer"],
                tenant_id="acme",
            )

        async def override_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db

        with TestClient(app) as client:
            r1 = client.get("/v1/admin/mcp/subscriptions/pending")
            r2 = client.get("/v1/admin/mcp/servers")

        app.dependency_overrides.clear()
        assert r1.status_code == 403
        assert r2.status_code == 403
