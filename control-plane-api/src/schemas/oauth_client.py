"""Pydantic schemas for OAuth client DCR onboarding API (CAB-1483)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OAuthClientCreate(BaseModel):
    """Request body for POST /v1/oauth-clients/."""

    client_name: str = Field(..., min_length=1, max_length=255, description="Human-readable client name")
    description: str | None = Field(None, max_length=1024, description="Optional description")
    product_roles: list[str] = Field(
        default_factory=list,
        description="SCIM-derived roles to embed in JWT via protocol mapper",
    )
    oauth_metadata: dict | None = Field(
        None,
        description="Optional OAuth metadata (grant_types, redirect_uris, etc.)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "client_name": "acme-billing-service",
                "description": "Billing service for Acme Corp tenant",
                "product_roles": ["api:read", "api:write", "billing:admin"],
                "oauth_metadata": {"grant_types": ["client_credentials"]},
            }
        }
    )


class OAuthClientResponse(BaseModel):
    """Response body for a registered OAuth client."""

    id: str
    tenant_id: str
    keycloak_client_id: str
    client_name: str
    description: str | None = None
    product_roles: list[str] | None = None
    oauth_metadata: dict | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OAuthClientListResponse(BaseModel):
    """Paginated list of OAuth clients."""

    items: list[OAuthClientResponse]
    total: int
    page: int
    page_size: int
