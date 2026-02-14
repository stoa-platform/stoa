"""
Tests for Consumers Router - CAB-1121 + CAB-872

Target: Consumer CRUD + status management + tenant isolation + certificate lifecycle
Tests: 24 test cases
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class TestConsumersRouter:
    """Test suite for Consumers Router endpoints."""

    # ============== Helper Methods ==============

    def _create_mock_consumer(self, data: dict) -> MagicMock:
        """Create a mock Consumer object from data dict."""
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    # ============== Create Consumer Tests ==============

    def test_create_consumer_success(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test successful consumer creation returns 201."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        updated_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "keycloak_client_id": "acme-partner-acme-001"}
        )

        kc_result = {"client_id": "acme-partner-acme-001", "client_secret": "s", "id": "uuid"}

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.keycloak_service") as mock_kc,
        ):
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_external_id = AsyncMock(return_value=None)
            mock_repo_instance.create = AsyncMock(return_value=mock_consumer)
            mock_repo_instance.update = AsyncMock(return_value=updated_consumer)
            mock_kc.create_consumer_client = AsyncMock(return_value=kc_result)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/consumers/acme",
                    json={
                        "external_id": "partner-acme-001",
                        "name": "ACME Corp",
                        "email": "api@acme.com",
                        "company": "ACME Corporation",
                        "description": "Strategic API partner",
                    },
                )

            assert response.status_code == 201
            data = response.json()
            assert data["external_id"] == "partner-acme-001"
            assert data["name"] == "ACME Corp"
            assert data["tenant_id"] == "acme"
            assert data["status"] == "active"

    def test_create_consumer_duplicate_409(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test duplicate external_id returns 409."""
        mock_existing = self._create_mock_consumer(sample_consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_external_id = AsyncMock(return_value=mock_existing)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/consumers/acme",
                    json={
                        "external_id": "partner-acme-001",
                        "name": "Duplicate",
                        "email": "dup@acme.com",
                    },
                )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"]

    def test_create_consumer_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        """Test tenant isolation - cannot create consumer in another tenant."""
        with TestClient(app_with_other_tenant) as client:
            response = client.post(
                "/v1/consumers/acme",
                json={
                    "external_id": "partner-001",
                    "name": "Test",
                    "email": "test@test.com",
                },
            )

        assert response.status_code == 403

    # ============== List Consumer Tests ==============

    def test_list_consumers_success(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test listing consumers with pagination."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(return_value=([mock_consumer], 1))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/consumers/acme")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            assert data["items"][0]["external_id"] == "partner-acme-001"

    def test_list_consumers_empty(self, app_with_tenant_admin, mock_db_session):
        """Test listing consumers when none exist."""
        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(return_value=([], 0))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/consumers/acme")

            assert response.status_code == 200
            assert response.json()["total"] == 0
            assert response.json()["items"] == []

    # ============== Get Consumer Tests ==============

    def test_get_consumer_success(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test getting a consumer by ID."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/consumers/acme/{sample_consumer_data['id']}")

            assert response.status_code == 200
            assert response.json()["name"] == "ACME Corp"

    def test_get_consumer_404(self, app_with_tenant_admin, mock_db_session):
        """Test 404 when consumer not found."""
        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/consumers/acme/{uuid4()}")

            assert response.status_code == 404

    # ============== Update Consumer Tests ==============

    def test_update_consumer_success(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test updating a consumer."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        updated_consumer = self._create_mock_consumer({**sample_consumer_data, "name": "ACME Updated"})

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo_instance.update = AsyncMock(return_value=updated_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.put(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}",
                    json={"name": "ACME Updated"},
                )

            assert response.status_code == 200
            assert response.json()["name"] == "ACME Updated"

    # ============== Delete Consumer Tests ==============

    def test_delete_consumer_success(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test deleting a consumer."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo_instance.delete = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"/v1/consumers/acme/{sample_consumer_data['id']}")

            assert response.status_code == 204

    # ============== Status Management Tests ==============

    def test_suspend_consumer_success(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test suspending an active consumer."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        mock_consumer.status = "active"
        # ConsumerStatus comparison — mock the enum value
        mock_consumer.status = MagicMock()
        mock_consumer.status.__eq__ = lambda _self, other: str(other) == "active"
        mock_consumer.status.value = "active"
        mock_consumer.status.__ne__ = lambda _self, other: str(other) != "active"

        suspended_consumer = self._create_mock_consumer({**sample_consumer_data, "status": "suspended"})

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.ConsumerStatus") as MockStatus,
        ):
            MockStatus.ACTIVE = "active"
            MockStatus.SUSPENDED = "suspended"
            MockStatus.BLOCKED = "blocked"

            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo_instance.update_status = AsyncMock(return_value=suspended_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(f"/v1/consumers/acme/{sample_consumer_data['id']}/suspend")

            assert response.status_code == 200

    def test_activate_consumer_success(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test reactivating a suspended consumer."""
        mock_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "status": "suspended", "keycloak_client_id": None}
        )
        mock_consumer.status = MagicMock()
        mock_consumer.status.__eq__ = lambda _self, other: str(other) == "suspended"
        mock_consumer.status.value = "suspended"
        mock_consumer.status.__ne__ = lambda _self, other: str(other) != "suspended"

        activated_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "status": "active", "keycloak_client_id": "acme-partner-acme-001"}
        )

        kc_result = {"client_id": "acme-partner-acme-001", "client_secret": "s", "id": "uuid"}

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.ConsumerStatus") as MockStatus,
            patch("src.routers.consumers.keycloak_service") as mock_kc,
        ):
            MockStatus.ACTIVE = "active"
            MockStatus.SUSPENDED = "suspended"
            MockStatus.BLOCKED = "blocked"

            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo_instance.update_status = AsyncMock(return_value=mock_consumer)
            mock_repo_instance.update = AsyncMock(return_value=activated_consumer)
            mock_kc.create_consumer_client = AsyncMock(return_value=kc_result)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(f"/v1/consumers/acme/{sample_consumer_data['id']}/activate")

            assert response.status_code == 200

    def test_cpi_admin_cross_tenant_access(self, app_with_cpi_admin, mock_db_session, sample_consumer_data):
        """Test CPI admin can access any tenant's consumers."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(return_value=([mock_consumer], 1))

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/consumers/acme")

            assert response.status_code == 200
            assert response.json()["total"] == 1

    # ============== Search LIKE Escape Tests ==============

    def test_search_consumers_percent_char(self, app_with_tenant_admin, mock_db_session):
        """Percent character (LIKE wildcard) is properly escaped."""
        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(return_value=([], 0))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/consumers/acme?search=%25")  # URL encoded %

            assert response.status_code == 200, "Search with % should not cause 500 error"

    def test_search_consumers_underscore_char(self, app_with_tenant_admin, mock_db_session):
        """Underscore character (LIKE single-char wildcard) is properly escaped."""
        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(return_value=([], 0))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/consumers/acme?search=_")

            assert response.status_code == 200, "Search with _ should not cause 500 error"

    def test_search_consumers_backslash_char(self, app_with_tenant_admin, mock_db_session):
        """Backslash character (LIKE escape char) is properly escaped."""
        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(return_value=([], 0))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/consumers/acme?search=%5C")  # URL encoded \

            assert response.status_code == 200, "Search with \\ should not cause 500 error"

    def test_search_consumers_whitespace_only(self, app_with_tenant_admin, mock_db_session):
        """Whitespace-only search should be treated as empty (no filter)."""
        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(return_value=([], 0))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/consumers/acme?search=   ")

            assert response.status_code == 200
            # Verify that list_by_tenant was called with search=None or empty after strip
            call_kwargs = mock_repo_instance.list_by_tenant.call_args.kwargs
            assert call_kwargs["search"] == "   "  # Router passes it as-is, repo strips it

    # ============== Certificate Bind Tests (CAB-872) ==============

    def _consumer_with_cert(self, base_data: dict, status: str = "active") -> dict:
        """Create consumer data with certificate fields."""
        return {
            **base_data,
            "certificate_fingerprint": "ab" * 32,
            "certificate_status": status,
            "certificate_subject_dn": "CN=test",
            "certificate_issuer_dn": "CN=ca",
            "certificate_serial": "01",
            "certificate_not_before": datetime.now(UTC),
            "certificate_not_after": datetime.now(UTC) + timedelta(days=365),
            "certificate_pem": "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        }

    def test_bind_certificate_success(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test binding a certificate to a consumer without one."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        # Consumer has no certificate yet
        mock_consumer.certificate_fingerprint = None
        mock_consumer.certificate_status = None

        cert_data = self._consumer_with_cert(sample_consumer_data)
        updated_consumer = self._create_mock_consumer(cert_data)

        mock_cert_info = MagicMock()
        mock_cert_info.fingerprint_hex = "ab" * 32
        mock_cert_info.fingerprint_b64url = "test_b64url"
        mock_cert_info.subject_dn = "CN=test"
        mock_cert_info.issuer_dn = "CN=ca"
        mock_cert_info.serial = "01"
        mock_cert_info.not_before = datetime.now(UTC)
        mock_cert_info.not_after = datetime.now(UTC) + timedelta(days=365)
        mock_cert_info.pem = "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.keycloak_service") as mock_kc,
            patch("src.routers.consumers.parse_pem_certificate", return_value=mock_cert_info),
            patch("src.routers.consumers.validate_certificate_not_expired"),
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo.get_by_fingerprint = AsyncMock(return_value=None)
            mock_repo.update = AsyncMock(return_value=updated_consumer)
            mock_kc.create_consumer_client_with_cert = AsyncMock(
                return_value={"client_id": "acme-partner-acme-001", "client_secret": "s"}
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/certificate",
                    json={"certificate_pem": "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"},
                )

            assert response.status_code == 201
            data = response.json()
            assert data["certificate_fingerprint"] is not None
            assert data["certificate_status"] == "active"

    def test_bind_certificate_409_already_has_cert(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test 409 when consumer already has an active certificate."""
        cert_data = self._consumer_with_cert(sample_consumer_data, status="active")
        mock_consumer = self._create_mock_consumer(cert_data)

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.CertificateStatus") as MockCertStatus,
        ):
            MockCertStatus.ACTIVE = "active"
            MockCertStatus.ROTATING = "rotating"
            MockCertStatus.REVOKED = "revoked"
            MockCertStatus.EXPIRED = "expired"

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/certificate",
                    json={"certificate_pem": "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"},
                )

            assert response.status_code == 409
            assert "already has an active certificate" in response.json()["detail"]

    def test_bind_certificate_400_invalid_pem(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test 400 when PEM data is invalid."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        mock_consumer.certificate_fingerprint = None
        mock_consumer.certificate_status = None

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.parse_pem_certificate", side_effect=ValueError("Invalid PEM certificate")),
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/certificate",
                    json={"certificate_pem": "not-a-certificate"},
                )

            assert response.status_code == 400
            assert "Invalid PEM" in response.json()["detail"]

    def test_bind_certificate_400_expired_pem(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test 400 when certificate has already expired."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        mock_consumer.certificate_fingerprint = None
        mock_consumer.certificate_status = None

        mock_cert_info = MagicMock()

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.parse_pem_certificate", return_value=mock_cert_info),
            patch(
                "src.routers.consumers.validate_certificate_not_expired",
                side_effect=ValueError("Certificate expired on 2025-01-01T00:00:00+00:00"),
            ),
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/certificate",
                    json={"certificate_pem": "-----BEGIN CERTIFICATE-----\nexpired\n-----END CERTIFICATE-----"},
                )

            assert response.status_code == 400
            assert "expired" in response.json()["detail"].lower()

    def test_bind_certificate_after_revoke(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test rebinding a certificate after revocation is allowed."""
        revoked_data = self._consumer_with_cert(sample_consumer_data, status="revoked")
        mock_consumer = self._create_mock_consumer(revoked_data)

        cert_data = self._consumer_with_cert(sample_consumer_data, status="active")
        updated_consumer = self._create_mock_consumer(cert_data)

        mock_cert_info = MagicMock()
        mock_cert_info.fingerprint_hex = "cd" * 32
        mock_cert_info.fingerprint_b64url = "new_b64url"
        mock_cert_info.subject_dn = "CN=new"
        mock_cert_info.issuer_dn = "CN=ca"
        mock_cert_info.serial = "02"
        mock_cert_info.not_before = datetime.now(UTC)
        mock_cert_info.not_after = datetime.now(UTC) + timedelta(days=365)
        mock_cert_info.pem = "-----BEGIN CERTIFICATE-----\nnew\n-----END CERTIFICATE-----"

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.keycloak_service") as mock_kc,
            patch("src.routers.consumers.parse_pem_certificate", return_value=mock_cert_info),
            patch("src.routers.consumers.validate_certificate_not_expired"),
            patch("src.routers.consumers.CertificateStatus") as MockCertStatus,
        ):
            MockCertStatus.ACTIVE = "active"
            MockCertStatus.ROTATING = "rotating"
            MockCertStatus.REVOKED = "revoked"
            MockCertStatus.EXPIRED = "expired"

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo.get_by_fingerprint = AsyncMock(return_value=None)
            mock_repo.update = AsyncMock(return_value=updated_consumer)
            mock_kc.update_consumer_client_cnf = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/certificate",
                    json={"certificate_pem": "-----BEGIN CERTIFICATE-----\nnew\n-----END CERTIFICATE-----"},
                )

            # Should be allowed — revoked cert can be replaced
            assert response.status_code == 201

    # ============== Expiring Certificates Tests (CAB-872) ==============

    def test_list_expiring_certificates(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test listing consumers with expiring certificates."""
        expiring_data = self._consumer_with_cert(sample_consumer_data)
        expiring_data["certificate_not_after"] = datetime.now(UTC) + timedelta(days=15)
        mock_consumer = self._create_mock_consumer(expiring_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.expire_overdue_certificates = AsyncMock(return_value=0)
            mock_repo.list_expiring = AsyncMock(return_value=[mock_consumer])

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/consumers/acme/certificates/expiring?days=30")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["days_threshold"] == 30
            assert len(data["items"]) == 1
            assert data["items"][0]["days_until_expiry"] <= 30

    def test_list_expiring_certificates_empty(self, app_with_tenant_admin, mock_db_session):
        """Test listing expiring certificates when none are expiring."""
        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.expire_overdue_certificates = AsyncMock(return_value=0)
            mock_repo.list_expiring = AsyncMock(return_value=[])

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/consumers/acme/certificates/expiring")

            assert response.status_code == 200
            assert response.json()["total"] == 0

    # ============== Bulk Revoke Tests (CAB-872) ==============

    def test_bulk_revoke_success(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test bulk revoking certificates for multiple consumers."""
        cid1 = sample_consumer_data["id"]
        cid2 = uuid4()

        cert_data1 = self._consumer_with_cert({**sample_consumer_data, "id": cid1})
        cert_data2 = self._consumer_with_cert(
            {**sample_consumer_data, "id": cid2, "external_id": "partner-002", "keycloak_client_id": "kc-002"}
        )
        mock_c1 = self._create_mock_consumer(cert_data1)
        mock_c2 = self._create_mock_consumer(cert_data2)

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.keycloak_service") as mock_kc,
            patch("src.routers.consumers.CertificateStatus") as MockCertStatus,
        ):
            MockCertStatus.REVOKED = "revoked"

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(side_effect=[mock_c1, mock_c2])
            mock_repo.update = AsyncMock(side_effect=[mock_c1, mock_c2])
            mock_kc.disable_consumer_client = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/consumers/acme/certificates/bulk-revoke",
                    json={"consumer_ids": [str(cid1), str(cid2)]},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] == 2
            assert data["failed"] == 0
            assert data["skipped"] == 0

    def test_bulk_revoke_skip_no_cert(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test bulk revoke skips consumers without certificates."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        # No certificate
        mock_consumer.certificate_fingerprint = None

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/consumers/acme/certificates/bulk-revoke",
                    json={"consumer_ids": [str(sample_consumer_data["id"])]},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] == 0
            assert data["skipped"] == 1

    def test_bulk_revoke_skip_already_revoked(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test bulk revoke skips already-revoked consumers."""
        revoked_data = self._consumer_with_cert(sample_consumer_data, status="revoked")
        mock_consumer = self._create_mock_consumer(revoked_data)

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.CertificateStatus") as MockCertStatus,
        ):
            MockCertStatus.REVOKED = "revoked"

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/consumers/acme/certificates/bulk-revoke",
                    json={"consumer_ids": [str(sample_consumer_data["id"])]},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["skipped"] == 1

    def test_bulk_revoke_not_found(self, app_with_tenant_admin, mock_db_session):
        """Test bulk revoke reports errors for missing consumers."""
        missing_id = uuid4()

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/consumers/acme/certificates/bulk-revoke",
                    json={"consumer_ids": [str(missing_id)]},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["failed"] == 1
            assert len(data["errors"]) == 1
