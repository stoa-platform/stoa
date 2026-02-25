"""Immutable audit event model for compliance-grade audit trail (CAB-1475).

Stores every mutating API operation in PostgreSQL for DORA/NIS2 retention.
This table is append-only — no UPDATE or DELETE is allowed by application code.
Dual-writes alongside OpenSearch (which handles search/analytics).
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AuditAction(enum.StrEnum):
    """High-level audit action categories."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    ACCESS_DENIED = "access_denied"
    CONFIG_CHANGE = "config_change"
    EXPORT = "export"
    DEPLOY = "deploy"


class AuditOutcome(enum.StrEnum):
    """Outcome of the audited operation."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


class AuditEvent(Base):
    """Immutable audit event — compliance-grade, append-only.

    Captures who did what, to which resource, when, and from where.
    Designed for DORA Article 11 (ICT incident retention) and NIS2 logging.
    """

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Actor
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="user"
    )  # user, system, api_key, service

    # Action
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)  # HTTP method
    path: Mapped[str] = mapped_column(String(1024), nullable=False)  # Request path

    # Resource
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Outcome
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default=AuditOutcome.SUCCESS.value)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Context
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Payload (sanitized — no secrets, no PII beyond actor email)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # Before/after for updates

    # Duration
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps — created_at only, no updated_at (immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("idx_audit_tenant_created", "tenant_id", "created_at"),
        Index("idx_audit_actor_created", "actor_id", "created_at"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_resource_type", "resource_type", "resource_id"),
        Index("idx_audit_outcome", "outcome"),
        Index("idx_audit_correlation", "correlation_id"),
    )

    def __repr__(self) -> str:
        return f"<AuditEvent {self.id} {self.action} {self.resource_type}/{self.resource_id}>"
