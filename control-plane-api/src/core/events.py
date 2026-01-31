"""
Domain Events for Client Certificate Lifecycle (CAB-865)

Stub implementations — log only for now.
CAB-866 will add Kafka consumers for Keycloak sync.
"""
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ClientCreatedEvent:
    client_id: str
    tenant_id: str
    common_name: str
    certificate_serial: str
    created_at: datetime


@dataclass
class CertificateRotatedEvent:
    client_id: str
    tenant_id: str
    old_serial: str
    new_serial: str
    rotated_at: datetime


@dataclass
class ClientRevokedEvent:
    client_id: str
    tenant_id: str
    certificate_serial: str
    reason: str
    revoked_at: datetime


def emit_event(event) -> None:
    """Emit a domain event. Stub: logs only. CAB-866 will add Kafka."""
    logger.info("domain_event", extra={"event_type": type(event).__name__, "event": event.__dict__})
