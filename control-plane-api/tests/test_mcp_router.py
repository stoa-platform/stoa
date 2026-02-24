"""Tests for MCP Router — CAB-1436

Covers: /v1/mcp/servers, /v1/mcp/subscriptions, /v1/mcp/validate
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


SERVER_REPO = "src.routers.mcp.MCPServerRepository"
SUB_REPO = "src.routers.mcp.MCPSubscriptionRepository"
TOOL_REPO = "src.routers.mcp.MCPToolAccessRepository"
API_KEY_SVC = "src.routers.mcp.APIKeyService"
CACHE = "src.routers.mcp.api_key_cache"


def _make_server(**overrides):
    """Create a mock MCPServer object."""
    mock = MagicMock()
    defaults = {
        "id": uuid.uuid4(),
        "name": "test-server",
        "display_name": "Test Server",
        "description": "A test MCP server",
        "icon": "icon.png",
        "tenant_id": None,
        "requires_approval": False,
        "auto_approve_roles": [],
        "version": "1.0.0",
        "documentation_url": "https://docs.example.com",
        "tools": [],
        "created_at": datetime(2026, 2, 24),
        "updated_at": datetime(2026, 2, 24),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)

    # Enum-like category and status
    mock.category = MagicMock()
    mock.category.value = overrides.get("category_value", "platform")
    mock.status = MagicMock()
    mock.status.value = overrides.get("status_value", "active")

    mock.visibility = overrides.get("visibility", {"public": True})
    return mock


def _make_tool(**overrides):
    """Create a mock MCPServerTool object."""
    mock = MagicMock()
    defaults = {
        "id": uuid.uuid4(),
        "name": "test-tool",
        "display_name": "Test Tool",
        "description": "A test tool",
        "input_schema": {},
        "enabled": True,
        "requires_approval": False,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_subscription(**overrides):
    """Create a mock MCPServerSubscription object."""
    mock = MagicMock()
    defaults = {
        "id": uuid.uuid4(),
        "server_id": uuid.uuid4(),
        "subscriber_id": "admin-user-id",
        "subscriber_email": "admin@gostoa.dev",
        "tenant_id": "acme",
        "plan": "basic",
        "api_key_hash": "hashed",
        "api_key_prefix": "stoa_mcp_abc",
        "status_reason": None,
        "tool_access": [],
        "last_rotated_at": None,
        "rotation_count": 0,
        "previous_key_expires_at": None,
        "created_at": datetime(2026, 2, 24),
        "updated_at": datetime(2026, 2, 24),
        "approved_at": None,
        "expires_at": None,
        "last_used_at": None,
        "usage_count": 0,
        "server": None,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)

    mock.status = MagicMock()
    mock.status.value = overrides.get("status_value", "active")
    return mock


class TestListServers:
    """Tests for GET /v1/mcp/servers."""

    def test_list_servers_success(self, app_with_cpi_admin, mock_db_session):
        """List MCP servers returns paginated results."""
        server = _make_server(tools=[_make_tool()])
        mock_repo = MagicMock()
        mock_repo.list_visible_for_user = AsyncMock(return_value=([server], 1))

        with patch(SERVER_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/mcp/servers")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert len(data["servers"]) == 1
        assert data["servers"][0]["name"] == "test-server"

    def test_list_servers_with_category_filter(self, app_with_cpi_admin, mock_db_session):
        """List servers filters by category."""
        mock_repo = MagicMock()
        mock_repo.list_visible_for_user = AsyncMock(return_value=([], 0))

        with patch(SERVER_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/mcp/servers?category=platform")

        assert resp.status_code == 200
        assert resp.json()["total_count"] == 0

    def test_list_servers_empty(self, app_with_cpi_admin, mock_db_session):
        """List servers returns empty when none exist."""
        mock_repo = MagicMock()
        mock_repo.list_visible_for_user = AsyncMock(return_value=([], 0))

        with patch(SERVER_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/mcp/servers")

        assert resp.status_code == 200
        assert resp.json()["total_count"] == 0
        assert resp.json()["servers"] == []


class TestGetServer:
    """Tests for GET /v1/mcp/servers/{server_id}."""

    def test_get_server_success(self, app_with_cpi_admin, mock_db_session):
        """Get a server by ID."""
        server = _make_server()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=server)

        with patch(SERVER_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get(f"/v1/mcp/servers/{server.id}")

        assert resp.status_code == 200
        assert resp.json()["name"] == "test-server"

    def test_get_server_404(self, app_with_cpi_admin, mock_db_session):
        """Non-existent server returns 404."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SERVER_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get(f"/v1/mcp/servers/{uuid.uuid4()}")

        assert resp.status_code == 404

    def test_get_server_403_not_visible(self, app_with_tenant_admin, mock_db_session):
        """Server not visible to user role returns 403."""
        server = _make_server(
            visibility={"public": False, "roles": ["special-role"]},
            tenant_id="other-tenant",
        )
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=server)

        with patch(SERVER_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get(f"/v1/mcp/servers/{server.id}")

        assert resp.status_code == 403


class TestCreateSubscription:
    """Tests for POST /v1/mcp/subscriptions."""

    def test_create_subscription_success(self, app_with_cpi_admin, mock_db_session):
        """Create a subscription to an active server."""
        from src.models.mcp_subscription import MCPServerStatus

        server = _make_server()
        server.status = MCPServerStatus.ACTIVE
        server.tools = [_make_tool()]

        sub = _make_subscription(server=server)
        mock_server_repo = MagicMock()
        mock_server_repo.get_by_id = AsyncMock(return_value=server)

        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_subscriber_and_server = AsyncMock(return_value=None)
        mock_sub_repo.create = AsyncMock(return_value=sub)
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        mock_tool_repo = MagicMock()
        mock_tool_repo.create_many = AsyncMock()

        with (
            patch(SERVER_REPO, return_value=mock_server_repo),
            patch(SUB_REPO, return_value=mock_sub_repo),
            patch(TOOL_REPO, return_value=mock_tool_repo),
            patch(API_KEY_SVC) as mock_key_svc,
        ):
            mock_key_svc.generate_key.return_value = ("stoa_mcp_test", "hash", "stoa_mcp_tes")
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post(
                    "/v1/mcp/subscriptions",
                    json={"server_id": str(server.id)},
                )

        assert resp.status_code == 201

    def test_create_subscription_server_not_found(self, app_with_cpi_admin, mock_db_session):
        """Create subscription fails when server does not exist."""
        mock_server_repo = MagicMock()
        mock_server_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SERVER_REPO, return_value=mock_server_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post(
                    "/v1/mcp/subscriptions",
                    json={"server_id": str(uuid.uuid4())},
                )

        assert resp.status_code == 404

    def test_create_subscription_duplicate(self, app_with_cpi_admin, mock_db_session):
        """Create subscription returns 409 when already subscribed."""
        from src.models.mcp_subscription import MCPServerStatus

        server = _make_server()
        server.status = MCPServerStatus.ACTIVE
        existing_sub = _make_subscription()

        mock_server_repo = MagicMock()
        mock_server_repo.get_by_id = AsyncMock(return_value=server)

        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_subscriber_and_server = AsyncMock(return_value=existing_sub)

        with (
            patch(SERVER_REPO, return_value=mock_server_repo),
            patch(SUB_REPO, return_value=mock_sub_repo),
        ):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post(
                    "/v1/mcp/subscriptions",
                    json={"server_id": str(server.id)},
                )

        assert resp.status_code == 409

    def test_create_subscription_server_inactive(self, app_with_cpi_admin, mock_db_session):
        """Create subscription fails when server is not active."""
        from src.models.mcp_subscription import MCPServerStatus

        server = _make_server()
        server.status = MCPServerStatus.MAINTENANCE

        mock_server_repo = MagicMock()
        mock_server_repo.get_by_id = AsyncMock(return_value=server)

        with patch(SERVER_REPO, return_value=mock_server_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post(
                    "/v1/mcp/subscriptions",
                    json={"server_id": str(server.id)},
                )

        assert resp.status_code == 400


class TestListSubscriptions:
    """Tests for GET /v1/mcp/subscriptions."""

    def test_list_subscriptions_success(self, app_with_cpi_admin, mock_db_session):
        """List user subscriptions with pagination."""
        sub = _make_subscription()
        mock_repo = MagicMock()
        mock_repo.list_by_subscriber = AsyncMock(return_value=([sub], 1))

        with patch(SUB_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/mcp/subscriptions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_subscriptions_empty(self, app_with_cpi_admin, mock_db_session):
        """List subscriptions returns empty when none exist."""
        mock_repo = MagicMock()
        mock_repo.list_by_subscriber = AsyncMock(return_value=([], 0))

        with patch(SUB_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/mcp/subscriptions")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestGetSubscription:
    """Tests for GET /v1/mcp/subscriptions/{subscription_id}."""

    def test_get_subscription_success(self, app_with_cpi_admin, mock_db_session):
        """Get subscription by ID (owner or admin)."""
        sub = _make_subscription()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get(f"/v1/mcp/subscriptions/{sub.id}")

        assert resp.status_code == 200

    def test_get_subscription_404(self, app_with_cpi_admin, mock_db_session):
        """Non-existent subscription returns 404."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SUB_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get(f"/v1/mcp/subscriptions/{uuid.uuid4()}")

        assert resp.status_code == 404

    def test_get_subscription_403_not_owner(self, app_with_tenant_admin, mock_db_session):
        """Non-owner, non-admin cannot access subscription."""
        sub = _make_subscription(subscriber_id="other-user-id")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get(f"/v1/mcp/subscriptions/{sub.id}")

        assert resp.status_code == 403


class TestCancelSubscription:
    """Tests for DELETE /v1/mcp/subscriptions/{subscription_id}."""

    def test_cancel_subscription_success(self, app_with_cpi_admin, mock_db_session):
        """Cancel an active subscription."""
        from src.models.mcp_subscription import MCPSubscriptionStatus

        sub = _make_subscription()
        sub.status = MCPSubscriptionStatus.ACTIVE
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub)
        mock_repo.update_status = AsyncMock()

        with patch(SUB_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.delete(f"/v1/mcp/subscriptions/{sub.id}")

        assert resp.status_code == 204

    def test_cancel_subscription_404(self, app_with_cpi_admin, mock_db_session):
        """Cancel non-existent subscription returns 404."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SUB_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.delete(f"/v1/mcp/subscriptions/{uuid.uuid4()}")

        assert resp.status_code == 404

    def test_cancel_subscription_403_not_owner(self, app_with_tenant_admin, mock_db_session):
        """Non-owner cannot cancel subscription."""
        sub = _make_subscription(subscriber_id="other-user-id")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.delete(f"/v1/mcp/subscriptions/{sub.id}")

        assert resp.status_code == 403

    def test_cancel_subscription_bad_status(self, app_with_cpi_admin, mock_db_session):
        """Cannot cancel subscription that is already revoked."""
        from src.models.mcp_subscription import MCPSubscriptionStatus

        sub = _make_subscription()
        sub.status = MCPSubscriptionStatus.REVOKED
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.delete(f"/v1/mcp/subscriptions/{sub.id}")

        assert resp.status_code == 400


class TestRotateApiKey:
    """Tests for POST /v1/mcp/subscriptions/{subscription_id}/rotate-key."""

    def test_rotate_key_success(self, app_with_cpi_admin, mock_db_session):
        """Rotate API key for active subscription."""
        from src.models.mcp_subscription import MCPSubscriptionStatus

        sub = _make_subscription(previous_key_expires_at=None)
        sub.status = MCPSubscriptionStatus.ACTIVE
        rotated_sub = _make_subscription(
            previous_key_expires_at=datetime.utcnow() + timedelta(hours=24),
            rotation_count=1,
        )

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub)
        mock_repo.rotate_key = AsyncMock(return_value=rotated_sub)

        with (
            patch(SUB_REPO, return_value=mock_repo),
            patch(API_KEY_SVC) as mock_key_svc,
        ):
            mock_key_svc.generate_key.return_value = ("stoa_mcp_new", "newhash", "stoa_mcp_new")
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post(f"/v1/mcp/subscriptions/{sub.id}/rotate-key")

        assert resp.status_code == 200
        data = resp.json()
        assert "new_api_key" in data

    def test_rotate_key_404(self, app_with_cpi_admin, mock_db_session):
        """Rotate key for non-existent subscription returns 404."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SUB_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post(f"/v1/mcp/subscriptions/{uuid.uuid4()}/rotate-key")

        assert resp.status_code == 404

    def test_rotate_key_grace_period_active(self, app_with_cpi_admin, mock_db_session):
        """Cannot rotate key when grace period is still active."""
        from src.models.mcp_subscription import MCPSubscriptionStatus

        sub = _make_subscription(
            previous_key_expires_at=datetime.utcnow() + timedelta(hours=12),
        )
        sub.status = MCPSubscriptionStatus.ACTIVE

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post(f"/v1/mcp/subscriptions/{sub.id}/rotate-key")

        assert resp.status_code == 400
        assert "grace period" in resp.json()["detail"].lower()


class TestValidateApiKey:
    """Tests for POST /v1/mcp/validate/api-key."""

    def test_validate_key_invalid_format(self, app_with_cpi_admin, mock_db_session):
        """Invalid API key format returns 401."""
        mock_cache = MagicMock()
        mock_cache.get = AsyncMock(return_value=None)

        with patch(CACHE, mock_cache):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post("/v1/mcp/validate/api-key?api_key=invalid_key")

        assert resp.status_code == 401

    def test_validate_key_not_found(self, app_with_cpi_admin, mock_db_session):
        """API key not in database returns 401."""
        mock_cache = MagicMock()
        mock_cache.get = AsyncMock(return_value=None)

        mock_repo = MagicMock()
        mock_repo.get_by_api_key_hash = AsyncMock(return_value=None)
        mock_repo.get_by_previous_key_hash = AsyncMock(return_value=None)

        with (
            patch(CACHE, mock_cache),
            patch(SUB_REPO, return_value=mock_repo),
            patch(API_KEY_SVC) as mock_key_svc,
        ):
            mock_key_svc.hash_key.return_value = "hashed"
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post("/v1/mcp/validate/api-key?api_key=stoa_mcp_testkey123")

        assert resp.status_code == 401

    def test_validate_key_cached_response(self, app_with_cpi_admin, mock_db_session):
        """Cached valid key returns immediately."""
        cached = {"valid": True, "subscription_id": "sub-1", "enabled_tools": ["tool-a"]}
        mock_cache = MagicMock()
        mock_cache.get = AsyncMock(return_value=cached)

        with (
            patch(CACHE, mock_cache),
            patch(API_KEY_SVC) as mock_key_svc,
        ):
            mock_key_svc.hash_key.return_value = "hashed"
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post("/v1/mcp/validate/api-key?api_key=stoa_mcp_testkey123")

        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_validate_key_inactive_subscription(self, app_with_cpi_admin, mock_db_session):
        """Key for inactive subscription returns 403."""
        from src.models.mcp_subscription import MCPSubscriptionStatus

        sub = _make_subscription()
        sub.status = MCPSubscriptionStatus.REVOKED

        mock_cache = MagicMock()
        mock_cache.get = AsyncMock(return_value=None)

        mock_repo = MagicMock()
        mock_repo.get_by_api_key_hash = AsyncMock(return_value=sub)

        with (
            patch(CACHE, mock_cache),
            patch(SUB_REPO, return_value=mock_repo),
            patch(API_KEY_SVC) as mock_key_svc,
        ):
            mock_key_svc.hash_key.return_value = "hashed"
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post("/v1/mcp/validate/api-key?api_key=stoa_mcp_testkey123")

        assert resp.status_code == 403
