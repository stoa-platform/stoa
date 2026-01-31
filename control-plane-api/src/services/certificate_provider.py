"""
Abstract Certificate Provider Interface (CAB-865)

Defines the contract for certificate provisioning backends.
MVP: MockCertificateProvider (self-signed)
Future: VaultPKIProvider (HashiCorp Vault PKI)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class CertificateResult:
    """Result of certificate generation. Private key is ONE-TIME only."""
    certificate_pem: str
    private_key_pem: str  # Never stored - returned once
    serial_number: str
    fingerprint_sha256: str
    common_name: str
    not_before: datetime
    not_after: datetime


@dataclass
class CertificateInfo:
    """Certificate metadata (no private key)."""
    serial_number: str
    common_name: str
    fingerprint_sha256: str
    not_before: datetime
    not_after: datetime
    is_valid: bool


class CertificateProvider(ABC):
    """Abstract base class for certificate provisioning backends."""

    @abstractmethod
    async def generate_certificate(
        self,
        common_name: str,
        tenant_id: str,
        validity_days: int = 365,
        key_size: int = 4096,
    ) -> CertificateResult:
        """Generate a new client certificate.

        Args:
            common_name: Sanitized CN for the certificate subject.
            tenant_id: Tenant identifier for isolation.
            validity_days: Certificate validity period.
            key_size: RSA key size in bits (min 2048).

        Returns:
            CertificateResult with PEM cert, private key (one-time), and metadata.
        """
        ...

    @abstractmethod
    async def revoke_certificate(
        self, serial_number: str, reason: str = "unspecified"
    ) -> bool:
        """Revoke a certificate by serial number."""
        ...

    @abstractmethod
    async def get_certificate_info(
        self, serial_number: str
    ) -> Optional[CertificateInfo]:
        """Get certificate metadata by serial number."""
        ...
