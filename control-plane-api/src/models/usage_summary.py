"""UsageSummary SQLAlchemy model for aggregated metering data (CAB-1334 Phase 1)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Enum, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class UsageSummary(Base):
    """Aggregated usage metrics per API/consumer/tenant, bucketed by period (daily/monthly)."""

    __tablename__ = "usage_summaries"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dimensions
    tenant_id = Column(String(255), nullable=False)
    api_id = Column(UUID(as_uuid=True), nullable=False)
    consumer_id = Column(UUID(as_uuid=True), nullable=True)
    period = Column(
        Enum("daily", "monthly", name="usage_period_enum", create_type=True),
        nullable=False,
    )
    period_start = Column(DateTime, nullable=False)

    # Counters
    request_count = Column(BigInteger, nullable=False, default=0)
    error_count = Column(BigInteger, nullable=False, default=0)

    # Latency metrics
    total_latency_ms = Column(BigInteger, nullable=False, default=0)
    p99_latency_ms = Column(Integer, nullable=True)

    # Token usage (for LLM/MCP tool calls)
    total_tokens = Column(BigInteger, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes for common query patterns
    __table_args__ = (
        Index(
            "ix_usage_summaries_tenant_api_period",
            "tenant_id",
            "api_id",
            "period",
            "period_start",
        ),
        Index("ix_usage_summaries_tenant_id", "tenant_id"),
        Index("ix_usage_summaries_api_id", "api_id"),
        Index("ix_usage_summaries_period_start", "period_start"),
    )

    def __repr__(self) -> str:
        return (
            f"<UsageSummary {self.id} tenant={self.tenant_id} "
            f"api={self.api_id} period={self.period} requests={self.request_count}>"
        )
