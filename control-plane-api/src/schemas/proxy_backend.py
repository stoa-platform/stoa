"""Pydantic schemas for proxy backend endpoints (CAB-1725)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProxyBackendAuthTypeEnum(StrEnum):
    """Authentication type for API responses."""

    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2_CC = "oauth2_cc"


class ProxyBackendStatusEnum(StrEnum):
    """Backend status for API responses."""

    ACTIVE = "active"
    DISABLED = "disabled"


class ProxyBackendCreate(BaseModel):
    """Schema for registering a new proxy backend."""

    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str | None = Field(None, max_length=255)
    description: str | None = None
    base_url: str = Field(..., min_length=1, max_length=2048)
    health_endpoint: str | None = Field(None, max_length=512)
    auth_type: ProxyBackendAuthTypeEnum = ProxyBackendAuthTypeEnum.API_KEY
    credential_ref: str | None = Field(None, max_length=255)
    rate_limit_rpm: int = Field(0, ge=0)
    circuit_breaker_enabled: bool = True
    fallback_direct: bool = False
    timeout_secs: int = Field(30, ge=1, le=300)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "n8n",
                "display_name": "n8n Workflow Automation",
                "base_url": "https://n8n.gostoa.dev",
                "health_endpoint": "/healthz",
                "auth_type": "api_key",
                "credential_ref": "api-proxy:n8n",
                "rate_limit_rpm": 60,
            }
        }
    )


class ProxyBackendUpdate(BaseModel):
    """Schema for updating an existing proxy backend."""

    display_name: str | None = Field(None, max_length=255)
    description: str | None = None
    base_url: str | None = Field(None, min_length=1, max_length=2048)
    health_endpoint: str | None = Field(None, max_length=512)
    auth_type: ProxyBackendAuthTypeEnum | None = None
    credential_ref: str | None = Field(None, max_length=255)
    rate_limit_rpm: int | None = Field(None, ge=0)
    circuit_breaker_enabled: bool | None = None
    fallback_direct: bool | None = None
    timeout_secs: int | None = Field(None, ge=1, le=300)
    is_active: bool | None = None


class ProxyBackendResponse(BaseModel):
    """Schema for proxy backend response."""

    id: UUID
    name: str
    display_name: str | None
    description: str | None
    base_url: str
    health_endpoint: str | None
    auth_type: ProxyBackendAuthTypeEnum
    credential_ref: str | None
    rate_limit_rpm: int
    circuit_breaker_enabled: bool
    fallback_direct: bool
    timeout_secs: int
    status: ProxyBackendStatusEnum
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProxyBackendHealthStatus(BaseModel):
    """Health check result for a proxy backend."""

    backend_name: str
    healthy: bool
    status_code: int | None = None
    latency_ms: float | None = None
    error: str | None = None
    checked_at: datetime


class ProxyBackendListResponse(BaseModel):
    """Schema for paginated proxy backend list."""

    items: list[ProxyBackendResponse]
    total: int
