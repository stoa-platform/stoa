import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AuditChainHead(Base):
    __tablename__ = "audit_chain_heads"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_row_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    last_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class PseudonymizedAuditErasure(Base):
    __tablename__ = "pseudonymized_audit_erasures"

    erasure_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    legal_basis: Mapped[str] = mapped_column(Text, nullable=False)
    dpo_approver_id: Mapped[str] = mapped_column(String(255), nullable=False)
    dpo_approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subject_external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    pseudonymization_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    scope_actor_ids: Mapped[list[str]] = mapped_column(ARRAY(String(255)), nullable=False, default=list)
    scope_event_ids: Mapped[list[str]] = mapped_column(ARRAY(String(36)), nullable=False, default=list)
    redaction_map: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AuditEventRedactedView(Base):
    __tablename__ = "audit_events_redacted"
    __table_args__ = {"info": {"is_view": True}}

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
