"""
Domain Events for Client Certificate Lifecycle (CAB-865 / CAB-866)

Events are published to Kafka CERT_EVENTS topic for async Keycloak sync.
"""
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ClientCreatedEvent:
    client_id: str
    tenant_id: str
    common_name: str
    certificate_serial: str
    certificate_fingerprint: str
    created_at: datetime
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class CertificateRotatedEvent:
    client_id: str
    tenant_id: str
    old_serial: str
    new_serial: str
    old_fingerprint: str
    new_fingerprint: str
    rotated_at: datetime
    grace_expires_at: Optional[datetime] = None
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class GracePeriodExpiredEvent:
    client_id: str
    tenant_id: str
    scheduled_at: datetime
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class ClientRevokedEvent:
    client_id: str
    tenant_id: str
    certificate_serial: str
    reason: str
    revoked_at: datetime
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))


_EVENT_TYPE_MAP = {
    "ClientCreatedEvent": "CLIENT_CREATED",
    "CertificateRotatedEvent": "CERTIFICATE_ROTATED",
    "ClientRevokedEvent": "CLIENT_REVOKED",
    "GracePeriodExpiredEvent": "GRACE_PERIOD_EXPIRED",
}


def emit_event(event) -> Optional[str]:
    """Publish a domain event to Kafka CERT_EVENTS topic."""
    from src.services.kafka_service import kafka_service, Topics

    event_class = type(event).__name__
    event_type = _EVENT_TYPE_MAP.get(event_class, event_class)
    correlation_id = getattr(event, "correlation_id", str(uuid.uuid4()))
    tenant_id = getattr(event, "tenant_id", "unknown")

    # Serialize dataclass, converting datetime to ISO strings
    payload = {}
    for k, v in asdict(event).items():
        if k == "correlation_id":
            continue
        payload[k] = v.isoformat() if isinstance(v, datetime) else v

    logger.info(
        "domain_event",
        extra={
            "event_type": event_type,
            "correlation_id": correlation_id,
            "tenant_id": tenant_id,
        },
    )

    try:
        import asyncio

        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an async context — schedule as a fire-and-forget task
        loop.create_task(_publish(
            Topics.CERT_EVENTS, event_type, tenant_id, payload, correlation_id,
        ))
    else:
        # Fallback: log only (should not happen in normal flow)
        logger.warning("emit_event_no_loop", extra={"correlation_id": correlation_id})

    return correlation_id


async def _publish(topic: str, event_type: str, tenant_id: str, payload: dict, correlation_id: str):
    """Async helper to publish to Kafka without blocking the caller."""
    from src.services.kafka_service import kafka_service

    try:
        await kafka_service.publish(
            topic=topic,
            event_type=event_type,
            tenant_id=tenant_id,
            payload=payload,
            key=correlation_id,
        )
    except Exception:
        logger.exception("emit_event_publish_failed", extra={"correlation_id": correlation_id})
