"""
Unit tests for KeycloakCertificateSyncService - CAB-866

Tests:
- RFC 8705 x5t#S256 computation
- Idempotent sync (lookup before create)
- No fingerprint in logs
- Certificate parse error handling
"""

import pytest
from unittest.mock import MagicMock
from src.services.keycloak_cert_sync_service import (
    KeycloakCertificateSyncService,
    SyncStatus,
    CertificateParseError,
)

# Test certificate (self-signed, for testing only)
TEST_CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIDBTCCAe2gAwIBAgIUdoF+IrcUnLko2hl0cTCR3lfImKMwDQYJKoZIhvcNAQEL
BQAwEjEQMA4GA1UEAwwHc3RvYS5pbzAeFw0yNjAxMjgwOTA5NDRaFw0yNzAxMjgw
OTA5NDRaMBIxEDAOBgNVBAMMB3N0b2EuaW8wggEiMA0GCSqGSIb3DQEBAQUAA4IB
DwAwggEKAoIBAQDPLt0zDGwEjI5LB76crJX/76MGKl5P+3UgLwa12THyZ3aajN/0
/juKX5NmnF/z+Q2f6RiR0btdErzzXiadqcjMjDi/P40qQF6j1/5bd5Jhu9nVTRmK
8aZXkcEQNlWukMMQf/3WZl6uaC13CukWVRynuLLYZCwPs319qu+hzswOZkmTYisX
x6Ex89FDeehSftysdsHv7/GQIbxkfTnmf9SGulsHHm8p8VdA5yhHv+8toVXwFfvg
79sAzqWp9LlbJtru2h6/xnncH6GWjASnFZ8R7Bp7Yjpv8YXwYnU8Byf7mNvHih4p
nTtcVmFIu03aVJONBwf9ObFMIOkFIijsJAPVAgMBAAGjUzBRMB0GA1UdDgQWBBTP
+9i28H3nfej2OIKzI2te4K6yjDAfBgNVHSMEGDAWgBTP+9i28H3nfej2OIKzI2te
4K6yjDAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQBK9uRzB6Xb
l5ciMtKi1gay28pYzZV5TAQR5zLEqEXgrNbE18i+ZmBCcyCSl2T+qkyZXak8NwIU
yg04fSheiNsbaNc9wxi550NxnPmnoA5XvAJo2P2i1g70IRLl8JCF9PL85gxEkHMv
bi7GHLOo1HFEAH3SIYBgF0ID7qcnSnu7vHWXg1N0cUrX2yUSxs/l8zzrYAIXrait
QXhH9e8pGYAwTLF//zjqL9fhgiOwCAFO1z9dLYaHvNCCYpniAVtvpLPqLus5MxIc
C0KcapgHdcXOWZx75GKPpEemc8/6wl8nhs+xEDht0o8OZb9RM42/dXjR/G+0LGJj
wUbHMphAQoFT
-----END CERTIFICATE-----"""


class TestComputeX5tS256:
    """Test RFC 8705 fingerprint computation."""

    def test_returns_base64url_no_padding(self, sync_service):
        """x5t#S256 must be base64url without padding."""
        fingerprint = sync_service.compute_x5t_s256(TEST_CERT_PEM)

        # No padding
        assert '=' not in fingerprint
        # base64url (no + or /)
        assert '+' not in fingerprint
        assert '/' not in fingerprint
        # Non-empty
        assert len(fingerprint) > 0

    def test_deterministic(self, sync_service):
        """Same cert = same fingerprint."""
        fp1 = sync_service.compute_x5t_s256(TEST_CERT_PEM)
        fp2 = sync_service.compute_x5t_s256(TEST_CERT_PEM)
        assert fp1 == fp2

    def test_invalid_pem_raises_error(self, sync_service):
        """Invalid PEM raises CertificateParseError."""
        with pytest.raises(CertificateParseError):
            sync_service.compute_x5t_s256("not a certificate")

    def test_empty_pem_raises_error(self, sync_service):
        """Empty string raises CertificateParseError."""
        with pytest.raises(CertificateParseError):
            sync_service.compute_x5t_s256("")


class TestSyncMtlsClientCreate:
    """Test client creation sync."""

    @pytest.mark.asyncio
    async def test_creates_client_in_keycloak(self, sync_service, mock_kc):
        """New client is created in Keycloak."""
        mock_kc.get_clients.return_value = []
        mock_kc.create_client.return_value = "kc-uuid-123"

        result = await sync_service.sync_mtls_client_create(
            stoa_client_id="stoa-001",
            client_name="Test Client",
            tenant_id="tenant-acme",
            certificate_pem=TEST_CERT_PEM,
        )

        assert result.status == SyncStatus.SYNCED
        assert result.keycloak_id == "kc-uuid-123"
        mock_kc.create_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotent_if_exists(self, sync_service, mock_kc):
        """Existing client is not recreated."""
        mock_kc.get_clients.return_value = [
            {"id": "kc-existing", "attributes": {"stoa.client_id": "stoa-001"}}
        ]

        result = await sync_service.sync_mtls_client_create(
            stoa_client_id="stoa-001",
            client_name="Test",
            tenant_id="tenant-1",
            certificate_pem=TEST_CERT_PEM,
        )

        assert result.status == SyncStatus.SYNCED
        assert result.keycloak_id == "kc-existing"
        mock_kc.create_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_cert_returns_failed(self, sync_service, mock_kc):
        """Invalid certificate returns FAILED status."""
        mock_kc.get_clients.return_value = []

        result = await sync_service.sync_mtls_client_create(
            stoa_client_id="stoa-001",
            client_name="Test",
            tenant_id="tenant-1",
            certificate_pem="invalid cert",
        )

        assert result.status == SyncStatus.FAILED
        assert "Invalid certificate" in result.error
        mock_kc.create_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_keycloak_error_returns_failed(self, sync_service, mock_kc):
        """Keycloak error returns FAILED status."""
        from keycloak.exceptions import KeycloakError

        mock_kc.get_clients.return_value = []
        mock_kc.create_client.side_effect = KeycloakError("Connection refused")

        result = await sync_service.sync_mtls_client_create(
            stoa_client_id="stoa-001",
            client_name="Test",
            tenant_id="tenant-1",
            certificate_pem=TEST_CERT_PEM,
        )

        assert result.status == SyncStatus.FAILED
        assert "Keycloak error" in result.error


class TestNoFingerprintInLogs:
    """Verify security requirement: no fingerprint in logs."""

    @pytest.mark.asyncio
    async def test_fingerprint_not_logged_on_success(self, sync_service, mock_kc, caplog):
        """Fingerprint must not appear in logs."""
        mock_kc.get_clients.return_value = []
        mock_kc.create_client.return_value = "kc-123"

        await sync_service.sync_mtls_client_create(
            stoa_client_id="stoa-001",
            client_name="Test",
            tenant_id="tenant-1",
            certificate_pem=TEST_CERT_PEM,
        )

        fingerprint = sync_service.compute_x5t_s256(TEST_CERT_PEM)
        assert fingerprint not in caplog.text

    @pytest.mark.asyncio
    async def test_fingerprint_not_logged_on_error(self, sync_service, mock_kc, caplog):
        """Fingerprint must not appear in error logs."""
        from keycloak.exceptions import KeycloakError

        mock_kc.get_clients.return_value = []
        mock_kc.create_client.side_effect = KeycloakError("Failed")

        await sync_service.sync_mtls_client_create(
            stoa_client_id="stoa-001",
            client_name="Test",
            tenant_id="tenant-1",
            certificate_pem=TEST_CERT_PEM,
        )

        fingerprint = sync_service.compute_x5t_s256(TEST_CERT_PEM)
        assert fingerprint not in caplog.text


class TestExtractSubjectDn:
    """Test subject DN extraction."""

    def test_extracts_valid_subject_dn(self, sync_service):
        """Subject DN is correctly extracted from certificate."""
        subject_dn = sync_service._extract_subject_dn(TEST_CERT_PEM)
        assert "stoa.io" in subject_dn

    def test_returns_unknown_for_invalid_cert(self, sync_service):
        """Invalid certificate returns 'unknown'."""
        subject_dn = sync_service._extract_subject_dn("invalid cert")
        assert subject_dn == "unknown"


class TestGenerateKeycloakClientId:
    """Test Keycloak client ID generation."""

    def test_generates_opaque_id(self, sync_service):
        """Client ID is opaque (no tenant info leaked)."""
        client_id = sync_service._generate_keycloak_client_id()
        assert client_id.startswith("stoa-mtls-")
        assert len(client_id) == len("stoa-mtls-") + 12

    def test_generates_unique_ids(self, sync_service):
        """Each call generates a unique ID."""
        id1 = sync_service._generate_keycloak_client_id()
        id2 = sync_service._generate_keycloak_client_id()
        assert id1 != id2


class TestDeleteKeycloakClient:
    """Test client deletion."""

    @pytest.mark.asyncio
    async def test_deletes_existing_client(self, sync_service, mock_kc):
        """Existing client is deleted from Keycloak."""
        mock_kc.get_clients.return_value = [
            {"id": "kc-123", "attributes": {"stoa.client_id": "stoa-001"}}
        ]

        result = await sync_service.delete_keycloak_client("stoa-001")

        assert result is True
        mock_kc.delete_client.assert_called_once_with("kc-123")

    @pytest.mark.asyncio
    async def test_idempotent_for_missing_client(self, sync_service, mock_kc):
        """Deleting non-existent client returns True (idempotent)."""
        mock_kc.get_clients.return_value = []

        result = await sync_service.delete_keycloak_client("stoa-001")

        assert result is True
        mock_kc.delete_client.assert_not_called()


# Fixtures

@pytest.fixture
def mock_kc():
    """Mock KeycloakAdmin."""
    return MagicMock()


@pytest.fixture
def sync_service(mock_kc):
    """Service instance with mocked Keycloak."""
    return KeycloakCertificateSyncService(
        keycloak_admin=mock_kc,
        realm="stoa"
    )
