"""
Mock Certificate Provider (CAB-865)

Self-signed certificate generation using the cryptography library.
Full X.509 extensions for production-grade client certificates.
Private key is NEVER stored — returned ONE TIME at creation.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from src.services.certificate_provider import (
    CertificateInfo,
    CertificateProvider,
    CertificateResult,
)


class MockCertificateProvider(CertificateProvider):
    """Self-signed certificate provider for development and MVP."""

    async def generate_certificate(
        self,
        common_name: str,
        tenant_id: str,
        validity_days: int = 365,
        key_size: int = 4096,
    ) -> CertificateResult:
        if key_size < 2048:
            raise ValueError("Key size must be at least 2048 bits")

        # Generate RSA keypair
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )

        now = datetime.now(timezone.utc)
        not_after = now + timedelta(days=validity_days)
        serial = x509.random_serial_number()

        # Build X.509 certificate with full extensions
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, f"tenant-{tenant_id}"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "STOA Platform Clients"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(serial)
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
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(f"{common_name}.{tenant_id}.clients.gostoa.dev"),
                ]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )

        # Serialize
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        fingerprint = cert.fingerprint(hashes.SHA256())
        fingerprint_hex = ":".join(f"{b:02x}" for b in fingerprint)

        return CertificateResult(
            certificate_pem=cert_pem,
            private_key_pem=key_pem,
            serial_number=format(serial, "x"),
            fingerprint_sha256=fingerprint_hex,
            common_name=common_name,
            not_before=now,
            not_after=not_after,
        )

    async def revoke_certificate(
        self, serial_number: str, reason: str = "unspecified"
    ) -> bool:
        # Mock provider: revocation is tracked in DB only
        return True

    async def get_certificate_info(
        self, serial_number: str
    ) -> Optional[CertificateInfo]:
        # Mock provider: info comes from DB, not from a CA
        return None
