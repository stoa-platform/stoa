"""Tenant-scoped MCP Servers router — developer self-service (CAB-1319).

Provides endpoints at /v1/tenants/{tenant_id}/mcp-servers for tenant developers
to register and manage their own external MCP servers without admin intervention.
Follows the backend_apis.py self-service pattern.
"""

import logging
import re
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..models.external_mcp_server import (
    ExternalMCPAuthType,
    ExternalMCPHealthStatus,
    ExternalMCPServer,
    ExternalMCPServerTool,
    ExternalMCPTransport,
)
from ..repositories.external_mcp_server import (
    ExternalMCPServerRepository,
    ExternalMCPServerToolRepository,
)
from ..schemas.external_mcp_server import (
    AuthTypeEnum,
    ExternalMCPServerToolResponse,
    ExternalMCPServerToolUpdate,
    HealthStatusEnum,
    SyncToolsResponse,
    TenantMCPServerCreate,
    TenantMCPServerDetailResponse,
    TenantMCPServerListResponse,
    TenantMCPServerResponse,
    TenantMCPServerUpdate,
    TestConnectionResponse,
    TransportTypeEnum,
)
from ..services.mcp_client import get_mcp_client_service
from ..services.vault_client import get_vault_client

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/mcp-servers",
    tags=["Tenant MCP Servers"],
)

# Name prefix separator for global uniqueness
_NAME_SEP = "--"


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


def _require_write_access(user: User, tenant_id: str) -> None:
    """Require write access (tenant-admin or cpi-admin)."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")
    if "cpi-admin" not in user.roles and "tenant-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Write access requires tenant-admin or cpi-admin role")


def _require_read_access(user: User, tenant_id: str) -> None:
    """Require read access (any role with tenant access)."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")


def _make_scoped_name(tenant_id: str, display_name: str) -> str:
    """Generate a globally unique name from tenant_id and display_name.

    Format: {tenant_id}--{slug} where slug is lowercased, hyphenated display_name.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
    return f"{tenant_id}{_NAME_SEP}{slug}"


def _strip_scoped_name(name: str, tenant_id: str) -> str:
    """Strip the tenant prefix from the scoped name for display."""
    prefix = f"{tenant_id}{_NAME_SEP}"
    if name.startswith(prefix):
        return name[len(prefix) :]
    return name


def _to_response(server: ExternalMCPServer, tenant_id: str) -> TenantMCPServerResponse:
    """Convert model to tenant-scoped response (never expose vault path)."""
    return TenantMCPServerResponse(
        id=server.id,
        name=_strip_scoped_name(server.name, tenant_id),
        display_name=server.display_name,
        description=server.description,
        icon=server.icon,
        base_url=server.base_url,
        transport=TransportTypeEnum(server.transport.value),
        auth_type=AuthTypeEnum(server.auth_type.value),
        has_credentials=server.credential_vault_path is not None,
        tool_prefix=server.tool_prefix,
        enabled=server.enabled,
        health_status=HealthStatusEnum(server.health_status.value),
        last_health_check=server.last_health_check,
        last_sync_at=server.last_sync_at,
        sync_error=server.sync_error,
        tools_count=len(server.tools) if server.tools else 0,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


def _to_detail_response(server: ExternalMCPServer, tenant_id: str) -> TenantMCPServerDetailResponse:
    """Convert model to tenant-scoped detail response with tools."""
    return TenantMCPServerDetailResponse(
        id=server.id,
        name=_strip_scoped_name(server.name, tenant_id),
        display_name=server.display_name,
        description=server.description,
        icon=server.icon,
        base_url=server.base_url,
        transport=TransportTypeEnum(server.transport.value),
        auth_type=AuthTypeEnum(server.auth_type.value),
        has_credentials=server.credential_vault_path is not None,
        tool_prefix=server.tool_prefix,
        enabled=server.enabled,
        health_status=HealthStatusEnum(server.health_status.value),
        last_health_check=server.last_health_check,
        last_sync_at=server.last_sync_at,
        sync_error=server.sync_error,
        tools_count=len(server.tools) if server.tools else 0,
        created_at=server.created_at,
        updated_at=server.updated_at,
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


def _ensure_tenant_owned(server: ExternalMCPServer, tenant_id: str) -> None:
    """Ensure the server belongs to this tenant (not platform-wide or other tenant)."""
    if server.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="MCP server not found")


# ============== Endpoints ==============


@router.get("", response_model=TenantMCPServerListResponse)
async def list_tenant_mcp_servers(
    tenant_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List MCP servers registered by this tenant."""
    _require_read_access(user, tenant_id)

    repo = ExternalMCPServerRepository(db)
    servers, total = await repo.list_by_tenant(tenant_id, page=page, page_size=page_size)

    return TenantMCPServerListResponse(
        servers=[_to_response(s, tenant_id) for s in servers],
        total_count=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{server_id}", response_model=TenantMCPServerDetailResponse)
async def get_tenant_mcp_server(
    tenant_id: str,
    server_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get MCP server detail with discovered tools."""
    _require_read_access(user, tenant_id)

    repo = ExternalMCPServerRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    _ensure_tenant_owned(server, tenant_id)

    return _to_detail_response(server, tenant_id)


@router.post("", response_model=TenantMCPServerResponse, status_code=201)
async def create_tenant_mcp_server(
    tenant_id: str,
    request: TenantMCPServerCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new MCP server for this tenant."""
    _require_write_access(user, tenant_id)

    repo = ExternalMCPServerRepository(db)

    # Generate scoped name for global uniqueness
    scoped_name = _make_scoped_name(tenant_id, request.display_name)

    # Check for duplicate within tenant
    existing = await repo.get_by_tenant_and_name(tenant_id, scoped_name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"MCP server '{request.display_name}' already exists in this tenant",
        )

    server = ExternalMCPServer(
        id=uuid.uuid4(),
        name=scoped_name,
        display_name=request.display_name,
        description=request.description,
        icon=request.icon,
        base_url=request.base_url,
        transport=ExternalMCPTransport(request.transport.value),
        auth_type=ExternalMCPAuthType(request.auth_type.value),
        tool_prefix=request.tool_prefix,
        tenant_id=tenant_id,
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
            logger.error("Failed to store credentials in Vault: %s", e)
            raise HTTPException(status_code=500, detail="Failed to store credentials securely")

    server = await repo.create(server)
    await db.commit()

    logger.info("Tenant MCP server created: %s/%s by %s", tenant_id, server.name, user.id)
    return _to_response(server, tenant_id)


@router.put("/{server_id}", response_model=TenantMCPServerResponse)
async def update_tenant_mcp_server(
    tenant_id: str,
    server_id: UUID,
    request: TenantMCPServerUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a tenant-owned MCP server."""
    _require_write_access(user, tenant_id)

    repo = ExternalMCPServerRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    _ensure_tenant_owned(server, tenant_id)

    if request.display_name is not None:
        server.display_name = request.display_name
        server.name = _make_scoped_name(tenant_id, request.display_name)
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

    if request.credentials:
        try:
            vault = get_vault_client()
            credentials_dict = request.credentials.model_dump(exclude_none=True)
            vault_path = await vault.store_credential(str(server.id), credentials_dict)
            server.credential_vault_path = vault_path
        except Exception as e:
            logger.error("Failed to update credentials in Vault: %s", e)
            raise HTTPException(status_code=500, detail="Failed to update credentials securely")

    server = await repo.update(server)
    await db.commit()

    logger.info("Tenant MCP server updated: %s/%s by %s", tenant_id, server.name, user.id)
    return _to_response(server, tenant_id)


@router.delete("/{server_id}", status_code=204)
async def delete_tenant_mcp_server(
    tenant_id: str,
    server_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a tenant-owned MCP server."""
    _require_write_access(user, tenant_id)

    repo = ExternalMCPServerRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    _ensure_tenant_owned(server, tenant_id)

    if server.credential_vault_path:
        try:
            vault = get_vault_client()
            await vault.delete_credential(str(server.id))
        except Exception as e:
            logger.warning("Failed to delete credentials from Vault: %s", e)

    await repo.delete(server)
    await db.commit()

    logger.info("Tenant MCP server deleted: %s/%s by %s", tenant_id, server.name, user.id)


@router.post("/{server_id}/test-connection", response_model=TestConnectionResponse)
async def test_tenant_mcp_server_connection(
    tenant_id: str,
    server_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test connection to a tenant-owned MCP server."""
    _require_read_access(user, tenant_id)
    # devops + tenant-admin + cpi-admin can test; viewer cannot
    if "cpi-admin" not in user.roles and "tenant-admin" not in user.roles and "devops" not in user.roles:
        raise HTTPException(status_code=403, detail="Test connection requires tenant-admin, devops, or cpi-admin role")

    repo = ExternalMCPServerRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    _ensure_tenant_owned(server, tenant_id)

    credentials = None
    if server.credential_vault_path and server.auth_type != ExternalMCPAuthType.NONE:
        try:
            vault = get_vault_client()
            credentials = await vault.retrieve_credential(str(server.id))
        except Exception as e:
            logger.error("Failed to retrieve credentials from Vault: %s", e)
            return TestConnectionResponse(success=False, error="Failed to retrieve credentials")

    mcp_client = get_mcp_client_service()
    result = await mcp_client.test_connection(
        base_url=server.base_url,
        transport=server.transport.value,
        auth_type=server.auth_type.value,
        credentials=credentials,
    )

    health_status = ExternalMCPHealthStatus.HEALTHY if result.success else ExternalMCPHealthStatus.UNHEALTHY
    await repo.update_health_status(server_id=server.id, status=health_status, error=result.error)
    await db.commit()

    return TestConnectionResponse(
        success=result.success,
        latency_ms=result.latency_ms,
        error=result.error,
        server_info=result.server_info,
        tools_discovered=result.tools_discovered,
    )


@router.post("/{server_id}/sync-tools", response_model=SyncToolsResponse)
async def sync_tenant_mcp_server_tools(
    tenant_id: str,
    server_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Discover and sync tools from a tenant-owned MCP server."""
    _require_write_access(user, tenant_id)

    repo = ExternalMCPServerRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    _ensure_tenant_owned(server, tenant_id)

    credentials = None
    if server.credential_vault_path and server.auth_type != ExternalMCPAuthType.NONE:
        try:
            vault = get_vault_client()
            credentials = await vault.retrieve_credential(str(server.id))
        except Exception as e:
            logger.error("Failed to retrieve credentials from Vault: %s", e)
            raise HTTPException(status_code=500, detail="Failed to retrieve credentials")

    mcp_client = get_mcp_client_service()
    try:
        discovered_tools = await mcp_client.list_tools(
            base_url=server.base_url,
            transport=server.transport.value,
            auth_type=server.auth_type.value,
            credentials=credentials,
        )
    except Exception as e:
        logger.error("Failed to discover tools: %s", e)
        await repo.set_sync_error(server.id, str(e))
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to discover tools: {e}")

    tool_prefix = server.tool_prefix or server.name
    tools_to_sync = []
    for tool in discovered_tools:
        namespaced_name = f"{tool_prefix}__{tool.name}" if tool_prefix else tool.name
        tools_to_sync.append(
            ExternalMCPServerTool(
                id=uuid.uuid4(),
                server_id=server.id,
                name=tool.name,
                namespaced_name=namespaced_name,
                display_name=tool.name.replace("_", " ").title(),
                description=tool.description,
                input_schema=tool.input_schema,
                enabled=True,
            )
        )

    synced_count, removed_count = await repo.sync_tools(server.id, tools_to_sync)
    await db.commit()

    server = await repo.get_by_id(server_id)

    logger.info(
        "Synced tools for tenant server '%s': %d synced, %d removed by %s",
        server.name,
        synced_count,
        removed_count,
        user.id,
    )

    return SyncToolsResponse(
        synced_count=synced_count,
        removed_count=removed_count,
        tools=[
            ExternalMCPServerToolResponse(
                id=t.id,
                name=t.name,
                namespaced_name=t.namespaced_name,
                display_name=t.display_name,
                description=t.description,
                input_schema=t.input_schema,
                enabled=t.enabled,
                synced_at=t.synced_at,
            )
            for t in (server.tools or [])
        ],
    )


@router.patch("/{server_id}/tools/{tool_id}", response_model=ExternalMCPServerToolResponse)
async def toggle_tenant_mcp_server_tool(
    tenant_id: str,
    server_id: UUID,
    tool_id: UUID,
    request: ExternalMCPServerToolUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable a tool on a tenant-owned MCP server."""
    _require_write_access(user, tenant_id)

    server_repo = ExternalMCPServerRepository(db)
    server = await server_repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    _ensure_tenant_owned(server, tenant_id)

    tool_repo = ExternalMCPServerToolRepository(db)
    tool = await tool_repo.update_enabled(tool_id, request.enabled)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    await db.commit()
    logger.info(
        "Tenant tool '%s' enabled=%s for server '%s' by %s",
        tool.name,
        request.enabled,
        server.name,
        user.id,
    )

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
