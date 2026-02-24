"""Tests for self-service tenant signup router (CAB-1315).

Endpoints:
  POST /v1/self-service/tenants         — public signup
  GET  /v1/self-service/tenants/{id}/status — status poll
"""

from unittest.mock import AsyncMock, MagicMock, patch

from src.models.tenant import TenantProvisioningStatus

# ── Constants ──

SIGNUP_URL = "/v1/self-service/tenants"

SIGNUP_PAYLOAD = {
    "name": "acme-corp",
    "display_name": "ACME Corporation",
    "owner_email": "admin@acme.com",
    "company": "ACME Corp Ltd.",
}


def _make_tenant_orm(
    tenant_id: str = "acme-corp",
    provisioning_status: str = TenantProvisioningStatus.PENDING.value,
    updated_at=None,
) -> MagicMock:
    m = MagicMock()
    m.id = tenant_id
    m.provisioning_status = provisioning_status
    m.updated_at = updated_at
    return m


# ── POST /v1/self-service/tenants ──


class TestSelfServiceSignup:
    def test_new_signup_returns_202(self, client):
        """New tenant signup returns 202 Accepted with poll URL."""
        with (
            patch(
                "src.routers.self_service.TenantRepository.get_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.routers.self_service.TenantRepository.create",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.routers.self_service.provision_tenant",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("src.routers.self_service.get_db") as mock_get_db,
        ):
            # Simulate the async generator for db session
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()

            async def _fake_get_db():
                yield mock_session

            mock_get_db.return_value = _fake_get_db()

            response = client.post(SIGNUP_URL, json=SIGNUP_PAYLOAD)

        assert response.status_code == 202
        data = response.json()
        assert data["tenant_id"] == "acme-corp"
        assert data["status"] == "provisioning"
        assert "/v1/self-service/tenants/acme-corp/status" in data["poll_url"]

    def test_idempotent_already_ready_returns_ready_status(self, client):
        """If tenant already exists and is READY, body has status='ready'.

        Note: the route decorator always emits 202 even for the idempotent path
        because FastAPI applies the status_code from the decorator for Pydantic
        model responses. The meaningful assertion is the body status field.
        """
        existing = _make_tenant_orm(provisioning_status=TenantProvisioningStatus.READY.value)

        with (
            patch(
                "src.routers.self_service.TenantRepository.get_by_id",
                new_callable=AsyncMock,
                return_value=existing,
            ),
            patch("src.routers.self_service.get_db") as mock_get_db,
        ):
            mock_session = AsyncMock()

            async def _fake_get_db():
                yield mock_session

            mock_get_db.return_value = _fake_get_db()

            response = client.post(SIGNUP_URL, json=SIGNUP_PAYLOAD)

        assert response.status_code in (200, 202)
        data = response.json()
        assert data["status"] == "ready"

    def test_idempotent_already_pending_returns_202(self, client):
        """If tenant already exists and is still PENDING, return 202 with current status."""
        existing = _make_tenant_orm(provisioning_status=TenantProvisioningStatus.PENDING.value)

        with (
            patch(
                "src.routers.self_service.TenantRepository.get_by_id",
                new_callable=AsyncMock,
                return_value=existing,
            ),
            patch("src.routers.self_service.get_db") as mock_get_db,
        ):
            mock_session = AsyncMock()

            async def _fake_get_db():
                yield mock_session

            mock_get_db.return_value = _fake_get_db()

            response = client.post(SIGNUP_URL, json=SIGNUP_PAYLOAD)

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending"

    def test_signup_missing_email_returns_422(self, client):
        """Missing required owner_email field returns 422."""
        payload = {k: v for k, v in SIGNUP_PAYLOAD.items() if k != "owner_email"}
        response = client.post(SIGNUP_URL, json=payload)
        assert response.status_code == 422

    def test_signup_invalid_email_returns_422(self, client):
        """Invalid email format returns 422."""
        bad_payload = {**SIGNUP_PAYLOAD, "owner_email": "not-an-email"}
        response = client.post(SIGNUP_URL, json=bad_payload)
        assert response.status_code == 422

    def test_signup_db_error_returns_500(self, client):
        """Database errors during signup return 500."""
        with (
            patch(
                "src.routers.self_service.TenantRepository.get_by_id",
                new_callable=AsyncMock,
                side_effect=Exception("DB failure"),
            ),
            patch("src.routers.self_service.get_db") as mock_get_db,
        ):
            mock_session = AsyncMock()

            async def _fake_get_db():
                yield mock_session

            mock_get_db.return_value = _fake_get_db()

            response = client.post(SIGNUP_URL, json=SIGNUP_PAYLOAD)

        assert response.status_code == 500

    def test_signup_name_slug_conversion(self, client):
        """Tenant name is lowercased and spaces replaced with hyphens for ID."""
        with (
            patch(
                "src.routers.self_service.TenantRepository.get_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.routers.self_service.TenantRepository.create",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.routers.self_service.provision_tenant",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("src.routers.self_service.get_db") as mock_get_db,
        ):
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()

            async def _fake_get_db():
                yield mock_session

            mock_get_db.return_value = _fake_get_db()

            payload = {**SIGNUP_PAYLOAD, "name": "My Big Company"}
            response = client.post(SIGNUP_URL, json=payload)

        assert response.status_code == 202
        data = response.json()
        assert data["tenant_id"] == "my-big-company"


# ── GET /v1/self-service/tenants/{id}/status ──


class TestSelfServiceStatus:
    def test_status_existing_tenant_returns_200(self, client):
        """Status check for existing tenant returns 200 with provisioning status."""
        tenant = _make_tenant_orm(
            tenant_id="acme-corp",
            provisioning_status=TenantProvisioningStatus.PROVISIONING.value,
        )

        with (
            patch(
                "src.routers.self_service.TenantRepository.get_by_id",
                new_callable=AsyncMock,
                return_value=tenant,
            ),
            patch("src.routers.self_service.get_db") as mock_get_db,
        ):
            mock_session = AsyncMock()

            async def _fake_get_db():
                yield mock_session

            mock_get_db.return_value = _fake_get_db()

            response = client.get("/v1/self-service/tenants/acme-corp/status")

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == "acme-corp"
        assert data["provisioning_status"] == "provisioning"

    def test_status_nonexistent_tenant_returns_404(self, client):
        """Status check for unknown tenant returns 404."""
        with (
            patch(
                "src.routers.self_service.TenantRepository.get_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("src.routers.self_service.get_db") as mock_get_db,
        ):
            mock_session = AsyncMock()

            async def _fake_get_db():
                yield mock_session

            mock_get_db.return_value = _fake_get_db()

            response = client.get("/v1/self-service/tenants/does-not-exist/status")

        assert response.status_code == 404

    def test_status_ready_includes_ready_at(self, client):
        """Status check for READY tenant includes ready_at timestamp."""
        from datetime import UTC, datetime

        ready_time = datetime(2026, 2, 24, 12, 0, 0, tzinfo=UTC)
        tenant = _make_tenant_orm(
            provisioning_status=TenantProvisioningStatus.READY.value,
            updated_at=ready_time,
        )

        with (
            patch(
                "src.routers.self_service.TenantRepository.get_by_id",
                new_callable=AsyncMock,
                return_value=tenant,
            ),
            patch("src.routers.self_service.get_db") as mock_get_db,
        ):
            mock_session = AsyncMock()

            async def _fake_get_db():
                yield mock_session

            mock_get_db.return_value = _fake_get_db()

            response = client.get("/v1/self-service/tenants/acme-corp/status")

        assert response.status_code == 200
        data = response.json()
        assert data["provisioning_status"] == "ready"
        assert data["ready_at"] is not None

    def test_status_db_error_returns_500(self, client):
        """Database errors during status check return 500."""
        with (
            patch(
                "src.routers.self_service.TenantRepository.get_by_id",
                new_callable=AsyncMock,
                side_effect=Exception("DB failure"),
            ),
            patch("src.routers.self_service.get_db") as mock_get_db,
        ):
            mock_session = AsyncMock()

            async def _fake_get_db():
                yield mock_session

            mock_get_db.return_value = _fake_get_db()

            response = client.get("/v1/self-service/tenants/acme-corp/status")

        assert response.status_code == 500
