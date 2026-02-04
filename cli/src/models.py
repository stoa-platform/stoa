"""Pydantic models for API responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TenantResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str = ""
    owner_email: str = ""
    status: str = "active"
    api_count: int = 0
    application_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class APIResponse(BaseModel):
    id: str
    name: str
    display_name: str
    version: str = "1.0.0"
    description: str = ""
    backend_url: str = ""
    status: str = ""
    tags: list[str] = []
    created_at: str | None = None
    updated_at: str | None = None


class APICreate(BaseModel):
    name: str
    display_name: str
    version: str = "1.0.0"
    description: str = ""
    backend_url: str
    openapi_spec: str | None = None
    tags: list[str] = []


class APIUpdate(BaseModel):
    display_name: str | None = None
    version: str | None = None
    description: str | None = None
    backend_url: str | None = None
    openapi_spec: str | None = None
    tags: list[str] | None = None


class HealthResponse(BaseModel):
    status: str
    version: str | None = None
    timestamp: datetime | None = None


class PlatformStatus(BaseModel):
    api_healthy: bool = False
    auth_healthy: bool = False
    server: str = ""
    user: str | None = None
    tenant_id: str | None = None
    token_valid: bool = False
