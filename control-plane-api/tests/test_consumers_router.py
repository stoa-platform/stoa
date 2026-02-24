"""Tests for Consumers Router — CAB-1436

Covers: /v1/consumers CRUD, status management, credentials, token exchange,
        expiring certificates, bulk revoke, and quota endpoints.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.models.consumer import CertificateStatus, ConsumerStatus

REPO_PATH = "src.routers.consumers.ConsumerRepository"
QUOTA_REPO_PATH = "src.routers.consumers.QuotaUsageRepository"
KC_PATH = "src.routers.consumers.keycloak_service"


def _mock_consumer(**overrides):
    """Build a MagicMock that mimics a Consumer ORM object."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "external_id": "ext-001",
        "name": "Test Corp",
        "email": "test@example.com",
        "company": "Test Corp",
        "description": None,
        "tenant_id": "acme",
        "status": ConsumerStatus.ACTIVE,
        "keycloak_client_id": "kc-client-1",
        "keycloak_user_id": None,
        "consumer_metadata": None,
        "certificate_fingerprint": None,
        "certificate_status": None,
        "certificate_fingerprint_previous": None,
        "certificate_subject_dn": None,
        "certificate_issuer_dn": None,
        "certificate_serial": None,
        "certificate_not_before": None,
        "certificate_not_after": None,
        "certificate_pem": None,
        "previous_cert_expires_at": None,
        "last_rotated_at": None,
        "rotation_count": 0,
        "created_by": "admin",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _mock_consumer_response(**overrides):
    """Build a MagicMock that mimics a ConsumerResponse Pydantic object."""
    from src.schemas.consumer import ConsumerStatusEnum

    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "external_id": "ext-001",
        "name": "Test Corp",
        "email": "test@example.com",
        "company": "Test Corp",
        "description": None,
        "tenant_id": "acme",
        "keycloak_user_id": None,
        "keycloak_client_id": "kc-client-1",
        "status": ConsumerStatusEnum.ACTIVE,
        "consumer_metadata": None,
        "certificate_fingerprint": None,
        "certificate_status": None,
        "certificate_subject_dn": None,
        "certificate_not_before": None,
        "certificate_not_after": None,
        "last_rotated_at": None,
        "rotation_count": 0,
        "created_by": "admin",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


# ============== Create Consumer ==============


class TestCreateConsumer:
    """POST /v1/consumers/{tenant_id}"""

    def test_create_success(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer()
        consumer.keycloak_client_id = "kc-client-1"

        mock_repo = MagicMock()
        mock_repo.get_by_external_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=consumer)
        mock_repo.update = AsyncMock(return_value=consumer)

        mock_kc = MagicMock()
        mock_kc.create_consumer_client = AsyncMock(return_value={"client_id": "kc-client-1"})

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch(KC_PATH, mock_kc),
            patch("src.routers.consumers.ConsumerResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_consumer_response()
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(
                    "/v1/consumers/acme",
                    json={
                        "external_id": "ext-001",
                        "name": "Test Corp",
                        "email": "test@example.com",
                    },
                )

        assert resp.status_code == 201

    def test_create_409_duplicate_external_id(self, app_with_tenant_admin, mock_db_session):
        existing = _mock_consumer()
        mock_repo = MagicMock()
        mock_repo.get_by_external_id = AsyncMock(return_value=existing)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/consumers/acme",
                json={"external_id": "ext-001", "name": "Test Corp", "email": "test@example.com"},
            )

        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_create_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.post(
                "/v1/consumers/acme",
                json={"external_id": "ext-001", "name": "Test Corp", "email": "test@example.com"},
            )

        assert resp.status_code == 403

    def test_create_keycloak_runtime_failure_returns_503(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer()
        mock_repo = MagicMock()
        mock_repo.get_by_external_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=consumer)

        mock_kc = MagicMock()
        mock_kc.create_consumer_client = AsyncMock(side_effect=RuntimeError("KC down"))

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch(KC_PATH, mock_kc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post(
                "/v1/consumers/acme",
                json={"external_id": "ext-001", "name": "Test Corp", "email": "test@example.com"},
            )

        assert resp.status_code == 503

    def test_create_cpi_admin_can_create_any_tenant(self, app_with_cpi_admin, mock_db_session):
        consumer = _mock_consumer(tenant_id="other-tenant")
        mock_repo = MagicMock()
        mock_repo.get_by_external_id = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=consumer)
        mock_repo.update = AsyncMock(return_value=consumer)

        mock_kc = MagicMock()
        mock_kc.create_consumer_client = AsyncMock(return_value={"client_id": "kc-client-1"})

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch(KC_PATH, mock_kc),
            patch("src.routers.consumers.ConsumerResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_consumer_response(tenant_id="other-tenant")
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post(
                    "/v1/consumers/other-tenant",
                    json={"external_id": "ext-001", "name": "Test Corp", "email": "test@example.com"},
                )

        assert resp.status_code == 201


# ============== List Consumers ==============


class TestListConsumers:
    """GET /v1/consumers/{tenant_id}"""

    def test_list_success(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer()
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([consumer], 1))

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch("src.routers.consumers.ConsumerResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_consumer_response()
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/consumers/acme")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_empty(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/consumers/acme")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_with_filters(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/consumers/acme?status=active&search=corp&page=2&page_size=10")

        assert resp.status_code == 200
        mock_repo.list_by_tenant.assert_called_once()

    def test_list_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get("/v1/consumers/acme")

        assert resp.status_code == 403


# ============== Get Consumer ==============


class TestGetConsumer:
    """GET /v1/consumers/{tenant_id}/{consumer_id}"""

    def test_get_success(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch("src.routers.consumers.ConsumerResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_consumer_response()
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get(f"/v1/consumers/acme/{consumer.id}")

        assert resp.status_code == 200

    def test_get_404_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/consumers/acme/{uuid4()}")

        assert resp.status_code == 404

    def test_get_404_wrong_tenant(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(tenant_id="other-tenant")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/consumers/acme/{consumer.id}")

        assert resp.status_code == 404

    def test_get_403_wrong_user_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get(f"/v1/consumers/acme/{uuid4()}")

        assert resp.status_code == 403


# ============== Update Consumer ==============


class TestUpdateConsumer:
    """PUT /v1/consumers/{tenant_id}/{consumer_id}"""

    def test_update_success(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer()
        updated = _mock_consumer(name="Updated Corp")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        mock_repo.update = AsyncMock(return_value=updated)

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch("src.routers.consumers.ConsumerResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_consumer_response(name="Updated Corp")
            with TestClient(app_with_tenant_admin) as client:
                resp = client.put(
                    f"/v1/consumers/acme/{consumer.id}",
                    json={"name": "Updated Corp"},
                )

        assert resp.status_code == 200

    def test_update_404(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.put(f"/v1/consumers/acme/{uuid4()}", json={"name": "X"})

        assert resp.status_code == 404


# ============== Delete Consumer ==============


class TestDeleteConsumer:
    """DELETE /v1/consumers/{tenant_id}/{consumer_id}"""

    def test_delete_success(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        mock_repo.delete = AsyncMock()

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/consumers/acme/{consumer.id}")

        assert resp.status_code == 204

    def test_delete_404(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/consumers/acme/{uuid4()}")

        assert resp.status_code == 404


# ============== Suspend Consumer ==============


class TestSuspendConsumer:
    """POST /v1/consumers/{tenant_id}/{consumer_id}/suspend"""

    def test_suspend_success(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.ACTIVE)
        suspended = _mock_consumer(status=ConsumerStatus.SUSPENDED)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        mock_repo.update_status = AsyncMock(return_value=suspended)

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch("src.routers.consumers.ConsumerResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_consumer_response()
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/consumers/acme/{consumer.id}/suspend")

        assert resp.status_code == 200

    def test_suspend_400_already_suspended(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.SUSPENDED)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/consumers/acme/{consumer.id}/suspend")

        assert resp.status_code == 400

    def test_suspend_404(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/consumers/acme/{uuid4()}/suspend")

        assert resp.status_code == 404


# ============== Activate Consumer ==============


class TestActivateConsumer:
    """POST /v1/consumers/{tenant_id}/{consumer_id}/activate"""

    def test_activate_success(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.SUSPENDED, keycloak_client_id="kc-client-1")
        activated = _mock_consumer(status=ConsumerStatus.ACTIVE)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        mock_repo.update_status = AsyncMock(return_value=activated)

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch("src.routers.consumers.ConsumerResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_consumer_response(status="active")
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/consumers/acme/{consumer.id}/activate")

        assert resp.status_code == 200

    def test_activate_400_already_active(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.ACTIVE)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/consumers/acme/{consumer.id}/activate")

        assert resp.status_code == 400


# ============== Block Consumer ==============


class TestBlockConsumer:
    """POST /v1/consumers/{tenant_id}/{consumer_id}/block"""

    def test_block_success(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.ACTIVE)
        blocked = _mock_consumer(status=ConsumerStatus.BLOCKED)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        mock_repo.update_status = AsyncMock(return_value=blocked)

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch("src.routers.consumers.ConsumerResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_consumer_response()
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/consumers/acme/{consumer.id}/block")

        assert resp.status_code == 200

    def test_block_400_already_blocked(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.BLOCKED)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/consumers/acme/{consumer.id}/block")

        assert resp.status_code == 400


# ============== Get Credentials ==============


class TestGetCredentials:
    """GET /v1/consumers/{tenant_id}/{consumer_id}/credentials"""

    def test_get_credentials_success(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.ACTIVE, keycloak_client_id="kc-client-1")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        mock_kc = MagicMock()
        mock_kc.get_client = AsyncMock(return_value={"id": "kc-uuid-1", "clientId": "kc-client-1"})
        mock_kc._admin = MagicMock()
        mock_kc._admin.generate_client_secrets.return_value = {"value": "super-secret"}

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch(KC_PATH, mock_kc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/consumers/acme/{consumer.id}/credentials")

        assert resp.status_code == 200
        data = resp.json()
        assert data["client_id"] == "kc-client-1"
        assert data["client_secret"] == "super-secret"

    def test_get_credentials_400_inactive_consumer(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.SUSPENDED)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/consumers/acme/{consumer.id}/credentials")

        assert resp.status_code == 400

    def test_get_credentials_404_no_kc_client(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.ACTIVE, keycloak_client_id=None)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/consumers/acme/{consumer.id}/credentials")

        assert resp.status_code == 404

    def test_get_credentials_503_keycloak_runtime_error(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.ACTIVE, keycloak_client_id="kc-client-1")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        mock_kc = MagicMock()
        mock_kc.get_client = AsyncMock(side_effect=RuntimeError("KC unavailable"))

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch(KC_PATH, mock_kc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/consumers/acme/{consumer.id}/credentials")

        assert resp.status_code == 503


# ============== Token Exchange ==============


class TestTokenExchange:
    """POST /v1/consumers/{tenant_id}/{consumer_id}/token-exchange"""

    def test_token_exchange_success(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.ACTIVE, keycloak_client_id="kc-client-1")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        mock_kc = MagicMock()
        mock_kc.get_client = AsyncMock(return_value={"id": "kc-uuid-1"})
        mock_kc._admin = MagicMock()
        mock_kc._admin.get_client_secrets.return_value = {"value": "secret"}
        mock_kc.exchange_token = AsyncMock(
            return_value={
                "access_token": "new-token",
                "token_type": "Bearer",
                "expires_in": 300,
            }
        )

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch(KC_PATH, mock_kc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post(
                f"/v1/consumers/acme/{consumer.id}/token-exchange",
                json={"subject_token": "old-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "new-token"

    def test_token_exchange_400_inactive_consumer(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(status=ConsumerStatus.SUSPENDED)
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                f"/v1/consumers/acme/{consumer.id}/token-exchange",
                json={"subject_token": "old-token"},
            )

        assert resp.status_code == 400

    def test_token_exchange_404_consumer_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                f"/v1/consumers/acme/{uuid4()}/token-exchange",
                json={"subject_token": "old-token"},
            )

        assert resp.status_code == 404


# ============== List Expiring Certificates ==============


class TestListExpiringCertificates:
    """GET /v1/consumers/{tenant_id}/certificates/expiring"""

    def test_list_expiring_success(self, app_with_tenant_admin, mock_db_session):
        from datetime import timedelta

        consumer = _mock_consumer(
            certificate_fingerprint="fp-abc",
            certificate_not_after=datetime.now(UTC) + timedelta(days=10),
            certificate_status=CertificateStatus.ACTIVE,
        )
        mock_repo = MagicMock()
        mock_repo.expire_overdue_certificates = AsyncMock(return_value=0)
        mock_repo.list_expiring = AsyncMock(return_value=[consumer])

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/consumers/acme/certificates/expiring")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_list_expiring_empty(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.expire_overdue_certificates = AsyncMock(return_value=0)
        mock_repo.list_expiring = AsyncMock(return_value=[])

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/consumers/acme/certificates/expiring?days=7")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_expiring_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get("/v1/consumers/acme/certificates/expiring")

        assert resp.status_code == 403


# ============== Bulk Revoke Certificates ==============


class TestBulkRevokeCertificates:
    """POST /v1/consumers/{tenant_id}/certificates/bulk-revoke"""

    def test_bulk_revoke_success(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer(
            certificate_fingerprint="fp-abc",
            certificate_status=CertificateStatus.ACTIVE,
        )
        consumer.keycloak_client_id = None
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        mock_repo.update = AsyncMock(return_value=consumer)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/consumers/acme/certificates/bulk-revoke",
                json={"consumer_ids": [str(consumer.id)]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] == 1
        assert data["failed"] == 0

    def test_bulk_revoke_consumer_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        missing_id = str(uuid4())
        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/consumers/acme/certificates/bulk-revoke",
                json={"consumer_ids": [missing_id]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1

    def test_bulk_revoke_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.post(
                "/v1/consumers/acme/certificates/bulk-revoke",
                json={"consumer_ids": [str(uuid4())]},
            )

        assert resp.status_code == 403


# ============== Quota Status ==============


class TestGetConsumerQuota:
    """GET /v1/consumers/{tenant_id}/{consumer_id}/quota"""

    def test_quota_success_no_plan(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        # db.execute returns mock with first() returning None (no subscription)
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        mock_quota_repo = MagicMock()
        mock_quota_repo.get_current = AsyncMock(return_value=None)

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch(QUOTA_REPO_PATH, return_value=mock_quota_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/consumers/acme/{consumer.id}/quota")

        assert resp.status_code == 200
        data = resp.json()
        assert data["consumer_id"] == str(consumer.id)
        assert data["usage"]["daily"] == 0
        assert data["usage"]["monthly"] == 0

    def test_quota_404_consumer_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/consumers/acme/{uuid4()}/quota")

        assert resp.status_code == 404

    def test_quota_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get(f"/v1/consumers/acme/{uuid4()}/quota")

        assert resp.status_code == 403

    def test_quota_success_with_usage(self, app_with_tenant_admin, mock_db_session):
        consumer = _mock_consumer()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)

        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        mock_usage = MagicMock()
        mock_usage.request_count_daily = 150
        mock_usage.request_count_monthly = 4500

        mock_quota_repo = MagicMock()
        mock_quota_repo.get_current = AsyncMock(return_value=mock_usage)

        with (
            patch(REPO_PATH, return_value=mock_repo),
            patch(QUOTA_REPO_PATH, return_value=mock_quota_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/consumers/acme/{consumer.id}/quota")

        assert resp.status_code == 200
        data = resp.json()
        assert data["usage"]["daily"] == 150
        assert data["usage"]["monthly"] == 4500
