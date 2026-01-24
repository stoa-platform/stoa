"""SQLAlchemy Model for MCP Error Snapshots.

Database model for storing error snapshots with full context for debugging.

Reference: CAB-397 - Error Snapshot / Flight Recorder (Time-Travel Debugging)
"""

import enum
from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import (
    DateTime,
    Enum,
    Integer,
    Float,
    String,
    Text,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .subscription import Base


class ResolutionStatus(str, enum.Enum):
    """Resolution status values.

    Inherits from str to ensure PostgreSQL receives lowercase values.
    """
    UNRESOLVED = "unresolved"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ErrorSnapshotModel(Base):
    """MCP Error Snapshot database model.

    Stores error snapshots with full context for time-travel debugging.
    """

    __tablename__ = "mcp_error_snapshots"

    # Primary key - matches the Pydantic model ID format
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Error classification
    error_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False, default=500, index=True)

    # Request context (extracted for filtering)
    request_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    request_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # User context (extracted for filtering)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # MCP context (extracted for filtering)
    mcp_server_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # LLM context (extracted for analytics)
    llm_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    llm_tokens_input: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    llm_tokens_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Cost tracking
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tokens_wasted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Retry context
    retry_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Tracing
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Resolution workflow
    resolution_status: Mapped[ResolutionStatus] = mapped_column(
        Enum(ResolutionStatus, values_callable=lambda x: [e.value for e in x], name="resolutionstatus", create_type=False),
        nullable=False,
        default=ResolutionStatus.UNRESOLVED,
        index=True,
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Full snapshot data as JSONB for complete context
    snapshot_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Indexes for common queries
    __table_args__ = (
        Index("ix_mcp_snapshots_timestamp_desc", timestamp.desc()),
        Index("ix_mcp_snapshots_tenant_timestamp", "tenant_id", timestamp.desc()),
        Index("ix_mcp_snapshots_server_timestamp", "mcp_server_name", timestamp.desc()),
        Index("ix_mcp_snapshots_tool_timestamp", "tool_name", timestamp.desc()),
        Index("ix_mcp_snapshots_error_type_timestamp", "error_type", timestamp.desc()),
        Index("ix_mcp_snapshots_status_timestamp", "response_status", timestamp.desc()),
        Index("ix_mcp_snapshots_resolution", "resolution_status", timestamp.desc()),
    )

    @classmethod
    def from_pydantic(cls, snapshot) -> "ErrorSnapshotModel":
        """Create from Pydantic MCPErrorSnapshot model."""
        # Extract nested fields for filtering
        user_id = snapshot.user.user_id if snapshot.user else None
        tenant_id = snapshot.user.tenant_id if snapshot.user else None
        mcp_server_name = snapshot.mcp_server.name if snapshot.mcp_server else None
        tool_name = snapshot.tool_invocation.tool_name if snapshot.tool_invocation else None
        llm_provider = snapshot.llm_context.provider if snapshot.llm_context else None
        llm_model = snapshot.llm_context.model if snapshot.llm_context else None
        llm_tokens_input = snapshot.llm_context.tokens_input if snapshot.llm_context else None
        llm_tokens_output = snapshot.llm_context.tokens_output if snapshot.llm_context else None
        retry_attempts = snapshot.retry_context.attempts if snapshot.retry_context else 1
        retry_max_attempts = snapshot.retry_context.max_attempts if snapshot.retry_context else 3

        return cls(
            id=snapshot.id,
            timestamp=snapshot.timestamp,
            error_type=snapshot.error_type.value,
            error_message=snapshot.error_message,
            error_code=snapshot.error_code,
            response_status=snapshot.response_status,
            request_method=snapshot.request.method,
            request_path=snapshot.request.path,
            user_id=user_id,
            tenant_id=tenant_id,
            mcp_server_name=mcp_server_name,
            tool_name=tool_name,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_tokens_input=llm_tokens_input,
            llm_tokens_output=llm_tokens_output,
            total_cost_usd=snapshot.total_cost_usd,
            tokens_wasted=snapshot.tokens_wasted,
            retry_attempts=retry_attempts,
            retry_max_attempts=retry_max_attempts,
            trace_id=snapshot.trace_id,
            conversation_id=snapshot.conversation_id,
            snapshot_data=snapshot.model_dump(mode="json"),
        )

    def to_summary_dict(self) -> dict:
        """Convert to summary dictionary for list responses."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "error_type": self.error_type,
            "error_message": self.error_message[:200] + "..." if len(self.error_message) > 200 else self.error_message,
            "response_status": self.response_status,
            "mcp_server_name": self.mcp_server_name,
            "tool_name": self.tool_name,
            "total_cost_usd": self.total_cost_usd,
            "tokens_wasted": self.tokens_wasted,
            "resolution_status": self.resolution_status.value,
        }

    def to_full_dict(self) -> dict:
        """Convert to full dictionary with complete snapshot data."""
        return {
            **self.to_summary_dict(),
            "error_code": self.error_code,
            "request_method": self.request_method,
            "request_path": self.request_path,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_tokens_input": self.llm_tokens_input,
            "llm_tokens_output": self.llm_tokens_output,
            "retry_attempts": self.retry_attempts,
            "retry_max_attempts": self.retry_max_attempts,
            "trace_id": self.trace_id,
            "conversation_id": self.conversation_id,
            "resolution_notes": self.resolution_notes,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            # Include full snapshot data
            "snapshot": self.snapshot_data,
        }

    def __repr__(self) -> str:
        return f"<ErrorSnapshot {self.id} type={self.error_type} status={self.response_status}>"
