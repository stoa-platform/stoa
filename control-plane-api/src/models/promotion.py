"""Promotion SQLAlchemy model for GitOps promotion flow (CAB-1706)"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.database import Base


class PromotionStatus(enum.StrEnum):
    """Promotion lifecycle status"""

    PENDING = "pending"
    PROMOTING = "promoting"
    PROMOTED = "promoted"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


# Valid promotion chains: only adjacent environments allowed
VALID_PROMOTION_CHAINS: set[tuple[str, str]] = {
    ("dev", "staging"),
    ("staging", "production"),
}


def validate_promotion_chain(source: str, target: str) -> None:
    """Validate that a promotion chain is allowed.

    Raises ValueError if the chain is invalid.
    """
    if source == target:
        raise ValueError(f"Cannot promote to the same environment: {source}")
    if (source, target) not in VALID_PROMOTION_CHAINS:
        allowed = ", ".join(f"{s}→{t}" for s, t in sorted(VALID_PROMOTION_CHAINS))
        raise ValueError(f"Invalid promotion chain: {source}→{target}. " f"Allowed chains: {allowed}")


class Promotion(Base):
    """Promotion record — tracks cross-environment promotions"""

    __tablename__ = "promotions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    api_id = Column(String(255), nullable=False)
    source_environment = Column(String(50), nullable=False)
    target_environment = Column(String(50), nullable=False)
    source_deployment_id = Column(UUID(as_uuid=True), nullable=True)
    target_deployment_id = Column(UUID(as_uuid=True), nullable=True)
    target_gateway_ids = Column(JSONB, nullable=True)
    status = Column(String(50), nullable=False, default=PromotionStatus.PENDING.value)
    spec_diff = Column(JSONB, nullable=True)
    message = Column(Text, nullable=False)
    requested_by = Column(String(255), nullable=False)
    approved_by = Column(String(255), nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_promotions_tenant_api", "tenant_id", "api_id"),
        Index(
            "ix_promotions_api_target_status",
            "api_id",
            "target_environment",
            "status",
        ),
        # Prevent concurrent promotions to the same target for the same API
        Index(
            "uq_promotions_active_per_target",
            "api_id",
            "target_environment",
            unique=True,
            postgresql_where=text("status IN ('pending', 'promoting')"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Promotion {self.id} " f"{self.source_environment}→{self.target_environment} " f"status={self.status}>"
