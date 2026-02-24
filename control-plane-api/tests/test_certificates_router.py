"""Tests for Certificates Router — CAB-313

Covers:
  - GET  /v1/certificates/health
  - POST /v1/certificates/validate
  - POST /v1/certificates/upload

All endpoints are public (no auth dependency). Uses the plain `client` fixture.
Real PEM certificates are generated via the `cryptography` library — no mocking
of _parse_certificate so the full code path is exercised.
"""

import io
from datetime import UTC, datetime, timedelta

import pytest


# ---------------------------------------------------------------------------
# Helpers: generate real PEM certificates via the cryptography library
# ---------------------------------------------------------------------------


def _make_cert(days_valid: int = 365, cn: str = "test.example.com") -> str:
    """Return a self-signed PEM certificate string.

    Args:
        days_valid: Positive = valid cert; negative = already expired.
        cn: Common Name for subject / issuer.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=days_valid))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _make_expired_cert() -> str:
    """Return a certificate whose not_valid_after is in the past."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cn = "expired.example.com"
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=10))
        .not_valid_after(now - timedelta(days=1))  # expired yesterday
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture(scope="module")
def valid_pem() -> str:
    """A self-signed certificate valid for 365 days."""
    return _make_cert(days_valid=365)


@pytest.fixture(scope="module")
def expired_pem() -> str:
    """A self-signed certificate that expired yesterday."""
    return _make_expired_cert()


# ---------------------------------------------------------------------------
# GET /v1/certificates/health
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """GET /v1/certificates/health"""

    def test_health_check_returns_healthy(self, client):
        resp = client.get("/v1/certificates/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["cryptography_available"] is True

    def test_health_check_expiry_warning_days_present(self, client):
        resp = client.get("/v1/certificates/health")

        data = resp.json()
        assert "expiry_warning_days" in data
        assert data["expiry_warning_days"] == 30

    def test_health_check_all_fields_present(self, client):
        resp = client.get("/v1/certificates/health")

        data = resp.json()
        assert "status" in data
        assert "cryptography_available" in data
        assert "expiry_warning_days" in data


# ---------------------------------------------------------------------------
# POST /v1/certificates/validate
# ---------------------------------------------------------------------------


class TestValidateCertificate:
    """POST /v1/certificates/validate"""

    def test_validate_valid_certificate(self, client, valid_pem):
        resp = client.post("/v1/certificates/validate", json={"pem_data": valid_pem})

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []
        assert data["certificate"] is not None

    def test_validate_invalid_pem(self, client):
        resp = client.post(
            "/v1/certificates/validate",
            json={"pem_data": "this-is-not-a-pem-certificate"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_expired_certificate(self, client, expired_pem):
        resp = client.post("/v1/certificates/validate", json={"pem_data": expired_pem})

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        error_text = " ".join(data["errors"]).lower()
        assert "expired" in error_text

    def test_validate_empty_pem_string(self, client):
        resp = client.post("/v1/certificates/validate", json={"pem_data": ""})

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_missing_pem_data_field_returns_422(self, client):
        resp = client.post("/v1/certificates/validate", json={})

        assert resp.status_code == 422

    def test_certificate_info_fields(self, client, valid_pem):
        """Verify all CertificateInfo fields are present in the response."""
        resp = client.post("/v1/certificates/validate", json={"pem_data": valid_pem})

        cert = resp.json()["certificate"]
        assert cert is not None
        required_fields = [
            "subject",
            "issuer",
            "valid_from",
            "valid_to",
            "days_until_expiry",
            "is_valid",
            "is_expired",
            "expires_soon",
            "serial_number",
            "fingerprint_sha256",
            "signature_algorithm",
            "san",
        ]
        for field in required_fields:
            assert field in cert, f"Missing CertificateInfo field: {field}"

    def test_validate_certificate_flags_for_valid_cert(self, client, valid_pem):
        resp = client.post("/v1/certificates/validate", json={"pem_data": valid_pem})

        cert = resp.json()["certificate"]
        assert cert["is_valid"] is True
        assert cert["is_expired"] is False
        assert cert["days_until_expiry"] > 0

    def test_validate_certificate_is_expired_for_expired_cert(self, client, expired_pem):
        resp = client.post("/v1/certificates/validate", json={"pem_data": expired_pem})

        data = resp.json()
        assert data["valid"] is False
        # If the certificate info is returned, it must reflect the expired state
        if data["certificate"] is not None:
            assert data["certificate"]["is_expired"] is True

    def test_validate_key_size_is_2048_for_rsa_cert(self, client, valid_pem):
        resp = client.post("/v1/certificates/validate", json={"pem_data": valid_pem})

        cert = resp.json()["certificate"]
        assert cert["key_size"] == 2048

    def test_validate_fingerprint_has_colon_separated_hex_pairs(self, client, valid_pem):
        resp = client.post("/v1/certificates/validate", json={"pem_data": valid_pem})

        fingerprint = resp.json()["certificate"]["fingerprint_sha256"]
        # SHA-256 = 32 bytes => 32 colon-separated hex pairs
        pairs = fingerprint.split(":")
        assert len(pairs) == 32
        for pair in pairs:
            assert len(pair) == 2
            int(pair, 16)  # raises ValueError if not valid hex

    def test_validate_subject_contains_cn(self, client):
        pem = _make_cert(cn="my.custom.cn")
        resp = client.post("/v1/certificates/validate", json={"pem_data": pem})

        subject = resp.json()["certificate"]["subject"]
        assert "my.custom.cn" in subject

    def test_validate_warnings_empty_for_long_lived_cert(self, client, valid_pem):
        # 365-day cert => no "expires soon" warning expected
        resp = client.post("/v1/certificates/validate", json={"pem_data": valid_pem})

        data = resp.json()
        assert data["warnings"] == []


# ---------------------------------------------------------------------------
# POST /v1/certificates/upload
# ---------------------------------------------------------------------------


class TestUploadCertificate:
    """POST /v1/certificates/upload"""

    def test_upload_valid_pem_file(self, client, valid_pem):
        pem_bytes = valid_pem.encode("utf-8")
        resp = client.post(
            "/v1/certificates/upload",
            files={"file": ("cert.pem", io.BytesIO(pem_bytes), "application/octet-stream")},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["certificate"] is not None
        assert data["errors"] == []

    def test_upload_crt_extension_accepted(self, client, valid_pem):
        pem_bytes = valid_pem.encode("utf-8")
        resp = client.post(
            "/v1/certificates/upload",
            files={"file": ("cert.crt", io.BytesIO(pem_bytes), "application/octet-stream")},
        )

        assert resp.status_code == 200

    def test_upload_cer_extension_accepted(self, client, valid_pem):
        pem_bytes = valid_pem.encode("utf-8")
        resp = client.post(
            "/v1/certificates/upload",
            files={"file": ("cert.cer", io.BytesIO(pem_bytes), "application/octet-stream")},
        )

        assert resp.status_code == 200

    def test_upload_invalid_extension_returns_400(self, client, valid_pem):
        pem_bytes = valid_pem.encode("utf-8")
        resp = client.post(
            "/v1/certificates/upload",
            files={"file": ("cert.txt", io.BytesIO(pem_bytes), "text/plain")},
        )

        assert resp.status_code == 400
        assert "extension" in resp.json()["detail"].lower()

    def test_upload_binary_content_returns_400(self, client):
        # Random byte values that are invalid UTF-8 sequences
        binary_data = bytes(range(128, 256)) * 16
        resp = client.post(
            "/v1/certificates/upload",
            files={"file": ("cert.pem", io.BytesIO(binary_data), "application/octet-stream")},
        )

        assert resp.status_code == 400
        assert "encoding" in resp.json()["detail"].lower()

    def test_upload_garbage_text_content_returns_validation_error(self, client):
        garbage = b"not-a-certificate-at-all"
        resp = client.post(
            "/v1/certificates/upload",
            files={"file": ("cert.pem", io.BytesIO(garbage), "application/octet-stream")},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_upload_expired_cert_file(self, client, expired_pem):
        pem_bytes = expired_pem.encode("utf-8")
        resp = client.post(
            "/v1/certificates/upload",
            files={"file": ("expired.pem", io.BytesIO(pem_bytes), "application/octet-stream")},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        error_text = " ".join(data["errors"]).lower()
        assert "expired" in error_text

    def test_upload_certificate_info_fields_present(self, client, valid_pem):
        pem_bytes = valid_pem.encode("utf-8")
        resp = client.post(
            "/v1/certificates/upload",
            files={"file": ("cert.pem", io.BytesIO(pem_bytes), "application/octet-stream")},
        )

        cert = resp.json()["certificate"]
        assert cert is not None
        required_fields = [
            "subject",
            "issuer",
            "valid_from",
            "valid_to",
            "days_until_expiry",
            "is_valid",
            "is_expired",
            "expires_soon",
            "serial_number",
            "fingerprint_sha256",
            "signature_algorithm",
            "san",
        ]
        for field in required_fields:
            assert field in cert, f"Missing CertificateInfo field: {field}"
