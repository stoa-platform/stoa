"""Portal API Router - Public endpoints for Developer Portal.

Provides endpoints for the Portal to browse APIs and MCP servers.
These endpoints are available to all authenticated users (no role requirement).

The source of truth for APIs is GitLab, for MCP servers it's the database
(which is synced from GitLab via GitOps).
"""
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth.dependencies import get_current_user, User
from ..services.git_service import git_service
from ..database import get_db as get_async_db
from ..models.mcp_subscription import MCPServer, MCPServerStatus
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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


# ============================================================================
# API Catalog Endpoints
# ============================================================================

@router.get("/apis", response_model=PortalAPIsResponse)
async def list_portal_apis(
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """
    List all published APIs available in the Portal catalog.

    Source: GitLab (source of truth for API definitions)

    Returns APIs from all tenants the user has access to.
    """
    try:
        # Ensure GitLab connection
        if not git_service._project:
            await git_service.connect()

        # Get all tenants from GitLab
        all_apis = []

        try:
            tenants_tree = git_service._project.repository_tree(path="tenants", ref="main")
            for tenant_item in tenants_tree:
                if tenant_item["type"] == "tree":
                    tenant_id = tenant_item["name"]
                    tenant_apis = await git_service.list_apis(tenant_id)

                    for api in tenant_apis:
                        # Filter by status if specified
                        api_status = api.get("status", "draft")
                        if status and api_status != status:
                            continue

                        # Filter by search term
                        if search:
                            search_lower = search.lower()
                            name_match = search_lower in api.get("name", "").lower()
                            display_match = search_lower in api.get("display_name", "").lower()
                            desc_match = search_lower in api.get("description", "").lower()
                            if not (name_match or display_match or desc_match):
                                continue

                        all_apis.append({
                            **api,
                            "tenant_id": tenant_id,
                            "tenant_name": tenant_id,  # Could be enhanced with tenant display name
                        })

        except Exception as e:
            logger.warning(f"Error listing tenants from GitLab: {e}")

        # Sort by name
        all_apis.sort(key=lambda x: x.get("name", ""))

        # Paginate
        total = len(all_apis)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_apis = all_apis[start:end]

        return PortalAPIsResponse(
            apis=[
                PortalAPIResponse(
                    id=api.get("id", api.get("name", "")),
                    name=api.get("name", ""),
                    display_name=api.get("display_name", api.get("name", "")),
                    version=api.get("version", "1.0.0"),
                    description=api.get("description", ""),
                    tenant_id=api.get("tenant_id", ""),
                    tenant_name=api.get("tenant_name"),
                    status=api.get("status", "draft"),
                    backend_url=api.get("backend_url"),
                    category=api.get("category"),
                    tags=api.get("tags", []),
                    deployments=api.get("deployments", {}),
                )
                for api in paginated_apis
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
):
    """
    Get a single API by ID.

    Note: api_id format is "{tenant_id}/{api_name}" or just "{api_name}"
    """
    try:
        if not git_service._project:
            await git_service.connect()

        # Parse api_id - could be "tenant/api_name" or just "api_name"
        if "/" in api_id:
            tenant_id, api_name = api_id.split("/", 1)
        else:
            # Search across all tenants
            api_name = api_id
            tenant_id = None

            tenants_tree = git_service._project.repository_tree(path="tenants", ref="main")
            for tenant_item in tenants_tree:
                if tenant_item["type"] == "tree":
                    api = await git_service.get_api(tenant_item["name"], api_name)
                    if api:
                        tenant_id = tenant_item["name"]
                        break

        if not tenant_id:
            raise HTTPException(status_code=404, detail=f"API {api_id} not found")

        api = await git_service.get_api(tenant_id, api_name)
        if not api:
            raise HTTPException(status_code=404, detail=f"API {api_id} not found")

        return PortalAPIResponse(
            id=api.get("id", api_name),
            name=api.get("name", api_name),
            display_name=api.get("display_name", api_name),
            version=api.get("version", "1.0.0"),
            description=api.get("description", ""),
            tenant_id=tenant_id,
            tenant_name=tenant_id,
            status=api.get("status", "draft"),
            backend_url=api.get("backend_url"),
            category=api.get("category"),
            tags=api.get("tags", []),
            deployments=api.get("deployments", {}),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get API {api_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get API: {str(e)}")


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

    Source: PostgreSQL (synced from GitLab via GitOps)

    Returns only active servers that the user can see based on visibility rules.
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

        # Filter by visibility
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
        )

    except Exception as e:
        logger.error(f"Failed to list Portal MCP servers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list MCP servers: {str(e)}")


# ============================================================================
# Categories and Tags
# ============================================================================

@router.get("/api-categories", response_model=List[str])
async def get_api_categories(
    user: User = Depends(get_current_user),
):
    """Get list of available API categories."""
    # For now, return static list - can be enhanced to extract from APIs
    return ["platform", "integration", "data", "ai", "utility"]


@router.get("/api-tags", response_model=List[str])
async def get_api_tags(
    user: User = Depends(get_current_user),
):
    """Get list of available API tags."""
    # For now, return static list - can be enhanced to extract from APIs
    return ["rest", "graphql", "grpc", "websocket", "internal", "external", "beta"]


@router.get("/mcp-categories", response_model=List[str])
async def get_mcp_categories(
    user: User = Depends(get_current_user),
):
    """Get list of MCP server categories."""
    return ["platform", "tenant", "public"]
