"""
Tests for personal tenant auto-provisioning — POST /v1/me/tenant

6 test cases covering:
- Happy path (tenant created + KC group + role)
- Idempotent (user already has tenant)
- Username sanitization
- Slug collision retry
- Keycloak failure (non-blocking)
- User already has tenant_id in token
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.models.tenant import Tenant, TenantStatus


def _make_tenant(tenant_id="free-testuser", name="testuser's workspace", personal=True):
    """Create a mock Tenant ORM object for personal tenant tests."""
    tenant = MagicMock(spec=Tenant)
    tenant.id = tenant_id
    tenant.name = name
    tenant.description = "Personal tenant (auto-provisioned)"
    tenant.status = TenantStatus.ACTIVE.value
    tenant.settings = {"personal": personal, "owner_user_id": "no-tenant-user-id"}
    tenant.created_at = datetime(2026, 2, 15, tzinfo=UTC)
    tenant.updated_at = datetime(2026, 2, 15, tzinfo=UTC)
    return tenant


class TestPersonalTenantProvisioning:
    """Test suite for POST /v1/me/tenant endpoint."""

    def test_provision_creates_tenant_and_assigns_user(self, app_with_no_tenant_user, mock_db_session):
        """Happy path: creates tenant, KC group, assigns user + viewer role."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(side_effect=lambda t: t)  # Return the tenant as-is

        with (
            patch("src.routers.users.TenantRepository", return_value=mock_repo),
            patch("src.routers.users.keycloak_service") as mock_kc,
            patch("src.routers.users.kafka_service") as mock_kafka,
        ):
            mock_kc.setup_tenant_group = AsyncMock()
            mock_kc.add_user_to_tenant = AsyncMock()
            mock_kc.assign_role = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()

            with TestClient(app_with_no_tenant_user) as client:
                response = client.post("/v1/me/tenant")

        assert response.status_code == 201
        data = response.json()
        assert data["tenant_id"].startswith("free-")
        assert data["created"] is True

        # Verify KC calls
        mock_kc.setup_tenant_group.assert_called_once()
        mock_kc.add_user_to_tenant.assert_called_once()
        mock_kc.assign_role.assert_called_once_with("no-tenant-user-id", "viewer")

        # Verify audit event
        mock_kafka.emit_audit_event.assert_called_once()

    def test_provision_idempotent_returns_existing(self, app_with_tenant_admin, mock_db_session):
        """User already has tenant_id → returns existing tenant, no creation."""
        existing_tenant = _make_tenant("acme", "ACME Corporation", personal=False)

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=existing_tenant)

        with (
            patch("src.routers.users.TenantRepository", return_value=mock_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            response = client.post("/v1/me/tenant")

        assert response.status_code == 201
        data = response.json()
        assert data["tenant_id"] == "acme"
        assert data["created"] is False

    def test_provision_sanitizes_username(self, app, mock_db_session):
        """Special characters in username are sanitized to valid slug."""
        from tests.conftest import User

        user_with_special_chars = User(
            id="special-user-id",
            email="special@example.com",
            username="John.Doe@Corp!",
            roles=[],
            tenant_id=None,
        )

        from src.auth.dependencies import get_current_user
        from src.database import get_db

        app.dependency_overrides[get_current_user] = lambda: user_with_special_chars
        app.dependency_overrides[get_db] = lambda: mock_db_session.__aiter__()

        # Override get_db properly
        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(side_effect=lambda t: t)

        with (
            patch("src.routers.users.TenantRepository", return_value=mock_repo),
            patch("src.routers.users.keycloak_service") as mock_kc,
            patch("src.routers.users.kafka_service") as mock_kafka,
        ):
            mock_kc.setup_tenant_group = AsyncMock()
            mock_kc.add_user_to_tenant = AsyncMock()
            mock_kc.assign_role = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()

            with TestClient(app) as client:
                response = client.post("/v1/me/tenant")

        assert response.status_code == 201
        data = response.json()
        # Should be sanitized: lowercase, special chars → hyphens
        assert data["tenant_id"] == "free-john-doe-corp-"
        assert "!" not in data["tenant_id"]
        assert "@" not in data["tenant_id"]

        app.dependency_overrides.clear()

    def test_provision_handles_slug_conflict(self, app_with_no_tenant_user, mock_db_session):
        """Slug collision → retry with random suffix."""
        existing_tenant = _make_tenant("free-orphan-user")

        mock_repo = MagicMock()
        # First call returns existing (conflict), second returns None (available)
        mock_repo.get_by_id = AsyncMock(side_effect=[existing_tenant, None])
        mock_repo.create = AsyncMock(side_effect=lambda t: t)

        with (
            patch("src.routers.users.TenantRepository", return_value=mock_repo),
            patch("src.routers.users.keycloak_service") as mock_kc,
            patch("src.routers.users.kafka_service") as mock_kafka,
        ):
            mock_kc.setup_tenant_group = AsyncMock()
            mock_kc.add_user_to_tenant = AsyncMock()
            mock_kc.assign_role = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()

            with TestClient(app_with_no_tenant_user) as client:
                response = client.post("/v1/me/tenant")

        assert response.status_code == 201
        data = response.json()
        # Should have a suffix appended
        assert data["tenant_id"].startswith("free-orphan-user-")
        assert len(data["tenant_id"]) > len("free-orphan-user")

    def test_provision_keycloak_failure_non_blocking(self, app_with_no_tenant_user, mock_db_session):
        """Keycloak failure doesn't prevent tenant creation."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(side_effect=lambda t: t)

        with (
            patch("src.routers.users.TenantRepository", return_value=mock_repo),
            patch("src.routers.users.keycloak_service") as mock_kc,
            patch("src.routers.users.kafka_service") as mock_kafka,
        ):
            # All KC calls fail
            mock_kc.setup_tenant_group = AsyncMock(side_effect=RuntimeError("Keycloak unreachable"))
            mock_kc.add_user_to_tenant = AsyncMock(side_effect=RuntimeError("Keycloak unreachable"))
            mock_kc.assign_role = AsyncMock(side_effect=RuntimeError("Keycloak unreachable"))
            mock_kafka.emit_audit_event = AsyncMock()

            with TestClient(app_with_no_tenant_user) as client:
                response = client.post("/v1/me/tenant")

        # Tenant still created despite KC failures
        assert response.status_code == 201
        data = response.json()
        assert data["created"] is True

    def test_provision_user_with_tenant_returns_it(self, app_with_tenant_admin, mock_db_session):
        """User who already has tenant_id gets their tenant back without side effects."""
        existing_tenant = _make_tenant("acme", "ACME Corporation", personal=False)

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=existing_tenant)

        with (
            patch("src.routers.users.TenantRepository", return_value=mock_repo),
            patch("src.routers.users.keycloak_service") as mock_kc,
            patch("src.routers.users.kafka_service") as mock_kafka,
        ):
            mock_kc.setup_tenant_group = AsyncMock()
            mock_kc.add_user_to_tenant = AsyncMock()
            mock_kc.assign_role = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.post("/v1/me/tenant")

        assert response.status_code == 201
        data = response.json()
        assert data["tenant_id"] == "acme"
        assert data["created"] is False

        # No KC calls should have been made
        mock_kc.setup_tenant_group.assert_not_called()
        mock_kc.add_user_to_tenant.assert_not_called()
        mock_kc.assign_role.assert_not_called()
        mock_kafka.emit_audit_event.assert_not_called()
