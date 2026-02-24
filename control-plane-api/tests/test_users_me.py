"""Tests for /v1/me and /v1/me/tenant — user permissions, scopes, personal tenant (CAB-1436)"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.routers.users import (
    _sanitize_slug,
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


class TestSanitizeSlug:
    """Tests for _sanitize_slug helper."""

    def test_simple_username(self):
        assert _sanitize_slug("alice") == "alice"

    def test_email_style_username(self):
        assert _sanitize_slug("alice@example.com") == "alice-example-com"

    def test_special_chars(self):
        assert _sanitize_slug("Al!ce B.ob") == "al-ce-b-ob"

    def test_consecutive_dashes_collapsed(self):
        assert _sanitize_slug("a--b---c") == "a-b-c"

    def test_empty_string_returns_user(self):
        assert _sanitize_slug("!!!") == "user"

    def test_long_username_truncated(self):
        slug = _sanitize_slug("a" * 100)
        assert len(slug) <= 50


TENANT_REPO = "src.routers.users.TenantRepository"
KC_SVC = "src.routers.users.keycloak_service"
KAFKA_SVC = "src.routers.users.kafka_service"


class TestProvisionPersonalTenant:
    """Tests for POST /v1/me/tenant."""

    def test_provision_new_tenant(self, app_with_no_tenant_user, mock_db_session):
        """User without tenant gets a personal tenant created."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)  # no collision
        mock_tenant = MagicMock()
        mock_tenant.id = "free-orphan-user"
        mock_tenant.name = "orphan-user's workspace"
        mock_repo.create = AsyncMock(return_value=mock_tenant)

        mock_kc = MagicMock()
        mock_kc.setup_tenant_group = AsyncMock()
        mock_kc.add_user_to_tenant = AsyncMock()
        mock_kc.assign_role = AsyncMock()

        mock_kafka = MagicMock()
        mock_kafka.emit_audit_event = AsyncMock()

        with (
            patch(TENANT_REPO, return_value=mock_repo),
            patch(KC_SVC, mock_kc),
            patch(KAFKA_SVC, mock_kafka),
        ):
            with TestClient(app_with_no_tenant_user) as client:
                resp = client.post("/v1/me/tenant")

        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] is True
        assert "free-" in data["tenant_id"]

    def test_provision_idempotent_existing_tenant(self, app_with_tenant_admin, mock_db_session):
        """User with existing tenant gets it returned (idempotent)."""
        existing = MagicMock()
        existing.id = "acme"
        existing.name = "ACME Corporation"

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=existing)

        with patch(TENANT_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post("/v1/me/tenant")

        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] is False
        assert data["tenant_id"] == "acme"

    def test_provision_unauthenticated(self, client):
        """Unauthenticated user gets 401."""
        resp = client.post("/v1/me/tenant")
        assert resp.status_code == 401
