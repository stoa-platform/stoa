"""
Certificate Provider Protocol and Data Types

CAB-865: mTLS API Client Certificate Provisioning

Security Requirements (Team Coca):
- Private key: NEVER stored, returned ONE TIME only
- Serial entropy: cryptographically secure random
- Key size: minimum 2048, default 4096
- Extensions: BasicConstraints, KeyUsage, ExtKeyUsage, SAN required
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass(frozen=True)
class CertificateRequest:
    """Request to generate a new certificate."""
    client_id: str
    client_name: str
    tenant_id: str
    validity_days: int = 365
    key_size: int = 4096  # Default to 4096 for security

    # SAN entries
    dns_names: List[str] = field(default_factory=list)
    uri_sans: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.key_size < 2048:
            raise ValueError("Key size must be at least 2048 bits")
        if self.validity_days < 1 or self.validity_days > 730:
            raise ValueError("Validity must be between 1 and 730 days")


@dataclass(frozen=True)
class CertificateBundle:
    """
    Complete certificate bundle with private key.

    SECURITY WARNING:
    - private_key_pem is returned ONE TIME ONLY at creation
    - NEVER store private_key_pem in database or logs
    - NEVER include in __repr__ or __str__
    """
    certificate_pem: str
    private_key_pem: str  # ONE-TIME ONLY - never stored
    ca_chain_pem: str
    serial_number: str
    fingerprint_sha256: str
    subject_dn: str
    issuer_dn: str
    not_before: datetime
    not_after: datetime

    # Vault reference for revocation (optional)
    vault_pki_serial: Optional[str] = None

    def __repr__(self) -> str:
        """Safe repr - NEVER includes private key."""
        return (
            f"CertificateBundle("
            f"serial={self.serial_number}, "
            f"fingerprint={self.fingerprint_sha256[:16]}..., "
            f"expires={self.not_after.isoformat()})"
        )

    def __str__(self) -> str:
        """Safe str - NEVER includes private key."""
        return self.__repr__()

    def to_public_dict(self) -> dict:
        """Return only public information (no private key)."""
        return {
            "certificate_pem": self.certificate_pem,
            "ca_chain_pem": self.ca_chain_pem,
            "serial_number": self.serial_number,
            "fingerprint_sha256": self.fingerprint_sha256,
            "subject_dn": self.subject_dn,
            "issuer_dn": self.issuer_dn,
            "not_before": self.not_before.isoformat(),
            "not_after": self.not_after.isoformat(),
        }


class CertificateProviderError(Exception):
    """Base exception for certificate provider errors."""
    pass


class CertificateGenerationError(CertificateProviderError):
    """Failed to generate certificate."""
    pass


class CertificateRevocationError(CertificateProviderError):
    """Failed to revoke certificate."""
    pass


class CertificateServiceUnavailable(CertificateProviderError):
    """
    Certificate service temporarily unavailable.

    Used to wrap internal errors without leaking details.
    Maps to HTTP 503.
    """
    def __init__(self, message: str = "Certificate service temporarily unavailable"):
        super().__init__(message)


class CertificateProvider(ABC):
    """
    Abstract certificate provider protocol.

    Implementations:
    - MockCertificateProvider: Self-signed certs for dev/test
    - VaultPKIProvider: HashiCorp Vault PKI for production (P1)
    """

    @abstractmethod
    async def generate_certificate(
        self,
        request: CertificateRequest
    ) -> CertificateBundle:
        """
        Generate a new client certificate.

        Args:
            request: Certificate generation request

        Returns:
            CertificateBundle with private key (ONE TIME ONLY)

        Raises:
            CertificateGenerationError: Generation failed
            CertificateServiceUnavailable: Service temporarily down
        """
        pass

    @abstractmethod
    async def revoke_certificate(
        self,
        serial_number: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Revoke a certificate by serial number.

        Args:
            serial_number: Certificate serial to revoke
            reason: Optional revocation reason

        Returns:
            True if revoked, False if already revoked

        Raises:
            CertificateRevocationError: Revocation failed
            CertificateServiceUnavailable: Service temporarily down
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier (e.g., 'mock', 'vault')."""
        pass
