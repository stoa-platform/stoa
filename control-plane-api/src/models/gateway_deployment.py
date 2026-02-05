"""Gateway Deployment SQLAlchemy models for desired vs actual state tracking.

Links an API catalog entry to a gateway instance, tracking synchronization
status between what the Control Plane wants (desired_state) and what the
gateway actually has (actual_state). Used by the Sync Engine for
reconciliation.
"""
import enum
import uuid

from sqlalchemy import Column, DateTime, Enum as SQLEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from src.database import Base


class DeploymentSyncStatus(str, enum.Enum):
    """Synchronization status of a gateway deployment."""
    PENDING = "pending"       # Desired state set, not yet synced
    SYNCING = "syncing"       # Sync in progress
    SYNCED = "synced"         # Desired == actual
    DRIFTED = "drifted"       # Actual != desired (detected by reconciler)
    ERROR = "error"           # Last sync attempt failed
    DELETING = "deleting"     # Marked for removal from gateway


class GatewayDeployment(Base):
    """Junction table linking an API catalog entry to a gateway instance.

    Tracks the desired state (what the Control Plane wants) vs actual state
    (what the gateway reports), enabling drift detection and reconciliation.
    """
    __tablename__ = "gateway_deployments"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # References
    api_catalog_id = Column(
        UUID(as_uuid=True),
        ForeignKey("api_catalog.id", ondelete="CASCADE"),
        nullable=False,
    )
    gateway_instance_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_instances.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Desired state (what the Control Plane wants on this gateway)
    desired_state = Column(JSONB, nullable=False, default=dict)
    # Example: {"spec_hash": "abc123", "version": "2.0", "policies": ["rate-limit-100"], "activated": true}
    desired_at = Column(DateTime(timezone=True), nullable=False)

    # Actual state (what the gateway reports)
    actual_state = Column(JSONB, nullable=True)
    # Example: {"gateway_api_id": "xyz", "spec_hash": "abc123", "activated": true}
    actual_at = Column(DateTime(timezone=True), nullable=True)

    # Sync tracking
    sync_status = Column(
        SQLEnum(DeploymentSyncStatus, name="deployment_sync_status_enum"),
        nullable=False,
        default=DeploymentSyncStatus.PENDING,
        server_default="pending",
    )
    last_sync_attempt = Column(DateTime(timezone=True), nullable=True)
    last_sync_success = Column(DateTime(timezone=True), nullable=True)
    sync_error = Column(Text, nullable=True)
    sync_attempts = Column(Integer, nullable=False, default=0, server_default="0")

    # Gateway-side resource ID (assigned by the gateway when the API is registered)
    gateway_resource_id = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint('api_catalog_id', 'gateway_instance_id', name='uq_deployment_api_gateway'),
        Index('ix_gw_deploy_sync_status', 'sync_status'),
        Index('ix_gw_deploy_gateway', 'gateway_instance_id'),
        Index('ix_gw_deploy_api', 'api_catalog_id'),
    )

    def __repr__(self) -> str:
        return (
            f"<GatewayDeployment api={self.api_catalog_id} "
            f"gw={self.gateway_instance_id} status={self.sync_status}>"
        )
