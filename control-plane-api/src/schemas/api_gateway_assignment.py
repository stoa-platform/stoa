"""Pydantic schemas for API Gateway Assignments (CAB-1888)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    """Create a default gateway target for an API/environment."""

    gateway_id: UUID
    environment: str = Field(pattern="^(dev|staging|production)$")
    auto_deploy: bool = False


class AssignmentResponse(BaseModel):
    """API gateway assignment response."""

    id: UUID
    api_id: UUID
    gateway_id: UUID
    environment: str
    auto_deploy: bool
    created_at: datetime

    # Joined fields (populated by list queries)
    gateway_name: str | None = None
    gateway_display_name: str | None = None
    gateway_type: str | None = None

    model_config = {"from_attributes": True}


class AssignmentListResponse(BaseModel):
    """Paginated assignment list."""

    items: list[AssignmentResponse]
    total: int
