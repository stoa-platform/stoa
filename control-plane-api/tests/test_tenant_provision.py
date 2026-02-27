"""Tests for POST /v1/tenants/provision — CAB-1547

Covers: idempotent provisioning, Keycloak realm creation (mocked), error handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

REPO_PATH = "src.routers.tenants.TenantRepository"
KC_PATH = "src.routers.tenants.keycloak_service"
KAFKA_PATH = "src.routers.tenants.kafka_service"
TENANT_ID = "acme"

PROVISION_PAYLOAD = {
    "name": "acme",
    "display_name": "ACME Corporation",
    "owner_email": "admin@acme.com",
}


def _make_tenant(**overrides):
    """Create a mock Tenant model."""
    mock = MagicMock()
    defaults = {
        "id": TENANT_ID,
        "name": "ACME Corporation",
        "description": "",
        "status": "active",
        "provisioning_status": "ready",
        "provisioning_error": None,
        "provisioning_started_at": None,
        "provisioning_attempts": 0,
        "kc_group_id": None,
        "settings": {"owner_email": "admin@acme.com"},
        "created_at": MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00")),
        "updated_at": MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00")),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestProvisionTenant:
    """Tests for POST /v1/tenants/provision."""

    def test_provision_success(self, client_as_cpi_admin):
        """New tenant is provisioned with KC realm and DB record."""
        tenant = _make_tenant(provisioning_status="ready")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=tenant)
        mock_repo.update = AsyncMock(return_value=tenant)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(KC_PATH) as mock_kc,
            patch(KAFKA_PATH) as mock_kafka,
        ):
            MockRepo.return_value = mock_repo
            mock_kc.create_realm = AsyncMock(return_value="acme")
            mock_kafka.emit_audit_event = AsyncMock()
            resp = client_as_cpi_admin.post("/v1/tenants/provision", json=PROVISION_PAYLOAD)

        assert resp.status_code == 201
        data = resp.json()
        assert data["tenant_id"] == TENANT_ID
        assert data["realm_name"] == TENANT_ID
        assert data["provisioning_status"] == "ready"
        mock_kc.create_realm.assert_awaited_once_with(realm_name="acme", display_name="ACME Corporation")

    def test_provision_idempotent(self, client_as_cpi_admin):
        """Existing tenant is returned without creating a new one."""
        existing = _make_tenant(provisioning_status="ready")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=existing)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_cpi_admin.post("/v1/tenants/provision", json=PROVISION_PAYLOAD)

        assert resp.status_code == 201
        data = resp.json()
        assert data["tenant_id"] == TENANT_ID
        assert data["provisioning_status"] == "ready"
        mock_repo.create.assert_not_called()

    def test_provision_kc_failure_marks_failed(self, client_as_cpi_admin):
        """Keycloak realm creation failure marks tenant as failed."""
        tenant = _make_tenant(provisioning_status="provisioning")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(side_effect=[None, tenant])
        mock_repo.create = AsyncMock(return_value=tenant)
        mock_repo.update = AsyncMock(return_value=tenant)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(KC_PATH) as mock_kc,
        ):
            MockRepo.return_value = mock_repo
            mock_kc.create_realm = AsyncMock(side_effect=RuntimeError("KC unreachable"))
            resp = client_as_cpi_admin.post("/v1/tenants/provision", json=PROVISION_PAYLOAD)

        assert resp.status_code == 500
        assert "Provisioning failed" in resp.json()["detail"]

    def test_provision_forbidden_for_non_admin(self, client_as_tenant_admin):
        """Non-CPI-admin users cannot provision tenants."""
        resp = client_as_tenant_admin.post("/v1/tenants/provision", json=PROVISION_PAYLOAD)
        assert resp.status_code == 403

    def test_provision_generates_slug_from_name(self, client_as_cpi_admin):
        """Tenant ID is generated as lowercase slug from name."""
        tenant = _make_tenant(id="my-new-tenant", provisioning_status="ready")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=tenant)
        mock_repo.update = AsyncMock(return_value=tenant)

        payload = {
            "name": "My New Tenant",
            "display_name": "My New Tenant Corp",
            "owner_email": "owner@new.com",
        }

        with (
            patch(REPO_PATH) as MockRepo,
            patch(KC_PATH) as mock_kc,
            patch(KAFKA_PATH) as mock_kafka,
        ):
            MockRepo.return_value = mock_repo
            mock_kc.create_realm = AsyncMock(return_value="my-new-tenant")
            mock_kafka.emit_audit_event = AsyncMock()
            resp = client_as_cpi_admin.post("/v1/tenants/provision", json=payload)

        assert resp.status_code == 201
        mock_kc.create_realm.assert_awaited_once_with(realm_name="my-new-tenant", display_name="My New Tenant Corp")

    def test_provision_emits_audit_event(self, client_as_cpi_admin):
        """Provisioning emits a Kafka audit event."""
        tenant = _make_tenant(provisioning_status="ready")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=tenant)
        mock_repo.update = AsyncMock(return_value=tenant)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(KC_PATH) as mock_kc,
            patch(KAFKA_PATH) as mock_kafka,
        ):
            MockRepo.return_value = mock_repo
            mock_kc.create_realm = AsyncMock(return_value="acme")
            mock_kafka.emit_audit_event = AsyncMock()
            resp = client_as_cpi_admin.post("/v1/tenants/provision", json=PROVISION_PAYLOAD)

        assert resp.status_code == 201
        mock_kafka.emit_audit_event.assert_awaited_once()
        call_kwargs = mock_kafka.emit_audit_event.call_args.kwargs
        assert call_kwargs["action"] == "provision"
        assert call_kwargs["resource_type"] == "tenant"
