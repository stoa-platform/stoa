"""
Pydantic schemas for Tenant DR (Disaster Recovery) — Export/Import (CAB-1474).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============ Export Schemas ============


class ExportMetadata(BaseModel):
    """Metadata about the export archive."""

    export_version: str = "1.0"
    exported_at: datetime
    tenant_id: str
    tenant_name: str | None = None
    resource_counts: dict[str, int] = Field(default_factory=dict)


class ExportedBackendApi(BaseModel):
    """Backend API in export format."""

    id: UUID
    name: str
    display_name: str | None = None
    description: str | None = None
    backend_url: str | None = None
    openapi_spec_url: str | None = None
    auth_type: str | None = None
    status: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ExportedContract(BaseModel):
    """Contract (UAC) in export format."""

    id: UUID
    name: str
    display_name: str | None = None
    description: str | None = None
    version: str
    status: str
    openapi_spec_url: str | None = None
    deprecated_at: datetime | None = None
    sunset_at: datetime | None = None
    deprecation_reason: str | None = None
    grace_period_days: int | None = None
    bindings: list[dict] = Field(default_factory=list)
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ExportedConsumer(BaseModel):
    """Consumer in export format."""

    id: UUID
    external_id: str
    name: str
    email: str
    company: str | None = None
    description: str | None = None
    status: str
    consumer_metadata: dict | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ExportedPlan(BaseModel):
    """Subscription plan in export format."""

    id: UUID
    slug: str
    name: str
    description: str | None = None
    rate_limit_per_second: int | None = None
    rate_limit_per_minute: int | None = None
    daily_request_limit: int | None = None
    monthly_request_limit: int | None = None
    burst_limit: int | None = None
    requires_approval: bool = False
    status: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ExportedSubscription(BaseModel):
    """Subscription in export format (no API keys — secrets excluded)."""

    id: UUID
    application_id: str
    application_name: str
    subscriber_email: str
    api_id: str
    api_name: str | None = None
    plan_id: str | None = None
    status: str
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ExportedPolicy(BaseModel):
    """Gateway policy in export format."""

    id: UUID
    name: str
    description: str | None = None
    policy_type: str
    config: dict | None = None
    enabled: bool = True
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ExportedSkill(BaseModel):
    """Skill in export format."""

    id: UUID
    name: str
    description: str | None = None
    scope: str
    priority: int = 50
    instructions: str | None = None
    tool_ref: str | None = None
    user_ref: str | None = None
    enabled: bool = True

    model_config = ConfigDict(from_attributes=True)


class ExportedWebhook(BaseModel):
    """Webhook config in export format (secret excluded)."""

    id: UUID
    name: str
    url: str
    events: list[str] = Field(default_factory=list)
    enabled: bool = True
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ExportedExternalMcpServer(BaseModel):
    """External MCP server in export format (auth config excluded)."""

    id: UUID
    name: str
    base_url: str
    description: str | None = None
    enabled: bool = True
    tools: list[dict] = Field(default_factory=list)
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TenantExportResponse(BaseModel):
    """Full tenant export archive."""

    metadata: ExportMetadata
    backend_apis: list[ExportedBackendApi] = Field(default_factory=list)
    contracts: list[ExportedContract] = Field(default_factory=list)
    consumers: list[ExportedConsumer] = Field(default_factory=list)
    plans: list[ExportedPlan] = Field(default_factory=list)
    subscriptions: list[ExportedSubscription] = Field(default_factory=list)
    policies: list[ExportedPolicy] = Field(default_factory=list)
    skills: list[ExportedSkill] = Field(default_factory=list)
    webhooks: list[ExportedWebhook] = Field(default_factory=list)
    external_mcp_servers: list[ExportedExternalMcpServer] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "metadata": {
                    "export_version": "1.0",
                    "exported_at": "2026-03-01T10:00:00Z",
                    "tenant_id": "acme-corp",
                    "tenant_name": "Acme Corporation",
                    "resource_counts": {
                        "backend_apis": 5,
                        "contracts": 3,
                        "consumers": 10,
                    },
                },
                "backend_apis": [],
                "contracts": [],
                "consumers": [],
                "plans": [],
                "subscriptions": [],
                "policies": [],
                "skills": [],
                "webhooks": [],
                "external_mcp_servers": [],
            }
        }
    )


# ============ Import Schemas ============


class ImportMode(BaseModel):
    """Configuration for import behavior."""

    conflict_resolution: str = Field(
        default="skip",
        description="How to handle conflicts: skip, overwrite, or fail",
        pattern="^(skip|overwrite|fail)$",
    )
    dry_run: bool = Field(default=False, description="Validate without applying changes")


class TenantImportRequest(BaseModel):
    """Request to import tenant data from an export archive."""

    archive: TenantExportResponse
    mode: ImportMode = Field(default_factory=ImportMode)


class ImportResult(BaseModel):
    """Result of an import operation."""

    tenant_id: str
    dry_run: bool = False
    created: dict[str, int] = Field(default_factory=dict)
    skipped: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    success: bool = True
