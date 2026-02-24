"""Tests for Certificates Router — CAB-1448

Covers: /v1/certificates (validate, upload, health).
Public endpoints — no auth required.
"""

from io import BytesIO
from unittest.mock import patch


class TestValidateCertificate:
    """Tests for POST /v1/certificates/validate."""

    def test_validate_valid_pem(self, client_as_tenant_admin):
        with (
            patch("src.routers.certificates.CRYPTOGRAPHY_AVAILABLE", True),
            patch("src.routers.certificates._parse_certificate") as mock_parse,
        ):
            from src.routers.certificates import CertificateInfo

            cert_info = CertificateInfo(
                subject="CN=test.com",
                issuer="CN=CA",
                valid_from="2026-01-01T00:00:00",
                valid_to="2027-01-01T00:00:00",
                days_until_expiry=365,
                is_valid=True,
                is_expired=False,
                expires_soon=False,
                serial_number="abc123",
                fingerprint_sha256="aa:bb:cc",
                key_size=2048,
                signature_algorithm="sha256WithRSAEncryption",
                san=["DNS:test.com"],
            )
            mock_parse.return_value = (cert_info, [], [])
            resp = client_as_tenant_admin.post(
                "/v1/certificates/validate",
                json={"pem_data": "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["certificate"]["subject"] == "CN=test.com"
        assert data["errors"] == []

    def test_validate_invalid_pem(self, client_as_tenant_admin):
        with (
            patch("src.routers.certificates.CRYPTOGRAPHY_AVAILABLE", True),
            patch("src.routers.certificates._parse_certificate") as mock_parse,
        ):
            mock_parse.return_value = (None, ["Invalid PEM format: bad data"], [])
            resp = client_as_tenant_admin.post(
                "/v1/certificates/validate",
                json={"pem_data": "not-a-certificate"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_expired_cert(self, client_as_tenant_admin):
        with (
            patch("src.routers.certificates.CRYPTOGRAPHY_AVAILABLE", True),
            patch("src.routers.certificates._parse_certificate") as mock_parse,
        ):
            from src.routers.certificates import CertificateInfo

            cert_info = CertificateInfo(
                subject="CN=expired.com",
                issuer="CN=CA",
                valid_from="2020-01-01T00:00:00",
                valid_to="2021-01-01T00:00:00",
                days_until_expiry=-1000,
                is_valid=False,
                is_expired=True,
                expires_soon=False,
                serial_number="def456",
                fingerprint_sha256="dd:ee:ff",
                key_size=2048,
                signature_algorithm="sha256WithRSAEncryption",
                san=[],
            )
            mock_parse.return_value = (cert_info, ["Certificate expired"], [])
            resp = client_as_tenant_admin.post(
                "/v1/certificates/validate",
                json={"pem_data": "-----BEGIN CERTIFICATE-----\nexpired\n-----END CERTIFICATE-----"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["certificate"]["is_expired"] is True

    def test_validate_501_no_cryptography(self, client_as_tenant_admin):
        with patch("src.routers.certificates.CRYPTOGRAPHY_AVAILABLE", False):
            resp = client_as_tenant_admin.post(
                "/v1/certificates/validate",
                json={"pem_data": "test"},
            )
        assert resp.status_code == 501


class TestUploadCertificate:
    """Tests for POST /v1/certificates/upload."""

    def test_upload_pem_file(self, client_as_tenant_admin):
        with (
            patch("src.routers.certificates.CRYPTOGRAPHY_AVAILABLE", True),
            patch("src.routers.certificates._parse_certificate") as mock_parse,
        ):
            from src.routers.certificates import CertificateInfo

            cert_info = CertificateInfo(
                subject="CN=uploaded.com",
                issuer="CN=CA",
                valid_from="2026-01-01T00:00:00",
                valid_to="2027-01-01T00:00:00",
                days_until_expiry=365,
                is_valid=True,
                is_expired=False,
                expires_soon=False,
                serial_number="789",
                fingerprint_sha256="11:22:33",
                key_size=4096,
                signature_algorithm="sha256WithRSAEncryption",
                san=[],
            )
            mock_parse.return_value = (cert_info, [], [])

            file_content = b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----"
            resp = client_as_tenant_admin.post(
                "/v1/certificates/upload",
                files={"file": ("test.pem", BytesIO(file_content), "application/x-pem-file")},
            )

        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_upload_invalid_extension(self, client_as_tenant_admin):
        with patch("src.routers.certificates.CRYPTOGRAPHY_AVAILABLE", True):
            resp = client_as_tenant_admin.post(
                "/v1/certificates/upload",
                files={"file": ("test.txt", BytesIO(b"data"), "text/plain")},
            )
        assert resp.status_code == 400
        assert "Invalid file extension" in resp.json()["detail"]

    def test_upload_501_no_cryptography(self, client_as_tenant_admin):
        with patch("src.routers.certificates.CRYPTOGRAPHY_AVAILABLE", False):
            resp = client_as_tenant_admin.post(
                "/v1/certificates/upload",
                files={"file": ("test.pem", BytesIO(b"data"), "application/x-pem-file")},
            )
        assert resp.status_code == 501


class TestCertificateHealth:
    """Tests for GET /v1/certificates/health."""

    def test_health_available(self, client_as_tenant_admin):
        with patch("src.routers.certificates.CRYPTOGRAPHY_AVAILABLE", True):
            resp = client_as_tenant_admin.get("/v1/certificates/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["cryptography_available"] is True

    def test_health_degraded(self, client_as_tenant_admin):
        with patch("src.routers.certificates.CRYPTOGRAPHY_AVAILABLE", False):
            resp = client_as_tenant_admin.get("/v1/certificates/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["cryptography_available"] is False
