"""Pydantic schemas for plan endpoints (CAB-1121)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlanStatusEnum(StrEnum):
    """Plan status enum for API responses."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class PlanCreate(BaseModel):
    """Schema for creating a new subscription plan."""

    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    rate_limit_per_second: int | None = Field(None, ge=0)
    rate_limit_per_minute: int | None = Field(None, ge=0)
    daily_request_limit: int | None = Field(None, ge=0)
    monthly_request_limit: int | None = Field(None, ge=0)
    burst_limit: int | None = Field(None, ge=0)
    requires_approval: bool = False
    auto_approve_roles: list[str] | None = None
    pricing_metadata: dict | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "slug": "gold",
                "name": "Gold Plan",
                "description": "High-volume plan for production workloads",
                "rate_limit_per_second": 100,
                "rate_limit_per_minute": 5000,
                "daily_request_limit": 1000000,
                "monthly_request_limit": 30000000,
                "requires_approval": True,
            }
        }
    )


class PlanUpdate(BaseModel):
    """Schema for updating an existing plan."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    rate_limit_per_second: int | None = Field(None, ge=0)
    rate_limit_per_minute: int | None = Field(None, ge=0)
    daily_request_limit: int | None = Field(None, ge=0)
    monthly_request_limit: int | None = Field(None, ge=0)
    burst_limit: int | None = Field(None, ge=0)
    requires_approval: bool | None = None
    auto_approve_roles: list[str] | None = None
    pricing_metadata: dict | None = None
    status: PlanStatusEnum | None = None


class PlanResponse(BaseModel):
    """Schema for plan response."""

    id: UUID
    slug: str
    name: str
    description: str | None
    tenant_id: str
    rate_limit_per_second: int | None
    rate_limit_per_minute: int | None
    daily_request_limit: int | None
    monthly_request_limit: int | None
    burst_limit: int | None
    requires_approval: bool
    auto_approve_roles: list[str] | None
    status: PlanStatusEnum
    pricing_metadata: dict | None
    created_at: datetime
    updated_at: datetime
    created_by: str | None

    model_config = ConfigDict(from_attributes=True)


class PlanListResponse(BaseModel):
    """Schema for paginated plan list."""

    items: list[PlanResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
