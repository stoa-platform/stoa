"""Pydantic schemas for gateway instance and deployment endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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


class GatewayInstanceResponse(BaseModel):
    """Schema for gateway instance in API responses."""
    id: UUID
    name: str
    display_name: str
    gateway_type: str
    environment: str
    tenant_id: str | None
    base_url: str
    auth_config: dict
    status: str
    last_health_check: datetime | None
    health_details: dict | None
    capabilities: list[str]
    version: str | None
    tags: list[str]
    mode: str | None = Field(None, description="STOA Gateway mode: edge-mcp, sidecar, proxy, shadow")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    actual_state: dict | None
    actual_at: datetime | None
    sync_status: str
    last_sync_attempt: datetime | None
    last_sync_success: datetime | None
    sync_error: str | None
    sync_attempts: int
    gateway_resource_id: str | None
    created_at: datetime
    updated_at: datetime

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
