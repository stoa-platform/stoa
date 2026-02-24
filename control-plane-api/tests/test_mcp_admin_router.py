"""Tests for MCP Admin Router — admin subscriptions and server management.

Covers:
- /v1/admin/mcp/subscriptions (list pending, list tenant, approve, revoke, suspend, reactivate, stats)
- /v1/admin/mcp/servers (list, create, add tool, update status, delete)
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.schemas.mcp_subscription import (
    MCPServerCategoryEnum,
    MCPServerResponse,
    MCPServerStatusEnum,
    MCPServerVisibility,
    MCPSubscriptionResponse,
    MCPSubscriptionStatusEnum,
)

SUB_REPO_PATH = "src.routers.mcp_admin.MCPSubscriptionRepository"
SERVER_REPO_PATH = "src.routers.mcp_admin.MCPServerRepository"
TOOL_REPO_PATH = "src.routers.mcp_admin.MCPToolAccessRepository"
API_KEY_SVC_PATH = "src.routers.mcp_admin.APIKeyService"
CONVERT_SUB_PATH = "src.routers.mcp_admin._convert_subscription_to_response"
CONVERT_SERVER_PATH = "src.routers.mcp_admin._convert_server_to_response"


def _make_sub_response(**overrides) -> MCPSubscriptionResponse:
    """Build a valid MCPSubscriptionResponse Pydantic instance."""
    defaults = {
        "id": uuid4(),
        "server_id": uuid4(),
        "server": None,
        "subscriber_id": "user-1",
        "subscriber_email": "user@test.com",
        "tenant_id": "acme",
        "plan": "free",
        "api_key_prefix": "stoa_mcp_",
        "status": MCPSubscriptionStatusEnum.ACTIVE,
        "status_reason": None,
        "tool_access": [],
        "last_rotated_at": None,
        "rotation_count": 0,
        "has_active_grace_period": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "approved_at": None,
        "expires_at": None,
        "last_used_at": None,
        "usage_count": 0,
    }
    defaults.update(overrides)
    return MCPSubscriptionResponse(**defaults)


def _make_server_response(**overrides) -> MCPServerResponse:
    """Build a valid MCPServerResponse Pydantic instance."""
    defaults = {
        "id": uuid4(),
        "name": "test-server",
        "display_name": "Test Server",
        "description": "A test server",
        "icon": None,
        "category": MCPServerCategoryEnum.PUBLIC,
        "tenant_id": "acme",
        "visibility": MCPServerVisibility(public=True),
        "requires_approval": False,
        "status": MCPServerStatusEnum.ACTIVE,
        "version": None,
        "documentation_url": None,
        "tools": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    return MCPServerResponse(**defaults)


def _make_sub_mock(tenant_id: str = "acme", status: str = "pending"):
    """Build a MagicMock representing a DB subscription."""
    from src.models.mcp_subscription import MCPSubscriptionStatus

    sub = MagicMock()
    sub.id = uuid4()
    sub.tenant_id = tenant_id
    sub.status = MCPSubscriptionStatus(status)
    sub.server = MagicMock()
    sub.server.name = "test-server"
    sub.server.display_name = "Test Server"
    sub.created_at = datetime.utcnow()
    sub.subscriber_email = "user@test.com"
    sub.tool_access = []
    sub.api_key_prefix = "stoa_mcp_"
    sub.previous_key_expires_at = None
    sub.last_rotated_at = None
    sub.rotation_count = 0
    sub.plan = "free"
    sub.status_reason = None
    sub.approved_at = None
    sub.expires_at = None
    sub.last_used_at = None
    sub.usage_count = 0
    return sub


# ============================================================
# Admin Subscriptions — GET /pending
# ============================================================


class TestListPendingApprovals:
    """Tests for GET /v1/admin/mcp/subscriptions/pending."""

    def test_list_pending_cpi_admin_success(self, app_with_cpi_admin, mock_db_session):
        sub_response = _make_sub_response(status=MCPSubscriptionStatusEnum.PENDING)
        sub_mock = _make_sub_mock(status="pending")

        mock_repo = MagicMock()
        mock_repo.list_pending = AsyncMock(return_value=([sub_mock], 1))

        with (
            patch(SUB_REPO_PATH, return_value=mock_repo),
            patch(CONVERT_SUB_PATH, return_value=sub_response),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/mcp/subscriptions/pending")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_pending_tenant_admin_scoped(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin only sees own tenant's pending subscriptions."""
        sub_response = _make_sub_response(status=MCPSubscriptionStatusEnum.PENDING)
        sub_mock = _make_sub_mock(tenant_id="acme", status="pending")

        mock_repo = MagicMock()
        mock_repo.list_pending = AsyncMock(return_value=([sub_mock], 1))

        with (
            patch(SUB_REPO_PATH, return_value=mock_repo),
            patch(CONVERT_SUB_PATH, return_value=sub_response),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/admin/mcp/subscriptions/pending")

        assert resp.status_code == 200
        # tenant_id filter should have been applied (acme)
        call_kwargs = mock_repo.list_pending.call_args.kwargs
        assert call_kwargs.get("tenant_id") == "acme"

    def test_list_pending_empty_list(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_pending = AsyncMock(return_value=([], 0))

        with patch(SUB_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/mcp/subscriptions/pending")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_pending_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get("/v1/admin/mcp/subscriptions/pending")
        assert resp.status_code == 403


# ============================================================
# Admin Subscriptions — GET /tenant/{tenant_id}
# ============================================================


class TestListTenantSubscriptions:
    """Tests for GET /v1/admin/mcp/subscriptions/tenant/{tenant_id}."""

    def test_list_tenant_subs_success(self, app_with_cpi_admin, mock_db_session):
        sub_response = _make_sub_response()
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([MagicMock()], 1))

        with (
            patch(SUB_REPO_PATH, return_value=mock_repo),
            patch(CONVERT_SUB_PATH, return_value=sub_response),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/mcp/subscriptions/tenant/acme")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_tenant_subs_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        """Tenant admin cannot view another tenant's subscriptions."""
        with TestClient(app_with_other_tenant) as client:
            resp = client.get("/v1/admin/mcp/subscriptions/tenant/acme")
        assert resp.status_code == 403

    def test_list_tenant_subs_own_tenant_ok(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with patch(SUB_REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/admin/mcp/subscriptions/tenant/acme")

        assert resp.status_code == 200


# ============================================================
# Admin Subscriptions — POST /{id}/approve
# ============================================================


class TestApproveSubscription:
    """Tests for POST /v1/admin/mcp/subscriptions/{id}/approve."""

    def test_approve_success(self, app_with_cpi_admin, mock_db_session):
        sub_mock = _make_sub_mock(status="pending")
        sub_response = _make_sub_response(status=MCPSubscriptionStatusEnum.ACTIVE)

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub_mock)
        mock_repo.set_api_key = AsyncMock()
        mock_repo.set_expiration = AsyncMock()
        mock_repo.update_status = AsyncMock(return_value=sub_mock)

        mock_tool_repo = MagicMock()
        mock_tool_repo.update_status = AsyncMock()

        with (
            patch(SUB_REPO_PATH, return_value=mock_repo),
            patch(TOOL_REPO_PATH, return_value=mock_tool_repo),
            patch(API_KEY_SVC_PATH) as mock_api_key,
            patch(CONVERT_SUB_PATH, return_value=sub_response),
            TestClient(app_with_cpi_admin) as client,
        ):
            mock_api_key.generate_key.return_value = ("stoa_mcp_test_key", "hash123", "stoa_mcp_")
            resp = client.post(f"/v1/admin/mcp/subscriptions/{uuid4()}/approve", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert "api_key" in data
        assert data["api_key"] == "stoa_mcp_test_key"

    def test_approve_400_not_pending(self, app_with_cpi_admin, mock_db_session):
        """Cannot approve an already active subscription."""
        sub_mock = _make_sub_mock(status="active")

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub_mock)

        mock_tool_repo = MagicMock()

        with (
            patch(SUB_REPO_PATH, return_value=mock_repo),
            patch(TOOL_REPO_PATH, return_value=mock_tool_repo),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(f"/v1/admin/mcp/subscriptions/{uuid4()}/approve", json={})

        assert resp.status_code == 400

    def test_approve_404_not_found(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_tool_repo = MagicMock()

        with (
            patch(SUB_REPO_PATH, return_value=mock_repo),
            patch(TOOL_REPO_PATH, return_value=mock_tool_repo),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(f"/v1/admin/mcp/subscriptions/{uuid4()}/approve", json={})

        assert resp.status_code == 404

    def test_approve_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.post(f"/v1/admin/mcp/subscriptions/{uuid4()}/approve", json={})
        assert resp.status_code == 403


# ============================================================
# Admin Subscriptions — POST /{id}/revoke
# ============================================================


class TestRevokeSubscription:
    """Tests for POST /v1/admin/mcp/subscriptions/{id}/revoke."""

    def test_revoke_success(self, app_with_cpi_admin, mock_db_session):
        sub_mock = _make_sub_mock(status="active")
        sub_response = _make_sub_response(status=MCPSubscriptionStatusEnum.REVOKED)

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub_mock)
        mock_repo.update_status = AsyncMock(return_value=sub_mock)

        with (
            patch(SUB_REPO_PATH, return_value=mock_repo),
            patch(CONVERT_SUB_PATH, return_value=sub_response),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                f"/v1/admin/mcp/subscriptions/{uuid4()}/revoke",
                json={"reason": "Policy violation"},
            )

        assert resp.status_code == 200

    def test_revoke_400_already_revoked(self, app_with_cpi_admin, mock_db_session):
        sub_mock = _make_sub_mock(status="revoked")

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub_mock)

        with patch(SUB_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.post(
                f"/v1/admin/mcp/subscriptions/{uuid4()}/revoke",
                json={"reason": "Already done"},
            )

        assert resp.status_code == 400

    def test_revoke_404_not_found(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SUB_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.post(
                f"/v1/admin/mcp/subscriptions/{uuid4()}/revoke",
                json={"reason": "Not found test"},
            )

        assert resp.status_code == 404


# ============================================================
# Admin Subscriptions — POST /{id}/suspend
# ============================================================


class TestSuspendSubscription:
    """Tests for POST /v1/admin/mcp/subscriptions/{id}/suspend."""

    def test_suspend_success(self, app_with_cpi_admin, mock_db_session):
        sub_mock = _make_sub_mock(status="active")
        sub_response = _make_sub_response(status=MCPSubscriptionStatusEnum.SUSPENDED)

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub_mock)
        mock_repo.update_status = AsyncMock(return_value=sub_mock)

        with (
            patch(SUB_REPO_PATH, return_value=mock_repo),
            patch(CONVERT_SUB_PATH, return_value=sub_response),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(f"/v1/admin/mcp/subscriptions/{uuid4()}/suspend")

        assert resp.status_code == 200

    def test_suspend_400_not_active(self, app_with_cpi_admin, mock_db_session):
        """Cannot suspend a pending subscription."""
        sub_mock = _make_sub_mock(status="pending")

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub_mock)

        with patch(SUB_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.post(f"/v1/admin/mcp/subscriptions/{uuid4()}/suspend")

        assert resp.status_code == 400

    def test_suspend_404_not_found(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SUB_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.post(f"/v1/admin/mcp/subscriptions/{uuid4()}/suspend")

        assert resp.status_code == 404


# ============================================================
# Admin Subscriptions — POST /{id}/reactivate
# ============================================================


class TestReactivateSubscription:
    """Tests for POST /v1/admin/mcp/subscriptions/{id}/reactivate."""

    def test_reactivate_success(self, app_with_cpi_admin, mock_db_session):
        sub_mock = _make_sub_mock(status="suspended")
        sub_response = _make_sub_response(status=MCPSubscriptionStatusEnum.ACTIVE)

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub_mock)
        mock_repo.update_status = AsyncMock(return_value=sub_mock)

        with (
            patch(SUB_REPO_PATH, return_value=mock_repo),
            patch(CONVERT_SUB_PATH, return_value=sub_response),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(f"/v1/admin/mcp/subscriptions/{uuid4()}/reactivate")

        assert resp.status_code == 200

    def test_reactivate_400_not_suspended(self, app_with_cpi_admin, mock_db_session):
        """Cannot reactivate an active subscription."""
        sub_mock = _make_sub_mock(status="active")

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub_mock)

        with patch(SUB_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.post(f"/v1/admin/mcp/subscriptions/{uuid4()}/reactivate")

        assert resp.status_code == 400


# ============================================================
# Admin Subscriptions — GET /stats
# ============================================================


class TestSubscriptionStats:
    """Tests for GET /v1/admin/mcp/subscriptions/stats."""

    def test_get_stats_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_stats = AsyncMock(
            return_value={
                "total_subscriptions": 10,
                "by_status": {"active": 8, "pending": 2},
                "by_server": {"server-a": 5, "server-b": 5},
                "recent_24h": 3,
            }
        )

        mock_server_repo = MagicMock()
        mock_server_repo.list_all = AsyncMock(return_value=([], 5))

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(SERVER_REPO_PATH, return_value=mock_server_repo),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/mcp/subscriptions/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_subscriptions"] == 10
        assert data["total_servers"] == 5

    def test_get_stats_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_stats = AsyncMock(
            return_value={
                "total_subscriptions": 2,
                "by_status": {"active": 2},
                "by_server": {},
                "recent_24h": 0,
            }
        )

        mock_server_repo = MagicMock()
        mock_server_repo.list_all = AsyncMock(return_value=([], 0))

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(SERVER_REPO_PATH, return_value=mock_server_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/admin/mcp/subscriptions/stats")

        assert resp.status_code == 200

    def test_get_stats_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get("/v1/admin/mcp/subscriptions/stats")
        assert resp.status_code == 403


# ============================================================
# Admin Servers — GET /v1/admin/mcp/servers
# ============================================================


class TestListAllServers:
    """Tests for GET /v1/admin/mcp/servers."""

    def test_list_servers_success(self, app_with_cpi_admin, mock_db_session):
        server_response = _make_server_response()
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=([MagicMock()], 1))

        with (
            patch(SERVER_REPO_PATH, return_value=mock_repo),
            patch(CONVERT_SERVER_PATH, return_value=server_response),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/mcp/servers")

        assert resp.status_code == 200
        assert resp.json()["total_count"] == 1

    def test_list_servers_with_filters(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=([], 0))

        with patch(SERVER_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/mcp/servers?category=public&status=active")

        assert resp.status_code == 200
        call_kwargs = mock_repo.list_all.call_args.kwargs
        assert call_kwargs.get("category") is not None
        assert call_kwargs.get("status") is not None

    def test_list_servers_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get("/v1/admin/mcp/servers")
        assert resp.status_code == 403


# ============================================================
# Admin Servers — POST /v1/admin/mcp/servers
# ============================================================


class TestCreateServer:
    """Tests for POST /v1/admin/mcp/servers."""

    def _server_payload(self, **overrides):
        payload = {
            "name": "new-server",
            "display_name": "New Server",
            "description": "A brand new server",
            "category": "public",
            "visibility": {"public": True},
        }
        payload.update(overrides)
        return payload

    def test_create_server_success(self, app_with_cpi_admin, mock_db_session):
        server_response = _make_server_response()
        created_server = MagicMock()
        created_server.name = "new-server"

        mock_repo = MagicMock()
        mock_repo.get_by_name = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=created_server)

        with (
            patch(SERVER_REPO_PATH, return_value=mock_repo),
            patch(CONVERT_SERVER_PATH, return_value=server_response),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post("/v1/admin/mcp/servers", json=self._server_payload())

        assert resp.status_code == 201

    def test_create_server_409_duplicate(self, app_with_cpi_admin, mock_db_session):
        existing_server = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_name = AsyncMock(return_value=existing_server)

        with patch(SERVER_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.post("/v1/admin/mcp/servers", json=self._server_payload())

        assert resp.status_code == 409

    def test_create_server_tenant_admin_only_tenant_category(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot create a public server."""
        with TestClient(app_with_tenant_admin) as client:
            resp = client.post("/v1/admin/mcp/servers", json=self._server_payload(category="public"))
        assert resp.status_code == 403

    def test_create_server_tenant_admin_can_create_tenant_server(self, app_with_tenant_admin, mock_db_session):
        server_response = _make_server_response(category=MCPServerCategoryEnum.TENANT)
        created_server = MagicMock()

        mock_repo = MagicMock()
        mock_repo.get_by_name = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=created_server)

        with (
            patch(SERVER_REPO_PATH, return_value=mock_repo),
            patch(CONVERT_SERVER_PATH, return_value=server_response),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post(
                "/v1/admin/mcp/servers",
                json=self._server_payload(category="tenant", tenant_id="acme"),
            )

        assert resp.status_code == 201


# ============================================================
# Admin Servers — POST /{id}/tools
# ============================================================


class TestAddToolToServer:
    """Tests for POST /v1/admin/mcp/servers/{id}/tools."""

    def _tool_payload(self):
        return {
            "name": "get-data",
            "display_name": "Get Data",
            "description": "Retrieves data from the API",
        }

    def test_add_tool_success(self, app_with_cpi_admin, mock_db_session):
        server_mock = MagicMock()
        server_mock.id = uuid4()
        server_mock.name = "test-server"
        server_mock.tenant_id = "acme"
        server_mock.tools = []

        tool_mock = MagicMock()
        tool_mock.id = uuid4()
        tool_mock.name = "get-data"
        tool_mock.display_name = "Get Data"
        tool_mock.description = "Retrieves data from the API"
        tool_mock.input_schema = None
        tool_mock.enabled = True
        tool_mock.requires_approval = False

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=server_mock)

        mock_db_session.add = MagicMock()
        mock_db_session.flush = AsyncMock()
        mock_db_session.refresh = AsyncMock(side_effect=lambda _obj: None)

        with (
            patch(SERVER_REPO_PATH, return_value=mock_repo),
            patch("src.routers.mcp_admin.MCPServerTool", return_value=tool_mock),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(f"/v1/admin/mcp/servers/{uuid4()}/tools", json=self._tool_payload())

        assert resp.status_code == 201

    def test_add_tool_409_duplicate_name(self, app_with_cpi_admin, mock_db_session):
        existing_tool = MagicMock()
        existing_tool.name = "get-data"

        server_mock = MagicMock()
        server_mock.id = uuid4()
        server_mock.tenant_id = "acme"
        server_mock.tools = [existing_tool]

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=server_mock)

        with patch(SERVER_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.post(f"/v1/admin/mcp/servers/{uuid4()}/tools", json=self._tool_payload())

        assert resp.status_code == 409

    def test_add_tool_404_server_not_found(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SERVER_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.post(f"/v1/admin/mcp/servers/{uuid4()}/tools", json=self._tool_payload())

        assert resp.status_code == 404


# ============================================================
# Admin Servers — PATCH /{id}/status
# ============================================================


class TestUpdateServerStatus:
    """Tests for PATCH /v1/admin/mcp/servers/{id}/status."""

    def test_update_status_success(self, app_with_cpi_admin, mock_db_session):
        server_mock = MagicMock()
        server_mock.id = uuid4()
        server_mock.name = "test-server"
        server_mock.tenant_id = "acme"

        server_response = _make_server_response(status=MCPServerStatusEnum.MAINTENANCE)

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=server_mock)
        mock_repo.update = AsyncMock()

        with (
            patch(SERVER_REPO_PATH, return_value=mock_repo),
            patch(CONVERT_SERVER_PATH, return_value=server_response),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.patch(f"/v1/admin/mcp/servers/{uuid4()}/status?status=maintenance")

        assert resp.status_code == 200

    def test_update_status_404_not_found(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SERVER_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.patch(f"/v1/admin/mcp/servers/{uuid4()}/status?status=active")

        assert resp.status_code == 404


# ============================================================
# Admin Servers — DELETE /{id}
# ============================================================


class TestDeleteServer:
    """Tests for DELETE /v1/admin/mcp/servers/{id}."""

    def test_delete_server_success(self, app_with_cpi_admin, mock_db_session):
        server_mock = MagicMock()
        server_mock.name = "test-server"

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=server_mock)
        mock_repo.delete = AsyncMock()

        with patch(SERVER_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.delete(f"/v1/admin/mcp/servers/{uuid4()}")

        assert resp.status_code == 204

    def test_delete_server_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """Tenant admins cannot delete servers."""
        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/admin/mcp/servers/{uuid4()}")
        assert resp.status_code == 403

    def test_delete_server_404_not_found(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SERVER_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.delete(f"/v1/admin/mcp/servers/{uuid4()}")

        assert resp.status_code == 404
