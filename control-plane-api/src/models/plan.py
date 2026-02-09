"""Plan SQLAlchemy model for subscription plans with quota definitions."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum as SQLEnum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from src.database import Base


class PlanStatus(enum.StrEnum):
    """Plan status enum."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class Plan(Base):
    """Plan model - defines subscription plans with quotas (Bronze/Silver/Gold)."""

    __tablename__ = "plans"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    slug = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Tenant (the API provider who defines this plan)
    tenant_id = Column(String(255), nullable=False, index=True)

    # Quotas
    rate_limit_per_second = Column(Integer, nullable=True)
    rate_limit_per_minute = Column(Integer, nullable=True)
    daily_request_limit = Column(Integer, nullable=True)
    monthly_request_limit = Column(Integer, nullable=True)
    burst_limit = Column(Integer, nullable=True)

    # Approval workflow
    requires_approval = Column(Boolean, nullable=False, default=False)
    auto_approve_roles = Column(JSON, nullable=True)

    # Status
    status = Column(
        SQLEnum(PlanStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PlanStatus.ACTIVE,
    )

    # Pricing (metadata, not enforced by platform)
    pricing_metadata = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Audit
    created_by = Column(String(255), nullable=True)

    # Indexes
    __table_args__ = (
        Index("ix_plans_tenant_slug", "tenant_id", "slug", unique=True),
        Index("ix_plans_tenant_status", "tenant_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Plan {self.id} slug={self.slug} tenant={self.tenant_id}>"
