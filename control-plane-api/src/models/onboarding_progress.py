"""Onboarding progress model for zero-touch trial (CAB-1325)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.database import Base


class OnboardingProgress(Base):
    """Tracks developer onboarding steps for TTFTC measurement.

    steps_completed is JSONB: {"choose_use_case": "2026-02-20T14:00", ...}
    Flexible schema — no migration needed for new steps.
    """

    __tablename__ = "onboarding_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    steps_completed = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime, nullable=True)
    ttftc_seconds = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_onboarding_tenant_user"),
    )

    def __repr__(self) -> str:
        return f"<OnboardingProgress {self.id} tenant={self.tenant_id} user={self.user_id}>"
