"""MCP Admin router for approval workflow and server management.

Provides endpoints for:
- /v1/admin/mcp/subscriptions - Admin approval/revocation of subscriptions
- /v1/admin/mcp/servers - Server CRUD (platform admins)

Reference: PLAN-MCP-SUBSCRIPTIONS.md
"""
import logging
import math
import uuid
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, User, require_permission, Permission
from ..database import get_db
from ..models.mcp_subscription import (
    MCPServer,
    MCPServerTool,
    MCPServerSubscription,
    MCPToolAccess,
    MCPServerCategory,
    MCPServerStatus,
    MCPSubscriptionStatus,
    MCPToolAccessStatus,
)
from ..repositories.mcp_subscription import (
    MCPServerRepository,
    MCPSubscriptionRepository,
    MCPToolAccessRepository,
)
from ..schemas.mcp_subscription import (
    MCPServerCreate,
    MCPServerResponse,
    MCPServerListResponse,
    MCPServerCategoryEnum,
    MCPServerStatusEnum,
    MCPServerVisibility,
    MCPServerToolCreate,
    MCPServerToolResponse,
    MCPSubscriptionApprove,
    MCPSubscriptionRevoke,
    MCPSubscriptionResponse,
    MCPSubscriptionListResponse,
    MCPSubscriptionWithKeyResponse,
    MCPSubscriptionStatusEnum,
    MCPPendingApprovalsListResponse,
    MCPPendingApprovalResponse,
    MCPSubscriptionStatsResponse,
    MCPToolAccessResponse,
)
from ..services.api_key import APIKeyService
from .mcp import _convert_server_to_response, _convert_subscription_to_response

logger = logging.getLogger(__name__)


def _require_admin(user: User) -> None:
    """Check if user has admin access."""
    if "cpi-admin" not in user.roles and "tenant-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    if user.tenant_id == tenant_id:
        return True
    return False


# ============ Admin Subscriptions Router ============

admin_subscriptions_router = APIRouter(
    prefix="/v1/admin/mcp/subscriptions",
    tags=["MCP Admin - Subscriptions"]
)


@admin_subscriptions_router.get("/pending", response_model=MCPPendingApprovalsListResponse)
async def list_pending_approvals(
    tenant_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List pending MCP subscription requests awaiting approval.

    CPI admins see all pending requests.
    Tenant admins see only their tenant's requests.
    """
    _require_admin(user)

    # Tenant admins can only see their own tenant
    effective_tenant_id = tenant_id
    if "cpi-admin" not in user.roles:
        effective_tenant_id = user.tenant_id

    repo = MCPSubscriptionRepository(db)
    subscriptions, total = await repo.list_pending(
        tenant_id=effective_tenant_id,
        page=page,
        page_size=page_size,
    )

    items = []
    for sub in subscriptions:
        items.append(MCPPendingApprovalResponse(
            subscription=_convert_subscription_to_response(sub),
            server_name=sub.server.name if sub.server else "unknown",
            server_display_name=sub.server.display_name if sub.server else "Unknown",
            requested_at=sub.created_at,
            subscriber_email=sub.subscriber_email,
        ))

    return MCPPendingApprovalsListResponse(
        items=items,
        total=total,
    )


@admin_subscriptions_router.get("/tenant/{tenant_id}", response_model=MCPSubscriptionListResponse)
async def list_tenant_subscriptions(
    tenant_id: str,
    status: Optional[MCPSubscriptionStatusEnum] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all MCP subscriptions for a tenant.

    Used by tenant admins to view and manage their tenant's subscriptions.
    """
    _require_admin(user)

    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = MCPSubscriptionRepository(db)

    db_status = MCPSubscriptionStatus(status.value) if status else None
    subscriptions, total = await repo.list_by_tenant(
        tenant_id=tenant_id,
        status=db_status,
        page=page,
        page_size=page_size,
    )

    return MCPSubscriptionListResponse(
        items=[_convert_subscription_to_response(s) for s in subscriptions],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@admin_subscriptions_router.post("/{subscription_id}/approve", response_model=MCPSubscriptionWithKeyResponse)
async def approve_subscription(
    subscription_id: UUID,
    request: MCPSubscriptionApprove = MCPSubscriptionApprove(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a pending MCP subscription.

    Generates an API key and activates the subscription.
    Returns the API key (shown only once!).
    """
    _require_admin(user)

    repo = MCPSubscriptionRepository(db)
    tool_repo = MCPToolAccessRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if subscription.status != MCPSubscriptionStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve subscription in {subscription.status.value} status"
        )

    # Generate API key
    api_key, api_key_hash, api_key_prefix = APIKeyService.generate_key(prefix="stoa_mcp_")

    # Set API key
    await repo.set_api_key(
        subscription,
        api_key_hash=api_key_hash,
        api_key_prefix=api_key_prefix,
    )

    # Set expiration if provided
    if request.expires_at:
        await repo.set_expiration(subscription, request.expires_at)

    # Update tool access to ENABLED
    for tool_access in subscription.tool_access:
        if request.approved_tools is None or tool_access.tool_id in request.approved_tools:
            await tool_repo.update_status(
                tool_access,
                MCPToolAccessStatus.ENABLED,
                actor_id=user.id,
            )
        else:
            await tool_repo.update_status(
                tool_access,
                MCPToolAccessStatus.DISABLED,
                actor_id=user.id,
            )

    # Activate subscription
    subscription = await repo.update_status(
        subscription,
        MCPSubscriptionStatus.ACTIVE,
        actor_id=user.id,
    )

    # Refresh to get updated relations
    subscription = await repo.get_by_id(subscription_id)

    logger.info(
        f"MCP subscription {subscription_id} approved by {user.email} "
        f"for server={subscription.server.name if subscription.server else 'unknown'}"
    )

    response = _convert_subscription_to_response(subscription)
    return MCPSubscriptionWithKeyResponse(
        **response.model_dump(),
        api_key=api_key,
    )


@admin_subscriptions_router.post("/{subscription_id}/revoke", response_model=MCPSubscriptionResponse)
async def revoke_subscription(
    subscription_id: UUID,
    request: MCPSubscriptionRevoke,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke an MCP subscription.

    Permanently revokes a subscription. The API key will no longer work.
    """
    _require_admin(user)

    repo = MCPSubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if subscription.status == MCPSubscriptionStatus.REVOKED:
        raise HTTPException(status_code=400, detail="Subscription already revoked")

    subscription = await repo.update_status(
        subscription,
        MCPSubscriptionStatus.REVOKED,
        reason=request.reason,
        actor_id=user.id,
    )

    logger.info(
        f"MCP subscription {subscription_id} revoked by {user.email} "
        f"reason={request.reason}"
    )

    return _convert_subscription_to_response(subscription)


@admin_subscriptions_router.post("/{subscription_id}/suspend", response_model=MCPSubscriptionResponse)
async def suspend_subscription(
    subscription_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Temporarily suspend an MCP subscription.

    Can be reactivated later.
    """
    _require_admin(user)

    repo = MCPSubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if subscription.status != MCPSubscriptionStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot suspend subscription in {subscription.status.value} status"
        )

    subscription = await repo.update_status(
        subscription,
        MCPSubscriptionStatus.SUSPENDED,
        reason="Suspended by admin",
        actor_id=user.id,
    )

    logger.info(f"MCP subscription {subscription_id} suspended by {user.email}")

    return _convert_subscription_to_response(subscription)


@admin_subscriptions_router.post("/{subscription_id}/reactivate", response_model=MCPSubscriptionResponse)
async def reactivate_subscription(
    subscription_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Reactivate a suspended MCP subscription.
    """
    _require_admin(user)

    repo = MCPSubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if subscription.status != MCPSubscriptionStatus.SUSPENDED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reactivate subscription in {subscription.status.value} status"
        )

    subscription = await repo.update_status(
        subscription,
        MCPSubscriptionStatus.ACTIVE,
        reason="Reactivated by admin",
        actor_id=user.id,
    )

    logger.info(f"MCP subscription {subscription_id} reactivated by {user.email}")

    return _convert_subscription_to_response(subscription)


@admin_subscriptions_router.get("/stats", response_model=MCPSubscriptionStatsResponse)
async def get_subscription_stats(
    tenant_id: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get MCP subscription statistics.
    """
    _require_admin(user)

    # Tenant admins can only see their own tenant
    effective_tenant_id = tenant_id
    if "cpi-admin" not in user.roles:
        effective_tenant_id = user.tenant_id

    sub_repo = MCPSubscriptionRepository(db)
    server_repo = MCPServerRepository(db)

    stats = await sub_repo.get_stats(tenant_id=effective_tenant_id)

    # Get server count
    servers, total_servers = await server_repo.list_all(page=1, page_size=1)

    return MCPSubscriptionStatsResponse(
        total_servers=total_servers,
        total_subscriptions=stats["total_subscriptions"],
        by_status=stats["by_status"],
        by_server=stats["by_server"],
        recent_24h=stats["recent_24h"],
    )


# ============ Admin Servers Router ============

admin_servers_router = APIRouter(
    prefix="/v1/admin/mcp/servers",
    tags=["MCP Admin - Servers"]
)


@admin_servers_router.get("", response_model=MCPServerListResponse)
async def list_all_servers(
    category: Optional[MCPServerCategoryEnum] = None,
    status: Optional[MCPServerStatusEnum] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all MCP servers (admin view).

    Shows all servers regardless of visibility configuration.
    """
    _require_admin(user)

    repo = MCPServerRepository(db)

    db_category = MCPServerCategory(category.value) if category else None
    db_status = MCPServerStatus(status.value) if status else None

    servers, total = await repo.list_all(
        category=db_category,
        status=db_status,
        page=page,
        page_size=page_size,
    )

    return MCPServerListResponse(
        servers=[_convert_server_to_response(s) for s in servers],
        total_count=total,
    )


@admin_servers_router.post("", response_model=MCPServerResponse, status_code=201)
async def create_server(
    request: MCPServerCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new MCP server.

    CPI admins can create servers of any category.
    Tenant admins can only create tenant-specific servers.
    """
    _require_admin(user)

    # Tenant admins can only create tenant servers
    if "cpi-admin" not in user.roles:
        if request.category != MCPServerCategoryEnum.TENANT:
            raise HTTPException(
                status_code=403,
                detail="Tenant admins can only create tenant-specific servers"
            )
        if request.tenant_id and request.tenant_id != user.tenant_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot create server for another tenant"
            )

    repo = MCPServerRepository(db)

    # Check for existing server with same name
    existing = await repo.get_by_name(request.name)
    if existing:
        raise HTTPException(status_code=409, detail="Server with this name already exists")

    # Build visibility JSON
    visibility = {
        "public": request.visibility.public,
        "roles": request.visibility.roles,
        "exclude_roles": request.visibility.exclude_roles,
    }

    server = MCPServer(
        id=uuid.uuid4(),
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        icon=request.icon,
        category=MCPServerCategory(request.category.value),
        tenant_id=request.tenant_id or user.tenant_id,
        visibility=visibility,
        requires_approval=request.requires_approval,
        auto_approve_roles=request.auto_approve_roles,
        status=MCPServerStatus.ACTIVE,
        version=request.version,
        documentation_url=request.documentation_url,
    )

    try:
        server = await repo.create(server)
        logger.info(f"Created MCP server {server.name} by {user.email}")
    except Exception as e:
        logger.error(f"Failed to create MCP server: {e}")
        raise HTTPException(status_code=500, detail="Failed to create server")

    return _convert_server_to_response(server)


@admin_servers_router.post("/{server_id}/tools", response_model=MCPServerToolResponse, status_code=201)
async def add_tool_to_server(
    server_id: UUID,
    request: MCPServerToolCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a tool to an MCP server.
    """
    _require_admin(user)

    repo = MCPServerRepository(db)
    server = await repo.get_by_id(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    # Check tenant access
    if "cpi-admin" not in user.roles and server.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check for existing tool with same name
    for tool in server.tools:
        if tool.name == request.name:
            raise HTTPException(status_code=409, detail="Tool with this name already exists")

    tool = MCPServerTool(
        id=uuid.uuid4(),
        server_id=server.id,
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        input_schema=request.input_schema,
        enabled=request.enabled,
        requires_approval=request.requires_approval,
    )

    db.add(tool)
    await db.flush()
    await db.refresh(tool)

    logger.info(f"Added tool {tool.name} to server {server.name} by {user.email}")

    return MCPServerToolResponse(
        id=tool.id,
        name=tool.name,
        display_name=tool.display_name,
        description=tool.description,
        input_schema=tool.input_schema,
        enabled=tool.enabled,
        requires_approval=tool.requires_approval,
    )


@admin_servers_router.patch("/{server_id}/status")
async def update_server_status(
    server_id: UUID,
    status: MCPServerStatusEnum,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update MCP server status.
    """
    _require_admin(user)

    repo = MCPServerRepository(db)
    server = await repo.get_by_id(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if "cpi-admin" not in user.roles and server.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    server.status = MCPServerStatus(status.value)
    await repo.update(server)

    logger.info(f"Updated server {server.name} status to {status.value} by {user.email}")

    return _convert_server_to_response(server)


@admin_servers_router.delete("/{server_id}", status_code=204)
async def delete_server(
    server_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete an MCP server.

    This will also delete all associated subscriptions.
    """
    _require_admin(user)

    # Only CPI admins can delete servers
    if "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Only CPI admins can delete servers")

    repo = MCPServerRepository(db)
    server = await repo.get_by_id(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    await repo.delete(server)

    logger.info(f"Deleted MCP server {server.name} by {user.email}")
