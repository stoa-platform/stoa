# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
Pydantic schemas for Contracts and Protocol Bindings API.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class ProtocolType(str, Enum):
    """Supported protocol types for UAC bindings."""
    REST = "rest"
    GRAPHQL = "graphql"
    GRPC = "grpc"
    MCP = "mcp"
    KAFKA = "kafka"


class ContractStatus(str, Enum):
    """Contract lifecycle status."""
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


# ============ Protocol Binding Schemas ============

class ProtocolBindingResponse(BaseModel):
    """Protocol binding information for a contract."""
    protocol: ProtocolType
    enabled: bool
    endpoint: Optional[str] = None
    playground_url: Optional[str] = None
    tool_name: Optional[str] = None  # For MCP
    operations: Optional[List[str]] = None  # For GraphQL
    proto_file_url: Optional[str] = None  # For gRPC
    topic_name: Optional[str] = None  # For Kafka
    traffic_24h: Optional[int] = None  # Request count in last 24 hours
    generated_at: Optional[datetime] = None
    generation_error: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "protocol": "rest",
                "enabled": True,
                "endpoint": "https://api.stoa.example.com/v1/payments",
                "playground_url": "https://api.stoa.example.com/docs",
                "traffic_24h": 1250,
                "generated_at": "2024-01-15T10:30:00Z"
            }
        }
    )


class BindingsListResponse(BaseModel):
    """List of protocol bindings for a contract."""
    contract_id: UUID
    contract_name: str
    bindings: List[ProtocolBindingResponse]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "contract_id": "550e8400-e29b-41d4-a716-446655440000",
                "contract_name": "payment-service",
                "bindings": [
                    {"protocol": "rest", "enabled": True, "endpoint": "/api/v1/payments"},
                    {"protocol": "mcp", "enabled": True, "tool_name": "create_payment"},
                    {"protocol": "graphql", "enabled": False},
                    {"protocol": "grpc", "enabled": False},
                    {"protocol": "kafka", "enabled": False}
                ]
            }
        }
    )


class EnableBindingRequest(BaseModel):
    """Request to enable a protocol binding."""
    protocol: ProtocolType = Field(..., description="Protocol to enable")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "protocol": "graphql"
            }
        }
    )


class EnableBindingResponse(BaseModel):
    """Response after enabling a protocol binding."""
    protocol: ProtocolType
    endpoint: str
    playground_url: Optional[str] = None
    tool_name: Optional[str] = None
    status: str = "active"
    generated_at: datetime

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "protocol": "graphql",
                "endpoint": "https://api.stoa.example.com/graphql",
                "playground_url": "https://api.stoa.example.com/graphql/playground",
                "status": "active",
                "generated_at": "2024-01-15T10:30:00Z"
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
    name: str = Field(..., min_length=1, max_length=255, description="Unique contract name")
    display_name: Optional[str] = Field(None, max_length=255, description="Human-friendly name")
    description: Optional[str] = Field(None, description="Contract description")
    version: str = Field(default="1.0.0", max_length=50, description="Contract version")
    openapi_spec_url: Optional[str] = Field(None, max_length=512, description="URL to OpenAPI spec")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "payment-service",
                "display_name": "Payment Service API",
                "description": "API for processing payments",
                "version": "2.0.0",
                "openapi_spec_url": "https://specs.example.com/payment-service/openapi.yaml"
            }
        }
    )


class ContractUpdate(BaseModel):
    """Request to update a contract."""
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    version: Optional[str] = Field(None, max_length=50)
    status: Optional[ContractStatus] = None
    openapi_spec_url: Optional[str] = Field(None, max_length=512)


class ContractResponse(BaseModel):
    """Contract information response."""
    id: UUID
    tenant_id: str
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    version: str
    status: str
    openapi_spec_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    bindings: List[ProtocolBindingResponse] = []

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
                "bindings": []
            }
        }
    )


class ContractListResponse(BaseModel):
    """Paginated list of contracts."""
    items: List[ContractResponse]
    total: int
    page: int
    page_size: int
