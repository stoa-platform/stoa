"""
Tests for Portal Applications Router — CAB-1306 Phase 1

Target: Coverage of src/routers/portal_applications.py (DB + Keycloak integration)
Tests: 19 test cases covering CRUD, ownership, pagination, KC integration, error cases.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.models.portal_application import PortalApplication, PortalAppStatus


def _make_app(
    owner_id: str = "tenant-admin-user-id",
    name: str = "test-app",
    display_name: str = "Test Application",
    tenant_id: str = "acme",
    keycloak_client_id: str | None = "app-abc123",
    keycloak_client_uuid: str | None = "kc-uuid-001",
    status: PortalAppStatus = PortalAppStatus.ACTIVE,
) -> PortalApplication:
    """Create a test PortalApplication model instance."""
    app = PortalApplication()
    app.id = uuid.uuid4()
    app.name = name
    app.display_name = display_name
    app.description = "A test app"
    app.owner_id = owner_id
    app.tenant_id = tenant_id
    app.keycloak_client_id = keycloak_client_id
    app.keycloak_client_uuid = keycloak_client_uuid
    app.status = status
    app.redirect_uris = ["https://example.com/callback"]
    app.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    app.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return app


class TestPortalApplicationsRouter:
    """Test suite for Portal Applications Router (DB-backed)."""

    # ============== List Applications ==============

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_list_applications_empty(self, mock_repo_cls, app_with_tenant_admin):
        """List returns empty when no applications exist."""
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([], 0)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/applications")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_list_applications_with_data(self, mock_repo_cls, app_with_tenant_admin):
        """List returns user's applications."""
        test_app = _make_app()
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([test_app], 1)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/applications")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "test-app"

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_list_applications_pagination(self, mock_repo_cls, app_with_tenant_admin):
        """Pagination parameters are respected."""
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([], 0)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/applications?page=1&page_size=10")

        assert response.status_code == 200
        data = response.json()
        assert data["pageSize"] == 10
        mock_repo.list_by_owner.assert_called_once()
        call_kwargs = mock_repo.list_by_owner.call_args
        assert call_kwargs.kwargs["page_size"] == 10

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_list_applications_filter_status(self, mock_repo_cls, app_with_tenant_admin):
        """Filter by status works."""
        test_app = _make_app()
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([test_app], 1)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/applications?status=active")

        assert response.status_code == 200
        call_kwargs = mock_repo.list_by_owner.call_args
        assert call_kwargs.kwargs["status"] == PortalAppStatus.ACTIVE

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_list_applications_other_user_sees_nothing(self, mock_repo_cls, app_with_other_tenant):
        """User from different tenant/ID sees no applications."""
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([], 0)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_other_tenant) as client:
            response = client.get("/v1/applications")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        # Verify it queries with the other user's ID
        call_kwargs = mock_repo.list_by_owner.call_args
        assert call_kwargs.kwargs["owner_id"] == "other-tenant-user-id"

    # ============== Get Application ==============

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_get_application_success(self, mock_repo_cls, app_with_tenant_admin):
        """Get application by ID."""
        test_app = _make_app()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = test_app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            response = client.get(f"/v1/applications/{test_app.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-app"

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_get_application_404(self, mock_repo_cls, app_with_tenant_admin):
        """Get non-existent application returns 404."""
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_cls.return_value = mock_repo

        fake_id = str(uuid.uuid4())
        with TestClient(app_with_tenant_admin) as client:
            response = client.get(f"/v1/applications/{fake_id}")

        assert response.status_code == 404

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_get_application_403_not_owner(self, mock_repo_cls, app_with_other_tenant):
        """Get application owned by another user returns 403."""
        test_app = _make_app(owner_id="tenant-admin-user-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = test_app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_other_tenant) as client:
            response = client.get(f"/v1/applications/{test_app.id}")

        assert response.status_code == 403

    # ============== Create Application ==============

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_application_success(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """Create application with Keycloak integration."""
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = None

        created_app = _make_app()
        mock_repo.create.return_value = created_app
        mock_repo_cls.return_value = mock_repo

        mock_kc.create_client = AsyncMock(
            return_value={"client_id": "app-new123", "id": "kc-uuid-new", "client_secret": "secret-123"}
        )

        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/applications",
                json={
                    "name": "new-app",
                    "display_name": "New Application",
                    "description": "Created in test",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-app"  # From the mock return
        assert data["client_secret"] == "secret-123"
        mock_kc.create_client.assert_called_once()

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_application_kc_failure_graceful(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """Create application succeeds even when Keycloak fails."""
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = None

        created_app = _make_app(keycloak_client_id=None, keycloak_client_uuid=None)
        mock_repo.create.return_value = created_app
        mock_repo_cls.return_value = mock_repo

        mock_kc.create_client = AsyncMock(side_effect=Exception("KC unavailable"))

        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/applications",
                json={"name": "new-app", "display_name": "New App"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["client_secret"] is None  # No KC secret
        assert data["client_id"] is None  # No KC client

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_application_duplicate_name_409(self, mock_repo_cls, app_with_tenant_admin):
        """Create application with duplicate name returns 409."""
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = _make_app()
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/applications",
                json={"name": "test-app", "display_name": "Duplicate"},
            )

        assert response.status_code == 409

    # ============== Update Application ==============

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_update_application_success(self, mock_repo_cls, app_with_tenant_admin):
        """Update application fields."""
        test_app = _make_app()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = test_app
        mock_repo.update.return_value = test_app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            response = client.patch(
                f"/v1/applications/{test_app.id}",
                json={"display_name": "Updated Name"},
            )

        assert response.status_code == 200

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_update_application_403_not_owner(self, mock_repo_cls, app_with_other_tenant):
        """Update application by non-owner returns 403."""
        test_app = _make_app(owner_id="tenant-admin-user-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = test_app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_other_tenant) as client:
            response = client.patch(
                f"/v1/applications/{test_app.id}",
                json={"display_name": "Hacked"},
            )

        assert response.status_code == 403

    # ============== Delete Application ==============

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_delete_application_success(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """Delete application owned by user."""
        test_app = _make_app()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = test_app
        mock_repo_cls.return_value = mock_repo
        mock_kc.delete_client = AsyncMock(return_value=True)

        with TestClient(app_with_tenant_admin) as client:
            response = client.delete(f"/v1/applications/{test_app.id}")

        assert response.status_code == 200
        assert response.json()["message"] == "Application deleted"
        mock_kc.delete_client.assert_called_once_with(test_app.keycloak_client_uuid)

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_delete_application_404(self, mock_repo_cls, app_with_tenant_admin):
        """Delete non-existent application returns 404."""
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_cls.return_value = mock_repo

        fake_id = str(uuid.uuid4())
        with TestClient(app_with_tenant_admin) as client:
            response = client.delete(f"/v1/applications/{fake_id}")

        assert response.status_code == 404

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_delete_application_403_not_owner(self, mock_repo_cls, app_with_other_tenant):
        """Delete application by non-owner returns 403."""
        test_app = _make_app(owner_id="tenant-admin-user-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = test_app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_other_tenant) as client:
            response = client.delete(f"/v1/applications/{test_app.id}")

        assert response.status_code == 403

    # ============== Regenerate Secret ==============

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_regenerate_secret_success(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """Regenerate secret returns new client secret."""
        test_app = _make_app()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = test_app
        mock_repo.update.return_value = test_app
        mock_repo_cls.return_value = mock_repo
        mock_kc.regenerate_client_secret = AsyncMock(return_value="new-secret-456")

        with TestClient(app_with_tenant_admin) as client:
            response = client.post(f"/v1/applications/{test_app.id}/regenerate-secret")

        assert response.status_code == 200
        data = response.json()
        assert data["clientSecret"] == "new-secret-456"
        mock_kc.regenerate_client_secret.assert_called_once_with(test_app.keycloak_client_uuid)

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_regenerate_secret_no_kc_client_400(self, mock_repo_cls, app_with_tenant_admin):
        """Regenerate secret without KC client returns 400."""
        test_app = _make_app(keycloak_client_uuid=None)
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = test_app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            response = client.post(f"/v1/applications/{test_app.id}/regenerate-secret")

        assert response.status_code == 400

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_regenerate_secret_404(self, mock_repo_cls, app_with_tenant_admin):
        """Regenerate secret for non-existent app returns 404."""
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_cls.return_value = mock_repo

        fake_id = str(uuid.uuid4())
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(f"/v1/applications/{fake_id}/regenerate-secret")

        assert response.status_code == 404
