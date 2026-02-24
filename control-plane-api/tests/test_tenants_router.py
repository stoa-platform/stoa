"""Tests for Tenants Router — CAB-1448

Covers: /v1/tenants (list, get, provisioning-status, create, update, delete).
"""

from unittest.mock import AsyncMock, MagicMock, patch

REPO_PATH = "src.routers.tenants.TenantRepository"
CACHE_PATH = "src.routers.tenants.tenant_cache"
KAFKA_PATH = "src.routers.tenants.kafka_service"
PROVISION_PATH = "src.routers.tenants.provision_tenant"
DEPROVISION_PATH = "src.routers.tenants.deprovision_tenant"
TENANT_ID = "acme"


def _make_tenant(**overrides):
    """Create a mock Tenant model."""
    mock = MagicMock()
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
        "settings": {"owner_email": "admin@acme.com"},
        "created_at": MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00")),
        "updated_at": MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00")),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestListTenants:
    """Tests for GET /v1/tenants."""

    def test_list_tenants_cpi_admin(self, client_as_cpi_admin):
        tenant = _make_tenant()
        mock_repo = MagicMock()
        mock_repo.list_for_user = AsyncMock(return_value=[tenant])

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_cpi_admin.get("/v1/tenants")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_list_tenants_tenant_admin(self, client_as_tenant_admin):
        tenant = _make_tenant()
        mock_repo = MagicMock()
        mock_repo.list_for_user = AsyncMock(return_value=[tenant])

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get("/v1/tenants")

        assert resp.status_code == 200

    def test_list_tenants_error_returns_empty(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.list_for_user = AsyncMock(side_effect=RuntimeError("DB down"))

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get("/v1/tenants")

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetTenant:
    """Tests for GET /v1/tenants/{tenant_id}."""

    def test_get_tenant_success(self, client_as_tenant_admin):
        tenant = _make_tenant()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with patch(REPO_PATH) as MockRepo, patch(CACHE_PATH) as mock_cache:
            MockRepo.return_value = mock_repo
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == TENANT_ID

    def test_get_tenant_404(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo, patch(CACHE_PATH) as mock_cache:
            MockRepo.return_value = mock_repo
            mock_cache.get = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}")

        assert resp.status_code == 404

    def test_get_tenant_403_other_tenant(self, client_as_other_tenant):
        resp = client_as_other_tenant.get(f"/v1/tenants/{TENANT_ID}")
        assert resp.status_code == 403

    def test_get_tenant_cpi_admin_cross_tenant(self, client_as_cpi_admin):
        tenant = _make_tenant()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with patch(REPO_PATH) as MockRepo, patch(CACHE_PATH) as mock_cache:
            MockRepo.return_value = mock_repo
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            resp = client_as_cpi_admin.get(f"/v1/tenants/{TENANT_ID}")

        assert resp.status_code == 200


class TestGetProvisioningStatus:
    """Tests for GET /v1/tenants/{tenant_id}/provisioning-status."""

    def test_provisioning_status_success(self, client_as_tenant_admin):
        tenant = _make_tenant()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/provisioning-status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == TENANT_ID
        assert data["provisioning_status"] == "ready"

    def test_provisioning_status_404(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/provisioning-status")

        assert resp.status_code == 404


class TestCreateTenant:
    """Tests for POST /v1/tenants."""

    def test_create_success(self, client_as_cpi_admin):
        tenant = _make_tenant(id="new-tenant")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=tenant)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(KAFKA_PATH) as mock_kafka,
            patch(PROVISION_PATH, new_callable=AsyncMock),
        ):
            MockRepo.return_value = mock_repo
            mock_kafka.publish = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()
            resp = client_as_cpi_admin.post(
                "/v1/tenants",
                json={
                    "name": "New Tenant",
                    "display_name": "New Tenant Corp",
                    "owner_email": "owner@new.com",
                },
            )

        assert resp.status_code == 200

    def test_create_duplicate_409(self, client_as_cpi_admin):
        existing = _make_tenant()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=existing)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_cpi_admin.post(
                "/v1/tenants",
                json={
                    "name": "acme",
                    "display_name": "ACME",
                    "owner_email": "admin@acme.com",
                },
            )

        assert resp.status_code == 409


class TestUpdateTenant:
    """Tests for PUT /v1/tenants/{tenant_id}."""

    def test_update_success(self, client_as_cpi_admin):
        tenant = _make_tenant()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)
        mock_repo.update = AsyncMock(return_value=tenant)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(CACHE_PATH) as mock_cache,
            patch(KAFKA_PATH) as mock_kafka,
        ):
            MockRepo.return_value = mock_repo
            mock_cache.delete = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()
            resp = client_as_cpi_admin.put(
                f"/v1/tenants/{TENANT_ID}",
                json={"display_name": "Updated ACME"},
            )

        assert resp.status_code == 200

    def test_update_404(self, client_as_cpi_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_cpi_admin.put(
                f"/v1/tenants/{TENANT_ID}",
                json={"display_name": "test"},
            )

        assert resp.status_code == 404


class TestDeleteTenant:
    """Tests for DELETE /v1/tenants/{tenant_id}."""

    def test_delete_success(self, client_as_cpi_admin):
        tenant = _make_tenant()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(CACHE_PATH) as mock_cache,
            patch(KAFKA_PATH) as mock_kafka,
            patch(DEPROVISION_PATH, new_callable=AsyncMock),
        ):
            MockRepo.return_value = mock_repo
            mock_cache.delete = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()
            resp = client_as_cpi_admin.delete(f"/v1/tenants/{TENANT_ID}")

        assert resp.status_code == 200
        assert "deprovisioning" in resp.json()["message"].lower()

    def test_delete_404(self, client_as_cpi_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_cpi_admin.delete(f"/v1/tenants/{TENANT_ID}")

        assert resp.status_code == 404
