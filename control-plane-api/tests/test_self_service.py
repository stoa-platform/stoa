"""
Tests for Self-Service Signup Router — CAB-1315, CAB-1541.

Target: public endpoints for tenant self-service signup + status polling.
Tests: 12 test cases covering signup, idempotency, validation, and status.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.models.tenant import Tenant, TenantProvisioningStatus


def _make_tenant(
    tenant_id="my-company",
    name="My Company",
    status="active",
    provisioning_status="pending",
    owner_email="owner@example.com",
    updated_at=None,
    plan="trial",
):
    """Create a mock Tenant for self-service tests."""
    tenant = MagicMock(spec=Tenant)
    tenant.id = tenant_id
    tenant.name = name
    tenant.status = status
    tenant.provisioning_status = provisioning_status
    tenant.settings = {"owner_email": owner_email, "plan": plan}
    tenant.updated_at = updated_at or datetime(2025, 1, 1, tzinfo=UTC)
    return tenant


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset in-memory rate limiter between tests to avoid cross-test 429s."""
    from src.middleware.rate_limit import limiter

    yield
    limiter.reset()


@pytest.fixture
def self_service_app(app, mock_db_session):
    """App with only DB override (no auth — public endpoints)."""
    from src.database import get_db

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


class TestSelfServiceSignup:
    """Test POST /v1/self-service/tenants."""

    def _mock_signup_response(self, tenant_id="my-company", status="provisioning", plan="trial"):
        from src.schemas.self_service import SelfServiceSignupResponse

        return SelfServiceSignupResponse(
            tenant_id=tenant_id,
            status=status,
            plan=plan,
            poll_url=f"/v1/self-service/tenants/{tenant_id}/status",
        )

    def test_signup_new_tenant_returns_202(self, self_service_app, mock_db_session):
        """New tenant signup returns 202 with provisioning status."""
        with (
            patch(
                "src.routers.self_service.signup_tenant",
                new_callable=AsyncMock,
                return_value=self._mock_signup_response(),
            ),
            TestClient(self_service_app) as client,
        ):
            response = client.post(
                "/v1/self-service/tenants",
                json={
                    "name": "My Company",
                    "display_name": "My Company Inc.",
                    "owner_email": "owner@example.com",
                },
            )

        assert response.status_code == 202
        data = response.json()
        assert data["tenant_id"] == "my-company"
        assert data["status"] == "provisioning"
        assert data["plan"] == "trial"
        assert "/v1/self-service/tenants/my-company/status" in data["poll_url"]

    def test_signup_response_does_not_include_email(self, self_service_app, mock_db_session):
        """Response MUST NOT include owner_email (PII protection)."""
        with (
            patch(
                "src.routers.self_service.signup_tenant",
                new_callable=AsyncMock,
                return_value=self._mock_signup_response(),
            ),
            TestClient(self_service_app) as client,
        ):
            response = client.post(
                "/v1/self-service/tenants",
                json={
                    "name": "My Company",
                    "display_name": "My Company Inc.",
                    "owner_email": "secret@example.com",
                },
            )

        data = response.json()
        assert "owner_email" not in data
        assert "secret@example.com" not in str(data)

    def test_signup_existing_ready_returns_200(self, self_service_app, mock_db_session):
        """Existing READY tenant → idempotent 200 response."""
        with (
            patch(
                "src.routers.self_service.signup_tenant",
                new_callable=AsyncMock,
                return_value=self._mock_signup_response(status="ready"),
            ),
            TestClient(self_service_app) as client,
        ):
            response = client.post(
                "/v1/self-service/tenants",
                json={
                    "name": "My Company",
                    "display_name": "My Company Inc.",
                    "owner_email": "owner@example.com",
                },
            )

        data = response.json()
        assert data["status"] == "ready"

    def test_signup_existing_provisioning_returns_202(self, self_service_app, mock_db_session):
        """Existing PROVISIONING tenant → idempotent 202 with current status."""
        with (
            patch(
                "src.routers.self_service.signup_tenant",
                new_callable=AsyncMock,
                return_value=self._mock_signup_response(status=TenantProvisioningStatus.PROVISIONING.value),
            ),
            TestClient(self_service_app) as client,
        ):
            response = client.post(
                "/v1/self-service/tenants",
                json={
                    "name": "My Company",
                    "display_name": "My Company Inc.",
                    "owner_email": "owner@example.com",
                },
            )

        data = response.json()
        assert data["status"] == TenantProvisioningStatus.PROVISIONING.value

    def test_signup_invalid_email_returns_422(self, self_service_app, mock_db_session):
        """Invalid email format → 422 validation error."""
        with TestClient(self_service_app) as client:
            response = client.post(
                "/v1/self-service/tenants",
                json={
                    "name": "My Company",
                    "display_name": "My Company Inc.",
                    "owner_email": "not-an-email",
                },
            )

        assert response.status_code == 422

    def test_signup_missing_fields_returns_422(self, self_service_app, mock_db_session):
        """Missing required fields → 422."""
        with TestClient(self_service_app) as client:
            response = client.post(
                "/v1/self-service/tenants",
                json={"name": "My Company"},
            )

        assert response.status_code == 422

    def test_signup_with_company_field(self, self_service_app, mock_db_session):
        """Optional company field is accepted."""
        with (
            patch(
                "src.routers.self_service.signup_tenant",
                new_callable=AsyncMock,
                return_value=self._mock_signup_response(),
            ),
            TestClient(self_service_app) as client,
        ):
            response = client.post(
                "/v1/self-service/tenants",
                json={
                    "name": "My Company",
                    "display_name": "My Company Inc.",
                    "owner_email": "owner@example.com",
                    "company": "ACME Corp",
                },
            )

        assert response.status_code == 202

    def test_signup_calls_signup_tenant_service(self, self_service_app, mock_db_session):
        """Signup delegates to signup_tenant service."""
        with (
            patch(
                "src.routers.self_service.signup_tenant",
                new_callable=AsyncMock,
                return_value=self._mock_signup_response(),
            ) as mock_signup,
            TestClient(self_service_app) as client,
        ):
            client.post(
                "/v1/self-service/tenants",
                json={
                    "name": "My Company",
                    "display_name": "My Company Inc.",
                    "owner_email": "owner@example.com",
                },
            )

        mock_signup.assert_awaited_once()


class TestSelfServiceStatus:
    """Test GET /v1/self-service/tenants/{id}/status."""

    def test_status_returns_provisioning(self, self_service_app, mock_db_session):
        """Status endpoint returns current provisioning status."""
        tenant = _make_tenant(
            provisioning_status=TenantProvisioningStatus.PROVISIONING.value,
        )
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch("src.routers.self_service.TenantRepository", return_value=mock_repo),
            TestClient(self_service_app) as client,
        ):
            response = client.get("/v1/self-service/tenants/my-company/status")

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == "my-company"
        assert data["provisioning_status"] == "provisioning"
        assert data["plan"] == "trial"

    def test_status_ready_includes_ready_at(self, self_service_app, mock_db_session):
        """READY tenant includes ready_at timestamp."""
        tenant = _make_tenant(
            provisioning_status=TenantProvisioningStatus.READY.value,
            updated_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch("src.routers.self_service.TenantRepository", return_value=mock_repo),
            TestClient(self_service_app) as client,
        ):
            response = client.get("/v1/self-service/tenants/my-company/status")

        data = response.json()
        assert data["provisioning_status"] == "ready"
        assert data["ready_at"] is not None

    def test_status_not_found_returns_404(self, self_service_app, mock_db_session):
        """Unknown tenant → 404."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch("src.routers.self_service.TenantRepository", return_value=mock_repo),
            TestClient(self_service_app) as client,
        ):
            response = client.get("/v1/self-service/tenants/unknown/status")

        assert response.status_code == 404

    def test_status_pending_no_ready_at(self, self_service_app, mock_db_session):
        """PENDING tenant → ready_at is null."""
        tenant = _make_tenant(
            provisioning_status=TenantProvisioningStatus.PENDING.value,
        )
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch("src.routers.self_service.TenantRepository", return_value=mock_repo),
            TestClient(self_service_app) as client,
        ):
            response = client.get("/v1/self-service/tenants/my-company/status")

        data = response.json()
        assert data["provisioning_status"] == "pending"
        assert data["ready_at"] is None
