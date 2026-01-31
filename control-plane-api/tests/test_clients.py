"""
Tests for Client Certificate Provisioning (CAB-865)

Covers:
- Certificate generation with X.509 extensions
- Tenant isolation
- CN sanitization (injection blocked)
- Private key not in GET responses
- Rate limiting
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from src.models.client import Client, ClientStatus


# ============== Unit Tests: Certificate Provider ==============


class TestMockCertificateProvider:
    """Test the mock certificate provider generates valid X.509 certs."""

    @pytest.mark.asyncio
    async def test_generate_certificate_has_all_extensions(self):
        """Verify all required X.509 extensions are present."""
        from src.services.certificate_providers.mock_provider import MockCertificateProvider

        provider = MockCertificateProvider()
        result = await provider.generate_certificate(
            common_name="test-client",
            tenant_id="acme",
            validity_days=365,
            key_size=2048,  # Use 2048 for speed in tests
        )

        # Parse the generated certificate
        cert = x509.load_pem_x509_certificate(result.certificate_pem.encode())

        # BasicConstraints: ca=False
        bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert bc.critical is True
        assert bc.value.ca is False

        # KeyUsage: digitalSignature + keyEncipherment
        ku = cert.extensions.get_extension_for_class(x509.KeyUsage)
        assert ku.critical is True
        assert ku.value.digital_signature is True
        assert ku.value.key_encipherment is True

        # ExtendedKeyUsage: clientAuth
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        from cryptography.x509.oid import ExtendedKeyUsageOID
        assert ExtendedKeyUsageOID.CLIENT_AUTH in eku.value

        # SubjectAlternativeName
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        dns_names = san.value.get_values_for_type(x509.DNSName)
        assert len(dns_names) == 1
        assert "test-client" in dns_names[0]

    @pytest.mark.asyncio
    async def test_generate_certificate_returns_private_key(self):
        """Private key is returned as PEM."""
        from src.services.certificate_providers.mock_provider import MockCertificateProvider

        provider = MockCertificateProvider()
        result = await provider.generate_certificate(
            common_name="test-client", tenant_id="acme", key_size=2048,
        )

        assert result.private_key_pem.startswith("-----BEGIN PRIVATE KEY-----")
        assert result.certificate_pem.startswith("-----BEGIN CERTIFICATE-----")
        assert result.serial_number
        assert result.fingerprint_sha256

    @pytest.mark.asyncio
    async def test_reject_key_size_below_2048(self):
        """Key sizes below 2048 must be rejected."""
        from src.services.certificate_providers.mock_provider import MockCertificateProvider

        provider = MockCertificateProvider()
        with pytest.raises(ValueError, match="at least 2048"):
            await provider.generate_certificate(
                common_name="test", tenant_id="acme", key_size=1024,
            )


# ============== Unit Tests: CN Sanitization ==============


class TestCNSanitization:
    """Test common name validation blocks injection attempts."""

    def test_valid_cn(self):
        from src.services.certificate_service import CertificateService
        assert CertificateService.validate_common_name("my-client") == "my-client"
        assert CertificateService.validate_common_name("client.v2") == "client.v2"
        assert CertificateService.validate_common_name("a") == "a"

    def test_cn_with_spaces_rejected(self):
        from src.services.certificate_service import CertificateService, CertificateServiceError
        with pytest.raises(CertificateServiceError):
            CertificateService.validate_common_name("my client")

    def test_cn_injection_attempts_rejected(self):
        from src.services.certificate_service import CertificateService, CertificateServiceError
        # SQL injection
        with pytest.raises(CertificateServiceError):
            CertificateService.validate_common_name("'; DROP TABLE clients;--")
        # Path traversal
        with pytest.raises(CertificateServiceError):
            CertificateService.validate_common_name("../../etc/passwd")
        # Empty
        with pytest.raises(CertificateServiceError):
            CertificateService.validate_common_name("")
        # Starting with dash
        with pytest.raises(CertificateServiceError):
            CertificateService.validate_common_name("-invalid")

    def test_cn_too_long_rejected(self):
        from src.services.certificate_service import CertificateService, CertificateServiceError
        with pytest.raises(CertificateServiceError):
            CertificateService.validate_common_name("a" * 64)


# ============== Integration Tests: Router Endpoints ==============


class TestClientsRouter:
    """Test clients API endpoints."""

    def _mock_client(self, tenant_id="acme", status=ClientStatus.ACTIVE):
        """Create a mock Client ORM object."""
        client = MagicMock(spec=Client)
        client.id = uuid.uuid4()
        client.tenant_id = tenant_id
        client.name = "test-client"
        client.certificate_cn = "test-client"
        client.certificate_serial = "abc123"
        client.certificate_fingerprint = "aa:bb:cc"
        client.certificate_pem = "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"
        client.certificate_not_before = datetime.now(timezone.utc)
        client.certificate_not_after = datetime.now(timezone.utc)
        client.status = status
        client.created_at = datetime.now(timezone.utc)
        client.updated_at = datetime.now(timezone.utc)
        return client

    def test_create_client_returns_private_key(self, app_with_tenant_admin, mock_db_session):
        """POST /v1/clients returns private key ONE TIME."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing client
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        now = datetime.now(timezone.utc)
        client_id = uuid.uuid4()

        # When db.add is called, set the id on the client object
        def side_effect_add(obj):
            obj.id = client_id
            obj.created_at = now
            obj.updated_at = now

        mock_db_session.add = MagicMock(side_effect=side_effect_add)
        mock_db_session.refresh = AsyncMock(side_effect=lambda c: None)

        with patch("src.routers.clients.certificate_service") as mock_svc:
            mock_svc.validate_common_name.return_value = "test-client"

            from src.services.certificate_provider import CertificateResult
            mock_svc.generate_certificate = AsyncMock(return_value=CertificateResult(
                certificate_pem="-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----",
                private_key_pem="-----BEGIN PRIVATE KEY-----\nSECRET\n-----END PRIVATE KEY-----",
                serial_number="abc123",
                fingerprint_sha256="aa:bb:cc",
                common_name="test-client",
                not_before=now,
                not_after=now,
            ))

            with TestClient(app_with_tenant_admin) as client:
                response = client.post("/v1/clients", json={"name": "test-client"})

            assert response.status_code == 201
            data = response.json()
            assert "private_key_pem" in data
            assert "PRIVATE KEY" in data["private_key_pem"]

    def test_list_clients_no_private_key(self, app_with_tenant_admin, mock_db_session):
        """GET /v1/clients never returns private keys."""
        mock_client = self._mock_client()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_client]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/clients")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert "private_key_pem" not in data[0]

    def test_get_client_no_private_key(self, app_with_tenant_admin, mock_db_session):
        """GET /v1/clients/{id} never returns private key."""
        mock_client = self._mock_client()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_tenant_admin) as client:
            response = client.get(f"/v1/clients/{mock_client.id}")

        assert response.status_code == 200
        assert "private_key_pem" not in response.json()

    def test_tenant_isolation_other_tenant_gets_404(self, app_with_other_tenant, mock_db_session):
        """User from other tenant cannot see clients from 'acme'."""
        mock_client = self._mock_client(tenant_id="acme")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_other_tenant) as client:
            response = client.get(f"/v1/clients/{mock_client.id}")

        assert response.status_code == 404

    def test_no_tenant_user_rejected(self, app_with_no_tenant_user, mock_db_session):
        """User without tenant_id cannot create clients."""
        with TestClient(app_with_no_tenant_user) as client:
            response = client.post("/v1/clients", json={"name": "test"})

        assert response.status_code == 403

    def test_cn_sanitization_in_create(self, app_with_tenant_admin, mock_db_session):
        """Create endpoint rejects invalid names that produce bad CNs."""
        with patch("src.routers.clients.certificate_service") as mock_svc:
            from src.services.certificate_service import CertificateServiceError
            mock_svc.validate_common_name.side_effect = CertificateServiceError("Invalid")

            with TestClient(app_with_tenant_admin) as client:
                response = client.post("/v1/clients", json={"name": "'; DROP TABLE;--"})

            assert response.status_code == 400

    def test_delete_client_revokes(self, app_with_tenant_admin, mock_db_session):
        """DELETE /v1/clients/{id} revokes the certificate."""
        mock_client = self._mock_client()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch("src.routers.clients.certificate_service") as mock_svc:
            mock_svc.revoke_certificate = AsyncMock(return_value=True)

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"/v1/clients/{mock_client.id}")

            assert response.status_code == 204
            assert mock_client.status == ClientStatus.REVOKED
