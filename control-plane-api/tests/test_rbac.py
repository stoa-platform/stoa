"""Tests for RBAC decorators and permission system (CAB-1292 Phase 2)."""

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import User, get_current_user
from src.auth.rbac import (
    Permission,
    Role,
    get_user_permissions,
    require_permission,
    require_role,
    require_tenant_access,
)


def _make_user(roles=None, tenant_id="acme", user_id="user-1", email="u@acme.com"):
    return User(id=user_id, email=email, username="testuser", roles=roles or [], tenant_id=tenant_id)


def _app_with_override(user):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: user
    return app


class TestGetUserPermissions:
    def test_cpi_admin_has_all_permissions(self):
        perms = get_user_permissions([Role.CPI_ADMIN])
        assert len(perms) == 18

    def test_viewer_read_only(self):
        perms = get_user_permissions([Role.VIEWER])
        assert Permission.APIS_READ in perms
        assert Permission.APIS_CREATE not in perms
        assert Permission.APIS_DELETE not in perms

    def test_multi_role_union(self):
        perms = get_user_permissions([Role.VIEWER, Role.DEVOPS])
        assert Permission.APIS_READ in perms
        assert Permission.APIS_DEPLOY in perms
        assert Permission.APIS_DELETE not in perms

    def test_unknown_role_ignored(self):
        perms = get_user_permissions(["nonexistent-role"])
        assert perms == []

    def test_empty_roles(self):
        perms = get_user_permissions([])
        assert perms == []

    def test_devops_no_delete(self):
        perms = get_user_permissions([Role.DEVOPS])
        assert Permission.APIS_DEPLOY in perms
        assert Permission.APIS_DELETE not in perms
        assert Permission.APPS_DELETE not in perms

    def test_tenant_admin_boundaries(self):
        perms = get_user_permissions([Role.TENANT_ADMIN])
        assert Permission.APIS_DELETE in perms
        assert Permission.TENANTS_CREATE not in perms
        assert Permission.TENANTS_DELETE not in perms


class TestRequireRole:
    @pytest.mark.asyncio
    async def test_allowed_role_passes(self):
        user = _make_user(roles=["cpi-admin"])
        app = FastAPI()
        checker = require_role(["cpi-admin", "devops"])

        @app.get("/test")
        async def endpoint(u: User = Depends(checker)):
            return {"ok": True}

        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/test")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_disallowed_role_403(self):
        user = _make_user(roles=["viewer"])
        app = FastAPI()
        checker = require_role(["cpi-admin"])

        @app.get("/test")
        async def endpoint(u: User = Depends(checker)):
            return {"ok": True}

        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/test")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_roles_403(self):
        user = _make_user(roles=[])
        app = FastAPI()
        checker = require_role(["cpi-admin"])

        @app.get("/test")
        async def endpoint(u: User = Depends(checker)):
            return {"ok": True}

        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/test")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_any_match_passes(self):
        user = _make_user(roles=["devops"])
        app = FastAPI()
        checker = require_role(["cpi-admin", "devops"])

        @app.get("/test")
        async def endpoint(u: User = Depends(checker)):
            return {"ok": True}

        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/test")
        assert resp.status_code == 200


class TestRequirePermission:
    @pytest.mark.asyncio
    async def test_admin_passes(self):
        user = _make_user(roles=["cpi-admin"])
        app = _app_with_override(user)

        @app.get("/test")
        @require_permission(Permission.APIS_DELETE)
        async def endpoint(user: User = Depends(get_current_user)):
            return {"ok": True}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/test")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_blocked(self):
        user = _make_user(roles=["viewer"])
        app = _app_with_override(user)

        @app.get("/test")
        @require_permission(Permission.APIS_DELETE)
        async def endpoint(user: User = Depends(get_current_user)):
            return {"ok": True}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/test")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_devops_deploy_ok(self):
        user = _make_user(roles=["devops"])
        app = _app_with_override(user)

        @app.get("/test")
        @require_permission(Permission.APIS_DEPLOY)
        async def endpoint(user: User = Depends(get_current_user)):
            return {"ok": True}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/test")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_devops_delete_blocked(self):
        user = _make_user(roles=["devops"])
        app = _app_with_override(user)

        @app.get("/test")
        @require_permission(Permission.APIS_DELETE)
        async def endpoint(user: User = Depends(get_current_user)):
            return {"ok": True}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/test")
        assert resp.status_code == 403


class TestRequireTenantAccess:
    @pytest.mark.asyncio
    async def test_cpi_admin_any_tenant(self):
        user = _make_user(roles=["cpi-admin"], tenant_id="other")
        app = _app_with_override(user)

        @app.get("/tenants/{tenant_id}/data")
        @require_tenant_access
        async def endpoint(tenant_id: str, user: User = Depends(get_current_user)):
            return {"tenant": tenant_id}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/tenants/acme/data")
        assert resp.status_code == 200
        assert resp.json()["tenant"] == "acme"

    @pytest.mark.asyncio
    async def test_own_tenant_ok(self):
        user = _make_user(roles=["tenant-admin"], tenant_id="acme")
        app = _app_with_override(user)

        @app.get("/tenants/{tenant_id}/data")
        @require_tenant_access
        async def endpoint(tenant_id: str, user: User = Depends(get_current_user)):
            return {"tenant": tenant_id}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/tenants/acme/data")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_other_tenant_403(self):
        user = _make_user(roles=["tenant-admin"], tenant_id="acme")
        app = _app_with_override(user)

        @app.get("/tenants/{tenant_id}/data")
        @require_tenant_access
        async def endpoint(tenant_id: str, user: User = Depends(get_current_user)):
            return {"tenant": tenant_id}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/tenants/globex/data")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_wrong_tenant(self):
        user = _make_user(roles=["viewer"], tenant_id="acme")
        app = _app_with_override(user)

        @app.get("/tenants/{tenant_id}/data")
        @require_tenant_access
        async def endpoint(tenant_id: str, user: User = Depends(get_current_user)):
            return {"tenant": tenant_id}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/tenants/globex/data")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_tenant_id_in_user(self):
        user = _make_user(roles=["viewer"], tenant_id=None)
        app = _app_with_override(user)

        @app.get("/tenants/{tenant_id}/data")
        @require_tenant_access
        async def endpoint(tenant_id: str, user: User = Depends(get_current_user)):
            return {"tenant": tenant_id}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/tenants/acme/data")
        assert resp.status_code == 403
