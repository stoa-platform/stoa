"""Pydantic schemas for gateway policy endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GatewayPolicyCreate(BaseModel):
    """Schema for creating a new gateway policy."""
    name: str = Field(..., max_length=255)
    description: str | None = None
    policy_type: str = Field(..., description="cors, rate_limit, jwt_validation, ip_filter, logging, caching, transform")
    tenant_id: str | None = Field(None, max_length=255, description="null = platform-wide")
    scope: str = Field("api", description="api, gateway, tenant")
    config: dict = Field(default_factory=dict)
    priority: int = Field(100, ge=0, le=10000)
    enabled: bool = True


class GatewayPolicyUpdate(BaseModel):
    """Schema for updating a gateway policy."""
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    config: dict | None = None
    priority: int | None = Field(None, ge=0, le=10000)
    enabled: bool | None = None


class GatewayPolicyResponse(BaseModel):
    """Schema for policy in API responses."""
    id: UUID
    name: str
    description: str | None
    policy_type: str
    tenant_id: str | None
    scope: str
    config: dict
    priority: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
    binding_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class PolicyBindingCreate(BaseModel):
    """Schema for creating a policy binding."""
    policy_id: UUID
    api_catalog_id: UUID | None = None
    gateway_instance_id: UUID | None = None
    tenant_id: str | None = Field(None, max_length=255)
    enabled: bool = True


class PolicyBindingResponse(BaseModel):
    """Schema for policy binding in API responses."""
    id: UUID
    policy_id: UUID
    api_catalog_id: UUID | None
    gateway_instance_id: UUID | None
    tenant_id: str | None
    enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
