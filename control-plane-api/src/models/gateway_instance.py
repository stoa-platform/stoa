"""Gateway Instance SQLAlchemy models for multi-gateway orchestration.

Represents a registered gateway (webMethods, Kong, Apigee, STOA, etc.)
that the Control Plane can pilot via the Adapter Pattern (ADR-027).
"""
import enum
import uuid

from sqlalchemy import Column, DateTime, Enum as SQLEnum, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from src.database import Base


class GatewayType(str, enum.Enum):
    """Supported gateway types — each has a corresponding adapter."""
    WEBMETHODS = "webmethods"
    KONG = "kong"
    APIGEE = "apigee"
    AWS_APIGATEWAY = "aws_apigateway"
    STOA = "stoa"


class GatewayInstanceStatus(str, enum.Enum):
    """Health status of a gateway instance."""
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"


class GatewayInstance(Base):
    """A registered gateway instance pilotable by the Control Plane.

    Each instance represents a specific gateway deployment (e.g. "webmethods-prod")
    with its connection configuration and health status.
    """
    __tablename__ = "gateway_instances"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    name = Column(String(255), unique=True, nullable=False)        # "webmethods-prod"
    display_name = Column(String(255), nullable=False)
    gateway_type = Column(
        SQLEnum(GatewayType, name="gateway_type_enum"),
        nullable=False,
    )
    environment = Column(String(50), nullable=False, index=True)   # dev / staging / prod
    tenant_id = Column(String(255), nullable=True, index=True)     # null = platform-wide

    # Connection configuration
    base_url = Column(String(500), nullable=False)                 # Admin API URL
    auth_config = Column(JSONB, nullable=False, default=dict)
    # auth_config examples:
    #   {"type": "oidc_proxy", "proxy_url": "https://apis.gostoa.dev/..."}
    #   {"type": "basic", "vault_path": "secret/gateways/webmethods-prod"}
    #   {"type": "api_key", "vault_path": "secret/gateways/kong-prod"}

    # Health
    status = Column(
        SQLEnum(GatewayInstanceStatus, name="gateway_instance_status_enum"),
        nullable=False,
        default=GatewayInstanceStatus.OFFLINE,
        server_default="offline",
    )
    last_health_check = Column(DateTime(timezone=True), nullable=True)
    health_details = Column(JSONB, nullable=True)  # Last health check result

    # Capabilities
    capabilities = Column(JSONB, nullable=False, default=list)
    # e.g. ["rest", "graphql", "websocket", "oidc", "rate_limiting", "mcp"]

    # Metadata
    version = Column(String(50), nullable=True)     # Gateway software version
    tags = Column(JSONB, nullable=False, default=list)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index('ix_gw_instances_type_env', 'gateway_type', 'environment'),
    )

    def __repr__(self) -> str:
        return f"<GatewayInstance {self.name} type={self.gateway_type} env={self.environment}>"
