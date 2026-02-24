"""Tests for Portal Applications Router — /v1/applications.

Complementary to test_portal_applications.py. Focuses on:
- Ownership check (403 for non-owner)
- Pagination calculations
- Keycloak integration paths (create with/without KC, regenerate secret)
- Delete with KC client cleanup
- 409 duplicate name conflict
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.models.portal_application import PortalApplication, PortalAppStatus


def _make_app(
    owner_id: str = "tenant-admin-user-id",
    name: str = "my-app",
    display_name: str = "My App",
    tenant_id: str = "acme",
    keycloak_client_id: str | None = "kc-client-id",
    keycloak_client_uuid: str | None = "kc-uuid-001",
    status: PortalAppStatus = PortalAppStatus.ACTIVE,
) -> PortalApplication:
    """Build a mock PortalApplication instance."""
    app = PortalApplication()
    app.id = uuid.uuid4()
    app.name = name
    app.display_name = display_name
    app.description = "Test application"
    app.owner_id = owner_id
    app.tenant_id = tenant_id
    app.keycloak_client_id = keycloak_client_id
    app.keycloak_client_uuid = keycloak_client_uuid
    app.status = status
    app.redirect_uris = ["https://app.example.com/callback"]
    app.created_at = datetime(2026, 1, 15, tzinfo=UTC)
    app.updated_at = datetime(2026, 1, 15, tzinfo=UTC)
    return app


# ---------------------------------------------------------------------------
# GET /v1/applications
# ---------------------------------------------------------------------------


class TestListApplications:
    """GET /v1/applications — list with pagination."""

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_pagination_total_pages_calculated(self, mock_repo_cls, app_with_tenant_admin):
        """totalPages is correctly rounded up."""
        apps = [_make_app(name=f"app-{i}") for i in range(3)]
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = (apps, 25)  # 25 total, page_size=20 → 2 pages
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/applications?page_size=20")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 25
        assert data["totalPages"] == 2

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_pagination_zero_total_returns_zero_pages(self, mock_repo_cls, app_with_tenant_admin):
        """Empty list returns 0 totalPages (not negative or NaN)."""
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([], 0)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/applications")

        assert resp.status_code == 200
        assert resp.json()["totalPages"] == 0

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_status_filter_forwarded_to_repo(self, mock_repo_cls, app_with_tenant_admin):
        """status query param is forwarded to repo as PortalAppStatus."""
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([], 0)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/applications?status=active")

        assert resp.status_code == 200
        call_kwargs = mock_repo.list_by_owner.call_args[1]
        assert call_kwargs["status"] == PortalAppStatus.ACTIVE


# ---------------------------------------------------------------------------
# GET /v1/applications/{app_id}
# ---------------------------------------------------------------------------


class TestGetApplication:
    """GET /v1/applications/{app_id}"""

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_get_returns_app_for_owner(self, mock_repo_cls, app_with_tenant_admin):
        """Owner can fetch their application."""
        app = _make_app(owner_id="tenant-admin-user-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/applications/{app.id}")

        assert resp.status_code == 200
        assert resp.json()["name"] == "my-app"

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_get_returns_404_when_not_found(self, mock_repo_cls, app_with_tenant_admin):
        """Non-existent app returns 404."""
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/applications/{uuid.uuid4()}")

        assert resp.status_code == 404

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_get_returns_403_for_non_owner(self, mock_repo_cls, app_with_tenant_admin):
        """Non-owner gets 403, not the app data."""
        # App owned by a different user
        app = _make_app(owner_id="someone-else-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/applications/{app.id}")

        assert resp.status_code == 403
        assert "Access denied" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /v1/applications
# ---------------------------------------------------------------------------


class TestCreateApplication:
    """POST /v1/applications"""

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_returns_201_with_client_secret(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """Create application returns KC client_secret on success."""
        created_app = _make_app()
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = None
        mock_repo.create.return_value = created_app
        mock_repo_cls.return_value = mock_repo

        mock_kc.create_client = AsyncMock(
            return_value={
                "client_id": "new-client-id",
                "id": "kc-new-uuid",
                "client_secret": "super-secret-value",
            }
        )

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/applications",
                json={
                    "name": "my-app",
                    "display_name": "My App",
                    "description": "A test app",
                    "redirect_uris": ["https://app.example.com/callback"],
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "my-app"
        assert data["client_secret"] == "super-secret-value"

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_succeeds_when_keycloak_fails(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """App is created even if Keycloak client creation fails (graceful degradation)."""
        created_app = _make_app(keycloak_client_id=None, keycloak_client_uuid=None)
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = None
        mock_repo.create.return_value = created_app
        mock_repo_cls.return_value = mock_repo

        mock_kc.create_client = AsyncMock(side_effect=RuntimeError("Keycloak unreachable"))

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/applications",
                json={"name": "my-app", "display_name": "My App"},
            )

        assert resp.status_code == 200
        # No client_secret since KC failed
        assert resp.json()["client_secret"] is None

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_returns_409_on_duplicate_name(self, mock_repo_cls, app_with_tenant_admin):
        """Duplicate app name returns 409 conflict."""
        existing = _make_app()
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = existing
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/applications",
                json={"name": "my-app", "display_name": "My App"},
            )

        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# PATCH /v1/applications/{app_id}
# ---------------------------------------------------------------------------


class TestUpdateApplication:
    """PATCH /v1/applications/{app_id}"""

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_update_changes_display_name(self, mock_repo_cls, app_with_tenant_admin):
        """PATCH updates display_name in DB."""
        app = _make_app(owner_id="tenant-admin-user-id")
        updated_app = _make_app(owner_id="tenant-admin-user-id", display_name="Updated Name")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo.update.return_value = updated_app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.patch(
                f"/v1/applications/{app.id}",
                json={"display_name": "Updated Name"},
            )

        assert resp.status_code == 200
        mock_repo.update.assert_awaited_once()

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_update_returns_404_when_not_found(self, mock_repo_cls, app_with_tenant_admin):
        """PATCH on non-existent app returns 404."""
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.patch(
                f"/v1/applications/{uuid.uuid4()}",
                json={"display_name": "Whatever"},
            )

        assert resp.status_code == 404

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_update_returns_403_for_non_owner(self, mock_repo_cls, app_with_tenant_admin):
        """PATCH by non-owner returns 403."""
        app = _make_app(owner_id="someone-else")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.patch(
                f"/v1/applications/{app.id}",
                json={"display_name": "Hijacked"},
            )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /v1/applications/{app_id}
# ---------------------------------------------------------------------------


class TestDeleteApplication:
    """DELETE /v1/applications/{app_id}"""

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_delete_removes_app_and_kc_client(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """Delete calls KC client deletion and DB delete."""
        app = _make_app(owner_id="tenant-admin-user-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo.delete = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_kc.delete_client = AsyncMock()

        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/applications/{app.id}")

        assert resp.status_code == 200
        assert resp.json()["message"] == "Application deleted"
        mock_kc.delete_client.assert_awaited_once_with("kc-uuid-001")
        mock_repo.delete.assert_awaited_once()

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_delete_succeeds_when_kc_client_deletion_fails(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """Delete app succeeds even if Keycloak client deletion fails."""
        app = _make_app(owner_id="tenant-admin-user-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo.delete = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_kc.delete_client = AsyncMock(side_effect=RuntimeError("KC down"))

        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/applications/{app.id}")

        assert resp.status_code == 200
        mock_repo.delete.assert_awaited_once()

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_delete_returns_403_for_non_owner(self, mock_repo_cls, app_with_tenant_admin):
        """Non-owner cannot delete the application."""
        app = _make_app(owner_id="another-user-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/applications/{app.id}")

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /v1/applications/{app_id}/regenerate-secret
# ---------------------------------------------------------------------------


class TestRegenerateSecret:
    """POST /v1/applications/{app_id}/regenerate-secret"""

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_regenerate_returns_new_secret(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """Regenerate secret returns new clientSecret."""
        app = _make_app(owner_id="tenant-admin-user-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo.update.return_value = app
        mock_repo_cls.return_value = mock_repo
        mock_kc.regenerate_client_secret = AsyncMock(return_value="brand-new-secret-xyz")

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/applications/{app.id}/regenerate-secret")

        assert resp.status_code == 200
        assert resp.json()["clientSecret"] == "brand-new-secret-xyz"

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_regenerate_returns_400_when_no_kc_client(self, mock_repo_cls, app_with_tenant_admin):
        """App without Keycloak client returns 400."""
        app = _make_app(owner_id="tenant-admin-user-id", keycloak_client_uuid=None)
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/applications/{app.id}/regenerate-secret")

        assert resp.status_code == 400
        assert "no Keycloak client" in resp.json()["detail"]

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_regenerate_returns_404_when_app_missing(self, mock_repo_cls, app_with_tenant_admin):
        """Regenerate on non-existent app returns 404."""
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/applications/{uuid.uuid4()}/regenerate-secret")

        assert resp.status_code == 404
