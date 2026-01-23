"""External MCP Servers Admin Router.

Provides endpoints for:
- /v1/admin/external-mcp-servers - CRUD for external MCP servers
- /v1/internal/external-mcp-servers - Internal endpoint for MCP Gateway

Reference: External MCP Server Registration Plan
"""
import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, User
from ..database import get_db
from ..models.external_mcp_server import (
    ExternalMCPServer,
    ExternalMCPServerTool,
    ExternalMCPTransport,
    ExternalMCPAuthType,
    ExternalMCPHealthStatus,
)
from ..repositories.external_mcp_server import (
    ExternalMCPServerRepository,
    ExternalMCPServerToolRepository,
)
from ..schemas.external_mcp_server import (
    ExternalMCPServerCreate,
    ExternalMCPServerUpdate,
    ExternalMCPServerResponse,
    ExternalMCPServerDetailResponse,
    ExternalMCPServerListResponse,
    ExternalMCPServerToolResponse,
    ExternalMCPServerToolUpdate,
    TestConnectionResponse,
    SyncToolsResponse,
    TransportTypeEnum,
    AuthTypeEnum,
    HealthStatusEnum,
    ExternalMCPServerForGateway,
    ExternalMCPServersForGatewayResponse,
)
from ..services.vault_client import get_vault_client
from ..services.mcp_client import get_mcp_client_service

logger = logging.getLogger(__name__)


def _require_admin(user: User) -> None:
    """Check if user has admin access."""
    if "cpi-admin" not in user.roles and "tenant-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")


def _has_tenant_access(user: User, tenant_id: Optional[str]) -> bool:
    """Check if user has access to manage a server with given tenant_id."""
    if "cpi-admin" in user.roles:
        return True
    # Tenant admins can manage platform-wide (tenant_id=None) or their own tenant's servers
    if tenant_id is None:
        return False  # Only CPI admins can manage platform-wide servers
    return user.tenant_id == tenant_id


def _convert_server_to_response(server: ExternalMCPServer) -> ExternalMCPServerResponse:
    """Convert SQLAlchemy model to response schema."""
    return ExternalMCPServerResponse(
        id=server.id,
        name=server.name,
        display_name=server.display_name,
        description=server.description,
        icon=server.icon,
        base_url=server.base_url,
        transport=TransportTypeEnum(server.transport.value),
        auth_type=AuthTypeEnum(server.auth_type.value),
        tool_prefix=server.tool_prefix,
        enabled=server.enabled,
        health_status=HealthStatusEnum(server.health_status.value),
        last_health_check=server.last_health_check,
        last_sync_at=server.last_sync_at,
        sync_error=server.sync_error,
        tenant_id=server.tenant_id,
        tools_count=len(server.tools) if server.tools else 0,
        created_at=server.created_at,
        updated_at=server.updated_at,
        created_by=server.created_by,
    )


def _convert_server_to_detail_response(server: ExternalMCPServer) -> ExternalMCPServerDetailResponse:
    """Convert SQLAlchemy model to detail response schema with tools."""
    return ExternalMCPServerDetailResponse(
        id=server.id,
        name=server.name,
        display_name=server.display_name,
        description=server.description,
        icon=server.icon,
        base_url=server.base_url,
        transport=TransportTypeEnum(server.transport.value),
        auth_type=AuthTypeEnum(server.auth_type.value),
        tool_prefix=server.tool_prefix,
        enabled=server.enabled,
        health_status=HealthStatusEnum(server.health_status.value),
        last_health_check=server.last_health_check,
        last_sync_at=server.last_sync_at,
        sync_error=server.sync_error,
        tenant_id=server.tenant_id,
        tools_count=len(server.tools) if server.tools else 0,
        created_at=server.created_at,
        updated_at=server.updated_at,
        created_by=server.created_by,
        tools=[
            ExternalMCPServerToolResponse(
                id=tool.id,
                name=tool.name,
                namespaced_name=tool.namespaced_name,
                display_name=tool.display_name,
                description=tool.description,
                input_schema=tool.input_schema,
                enabled=tool.enabled,
                synced_at=tool.synced_at,
            )
            for tool in (server.tools or [])
        ],
    )


def _convert_tool_to_response(tool: ExternalMCPServerTool) -> ExternalMCPServerToolResponse:
    """Convert tool model to response schema."""
    return ExternalMCPServerToolResponse(
        id=tool.id,
        name=tool.name,
        namespaced_name=tool.namespaced_name,
        display_name=tool.display_name,
        description=tool.description,
        input_schema=tool.input_schema,
        enabled=tool.enabled,
        synced_at=tool.synced_at,
    )


# ============ Admin Router ============

admin_router = APIRouter(
    prefix="/v1/admin/external-mcp-servers",
    tags=["External MCP Servers - Admin"]
)


@admin_router.get("", response_model=ExternalMCPServerListResponse)
async def list_servers(
    enabled_only: bool = Query(False, description="Filter to enabled servers only"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all external MCP servers.

    CPI admins see all servers.
    Tenant admins see platform-wide servers and their tenant's servers.
    """
    _require_admin(user)

    # Determine tenant filter
    tenant_id = None if "cpi-admin" in user.roles else user.tenant_id

    repo = ExternalMCPServerRepository(db)
    servers, total = await repo.list_all(
        tenant_id=tenant_id,
        enabled_only=enabled_only,
        page=page,
        page_size=page_size,
    )

    return ExternalMCPServerListResponse(
        servers=[_convert_server_to_response(s) for s in servers],
        total_count=total,
        page=page,
        page_size=page_size,
    )


@admin_router.post("", response_model=ExternalMCPServerResponse, status_code=201)
async def create_server(
    request: ExternalMCPServerCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new external MCP server.

    Credentials are stored securely in Vault.
    """
    _require_admin(user)

    # Check tenant access
    if not _has_tenant_access(user, request.tenant_id):
        raise HTTPException(
            status_code=403,
            detail="Cannot create platform-wide servers (tenant_id=null) without CPI admin role"
        )

    repo = ExternalMCPServerRepository(db)

    # Check for duplicate name
    existing = await repo.get_by_name(request.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Server with name '{request.name}' already exists")

    # Create server model
    server = ExternalMCPServer(
        id=uuid.uuid4(),
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        icon=request.icon,
        base_url=request.base_url,
        transport=ExternalMCPTransport(request.transport.value),
        auth_type=ExternalMCPAuthType(request.auth_type.value),
        tool_prefix=request.tool_prefix,
        tenant_id=request.tenant_id,
        created_by=user.id,
    )

    # Store credentials in Vault if provided
    if request.credentials and request.auth_type != AuthTypeEnum.NONE:
        try:
            vault = get_vault_client()
            credentials_dict = request.credentials.model_dump(exclude_none=True)
            vault_path = await vault.store_credential(str(server.id), credentials_dict)
            server.credential_vault_path = vault_path
        except Exception as e:
            logger.error(f"Failed to store credentials in Vault: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to store credentials securely"
            )

    try:
        server = await repo.create(server)
        await db.commit()
        logger.info(f"Created external MCP server '{server.name}' by {user.email}")
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create external MCP server: {e}")
        raise HTTPException(status_code=500, detail="Failed to create server")

    return _convert_server_to_response(server)


@admin_router.get("/{server_id}", response_model=ExternalMCPServerDetailResponse)
async def get_server(
    server_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get external MCP server details with tools."""
    _require_admin(user)

    repo = ExternalMCPServerRepository(db)
    server = await repo.get_by_id(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not _has_tenant_access(user, server.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    return _convert_server_to_detail_response(server)


@admin_router.put("/{server_id}", response_model=ExternalMCPServerResponse)
async def update_server(
    server_id: UUID,
    request: ExternalMCPServerUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an external MCP server."""
    _require_admin(user)

    repo = ExternalMCPServerRepository(db)
    server = await repo.get_by_id(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not _has_tenant_access(user, server.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Update fields
    if request.display_name is not None:
        server.display_name = request.display_name
    if request.description is not None:
        server.description = request.description
    if request.icon is not None:
        server.icon = request.icon
    if request.base_url is not None:
        server.base_url = request.base_url
    if request.transport is not None:
        server.transport = ExternalMCPTransport(request.transport.value)
    if request.auth_type is not None:
        server.auth_type = ExternalMCPAuthType(request.auth_type.value)
    if request.tool_prefix is not None:
        server.tool_prefix = request.tool_prefix
    if request.enabled is not None:
        server.enabled = request.enabled

    # Update credentials in Vault if provided
    if request.credentials:
        try:
            vault = get_vault_client()
            credentials_dict = request.credentials.model_dump(exclude_none=True)
            vault_path = await vault.store_credential(str(server.id), credentials_dict)
            server.credential_vault_path = vault_path
        except Exception as e:
            logger.error(f"Failed to update credentials in Vault: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to update credentials securely"
            )

    try:
        server = await repo.update(server)
        await db.commit()
        logger.info(f"Updated external MCP server '{server.name}' by {user.email}")
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update external MCP server: {e}")
        raise HTTPException(status_code=500, detail="Failed to update server")

    return _convert_server_to_response(server)


@admin_router.delete("/{server_id}", status_code=204)
async def delete_server(
    server_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an external MCP server and its credentials."""
    _require_admin(user)

    repo = ExternalMCPServerRepository(db)
    server = await repo.get_by_id(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not _has_tenant_access(user, server.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete credentials from Vault
    if server.credential_vault_path:
        try:
            vault = get_vault_client()
            await vault.delete_credential(str(server.id))
        except Exception as e:
            logger.warning(f"Failed to delete credentials from Vault: {e}")
            # Continue with deletion even if Vault cleanup fails

    try:
        await repo.delete(server)
        await db.commit()
        logger.info(f"Deleted external MCP server '{server.name}' by {user.email}")
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete external MCP server: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete server")


@admin_router.post("/{server_id}/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    server_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test connection to an external MCP server."""
    _require_admin(user)

    repo = ExternalMCPServerRepository(db)
    server = await repo.get_by_id(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not _has_tenant_access(user, server.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Retrieve credentials from Vault
    credentials = None
    if server.credential_vault_path and server.auth_type != ExternalMCPAuthType.NONE:
        try:
            vault = get_vault_client()
            credentials = await vault.retrieve_credential(str(server.id))
        except Exception as e:
            logger.error(f"Failed to retrieve credentials from Vault: {e}")
            return TestConnectionResponse(
                success=False,
                error="Failed to retrieve credentials"
            )

    # Test connection
    mcp_client = get_mcp_client_service()
    result = await mcp_client.test_connection(
        base_url=server.base_url,
        transport=server.transport.value,
        auth_type=server.auth_type.value,
        credentials=credentials,
    )

    # Update health status
    health_status = (
        ExternalMCPHealthStatus.HEALTHY if result.success
        else ExternalMCPHealthStatus.UNHEALTHY
    )
    await repo.update_health_status(
        server_id=server.id,
        status=health_status,
        error=result.error,
    )
    await db.commit()

    return TestConnectionResponse(
        success=result.success,
        latency_ms=result.latency_ms,
        error=result.error,
        server_info=result.server_info,
        tools_discovered=result.tools_discovered,
    )


@admin_router.post("/{server_id}/sync-tools", response_model=SyncToolsResponse)
async def sync_tools(
    server_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Discover and sync tools from an external MCP server."""
    _require_admin(user)

    repo = ExternalMCPServerRepository(db)
    server = await repo.get_by_id(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not _has_tenant_access(user, server.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Retrieve credentials from Vault
    credentials = None
    if server.credential_vault_path and server.auth_type != ExternalMCPAuthType.NONE:
        try:
            vault = get_vault_client()
            credentials = await vault.retrieve_credential(str(server.id))
        except Exception as e:
            logger.error(f"Failed to retrieve credentials from Vault: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve credentials"
            )

    # Discover tools
    mcp_client = get_mcp_client_service()
    try:
        discovered_tools = await mcp_client.list_tools(
            base_url=server.base_url,
            transport=server.transport.value,
            auth_type=server.auth_type.value,
            credentials=credentials,
        )
    except Exception as e:
        logger.error(f"Failed to discover tools: {e}")
        await repo.set_sync_error(server.id, str(e))
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to discover tools: {e}"
        )

    # Convert to tool models with namespacing
    tool_prefix = server.tool_prefix or server.name
    tools_to_sync = []
    for tool in discovered_tools:
        namespaced_name = f"{tool_prefix}__{tool.name}" if tool_prefix else tool.name
        tools_to_sync.append(ExternalMCPServerTool(
            id=uuid.uuid4(),
            server_id=server.id,
            name=tool.name,
            namespaced_name=namespaced_name,
            display_name=tool.name.replace("_", " ").title(),
            description=tool.description,
            input_schema=tool.input_schema,
            enabled=True,
        ))

    # Sync tools
    synced_count, removed_count = await repo.sync_tools(server.id, tools_to_sync)
    await db.commit()

    # Refresh to get updated tools
    server = await repo.get_by_id(server_id)

    logger.info(
        f"Synced tools for '{server.name}': {synced_count} synced, {removed_count} removed by {user.email}"
    )

    return SyncToolsResponse(
        synced_count=synced_count,
        removed_count=removed_count,
        tools=[_convert_tool_to_response(t) for t in (server.tools or [])],
    )


@admin_router.patch("/{server_id}/tools/{tool_id}", response_model=ExternalMCPServerToolResponse)
async def update_tool(
    server_id: UUID,
    tool_id: UUID,
    request: ExternalMCPServerToolUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable a tool."""
    _require_admin(user)

    server_repo = ExternalMCPServerRepository(db)
    server = await server_repo.get_by_id(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not _has_tenant_access(user, server.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    tool_repo = ExternalMCPServerToolRepository(db)
    tool = await tool_repo.update_enabled(tool_id, request.enabled)

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    await db.commit()
    logger.info(
        f"Updated tool '{tool.name}' enabled={request.enabled} for server '{server.name}' by {user.email}"
    )

    return _convert_tool_to_response(tool)


# ============ Internal Router (for MCP Gateway) ============

internal_router = APIRouter(
    prefix="/v1/internal",
    tags=["Internal - MCP Gateway"]
)


@internal_router.get("/external-mcp-servers", response_model=ExternalMCPServersForGatewayResponse)
async def list_servers_for_gateway(
    db: AsyncSession = Depends(get_db),
    # TODO: Add service-to-service authentication
):
    """
    List all enabled external MCP servers with credentials for MCP Gateway.

    This is an internal endpoint called by MCP Gateway.
    Returns servers with decrypted credentials.
    """
    repo = ExternalMCPServerRepository(db)
    servers = await repo.list_enabled_with_tools()

    vault = get_vault_client()
    result = []

    for server in servers:
        # Retrieve credentials
        credentials = None
        if server.credential_vault_path and server.auth_type != ExternalMCPAuthType.NONE:
            try:
                credentials = await vault.retrieve_credential(str(server.id))
            except Exception as e:
                logger.warning(f"Failed to retrieve credentials for server {server.name}: {e}")

        result.append(ExternalMCPServerForGateway(
            id=server.id,
            name=server.name,
            base_url=server.base_url,
            transport=TransportTypeEnum(server.transport.value),
            auth_type=AuthTypeEnum(server.auth_type.value),
            credentials=credentials,
            tool_prefix=server.tool_prefix,
            tenant_id=server.tenant_id,
            tools=[
                ExternalMCPServerToolResponse(
                    id=tool.id,
                    name=tool.name,
                    namespaced_name=tool.namespaced_name,
                    display_name=tool.display_name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    enabled=tool.enabled,
                    synced_at=tool.synced_at,
                )
                for tool in (server.tools or []) if tool.enabled
            ],
        ))

    return ExternalMCPServersForGatewayResponse(servers=result)
