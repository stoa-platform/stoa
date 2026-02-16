"""Deployment SQLAlchemy model for deployment lifecycle tracking (CAB-1353)"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class DeploymentStatus(enum.StrEnum):
    """Deployment status values"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class Environment(enum.StrEnum):
    """Deployment environment"""
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


class Deployment(Base):
    """Deployment record — tracks each deployment attempt"""
    __tablename__ = "deployments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    api_id = Column(String(255), nullable=False)
    api_name = Column(String(255), nullable=False, default="")
    environment = Column(String(50), nullable=False)
    version = Column(String(100), nullable=False, default="1.0.0")
    status = Column(String(50), nullable=False, default=DeploymentStatus.PENDING.value)
    deployed_by = Column(String(255), nullable=False)
    gateway_id = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    spec_hash = Column(String(64), nullable=True)
    commit_sha = Column(String(40), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    rollback_of = Column(UUID(as_uuid=True), nullable=True)
    rollback_version = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_deployments_tenant_api", "tenant_id", "api_id"),
        Index("ix_deployments_tenant_env", "tenant_id", "environment"),
        Index("ix_deployments_tenant_status", "tenant_id", "status"),
        Index("ix_deployments_tenant_created", "tenant_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Deployment {self.id} api={self.api_id} env={self.environment} status={self.status}>"
