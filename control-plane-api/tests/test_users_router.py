"""Tests for users router — /v1/me and /v1/me/tenant endpoints.

Covers:
- GET /v1/me — permissions response, role filtering, scope calculation
- POST /v1/me/tenant — idempotent personal tenant provisioning, slug sanitization
- Helper functions: get_effective_scopes, filter_system_roles, _sanitize_slug
"""

from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestGetEffectiveScopes:
    """Unit tests for get_effective_scopes()."""

    def test_cpi_admin_has_all_platform_scopes(self):
        from src.routers.users import get_effective_scopes

        scopes = get_effective_scopes(["cpi-admin"])
        assert "stoa:platform:read" in scopes
        assert "stoa:platform:write" in scopes
        assert "stoa:admin:read" in scopes
        assert "stoa:admin:write" in scopes

    def test_viewer_has_only_read_scopes(self):
        from src.routers.users import get_effective_scopes

        scopes = get_effective_scopes(["viewer"])
        assert "stoa:catalog:read" in scopes
        assert "stoa:catalog:write" not in scopes
        assert "stoa:platform:write" not in scopes

    def test_unknown_role_returns_empty(self):
        from src.routers.users import get_effective_scopes

        scopes = get_effective_scopes(["totally-unknown-role"])
        assert scopes == []

    def test_multiple_roles_merge_scopes(self):
        from src.routers.users import get_effective_scopes

        scopes = get_effective_scopes(["viewer", "devops"])
        # viewer + devops should have catalog:read from both
        assert "stoa:catalog:read" in scopes
        # devops has catalog:write, viewer does not — merged result has it
        assert "stoa:catalog:write" in scopes

    def test_scopes_are_sorted(self):
        from src.routers.users import get_effective_scopes

        scopes = get_effective_scopes(["tenant-admin"])
        assert scopes == sorted(scopes)


class TestFilterSystemRoles:
    """Unit tests for filter_system_roles()."""

    def test_removes_default_roles_prefix(self):
        from src.routers.users import filter_system_roles

        result = filter_system_roles(["tenant-admin", "default-roles-stoa", "viewer"])
        assert "default-roles-stoa" not in result
        assert "tenant-admin" in result
        assert "viewer" in result

    def test_removes_offline_access(self):
        from src.routers.users import filter_system_roles

        result = filter_system_roles(["cpi-admin", "offline_access", "uma_authorization"])
        assert "offline_access" not in result
        assert "uma_authorization" not in result
        assert "cpi-admin" in result

    def test_empty_input_returns_empty(self):
        from src.routers.users import filter_system_roles

        assert filter_system_roles([]) == []

    def test_all_system_roles_filtered_out(self):
        from src.routers.users import filter_system_roles

        result = filter_system_roles(["default-roles-master", "offline_access"])
        assert result == []


class TestSanitizeSlug:
    """Unit tests for _sanitize_slug()."""

    def test_username_with_dots_replaced(self):
        from src.routers.users import _sanitize_slug

        assert _sanitize_slug("john.doe") == "john-doe"

    def test_uppercase_lowercased(self):
        from src.routers.users import _sanitize_slug

        assert _sanitize_slug("JohnDoe") == "johndoe"

    def test_multiple_separators_collapsed(self):
        from src.routers.users import _sanitize_slug

        assert _sanitize_slug("john--doe") == "john-doe"

    def test_leading_trailing_dashes_stripped(self):
        from src.routers.users import _sanitize_slug

        assert _sanitize_slug("-john-") == "john"

    def test_empty_username_returns_user(self):
        from src.routers.users import _sanitize_slug

        assert _sanitize_slug("") == "user"

    def test_slug_truncated_at_50_chars(self):
        from src.routers.users import _sanitize_slug

        long_name = "a" * 100
        result = _sanitize_slug(long_name)
        assert len(result) <= 50


# ---------------------------------------------------------------------------
# GET /v1/me
# ---------------------------------------------------------------------------


class TestGetCurrentUserInfo:
    """GET /v1/me — user info + permissions."""

    def test_returns_permissions_for_cpi_admin(self, client_as_cpi_admin):
        """cpi-admin gets full platform permissions."""
        resp = client_as_cpi_admin.get("/v1/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "cpi-admin"
        assert "cpi-admin" in data["roles"]
        assert "stoa:platform:read" in data["effective_scopes"]
        assert "stoa:admin:write" in data["effective_scopes"]

    def test_returns_permissions_for_tenant_admin(self, client_as_tenant_admin):
        """tenant-admin gets tenant-scoped permissions."""
        resp = client_as_tenant_admin.get("/v1/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "acme"
        assert "tenant-admin" in data["roles"]
        assert "stoa:catalog:read" in data["effective_scopes"]
        # tenant-admin does NOT have platform:write
        assert "stoa:platform:write" not in data["effective_scopes"]

    def test_user_without_stoa_role_defaults_to_viewer(self, client_as_no_tenant_user):
        """Self-registered user with no STOA role defaults to viewer."""
        resp = client_as_no_tenant_user.get("/v1/me")

        assert resp.status_code == 200
        data = resp.json()
        # Should be assigned viewer role as default
        assert "viewer" in data["roles"]

    def test_response_includes_user_id_and_email(self, client_as_tenant_admin):
        """Response always includes user_id and email."""
        resp = client_as_tenant_admin.get("/v1/me")

        data = resp.json()
        assert data["user_id"] == "tenant-admin-user-id"
        assert data["email"] == "admin@acme.com"

    def test_permissions_list_is_sorted(self, client_as_cpi_admin):
        """Permissions are returned sorted for deterministic output."""
        resp = client_as_cpi_admin.get("/v1/me")

        data = resp.json()
        assert data["permissions"] == sorted(data["permissions"])

    def test_system_roles_filtered_from_response(self, app, mock_db_session):
        """Keycloak system roles are filtered before response."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db
        from tests.conftest import User

        user_with_system_roles = User(
            id="user-with-sys-roles",
            email="user@test.com",
            username="testuser",
            # Mix of real role + Keycloak system roles
            roles=["tenant-admin", "default-roles-stoa", "offline_access"],
            tenant_id="acme",
        )

        async def override_user():
            return user_with_system_roles

        async def override_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db

        try:
            from fastapi.testclient import TestClient

            with TestClient(app) as client:
                resp = client.get("/v1/me")

            data = resp.json()
            assert "default-roles-stoa" not in data["roles"]
            assert "offline_access" not in data["roles"]
            assert "tenant-admin" in data["roles"]
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /v1/me/tenant
# ---------------------------------------------------------------------------


class TestProvisionPersonalTenant:
    """POST /v1/me/tenant — personal tenant provisioning."""

    @patch("src.routers.users.keycloak_service")
    @patch("src.routers.users.kafka_service")
    @patch("src.routers.users.TenantRepository")
    def test_creates_personal_tenant_for_new_user(self, mock_repo_cls, mock_kafka, mock_kc, app, mock_db_session):
        """New user without tenant gets a personal tenant created."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db
        from tests.conftest import User

        user = User(
            id="new-user-id",
            email="new@example.com",
            username="newuser",
            roles=["viewer"],
            tenant_id=None,  # No tenant yet
        )

        async def override_user():
            return user

        async def override_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db

        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None  # no existing tenant
        created_tenant = MagicMock()
        created_tenant.id = "free-newuser"
        created_tenant.name = "newuser's workspace"
        mock_repo.create.return_value = created_tenant
        mock_repo_cls.return_value = mock_repo

        mock_kc.setup_tenant_group = AsyncMock()
        mock_kc.add_user_to_tenant = AsyncMock()
        mock_kc.assign_role = AsyncMock()
        mock_kafka.emit_audit_event = AsyncMock()

        try:
            from fastapi.testclient import TestClient

            with TestClient(app) as client:
                resp = client.post("/v1/me/tenant")

            assert resp.status_code == 201
            data = resp.json()
            assert data["created"] is True
            assert "free-newuser" in data["tenant_id"]
        finally:
            app.dependency_overrides.clear()

    @patch("src.routers.users.TenantRepository")
    def test_idempotent_returns_existing_tenant(self, mock_repo_cls, app, mock_db_session):
        """User with existing tenant_id returns existing tenant without creating a new one."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db
        from tests.conftest import User

        user = User(
            id="existing-user",
            email="existing@acme.com",
            username="existinguser",
            roles=["viewer"],
            tenant_id="acme",  # already has tenant
        )

        async def override_user():
            return user

        async def override_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db

        existing_tenant = MagicMock()
        existing_tenant.id = "acme"
        existing_tenant.name = "ACME Corp"
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = existing_tenant
        mock_repo_cls.return_value = mock_repo

        try:
            from fastapi.testclient import TestClient

            with TestClient(app) as client:
                resp = client.post("/v1/me/tenant")

            assert resp.status_code == 201
            data = resp.json()
            assert data["tenant_id"] == "acme"
            assert data["created"] is False
            # Should NOT call create
            mock_repo.create.assert_not_called()
        finally:
            app.dependency_overrides.clear()

    @patch("src.routers.users.keycloak_service")
    @patch("src.routers.users.kafka_service")
    @patch("src.routers.users.TenantRepository")
    def test_kc_failure_does_not_block_tenant_creation(self, mock_repo_cls, mock_kafka, mock_kc, app, mock_db_session):
        """Keycloak failures during provisioning are non-blocking."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db
        from tests.conftest import User

        user = User(
            id="user-kc-fail",
            email="kc-fail@example.com",
            username="kc-fail-user",
            roles=["viewer"],
            tenant_id=None,
        )

        async def override_user():
            return user

        async def override_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db

        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        created_tenant = MagicMock()
        created_tenant.id = "free-kc-fail-user"
        created_tenant.name = "kc-fail-user's workspace"
        mock_repo.create.return_value = created_tenant
        mock_repo_cls.return_value = mock_repo

        # All KC operations fail
        mock_kc.setup_tenant_group = AsyncMock(side_effect=RuntimeError("KC down"))
        mock_kc.add_user_to_tenant = AsyncMock(side_effect=RuntimeError("KC down"))
        mock_kc.assign_role = AsyncMock(side_effect=RuntimeError("KC down"))
        mock_kafka.emit_audit_event = AsyncMock()

        try:
            from fastapi.testclient import TestClient

            with TestClient(app) as client:
                resp = client.post("/v1/me/tenant")

            # Tenant should still be created despite KC failures
            assert resp.status_code == 201
            assert resp.json()["created"] is True
        finally:
            app.dependency_overrides.clear()
