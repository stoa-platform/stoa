"""MCP GitOps Router - Endpoints for GitOps synchronization (CAB-1890).

Provides endpoints for triggering MCP server syncs from the git provider
and monitoring sync status.

These endpoints are admin-only.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import User, get_current_user
from ..config import settings
from ..database import get_db as get_async_db
from ..services.git_provider import GitProvider, get_git_provider
from ..services.mcp_sync_service import MCPSyncService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/mcp/gitops", tags=["MCP GitOps"])

_SYNC_ERROR_MAX_LEN = 200


def _scrub_sync_error(raw: str | None) -> str:
    """Strip stack traces from sync error strings before returning them over HTTP.

    Upstream services may store full tracebacks in ``MCPServer.sync_error``; this
    keeps only the first non-empty line and caps the length so CodeQL's
    ``py/stack-trace-exposure`` taint does not flow into the response body.
    """
    if not raw:
        return ""
    first_line = next((line.strip() for line in str(raw).splitlines() if line.strip()), "")
    return first_line[:_SYNC_ERROR_MAX_LEN]


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
    last_sync_at: str | None = None
    errors: list = []


class GitHealthResponse(BaseModel):
    """Git provider connection health status."""

    status: str
    project: str | None = None
    project_id: str | int | None = None
    default_branch: str | None = None
    error: str | None = None


class GitServerSummary(BaseModel):
    """Summary of a git-defined MCP server."""

    name: str | None = None
    tenant_id: str | None = None
    display_name: str | None = None
    category: str | None = None
    status: str | None = None
    tools_count: int = 0
    git_path: str | None = None


class GitServersResponse(BaseModel):
    """List of MCP servers found in the git provider."""

    total: int = 0
    servers: list[GitServerSummary] = []


# ============================================================================
# Admin Check
# ============================================================================


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require admin role for GitOps operations."""
    admin_roles = {"cpi-admin", "admin"}
    if not any(role in admin_roles for role in (user.roles or [])):
        raise HTTPException(status_code=403, detail="Admin role required for GitOps operations")
    return user


# ============================================================================
# GitOps Sync Endpoints
# ============================================================================


@router.post("/sync", response_model=SyncResponse)
async def trigger_full_sync(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
    git: GitProvider = Depends(get_git_provider),
):
    """
    Trigger a full sync of all MCP servers from git provider.

    This will:
    1. Read all MCP server definitions from git
    2. Create/update servers in the database
    3. Mark servers not in git as orphans

    Requires: cpi-admin role
    """
    logger.info(f"User {user.username} triggered full MCP GitOps sync")

    try:
        # Ensure git provider connection
        if not git.is_connected():
            await git.connect()

        # Run sync
        sync_service = MCPSyncService(git, db)
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
        raise HTTPException(status_code=500, detail=f"Sync failed: {e!s}")


@router.post("/sync/tenant/{tenant_id}", response_model=SyncResponse)
async def trigger_tenant_sync(
    tenant_id: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
    git: GitProvider = Depends(get_git_provider),
):
    """
    Trigger sync of all MCP servers for a specific tenant.

    Use tenant_id="_platform" for platform-level servers.

    Requires: cpi-admin role
    """
    logger.info(f"User {user.username} triggered MCP sync for tenant {tenant_id}")

    try:
        if not git.is_connected():
            await git.connect()

        sync_service = MCPSyncService(git, db)
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
        raise HTTPException(status_code=500, detail=f"Sync failed: {e!s}")


@router.post("/sync/server/{tenant_id}/{server_name}", response_model=SyncResponse)
async def trigger_server_sync(
    tenant_id: str,
    server_name: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
    git: GitProvider = Depends(get_git_provider),
):
    """
    Trigger sync of a specific MCP server.

    Requires: cpi-admin role
    """
    logger.info(f"User {user.username} triggered sync for MCP server {server_name}")

    try:
        if not git.is_connected():
            await git.connect()

        sync_service = MCPSyncService(git, db)
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
                message=f"Server {server_name} not found in git",
                errors=[f"Server {server_name} not found"],
            )

    except Exception as e:
        logger.error(f"Server sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {e!s}")


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
    git: GitProvider = Depends(get_git_provider),
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
        sync_service = MCPSyncService(git, db)
        status = await sync_service.get_sync_status()

        scrubbed_errors = [
            {"server": err.get("server"), "error": _scrub_sync_error(err.get("error"))}
            for err in status.get("errors", [])
        ]

        return SyncStatusResponse(
            total_servers=status.get("total_servers", 0),
            synced=status.get("synced", 0),
            pending=status.get("pending", 0),
            error=status.get("error", 0),
            orphan=status.get("orphan", 0),
            untracked=status.get("untracked", 0),
            last_sync_at=status.get("last_sync_at"),
            errors=scrubbed_errors,
        )

    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sync status")


# ============================================================================
# Git Provider Status
# ============================================================================


@router.get("/git/health", response_model=GitHealthResponse)
async def get_git_health(
    user: User = Depends(require_admin),
    git: GitProvider = Depends(get_git_provider),
):
    """
    Check git provider connection health.

    Requires: cpi-admin role
    """
    try:
        if not git.is_connected():
            await git.connect()

        project_id: str | int
        if settings.GIT_PROVIDER.lower() == "github":
            project_id = f"{settings.GITHUB_ORG}/{settings.GITHUB_CATALOG_REPO}"
        else:
            project_id = settings.GITLAB_PROJECT_ID
        repo = await git.get_repo_info(str(project_id))

        return {
            "status": "healthy",
            "project": repo.get("name"),
            "project_id": project_id,
            "default_branch": repo.get("default_branch", "main"),
        }

    except Exception:
        logger.exception("Git provider health check failed")
        return {
            "status": "unhealthy",
            "error": "Git provider connection failed. Check server logs for details.",
        }


@router.get("/git/servers", response_model=GitServersResponse)
async def list_git_servers(
    user: User = Depends(require_admin),
    git: GitProvider = Depends(get_git_provider),
):
    """
    List all MCP servers defined in git provider (before sync to DB).

    Useful for debugging and verifying git content.

    Requires: cpi-admin role
    """
    try:
        if not git.is_connected():
            await git.connect()

        servers = await git.list_all_mcp_servers()  # TODO(CAB-1889): add list_all_mcp_servers to GitProvider ABC

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
        logger.error(f"Failed to list git servers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list servers: {e!s}")
