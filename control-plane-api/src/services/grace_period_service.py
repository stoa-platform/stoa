"""
Grace Period Service (CAB-869)

Manages certificate rotation grace periods:
- Schedules cleanup events via Kafka
- Clears previous fingerprints after grace period expires
"""
import logging
from datetime import datetime

from src.core.events import GracePeriodExpiredEvent, emit_event

logger = logging.getLogger(__name__)


class GracePeriodService:
    """Manages certificate rotation grace periods."""

    def schedule_cleanup(
        self,
        client_id: str,
        tenant_id: str,
        expires_at: datetime,
    ) -> None:
        """Emit a GracePeriodExpiredEvent to Kafka for deferred cleanup."""
        emit_event(GracePeriodExpiredEvent(
            client_id=client_id,
            tenant_id=tenant_id,
            scheduled_at=expires_at,
        ))
        logger.info(
            "grace_period_cleanup_scheduled",
            extra={
                "client_id": client_id,
                "tenant_id": tenant_id,
                "expires_at": expires_at.isoformat(),
            },
        )

    async def cleanup_expired(
        self,
        client_id: str,
        correlation_id: str,
    ) -> None:
        """Clear previous fingerprint from DB and Keycloak after grace period ends."""
        from src.database import async_session
        from src.models.client import Client
        from src.services.keycloak_cert_sync_service import keycloak_cert_sync_service

        async with async_session() as session:
            client = await session.get(Client, client_id)
            if not client:
                logger.warning("grace_cleanup_client_not_found", extra={
                    "client_id": client_id, "correlation_id": correlation_id,
                })
                return

            if not client.certificate_fingerprint_previous:
                logger.info("grace_cleanup_already_cleared", extra={
                    "client_id": client_id, "correlation_id": correlation_id,
                })
                return

            # Clear DB fields
            client.certificate_fingerprint_previous = None
            client.previous_cert_expires_at = None
            await session.commit()

        # Clear Keycloak attributes
        await keycloak_cert_sync_service.clear_previous_fingerprint(
            client, correlation_id
        )

        logger.info("grace_period_cleanup_completed", extra={
            "client_id": client_id, "correlation_id": correlation_id,
        })


grace_period_service = GracePeriodService()
