"""Tenant CA service — RSA-4096 keypair generation and CSR signing (CAB-1787).

Generates per-tenant CA keypairs with encrypted private key storage.
Signs CSRs for consumer mTLS certificates.
"""

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from .encryption_service import decrypt_auth_config, encrypt_auth_config

logger = logging.getLogger(__name__)

# CA certificate validity: 10 years
CA_VALIDITY_DAYS = 3650

# Signed client certificate validity: 1 year
CLIENT_CERT_VALIDITY_DAYS = 365


def generate_ca_keypair(tenant_id: str, tenant_name: str) -> dict:
    """Generate an RSA-4096 CA keypair for a tenant.

    Args:
        tenant_id: Tenant slug identifier.
        tenant_name: Tenant display name for the subject DN.

    Returns:
        Dict with ca_certificate_pem, encrypted_private_key, subject_dn,
        serial_number, not_before, not_after, fingerprint_sha256.
    """
    # Generate RSA-4096 private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    # Build CA subject
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "STOA Platform"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, tenant_name),
            x509.NameAttribute(NameOID.COMMON_NAME, f"{tenant_id}-ca"),
        ]
    )

    now = datetime.now(UTC)
    not_after = now + timedelta(days=CA_VALIDITY_DAYS)
    serial = x509.random_serial_number()

    # Build self-signed CA certificate
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(serial)
        .not_valid_before(now)
        .not_valid_after(not_after)
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    # Serialize
    ca_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    # Encrypt private key with Fernet
    encrypted_key = encrypt_auth_config({"key": private_key_pem})

    # Compute SHA-256 fingerprint
    der_bytes = cert.public_bytes(serialization.Encoding.DER)
    fingerprint = hashlib.sha256(der_bytes).hexdigest()

    logger.info("Generated CA keypair for tenant %s", tenant_id)

    return {
        "ca_certificate_pem": ca_pem,
        "encrypted_private_key": encrypted_key,
        "subject_dn": subject.rfc4514_string(),
        "serial_number": format(serial, "x"),
        "not_before": now,
        "not_after": not_after,
        "fingerprint_sha256": fingerprint,
        "key_algorithm": "RSA-4096",
    }


def sign_csr(
    csr_pem: str,
    ca_cert_pem: str,
    encrypted_private_key: str,
    validity_days: int = CLIENT_CERT_VALIDITY_DAYS,
) -> str:
    """Sign a CSR with the tenant's CA private key.

    Args:
        csr_pem: PEM-encoded CSR from the consumer.
        ca_cert_pem: PEM-encoded CA certificate.
        encrypted_private_key: Fernet-encrypted CA private key.
        validity_days: Certificate validity period in days.

    Returns:
        PEM-encoded signed certificate.

    Raises:
        ValueError: If CSR is invalid or CA key cannot be decrypted.
    """
    # Decrypt CA private key
    key_data = decrypt_auth_config(encrypted_private_key)
    private_key_pem = key_data["key"]
    ca_private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=None,
    )

    # Load CA certificate
    ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode("utf-8"))

    # Parse CSR
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid CSR: {e}") from e

    # Validate CSR signature
    if not csr.is_signature_valid:
        raise ValueError("CSR signature verification failed")

    now = datetime.now(UTC)
    not_after = now + timedelta(days=validity_days)

    # Build signed certificate
    cert = (
        x509.CertificateBuilder()
        .subject_name(csr.subject)
        .issuer_name(ca_cert.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(not_after)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_private_key.public_key()),
            critical=False,
        )
        .sign(ca_private_key, hashes.SHA256())
    )

    signed_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    logger.info(
        "Signed CSR for subject %s (valid %d days)",
        csr.subject.rfc4514_string(),
        validity_days,
    )
    return signed_pem
