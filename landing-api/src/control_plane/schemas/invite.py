"""Pydantic schemas for invite endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from control_plane.models.invite import InviteStatus


class InviteCreate(BaseModel):
    """Request schema for creating an invite."""

    email: EmailStr = Field(..., description="Prospect's email address")
    company: str = Field(..., min_length=1, max_length=100, description="Company name")
    source: str | None = Field(
        None,
        max_length=50,
        description="Source of the invite (e.g., 'demo-26-jan')",
    )


class InviteResponse(BaseModel):
    """Invite fields safe to return from list and read endpoints.

    The invite token and link are omitted. They are delivered once, on create.
    """

    id: UUID
    email: str
    company: str
    tenant_id: str
    source: str | None
    status: InviteStatus
    created_at: datetime
    expires_at: datetime
    opened_at: datetime | None = None

    model_config = {"from_attributes": True}


class InviteCreatedResponse(InviteResponse):
    """Create response. Includes the token a single time."""

    token: str
    invite_link: str = Field(..., description="Full URL for the invite")


class InviteListResponse(BaseModel):
    """Response schema for listing invites."""

    invites: list[InviteResponse]
    total: int


class InviteBrief(BaseModel):
    """Brief invite info for quick reference."""

    id: UUID
    email: str
    company: str
    status: InviteStatus
    created_at: datetime

    model_config = {"from_attributes": True}
