"""Schemas for the canonical API lifecycle endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiLifecycleCreateDraftRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=255)
    version: str = Field(default="1.0.0", min_length=1, max_length=50)
    description: str = ""
    backend_url: str = Field(..., min_length=1, max_length=500)
    openapi_spec: str | dict[str, Any] | None = None
    spec_reference: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list)
    owner_team: str | None = Field(default=None, max_length=255)


class ApiLifecycleValidateDraftRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class ApiLifecycleDeployRequest(BaseModel):
    environment: str = Field(..., min_length=1, max_length=50)
    gateway_instance_id: UUID | None = None
    force: bool = False


class ApiLifecyclePublishRequest(BaseModel):
    environment: str = Field(..., min_length=1, max_length=50)
    gateway_instance_id: UUID | None = None
    force: bool = False


class ApiLifecyclePromoteRequest(BaseModel):
    source_environment: str = Field(..., min_length=1, max_length=50)
    target_environment: str = Field(..., min_length=1, max_length=50)
    source_gateway_instance_id: UUID | None = None
    target_gateway_instance_id: UUID | None = None
    force: bool = False


class ApiLifecycleValidationResultResponse(BaseModel):
    valid: bool
    code: str
    message: str
    spec_source: str
    spec_format: str | None = None
    spec_version: str | None = None
    title: str | None = None
    version: str | None = None
    path_count: int = 0
    operation_count: int = 0
    validated_at: datetime | None = None


class ApiLifecycleSpecResponse(BaseModel):
    source: str
    has_openapi_spec: bool
    git_path: str | None = None
    git_commit_sha: str | None = None
    reference: str | None = None
    fallback_reason: str | None = None


class ApiLifecycleSyncStepResponse(BaseModel):
    name: str
    status: str
    detail: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ApiLifecycleGatewayDeploymentResponse(BaseModel):
    id: UUID
    environment: str
    gateway_instance_id: UUID
    gateway_name: str
    gateway_type: str
    sync_status: str
    desired_generation: int
    synced_generation: int
    gateway_resource_id: str | None = None
    public_url: str | None = None
    sync_error: str | None = None
    last_sync_attempt: datetime | None = None
    last_sync_success: datetime | None = None
    policy_sync_status: str | None = None
    policy_sync_error: str | None = None
    sync_steps: list[ApiLifecycleSyncStepResponse] = Field(default_factory=list)


class ApiLifecyclePromotionResponse(BaseModel):
    id: UUID
    source_environment: str
    target_environment: str
    status: str
    message: str
    requested_by: str
    approved_by: str | None = None
    completed_at: datetime | None = None
    source_deployment_id: UUID | None = None
    target_deployment_id: UUID | None = None
    target_gateway_ids: list[UUID] = Field(default_factory=list)


class ApiLifecyclePortalPublicationResponse(BaseModel):
    environment: str
    gateway_instance_id: UUID
    deployment_id: UUID
    publication_status: str
    result: str
    spec_hash: str
    published_at: datetime


class ApiLifecyclePortalResponse(BaseModel):
    published: bool
    status: str
    publications: list[ApiLifecyclePortalPublicationResponse] = Field(default_factory=list)
    last_result: str | None = None
    last_environment: str | None = None
    last_gateway_instance_id: UUID | None = None
    last_deployment_id: UUID | None = None
    last_published_at: datetime | None = None


class ApiLifecycleStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    catalog_id: UUID
    tenant_id: str
    api_id: str
    api_name: str
    display_name: str
    version: str
    description: str
    backend_url: str
    catalog_status: str
    lifecycle_phase: str
    portal_published: bool
    tags: list[str]
    spec: ApiLifecycleSpecResponse
    deployments: list[ApiLifecycleGatewayDeploymentResponse]
    promotions: list[ApiLifecyclePromotionResponse]
    last_error: str | None = None
    portal: ApiLifecyclePortalResponse


class ApiLifecycleValidateDraftResponse(BaseModel):
    tenant_id: str
    api_id: str
    status: str
    validation: ApiLifecycleValidationResultResponse
    lifecycle: ApiLifecycleStateResponse


class ApiLifecycleDeployResponse(BaseModel):
    tenant_id: str
    api_id: str
    environment: str
    gateway_instance_id: UUID
    deployment_id: UUID
    deployment_status: str
    action: str
    lifecycle: ApiLifecycleStateResponse


class ApiLifecyclePublishResponse(BaseModel):
    tenant_id: str
    api_id: str
    environment: str
    gateway_instance_id: UUID
    deployment_id: UUID
    publication_status: str
    portal_published: bool
    result: str
    lifecycle: ApiLifecycleStateResponse


class ApiLifecyclePromotionRequestResponse(BaseModel):
    tenant_id: str
    api_id: str
    promotion_id: UUID
    source_environment: str
    target_environment: str
    source_gateway_instance_id: UUID
    target_gateway_instance_id: UUID
    target_deployment_id: UUID
    promotion_status: str
    deployment_status: str
    result: str
    lifecycle: ApiLifecycleStateResponse
