"""API Gateway Assignment model — default gateway targets per API/environment (CAB-1888).

Maps an API to its default gateway targets for each environment,
enabling auto-deploy on promotion and pre-filling the deploy modal.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from src.database import Base


class ApiGatewayAssignment(Base):
    """Default gateway target for an API in a given environment.

    When auto_deploy=True and the API is promoted to this environment,
    the DeploymentOrchestrationService automatically creates GatewayDeployment
    records and triggers the SyncEngine.
    """

    __tablename__ = "api_gateway_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_id = Column(
        UUID(as_uuid=True),
        ForeignKey("api_catalog.id", ondelete="CASCADE"),
        nullable=False,
    )
    gateway_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    environment = Column(String(50), nullable=False)  # dev / staging / production
    auto_deploy = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("api_id", "gateway_id", "environment", name="uq_api_gateway_env"),
        Index("ix_api_gw_assign_api_env", "api_id", "environment"),
        Index("ix_api_gw_assign_gateway", "gateway_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ApiGatewayAssignment api={self.api_id} gw={self.gateway_id} "
            f"env={self.environment} auto={self.auto_deploy}>"
        )
