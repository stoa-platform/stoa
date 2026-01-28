"""
Certificate Service Facade

CAB-865: mTLS API Client Certificate Provisioning

Provides unified interface for certificate operations.
Automatically selects provider based on configuration.

Security (Gh0st):
- Error wrapping: Internal errors wrapped with generic messages
- No Vault/internal details leaked to clients
"""
import logging
from typing import Optional

from src.config import settings
from src.services.certificate_provider import (
    CertificateProvider,
    CertificateRequest,
    CertificateBundle,
    CertificateServiceUnavailable,
)
from src.services.certificate_providers.mock_provider import MockCertificateProvider

logger = logging.getLogger(__name__)

# Singleton instance
_certificate_service: Optional['CertificateService'] = None


class CertificateService:
    """
    Certificate service facade.

    Usage:
        service = get_certificate_service()
        bundle = await service.generate_certificate(request)
    """

    def __init__(self, provider: CertificateProvider):
        self._provider = provider
        logger.info(f"CertificateService initialized with provider: {provider.provider_name}")

    @property
    def provider_name(self) -> str:
        """Return current provider name."""
        return self._provider.provider_name

    async def generate_certificate(
        self,
        request: CertificateRequest
    ) -> CertificateBundle:
        """
        Generate a new client certificate.

        Wraps provider errors with generic message (Gh0st security).
        """
        try:
            return await self._provider.generate_certificate(request)
        except CertificateServiceUnavailable:
            raise
        except Exception as e:
            # Log full error internally
            logger.error(
                f"Certificate generation failed for client {request.client_id}: {e}",
                exc_info=True
            )
            # Return generic error (no internal details - Gh0st security)
            raise CertificateServiceUnavailable(
                "Certificate service temporarily unavailable. Please try again."
            )

    async def revoke_certificate(
        self,
        serial_number: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Revoke a certificate.

        Wraps provider errors with generic message (Gh0st security).
        """
        try:
            return await self._provider.revoke_certificate(serial_number, reason)
        except CertificateServiceUnavailable:
            raise
        except Exception as e:
            logger.error(
                f"Certificate revocation failed for serial {serial_number}: {e}",
                exc_info=True
            )
            raise CertificateServiceUnavailable(
                "Certificate service temporarily unavailable. Please try again."
            )


def get_certificate_service() -> CertificateService:
    """
    Get or create certificate service singleton.

    Provider selection based on settings:
    - VAULT_PKI_ENABLED=true: VaultPKIProvider (P1 - not yet implemented)
    - Default: MockCertificateProvider
    """
    global _certificate_service

    if _certificate_service is not None:
        return _certificate_service

    # Select provider based on configuration
    vault_pki_enabled = getattr(settings, 'VAULT_PKI_ENABLED', False)

    if vault_pki_enabled:
        # VaultPKIProvider is P1 - not yet implemented
        # For now, fall back to mock with warning
        logger.warning(
            "VAULT_PKI_ENABLED is true but VaultPKIProvider not yet implemented (P1). "
            "Using MockCertificateProvider."
        )
        provider = MockCertificateProvider()
    else:
        provider = MockCertificateProvider()
        logger.warning(
            "Certificate service using MOCK provider - "
            "NOT FOR PRODUCTION (self-signed certificates)"
        )

    _certificate_service = CertificateService(provider)
    return _certificate_service


async def get_certificate_service_dep() -> CertificateService:
    """FastAPI dependency for certificate service."""
    return get_certificate_service()


# For use in services/__init__.py export
certificate_service = None  # Lazy initialization


def _ensure_certificate_service() -> CertificateService:
    """Ensure certificate service is initialized."""
    global certificate_service
    if certificate_service is None:
        certificate_service = get_certificate_service()
    return certificate_service
