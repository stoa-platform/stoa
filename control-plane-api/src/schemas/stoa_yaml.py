"""stoa.yaml declarative spec — Pydantic v2 models (CAB-1410).

stoa.yaml is the Git-first API deployment contract.
CLI validates against the JSON Schema; CP API parses this model on deploy.

Example:
    name: petstore
    version: 1.2.0
    tags: [payments, internal]
    endpoints:
      - path: /pets
        method: GET
        description: List all pets
    rate_limit:
      requests_per_minute: 100
      burst: 20
    auth:
      type: jwt
      issuer: https://auth.example.com
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class AuthType(StrEnum):
    JWT = "jwt"
    API_KEY = "api_key"
    MTLS = "mtls"
    OAUTH2 = "oauth2"
    NONE = "none"


class StoaEndpoint(BaseModel):
    """Single endpoint definition in stoa.yaml."""

    path: Annotated[str, Field(description="URL path (e.g. /pets or /pets/{id})")]
    method: HttpMethod = HttpMethod.GET
    description: str | None = Field(default=None, description="Human-readable description")
    tags: list[str] = Field(default_factory=list, description="Endpoint-level tags")


class StoaRateLimit(BaseModel):
    """Rate limiting configuration."""

    requests_per_minute: Annotated[int, Field(gt=0, description="Max requests per minute")] = 60
    burst: Annotated[int, Field(gt=0, description="Burst allowance above rpm")] = 10


class StoaAuth(BaseModel):
    """Authentication configuration."""

    type: AuthType = AuthType.JWT
    issuer: str | None = Field(default=None, description="OIDC issuer URL (for jwt/oauth2)")
    header: str | None = Field(default=None, description="Header name (for api_key auth)")
    required: bool = True


class StoaYamlSpec(BaseModel):
    """Root model for stoa.yaml declarative API spec.

    This is the contract between the stoactl CLI and the CP API.
    The CLI serialises this to JSON and POSTs to /v1/deployments.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "title": "stoa.yaml",
            "description": "STOA declarative API deployment specification",
            "examples": [
                {
                    "name": "petstore",
                    "version": "1.2.0",
                    "tags": ["payments", "internal"],
                    "endpoints": [
                        {"path": "/pets", "method": "GET", "description": "List all pets"},
                        {"path": "/pets/{id}", "method": "GET", "description": "Get a pet"},
                    ],
                    "rate_limit": {"requests_per_minute": 100, "burst": 20},
                    "auth": {"type": "jwt", "issuer": "https://auth.example.com"},
                }
            ],
        }
    )

    name: Annotated[str, Field(min_length=1, max_length=255, description="API identifier (slug)")]
    version: Annotated[
        str,
        Field(
            min_length=1,
            max_length=100,
            description="Semantic version (e.g. 1.2.0)",
            pattern=r"^\d+\.\d+\.\d+.*$",
        ),
    ] = "1.0.0"
    endpoints: list[StoaEndpoint] = Field(default_factory=list, description="API endpoint definitions")
    rate_limit: StoaRateLimit | None = Field(default=None, description="Rate limiting config")
    auth: StoaAuth | None = Field(default=None, description="Authentication config")
    tags: list[str] = Field(default_factory=list, description="API-level tags for routing and filtering")


def export_json_schema() -> dict:
    """Export the JSON Schema for stoa.yaml (used by stoactl CLI for validation)."""
    return StoaYamlSpec.model_json_schema()
