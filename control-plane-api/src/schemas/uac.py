"""
Pydantic schemas for UAC (Universal API Contract) v1.

Mirror types of the gateway's Rust `uac::schema` module.
Cross-language parity is enforced via `uac-contract-v1.schema.json`.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class UacClassification(StrEnum):
    """ICT risk classification (DORA-aligned).

    - H: High — standard APIs, auto-approved
    - VH: Very High — sensitive APIs, requires review
    - VVH: Very Very High — critical APIs, requires review + encryption
    """

    H = "H"
    VH = "VH"
    VVH = "VVH"


CLASSIFICATION_POLICIES: dict[UacClassification, list[str]] = {
    UacClassification.H: ["rate-limit", "auth-jwt"],
    UacClassification.VH: ["rate-limit", "auth-jwt", "mtls", "audit-logging"],
    UacClassification.VVH: [
        "rate-limit",
        "auth-jwt",
        "mtls",
        "audit-logging",
        "data-encryption",
        "geo-restriction",
    ],
}


class UacContractStatus(StrEnum):
    """Contract lifecycle status."""

    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class UacEndpointSpec(BaseModel):
    """A single API endpoint within a UAC contract."""

    path: str = Field(..., min_length=1, description="URL path pattern (e.g. /payments/{id})")
    methods: list[str] = Field(
        ...,
        min_length=1,
        description="Allowed HTTP methods (e.g. ['GET', 'POST'])",
    )
    backend_url: str = Field(..., min_length=1, description="Backend URL to proxy requests to")
    operation_id: str | None = Field(
        None, description="OpenAPI operationId (used for MCP tool naming)"
    )
    input_schema: dict | None = Field(None, description="JSON Schema for request body")
    output_schema: dict | None = Field(None, description="JSON Schema for response body")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "path": "/payments/{id}",
                "methods": ["GET", "POST"],
                "backend_url": "https://backend.acme.com/v1/payments",
                "operation_id": "get_payment",
            }
        }
    )


class UacContractSpec(BaseModel):
    """UAC Contract v1 specification.

    Define Once, Expose Everywhere — a single contract generates
    REST routes, MCP tools, and protocol bindings automatically.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$",
        description="Unique contract name within tenant (kebab-case)",
    )
    version: str = Field(
        default="1.0.0",
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version",
    )
    tenant_id: str = Field(..., min_length=1, description="Owning tenant identifier")
    display_name: str | None = Field(None, max_length=255, description="Human-readable name")
    description: str | None = Field(None, description="Contract description")
    classification: UacClassification = Field(
        default=UacClassification.H,
        description="ICT risk classification (DORA-aligned)",
    )
    endpoints: list[UacEndpointSpec] = Field(
        default_factory=list,
        description="API endpoints exposed by this contract",
    )
    required_policies: list[str] = Field(
        default_factory=list,
        description="Policies derived from classification (auto-populated)",
    )
    status: UacContractStatus = Field(
        default=UacContractStatus.DRAFT,
        description="Contract lifecycle status",
    )
    source_spec_url: str | None = Field(None, description="URL of the source OpenAPI spec")
    spec_hash: str | None = Field(None, description="SHA-256 hash of source spec")

    def refresh_policies(self) -> None:
        """Recompute required_policies from the current classification."""
        self.required_policies = list(CLASSIFICATION_POLICIES.get(self.classification, []))

    def validate_for_publish(self) -> list[str]:
        """Validate contract is ready to be published. Returns list of errors."""
        errors: list[str] = []
        if not self.endpoints:
            errors.append("published contract must have at least one endpoint")
        for i, ep in enumerate(self.endpoints):
            if not ep.path:
                errors.append(f"endpoints[{i}].path must not be empty")
            if not ep.methods:
                errors.append(f"endpoints[{i}].methods must not be empty")
            if not ep.backend_url:
                errors.append(f"endpoints[{i}].backend_url must not be empty")
        return errors

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "payment-service",
                "version": "1.0.0",
                "tenant_id": "acme",
                "display_name": "Payment Service",
                "classification": "H",
                "endpoints": [
                    {
                        "path": "/payments/{id}",
                        "methods": ["GET", "POST"],
                        "backend_url": "https://backend.acme.com/v1/payments",
                        "operation_id": "get_payment",
                    }
                ],
                "status": "draft",
            }
        }
    )
