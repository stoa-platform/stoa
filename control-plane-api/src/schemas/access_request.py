"""Pydantic schemas for portal access request email capture."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class AccessRequestCreate(BaseModel):
    """Public form submission: email + optional company."""

    email: EmailStr
    company: str | None = None
    source: str | None = None


class AccessRequestResponse(BaseModel):
    """Response after submitting an access request."""

    message: str
    request_id: UUID


class AccessRequestDetail(BaseModel):
    """Admin view of an access request."""

    id: UUID
    email: str
    company: str | None = None
    source: str | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
