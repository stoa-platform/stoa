# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
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
    """Response schema for invite operations."""

    id: UUID
    email: str
    company: str
    token: str
    source: str | None
    status: InviteStatus
    invite_link: str = Field(..., description="Full URL for the invite")
    created_at: datetime
    expires_at: datetime
    opened_at: datetime | None = None

    model_config = {"from_attributes": True}


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
