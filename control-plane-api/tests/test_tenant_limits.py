"""Tests for tenant usage limits — CAB-1549

Covers:
- GET /v1/tenants/{tenant_id}/usage (counts + limits)
- PUT /v1/tenants/{tenant_id} (configuring limits)
- POST /v1/tenants/{tenant_id}/apis (limit enforcement)
- POST /v1/tenants/{tenant_id}/applications (limit enforcement)
"""

from unittest.mock import AsyncMock, MagicMock, patch

TENANT_REPO = "src.routers.tenants.TenantRepository"
GIT_SVC = "src.routers.tenants.git_service"
KC_SVC = "src.routers.tenants.keycloak_service"
CACHE = "src.routers.tenants.tenant_cache"
KAFKA = "src.routers.tenants.kafka_service"
API_GIT_SVC = "src.routers.apis.git_service"
API_TENANT_REPO = "src.routers.apis.TenantRepository"
APP_KC_SVC = "src.routers.applications.keycloak_service"
APP_TENANT_REPO = "src.routers.applications.TenantRepository"
TENANT_ID = "acme"


def _make_tenant(max_apis=None, max_applications=None, **overrides):
    """Create a mock Tenant model with optional limits in settings."""
    mock = MagicMock()
    settings = {"owner_email": "admin@acme.com"}
    if max_apis is not None:
        settings["max_apis"] = max_apis
    if max_applications is not None:
        settings["max_applications"] = max_applications
    defaults = {
        "id": TENANT_ID,
        "name": "ACME Corporation",
        "description": "Test tenant",
        "status": "active",
        "provisioning_status": "ready",
        "provisioning_error": None,
        "provisioning_started_at": None,
        "provisioning_attempts": 0,
        "kc_group_id": "kc-group-123",
        "settings": settings,
        "created_at": MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00")),
        "updated_at": MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00")),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestGetTenantUsage:
    """Tests for GET /v1/tenants/{tenant_id}/usage."""

    def test_usage_returns_counts_and_defaults(self, client_as_tenant_admin):
        tenant = _make_tenant()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(TENANT_REPO) as MockRepo,
            patch(GIT_SVC) as mock_git,
            patch(KC_SVC) as mock_kc,
        ):
            MockRepo.return_value = mock_repo
            mock_git.list_apis = AsyncMock(return_value=[{"id": "api-1"}, {"id": "api-2"}])
            mock_kc.get_clients = AsyncMock(return_value=[{"id": "app-1"}])
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/usage")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == TENANT_ID
        assert data["api_count"] == 2
        assert data["max_apis"] == 10  # default
        assert data["application_count"] == 1
        assert data["max_applications"] == 20  # default

    def test_usage_returns_custom_limits(self, client_as_tenant_admin):
        tenant = _make_tenant(max_apis=5, max_applications=8)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(TENANT_REPO) as MockRepo,
            patch(GIT_SVC) as mock_git,
            patch(KC_SVC) as mock_kc,
        ):
            MockRepo.return_value = mock_repo
            mock_git.list_apis = AsyncMock(return_value=[])
            mock_kc.get_clients = AsyncMock(return_value=[])
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/usage")

        assert resp.status_code == 200
        data = resp.json()
        assert data["max_apis"] == 5
        assert data["max_applications"] == 8

    def test_usage_404_tenant_not_found(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(TENANT_REPO) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/usage")

        assert resp.status_code == 404

    def test_usage_403_other_tenant(self, client_as_other_tenant):
        resp = client_as_other_tenant.get(f"/v1/tenants/{TENANT_ID}/usage")
        assert resp.status_code == 403

    def test_usage_graceful_on_service_error(self, client_as_tenant_admin):
        tenant = _make_tenant()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(TENANT_REPO) as MockRepo,
            patch(GIT_SVC) as mock_git,
            patch(KC_SVC) as mock_kc,
        ):
            MockRepo.return_value = mock_repo
            mock_git.list_apis = AsyncMock(side_effect=RuntimeError("GitLab down"))
            mock_kc.get_clients = AsyncMock(side_effect=RuntimeError("KC down"))
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/usage")

        assert resp.status_code == 200
        data = resp.json()
        assert data["api_count"] == 0
        assert data["application_count"] == 0


class TestUpdateTenantLimits:
    """Tests for PUT /v1/tenants/{tenant_id} — updating limits."""

    def test_update_limits(self, client_as_cpi_admin):
        tenant = _make_tenant()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)
        mock_repo.update = AsyncMock(return_value=tenant)

        with (
            patch(TENANT_REPO) as MockRepo,
            patch(CACHE) as mock_cache,
            patch(KAFKA) as mock_kafka,
        ):
            MockRepo.return_value = mock_repo
            mock_cache.delete = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()
            resp = client_as_cpi_admin.put(
                f"/v1/tenants/{TENANT_ID}",
                json={"max_apis": 50, "max_applications": 100},
            )

        assert resp.status_code == 200
        # Verify settings were updated on the tenant object
        assert tenant.settings["max_apis"] == 50
        assert tenant.settings["max_applications"] == 100


class TestApiCreationLimit:
    """Tests for POST /v1/tenants/{tenant_id}/apis — limit enforcement."""

    def test_create_api_under_limit(self, client_as_tenant_admin):
        tenant = _make_tenant(max_apis=5)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(API_TENANT_REPO) as MockRepo,
            patch(API_GIT_SVC) as mock_git,
            patch("src.routers.apis.kafka_service") as mock_kafka,
        ):
            MockRepo.return_value = mock_repo
            mock_git.list_apis = AsyncMock(return_value=[{"id": "1"}, {"id": "2"}])
            mock_git.create_api = AsyncMock()
            mock_kafka.emit_api_created = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()
            resp = client_as_tenant_admin.post(
                f"/v1/tenants/{TENANT_ID}/apis",
                json={
                    "name": "new-api",
                    "display_name": "New API",
                    "backend_url": "https://backend.example.com",
                },
            )

        assert resp.status_code == 200

    def test_create_api_at_limit_returns_429(self, client_as_tenant_admin):
        tenant = _make_tenant(max_apis=2)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(API_TENANT_REPO) as MockRepo,
            patch(API_GIT_SVC) as mock_git,
        ):
            MockRepo.return_value = mock_repo
            mock_git.list_apis = AsyncMock(return_value=[{"id": "1"}, {"id": "2"}])
            resp = client_as_tenant_admin.post(
                f"/v1/tenants/{TENANT_ID}/apis",
                json={
                    "name": "new-api",
                    "display_name": "New API",
                    "backend_url": "https://backend.example.com",
                },
            )

        assert resp.status_code == 429
        assert "limit reached" in resp.json()["detail"].lower()


class TestApplicationCreationLimit:
    """Tests for POST /v1/tenants/{tenant_id}/applications — limit enforcement."""

    def test_create_app_under_limit(self, client_as_tenant_admin):
        tenant = _make_tenant(max_applications=5)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(APP_TENANT_REPO) as MockRepo,
            patch(APP_KC_SVC) as mock_kc,
        ):
            MockRepo.return_value = mock_repo
            mock_kc.get_clients = AsyncMock(return_value=[{"id": "1"}])
            mock_kc.create_client = AsyncMock(return_value={"id": "new-app-id"})
            mock_kc.update_client = AsyncMock()
            mock_kc.get_client_by_id = AsyncMock(
                return_value={
                    "id": "new-app-id",
                    "clientId": f"{TENANT_ID}-test-app",
                    "name": "Test App",
                    "description": "",
                    "enabled": True,
                    "attributes": {
                        "tenant_id": TENANT_ID,
                        "api_subscriptions": "[]",
                        "created_at": "2026-01-01T00:00:00",
                        "updated_at": "2026-01-01T00:00:00",
                    },
                }
            )
            resp = client_as_tenant_admin.post(
                f"/v1/tenants/{TENANT_ID}/applications",
                json={
                    "name": "test-app",
                    "display_name": "Test App",
                },
            )

        assert resp.status_code == 201

    def test_create_app_at_limit_returns_429(self, client_as_tenant_admin):
        tenant = _make_tenant(max_applications=1)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(APP_TENANT_REPO) as MockRepo,
            patch(APP_KC_SVC) as mock_kc,
        ):
            MockRepo.return_value = mock_repo
            mock_kc.get_clients = AsyncMock(return_value=[{"id": "1"}])
            resp = client_as_tenant_admin.post(
                f"/v1/tenants/{TENANT_ID}/applications",
                json={
                    "name": "test-app",
                    "display_name": "Test App",
                },
            )

        assert resp.status_code == 429
        assert "limit reached" in resp.json()["detail"].lower()
