"""Prospect feedback model for NPS tracking.

Stores NPS (Net Promoter Score) feedback from prospects.
Each invite can have at most one feedback submission.
"""
from sqlalchemy import (
    Column,
    String,
    DateTime,
    SmallInteger,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from src.database import Base


class ProspectFeedback(Base):
    """Feedback model for tracking NPS scores from prospects.

    NPS scores follow the standard 1-10 scale:
    - Promoters: 9-10
    - Passives: 7-8
    - Detractors: 1-6
    """
    __tablename__ = "prospect_feedback"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Invite reference (unique - one feedback per invite)
    invite_id = Column(UUID(as_uuid=True), unique=True, nullable=False)

    # NPS Score (1-10)
    nps_score = Column(SmallInteger, nullable=False)

    # Optional comment
    comment = Column(String(500), nullable=True)

    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Constraints
    __table_args__ = (
        CheckConstraint('nps_score >= 1 AND nps_score <= 10', name='ck_prospect_feedback_nps_score_range'),
        Index('ix_prospect_feedback_nps_score', 'nps_score'),
    )

    @property
    def nps_category(self) -> str:
        """Return the NPS category based on score."""
        if self.nps_score >= 9:
            return "promoter"
        elif self.nps_score >= 7:
            return "passive"
        else:
            return "detractor"

    def __repr__(self) -> str:
        return f"<ProspectFeedback score={self.nps_score} invite_id={self.invite_id}>"
