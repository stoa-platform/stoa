"""Tests for tenant tool permissions CRUD + cache + enforcement (CAB-1980).

Tests cover:
- CRUD endpoints (list, create/upsert, delete)
- RBAC (tenant-admin, cpi-admin, viewer denied, tenant isolation)
- In-memory cache behavior (load, invalidation)
- Enforcement in invoke_tool endpoint (403 when tool denied)
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.models.tenant_tool_permission import TenantToolPermission

# ============== Helpers ==============


def _mock_permission(**kwargs):
    """Create a mock TenantToolPermission."""
    perm = MagicMock(spec=TenantToolPermission)
    perm.id = kwargs.get("id", uuid.uuid4())
    perm.tenant_id = kwargs.get("tenant_id", "acme")
    perm.mcp_server_id = kwargs.get("mcp_server_id", uuid.uuid4())
    perm.tool_name = kwargs.get("tool_name", "create_issue")
    perm.allowed = kwargs.get("allowed", True)
    perm.created_by = kwargs.get("created_by", "tenant-admin-user-id")
    perm.created_at = kwargs.get("created_at", datetime.now(UTC))
    perm.updated_at = kwargs.get("updated_at", datetime.now(UTC))
    return perm


# ============== Fixtures ==============


@pytest.fixture
def app_with_viewer(app, mock_db_session):
    """App with viewer user (read-only, no write)."""
    from src.auth.dependencies import get_current_user
    from src.database import get_db
    from tests.conftest import User

    viewer = User(
        id="viewer-user-id",
        email="viewer@acme.com",
        username="viewer",
        roles=["viewer"],
        tenant_id="acme",
    )

    async def override_get_current_user():
        return viewer

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client_as_viewer(app_with_viewer):
    with TestClient(app_with_viewer) as c:
        yield c


@pytest.fixture(autouse=True)
async def clear_permission_cache():
    """Clear permission cache before each test."""
    from src.routers.tenant_tool_permissions import _permission_cache

    await _permission_cache.clear()
    yield
    await _permission_cache.clear()


# ============== List Permissions ==============


class TestListPermissions:
    """GET /v1/tenants/{tenant_id}/tool-permissions"""

    def test_list_empty(self, client_as_tenant_admin, mock_db_session):
        """List returns empty when no permissions exist."""
        # Mock count query
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        # Mock items query
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = client_as_tenant_admin.get("/v1/tenants/acme/tool-permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_with_items(self, client_as_tenant_admin, mock_db_session):
        """List returns permissions for the tenant."""
        server_id = uuid.uuid4()
        perm = _mock_permission(mcp_server_id=server_id, tool_name="search_docs")

        count_result = MagicMock()
        count_result.scalar.return_value = 1
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [perm]

        mock_db_session.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = client_as_tenant_admin.get("/v1/tenants/acme/tool-permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["tool_name"] == "search_docs"
        assert data["total"] == 1

    def test_list_filter_by_server(self, client_as_tenant_admin, mock_db_session):
        """List can filter by mcp_server_id."""
        server_id = uuid.uuid4()

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = client_as_tenant_admin.get(
            f"/v1/tenants/acme/tool-permissions?mcp_server_id={server_id}"
        )
        assert resp.status_code == 200

    def test_list_cpi_admin_any_tenant(self, client_as_cpi_admin, mock_db_session):
        """cpi-admin can list permissions for any tenant."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = client_as_cpi_admin.get("/v1/tenants/other-tenant/tool-permissions")
        assert resp.status_code == 200

    def test_list_tenant_isolation(self, client_as_tenant_admin):
        """tenant-admin cannot list permissions for another tenant."""
        resp = client_as_tenant_admin.get("/v1/tenants/other-tenant/tool-permissions")
        assert resp.status_code == 403


# ============== Create Permission ==============


class TestCreatePermission:
    """POST /v1/tenants/{tenant_id}/tool-permissions"""

    def test_create_permission(self, client_as_tenant_admin, mock_db_session):
        """Create a tool permission."""
        server_id = uuid.uuid4()
        perm = _mock_permission(
            mcp_server_id=server_id,
            tool_name="delete_user",
            allowed=False,
        )

        # First execute: check for existing → not found
        select_result = MagicMock()
        select_result.scalars.return_value.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=select_result)
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(side_effect=lambda p: setattr(p, "id", perm.id))

        resp = client_as_tenant_admin.post(
            "/v1/tenants/acme/tool-permissions",
            json={
                "mcp_server_id": str(server_id),
                "tool_name": "delete_user",
                "allowed": False,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["tool_name"] == "delete_user"
        assert data["allowed"] is False

    def test_create_denied_viewer(self, client_as_viewer):
        """Viewer cannot create permissions."""
        resp = client_as_viewer.post(
            "/v1/tenants/acme/tool-permissions",
            json={
                "mcp_server_id": str(uuid.uuid4()),
                "tool_name": "test_tool",
                "allowed": False,
            },
        )
        assert resp.status_code == 403

    def test_create_tenant_isolation(self, client_as_tenant_admin):
        """tenant-admin cannot create permissions for another tenant."""
        resp = client_as_tenant_admin.post(
            "/v1/tenants/other-tenant/tool-permissions",
            json={
                "mcp_server_id": str(uuid.uuid4()),
                "tool_name": "test_tool",
                "allowed": False,
            },
        )
        assert resp.status_code == 403

    def test_create_cpi_admin_any_tenant(self, client_as_cpi_admin, mock_db_session):
        """cpi-admin can create permissions for any tenant."""
        server_id = uuid.uuid4()

        # First execute: check for existing → not found
        select_result = MagicMock()
        select_result.scalars.return_value.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=select_result)
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        resp = client_as_cpi_admin.post(
            "/v1/tenants/other-tenant/tool-permissions",
            json={
                "mcp_server_id": str(server_id),
                "tool_name": "admin_tool",
                "allowed": False,
            },
        )
        assert resp.status_code == 201

    def test_create_validation_empty_tool_name(self, client_as_tenant_admin):
        """Empty tool_name is rejected."""
        resp = client_as_tenant_admin.post(
            "/v1/tenants/acme/tool-permissions",
            json={
                "mcp_server_id": str(uuid.uuid4()),
                "tool_name": "",
                "allowed": False,
            },
        )
        assert resp.status_code == 422


# ============== Delete Permission ==============


class TestDeletePermission:
    """DELETE /v1/tenants/{tenant_id}/tool-permissions/{permission_id}"""

    def test_delete_permission(self, client_as_tenant_admin, mock_db_session):
        """Delete a tool permission."""
        perm_id = uuid.uuid4()
        perm = _mock_permission(id=perm_id)

        select_result = MagicMock()
        select_result.scalars.return_value.first.return_value = perm
        mock_db_session.execute = AsyncMock(
            side_effect=[select_result, MagicMock()]
        )
        mock_db_session.commit = AsyncMock()

        resp = client_as_tenant_admin.delete(
            f"/v1/tenants/acme/tool-permissions/{perm_id}"
        )
        assert resp.status_code == 204

    def test_delete_not_found(self, client_as_tenant_admin, mock_db_session):
        """Delete returns 404 for non-existent permission."""
        select_result = MagicMock()
        select_result.scalars.return_value.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=select_result)

        resp = client_as_tenant_admin.delete(
            f"/v1/tenants/acme/tool-permissions/{uuid.uuid4()}"
        )
        assert resp.status_code == 404

    def test_delete_denied_viewer(self, client_as_viewer):
        """Viewer cannot delete permissions."""
        resp = client_as_viewer.delete(
            f"/v1/tenants/acme/tool-permissions/{uuid.uuid4()}"
        )
        assert resp.status_code == 403

    def test_delete_tenant_isolation(self, client_as_tenant_admin):
        """tenant-admin cannot delete permissions for another tenant."""
        resp = client_as_tenant_admin.delete(
            f"/v1/tenants/other-tenant/tool-permissions/{uuid.uuid4()}"
        )
        assert resp.status_code == 403


# ============== Cache Behavior ==============


class TestPermissionCache:
    """Test in-memory cache behavior."""

    @pytest.mark.asyncio
    async def test_cache_loads_on_first_check(self):
        """Cache loads all tenant permissions on first check."""
        from src.routers.tenant_tool_permissions import (
            _permission_cache,
            check_tool_allowed,
        )

        server_id = uuid.uuid4()
        perm = _mock_permission(
            mcp_server_id=server_id,
            tool_name="blocked_tool",
            allowed=False,
        )

        mock_db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [perm]
        mock_db.execute = AsyncMock(return_value=result)

        allowed = await check_tool_allowed("acme", "blocked_tool", mock_db)
        assert allowed is False

        # Verify cache was populated
        cached = await _permission_cache.get("tenant:acme")
        assert cached is not None

    @pytest.mark.asyncio
    async def test_cache_hit_no_db_call(self):
        """Cached permissions skip database query."""
        from src.routers.tenant_tool_permissions import (
            _permission_cache,
            check_tool_allowed,
        )

        server_id = uuid.uuid4()
        await _permission_cache.set(
            "tenant:acme",
            {(str(server_id), "denied_tool"): False},
            ttl_seconds=60,
        )

        mock_db = AsyncMock()
        allowed = await check_tool_allowed("acme", "denied_tool", mock_db)
        assert allowed is False
        # DB should not be called
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_allow_when_no_permission(self):
        """Tools are allowed by default when no permission row exists."""
        from src.routers.tenant_tool_permissions import check_tool_allowed

        mock_db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        allowed = await check_tool_allowed("acme", "any_tool", mock_db)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_create(self):
        """Cache is invalidated after creating a permission."""
        from src.routers.tenant_tool_permissions import (
            _invalidate_cache,
            _permission_cache,
        )

        await _permission_cache.set("tenant:acme", {"some": "data"}, ttl_seconds=60)
        assert await _permission_cache.get("tenant:acme") is not None

        await _invalidate_cache("acme")
        assert await _permission_cache.get("tenant:acme") is None

    @pytest.mark.asyncio
    async def test_check_with_server_id(self):
        """check_tool_allowed with specific server_id."""
        from src.routers.tenant_tool_permissions import (
            _permission_cache,
            check_tool_allowed,
        )

        server_a = uuid.uuid4()
        server_b = uuid.uuid4()
        await _permission_cache.set(
            "tenant:acme",
            {
                (str(server_a), "tool_x"): False,
                (str(server_b), "tool_x"): True,
            },
            ttl_seconds=60,
        )

        mock_db = AsyncMock()
        # Denied for server_a
        assert await check_tool_allowed("acme", "tool_x", mock_db, server_a) is False
        # Allowed for server_b
        assert await check_tool_allowed("acme", "tool_x", mock_db, server_b) is True

    @pytest.mark.asyncio
    async def test_check_without_server_id_any_denied(self):
        """Without server_id, if any server has tool denied, it's denied."""
        from src.routers.tenant_tool_permissions import (
            _permission_cache,
            check_tool_allowed,
        )

        server_a = uuid.uuid4()
        server_b = uuid.uuid4()
        await _permission_cache.set(
            "tenant:acme",
            {
                (str(server_a), "tool_x"): True,
                (str(server_b), "tool_x"): False,
            },
            ttl_seconds=60,
        )

        mock_db = AsyncMock()
        # Without server_id, denied because server_b denies it
        assert await check_tool_allowed("acme", "tool_x", mock_db) is False


# ============== Enforcement in invoke_tool ==============


class TestInvokeToolEnforcement:
    """Test that invoke_tool checks tenant tool permissions."""

    def test_invoke_denied_tool_returns_403(self, app, mock_db_session):
        """Invoking a denied tool returns 403."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db
        from tests.conftest import User

        user = User(
            id="tenant-admin-user-id",
            email="admin@acme.com",
            username="tenant-admin",
            roles=["tenant-admin"],
            tenant_id="acme",
        )

        async def override_user():
            return user

        async def override_db():
            yield mock_db_session

        from fastapi.security import HTTPAuthorizationCredentials

        from src.routers.mcp_proxy import security

        async def override_security():
            return HTTPAuthorizationCredentials(
                scheme="Bearer", credentials="mock-token"
            )

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[security] = override_security

        with patch(
            "src.routers.tenant_tool_permissions.check_tool_allowed",
            new_callable=AsyncMock,
            return_value=False,
        ), TestClient(app) as client:
            resp = client.post(
                "/v1/mcp/tools/blocked_tool/invoke",
                json={"arguments": {"query": "test"}},
            )
            assert resp.status_code == 403
            assert "not allowed" in resp.json()["detail"]

        app.dependency_overrides.clear()

    def test_invoke_allowed_tool_proxies(self, app, mock_db_session):
        """Invoking an allowed tool proceeds to proxy."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db
        from tests.conftest import User

        user = User(
            id="tenant-admin-user-id",
            email="admin@acme.com",
            username="tenant-admin",
            roles=["tenant-admin"],
            tenant_id="acme",
        )

        async def override_user():
            return user

        async def override_db():
            yield mock_db_session

        from fastapi.security import HTTPAuthorizationCredentials

        from src.routers.mcp_proxy import security

        async def override_security():
            return HTTPAuthorizationCredentials(
                scheme="Bearer", credentials="mock-token"
            )

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[security] = override_security

        with patch(
            "src.routers.tenant_tool_permissions.check_tool_allowed",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "src.routers.mcp_proxy.proxy_to_mcp",
            new_callable=AsyncMock,
            return_value={"content": [{"type": "text", "text": "ok"}], "isError": False},
        ), TestClient(app) as client:
            resp = client.post(
                "/v1/mcp/tools/allowed_tool/invoke",
                json={"arguments": {"query": "test"}},
            )
            assert resp.status_code == 200

        app.dependency_overrides.clear()
