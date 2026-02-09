"""QuotaUsage SQLAlchemy model for daily/monthly request tracking (CAB-1121 Phase 4)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class QuotaUsage(Base):
    """Tracks daily and monthly request/bandwidth counters per consumer."""

    __tablename__ = "quota_usage"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # References
    consumer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("consumers.id", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    tenant_id = Column(String(255), nullable=False)

    # Request counters
    request_count_daily = Column(Integer, nullable=False, default=0)
    request_count_monthly = Column(Integer, nullable=False, default=0)

    # Bandwidth counters
    bandwidth_bytes_daily = Column(BigInteger, nullable=False, default=0)
    bandwidth_bytes_monthly = Column(BigInteger, nullable=False, default=0)

    # Period markers
    period_start_daily = Column(Date, nullable=False)
    period_start_monthly = Column(Date, nullable=False)

    # Timestamps
    last_reset_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index(
            "ix_quota_usage_consumer_tenant_daily",
            "consumer_id",
            "tenant_id",
            "period_start_daily",
            unique=True,
        ),
        Index("ix_quota_usage_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<QuotaUsage {self.id} consumer={self.consumer_id} "
            f"daily={self.request_count_daily} monthly={self.request_count_monthly}>"
        )
