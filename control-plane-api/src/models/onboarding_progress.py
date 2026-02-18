"""Onboarding progress model — tracks zero-touch trial flow (CAB-1325)."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from ..database import Base


class OnboardingProgress(Base):
    """Tracks per-user onboarding progress with flexible JSONB step tracking."""

    __tablename__ = "onboarding_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    steps_completed = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    ttftc_seconds = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_onboarding_tenant_user"),
    )
