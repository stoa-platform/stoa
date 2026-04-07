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

from src.models.portal_application import PortalApplication, PortalAppStatus, SecurityProfile


def _make_app(
    owner_id: str = "tenant-admin-user-id",
    name: str = "my-app",
    display_name: str = "My App",
    tenant_id: str = "acme",
    keycloak_client_id: str | None = "kc-client-id",
    keycloak_client_uuid: str | None = "kc-uuid-001",
    status: PortalAppStatus = PortalAppStatus.ACTIVE,
    security_profile: SecurityProfile = SecurityProfile.OAUTH2_PUBLIC,
    api_key_hash: str | None = None,
    api_key_prefix: str | None = None,
    jwks_uri: str | None = None,
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
    app.security_profile = security_profile
    app.api_key_hash = api_key_hash
    app.api_key_prefix = api_key_prefix
    app.jwks_uri = jwks_uri
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
    def test_get_returns_app_for_admin_even_if_not_owner(self, mock_repo_cls, app_with_tenant_admin):
        """Admin can fetch any application regardless of ownership."""
        app = _make_app(owner_id="someone-else-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/applications/{app.id}")

        assert resp.status_code == 200
        assert resp.json()["name"] == "my-app"

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_get_returns_403_for_non_owner_viewer(self, mock_repo_cls, app_with_viewer):
        """Non-admin non-owner gets 403."""
        app = _make_app(owner_id="someone-else-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_viewer) as client:
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
    def test_update_allowed_for_admin_non_owner(self, mock_repo_cls, app_with_tenant_admin):
        """Admin can update any application regardless of ownership."""
        app = _make_app(owner_id="someone-else")
        updated_app = _make_app(owner_id="someone-else", display_name="Updated")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo.update.return_value = updated_app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.patch(
                f"/v1/applications/{app.id}",
                json={"display_name": "Updated"},
            )

        assert resp.status_code == 200

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_update_returns_403_for_non_owner_viewer(self, mock_repo_cls, app_with_viewer):
        """Non-admin non-owner gets 403 on PATCH."""
        app = _make_app(owner_id="someone-else")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_viewer) as client:
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

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_delete_allowed_for_admin_non_owner(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """Admin can delete any application regardless of ownership."""
        app = _make_app(owner_id="another-user-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo.delete = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_kc.delete_client = AsyncMock()

        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/applications/{app.id}")

        assert resp.status_code == 200

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_delete_returns_403_for_non_owner_viewer(self, mock_repo_cls, app_with_viewer):
        """Non-admin non-owner cannot delete the application."""
        app = _make_app(owner_id="another-user-id")
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_viewer) as client:
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


# ============== Environment Filter (CAB-1665) ==============


class TestListApplicationsEnvironmentFilter:
    """GET /v1/applications?environment= — CAB-1665."""

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_environment_param_passed_to_repo(self, mock_repo_cls, app_with_tenant_admin):
        """When environment is provided, it is forwarded to the repository."""
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([], 0)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/applications?environment=dev")

        assert resp.status_code == 200
        call_kwargs = mock_repo.list_by_owner.call_args[1]
        assert call_kwargs["environment"] == "dev"

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_no_environment_param_passes_none(self, mock_repo_cls, app_with_tenant_admin):
        """When environment is omitted, None is forwarded (returns all)."""
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([], 0)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/applications")

        assert resp.status_code == 200
        call_kwargs = mock_repo.list_by_owner.call_args[1]
        assert call_kwargs["environment"] is None


# ---------------------------------------------------------------------------
# Security Profile (CAB-1744)
# ---------------------------------------------------------------------------


class TestSecurityProfile:
    """POST /v1/applications — security_profile parameter."""

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_default_profile_is_oauth2_public(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """When no security_profile is specified, defaults to oauth2_public."""
        created_app = _make_app(security_profile=SecurityProfile.OAUTH2_PUBLIC)
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = None
        mock_repo.create.return_value = created_app
        mock_repo_cls.return_value = mock_repo
        mock_kc.create_client = AsyncMock(
            return_value={"client_id": "cid", "id": "uuid", "client_secret": None}
        )

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/applications",
                json={"name": "pub-app", "display_name": "Public App"},
            )

        assert resp.status_code == 200
        assert resp.json()["security_profile"] == "oauth2_public"
        # KC called with profile parameter
        mock_kc.create_client.assert_awaited_once()
        call_kwargs = mock_kc.create_client.call_args[1]
        assert call_kwargs["security_profile"] == "oauth2_public"

    @patch("src.routers.portal_applications.api_key_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_api_key_profile_skips_keycloak(self, mock_repo_cls, mock_api_key, app_with_tenant_admin):
        """api_key profile generates an API key and skips Keycloak."""
        created_app = _make_app(
            security_profile=SecurityProfile.API_KEY,
            keycloak_client_id=None,
            keycloak_client_uuid=None,
            api_key_hash="abc123hash",
            api_key_prefix="stoa_sk_abcd",
        )
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = None
        mock_repo.create.return_value = created_app
        mock_repo_cls.return_value = mock_repo
        mock_api_key.generate_key.return_value = ("stoa_sk_full_key_value", "abc123hash", "stoa_sk_abcd")

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/applications",
                json={"name": "key-app", "display_name": "Key App", "security_profile": "api_key"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["security_profile"] == "api_key"
        assert data["api_key"] == "stoa_sk_full_key_value"
        assert data["api_key_prefix"] == "stoa_sk_abcd"
        assert data["client_secret"] is None
        mock_api_key.generate_key.assert_called_once()

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_oauth2_confidential_profile(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """oauth2_confidential profile creates confidential KC client."""
        created_app = _make_app(security_profile=SecurityProfile.OAUTH2_CONFIDENTIAL)
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = None
        mock_repo.create.return_value = created_app
        mock_repo_cls.return_value = mock_repo
        mock_kc.create_client = AsyncMock(
            return_value={"client_id": "cid", "id": "uuid", "client_secret": "conf-secret"}
        )

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/applications",
                json={
                    "name": "conf-app",
                    "display_name": "Confidential App",
                    "security_profile": "oauth2_confidential",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["security_profile"] == "oauth2_confidential"
        assert data["client_secret"] == "conf-secret"
        call_kwargs = mock_kc.create_client.call_args[1]
        assert call_kwargs["security_profile"] == "oauth2_confidential"

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_fapi_baseline_requires_jwks_uri(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """fapi_baseline without jwks_uri returns 422."""
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = None
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/applications",
                json={
                    "name": "fapi-app",
                    "display_name": "FAPI App",
                    "security_profile": "fapi_baseline",
                },
            )

        assert resp.status_code == 422
        assert "jwks_uri" in resp.json()["detail"]

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_fapi_baseline_with_jwks_uri(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """fapi_baseline with jwks_uri creates the application."""
        created_app = _make_app(
            security_profile=SecurityProfile.FAPI_BASELINE,
            jwks_uri="https://client.example.com/.well-known/jwks.json",
        )
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = None
        mock_repo.create.return_value = created_app
        mock_repo_cls.return_value = mock_repo
        mock_kc.create_client = AsyncMock(
            return_value={"client_id": "cid", "id": "uuid", "client_secret": "fapi-secret"}
        )

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/applications",
                json={
                    "name": "fapi-app",
                    "display_name": "FAPI App",
                    "security_profile": "fapi_baseline",
                    "jwks_uri": "https://client.example.com/.well-known/jwks.json",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["security_profile"] == "fapi_baseline"
        assert data["jwks_uri"] == "https://client.example.com/.well-known/jwks.json"
        call_kwargs = mock_kc.create_client.call_args[1]
        assert call_kwargs["security_profile"] == "fapi_baseline"

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_fapi_advanced_requires_jwks_uri(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """fapi_advanced without jwks_uri returns 422."""
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = None
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/applications",
                json={
                    "name": "fapi-adv",
                    "display_name": "FAPI Adv",
                    "security_profile": "fapi_advanced",
                },
            )

        assert resp.status_code == 422

    @patch("src.routers.portal_applications.keycloak_service")
    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_create_fapi_advanced_with_dpop(self, mock_repo_cls, mock_kc, app_with_tenant_admin):
        """fapi_advanced sets DPoP attributes on the KC client."""
        created_app = _make_app(
            security_profile=SecurityProfile.FAPI_ADVANCED,
            jwks_uri="https://client.example.com/jwks",
        )
        mock_repo = AsyncMock()
        mock_repo.get_by_owner_and_name.return_value = None
        mock_repo.create.return_value = created_app
        mock_repo_cls.return_value = mock_repo
        mock_kc.create_client = AsyncMock(
            return_value={"client_id": "cid", "id": "uuid", "client_secret": "fapi-adv-secret"}
        )

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/applications",
                json={
                    "name": "fapi-adv",
                    "display_name": "FAPI Adv",
                    "security_profile": "fapi_advanced",
                    "jwks_uri": "https://client.example.com/jwks",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["security_profile"] == "fapi_advanced"
        call_kwargs = mock_kc.create_client.call_args[1]
        assert call_kwargs["security_profile"] == "fapi_advanced"

    def test_invalid_security_profile_rejected(self, app_with_tenant_admin):
        """Invalid security_profile value returns 422."""
        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/applications",
                json={
                    "name": "bad-app",
                    "display_name": "Bad App",
                    "security_profile": "not_a_profile",
                },
            )

        assert resp.status_code == 422

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_response_includes_security_profile(self, mock_repo_cls, app_with_tenant_admin):
        """GET response includes security_profile field."""
        app = _make_app(
            owner_id="tenant-admin-user-id",
            security_profile=SecurityProfile.OAUTH2_CONFIDENTIAL,
        )
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = app
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/applications/{app.id}")

        assert resp.status_code == 200
        assert resp.json()["security_profile"] == "oauth2_confidential"

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_list_includes_security_profile(self, mock_repo_cls, app_with_tenant_admin):
        """GET /v1/applications list includes security_profile for each app."""
        apps = [
            _make_app(name="app-1", security_profile=SecurityProfile.API_KEY),
            _make_app(name="app-2", security_profile=SecurityProfile.FAPI_BASELINE),
        ]
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = (apps, 2)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/applications")

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items[0]["security_profile"] == "api_key"
        assert items[1]["security_profile"] == "fapi_baseline"


# ---------------------------------------------------------------------------
# Admin visibility — list all apps regardless of ownership
# ---------------------------------------------------------------------------


class TestAdminListsAllApplications:
    """GET /v1/applications — admin sees all apps, viewer sees only own."""

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_admin_list_passes_is_admin_true(self, mock_repo_cls, app_with_cpi_admin):
        """cpi-admin triggers is_admin=True on list_by_owner."""
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([], 0)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/applications")

        assert resp.status_code == 200
        call_kwargs = mock_repo.list_by_owner.call_args[1]
        assert call_kwargs["is_admin"] is True

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_tenant_admin_list_passes_is_admin_true(self, mock_repo_cls, app_with_tenant_admin):
        """tenant-admin triggers is_admin=True on list_by_owner."""
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([], 0)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/applications")

        assert resp.status_code == 200
        call_kwargs = mock_repo.list_by_owner.call_args[1]
        assert call_kwargs["is_admin"] is True

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_viewer_list_passes_is_admin_false(self, mock_repo_cls, app_with_viewer):
        """viewer triggers is_admin=False — only sees own apps."""
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = ([], 0)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_viewer) as client:
            resp = client.get("/v1/applications")

        assert resp.status_code == 200
        call_kwargs = mock_repo.list_by_owner.call_args[1]
        assert call_kwargs["is_admin"] is False

    @patch("src.routers.portal_applications.PortalApplicationRepository")
    def test_response_includes_owner_id(self, mock_repo_cls, app_with_cpi_admin):
        """Response includes owner_id so admin can see who owns each app."""
        apps = [_make_app(owner_id="user-A", name="app-A")]
        mock_repo = AsyncMock()
        mock_repo.list_by_owner.return_value = (apps, 1)
        mock_repo_cls.return_value = mock_repo

        with TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/applications")

        assert resp.status_code == 200
        assert resp.json()["items"][0]["owner_id"] == "user-A"
