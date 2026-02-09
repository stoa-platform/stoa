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
        raise ValueError(
            f"Certificate expired on {cert_info.not_after.isoformat()}"
        )
