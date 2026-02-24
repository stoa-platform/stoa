"""UsageRecord SQLAlchemy model for aggregated metering data (CAB-1334 Phase 1)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class UsageRecord(Base):
    """Stores aggregated usage metrics per tenant/tool/period.

    Records are upserted by the metering pipeline (Kafka consumer or batch job).
    Queried by the /v1/metering endpoints for admin dashboards.
    """

    __tablename__ = "usage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    tool_name = Column(String(255), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    period_type = Column(String(20), nullable=False)  # "hourly", "daily", "monthly"
    request_count = Column(Integer, nullable=False, default=0)
    token_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    avg_latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "tool_name",
            "period_start",
            "period_type",
            name="uq_usage_tenant_tool_period",
        ),
        Index("ix_usage_tenant_period", "tenant_id", "period_type", "period_start"),
    )

    def __repr__(self) -> str:
        return (
            f"<UsageRecord {self.id} tenant={self.tenant_id} "
            f"tool={self.tool_name} period={self.period_type}>"
        )
