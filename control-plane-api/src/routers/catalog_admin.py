"""Catalog Admin API Router - Admin endpoints for catalog sync operations (CAB-682).

Provides endpoints for managing the catalog cache synchronization.
These endpoints require admin role (cpi-admin or tenant-admin).
"""
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user, User
from ..database import get_db as get_async_db
from ..models.catalog import APICatalog
from ..services.catalog_sync_service import CatalogSyncService
from ..services.git_service import git_service
from ..repositories.catalog import CatalogRepository
from ..schemas.catalog import (
    SyncTriggerResponse,
    SyncStatusResponse,
    SyncHistoryResponse,
    CatalogStatsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin/catalog", tags=["Catalog Admin"])


def _require_admin(user: User) -> None:
    """Require admin role for access."""
    if "cpi-admin" not in user.roles and "tenant-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")


# ============================================================================
# Sync Operations
# ============================================================================

@router.post("/sync", response_model=SyncTriggerResponse)
async def trigger_catalog_sync(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Trigger a full catalog synchronization from GitLab.

    This operation runs in the background and syncs all APIs from all tenants.
    Use GET /sync/status to check progress.

    Requires: cpi-admin or tenant-admin role
    """
    _require_admin(user)

    try:
        sync_service = CatalogSyncService(db, git_service)

        # Check if a sync is already running
        last_sync = await sync_service.get_last_sync_status()
        if last_sync and last_sync.status == "running":
            return SyncTriggerResponse(
                status="sync_already_running",
                message="A sync operation is already in progress",
                sync_id=last_sync.id,
            )

        # Launch sync in background
        async def run_sync():
            async with get_async_db() as session:
                service = CatalogSyncService(session, git_service)
                await service.sync_all()

        background_tasks.add_task(run_sync)

        logger.info(f"Catalog sync triggered by user {user.id}")
        return SyncTriggerResponse(
            status="sync_started",
            message="Catalog sync triggered successfully",
        )

    except Exception as e:
        logger.error(f"Failed to trigger catalog sync: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger sync: {str(e)}")


@router.post("/sync/mcp-servers", response_model=SyncTriggerResponse)
async def trigger_mcp_servers_sync(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    tenant_id: Optional[str] = Query(None, description="Sync specific tenant only"),
):
    """
    Trigger MCP servers synchronization from GitLab.

    CAB-689: Syncs server.yaml files from Git to the mcp_servers table.
    Runs in the background.

    Requires: cpi-admin or tenant-admin role
    """
    _require_admin(user)

    try:
        async def run_sync():
            from ..database import get_db as get_async_db_gen
            async for session in get_async_db_gen():
                service = CatalogSyncService(session, git_service)
                await service.sync_mcp_servers(tenant_id)

        background_tasks.add_task(run_sync)

        logger.info(f"MCP servers sync triggered by user {user.id}")
        return SyncTriggerResponse(
            status="sync_started",
            message=f"MCP servers sync triggered{f' for tenant {tenant_id}' if tenant_id else ''}",
        )

    except Exception as e:
        logger.error(f"Failed to trigger MCP servers sync: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger sync: {str(e)}")


@router.post("/sync/tenant/{tenant_id}", response_model=SyncTriggerResponse)
async def trigger_tenant_sync(
    tenant_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Trigger catalog synchronization for a specific tenant.

    Requires: cpi-admin or tenant-admin role
    """
    _require_admin(user)

    # Tenant-admins can only sync their own tenant
    if "cpi-admin" not in user.roles and user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    try:
        async def run_sync():
            async with get_async_db() as session:
                service = CatalogSyncService(session, git_service)
                await service.sync_tenant(tenant_id)

        background_tasks.add_task(run_sync)

        logger.info(f"Tenant sync triggered for {tenant_id} by user {user.id}")
        return SyncTriggerResponse(
            status="sync_started",
            message=f"Catalog sync triggered for tenant {tenant_id}",
        )

    except Exception as e:
        logger.error(f"Failed to trigger tenant sync: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger sync: {str(e)}")


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get the status of the last catalog sync operation.

    Returns information about the most recent sync including:
    - Sync type (full/tenant/api)
    - Status (running/success/failed)
    - Items synced count
    - Duration
    - Any errors encountered

    Requires: cpi-admin or tenant-admin role
    """
    _require_admin(user)

    try:
        sync_service = CatalogSyncService(db, git_service)
        last_sync = await sync_service.get_last_sync_status()

        if not last_sync:
            raise HTTPException(status_code=404, detail="No sync operations found")

        return SyncStatusResponse.from_db_model(last_sync)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {str(e)}")


@router.get("/sync/history", response_model=SyncHistoryResponse)
async def get_sync_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    limit: int = Query(10, ge=1, le=100),
):
    """
    Get the history of catalog sync operations.

    Returns the most recent sync operations ordered by start time.

    Requires: cpi-admin or tenant-admin role
    """
    _require_admin(user)

    try:
        sync_service = CatalogSyncService(db, git_service)
        syncs = await sync_service.get_sync_history(limit=limit)

        return SyncHistoryResponse(
            syncs=[SyncStatusResponse.from_db_model(s) for s in syncs],
            total=len(syncs),
        )

    except Exception as e:
        logger.error(f"Failed to get sync history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sync history: {str(e)}")


# ============================================================================
# Catalog Stats
# ============================================================================

@router.get("/stats", response_model=CatalogStatsResponse)
async def get_catalog_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get statistics about the catalog cache.

    Returns counts of:
    - Total APIs
    - Published/unpublished APIs
    - APIs by tenant
    - APIs by category
    - Last sync information

    Requires: cpi-admin or tenant-admin role
    """
    _require_admin(user)

    try:
        repo = CatalogRepository(db)
        stats = await repo.get_stats()

        # Get last sync info
        sync_service = CatalogSyncService(db, git_service)
        last_sync = await sync_service.get_last_sync_status()

        return CatalogStatsResponse(
            total_apis=stats["total_apis"],
            published_apis=stats["published_apis"],
            unpublished_apis=stats["unpublished_apis"],
            by_tenant=stats["by_tenant"],
            by_category=stats["by_category"],
            last_sync=SyncStatusResponse.from_db_model(last_sync) if last_sync else None,
        )

    except Exception as e:
        logger.error(f"Failed to get catalog stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get catalog stats: {str(e)}")


# ============================================================================
# Cache Invalidation (for manual refresh)
# ============================================================================

@router.delete("/cache")
async def invalidate_cache(
    user: User = Depends(get_current_user),
):
    """
    Invalidate the in-memory API cache (if any).

    Note: This endpoint is maintained for backwards compatibility.
    With the new PostgreSQL-based cache, the sync endpoints should be used instead.

    Requires: cpi-admin role
    """
    if "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Platform admin access required")

    logger.info(f"Cache invalidation requested by user {user.id}")
    return {
        "status": "ok",
        "message": "Cache invalidated. Use POST /sync to refresh data from GitLab."
    }


# ============================================================================
# Direct Catalog Seed (offline mode — bypasses GitLab)
# ============================================================================

class CatalogSeedAPIEntry(BaseModel):
    """Single API entry for direct catalog seeding."""
    name: str
    display_name: str
    version: str = "1.0.0"
    description: str = ""
    backend_url: str = ""
    tags: List[str] = []
    category: Optional[str] = None
    openapi_spec: Optional[str] = None  # JSON string


class CatalogSeedRequest(BaseModel):
    """Request to seed APIs directly into catalog (bypasses GitLab)."""
    tenant_id: str
    apis: List[CatalogSeedAPIEntry]


class CatalogSeedResponse(BaseModel):
    """Response from catalog seed operation."""
    seeded: int
    failed: int
    results: dict


@router.post("/seed")
async def seed_catalog_directly(
    data: CatalogSeedRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Seed APIs directly into the catalog cache (bypasses GitLab).

    Use this when GitLab is not connected (e.g., demo environments,
    local development). Inserts or updates entries in the api_catalog table.

    Requires: cpi-admin role
    """
    if "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Platform admin access required")

    seeded = 0
    failed = 0
    results = {}

    for api_entry in data.apis:
        api_id = api_entry.name
        tags = api_entry.tags
        promotion_tags = {"portal:published", "promoted:portal", "portal-promoted"}
        portal_published = any(tag.lower() in promotion_tags for tag in tags)

        # Build metadata dict (same shape as GitLab api.yaml)
        api_metadata = {
            "name": api_entry.name,
            "display_name": api_entry.display_name,
            "version": api_entry.version,
            "description": api_entry.description,
            "backend_url": api_entry.backend_url,
            "tags": tags,
            "status": "active",
            "deployments": {"dev": True, "staging": False},
        }

        # Parse openapi_spec from JSON string if provided
        openapi_spec = None
        if api_entry.openapi_spec:
            try:
                openapi_spec = json.loads(api_entry.openapi_spec)
            except (json.JSONDecodeError, TypeError):
                openapi_spec = None

        try:
            stmt = insert(APICatalog).values(
                tenant_id=data.tenant_id,
                api_id=api_id,
                api_name=api_entry.display_name,
                version=api_entry.version,
                status="active",
                category=api_entry.category,
                tags=tags,
                portal_published=portal_published,
                api_metadata=api_metadata,
                openapi_spec=openapi_spec,
                git_path=None,
                git_commit_sha=None,
                synced_at=datetime.now(timezone.utc),
                deleted_at=None,
            ).on_conflict_do_update(
                index_elements=["tenant_id", "api_id"],
                set_={
                    APICatalog.api_name: api_entry.display_name,
                    APICatalog.version: api_entry.version,
                    APICatalog.status: "active",
                    APICatalog.category: api_entry.category,
                    APICatalog.tags: tags,
                    APICatalog.portal_published: portal_published,
                    APICatalog.api_metadata: api_metadata,
                    APICatalog.openapi_spec: openapi_spec,
                    APICatalog.synced_at: datetime.now(timezone.utc),
                    APICatalog.deleted_at: None,
                },
            )
            await db.execute(stmt)
            seeded += 1
            results[api_id] = "seeded"
        except Exception as e:
            logger.error(f"Failed to seed API {api_id}: {e}")
            failed += 1
            results[api_id] = f"failed: {str(e)[:100]}"

    await db.commit()

    logger.info(
        f"Catalog seed by {user.username}: {seeded} seeded, {failed} failed "
        f"(tenant: {data.tenant_id})"
    )

    return CatalogSeedResponse(seeded=seeded, failed=failed, results=results)
