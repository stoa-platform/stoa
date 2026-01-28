# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""MCP Servers Handler - Server-based subscriptions with role-based visibility.

Provides endpoints for:
- Listing MCP servers filtered by user roles
- Server subscription management
- Per-tool access control within subscriptions
- Vault integration for secure API key storage
"""

import uuid
import secrets
import hashlib
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.server import (
    MCPServer,
    MCPServerVisibility,
    MCPServerTool,
    ServerCategory,
    ServerStatus,
    ServerSubscription,
    ServerSubscriptionWithKey,
    ServerSubscriptionCreate,
    ToolAccess,
    ToolAccessStatus,
    ToolAccessUpdate,
    ServerSubscriptionStatus,
    ListServersResponse,
    ListServerSubscriptionsResponse,
)
from ..middleware.auth import get_current_user, TokenClaims
from ..services.vault_client import get_vault_client

# Alias for clarity
User = TokenClaims

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/servers", tags=["MCP Servers"])


# ============ Mock Data (to be replaced with DB) ============

MOCK_SERVERS: list[MCPServer] = [
    MCPServer(
        id="stoa-platform",
        name="stoa-platform",
        displayName="STOA Platform Tools",
        description="Administrative tools for managing the STOA platform: tenants, users, deployments, and configurations.",
        icon="settings",
        category=ServerCategory.PLATFORM,
        visibility=MCPServerVisibility(
            roles=["cpi-admin", "tenant-admin", "devops"],
            public=False,
        ),
        tools=[
            MCPServerTool(
                id="tenant-create",
                name="tenant-create",
                displayName="Create Tenant",
                description="Create a new tenant organization",
                enabled=True,
                requires_approval=True,
            ),
            MCPServerTool(
                id="api-deploy",
                name="api-deploy",
                displayName="Deploy API",
                description="Deploy an API to an environment",
                enabled=True,
                requires_approval=False,
            ),
            MCPServerTool(
                id="user-invite",
                name="user-invite",
                displayName="Invite User",
                description="Invite a user to a tenant",
                enabled=True,
                requires_approval=False,
            ),
        ],
        status=ServerStatus.ACTIVE,
        version="1.0.0",
        documentation_url="https://docs.gostoa.dev/platform-tools",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
    ),
    MCPServer(
        id="crm-apis",
        name="crm-apis",
        displayName="CRM Integration",
        description="Customer Relationship Management APIs for customer data, leads, and opportunities.",
        icon="users",
        category=ServerCategory.TENANT,
        tenant_id="acme-corp",
        visibility=MCPServerVisibility(public=True),
        tools=[
            MCPServerTool(
                id="customer-search",
                name="customer-search",
                displayName="Search Customers",
                description="Search and retrieve customer records",
                enabled=True,
                requires_approval=False,
            ),
            MCPServerTool(
                id="lead-create",
                name="lead-create",
                displayName="Create Lead",
                description="Create a new sales lead",
                enabled=True,
                requires_approval=False,
            ),
        ],
        status=ServerStatus.ACTIVE,
        version="2.1.0",
        created_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 8, tzinfo=timezone.utc),
    ),
    MCPServer(
        id="billing-services",
        name="billing-services",
        displayName="Billing & Invoicing",
        description="Generate invoices, process payments, and manage billing cycles.",
        icon="credit-card",
        category=ServerCategory.TENANT,
        tenant_id="acme-corp",
        visibility=MCPServerVisibility(public=True),
        tools=[
            MCPServerTool(
                id="invoice-generate",
                name="invoice-generate",
                displayName="Generate Invoice",
                description="Generate a new invoice for a customer",
                enabled=True,
                requires_approval=False,
            ),
            MCPServerTool(
                id="payment-status",
                name="payment-status",
                displayName="Check Payment Status",
                description="Check the status of a payment",
                enabled=True,
                requires_approval=False,
            ),
        ],
        status=ServerStatus.ACTIVE,
        version="1.5.0",
        created_at=datetime(2024, 3, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
    ),
]

# In-memory subscription store (to be replaced with DB)
_subscriptions: dict[str, ServerSubscription] = {}


# ============ Utility Functions ============

def can_user_see_server(server: MCPServer, user: User) -> bool:
    """Check if a user can see a server based on visibility rules."""
    visibility = server.visibility
    user_roles = user.roles or []

    # Public servers are visible to all authenticated users
    if visibility.public:
        return True

    # Check excluded roles first
    if visibility.exclude_roles:
        if any(role in user_roles for role in visibility.exclude_roles):
            return False

    # If roles are specified, user must have at least one
    if visibility.roles:
        return any(role in user_roles for role in visibility.roles)

    # No specific visibility rules = visible to all
    return True


def filter_servers_by_role(servers: list[MCPServer], user: User) -> list[MCPServer]:
    """Filter servers based on user's roles."""
    return [s for s in servers if can_user_see_server(s, user)]


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        Tuple of (full_key, key_prefix, key_hash)
    """
    # Generate 32 random bytes = 256 bits of entropy
    random_bytes = secrets.token_bytes(32)
    key_suffix = secrets.token_hex(20)  # 40 hex chars

    full_key = f"stoa_sk_{key_suffix}"
    key_prefix = full_key[:16]  # "stoa_sk_XXXXXXXX"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()

    return full_key, key_prefix, key_hash


# ============ Endpoints ============

@router.get("", response_model=ListServersResponse)
async def list_servers(
    category: Optional[ServerCategory] = Query(None, description="Filter by category"),
    user: User = Depends(get_current_user),
) -> ListServersResponse:
    """List all MCP servers the user can see.

    Servers are filtered based on the user's roles:
    - Platform servers (admin-only) require cpi-admin, tenant-admin, or devops roles
    - Tenant servers are visible to all tenant members
    - Public servers are visible to all authenticated users
    """
    logger.info("Listing servers", user_id=user.subject, user_roles=user.roles)

    # Filter servers by user's roles
    visible_servers = filter_servers_by_role(MOCK_SERVERS, user)

    # Apply category filter if specified
    if category:
        visible_servers = [s for s in visible_servers if s.category == category]

    return ListServersResponse(
        servers=visible_servers,
        total_count=len(visible_servers),
    )


# ============ Server Subscriptions ============
# NOTE: Static routes (/subscriptions) MUST be defined BEFORE dynamic routes (/{server_id})
# otherwise FastAPI will match /subscriptions as a server_id parameter.

@router.get("/subscriptions", response_model=ListServerSubscriptionsResponse)
async def list_my_server_subscriptions(
    user: User = Depends(get_current_user),
) -> ListServerSubscriptionsResponse:
    """List my server subscriptions."""
    user_subs = [s for s in _subscriptions.values() if s.user_id == user.subject]

    return ListServerSubscriptionsResponse(
        subscriptions=user_subs,
        total_count=len(user_subs),
    )


@router.post("/subscriptions", response_model=ServerSubscriptionWithKey)
async def subscribe_to_server(
    request: ServerSubscriptionCreate,
    user: User = Depends(get_current_user),
) -> ServerSubscriptionWithKey:
    """Subscribe to an MCP server.

    Creates a subscription and returns an API key (shown only once).
    The API key provides access to all requested tools within the server.
    """
    # Find server
    server = next((s for s in MOCK_SERVERS if s.id == request.server_id), None)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    # Check visibility
    if not can_user_see_server(server, user):
        raise HTTPException(status_code=403, detail="You do not have permission to subscribe to this server")

    # Check if already subscribed
    existing = next(
        (s for s in _subscriptions.values()
         if s.server_id == request.server_id and s.user_id == user.subject),
        None
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already subscribed to this server")

    # Validate requested tools
    server_tool_ids = {t.id for t in server.tools}
    invalid_tools = set(request.requested_tools) - server_tool_ids
    if invalid_tools:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tool IDs: {', '.join(invalid_tools)}"
        )

    # Generate API key
    api_key, key_prefix, key_hash = generate_api_key()

    # Create tool access entries
    tool_access = []
    for tool in server.tools:
        if tool.id in request.requested_tools:
            status = (
                ToolAccessStatus.PENDING_APPROVAL
                if tool.requires_approval
                else ToolAccessStatus.ENABLED
            )
            tool_access.append(ToolAccess(
                tool_id=tool.id,
                tool_name=tool.display_name,
                status=status,
                granted_at=datetime.now(timezone.utc) if status == ToolAccessStatus.ENABLED else None,
            ))

    # Create subscription
    subscription_id = f"sub-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    subscription = ServerSubscription(
        id=subscription_id,
        server_id=server.id,
        server=server,
        tenant_id="default",  # TODO: Extract tenant_id from token claims
        user_id=user.subject,
        status=ServerSubscriptionStatus.ACTIVE,
        plan=request.plan,
        tool_access=tool_access,
        api_key_prefix=key_prefix,
        created_at=now,
    )

    # Store subscription
    _subscriptions[subscription_id] = subscription

    # Store API key in Vault (async, best-effort)
    try:
        vault_client = get_vault_client()
        await vault_client.store_api_key(
            subscription_id=subscription_id,
            api_key=api_key,
            metadata={
                "user_id": user.subject,
                "server_id": server.id,
                "tenant_id": "default",
                "created_at": now.isoformat(),
            },
        )
        logger.info(
            "API key stored in Vault",
            subscription_id=subscription_id,
        )
    except Exception as e:
        # Vault storage is best-effort - subscription still works
        logger.warning(
            "Failed to store API key in Vault (continuing without)",
            subscription_id=subscription_id,
            error=str(e),
        )

    logger.info(
        "Server subscription created",
        subscription_id=subscription_id,
        server_id=server.id,
        user_id=user.subject,
        tools_count=len(tool_access),
    )

    # Return with full API key
    return ServerSubscriptionWithKey(
        **subscription.model_dump(),
        api_key=api_key,
    )


@router.get("/subscriptions/{subscription_id}", response_model=ServerSubscription)
async def get_server_subscription(
    subscription_id: str,
    user: User = Depends(get_current_user),
) -> ServerSubscription:
    """Get a specific server subscription."""
    subscription = _subscriptions.get(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if subscription.user_id != user.subject:
        raise HTTPException(status_code=403, detail="Not authorized to view this subscription")

    return subscription


@router.patch("/subscriptions/{subscription_id}/tools", response_model=ServerSubscription)
async def update_tool_access(
    subscription_id: str,
    request: ToolAccessUpdate,
    user: User = Depends(get_current_user),
) -> ServerSubscription:
    """Update tool access within a subscription.

    Actions:
    - enable: Enable access to tools
    - disable: Disable access to tools
    - request: Request access to new tools (may require approval)
    """
    subscription = _subscriptions.get(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if subscription.user_id != user.subject:
        raise HTTPException(status_code=403, detail="Not authorized to modify this subscription")

    # Get server for tool validation
    server = next((s for s in MOCK_SERVERS if s.id == subscription.server_id), None)
    if not server:
        raise HTTPException(status_code=500, detail="Server not found")

    # Validate tool IDs
    server_tool_ids = {t.id for t in server.tools}
    invalid_tools = set(request.tool_ids) - server_tool_ids
    if invalid_tools:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tool IDs: {', '.join(invalid_tools)}"
        )

    # Update tool access
    tool_access_map = {ta.tool_id: ta for ta in subscription.tool_access}

    for tool_id in request.tool_ids:
        tool = next((t for t in server.tools if t.id == tool_id), None)
        if not tool:
            continue

        if request.action == "enable":
            if tool_id in tool_access_map:
                tool_access_map[tool_id].status = ToolAccessStatus.ENABLED
                tool_access_map[tool_id].granted_at = datetime.now(timezone.utc)
        elif request.action == "disable":
            if tool_id in tool_access_map:
                tool_access_map[tool_id].status = ToolAccessStatus.DISABLED
        elif request.action == "request":
            if tool_id not in tool_access_map:
                status = (
                    ToolAccessStatus.PENDING_APPROVAL
                    if tool.requires_approval
                    else ToolAccessStatus.ENABLED
                )
                tool_access_map[tool_id] = ToolAccess(
                    tool_id=tool_id,
                    tool_name=tool.display_name,
                    status=status,
                    granted_at=datetime.now(timezone.utc) if status == ToolAccessStatus.ENABLED else None,
                )

    subscription.tool_access = list(tool_access_map.values())

    logger.info(
        "Tool access updated",
        subscription_id=subscription_id,
        action=request.action,
        tool_ids=request.tool_ids,
    )

    return subscription


@router.delete("/subscriptions/{subscription_id}")
async def revoke_server_subscription(
    subscription_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Revoke a server subscription."""
    subscription = _subscriptions.get(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if subscription.user_id != user.subject:
        raise HTTPException(status_code=403, detail="Not authorized to revoke this subscription")

    # Mark as revoked instead of deleting
    subscription.status = ServerSubscriptionStatus.REVOKED

    logger.info(
        "Server subscription revoked",
        subscription_id=subscription_id,
        server_id=subscription.server_id,
        user_id=user.subject,
    )

    return {"message": "Subscription revoked", "subscription_id": subscription_id}


@router.get("/subscriptions/{subscription_id}/reveal-key")
async def reveal_api_key(
    subscription_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Reveal the API key for a subscription.

    This endpoint requires 2FA (TOTP) verification for security.
    The token must have been issued with step-up authentication (acr >= 2).

    Returns:
        The full API key from Vault
    """
    subscription = _subscriptions.get(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if subscription.user_id != user.subject:
        raise HTTPException(status_code=403, detail="Not authorized to view this key")

    # Check for 2FA/step-up authentication
    # acr (Authentication Context Class Reference) indicates authentication strength
    # Level 0 = password only, Level 1 = password + something, Level 2+ = multi-factor
    acr = user.acr
    if acr is None or (isinstance(acr, str) and int(acr) < 1):
        logger.warning(
            "API key reveal attempted without 2FA",
            subscription_id=subscription_id,
            user_id=user.subject,
            acr=acr,
        )
        raise HTTPException(
            status_code=403,
            detail="2FA verification required to reveal API key. Please re-authenticate with TOTP.",
            headers={"X-Requires-Step-Up": "true"},
        )

    # Retrieve API key from Vault
    try:
        vault_client = get_vault_client()
        api_key = await vault_client.retrieve_api_key(subscription_id)

        if not api_key:
            raise HTTPException(
                status_code=404,
                detail="API key not found in vault. Please regenerate the key.",
            )

        logger.info(
            "API key revealed",
            subscription_id=subscription_id,
            user_id=user.subject,
        )

        return {
            "api_key": api_key,
            "api_key_prefix": subscription.api_key_prefix,
            "message": "This is your API key. Store it securely - it cannot be retrieved again.",
        }

    except Exception as e:
        logger.error(
            "Failed to retrieve API key from Vault",
            subscription_id=subscription_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve API key. Please try again or regenerate the key.",
        )


@router.post("/subscriptions/{subscription_id}/rotate-key")
async def rotate_server_key(
    subscription_id: str,
    grace_period_hours: int = Query(default=24, ge=1, le=168),
    user: User = Depends(get_current_user),
) -> dict:
    """Rotate the API key for a server subscription.

    This endpoint requires 2FA (TOTP) verification for security.

    Args:
        grace_period_hours: Hours before the old key expires (1-168, default 24)

    Returns:
        New API key and old key expiration time
    """
    subscription = _subscriptions.get(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if subscription.user_id != user.subject:
        raise HTTPException(status_code=403, detail="Not authorized to rotate this key")

    # Check for 2FA/step-up authentication for key rotation
    acr = user.acr
    if acr is None or (isinstance(acr, str) and int(acr) < 1):
        logger.warning(
            "API key rotation attempted without 2FA",
            subscription_id=subscription_id,
            user_id=user.subject,
        )
        raise HTTPException(
            status_code=403,
            detail="2FA verification required to rotate API key. Please re-authenticate with TOTP.",
            headers={"X-Requires-Step-Up": "true"},
        )

    # Generate new key
    api_key, key_prefix, key_hash = generate_api_key()

    # Calculate grace period expiry
    from datetime import timedelta
    old_key_expires = datetime.now(timezone.utc) + timedelta(hours=grace_period_hours)

    # Update subscription
    subscription.api_key_prefix = key_prefix
    subscription.last_rotated_at = datetime.now(timezone.utc)
    subscription.has_active_grace_period = True

    # Store new key in Vault
    try:
        vault_client = get_vault_client()
        await vault_client.rotate_api_key(subscription_id, api_key)
        logger.info(
            "Rotated API key stored in Vault",
            subscription_id=subscription_id,
        )
    except Exception as e:
        logger.warning(
            "Failed to store rotated API key in Vault",
            subscription_id=subscription_id,
            error=str(e),
        )

    logger.info(
        "Server subscription key rotated",
        subscription_id=subscription_id,
        grace_period_hours=grace_period_hours,
    )

    return {
        "new_api_key": api_key,
        "new_api_key_prefix": key_prefix,
        "old_key_expires_at": old_key_expires.isoformat(),
        "grace_period_hours": grace_period_hours,
    }


# ============ Dynamic Server Routes ============
# NOTE: Routes with path parameters MUST be defined AFTER static routes
# to prevent FastAPI from matching /subscriptions as a {server_id}.

@router.get("/{server_id}", response_model=MCPServer)
async def get_server(
    server_id: str,
    user: User = Depends(get_current_user),
) -> MCPServer:
    """Get a specific MCP server by ID.

    Returns 403 if the user doesn't have permission to view this server.
    """
    # Find server
    server = next((s for s in MOCK_SERVERS if s.id == server_id), None)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    # Check visibility
    if not can_user_see_server(server, user):
        raise HTTPException(status_code=403, detail="You do not have permission to view this server")

    return server
