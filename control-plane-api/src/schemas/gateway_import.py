"""Pydantic schemas for gateway import endpoints."""
from pydantic import BaseModel


class ImportPreviewResponse(BaseModel):
    """Preview of a single API to be imported."""

    api_id: str
    api_name: str
    tenant_id: str
    gateway_resource_id: str
    action: str
    reason: str


class ImportResultResponse(BaseModel):
    """Result of a gateway import operation."""

    created: int
    skipped: int
    errors: list[str]
    details: list[ImportPreviewResponse]
