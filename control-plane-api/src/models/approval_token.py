"""Single-use MCP approval token store (CAB-2227 / ADR-067)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ApprovalTokenStatus(enum.StrEnum):
    ISSUED = "issued"
    CONSUMED = "consumed"
    EXPIRED = "expired"


class ApprovalToken(Base):
    __tablename__ = "approval_tokens"

    jti: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(512), nullable=False)
    tool_call_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(128), nullable=False)
    requester_actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    approver_actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ApprovalTokenStatus.ISSUED.value)

    __table_args__ = (
        Index("idx_approval_tokens_tenant_status", "tenant_id", "status"),
        Index("idx_approval_tokens_expires_at", "expires_at"),
    )
