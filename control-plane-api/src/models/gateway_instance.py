"""Gateway Instance SQLAlchemy models for multi-gateway orchestration.

Represents a registered gateway (webMethods, Kong, Apigee, STOA, etc.)
that the Control Plane can pilot via the Adapter Pattern (ADR-035).
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum as SQLEnum, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from src.database import Base


class GatewayType(enum.StrEnum):
    """Supported gateway types — each has a corresponding adapter."""

    WEBMETHODS = "webmethods"
    KONG = "kong"
    APIGEE = "apigee"
    AWS_APIGATEWAY = "aws_apigateway"
    AZURE_APIM = "azure_apim"
    GRAVITEE = "gravitee"
    STOA = "stoa"
    # STOA Gateway modes (ADR-024) — for filtering/grouping
    STOA_EDGE_MCP = "stoa_edge_mcp"
    STOA_SIDECAR = "stoa_sidecar"
    STOA_PROXY = "stoa_proxy"
    STOA_SHADOW = "stoa_shadow"


class GatewayInstanceStatus(enum.StrEnum):
    """Health status of a gateway instance."""

    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"


class GatewayInstance(Base):
    """A registered gateway instance pilotable by the Control Plane.

    Each instance represents a specific gateway deployment (e.g. "webmethods-prod")
    with its connection configuration and health status.

    URL semantics (CAB-1953):
        base_url            — Admin API URL used by the Control Plane to pilot this gateway.
        public_url          — Public DNS URL where runtime APIs are served (e.g. https://mcp.gostoa.dev).
        target_gateway_url  — Admin API URL of the third-party gateway managed by Link/Connect.
        ui_url              — Web UI URL of the third-party gateway (e.g. webMethods console at :9072).
    """

    __tablename__ = "gateway_instances"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    name = Column(String(255), unique=True, nullable=False)  # "webmethods-prod"
    display_name = Column(String(255), nullable=False)
    gateway_type = Column(
        SQLEnum(
            GatewayType,
            name="gateway_type_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    environment = Column(String(50), nullable=False, index=True)  # dev / staging / prod
    tenant_id = Column(String(255), nullable=True, index=True)  # null = platform-wide

    # Connection configuration
    base_url = Column(String(500), nullable=False)  # Admin API URL
    target_gateway_url = Column(String(500), nullable=True)  # Third-party gateway URL (for Link/Connect)
    public_url = Column(String(500), nullable=True)  # Public DNS URL for Console display (CAB-1940)
    ui_url = Column(String(500), nullable=True)  # Web UI URL of third-party gateway (CAB-1953)
    auth_config = Column(JSONB, nullable=False, default=dict, server_default="{}")
    # auth_config examples:
    #   {"type": "oidc_proxy", "proxy_url": "https://apis.gostoa.dev/..."}
    #   {"type": "basic", "vault_path": "secret/gateways/webmethods-prod"}
    #   {"type": "api_key", "vault_path": "secret/gateways/kong-prod"}

    # Health
    status = Column(
        SQLEnum(
            GatewayInstanceStatus,
            name="gateway_instance_status_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=GatewayInstanceStatus.OFFLINE,
        server_default="offline",
    )
    last_health_check = Column(DateTime(timezone=True), nullable=True)
    health_details = Column(JSONB, nullable=True)  # Last health check result

    # Capabilities
    capabilities = Column(JSONB, nullable=False, default=list)
    # e.g. ["rest", "graphql", "websocket", "oidc", "rate_limiting", "mcp"]

    # STOA Gateway mode (ADR-024)
    mode = Column(String(50), nullable=True, index=True)  # edge-mcp, sidecar, proxy, shadow

    # Metadata
    version = Column(String(50), nullable=True)  # Gateway software version
    tags = Column(JSONB, nullable=False, default=list, server_default="[]")

    # Operational control (CAB-1979)
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    visibility = Column(JSONB, nullable=True)
    # visibility schema: {"tenant_ids": ["acme", "partner-co"]} — null = visible to all

    # Source of truth tracking (argocd, self_register, manual)
    source = Column(String(50), nullable=False, default="self_register", server_default="self_register")

    # Deletion protection + soft-delete (CAB-1749)
    protected = Column(Boolean, nullable=False, default=False, server_default="false")
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_gw_instances_type_env", "gateway_type", "environment"),)

    def __repr__(self) -> str:
        return f"<GatewayInstance {self.name} type={self.gateway_type} env={self.environment}>"
