"""Pydantic schemas for GitOps promotion flow API (CAB-1706)"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PromotionStatusEnum(StrEnum):
    PENDING = "pending"
    PROMOTING = "promoting"
    PROMOTED = "promoted"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class PromotionCreate(BaseModel):
    source_environment: str = Field(
        ..., description="Source environment (dev, staging)"
    )
    target_environment: str = Field(
        ..., description="Target environment (staging, production)"
    )
    message: str = Field(
        ..., min_length=1, max_length=1000,
        description="Mandatory audit trail message explaining the promotion reason"
    )


class PromotionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    api_id: str
    source_environment: str
    target_environment: str
    source_deployment_id: UUID | None = None
    target_deployment_id: UUID | None = None
    status: str
    spec_diff: dict | None = None
    message: str
    requested_by: str
    approved_by: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PromotionListResponse(BaseModel):
    items: list[PromotionResponse]
    total: int
    page: int = 1
    page_size: int = 50


class PromotionRollbackRequest(BaseModel):
    message: str = Field(
        ..., min_length=1, max_length=1000,
        description="Mandatory audit trail message explaining the rollback reason"
    )


class PromotionDiffResponse(BaseModel):
    promotion_id: UUID
    source_environment: str
    target_environment: str
    source_spec: dict | None = None
    target_spec: dict | None = None
    diff_summary: dict | None = None
