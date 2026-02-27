"""Tests for certificate utility functions (CAB-872)."""

import datetime
from datetime import UTC, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from src.services.certificate_utils import (
    CertificateInfo,
    certificate_health_score,
    days_until_expiry,
    parse_pem_certificate,
    validate_certificate_not_expired,
)

# ── Test certificate fixtures ──


def _make_cert_pem(not_before: datetime.datetime, not_after: datetime.datetime) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")


VALID_PEM = _make_cert_pem(
    not_before=datetime.datetime.now(UTC) - timedelta(days=1),
    not_after=datetime.datetime.now(UTC) + timedelta(days=365),
)

EXPIRED_PEM = _make_cert_pem(
    not_before=datetime.datetime.now(UTC) - timedelta(days=10),
    not_after=datetime.datetime.now(UTC) - timedelta(days=1),
)


# ── days_until_expiry ──


class TestDaysUntilExpiry:
    """Tests for days_until_expiry."""

    def test_future_cert(self):
        """Certificate expiring in 90 days returns ~90."""
        not_after = datetime.datetime.now(UTC) + timedelta(days=90)
        result = days_until_expiry(not_after)
        assert 89 <= result <= 90

    def test_expired_cert(self):
        """Expired certificate returns negative days."""
        not_after = datetime.datetime.now(UTC) - timedelta(days=10)
        result = days_until_expiry(not_after)
        assert result <= -10

    def test_expiring_today(self):
        """Certificate expiring today returns 0."""
        not_after = datetime.datetime.now(UTC) + timedelta(hours=12)
        result = days_until_expiry(not_after)
        assert result == 0


# ── certificate_health_score ──


class TestCertificateHealthScore:
    """Tests for certificate_health_score."""

    def test_healthy_active_cert(self):
        """Active cert with >90 days returns high score."""
        not_after = datetime.datetime.now(UTC) + timedelta(days=365)
        score = certificate_health_score(not_after, "active", rotation_count=1)
        # base=70 + status=30 + rotation=5 → capped at 100
        assert score == 100

    def test_expiring_soon_cert(self):
        """Active cert with 15 days returns moderate score."""
        not_after = datetime.datetime.now(UTC) + timedelta(days=15)
        score = certificate_health_score(not_after, "active", rotation_count=0)
        # base=30 + status=30 + rotation=0 = 60
        assert score == 60

    def test_critical_cert(self):
        """Active cert with 3 days returns low score."""
        not_after = datetime.datetime.now(UTC) + timedelta(days=3)
        score = certificate_health_score(not_after, "active", rotation_count=0)
        # base=10 + status=30 + rotation=0 = 40
        assert score == 40

    def test_expired_cert(self):
        """Expired cert returns 0."""
        not_after = datetime.datetime.now(UTC) - timedelta(days=5)
        score = certificate_health_score(not_after, "expired", rotation_count=0)
        # base=0 + status=0 + rotation=0 = 0
        assert score == 0

    def test_revoked_cert(self):
        """Revoked cert returns 0 status bonus."""
        not_after = datetime.datetime.now(UTC) + timedelta(days=365)
        score = certificate_health_score(not_after, "revoked", rotation_count=0)
        # base=70 + status=0 + rotation=0 = 70
        assert score == 70

    def test_rotating_cert(self):
        """Rotating cert gets 20 status bonus."""
        not_after = datetime.datetime.now(UTC) + timedelta(days=60)
        score = certificate_health_score(not_after, "rotating", rotation_count=1)
        # base=50 + status=20 + rotation=5 = 75
        assert score == 75

    def test_none_rotation_count(self):
        """None rotation_count is treated as 0."""
        not_after = datetime.datetime.now(UTC) + timedelta(days=365)
        score = certificate_health_score(not_after, "active", rotation_count=None)
        # base=70 + status=30 + rotation=0 = 100
        assert score == 100


# ── parse_pem_certificate (CAB-1538) ──


class TestParsePemCertificate:
    def test_valid_pem_returns_certificate_info(self):
        info = parse_pem_certificate(VALID_PEM)
        assert isinstance(info.fingerprint_hex, str)
        assert len(info.fingerprint_hex) == 64
        assert isinstance(info.fingerprint_b64url, str)
        assert "CN=test.example.com" in info.subject_dn
        assert "CN=test.example.com" in info.issuer_dn
        assert isinstance(info.serial, str)
        assert len(info.serial) > 0
        assert info.not_before.tzinfo is not None
        assert info.not_after.tzinfo is not None
        assert info.pem == VALID_PEM.strip()

    def test_fingerprint_hex_is_lowercase_sha256(self):
        info = parse_pem_certificate(VALID_PEM)
        assert info.fingerprint_hex == info.fingerprint_hex.lower()
        assert all(c in "0123456789abcdef" for c in info.fingerprint_hex)

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError, match="Empty certificate PEM data"):
            parse_pem_certificate("")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError, match="Empty certificate PEM data"):
            parse_pem_certificate("   \n  ")

    def test_invalid_pem_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid PEM certificate"):
            parse_pem_certificate("-----BEGIN CERTIFICATE-----\nnotbase64!!!\n-----END CERTIFICATE-----")


# ── validate_certificate_not_expired (CAB-1538) ──


class TestValidateCertificateNotExpired:
    def _make_info(self, not_after: datetime.datetime) -> CertificateInfo:
        return CertificateInfo(
            fingerprint_hex="a" * 64,
            fingerprint_b64url="dGVzdA",
            subject_dn="CN=test",
            issuer_dn="CN=test",
            serial="1a2b3c",
            not_before=datetime.datetime.now(UTC) - timedelta(days=1),
            not_after=not_after,
            pem="",
        )

    def test_valid_cert_does_not_raise(self):
        info = self._make_info(datetime.datetime.now(UTC) + timedelta(days=30))
        validate_certificate_not_expired(info)  # must not raise

    def test_expired_cert_raises_value_error(self):
        info = self._make_info(datetime.datetime.now(UTC) - timedelta(seconds=1))
        with pytest.raises(ValueError, match="Certificate expired on"):
            validate_certificate_not_expired(info)
