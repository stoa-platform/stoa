"""
Pydantic schemas for Contracts and Protocol Bindings API.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProtocolType(StrEnum):
    """Supported protocol types for UAC bindings."""

    REST = "rest"
    GRAPHQL = "graphql"
    GRPC = "grpc"
    MCP = "mcp"
    KAFKA = "kafka"


class ContractStatus(StrEnum):
    """Contract lifecycle status."""

    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


# ============ Protocol Binding Schemas ============


class ProtocolBindingResponse(BaseModel):
    """Protocol binding information for a contract."""

    protocol: ProtocolType
    enabled: bool
    endpoint: str | None = None
    playground_url: str | None = None
    tool_name: str | None = None  # For MCP
    operations: list[str] | None = None  # For GraphQL
    proto_file_url: str | None = None  # For gRPC
    topic_name: str | None = None  # For Kafka
    traffic_24h: int | None = None  # Request count in last 24 hours
    generated_at: datetime | None = None
    generation_error: str | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "protocol": "rest",
                "enabled": True,
                "endpoint": "https://api.stoa.example.com/v1/payments",
                "playground_url": "https://api.stoa.example.com/docs",
                "traffic_24h": 1250,
                "generated_at": "2024-01-15T10:30:00Z",
            }
        },
    )


class BindingsListResponse(BaseModel):
    """List of protocol bindings for a contract."""

    contract_id: UUID
    contract_name: str
    bindings: list[ProtocolBindingResponse]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "contract_id": "550e8400-e29b-41d4-a716-446655440000",
                "contract_name": "payment-service",
                "bindings": [
                    {
                        "protocol": "rest",
                        "enabled": True,
                        "endpoint": "/api/v1/payments",
                    },
                    {"protocol": "mcp", "enabled": True, "tool_name": "create_payment"},
                    {"protocol": "graphql", "enabled": False},
                    {"protocol": "grpc", "enabled": False},
                    {"protocol": "kafka", "enabled": False},
                ],
            }
        }
    )


class EnableBindingRequest(BaseModel):
    """Request to enable a protocol binding."""

    protocol: ProtocolType = Field(..., description="Protocol to enable")

    model_config = ConfigDict(json_schema_extra={"example": {"protocol": "graphql"}})


class EnableBindingResponse(BaseModel):
    """Response after enabling a protocol binding."""

    protocol: ProtocolType
    endpoint: str
    playground_url: str | None = None
    tool_name: str | None = None
    status: str = "active"
    generated_at: datetime

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "protocol": "graphql",
                "endpoint": "https://api.stoa.example.com/graphql",
                "playground_url": "https://api.stoa.example.com/graphql/playground",
                "status": "active",
                "generated_at": "2024-01-15T10:30:00Z",
            }
        }
    )


class DisableBindingResponse(BaseModel):
    """Response after disabling a protocol binding."""

    protocol: ProtocolType
    status: str = "disabled"
    disabled_at: datetime


# ============ Contract Schemas ============


class ContractCreate(BaseModel):
    """Request to create a new contract."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Unique contract name"
    )
    display_name: str | None = Field(
        None, max_length=255, description="Human-friendly name"
    )
    description: str | None = Field(None, description="Contract description")
    version: str = Field(default="1.0.0", max_length=50, description="Contract version")
    openapi_spec_url: str | None = Field(
        None, max_length=512, description="URL to OpenAPI spec"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "payment-service",
                "display_name": "Payment Service API",
                "description": "API for processing payments",
                "version": "2.0.0",
                "openapi_spec_url": "https://specs.example.com/payment-service/openapi.yaml",
            }
        }
    )


class ContractUpdate(BaseModel):
    """Request to update a contract."""

    display_name: str | None = Field(None, max_length=255)
    description: str | None = None
    version: str | None = Field(None, max_length=50)
    status: ContractStatus | None = None
    openapi_spec_url: str | None = Field(None, max_length=512)


class ContractResponse(BaseModel):
    """Contract information response."""

    id: UUID
    tenant_id: str
    name: str
    display_name: str | None = None
    description: str | None = None
    version: str
    status: str
    openapi_spec_url: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    bindings: list[ProtocolBindingResponse] = []

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "tenant_id": "acme-corp",
                "name": "payment-service",
                "display_name": "Payment Service API",
                "description": "API for processing payments",
                "version": "2.0.0",
                "status": "published",
                "created_at": "2024-01-10T08:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
                "bindings": [],
            }
        },
    )


class ContractListResponse(BaseModel):
    """Paginated list of contracts."""

    items: list[ContractResponse]
    total: int
    page: int
    page_size: int


# ============ MCP Generated Tool Schemas (CAB-605) ============


class McpToolDefinition(BaseModel):
    """A single MCP tool generated from a UAC endpoint."""

    tool_name: str
    description: str | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    backend_url: str | None = None
    http_method: str | None = None
    path_pattern: str | None = None
    version: str
    spec_hash: str | None = None
    enabled: bool = True


class McpToolsListResponse(BaseModel):
    """List of MCP tools generated from a contract."""

    contract_id: UUID
    contract_name: str
    tools: list[McpToolDefinition]
    spec_hash: str | None = None


class McpToolsGenerateResponse(BaseModel):
    """Response after generating MCP tools from a UAC contract."""

    generated: int
    contract_id: UUID
    tools: list[McpToolDefinition]


class TenantToolsResponse(BaseModel):
    """All generated MCP tools for a tenant (gateway discovery)."""

    tenant_id: str
    tools: list[McpToolDefinition]
    total: int
