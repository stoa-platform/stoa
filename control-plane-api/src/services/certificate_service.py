"""
Certificate Service Facade (CAB-865)

Orchestrates certificate provisioning with:
- Provider selection (mock/vault)
- CN sanitization
- Error wrapping (no internal crypto leaks)
- Event emission for Keycloak sync (CAB-866)
"""
import logging
import re
from datetime import datetime, timezone

from src.config import settings
from src.core.events import (
    CertificateRotatedEvent,
    ClientCreatedEvent,
    ClientRevokedEvent,
    emit_event,
)
from src.services.certificate_provider import CertificateProvider, CertificateResult

logger = logging.getLogger(__name__)

CN_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,62}$")


class CertificateServiceError(Exception):
    """Public-facing certificate service error. Never exposes internals."""
    pass


class CertificateService:
    """Facade for certificate provisioning operations."""

    def __init__(self):
        self._provider: CertificateProvider | None = None

    @property
    def provider(self) -> CertificateProvider:
        if self._provider is None:
            self._provider = self._create_provider()
        return self._provider

    def _create_provider(self) -> CertificateProvider:
        provider_type = getattr(settings, "CERTIFICATE_PROVIDER", "mock")
        if provider_type == "vault":
            raise CertificateServiceError(
                "Vault PKI provider not yet implemented. Use 'mock' provider."
            )
        from src.services.certificate_providers.mock_provider import (
            MockCertificateProvider,
        )
        return MockCertificateProvider()

    @staticmethod
    def validate_common_name(common_name: str) -> str:
        """Sanitize and validate CN. Raises CertificateServiceError on invalid input."""
        cn = common_name.strip()
        if not CN_PATTERN.match(cn):
            raise CertificateServiceError(
                "Invalid common name. Must match: alphanumeric start, "
                "followed by alphanumeric, dots, hyphens, or underscores (max 63 chars)."
            )
        return cn

    async def generate_certificate(
        self,
        common_name: str,
        tenant_id: str,
        client_id: str,
        validity_days: int | None = None,
        key_size: int | None = None,
    ) -> CertificateResult:
        """Generate a client certificate. Returns private key ONE TIME."""
        cn = self.validate_common_name(common_name)
        vdays = validity_days or getattr(settings, "CERTIFICATE_VALIDITY_DAYS", 365)
        ksize = key_size or getattr(settings, "CERTIFICATE_KEY_SIZE", 4096)

        try:
            result = await self.provider.generate_certificate(
                common_name=cn,
                tenant_id=tenant_id,
                validity_days=vdays,
                key_size=ksize,
            )
        except Exception:
            logger.exception("certificate_generation_failed", extra={"tenant_id": tenant_id, "cn": cn})
            raise CertificateServiceError("Failed to generate certificate. Please try again.")

        emit_event(ClientCreatedEvent(
            client_id=client_id,
            tenant_id=tenant_id,
            common_name=cn,
            certificate_serial=result.serial_number,
            created_at=datetime.now(timezone.utc),
        ))

        return result

    async def rotate_certificate(
        self,
        client_id: str,
        tenant_id: str,
        common_name: str,
        old_serial: str,
    ) -> CertificateResult:
        """Rotate: revoke old cert + generate new one."""
        try:
            await self.provider.revoke_certificate(old_serial, reason="superseded")
            result = await self.provider.generate_certificate(
                common_name=common_name,
                tenant_id=tenant_id,
                validity_days=getattr(settings, "CERTIFICATE_VALIDITY_DAYS", 365),
                key_size=getattr(settings, "CERTIFICATE_KEY_SIZE", 4096),
            )
        except Exception:
            logger.exception("certificate_rotation_failed", extra={"tenant_id": tenant_id, "client_id": client_id})
            raise CertificateServiceError("Failed to rotate certificate. Please try again.")

        emit_event(CertificateRotatedEvent(
            client_id=client_id,
            tenant_id=tenant_id,
            old_serial=old_serial,
            new_serial=result.serial_number,
            rotated_at=datetime.now(timezone.utc),
        ))

        return result

    async def revoke_certificate(
        self,
        client_id: str,
        tenant_id: str,
        serial_number: str,
        reason: str = "unspecified",
    ) -> bool:
        """Revoke a certificate."""
        try:
            success = await self.provider.revoke_certificate(serial_number, reason)
        except Exception:
            logger.exception("certificate_revocation_failed", extra={"tenant_id": tenant_id, "serial": serial_number})
            raise CertificateServiceError("Failed to revoke certificate. Please try again.")

        if success:
            emit_event(ClientRevokedEvent(
                client_id=client_id,
                tenant_id=tenant_id,
                certificate_serial=serial_number,
                reason=reason,
                revoked_at=datetime.now(timezone.utc),
            ))

        return success


certificate_service = CertificateService()
