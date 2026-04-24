"""Pydantic schemas for gateway instance and deployment endpoints."""

import logging
from datetime import datetime
from typing import Literal, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

# CAB-2159 BUG-2 — narrowed enums so the UI can branch on exact values rather
# than carrying wire/UI adapter casts. Keep synchronized with:
#   - src/models/gateway_instance.py:GatewayType (regression: test_gateway_type_literal_matches_orm)
#   - src/models/gateway_instance.py:GatewayInstanceStatus
#   - src/models/gateway_instance.py:source column
#   - ADR-024 (Gateway 4-mode split)
GatewayTypeLiteral = Literal[
    "webmethods",
    "kong",
    "apigee",
    "aws_apigateway",
    "azure_apim",
    "gravitee",
    "stoa",
    "stoa_edge_mcp",
    "stoa_sidecar",
    "stoa_proxy",
    "stoa_shadow",
]
GatewayModeLiteral = Literal["edge-mcp", "sidecar", "proxy", "shadow", "connect"]
GatewayStatusLiteral = Literal["online", "offline", "degraded", "maintenance"]
GatewaySourceLiteral = Literal["argocd", "self_register", "manual"]

# =========================================================================
# Gateway Instance Schemas
# =========================================================================


class GatewayInstanceCreate(BaseModel):
    """Schema for creating a new gateway instance."""

    name: str = Field(..., max_length=255, description="Unique identifier (e.g. 'webmethods-prod')")
    display_name: str = Field(..., max_length=255)
    gateway_type: str = Field(..., description="webmethods, kong, apigee, aws_apigateway, stoa")
    environment: str = Field(..., max_length=50, description="dev, staging, prod")
    tenant_id: str | None = Field(None, max_length=255, description="null = platform-wide")
    base_url: str = Field(..., max_length=500, description="Admin API URL")
    auth_config: dict = Field(default_factory=dict, description="Auth config: {type, vault_path, ...}")
    capabilities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class GatewayInstanceUpdate(BaseModel):
    """Schema for updating a gateway instance."""

    display_name: str | None = Field(None, max_length=255)
    base_url: str | None = Field(None, max_length=500)
    auth_config: dict | None = None
    capabilities: list[str] | None = None
    tags: list[str] | None = None
    environment: str | None = Field(None, max_length=50)
    protected: bool | None = Field(None, description="Toggle deletion protection")
    enabled: bool | None = Field(None, description="Enable/disable gateway for deployments")
    visibility: dict | None = Field(None, description="Restrict visibility to specific tenants (null = all)")


class GatewayVisibility(BaseModel):
    """Visibility restriction for a gateway instance."""

    tenant_ids: list[str] = Field(..., min_length=1, description="Tenant IDs that can see this gateway")


class GatewayInstanceResponse(BaseModel):
    """Schema for gateway instance in API responses."""

    id: UUID
    name: str
    display_name: str
    gateway_type: GatewayTypeLiteral
    environment: str
    tenant_id: str | None
    base_url: str
    target_gateway_url: str | None = Field(
        None, description="URL of the third-party gateway managed by this Link/Connect instance"
    )
    public_url: str | None = Field(None, description="Public DNS URL of this gateway (e.g. https://mcp.gostoa.dev)")
    ui_url: str | None = Field(
        None, description="Web UI URL of the third-party gateway (e.g. webMethods console at :9072)"
    )
    auth_config: dict
    status: GatewayStatusLiteral
    last_health_check: datetime | None
    health_details: dict | None
    capabilities: list[str]
    version: str | None
    tags: list[str]
    mode: GatewayModeLiteral | None = Field(
        None, description="STOA Gateway mode: edge-mcp, sidecar, proxy, shadow, connect"
    )
    protected: bool = Field(False, description="Whether this gateway is protected from deletion")
    enabled: bool = Field(True, description="Whether this gateway accepts deployments and syncs")
    visibility: dict | None = Field(None, description="Visibility restriction: {tenant_ids: [...]} or null (all)")
    source: GatewaySourceLiteral = Field(
        "self_register",
        description="Source of truth for this gateway entry — argocd (GitOps-managed), "
        "self_register (auto-announced via /v1/gateways/register) or manual (admin CLI)",
    )
    deleted_at: datetime | None = Field(None, description="Soft-delete timestamp (null = active)")
    deleted_by: str | None = Field(None, description="User ID who deleted this gateway")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("capabilities", "tags", mode="before")
    @classmethod
    def coerce_to_list(cls, v: object) -> list[str]:
        """Handle JSONB columns that may be stored as dict instead of list."""
        if isinstance(v, dict):
            return [k for k, val in v.items() if val]
        if v is None:
            return []
        if not isinstance(v, list):
            return [str(v)]
        return list(v)

    @field_validator("mode", mode="before")
    @classmethod
    def coerce_mode(cls, v: object) -> str | None:
        """Coerce unknown ``mode`` values to ``None`` instead of 500ing the response.

        ``mode`` is a free-form ``String(50)`` on the ORM (`models/gateway_instance.py:105`),
        so drift between stored values and the Literal whitelist is possible. A bad row
        must not nuke the whole list endpoint — log + return ``None`` so the UI can
        surface the other gateways.
        """
        if v is None or v == "":
            return None
        if v in get_args(GatewayModeLiteral):
            return v  # type: ignore[return-value]
        logger.warning("Unknown gateway mode %r — coerced to None. Update GatewayModeLiteral if this is valid.", v)
        return None

    @field_validator("source", mode="before")
    @classmethod
    def coerce_source(cls, v: object) -> str:
        """Coerce unknown ``source`` values to ``"manual"`` instead of 500ing.

        ``source`` is a free-form ``String(50)`` on the ORM with a ``self_register``
        default. Unknown values (drift, manual inserts) fall back to ``"manual"``.
        """
        if v in get_args(GatewaySourceLiteral):
            return v  # type: ignore[return-value]
        logger.warning(
            "Unknown gateway source %r — coerced to 'manual'. Update GatewaySourceLiteral if this is valid.", v
        )
        return "manual"


class GatewayHealthCheckResponse(BaseModel):
    """Schema for health check result."""

    status: str
    details: dict | None = None
    gateway_name: str
    gateway_type: str


# =========================================================================
# Gateway Mode Statistics (ADR-024)
# =========================================================================


class ModeStatItem(BaseModel):
    """Statistics for a single gateway mode."""

    mode: str
    total: int
    online: int
    offline: int
    degraded: int


class GatewayModeStats(BaseModel):
    """Gateway statistics grouped by mode."""

    modes: list[ModeStatItem]
    total_gateways: int


# =========================================================================
# Gateway Deployment Schemas
# =========================================================================


class GatewayDeploymentCreate(BaseModel):
    """Schema for deploying an API to gateway(s)."""

    api_catalog_id: UUID
    gateway_instance_ids: list[UUID] = Field(..., min_length=1)


class GatewayDeploymentResponse(BaseModel):
    """Schema for deployment in API responses."""

    id: UUID
    api_catalog_id: UUID
    gateway_instance_id: UUID
    desired_state: dict
    desired_at: datetime
    actual_state: dict | None = None
    actual_at: datetime | None = None
    sync_status: str
    last_sync_attempt: datetime | None = None
    last_sync_success: datetime | None = None
    sync_error: str | None = None
    sync_attempts: int
    sync_steps: list[dict] | None = None
    gateway_resource_id: str | None = None
    created_at: datetime
    updated_at: datetime
    # Joined from GatewayInstance (populated by list queries, absent on single-object endpoints)
    gateway_name: str | None = None
    gateway_display_name: str | None = None
    gateway_type: str | None = None
    gateway_environment: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DeploymentStatusSummary(BaseModel):
    """Sync status counts for the dashboard."""

    pending: int = 0
    syncing: int = 0
    synced: int = 0
    drifted: int = 0
    error: int = 0
    deleting: int = 0
    total: int = 0


# =========================================================================
# Pagination
# =========================================================================


class PaginatedGatewayInstances(BaseModel):
    """Paginated list of gateway instances."""

    items: list[GatewayInstanceResponse]
    total: int
    page: int
    page_size: int


class PaginatedGatewayDeployments(BaseModel):
    """Paginated list of gateway deployments."""

    items: list[GatewayDeploymentResponse]
    total: int
    page: int
    page_size: int
