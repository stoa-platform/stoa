"""SecurityEvent model — stores security alerts from Kafka for DORA retention."""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from ..database import Base


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = sa.Column(UUID(as_uuid=True), nullable=False, unique=True)
    tenant_id = sa.Column(sa.String(255), nullable=False, index=True)
    event_type = sa.Column(sa.String(100), nullable=False)
    severity = sa.Column(sa.String(20), nullable=False)
    source = sa.Column(sa.String(100), nullable=False)
    payload = sa.Column(JSONB, nullable=False, default=dict)
    created_at = sa.Column(sa.DateTime(), nullable=False, server_default=sa.text("now()"), index=True)
