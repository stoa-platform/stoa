"""Pydantic schemas for catalog cache endpoints (CAB-682)"""
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# ============== Enums ==============

class SyncTypeEnum(str, Enum):
    """Sync operation type."""
    FULL = "full"
    TENANT = "tenant"
    API = "api"


class SyncStatusEnum(str, Enum):
    """Sync operation status."""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


# ============== API Catalog Schemas ==============

class APICatalogResponse(BaseModel):
    """API catalog entry response."""
    id: UUID
    tenant_id: str
    api_id: str
    api_name: str | None = None
    version: str | None = None
    status: str = "active"
    category: str | None = None
    tags: list[str] = []
    portal_published: bool = False

    # Extracted from metadata for convenience
    display_name: str | None = None
    description: str | None = None
    backend_url: str | None = None
    deployments: dict | None = None

    # Git tracking
    git_path: str | None = None
    git_commit_sha: str | None = None

    # Timing
    synced_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_db_model(cls, api: Any) -> "APICatalogResponse":
        """Convert database model to response schema with metadata extraction."""
        metadata = api.api_metadata or {}
        return cls(
            id=api.id,
            tenant_id=api.tenant_id,
            api_id=api.api_id,
            api_name=api.api_name,
            version=api.version,
            status=api.status,
            category=api.category,
            tags=api.tags or [],
            portal_published=api.portal_published,
            display_name=metadata.get("display_name", api.api_name),
            description=metadata.get("description", ""),
            backend_url=metadata.get("backend_url"),
            deployments=metadata.get("deployments", {}),
            git_path=api.git_path,
            git_commit_sha=api.git_commit_sha,
            synced_at=api.synced_at,
        )


class APICatalogListResponse(BaseModel):
    """Response for listing API catalog entries."""
    apis: list[APICatalogResponse]
    total: int
    page: int = 1
    page_size: int = 20


class APICatalogDetailResponse(APICatalogResponse):
    """Detailed API catalog response including OpenAPI spec."""
    openapi_spec: dict | None = None
    metadata: dict | None = None

    @classmethod
    def from_db_model(cls, api: Any) -> "APICatalogDetailResponse":
        """Convert database model to detailed response schema."""
        metadata = api.api_metadata or {}
        return cls(
            id=api.id,
            tenant_id=api.tenant_id,
            api_id=api.api_id,
            api_name=api.api_name,
            version=api.version,
            status=api.status,
            category=api.category,
            tags=api.tags or [],
            portal_published=api.portal_published,
            display_name=metadata.get("display_name", api.api_name),
            description=metadata.get("description", ""),
            backend_url=metadata.get("backend_url"),
            deployments=metadata.get("deployments", {}),
            git_path=api.git_path,
            git_commit_sha=api.git_commit_sha,
            synced_at=api.synced_at,
            openapi_spec=api.openapi_spec,
            metadata=api.api_metadata,
        )


# ============== Sync Status Schemas ==============

class SyncStatusResponse(BaseModel):
    """Sync operation status response."""
    id: UUID
    sync_type: SyncTypeEnum
    status: SyncStatusEnum
    started_at: datetime
    completed_at: datetime | None = None
    items_synced: int = 0
    errors: list[dict] = []
    git_commit_sha: str | None = None
    duration_seconds: float | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_db_model(cls, sync: Any) -> "SyncStatusResponse":
        """Convert database model to response schema."""
        return cls(
            id=sync.id,
            sync_type=SyncTypeEnum(sync.sync_type),
            status=SyncStatusEnum(sync.status),
            started_at=sync.started_at,
            completed_at=sync.completed_at,
            items_synced=sync.items_synced,
            errors=sync.errors or [],
            git_commit_sha=sync.git_commit_sha,
            duration_seconds=sync.duration_seconds,
        )


class SyncTriggerResponse(BaseModel):
    """Response when triggering a sync operation."""
    status: str = "sync_started"
    message: str = "Catalog sync triggered"
    sync_id: UUID | None = None


class SyncHistoryResponse(BaseModel):
    """Response for sync history."""
    syncs: list[SyncStatusResponse]
    total: int


# ============== Catalog Stats Schemas ==============

class CatalogStatsResponse(BaseModel):
    """Catalog statistics response."""
    total_apis: int
    published_apis: int
    unpublished_apis: int
    by_tenant: dict[str, int] = {}
    by_category: dict[str, int] = {}
    last_sync: SyncStatusResponse | None = None


# ============== Categories/Tags Schemas ==============

class CategoriesResponse(BaseModel):
    """Available categories response."""
    categories: list[str]


class TagsResponse(BaseModel):
    """Available tags response."""
    tags: list[str]
