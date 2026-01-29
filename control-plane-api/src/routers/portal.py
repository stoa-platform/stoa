"""Portal API Router - Public endpoints for Developer Portal (CAB-682 optimized).

Provides endpoints for the Portal to browse APIs and MCP servers.
These endpoints are available to all authenticated users (no role requirement).

PERFORMANCE OPTIMIZATION (CAB-682):
- APIs are now served from PostgreSQL cache instead of real-time GitLab API calls
- Latency reduced from 2-5 seconds to <200ms
- Cache is synced from GitLab via the catalog sync service
"""
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth.dependencies import get_current_user, User
from ..database import get_db as get_async_db
from ..models.mcp_subscription import MCPServer, MCPServerStatus
from ..repositories.catalog import CatalogRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/portal", tags=["Portal"])


# ============================================================================
# Response Models
# ============================================================================

class PortalAPIResponse(BaseModel):
    """API response for Portal catalog."""
    id: str
    name: str
    display_name: str
    version: str
    description: str
    tenant_id: str
    tenant_name: Optional[str] = None
    status: str
    backend_url: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = []
    deployments: dict = {}
    is_promoted: bool = True  # Whether API is promoted to Portal (portal_published=True)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class PortalAPIsResponse(BaseModel):
    """Paginated API list response."""
    apis: List[PortalAPIResponse]
    total: int
    page: int
    page_size: int


class PortalMCPServerResponse(BaseModel):
    """MCP Server response for Portal catalog."""
    id: str
    name: str
    display_name: str
    description: str
    icon: Optional[str] = None
    category: str
    tenant_id: Optional[str] = None
    status: str
    version: Optional[str] = None
    documentation_url: Optional[str] = None
    requires_approval: bool = False
    tools_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PortalMCPServersResponse(BaseModel):
    """Paginated MCP servers list response."""
    servers: List[PortalMCPServerResponse]
    total: int
    page: int
    page_size: int
    synced_at: Optional[datetime] = None  # CAB-689: Obligation #4


# ============================================================================
# API Catalog Endpoints (CAB-682: Now using PostgreSQL cache)
# ============================================================================

@router.get("/apis", response_model=PortalAPIsResponse)
async def list_portal_apis(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    include_unpromoted: bool = Query(False, description="Include APIs not promoted to Portal"),
):
    """
    List all promoted APIs available in the Portal catalog.

    Source: PostgreSQL cache (synced from GitLab)

    By default, only returns APIs with portal_published=true.
    Set include_unpromoted=true to see all APIs (for admin/debugging).

    Returns APIs from all tenants the user has access to.

    Performance: Uses PostgreSQL cache - <200ms response time.
    """
    try:
        repo = CatalogRepository(db)
        apis, total = await repo.get_portal_apis(
            category=category,
            search=search,
            status=status,
            include_unpublished=include_unpromoted,
            page=page,
            page_size=page_size,
        )

        return PortalAPIsResponse(
            apis=[
                PortalAPIResponse(
                    id=api.api_id,
                    name=api.api_name or api.api_id,
                    display_name=(api.api_metadata or {}).get("display_name", api.api_name or api.api_id),
                    version=api.version or "1.0.0",
                    description=(api.api_metadata or {}).get("description", ""),
                    tenant_id=api.tenant_id,
                    tenant_name=api.tenant_id,
                    status=api.status or "draft",
                    backend_url=(api.api_metadata or {}).get("backend_url"),
                    category=api.category,
                    tags=api.tags or [],
                    deployments=(api.api_metadata or {}).get("deployments", {}),
                    is_promoted=api.portal_published,
                )
                for api in apis
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"Failed to list Portal APIs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list APIs: {str(e)}")


@router.get("/apis/{api_id}", response_model=PortalAPIResponse)
async def get_portal_api(
    api_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get a single API by ID.

    Source: PostgreSQL cache (synced from GitLab)

    Note: api_id format is "{tenant_id}/{api_name}" or just "{api_name}"
    """
    try:
        repo = CatalogRepository(db)

        # Parse api_id - could be "tenant/api_name" or just "api_name"
        if "/" in api_id:
            tenant_id, api_name = api_id.split("/", 1)
            api = await repo.get_api_by_id(tenant_id, api_name)
        else:
            # Search across all tenants for this api_id
            api = await repo.find_api_by_name(api_id)

        if not api:
            raise HTTPException(status_code=404, detail=f"API {api_id} not found")

        metadata = api.api_metadata or {}
        return PortalAPIResponse(
            id=api.api_id,
            name=api.api_name or api.api_id,
            display_name=metadata.get("display_name", api.api_name or api.api_id),
            version=api.version or "1.0.0",
            description=metadata.get("description", ""),
            tenant_id=api.tenant_id,
            tenant_name=api.tenant_id,
            status=api.status or "draft",
            backend_url=metadata.get("backend_url"),
            category=api.category,
            tags=api.tags or [],
            deployments=metadata.get("deployments", {}),
            is_promoted=api.portal_published,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get API {api_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get API: {str(e)}")


@router.get("/apis/{api_id}/openapi")
async def get_portal_api_openapi(
    api_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get OpenAPI specification for an API.

    Source: PostgreSQL cache (synced from GitLab)

    Returns the cached OpenAPI spec (originally from openapi.yaml or openapi.json).
    """
    try:
        repo = CatalogRepository(db)

        # Parse api_id - could be "tenant/api_name" or just "api_name"
        if "/" in api_id:
            tenant_id, api_name = api_id.split("/", 1)
            api = await repo.get_api_by_id(tenant_id, api_name)
        else:
            api = await repo.find_api_by_name(api_id)

        if not api:
            raise HTTPException(status_code=404, detail=f"API {api_id} not found")

        if not api.openapi_spec:
            # Return minimal spec if not available
            return {
                "openapi": "3.0.0",
                "info": {
                    "title": api.api_name or api.api_id,
                    "version": api.version or "1.0.0"
                },
                "paths": {}
            }

        return api.openapi_spec

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get OpenAPI spec for {api_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get OpenAPI spec: {str(e)}")


# ============================================================================
# MCP Server Catalog Endpoints
# ============================================================================

@router.get("/mcp-servers", response_model=PortalMCPServersResponse)
async def list_portal_mcp_servers(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    """
    List all MCP servers available in the Portal catalog.

    Source: PostgreSQL cache (synced from GitLab via GitOps — CAB-689)

    Returns only active servers that the user can see based on visibility rules.
    Includes synced_at timestamp for cache freshness tracking.
    Falls back to Git sync if cache is empty (Obligation #3).
    """
    try:
        # Build query
        query = select(MCPServer).where(
            MCPServer.status == MCPServerStatus.ACTIVE
        ).options(selectinload(MCPServer.tools))

        # Filter by category if specified
        if category:
            from ..models.mcp_subscription import MCPServerCategory
            cat_map = {
                "platform": MCPServerCategory.PLATFORM,
                "tenant": MCPServerCategory.TENANT,
                "public": MCPServerCategory.PUBLIC,
            }
            if category in cat_map:
                query = query.where(MCPServer.category == cat_map[category])

        result = await db.execute(query)
        all_servers = result.scalars().all()

        # CAB-689 Obligation #3: Fallback if cache is empty
        if not all_servers:
            logger.warning("MCP servers cache empty, falling back to Git sync")
            try:
                from ..services.catalog_sync_service import CatalogSyncService
                from ..services.git_service import git_service
                sync_service = CatalogSyncService(db, git_service)
                await sync_service.sync_mcp_servers()
                await db.commit()

                # Re-query after sync
                result = await db.execute(query)
                all_servers = result.scalars().all()
            except Exception as sync_err:
                logger.error(f"Fallback Git sync failed: {sync_err}")

        # Filter by visibility (Obligation #6)
        visible_servers = []
        user_roles = set(user.roles or [])

        for server in all_servers:
            visibility = server.visibility or {"public": True}

            # Check if server is public
            if visibility.get("public", True):
                visible_servers.append(server)
                continue

            # Check role-based visibility
            required_roles = visibility.get("roles", [])
            exclude_roles = visibility.get("excludeRoles", [])

            # If user has any excluded role, skip
            if any(role in user_roles for role in exclude_roles):
                continue

            # If roles specified, user must have at least one
            if required_roles:
                if any(role in user_roles for role in required_roles):
                    visible_servers.append(server)
            else:
                # No specific roles required, visible to all
                visible_servers.append(server)

        # Apply search filter
        if search:
            search_lower = search.lower()
            visible_servers = [
                s for s in visible_servers
                if search_lower in s.name.lower()
                or search_lower in s.display_name.lower()
                or search_lower in (s.description or "").lower()
            ]

        # Sort by name
        visible_servers.sort(key=lambda s: s.display_name or s.name)

        # CAB-689 Obligation #4: Get last synced_at
        synced_at_result = await db.execute(
            select(func.max(MCPServer.last_synced_at))
        )
        last_synced_at = synced_at_result.scalar_one_or_none()

        # Paginate
        total = len(visible_servers)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_servers = visible_servers[start:end]

        return PortalMCPServersResponse(
            servers=[
                PortalMCPServerResponse(
                    id=str(server.id),
                    name=server.name,
                    display_name=server.display_name,
                    description=server.description or "",
                    icon=server.icon,
                    category=server.category.value,
                    tenant_id=server.tenant_id,
                    status=server.status.value,
                    version=server.version,
                    documentation_url=server.documentation_url,
                    requires_approval=server.requires_approval,
                    tools_count=len([t for t in server.tools if t.enabled]),
                    created_at=server.created_at,
                )
                for server in paginated_servers
            ],
            total=total,
            page=page,
            page_size=page_size,
            synced_at=last_synced_at,
        )

    except Exception as e:
        logger.error(f"Failed to list Portal MCP servers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list MCP servers: {str(e)}")


# ============================================================================
# Categories and Tags (CAB-682: Now from database)
# ============================================================================

@router.get("/api-categories", response_model=List[str])
async def get_api_categories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Get list of available API categories from the catalog cache."""
    try:
        repo = CatalogRepository(db)
        categories = await repo.get_categories()
        # Return sorted unique categories, add defaults if empty
        if not categories:
            return ["platform", "integration", "data", "ai", "utility"]
        return sorted(set(categories))
    except Exception as e:
        logger.warning(f"Failed to get categories from DB, using defaults: {e}")
        return ["platform", "integration", "data", "ai", "utility"]


@router.get("/api-tags", response_model=List[str])
async def get_api_tags(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Get list of available API tags from the catalog cache."""
    try:
        repo = CatalogRepository(db)
        tags = await repo.get_tags()
        if not tags:
            return ["rest", "graphql", "grpc", "websocket", "internal", "external", "beta"]
        return sorted(set(tags))
    except Exception as e:
        logger.warning(f"Failed to get tags from DB, using defaults: {e}")
        return ["rest", "graphql", "grpc", "websocket", "internal", "external", "beta"]


@router.get("/mcp-categories", response_model=List[str])
async def get_mcp_categories(
    user: User = Depends(get_current_user),
):
    """Get list of MCP server categories."""
    return ["platform", "tenant", "public"]
