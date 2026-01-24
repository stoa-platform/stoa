"""MCP GitOps Router - Endpoints for GitOps synchronization.

Provides endpoints for triggering MCP server syncs from GitLab and
monitoring sync status.

These endpoints are admin-only.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime

from ..auth.dependencies import get_current_user, User
from ..services.git_service import git_service
from ..services.mcp_sync_service import MCPSyncService, SyncResult
from ..database import get_db as get_async_db
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/mcp/gitops", tags=["MCP GitOps"])


# ============================================================================
# Response Models
# ============================================================================

class SyncResponse(BaseModel):
    """Response for sync operations."""
    success: bool
    message: str
    servers_synced: int = 0
    servers_created: int = 0
    servers_updated: int = 0
    servers_orphaned: int = 0
    errors: list = []


class SyncStatusResponse(BaseModel):
    """Response for sync status."""
    total_servers: int
    synced: int
    pending: int
    error: int
    orphan: int
    untracked: int
    last_sync_at: Optional[str] = None
    errors: list = []


# ============================================================================
# Admin Check
# ============================================================================

def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require admin role for GitOps operations."""
    admin_roles = {"cpi-admin", "admin"}
    if not any(role in admin_roles for role in (user.roles or [])):
        raise HTTPException(
            status_code=403,
            detail="Admin role required for GitOps operations"
        )
    return user


# ============================================================================
# GitOps Sync Endpoints
# ============================================================================

@router.post("/sync", response_model=SyncResponse)
async def trigger_full_sync(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Trigger a full sync of all MCP servers from GitLab.

    This will:
    1. Read all MCP server definitions from GitLab
    2. Create/update servers in the database
    3. Mark servers not in GitLab as orphans

    Requires: cpi-admin role
    """
    logger.info(f"User {user.username} triggered full MCP GitOps sync")

    try:
        # Ensure GitLab connection
        if not git_service._project:
            await git_service.connect()

        # Run sync
        sync_service = MCPSyncService(git_service, db)
        result = await sync_service.sync_all_servers()

        return SyncResponse(
            success=result.success,
            message="Full sync completed" if result.success else "Sync completed with errors",
            servers_synced=result.servers_synced,
            servers_created=result.servers_created,
            servers_updated=result.servers_updated,
            servers_orphaned=result.servers_orphaned,
            errors=result.errors,
        )

    except Exception as e:
        logger.error(f"Full sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/sync/tenant/{tenant_id}", response_model=SyncResponse)
async def trigger_tenant_sync(
    tenant_id: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Trigger sync of all MCP servers for a specific tenant.

    Use tenant_id="_platform" for platform-level servers.

    Requires: cpi-admin role
    """
    logger.info(f"User {user.username} triggered MCP sync for tenant {tenant_id}")

    try:
        if not git_service._project:
            await git_service.connect()

        sync_service = MCPSyncService(git_service, db)
        result = await sync_service.sync_tenant_servers(tenant_id)

        return SyncResponse(
            success=result.success,
            message=f"Tenant {tenant_id} sync completed",
            servers_synced=result.servers_synced,
            servers_created=result.servers_created,
            servers_updated=result.servers_updated,
            servers_orphaned=result.servers_orphaned,
            errors=result.errors,
        )

    except Exception as e:
        logger.error(f"Tenant sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/sync/server/{tenant_id}/{server_name}", response_model=SyncResponse)
async def trigger_server_sync(
    tenant_id: str,
    server_name: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Trigger sync of a specific MCP server.

    Requires: cpi-admin role
    """
    logger.info(f"User {user.username} triggered sync for MCP server {server_name}")

    try:
        if not git_service._project:
            await git_service.connect()

        sync_service = MCPSyncService(git_service, db)
        server = await sync_service.sync_server(tenant_id, server_name)

        if server:
            return SyncResponse(
                success=True,
                message=f"Server {server_name} synced successfully",
                servers_synced=1,
                servers_updated=1,
            )
        else:
            return SyncResponse(
                success=False,
                message=f"Server {server_name} not found in GitLab",
                errors=[f"Server {server_name} not found"],
            )

    except Exception as e:
        logger.error(f"Server sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get current GitOps sync status.

    Shows:
    - Total servers in database
    - Count by sync status (synced, pending, error, orphan)
    - Last sync timestamp
    - Any sync errors

    Requires: cpi-admin role
    """
    try:
        sync_service = MCPSyncService(git_service, db)
        status = await sync_service.get_sync_status()

        return SyncStatusResponse(
            total_servers=status.get("total_servers", 0),
            synced=status.get("synced", 0),
            pending=status.get("pending", 0),
            error=status.get("error", 0),
            orphan=status.get("orphan", 0),
            untracked=status.get("untracked", 0),
            last_sync_at=status.get("last_sync_at"),
            errors=status.get("errors", []),
        )

    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


# ============================================================================
# GitLab Status
# ============================================================================

@router.get("/gitlab/health")
async def get_gitlab_health(
    user: User = Depends(require_admin),
):
    """
    Check GitLab connection health.

    Requires: cpi-admin role
    """
    try:
        if not git_service._project:
            await git_service.connect()

        # Try to list root directory
        tree = git_service._project.repository_tree(ref="main", per_page=1)

        return {
            "status": "healthy",
            "project": git_service._project.name,
            "project_id": git_service._project.id,
            "default_branch": "main",
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


@router.get("/gitlab/servers")
async def list_gitlab_servers(
    user: User = Depends(require_admin),
):
    """
    List all MCP servers defined in GitLab (before sync to DB).

    Useful for debugging and verifying GitLab content.

    Requires: cpi-admin role
    """
    try:
        if not git_service._project:
            await git_service.connect()

        servers = await git_service.list_all_mcp_servers()

        return {
            "total": len(servers),
            "servers": [
                {
                    "name": s.get("name"),
                    "tenant_id": s.get("tenant_id"),
                    "display_name": s.get("display_name"),
                    "category": s.get("category"),
                    "status": s.get("status"),
                    "tools_count": len(s.get("tools", [])),
                    "git_path": s.get("git_path"),
                }
                for s in servers
            ],
        }

    except Exception as e:
        logger.error(f"Failed to list GitLab servers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list servers: {str(e)}")
