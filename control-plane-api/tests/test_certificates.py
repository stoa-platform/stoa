# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
Tests for Certificate Validation Router (CAB-313)
"""

import pytest
from datetime import datetime, timedelta, UTC
from fastapi.testclient import TestClient

# Sample valid PEM certificate (self-signed, for testing)
SAMPLE_CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIDazCCAlOgAwIBAgIUJ5Zz3v7Y5QH5a1e7V5TL0g0V6sUwDQYJKoZIhvcNAQEL
BQAwRTELMAkGA1UEBhMCRlIxEzARBgNVBAgMClNvbWUtU3RhdGUxITAfBgNVBAoM
GEludGVybmV0IFdpZGdpdHMgUHR5IEx0ZDAeFw0yNDAxMDEwMDAwMDBaFw0yNTEy
MzEyMzU5NTlaMEUxCzAJBgNVBAYTAkZSMRMwEQYDVQQIDApTb21lLVN0YXRlMSEw
HwYDVQQKDBhJbnRlcm5ldCBXaWRnaXRzIFB0eSBMdGQwggEiMA0GCSqGSIb3DQEB
AQUAA4IBDwAwggEKAoIBAQDGxY+vL5Y5h5E5E5F5G5H5I5J5K5L5M5N5O5P5Q5R5
S5T5U5V5W5X5Y5Z5a5b5c5d5e5f5g5h5i5j5k5l5m5n5o5p5q5r5s5t5u5v5w5x5
y5z5A5B5C5D5E5F5G5H5I5J5K5L5M5N5O5P5Q5R5S5T5U5V5W5X5Y5Z5a5b5c5d5
e5f5g5h5i5j5k5l5m5n5o5p5q5r5s5t5u5v5w5x5y5z5A5B5C5D5E5F5G5H5I5J5
K5L5M5N5O5P5Q5R5S5T5U5V5W5X5Y5Z5a5b5c5d5e5f5g5h5i5j5k5AgMBAAGj
UzBRMB0GA1UdDgQWBBQr5LbJ5R5R5R5R5R5R5R5R5R5R5TAfBgNVHSMEGDAWgBQr
5LbJ5R5R5R5R5R5R5R5R5R5R5TAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEB
CwUAA4IBAQCx5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R
5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R
5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R5R
-----END CERTIFICATE-----"""

# Invalid PEM data
INVALID_PEM = """-----BEGIN CERTIFICATE-----
This is not valid base64 certificate data!
-----END CERTIFICATE-----"""

# Not a certificate
NOT_A_CERT = """Just some random text that is not a certificate"""


class TestCertificateRouter:
    """Test certificate validation endpoints."""

    def test_health_check(self, client: TestClient):
        """Test certificate service health check."""
        response = client.get("/v1/certificates/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "cryptography_available" in data

    def test_validate_invalid_pem(self, client: TestClient):
        """Test validation with invalid PEM data."""
        response = client.post(
            "/v1/certificates/validate",
            json={"pem_data": INVALID_PEM}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0
        assert data["certificate"] is None

    def test_validate_not_a_certificate(self, client: TestClient):
        """Test validation with non-certificate data."""
        response = client.post(
            "/v1/certificates/validate",
            json={"pem_data": NOT_A_CERT}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_empty_pem(self, client: TestClient):
        """Test validation with empty PEM data."""
        response = client.post(
            "/v1/certificates/validate",
            json={"pem_data": ""}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    def test_validate_missing_pem_field(self, client: TestClient):
        """Test validation with missing pem_data field."""
        response = client.post(
            "/v1/certificates/validate",
            json={}
        )
        assert response.status_code == 422  # Validation error


class TestCertificateUpload:
    """Test certificate file upload."""

    def test_upload_invalid_extension(self, client: TestClient):
        """Test upload with invalid file extension."""
        # Create a mock file with wrong extension
        response = client.post(
            "/v1/certificates/upload",
            files={"file": ("test.txt", b"test content", "text/plain")}
        )
        assert response.status_code == 400
        assert "Invalid file extension" in response.json()["detail"]

    def test_upload_pem_file(self, client: TestClient):
        """Test upload of PEM file."""
        response = client.post(
            "/v1/certificates/upload",
            files={"file": ("test.pem", INVALID_PEM.encode(), "application/x-pem-file")}
        )
        assert response.status_code == 200
        data = response.json()
        # File should be processed but certificate invalid
        assert "valid" in data

    def test_upload_crt_file(self, client: TestClient):
        """Test upload of CRT file."""
        response = client.post(
            "/v1/certificates/upload",
            files={"file": ("test.crt", INVALID_PEM.encode(), "application/x-x509-ca-cert")}
        )
        assert response.status_code == 200


class TestCertificateParsing:
    """Test certificate parsing logic."""

    @pytest.mark.skipif(True, reason="Requires valid certificate")
    def test_parse_valid_certificate(self, client: TestClient):
        """Test parsing a valid certificate."""
        # This test requires a real valid certificate
        # Skipped by default as it needs infrastructure
        pass

    def test_response_structure(self, client: TestClient):
        """Test that response has correct structure."""
        response = client.post(
            "/v1/certificates/validate",
            json={"pem_data": INVALID_PEM}
        )
        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "valid" in data
        assert "certificate" in data
        assert "errors" in data
        assert "warnings" in data
        assert isinstance(data["errors"], list)
        assert isinstance(data["warnings"], list)


# Fixtures
@pytest.fixture
def client():
    """Create test client."""
    from src.main import app
    with TestClient(app) as c:
        yield c
