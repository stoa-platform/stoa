"""SQLAlchemy model for execution logs (CAB-1318)."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ErrorCategory(enum.StrEnum):
    """Error category for execution failures."""

    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    BACKEND = "backend"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    NETWORK = "network"
    CERTIFICATE = "certificate"
    POLICY = "policy"
    CIRCUIT_BREAKER = "circuit_breaker"


class ExecutionStatus(enum.StrEnum):
    """Execution outcome status."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ExecutionLog(Base):
    """Execution log entry for API calls and tool invocations."""

    __tablename__ = "execution_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    consumer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    api_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    # Execution details
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(
            ExecutionStatus,
            values_callable=lambda x: [e.value for e in x],
            name="executionstatus",
            create_type=False,
        ),
        nullable=False,
        default=ExecutionStatus.SUCCESS,
    )
    error_category: Mapped[ErrorCategory | None] = mapped_column(
        Enum(
            ErrorCategory,
            values_callable=lambda x: [e.value for e in x],
            name="errorcategory",
            create_type=False,
        ),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Request/Response metadata (sanitized)
    request_headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_exec_tenant_started", "tenant_id", "started_at"),
        Index("idx_exec_consumer_started", "consumer_id", "started_at"),
        Index("idx_exec_error_category", "error_category", "started_at"),
        Index("idx_exec_status", "status"),
        Index("idx_exec_request_id", "request_id"),
    )
