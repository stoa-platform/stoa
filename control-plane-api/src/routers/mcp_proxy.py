"""MCP Gateway Proxy Router.

Proxies requests to the MCP Gateway for tools discovery and invocation.
This allows the Console UI to access MCP tools through the Control-Plane-API
which is already authenticated via webMethods Gateway.

Endpoints:
- GET /v1/mcp/tools - List all available tools
- GET /v1/mcp/tools/tags - Get all tool tags
- GET /v1/mcp/tools/categories - Get all tool categories
- GET /v1/mcp/tools/{name} - Get a specific tool
- GET /v1/mcp/tools/{name}/schema - Get tool input schema
- POST /v1/mcp/tools/{name}/invoke - Invoke a tool
"""
import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..auth import get_current_user, User
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/mcp/tools", tags=["MCP Tools"])

# MCP Gateway base URL
MCP_GATEWAY_URL = settings.MCP_GATEWAY_URL.rstrip("/")

# HTTP client for MCP Gateway
_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    """Get or create HTTP client for MCP Gateway."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            base_url=MCP_GATEWAY_URL,
            timeout=30.0,
            follow_redirects=True,
        )
    return _http_client


async def proxy_to_mcp(
    method: str,
    path: str,
    user: User,
    params: dict | None = None,
    json_body: dict | None = None,
) -> Any:
    """Proxy a request to the MCP Gateway.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: Path on MCP Gateway (e.g., /mcp/v1/tools)
        user: Authenticated user
        params: Query parameters
        json_body: JSON body for POST/PUT requests

    Returns:
        Response JSON from MCP Gateway

    Raises:
        HTTPException: If MCP Gateway returns an error
    """
    client = await get_http_client()

    # Build headers - pass user context to MCP Gateway
    headers = {
        "Content-Type": "application/json",
        "X-User-Id": user.id,
        "X-User-Email": user.email or "",
        "X-User-Roles": ",".join(user.roles or []),
        "X-Tenant-Id": user.tenant_id or "",
    }

    try:
        if method.upper() == "GET":
            response = await client.get(path, params=params, headers=headers)
        elif method.upper() == "POST":
            response = await client.post(path, json=json_body, headers=headers)
        else:
            raise HTTPException(status_code=405, detail=f"Method {method} not supported")

        # Handle MCP Gateway errors
        if response.status_code >= 400:
            logger.warning(
                "MCP Gateway returned %d for path=%s user=%s",
                response.status_code,
                path,
                user.email,
            )
            # Pass through the error from MCP Gateway
            try:
                error_detail = response.json().get("detail", response.text)
            except Exception:
                error_detail = response.text
            raise HTTPException(status_code=response.status_code, detail=error_detail)

        return response.json()

    except httpx.HTTPError as e:
        logger.error("MCP Gateway request failed: %s for path=%s", str(e), path)
        raise HTTPException(status_code=503, detail="MCP Gateway unavailable")


# =============================================================================
# Response Models
# =============================================================================

class MCPToolResponse(BaseModel):
    """MCP Tool response."""
    name: str
    description: str | None = None
    inputSchema: dict | None = None
    tags: list[str] | None = None
    tenant_id: str | None = None
    category: str | None = None


class ListToolsResponse(BaseModel):
    """List tools response."""
    tools: list[MCPToolResponse]
    cursor: str | None = None
    totalCount: int = 0


class ListTagsResponse(BaseModel):
    """List tags response."""
    tags: list[str]
    tagCounts: dict[str, int] | None = None


class ListCategoriesResponse(BaseModel):
    """List categories response."""
    categories: list[dict]


class ToolInvokeRequest(BaseModel):
    """Tool invocation request."""
    arguments: dict[str, Any]


class ToolInvokeResponse(BaseModel):
    """Tool invocation response."""
    content: list[dict] | None = None
    isError: bool = False


# =============================================================================
# Endpoints
# =============================================================================

@router.get("", response_model=ListToolsResponse)
async def list_tools(
    request: Request,
    tag: Optional[str] = Query(None, description="Filter by tag"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search in name and description"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    user: User = Depends(get_current_user),
):
    """
    List all available MCP tools.

    Proxies to MCP Gateway with user context for role-based filtering.
    """
    params = {
        "tag": tag,
        "tags": tags,
        "category": category,
        "search": search,
        "tenant_id": tenant_id,
        "cursor": cursor,
        "limit": limit,
    }
    # Remove None values
    params = {k: v for k, v in params.items() if v is not None}

    result = await proxy_to_mcp("GET", "/mcp/v1/tools", user, params=params)
    return result


@router.get("/tags", response_model=ListTagsResponse)
async def get_tool_tags(
    request: Request,
    user: User = Depends(get_current_user),
):
    """
    Get all available tool tags with counts.

    Proxies to MCP Gateway.
    """
    result = await proxy_to_mcp("GET", "/mcp/v1/tools/tags", user)
    return result


@router.get("/categories", response_model=ListCategoriesResponse)
async def get_tool_categories(
    request: Request,
    user: User = Depends(get_current_user),
):
    """
    Get all available tool categories with counts.

    Proxies to MCP Gateway.
    """
    result = await proxy_to_mcp("GET", "/mcp/v1/tools/categories", user)
    return result


@router.get("/{tool_name}", response_model=MCPToolResponse)
async def get_tool(
    request: Request,
    tool_name: str,
    user: User = Depends(get_current_user),
):
    """
    Get details of a specific tool.

    Proxies to MCP Gateway.
    """
    result = await proxy_to_mcp("GET", f"/mcp/v1/tools/{tool_name}", user)
    return result


@router.get("/{tool_name}/schema")
async def get_tool_schema(
    request: Request,
    tool_name: str,
    user: User = Depends(get_current_user),
):
    """
    Get the input schema for a tool.

    Proxies to MCP Gateway.
    """
    result = await proxy_to_mcp("GET", f"/mcp/v1/tools/{tool_name}/schema", user)
    return result


@router.post("/{tool_name}/invoke", response_model=ToolInvokeResponse)
async def invoke_tool(
    request: Request,
    tool_name: str,
    body: ToolInvokeRequest,
    user: User = Depends(get_current_user),
):
    """
    Invoke a tool with the provided arguments.

    Proxies to MCP Gateway with user context.
    """
    result = await proxy_to_mcp(
        "POST",
        f"/mcp/v1/tools/{tool_name}/invoke",
        user,
        json_body={"arguments": body.arguments},
    )
    return result
