"""MCP Subscriptions Handler.

FastAPI router for MCP subscription endpoints.
Manages tool subscriptions and API keys for users.

Reference: Linear CAB-247, CAB-292
"""

import secrets
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..middleware.auth import TokenClaims, get_current_user

logger = structlog.get_logger(__name__)

# Create router
router = APIRouter(prefix="/mcp/v1/subscriptions", tags=["Subscriptions"])


# =============================================================================
# Models
# =============================================================================


class SubscriptionCreate(BaseModel):
    """Request to create a new subscription."""

    tool_id: str = Field(..., description="Tool to subscribe to")
    plan: str = Field(default="free", description="Subscription plan")
    tenant_id: str | None = Field(None, description="Optional tenant ID")


class Subscription(BaseModel):
    """Subscription details."""

    id: str
    tenant_id: str
    user_id: str
    tool_id: str
    status: str  # active, expired, revoked
    plan: str
    created_at: str
    expires_at: str | None = None
    last_used_at: str | None = None
    usage_count: int = 0
    api_key_prefix: str | None = None  # First 8 chars for display


class SubscriptionWithKey(BaseModel):
    """Subscription with the API key (returned only on creation)."""

    subscription: Subscription
    api_key: str  # Full API key - shown only ONCE!


class SubscriptionListResponse(BaseModel):
    """Paginated list of subscriptions."""

    subscriptions: list[Subscription]
    total: int
    page: int
    page_size: int


class SubscriptionConfig(BaseModel):
    """Claude Desktop configuration export."""

    mcpServers: dict


# =============================================================================
# In-Memory Storage (replace with database in production)
# =============================================================================

# Storage: subscription_id -> Subscription
_subscriptions: dict[str, dict] = {}

# Storage: api_key_hash -> subscription_id
_api_keys: dict[str, str] = {}

# Storage: user_id -> list of subscription_ids
_user_subscriptions: dict[str, list[str]] = {}


def _generate_api_key() -> str:
    """Generate a secure API key."""
    return f"stoa_sk_{secrets.token_hex(16)}"


def _hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=SubscriptionListResponse,
    summary="List my subscriptions",
    description="Returns a paginated list of subscriptions for the authenticated user.",
)
async def list_subscriptions(
    user: Annotated[TokenClaims, Depends(get_current_user)],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
) -> SubscriptionListResponse:
    """List subscriptions for the authenticated user."""
    user_id = user.subject

    # Get user's subscription IDs
    sub_ids = _user_subscriptions.get(user_id, [])

    # Filter and paginate
    all_subs = []
    for sub_id in sub_ids:
        sub = _subscriptions.get(sub_id)
        if sub:
            if status_filter and sub["status"] != status_filter:
                continue
            all_subs.append(Subscription(**sub))

    total = len(all_subs)
    start = (page - 1) * page_size
    end = start + page_size
    page_subs = all_subs[start:end]

    logger.info(
        "Listed subscriptions",
        user=user_id,
        total=total,
        page=page,
    )

    return SubscriptionListResponse(
        subscriptions=page_subs,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{subscription_id}",
    response_model=Subscription,
    summary="Get subscription details",
)
async def get_subscription(
    subscription_id: str,
    user: Annotated[TokenClaims, Depends(get_current_user)],
) -> Subscription:
    """Get details of a specific subscription."""
    sub = _subscriptions.get(subscription_id)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # Check ownership
    if sub["user_id"] != user.subject:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this subscription",
        )

    return Subscription(**sub)


@router.post(
    "",
    response_model=SubscriptionWithKey,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new subscription",
    description="Subscribe to a tool and receive an API key. The key is shown only ONCE!",
)
async def create_subscription(
    data: SubscriptionCreate,
    user: Annotated[TokenClaims, Depends(get_current_user)],
) -> SubscriptionWithKey:
    """Create a new subscription and return the API key."""
    user_id = user.subject
    now = datetime.now(timezone.utc).isoformat()

    # Check for existing active subscription to same tool
    user_sub_ids = _user_subscriptions.get(user_id, [])
    for sub_id in user_sub_ids:
        existing = _subscriptions.get(sub_id)
        if existing and existing["tool_id"] == data.tool_id and existing["status"] == "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Already subscribed to tool: {data.tool_id}",
            )

    # Generate subscription ID and API key
    subscription_id = str(uuid.uuid4())
    api_key = _generate_api_key()
    api_key_hash = _hash_api_key(api_key)

    # Create subscription record
    subscription_data = {
        "id": subscription_id,
        "tenant_id": data.tenant_id or "default",
        "user_id": user_id,
        "tool_id": data.tool_id,
        "status": "active",
        "plan": data.plan,
        "created_at": now,
        "expires_at": None,
        "last_used_at": None,
        "usage_count": 0,
        "api_key_prefix": api_key[:12],  # "stoa_sk_XXXX"
    }

    # Store subscription
    _subscriptions[subscription_id] = subscription_data
    _api_keys[api_key_hash] = subscription_id

    # Add to user's subscriptions
    if user_id not in _user_subscriptions:
        _user_subscriptions[user_id] = []
    _user_subscriptions[user_id].append(subscription_id)

    logger.info(
        "Created subscription",
        subscription_id=subscription_id,
        user=user_id,
        tool=data.tool_id,
        plan=data.plan,
    )

    return SubscriptionWithKey(
        subscription=Subscription(**subscription_data),
        api_key=api_key,
    )


@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a subscription",
)
async def revoke_subscription(
    subscription_id: str,
    user: Annotated[TokenClaims, Depends(get_current_user)],
) -> None:
    """Revoke a subscription and invalidate its API key."""
    sub = _subscriptions.get(subscription_id)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # Check ownership
    if sub["user_id"] != user.subject:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to revoke this subscription",
        )

    # Update status
    sub["status"] = "revoked"
    _subscriptions[subscription_id] = sub

    # Invalidate API key (remove from lookup)
    api_key_prefix = sub.get("api_key_prefix", "")
    keys_to_remove = [k for k, v in _api_keys.items() if v == subscription_id]
    for key in keys_to_remove:
        del _api_keys[key]

    logger.info(
        "Revoked subscription",
        subscription_id=subscription_id,
        user=user.subject,
    )


@router.post(
    "/{subscription_id}/regenerate",
    summary="Regenerate API key",
    description="Generate a new API key. The old key is immediately invalidated!",
)
async def regenerate_api_key(
    subscription_id: str,
    user: Annotated[TokenClaims, Depends(get_current_user)],
) -> dict:
    """Regenerate the API key for a subscription."""
    sub = _subscriptions.get(subscription_id)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # Check ownership
    if sub["user_id"] != user.subject:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to regenerate this key",
        )

    if sub["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot regenerate key for inactive subscription",
        )

    # Remove old API key
    keys_to_remove = [k for k, v in _api_keys.items() if v == subscription_id]
    for key in keys_to_remove:
        del _api_keys[key]

    # Generate new API key
    api_key = _generate_api_key()
    api_key_hash = _hash_api_key(api_key)
    _api_keys[api_key_hash] = subscription_id

    # Update subscription
    sub["api_key_prefix"] = api_key[:12]
    _subscriptions[subscription_id] = sub

    logger.info(
        "Regenerated API key",
        subscription_id=subscription_id,
        user=user.subject,
    )

    return {"api_key": api_key}


@router.get(
    "/{subscription_id}/config",
    response_model=SubscriptionConfig,
    summary="Get Claude Desktop config",
    description="Get the claude_desktop_config.json configuration for this subscription.",
)
async def get_config_export(
    subscription_id: str,
    user: Annotated[TokenClaims, Depends(get_current_user)],
) -> SubscriptionConfig:
    """Get Claude Desktop configuration export."""
    sub = _subscriptions.get(subscription_id)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # Check ownership
    if sub["user_id"] != user.subject:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this subscription",
        )

    # Note: We don't return the actual API key here
    # User must have saved it when subscription was created
    return SubscriptionConfig(
        mcpServers={
            "stoa": {
                "command": "npx",
                "args": ["-y", "@anthropic/mcp-client", "stdio"],
                "env": {
                    "STOA_API_KEY": "<YOUR_API_KEY>",
                    "STOA_MCP_URL": "https://mcp.stoa.cab-i.com",
                },
            }
        }
    )


# =============================================================================
# API Key Validation (for internal use)
# =============================================================================


async def validate_api_key(api_key: str) -> Subscription | None:
    """Validate an API key and return the associated subscription.

    This is called by the auth middleware when X-API-Key is provided.
    """
    api_key_hash = _hash_api_key(api_key)
    subscription_id = _api_keys.get(api_key_hash)

    if not subscription_id:
        return None

    sub = _subscriptions.get(subscription_id)
    if not sub or sub["status"] != "active":
        return None

    # Update usage
    sub["usage_count"] = sub.get("usage_count", 0) + 1
    sub["last_used_at"] = datetime.now(timezone.utc).isoformat()
    _subscriptions[subscription_id] = sub

    return Subscription(**sub)
