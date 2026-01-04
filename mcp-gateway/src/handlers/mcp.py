"""MCP Protocol Handler.

FastAPI router for MCP endpoints.
Implements the Model Context Protocol specification.
"""

import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Header, Query, status

from ..config import get_settings
from ..metering import MeteringEvent, MeteringStatus, get_metering_producer
from ..middleware.auth import TokenClaims, get_current_user, get_optional_user
from ..models import (
    Tool,
    ToolInvocation,
    ToolResult,
    ListToolsResponse,
    ListResourcesResponse,
    ListPromptsResponse,
    InvokeToolResponse,
    ErrorResponse,
    Resource,
    Prompt,
)
from ..policy import get_opa_client
from ..services import get_tool_registry

logger = structlog.get_logger(__name__)

# Create router
router = APIRouter(prefix="/mcp/v1", tags=["MCP"])


# =============================================================================
# Tools Endpoints
# =============================================================================


@router.get(
    "/tools",
    response_model=ListToolsResponse,
    summary="List available MCP tools",
    description="Returns a list of all tools available to the authenticated user.",
)
async def list_tools(
    tenant_id: str | None = Query(None, description="Filter by tenant ID"),
    tag: str | None = Query(None, description="Filter by tag"),
    cursor: str | None = Query(None, description="Pagination cursor"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results to return"),
    user: TokenClaims | None = Depends(get_optional_user),
) -> ListToolsResponse:
    """List all available MCP tools.

    Tools are mapped from registered APIs in the STOA platform.
    Results can be filtered by tenant and tags.
    """
    registry = await get_tool_registry()

    # If user is authenticated, filter by their accessible tenants
    effective_tenant = tenant_id
    if user and tenant_id:
        # TODO: Validate user has access to requested tenant
        pass

    result = registry.list_tools(
        tenant_id=effective_tenant,
        tag=tag,
        cursor=cursor,
        limit=limit,
    )

    logger.info(
        "Listed tools",
        count=len(result.tools),
        user=user.sub if user else "anonymous",
    )

    return result


@router.get(
    "/tools/{tool_name}",
    response_model=Tool,
    summary="Get tool details",
    description="Returns detailed information about a specific tool.",
    responses={
        404: {"model": ErrorResponse, "description": "Tool not found"},
    },
)
async def get_tool(
    tool_name: str,
    user: TokenClaims | None = Depends(get_optional_user),
) -> Tool:
    """Get details of a specific tool."""
    registry = await get_tool_registry()
    tool = registry.get(tool_name)

    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool not found: {tool_name}",
        )

    return tool


@router.post(
    "/tools/{tool_name}/invoke",
    response_model=InvokeToolResponse,
    summary="Invoke a tool",
    description="Execute a tool with the provided arguments.",
    responses={
        404: {"model": ErrorResponse, "description": "Tool not found"},
        403: {"model": ErrorResponse, "description": "Access denied"},
    },
)
async def invoke_tool(
    tool_name: str,
    invocation: ToolInvocation,
    user: TokenClaims = Depends(get_current_user),
    x_consumer_id: str | None = Header(None, alias="X-Consumer-ID"),
) -> InvokeToolResponse:
    """Invoke a tool.

    Requires authentication. The tool will be executed with the user's
    permissions and credentials.
    """
    start_time = time.perf_counter()
    metering_status = MeteringStatus.SUCCESS
    error_detail: str | None = None

    registry = await get_tool_registry()
    tool = registry.get(tool_name)

    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool not found: {tool_name}",
        )

    # Check user permissions via OPA policy
    opa = await get_opa_client()
    user_claims = {
        "sub": user.sub,
        "email": user.email,
        "realm_access": {"roles": user.roles},
        "tenant_id": getattr(user, "tenant_id", None),
        "scope": getattr(user, "scope", ""),
    }
    tool_info = {
        "name": tool_name,
        "tenant_id": tool.tenant_id,
        "arguments": invocation.arguments,
    }

    allowed, reason = await opa.check_authorization(user_claims, tool_info)
    if not allowed:
        logger.warning(
            "Tool access denied by policy",
            tool_name=tool_name,
            user=user.sub,
            reason=reason,
        )
        # Emit metering event for unauthorized access
        await _emit_metering_event(
            user=user,
            tool=tool,
            tool_name=tool_name,
            start_time=start_time,
            status=MeteringStatus.UNAUTHORIZED,
            request_id=invocation.request_id,
            consumer=x_consumer_id,
            error=reason,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {reason}",
        )

    # Override tool name from path
    invocation.name = tool_name

    logger.info(
        "Invoking tool",
        tool_name=tool_name,
        user=user.sub,
        request_id=invocation.request_id,
    )

    try:
        # Get user's token for backend calls
        # Note: In production, you might want to use a service token
        # or token exchange instead of passing user's token
        result = await registry.invoke(invocation, user_token=None)
        metering_status = MeteringStatus.SUCCESS
    except Exception as e:
        metering_status = MeteringStatus.ERROR
        error_detail = str(e)
        raise
    finally:
        # Emit metering event
        await _emit_metering_event(
            user=user,
            tool=tool,
            tool_name=tool_name,
            start_time=start_time,
            status=metering_status,
            request_id=invocation.request_id,
            consumer=x_consumer_id,
            error=error_detail,
        )

    return InvokeToolResponse(
        result=result,
        tool_name=tool_name,
    )


async def _emit_metering_event(
    user: TokenClaims,
    tool: Tool,
    tool_name: str,
    start_time: float,
    status: MeteringStatus,
    request_id: str | None = None,
    consumer: str | None = None,
    error: str | None = None,
) -> None:
    """Emit a metering event for tool invocation.

    Args:
        user: Authenticated user claims
        tool: Tool being invoked
        tool_name: Name of the tool
        start_time: Start time from time.perf_counter()
        status: Outcome status
        request_id: Optional correlation ID
        consumer: Optional consumer application identifier
        error: Optional error message
    """
    try:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        tenant = getattr(user, "tenant_id", None) or "default"

        metadata = {}
        if error:
            metadata["error"] = error

        event = MeteringEvent.from_tool_invocation(
            tenant=tenant,
            user_id=user.sub,
            tool=tool_name,
            latency_ms=latency_ms,
            status=status,
            project=tool.tenant_id,
            consumer=consumer or "unknown",
            request_id=request_id,
            metadata=metadata,
        )

        producer = await get_metering_producer()
        await producer.emit(event)

        logger.debug(
            "Metering event emitted",
            event_id=str(event.event_id),
            tool=tool_name,
            latency_ms=latency_ms,
            status=status.value,
        )
    except Exception as e:
        # Don't fail the request if metering fails
        logger.error("Failed to emit metering event", error=str(e))


# =============================================================================
# Resources Endpoints
# =============================================================================


@router.get(
    "/resources",
    response_model=ListResourcesResponse,
    summary="List available MCP resources",
    description="Returns a list of all resources available to the authenticated user.",
)
async def list_resources(
    tenant_id: str | None = Query(None, description="Filter by tenant ID"),
    cursor: str | None = Query(None, description="Pagination cursor"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results to return"),
    user: TokenClaims | None = Depends(get_optional_user),
) -> ListResourcesResponse:
    """List all available MCP resources.

    Resources represent data sources that can be accessed by LLMs.
    """
    # TODO: Implement resource registry
    return ListResourcesResponse(
        resources=[],
        total_count=0,
    )


@router.get(
    "/resources/{resource_uri:path}",
    summary="Read a resource",
    description="Read the contents of a resource.",
    responses={
        404: {"model": ErrorResponse, "description": "Resource not found"},
    },
)
async def read_resource(
    resource_uri: str,
    user: TokenClaims = Depends(get_current_user),
) -> dict[str, Any]:
    """Read a resource's contents.

    Requires authentication. Resources are read with the user's permissions.
    """
    # TODO: Implement resource reading
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Resource not found: {resource_uri}",
    )


# =============================================================================
# Prompts Endpoints
# =============================================================================


@router.get(
    "/prompts",
    response_model=ListPromptsResponse,
    summary="List available MCP prompts",
    description="Returns a list of all prompt templates.",
)
async def list_prompts(
    cursor: str | None = Query(None, description="Pagination cursor"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results to return"),
    user: TokenClaims | None = Depends(get_optional_user),
) -> ListPromptsResponse:
    """List all available MCP prompts.

    Prompts are reusable templates for LLM interactions.
    """
    # TODO: Implement prompt registry
    return ListPromptsResponse(
        prompts=[],
        total_count=0,
    )


@router.get(
    "/prompts/{prompt_name}",
    summary="Get a prompt",
    description="Get a prompt template with optional argument substitution.",
    responses={
        404: {"model": ErrorResponse, "description": "Prompt not found"},
    },
)
async def get_prompt(
    prompt_name: str,
    user: TokenClaims | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Get a prompt template."""
    # TODO: Implement prompt retrieval
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Prompt not found: {prompt_name}",
    )


# =============================================================================
# Server Info Endpoints
# =============================================================================


@router.get(
    "/",
    summary="MCP Server Info",
    description="Get MCP server capabilities and version information.",
)
async def server_info() -> dict[str, Any]:
    """Get MCP server information."""
    settings = get_settings()

    return {
        "name": "stoa-mcp-gateway",
        "version": settings.app_version,
        "protocol_version": "1.0",
        "capabilities": {
            "tools": True,
            "resources": True,
            "prompts": True,
            "sampling": False,  # Not yet implemented
        },
        "instructions": (
            "STOA MCP Gateway exposes APIs as MCP tools. "
            "Use /mcp/v1/tools to discover available tools."
        ),
    }
