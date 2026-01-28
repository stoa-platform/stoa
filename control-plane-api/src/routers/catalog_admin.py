# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Catalog Admin API Router - Admin endpoints for catalog sync operations (CAB-682).

Provides endpoints for managing the catalog cache synchronization.
These endpoints require admin role (cpi-admin or tenant-admin).
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user, User
from ..database import get_db as get_async_db
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
