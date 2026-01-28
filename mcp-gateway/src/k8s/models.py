# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Kubernetes Custom Resource models for STOA MCP Gateway.

Pydantic models representing Tool and ToolSet CRDs.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# =============================================================================
# Tool CRD Models
# =============================================================================


class ToolAuthenticationSpec(BaseModel):
    """Authentication configuration for a tool endpoint."""

    type: Literal["none", "bearer", "basic", "apiKey", "oauth2"] = "bearer"
    secretRef: dict[str, str] | None = None
    headerName: str = "Authorization"


class ToolRateLimitSpec(BaseModel):
    """Rate limiting configuration."""

    requestsPerMinute: int = Field(default=60, ge=1, le=10000)
    burst: int = Field(default=10, ge=1, le=1000)


class ToolApiRefSpec(BaseModel):
    """Reference to source API."""

    name: str | None = None
    version: str | None = None
    operationId: str | None = None


class ToolCRSpec(BaseModel):
    """Spec section of a Tool custom resource."""

    displayName: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=1024)
    endpoint: str | None = None
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    inputSchema: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    apiRef: ToolApiRefSpec | None = None
    authentication: ToolAuthenticationSpec | None = None
    timeout: str = "30s"
    rateLimit: ToolRateLimitSpec | None = None
    enabled: bool = True


class ToolCondition(BaseModel):
    """Condition in Tool status."""

    type: str
    status: Literal["True", "False", "Unknown"]
    reason: str | None = None
    message: str | None = None
    lastTransitionTime: datetime | None = None


class ToolCRStatus(BaseModel):
    """Status section of a Tool custom resource."""

    phase: Literal["Pending", "Registered", "Error", "Disabled"] = "Pending"
    registeredAt: datetime | None = None
    lastSyncedAt: datetime | None = None
    invocationCount: int = 0
    errorCount: int = 0
    lastError: str | None = None
    conditions: list[ToolCondition] = Field(default_factory=list)


class ToolCRMetadata(BaseModel):
    """Kubernetes metadata for Tool CR."""

    name: str
    namespace: str
    uid: str | None = None
    resourceVersion: str | None = None
    creationTimestamp: datetime | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class ToolCR(BaseModel):
    """Complete Tool custom resource."""

    apiVersion: str = "gostoa.dev/v1alpha1"
    kind: str = "Tool"
    metadata: ToolCRMetadata
    spec: ToolCRSpec
    status: ToolCRStatus | None = None


# =============================================================================
# ToolSet CRD Models
# =============================================================================


class OpenAPISpecSource(BaseModel):
    """Source configuration for OpenAPI spec."""

    url: str | None = None
    configMapRef: dict[str, str] | None = None
    secretRef: dict[str, str] | None = None
    inline: str | None = None
    refreshInterval: str = "1h"


class ToolSetSelectorSpec(BaseModel):
    """Selector for filtering operations from OpenAPI spec."""

    tags: list[str] | None = None
    excludeTags: list[str] | None = None
    methods: list[Literal["GET", "POST", "PUT", "PATCH", "DELETE"]] | None = None
    pathPrefix: str | None = None
    operationIds: list[str] | None = None


class ToolSetDefaultsSpec(BaseModel):
    """Default values for generated tools."""

    tags: list[str] = Field(default_factory=list)
    timeout: str = "30s"
    rateLimit: ToolRateLimitSpec | None = None
    authentication: ToolAuthenticationSpec | None = None


class ToolSetNamingSpec(BaseModel):
    """Naming configuration for generated tools."""

    prefix: str | None = None
    suffix: str | None = None
    useOperationId: bool = True


class ToolSetCRSpec(BaseModel):
    """Spec section of a ToolSet custom resource."""

    displayName: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    openAPISpec: OpenAPISpecSource | None = None
    baseURL: str | None = None
    selector: ToolSetSelectorSpec | None = None
    toolDefaults: ToolSetDefaultsSpec | None = None
    naming: ToolSetNamingSpec | None = None
    enabled: bool = True


class ToolSetCRStatus(BaseModel):
    """Status section of a ToolSet custom resource."""

    phase: Literal["Pending", "Syncing", "Ready", "Error", "Disabled"] = "Pending"
    toolCount: int = 0
    tools: list[str] = Field(default_factory=list)
    lastSyncedAt: datetime | None = None
    specHash: str | None = None
    lastError: str | None = None
    conditions: list[ToolCondition] = Field(default_factory=list)


class ToolSetCRMetadata(BaseModel):
    """Kubernetes metadata for ToolSet CR."""

    name: str
    namespace: str
    uid: str | None = None
    resourceVersion: str | None = None
    creationTimestamp: datetime | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class ToolSetCR(BaseModel):
    """Complete ToolSet custom resource."""

    apiVersion: str = "gostoa.dev/v1alpha1"
    kind: str = "ToolSet"
    metadata: ToolSetCRMetadata
    spec: ToolSetCRSpec
    status: ToolSetCRStatus | None = None
