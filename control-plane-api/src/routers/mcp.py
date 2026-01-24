"""MCP Server and Subscription routers.

Provides endpoints for:
- /v1/mcp/servers - List and browse available MCP servers
- /v1/mcp/subscriptions - Manage user's server subscriptions

Reference: PLAN-MCP-SUBSCRIPTIONS.md

Rate limits (CAB-298):
- List servers/subscriptions: 100/minute
- Create subscription: 30/minute
- Rotate key: 10/minute
- Validate API key (internal): 1000/minute

Performance optimizations:
- API key validation caching (10s TTL) to reduce DB hits
"""
import logging
import math
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, User
from ..middleware.rate_limit import limiter
from ..database import get_db
from ..services.cache_service import api_key_cache
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
    MCPServerResponse,
    MCPServerListResponse,
    MCPServerCategoryEnum,
    MCPServerVisibility,
    MCPServerToolResponse,
    MCPSubscriptionCreate,
    MCPSubscriptionResponse,
    MCPSubscriptionWithKeyResponse,
    MCPSubscriptionListResponse,
    MCPSubscriptionStatusEnum,
    MCPToolAccessStatusEnum,
    MCPToolAccessResponse,
    MCPKeyRotationRequest,
    MCPKeyRotationResponse,
)
from ..services.api_key import APIKeyService

logger = logging.getLogger(__name__)

# ============ Servers Router ============

servers_router = APIRouter(prefix="/v1/mcp/servers", tags=["MCP Servers"])


def _convert_server_to_response(server: MCPServer) -> MCPServerResponse:
    """Convert SQLAlchemy model to Pydantic response."""
    visibility_data = server.visibility or {"public": True}
    visibility = MCPServerVisibility(
        roles=visibility_data.get("roles"),
        exclude_roles=visibility_data.get("exclude_roles"),
        public=visibility_data.get("public", True),
    )

    tools = [
        MCPServerToolResponse(
            id=tool.id,
            name=tool.name,
            display_name=tool.display_name,
            description=tool.description,
            input_schema=tool.input_schema,
            enabled=tool.enabled,
            requires_approval=tool.requires_approval,
        )
        for tool in (server.tools or [])
    ]

    return MCPServerResponse(
        id=server.id,
        name=server.name,
        display_name=server.display_name,
        description=server.description,
        icon=server.icon,
        category=MCPServerCategoryEnum(server.category.value),
        tenant_id=server.tenant_id,
        visibility=visibility,
        requires_approval=server.requires_approval,
        status=server.status.value,
        version=server.version,
        documentation_url=server.documentation_url,
        tools=tools,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@servers_router.get(
    "",
    response_model=MCPServerListResponse,
    summary="List MCP servers",
    description="List available MCP servers visible to the current user based on roles and tenant.",
    responses={
        200: {"description": "List of MCP servers with pagination"},
        401: {"description": "Not authenticated"},
        429: {"description": "Rate limit exceeded"},
    },
)
@limiter.limit("100/minute")
async def list_servers(
    request: Request,
    category: Optional[MCPServerCategoryEnum] = Query(None, description="Filter by server category"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List available MCP servers visible to the current user.

    Servers are filtered based on:
    - User's roles and visibility configuration
    - User's tenant (for tenant-specific servers)
    - Server status (only active servers)
    """
    repo = MCPServerRepository(db)

    db_category = MCPServerCategory(category.value) if category else None
    servers, total = await repo.list_visible_for_user(
        user_roles=user.roles,
        tenant_id=user.tenant_id,
        category=db_category,
        page=page,
        page_size=page_size,
    )

    return MCPServerListResponse(
        servers=[_convert_server_to_response(s) for s in servers],
        total_count=total,
    )


@servers_router.get(
    "/{server_id}",
    response_model=MCPServerResponse,
    summary="Get MCP server",
    description="Get detailed information about a specific MCP server including its tools.",
    responses={
        200: {"description": "Server details with tools list"},
        401: {"description": "Not authenticated"},
        404: {"description": "Server not found"},
        429: {"description": "Rate limit exceeded"},
    },
)
@limiter.limit("100/minute")
async def get_server(
    request: Request,
    server_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get MCP server details by ID."""
    repo = MCPServerRepository(db)
    server = await repo.get_by_id(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    # TODO: Check visibility based on user roles

    return _convert_server_to_response(server)


# ============ Subscriptions Router ============

subscriptions_router = APIRouter(prefix="/v1/mcp/subscriptions", tags=["MCP Subscriptions"])


def _has_active_grace_period(subscription: MCPServerSubscription) -> bool:
    """Check if subscription has an active key grace period."""
    if not subscription.previous_key_expires_at:
        return False
    return subscription.previous_key_expires_at > datetime.utcnow()


def _convert_subscription_to_response(
    subscription: MCPServerSubscription,
    include_server: bool = True,
) -> MCPSubscriptionResponse:
    """Convert SQLAlchemy model to Pydantic response."""
    server_response = None
    if include_server and subscription.server:
        server_response = _convert_server_to_response(subscription.server)

    tool_access = [
        MCPToolAccessResponse(
            tool_id=ta.tool_id,
            tool_name=ta.tool_name,
            status=MCPToolAccessStatusEnum(ta.status.value),
            granted_at=ta.granted_at,
            granted_by=ta.granted_by,
            usage_count=ta.usage_count or 0,
            last_used_at=ta.last_used_at,
        )
        for ta in (subscription.tool_access or [])
    ]

    return MCPSubscriptionResponse(
        id=subscription.id,
        server_id=subscription.server_id,
        server=server_response,
        subscriber_id=subscription.subscriber_id,
        subscriber_email=subscription.subscriber_email,
        tenant_id=subscription.tenant_id,
        plan=subscription.plan,
        api_key_prefix=subscription.api_key_prefix,
        status=MCPSubscriptionStatusEnum(subscription.status.value),
        status_reason=subscription.status_reason,
        tool_access=tool_access,
        last_rotated_at=subscription.last_rotated_at,
        rotation_count=subscription.rotation_count or 0,
        has_active_grace_period=_has_active_grace_period(subscription),
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
        approved_at=subscription.approved_at,
        expires_at=subscription.expires_at,
        last_used_at=subscription.last_used_at,
        usage_count=subscription.usage_count or 0,
    )


@subscriptions_router.post(
    "",
    response_model=MCPSubscriptionWithKeyResponse,
    status_code=201,
    summary="Subscribe to a server",
    description="Create a subscription to an MCP server. Returns an API key (shown only once!).",
    responses={
        201: {"description": "Subscription created successfully"},
        400: {"description": "Server not available for subscriptions"},
        401: {"description": "Not authenticated"},
        404: {"description": "Server not found"},
        409: {"description": "Already subscribed to this server"},
        429: {"description": "Rate limit exceeded"},
    },
)
@limiter.limit("30/minute")
async def create_subscription(
    request: Request,
    body: MCPSubscriptionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Subscribe to an MCP server.

    Creates a new subscription. Depending on server configuration:
    - If server requires approval: status will be PENDING
    - If auto-approve enabled for user's role: status will be ACTIVE
    - Otherwise: status will be ACTIVE immediately

    **Important**: The API key is shown only once! Store it securely.
    """
    server_repo = MCPServerRepository(db)
    sub_repo = MCPSubscriptionRepository(db)
    tool_repo = MCPToolAccessRepository(db)

    # Get server
    server = await server_repo.get_by_id(body.server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if server.status != MCPServerStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Server is not available for subscriptions")

    # Check for existing subscription
    existing = await sub_repo.get_by_subscriber_and_server(user.id, body.server_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Already subscribed to this server (status: {existing.status.value})"
        )

    # Determine initial status
    initial_status = MCPSubscriptionStatus.ACTIVE
    if server.requires_approval:
        # Check auto-approve roles
        auto_approve_roles = server.auto_approve_roles or []
        if not any(role in auto_approve_roles for role in user.roles):
            initial_status = MCPSubscriptionStatus.PENDING

    # Generate API key (only if auto-approved)
    api_key = None
    api_key_hash = None
    api_key_prefix = None
    if initial_status == MCPSubscriptionStatus.ACTIVE:
        api_key, api_key_hash, api_key_prefix = APIKeyService.generate_key(prefix="stoa_mcp_")

    # Create subscription
    subscription = MCPServerSubscription(
        id=uuid.uuid4(),
        server_id=server.id,
        subscriber_id=user.id,
        subscriber_email=user.email,
        tenant_id=user.tenant_id or "default",
        plan=body.plan,
        api_key_hash=api_key_hash,
        api_key_prefix=api_key_prefix,
        status=initial_status,
    )

    try:
        subscription = await sub_repo.create(subscription)

        # Create tool access records
        requested_tool_ids = set(body.requested_tools) if body.requested_tools else None
        tool_accesses = []

        for tool in server.tools:
            if not tool.enabled:
                continue

            # If specific tools requested, filter by them
            if requested_tool_ids and tool.id not in requested_tool_ids:
                continue

            # Determine tool access status
            tool_status = MCPToolAccessStatus.ENABLED
            if tool.requires_approval and initial_status == MCPSubscriptionStatus.PENDING:
                tool_status = MCPToolAccessStatus.PENDING_APPROVAL
            elif initial_status == MCPSubscriptionStatus.PENDING:
                tool_status = MCPToolAccessStatus.PENDING_APPROVAL

            tool_access = MCPToolAccess(
                id=uuid.uuid4(),
                subscription_id=subscription.id,
                tool_id=tool.id,
                tool_name=tool.name,
                status=tool_status,
                granted_at=datetime.utcnow() if tool_status == MCPToolAccessStatus.ENABLED else None,
            )
            tool_accesses.append(tool_access)

        if tool_accesses:
            await tool_repo.create_many(tool_accesses)

        # Refresh to get tool_access
        subscription = await sub_repo.get_by_id(subscription.id)

        logger.info(
            f"Created MCP subscription {subscription.id} for server={server.name} "
            f"user={user.email} status={initial_status.value}"
        )

    except Exception as e:
        logger.error(f"Failed to create MCP subscription: {e}")
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    # Build response
    response = _convert_subscription_to_response(subscription)

    # Return with API key if created
    if api_key:
        return MCPSubscriptionWithKeyResponse(
            **response.model_dump(),
            api_key=api_key,
        )
    else:
        # For pending subscriptions, return without key
        return MCPSubscriptionWithKeyResponse(
            **response.model_dump(),
            api_key="",  # Will be generated on approval
        )


@subscriptions_router.get(
    "",
    response_model=MCPSubscriptionListResponse,
    summary="List my subscriptions",
    description="List all MCP server subscriptions for the current user.",
    responses={
        200: {"description": "List of subscriptions with pagination"},
        401: {"description": "Not authenticated"},
        429: {"description": "Rate limit exceeded"},
    },
)
@limiter.limit("100/minute")
async def list_my_subscriptions(
    request: Request,
    status: Optional[MCPSubscriptionStatusEnum] = Query(None, description="Filter by subscription status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List current user's MCP server subscriptions.

    Includes subscription status, API key prefix, and tool access details.
    """
    repo = MCPSubscriptionRepository(db)

    db_status = MCPSubscriptionStatus(status.value) if status else None
    subscriptions, total = await repo.list_by_subscriber(
        subscriber_id=user.id,
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


@subscriptions_router.get(
    "/{subscription_id}",
    response_model=MCPSubscriptionResponse,
    summary="Get subscription details",
    description="Get detailed information about a specific subscription including tool access.",
    responses={
        200: {"description": "Subscription details"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied (not owner)"},
        404: {"description": "Subscription not found"},
        429: {"description": "Rate limit exceeded"},
    },
)
@limiter.limit("100/minute")
async def get_subscription(
    request: Request,
    subscription_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get subscription details by ID."""
    repo = MCPSubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Check access: subscriber or admin
    if subscription.subscriber_id != user.id and "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Access denied")

    return _convert_subscription_to_response(subscription)


@subscriptions_router.delete(
    "/{subscription_id}",
    status_code=204,
    summary="Cancel subscription",
    description="Cancel a pending or active subscription. This is a subscriber action.",
    responses={
        204: {"description": "Subscription cancelled successfully"},
        400: {"description": "Cannot cancel subscription in current status"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied (not owner)"},
        404: {"description": "Subscription not found"},
        429: {"description": "Rate limit exceeded"},
    },
)
@limiter.limit("30/minute")
async def cancel_subscription(
    request: Request,
    subscription_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel a subscription (subscriber action).

    Subscribers can cancel their own pending or active subscriptions.
    """
    repo = MCPSubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if subscription.subscriber_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if subscription.status not in [MCPSubscriptionStatus.PENDING, MCPSubscriptionStatus.ACTIVE]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel subscription in {subscription.status.value} status"
        )

    await repo.update_status(
        subscription,
        MCPSubscriptionStatus.REVOKED,
        reason="Cancelled by subscriber",
        actor_id=user.id,
    )

    logger.info(f"MCP subscription {subscription_id} cancelled by subscriber {user.email}")


@subscriptions_router.post(
    "/{subscription_id}/rotate-key",
    response_model=MCPKeyRotationResponse,
    summary="Rotate API key",
    description="Rotate the API key for a subscription. The old key remains valid during a grace period.",
    responses={
        200: {"description": "New API key generated with grace period"},
        400: {"description": "Cannot rotate key (wrong status or rotation already in progress)"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied (not owner)"},
        404: {"description": "Subscription not found"},
        429: {"description": "Rate limit exceeded"},
    },
)
@limiter.limit("10/minute")
async def rotate_api_key(
    request: Request,
    subscription_id: UUID,
    body: MCPKeyRotationRequest = MCPKeyRotationRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Rotate the API key for a subscription with grace period.

    The old key remains valid for the specified grace period (default 24 hours).

    **Important**: The new API key is shown only once! Store it securely.
    """
    repo = MCPSubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if subscription.subscriber_id != user.id and "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Access denied")

    if subscription.status != MCPSubscriptionStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot rotate key for subscription in {subscription.status.value} status"
        )

    # Check for existing grace period
    if _has_active_grace_period(subscription):
        raise HTTPException(
            status_code=400,
            detail=f"A key rotation is already in progress. Previous key expires at "
                   f"{subscription.previous_key_expires_at.isoformat()}. "
                   f"Wait for the grace period to end before rotating again."
        )

    # Generate new key
    new_api_key, new_api_key_hash, new_api_key_prefix = APIKeyService.generate_key(prefix="stoa_mcp_")

    try:
        subscription = await repo.rotate_key(
            subscription=subscription,
            new_api_key_hash=new_api_key_hash,
            new_api_key_prefix=new_api_key_prefix,
            grace_period_hours=body.grace_period_hours,
        )

        logger.info(
            f"API key rotated for MCP subscription {subscription_id} by {user.email}. "
            f"Grace period: {body.grace_period_hours}h"
        )

        return MCPKeyRotationResponse(
            subscription_id=subscription.id,
            new_api_key=new_api_key,
            new_api_key_prefix=new_api_key_prefix,
            old_key_expires_at=subscription.previous_key_expires_at,
            grace_period_hours=body.grace_period_hours,
            rotation_count=subscription.rotation_count,
        )

    except Exception as e:
        logger.error(f"Failed to rotate API key for MCP subscription {subscription_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to rotate API key")


# ============ API Key Validation (for MCP Gateway) ============

validation_router = APIRouter(prefix="/v1/mcp/validate", tags=["MCP Validation"])


@validation_router.post(
    "/api-key",
    summary="Validate API key",
    description="Internal endpoint for MCP Gateway to validate API keys and get subscription details.",
    responses={
        200: {"description": "API key is valid, returns subscription info"},
        401: {"description": "Invalid API key format or key not found"},
        403: {"description": "Subscription is not active or has expired"},
        429: {"description": "Rate limit exceeded"},
    },
    include_in_schema=False,  # Internal endpoint
)
@limiter.limit("1000/minute")  # High limit for internal gateway calls
async def validate_api_key(
    request: Request,
    api_key: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate an MCP API key (used by MCP Gateway).

    This is an internal endpoint for the MCP Gateway to validate
    incoming API keys and get subscription/tool access details.

    Performance: Uses 10-second cache to reduce DB hits for repeated validations.
    """
    # Validate format
    if not api_key.startswith("stoa_mcp_"):
        raise HTTPException(status_code=401, detail="Invalid API key format")

    # Hash and lookup
    api_key_hash = APIKeyService.hash_key(api_key)
    cache_key = f"apikey:{api_key_hash}"

    # Check cache first (10s TTL reduces DB hits by ~90% for active keys)
    cached_response = await api_key_cache.get(cache_key)
    if cached_response is not None:
        # Return cached response for valid keys
        if cached_response.get("valid"):
            return cached_response
        # For invalid keys, re-validate (they might have been activated)

    repo = MCPSubscriptionRepository(db)

    # Try current key first
    subscription = await repo.get_by_api_key_hash(api_key_hash)
    is_previous_key = False

    # If not found, check previous key (grace period)
    if not subscription:
        subscription = await repo.get_by_previous_key_hash(api_key_hash)
        if subscription:
            is_previous_key = True
            logger.info(
                f"Using previous API key during grace period for MCP subscription {subscription.id}"
            )

    if not subscription:
        raise HTTPException(status_code=401, detail="API key not found")

    # Check status
    if subscription.status != MCPSubscriptionStatus.ACTIVE:
        raise HTTPException(
            status_code=403,
            detail=f"Subscription is {subscription.status.value}"
        )

    # Check expiration
    now = datetime.utcnow()
    if subscription.expires_at and now > subscription.expires_at:
        raise HTTPException(status_code=403, detail="Subscription expired")

    # Get enabled tools
    enabled_tools = [
        ta.tool_name for ta in subscription.tool_access
        if ta.status == MCPToolAccessStatus.ENABLED
    ]

    # Update usage tracking (async, don't block response)
    await repo.update_usage(subscription)

    # Build response
    response = {
        "valid": True,
        "subscription_id": str(subscription.id),
        "server_id": str(subscription.server_id),
        "subscriber_id": subscription.subscriber_id,
        "tenant_id": subscription.tenant_id,
        "plan": subscription.plan,
        "enabled_tools": enabled_tools,
        "using_previous_key": is_previous_key,
    }

    if is_previous_key:
        response["warning"] = "Using deprecated API key during grace period"
        response["key_expires_at"] = subscription.previous_key_expires_at.isoformat()

    # Cache successful validation (10 seconds)
    await api_key_cache.set(cache_key, response, ttl_seconds=10)

    return response
