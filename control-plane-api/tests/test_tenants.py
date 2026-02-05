"""
Tests for Tenants Router - CAB-839

Target: 80%+ coverage on src/routers/tenants.py
Tests: 16 test cases covering CRUD, RBAC, and multi-tenant isolation.
Updated to match DB-backed TenantRepository router (no more git_service).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from src.models.tenant import Tenant, TenantStatus


def _make_tenant(
    tenant_id="acme",
    name="ACME Corporation",
    description="Test tenant",
    status="active",
    owner_email="admin@acme.com",
):
    """Create a mock Tenant ORM object."""
    tenant = MagicMock(spec=Tenant)
    tenant.id = tenant_id
    tenant.name = name
    tenant.description = description
    tenant.status = status
    tenant.settings = {"owner_email": owner_email}
    tenant.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    tenant.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return tenant


class TestTenantsRouter:
    """Test suite for Tenants Router endpoints."""

    # ============== List Tenants Tests ==============

    def test_list_tenants_cpi_admin_sees_all(self, app_with_cpi_admin, mock_db_session):
        """Test CPI Admin can see all tenants."""
        tenants = [
            _make_tenant("acme", "ACME Corp"),
            _make_tenant("beta-corp", "Beta Corp"),
        ]

        mock_repo = MagicMock()
        mock_repo.list_for_user = AsyncMock(return_value=tenants)

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/tenants")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_list_tenants_tenant_admin_sees_own(self, app_with_tenant_admin, mock_db_session):
        """Test Tenant Admin can only see their own tenant."""
        tenant = _make_tenant("acme", "ACME Corporation")
        mock_repo = MagicMock()
        mock_repo.list_for_user = AsyncMock(return_value=[tenant])

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/tenants")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "acme"

    # ============== Get Tenant Tests ==============

    def test_get_tenant_success(self, app_with_tenant_admin, mock_db_session):
        """Test getting tenant details by ID."""
        tenant = _make_tenant("acme", "ACME Corporation")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/tenants/acme")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "acme"

    def test_get_tenant_404(self, app_with_cpi_admin, mock_db_session):
        """Test getting non-existent tenant returns 404."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/tenants/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_get_tenant_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        """Test user from different tenant cannot access another tenant."""
        with TestClient(app_with_other_tenant) as client:
            response = client.get("/v1/tenants/acme")

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    # ============== Create Tenant Tests ==============

    def test_create_tenant_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        """Test CPI Admin can create a new tenant."""
        created_tenant = _make_tenant("new-tenant", "New Tenant Corp", owner_email="owner@newtenant.com")

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=created_tenant)

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo), \
             patch("src.routers.tenants.keycloak_service") as mock_keycloak, \
             patch("src.routers.tenants.kafka_service") as mock_kafka:

            mock_keycloak.setup_tenant_group = AsyncMock(return_value=True)
            mock_kafka.publish = AsyncMock(return_value=True)
            mock_kafka.emit_audit_event = AsyncMock(return_value=True)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/v1/tenants",
                    json={
                        "name": "New Tenant",
                        "display_name": "New Tenant Corp",
                        "description": "A new test tenant",
                        "owner_email": "owner@newtenant.com",
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "new-tenant"
        assert data["status"] == "active"

    def test_create_tenant_403_not_admin(self, app_with_tenant_admin, mock_db_session):
        """Test non-admin cannot create tenant."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/tenants",
                json={
                    "name": "Unauthorized Tenant",
                    "display_name": "Should Fail",
                    "description": "This should be denied",
                    "owner_email": "fail@example.com",
                },
            )

        assert response.status_code == 403

    def test_create_tenant_409_already_exists(self, app_with_cpi_admin, mock_db_session):
        """Test creating duplicate tenant returns 409."""
        existing = _make_tenant("existing-tenant")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=existing)

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/v1/tenants",
                    json={
                        "name": "existing-tenant",
                        "display_name": "Existing",
                        "description": "Already exists",
                        "owner_email": "x@x.com",
                    },
                )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    # ============== Update Tenant Tests ==============

    def test_update_tenant_success(self, app_with_cpi_admin, mock_db_session):
        """Test CPI Admin can update tenant."""
        tenant = _make_tenant("acme", "ACME Corporation")
        updated_tenant = _make_tenant("acme", "Updated ACME Corp")

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)
        mock_repo.update = AsyncMock(return_value=updated_tenant)

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo), \
             patch("src.routers.tenants.kafka_service") as mock_kafka:

            mock_kafka.emit_audit_event = AsyncMock(return_value=True)

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    "/v1/tenants/acme",
                    json={"display_name": "Updated ACME Corp"},
                )

        assert response.status_code == 200

    def test_update_tenant_404(self, app_with_cpi_admin, mock_db_session):
        """Test updating non-existent tenant returns 404."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    "/v1/tenants/nonexistent",
                    json={"display_name": "Updated Name"},
                )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_update_tenant_no_changes(self, app_with_cpi_admin, mock_db_session):
        """Test PUT /{id} with no changes returns current data (no-op)."""
        tenant = _make_tenant("acme", "ACME Corporation")

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo), \
             patch("src.routers.tenants.kafka_service") as mock_kafka:

            mock_kafka.emit_audit_event = AsyncMock(return_value=True)

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    "/v1/tenants/acme",
                    json={},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "acme"
        assert not mock_kafka.emit_audit_event.called

    # ============== Delete Tenant Tests ==============

    def test_delete_tenant_success(self, app_with_cpi_admin, mock_db_session):
        """Test CPI Admin can archive tenant."""
        tenant = _make_tenant("acme", "ACME Corporation")

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)
        mock_repo.update = AsyncMock(return_value=tenant)

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo), \
             patch("src.routers.tenants.kafka_service") as mock_kafka:

            mock_kafka.publish = AsyncMock(return_value=True)
            mock_kafka.emit_audit_event = AsyncMock(return_value=True)

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete("/v1/tenants/acme")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Tenant archived"
        assert data["id"] == "acme"

    def test_delete_tenant_404(self, app_with_cpi_admin, mock_db_session):
        """Test deleting non-existent tenant returns 404."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                response = client.delete("/v1/tenants/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    # ============== Error Handling Tests ==============

    def test_list_tenants_error_returns_empty(self, app_with_cpi_admin, mock_db_session):
        """Test list tenants returns empty list when repo fails."""
        mock_repo = MagicMock()
        mock_repo.list_for_user = AsyncMock(side_effect=Exception("DB connection failed"))

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/tenants")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_create_tenant_keycloak_failure(self, app_with_cpi_admin, mock_db_session):
        """Test POST / succeeds even if Keycloak setup fails."""
        created_tenant = _make_tenant("new-tenant", "New Tenant Corp", owner_email="owner@newtenant.com")

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=created_tenant)

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo), \
             patch("src.routers.tenants.keycloak_service") as mock_keycloak, \
             patch("src.routers.tenants.kafka_service") as mock_kafka:

            mock_keycloak.setup_tenant_group = AsyncMock(side_effect=Exception("Keycloak unavailable"))
            mock_kafka.publish = AsyncMock(return_value=True)
            mock_kafka.emit_audit_event = AsyncMock(return_value=True)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/v1/tenants",
                    json={
                        "name": "New Tenant",
                        "display_name": "New Tenant Corp",
                        "description": "A new test tenant",
                        "owner_email": "owner@newtenant.com",
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "new-tenant"
        assert data["status"] == "active"

    def test_update_tenant_error(self, app_with_cpi_admin, mock_db_session):
        """Test PUT /{id} when repo fails returns 500."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(side_effect=Exception("DB connection timeout"))

        with patch("src.routers.tenants.TenantRepository", return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    "/v1/tenants/acme",
                    json={"display_name": "Updated Name"},
                )

        assert response.status_code == 500
        assert "Failed to update tenant" in response.json()["detail"]
