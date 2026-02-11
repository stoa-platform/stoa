"""Access request model for portal email capture.

Stores email + company from unauthenticated visitors who want
early access to the STOA Developer Portal.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class AccessRequest(Base):
    """Email capture from unauthenticated portal visitors."""

    __tablename__ = "access_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    source = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("email", name="uq_access_requests_email"),
        Index("ix_access_requests_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AccessRequest email={self.email} status={self.status}>"
