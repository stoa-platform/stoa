"""Certificate parsing and validation utilities (CAB-864).

Provides X.509 PEM certificate parsing, SHA-256 fingerprint computation,
and expiry validation for mTLS consumer onboarding.
"""

import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding


@dataclass
class CertificateInfo:
    """Parsed certificate metadata."""

    fingerprint_hex: str
    fingerprint_b64url: str
    subject_dn: str
    issuer_dn: str
    serial: str
    not_before: datetime
    not_after: datetime
    pem: str


def parse_pem_certificate(pem_data: str) -> CertificateInfo:
    """Parse a PEM-encoded X.509 certificate and extract metadata.

    Args:
        pem_data: PEM-encoded certificate string.

    Returns:
        CertificateInfo with fingerprint, DN fields, validity dates.

    Raises:
        ValueError: If the PEM data is invalid or cannot be parsed.
    """
    pem_data = pem_data.strip()
    if not pem_data:
        raise ValueError("Empty certificate PEM data")

    try:
        cert = x509.load_pem_x509_certificate(pem_data.encode("utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid PEM certificate: {e}") from e

    # SHA-256 fingerprint (hex lowercase)
    der_bytes = cert.public_bytes(Encoding.DER)
    sha256_digest = hashlib.sha256(der_bytes).digest()
    fingerprint_hex = sha256_digest.hex()

    # Base64url for RFC 8705 cnf.x5t#S256
    fingerprint_b64url = base64.urlsafe_b64encode(sha256_digest).rstrip(b"=").decode("ascii")

    subject_dn = cert.subject.rfc4514_string()
    issuer_dn = cert.issuer.rfc4514_string()
    serial = format(cert.serial_number, "x")

    return CertificateInfo(
        fingerprint_hex=fingerprint_hex,
        fingerprint_b64url=fingerprint_b64url,
        subject_dn=subject_dn,
        issuer_dn=issuer_dn,
        serial=serial,
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        pem=pem_data,
    )


def validate_certificate_not_expired(cert_info: CertificateInfo) -> None:
    """Validate that a certificate has not expired.

    Args:
        cert_info: Parsed certificate info.

    Raises:
        ValueError: If the certificate has expired.
    """
    now = datetime.now(UTC)
    if cert_info.not_after < now:
        raise ValueError(f"Certificate expired on {cert_info.not_after.isoformat()}")


def days_until_expiry(not_after: datetime) -> int:
    """Calculate days until certificate expiry.

    Args:
        not_after: Certificate expiration datetime.

    Returns:
        Number of days until expiry (negative if already expired).
    """
    now = datetime.now(UTC)
    delta = not_after - now
    return delta.days


def certificate_health_score(
    not_after: datetime,
    status: str,
    rotation_count: int | None = None,
) -> int:
    """Compute a 0-100 health score for a certificate.

    Scoring:
    - Base: days until expiry mapped to 0-70 points
    - Status bonus: active=30, rotating=20, revoked/expired=0
    - Rotation bonus: +5 if rotated at least once (max 5)

    Args:
        not_after: Certificate expiration datetime.
        status: Certificate status string.
        rotation_count: Number of times certificate has been rotated.

    Returns:
        Integer health score 0-100.
    """
    days = days_until_expiry(not_after)

    # Base score from days until expiry (0-70)
    if days <= 0:
        base = 0
    elif days <= 7:
        base = 10
    elif days <= 30:
        base = 30
    elif days <= 90:
        base = 50
    else:
        base = 70

    # Status bonus (0-30)
    status_bonus = {"active": 30, "rotating": 20}.get(status, 0)

    # Rotation bonus (0-5)
    rotation_bonus = 5 if (rotation_count or 0) > 0 else 0

    return min(base + status_bonus + rotation_bonus, 100)
