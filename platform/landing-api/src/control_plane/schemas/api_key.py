"""Schemas for API key delivery.

The plaintext key exists only on the create response. List and read
schemas have no field that could carry it.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    """Request schema for issuing an API key."""

    name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., min_length=1, max_length=32)
    tenant_id: str | None = Field(None, max_length=128)


class ApiKeyPublic(BaseModel):
    """Key metadata safe to return after creation."""

    id: UUID
    name: str
    role: str
    tenant_id: str
    key_prefix: str
    created_at: datetime


class ApiKeyCreatedResponse(ApiKeyPublic):
    """Create response. `api_key` is delivered once and then discarded."""

    api_key: str


class ApiKeyListResponse(BaseModel):
    """List response. Items never include the secret or its hash."""

    api_keys: list[ApiKeyPublic]
    total: int
