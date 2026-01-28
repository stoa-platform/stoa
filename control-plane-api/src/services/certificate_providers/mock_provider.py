"""
Mock Certificate Provider for Development/Testing

CAB-865: mTLS API Client Certificate Provisioning

Generates self-signed certificates with FULL X.509 extensions.
NOT for production use - certificates are self-signed.

Security Notes (Team Coca - Chucky):
- Full X.509 extensions (BasicConstraints, KeyUsage, ExtKeyUsage, SAN)
- Cryptographically secure serial numbers via x509.random_serial_number()
- SHA-256 signatures
- Minimum 2048-bit keys
"""
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Set

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from src.services.certificate_provider import (
    CertificateProvider,
    CertificateRequest,
    CertificateBundle,
    CertificateGenerationError,
)

logger = logging.getLogger(__name__)


class MockCertificateProvider(CertificateProvider):
    """
    Self-signed certificate provider for development and testing.

    WARNING: Not for production use!
    Certificates are self-signed and not trusted by browsers/systems.
    """

    def __init__(
        self,
        ca_common_name: str = "STOA Mock CA",
        ca_organization: str = "STOA Platform (Development)",
    ):
        self.ca_common_name = ca_common_name
        self.ca_organization = ca_organization
        self._revoked_serials: Set[str] = set()

        logger.warning(
            "MockCertificateProvider initialized - "
            "NOT FOR PRODUCTION USE (self-signed certificates)"
        )

    @property
    def provider_name(self) -> str:
        return "mock"

    def _sanitize_cn(self, value: str) -> str:
        """
        Sanitize Common Name to prevent injection.

        Security (Team Coca - N3m0):
        - Remove all non-alphanumeric except dash, underscore, dot
        - Limit to 64 characters
        """
        sanitized = re.sub(r'[^a-zA-Z0-9\-_\.]', '', value)
        return sanitized[:64]

    async def generate_certificate(
        self,
        request: CertificateRequest
    ) -> CertificateBundle:
        """Generate a self-signed client certificate with full X.509 extensions."""

        try:
            # Sanitize inputs (N3m0 security)
            safe_client_name = self._sanitize_cn(request.client_name)
            safe_tenant_id = self._sanitize_cn(request.tenant_id)

            # Build Common Name
            common_name = f"{safe_client_name}.{safe_tenant_id}.stoa.local"

            logger.info(
                f"Generating mock certificate for {common_name} "
                f"(key_size={request.key_size}, validity={request.validity_days}d)"
            )

            # Generate RSA key pair
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=request.key_size,
                backend=default_backend()
            )

            # Generate cryptographically secure serial number
            serial_number = x509.random_serial_number()

            # Validity period
            now = datetime.now(timezone.utc)
            not_before = now
            not_after = now + timedelta(days=request.validity_days)

            # Build subject and issuer (self-signed)
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "EU"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.ca_organization),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, f"Tenant {safe_tenant_id}"),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ])

            # Build SAN entries
            san_entries = [
                x509.DNSName(common_name),
                x509.DNSName(f"{request.client_id}.stoa.local"),
            ]

            # Add custom DNS names
            for dns_name in request.dns_names:
                san_entries.append(x509.DNSName(self._sanitize_cn(dns_name)))

            # Add SPIFFE URI
            spiffe_uri = f"spiffe://stoa.local/tenant/{safe_tenant_id}/client/{request.client_id}"
            san_entries.append(x509.UniformResourceIdentifier(spiffe_uri))

            # Add custom URIs
            for uri in request.uri_sans:
                san_entries.append(x509.UniformResourceIdentifier(uri))

            # Build certificate with FULL X.509 extensions (Chucky security fix)
            cert_builder = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(private_key.public_key())
                .serial_number(serial_number)
                .not_valid_before(not_before)
                .not_valid_after(not_after)

                # Extension 1: Basic Constraints (CRITICAL)
                # This is NOT a CA certificate
                .add_extension(
                    x509.BasicConstraints(ca=False, path_length=None),
                    critical=True
                )

                # Extension 2: Key Usage (CRITICAL)
                # Only allow digital signature and key encipherment
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
                        decipher_only=False
                    ),
                    critical=True
                )

                # Extension 3: Extended Key Usage
                # Only allow TLS Client Authentication
                .add_extension(
                    x509.ExtendedKeyUsage([
                        ExtendedKeyUsageOID.CLIENT_AUTH
                    ]),
                    critical=False
                )

                # Extension 4: Subject Alternative Name
                .add_extension(
                    x509.SubjectAlternativeName(san_entries),
                    critical=False
                )

                # Extension 5: Subject Key Identifier
                .add_extension(
                    x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
                    critical=False
                )
            )

            # Sign certificate with SHA-256 (Chucky security requirement)
            certificate = cert_builder.sign(
                private_key=private_key,
                algorithm=hashes.SHA256(),
                backend=default_backend()
            )

            # Serialize to PEM
            cert_pem = certificate.public_bytes(serialization.Encoding.PEM).decode('utf-8')
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')

            # Calculate SHA-256 fingerprint
            der_bytes = certificate.public_bytes(serialization.Encoding.DER)
            fingerprint = hashlib.sha256(der_bytes).hexdigest()

            logger.info(
                f"Generated mock certificate: serial={format(serial_number, 'x')}, "
                f"fingerprint={fingerprint[:16]}..., expires={not_after.isoformat()}"
            )

            return CertificateBundle(
                certificate_pem=cert_pem,
                private_key_pem=key_pem,
                ca_chain_pem=cert_pem,  # Self-signed, CA is itself
                serial_number=format(serial_number, 'x'),
                fingerprint_sha256=fingerprint,
                subject_dn=subject.rfc4514_string(),
                issuer_dn=issuer.rfc4514_string(),
                not_before=not_before,
                not_after=not_after,
                vault_pki_serial=None  # No Vault for mock
            )

        except Exception as e:
            logger.error(f"Failed to generate certificate: {e}", exc_info=True)
            raise CertificateGenerationError(f"Certificate generation failed: {e}")

    async def revoke_certificate(
        self,
        serial_number: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Revoke a certificate (mock - just tracks in memory).

        In production, this would call Vault PKI revoke API.
        """
        if serial_number in self._revoked_serials:
            logger.info(f"Certificate {serial_number} already revoked")
            return False

        self._revoked_serials.add(serial_number)
        logger.info(
            f"Revoked mock certificate: serial={serial_number}, "
            f"reason={reason or 'unspecified'}"
        )
        return True

    def is_revoked(self, serial_number: str) -> bool:
        """Check if a certificate is revoked (mock only)."""
        return serial_number in self._revoked_serials
