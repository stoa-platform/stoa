"""Deployment log model — stores log entries per deployment (CAB-1420)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class LogLevel(enum.StrEnum):
    """Log severity level."""

    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    DEBUG = "debug"


class DeploymentLog(Base):
    """A single log entry within a deployment lifecycle."""

    __tablename__ = "deployment_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deployments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(String(255), nullable=False, index=True)
    seq = Column(Integer, nullable=False, default=0)
    level = Column(String(10), nullable=False, default=LogLevel.INFO.value)
    step = Column(String(100), nullable=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("ix_deployment_logs_deploy_seq", "deployment_id", "seq"),)

    def __repr__(self) -> str:
        return f"<DeploymentLog {self.id} deploy={self.deployment_id} seq={self.seq}>"
