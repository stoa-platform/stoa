"""Pydantic schemas for deployment lifecycle API (CAB-1353)"""
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeploymentStatusEnum(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class EnvironmentEnum(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


class DeploymentCreate(BaseModel):
    api_id: str
    api_name: str | None = None
    environment: EnvironmentEnum
    version: str | None = None
    gateway_id: str | None = None


class DeploymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    api_id: str
    api_name: str
    environment: str
    version: str
    status: str
    deployed_by: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    rollback_of: UUID | None = None
    rollback_version: str | None = None
    gateway_id: str | None = None
    spec_hash: str | None = None
    commit_sha: str | None = None
    attempt_count: int = 0


class DeploymentListResponse(BaseModel):
    items: list[DeploymentResponse]
    total: int
    page: int = 1
    page_size: int = 50


class RollbackCreate(BaseModel):
    target_version: str | None = None


class DeploymentStatusUpdate(BaseModel):
    status: DeploymentStatusEnum
    error_message: str | None = None
    spec_hash: str | None = None
    commit_sha: str | None = None
    metadata: dict | None = Field(default=None, description="Additional metadata from gateway callback")


class EnvironmentDeployment(BaseModel):
    api_id: str
    api_name: str
    version: str
    status: str
    deployed_at: datetime | None = None


class EnvironmentStatusResponse(BaseModel):
    environment: str
    healthy: bool
    deployments: list[EnvironmentDeployment]


class DeploymentLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deployment_id: UUID
    seq: int
    level: str
    step: str | None = None
    message: str
    created_at: datetime


class DeploymentLogListResponse(BaseModel):
    deployment_id: UUID
    logs: list[DeploymentLogResponse]
    total: int
