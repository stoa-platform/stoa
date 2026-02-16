"""Tests for GET /v1/me — user permissions and scopes endpoint"""

from src.routers.users import (
    filter_system_roles,
    get_effective_scopes,
)


class TestGetCurrentUserInfo:
    def test_cpi_admin_full_permissions(self, client_as_cpi_admin):
        resp = client_as_cpi_admin.get("/v1/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "admin-user-id"
        assert "cpi-admin" in body["roles"]
        assert "apis:create" in body["permissions"]
        assert "tenants:create" in body["permissions"]
        assert "stoa:admin:write" in body["effective_scopes"]

    def test_tenant_admin_scoped_permissions(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "acme"
        assert "tenant-admin" in body["roles"]
        assert "apis:create" in body["permissions"]
        # tenant-admin has no tenants:create
        assert "tenants:create" not in body["permissions"]

    def test_viewer_readonly_permissions(self, client_as_no_tenant_user):
        resp = client_as_no_tenant_user.get("/v1/me")
        assert resp.status_code == 200
        body = resp.json()
        assert "viewer" in body["roles"]
        assert "apis:read" in body["permissions"]
        assert "apis:create" not in body["permissions"]

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/v1/me")
        assert resp.status_code == 401


class TestFilterSystemRoles:
    def test_filters_default_roles(self):
        roles = ["tenant-admin", "default-roles-stoa", "offline_access", "uma_authorization"]
        filtered = filter_system_roles(roles)
        assert filtered == ["tenant-admin"]

    def test_keeps_stoa_roles(self):
        roles = ["cpi-admin", "viewer"]
        filtered = filter_system_roles(roles)
        assert filtered == ["cpi-admin", "viewer"]

    def test_empty_input(self):
        assert filter_system_roles([]) == []


class TestGetEffectiveScopes:
    def test_cpi_admin_has_admin_scopes(self):
        scopes = get_effective_scopes(["cpi-admin"])
        assert "stoa:admin:write" in scopes
        assert "stoa:platform:write" in scopes

    def test_viewer_has_read_only_scopes(self):
        scopes = get_effective_scopes(["viewer"])
        assert "stoa:catalog:read" in scopes
        assert "stoa:catalog:write" not in scopes

    def test_unknown_role_returns_empty(self):
        scopes = get_effective_scopes(["unknown-role"])
        assert scopes == []

    def test_combined_roles_union_scopes(self):
        scopes = get_effective_scopes(["viewer", "devops"])
        # viewer has stoa:catalog:read, devops adds stoa:catalog:write
        assert "stoa:catalog:read" in scopes
        assert "stoa:catalog:write" in scopes
