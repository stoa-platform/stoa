"""Pydantic schemas for tenant tool permissions (CAB-1980)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TenantToolPermissionCreate(BaseModel):
    """Request body for creating/updating a tool permission."""

    mcp_server_id: UUID
    tool_name: str = Field(..., min_length=1, max_length=255)
    allowed: bool = True


class TenantToolPermissionResponse(BaseModel):
    """Response schema for a tool permission."""

    id: UUID
    tenant_id: str
    mcp_server_id: UUID
    tool_name: str
    allowed: bool
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TenantToolPermissionListResponse(BaseModel):
    """Paginated list of tool permissions."""

    items: list[TenantToolPermissionResponse]
    total: int
    page: int
    page_size: int
