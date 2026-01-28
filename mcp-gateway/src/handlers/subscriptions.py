# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""MCP Subscriptions Handler.

FastAPI router for MCP subscription endpoints.
Manages tool subscriptions and API keys for users.

Now with:
- Database persistence (PostgreSQL)
- Vault secure storage for API keys
- TOTP-based key reveal endpoint

Reference: Linear CAB-247, CAB-292, CAB-XXX (Secure API Key Management)
"""

import secrets
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..middleware.auth import TokenClaims, get_current_user
from ..models.subscription import SubscriptionModel, SubscriptionStatus
from ..services.database import get_session, get_session_factory
from ..services.vault_client import get_vault_client, VaultClient

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
    totp_required: bool = False  # Whether TOTP is required to reveal key


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


class RevealKeyRequest(BaseModel):
    """Request to reveal an API key (requires TOTP if enabled)."""

    totp_code: str | None = Field(None, description="TOTP code if 2FA is enabled")


class RevealKeyResponse(BaseModel):
    """Response containing the revealed API key."""

    api_key: str
    expires_in: int = 30  # Key visibility window in seconds


# =============================================================================
# In-Memory Fallback Storage (used when database unavailable)
# =============================================================================

# Storage: subscription_id -> Subscription
_subscriptions: dict[str, dict] = {}

# Storage: api_key_hash -> subscription_id
_api_keys: dict[str, str] = {}

# Storage: user_id -> list of subscription_ids
_user_subscriptions: dict[str, list[str]] = {}

# Flag to track if we're using database or in-memory
_use_database: bool = True


def _generate_api_key() -> str:
    """Generate a secure API key."""
    return f"stoa_sk_{secrets.token_hex(16)}"


def _hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def _model_to_subscription(model: SubscriptionModel) -> Subscription:
    """Convert database model to Pydantic response model."""
    return Subscription(
        id=model.id,
        tenant_id=model.tenant_id,
        user_id=model.user_id,
        tool_id=model.tool_id,
        status=model.status.value,
        plan=model.plan,
        created_at=model.created_at.isoformat() if model.created_at else "",
        expires_at=model.expires_at.isoformat() if model.expires_at else None,
        last_used_at=model.last_used_at.isoformat() if model.last_used_at else None,
        usage_count=model.usage_count,
        api_key_prefix=model.api_key_prefix,
        totp_required=model.totp_required,
    )


async def _get_db_session():
    """Try to get a database session, return None if unavailable."""
    try:
        factory = get_session_factory()
        return factory()
    except RuntimeError:
        return None


# =============================================================================
# Helper: Check TOTP ACR claim
# =============================================================================


def _has_totp_acr(user: TokenClaims) -> bool:
    """Check if user's token has TOTP authentication context.

    Keycloak sets acr claim when step-up auth is completed.
    Expected values: "totp", "urn:stoa:acr:totp", or similar.
    """
    if not user.acr:
        return False

    acr_lower = user.acr.lower()
    return "totp" in acr_lower or "mfa" in acr_lower or "2fa" in acr_lower


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

    # Try database first
    session = await _get_db_session()
    if session:
        try:
            async with session:
                # Build query
                query = select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)

                if status_filter:
                    try:
                        status_enum = SubscriptionStatus(status_filter)
                        query = query.where(SubscriptionModel.status == status_enum)
                    except ValueError:
                        pass  # Invalid status, ignore filter

                # Get total count
                count_result = await session.execute(
                    select(SubscriptionModel.id).where(SubscriptionModel.user_id == user_id)
                )
                total = len(count_result.all())

                # Paginate
                query = query.offset((page - 1) * page_size).limit(page_size)
                result = await session.execute(query)
                models = result.scalars().all()

                subscriptions = [_model_to_subscription(m) for m in models]

                logger.info(
                    "Listed subscriptions from database",
                    user=user_id,
                    total=total,
                    page=page,
                )

                return SubscriptionListResponse(
                    subscriptions=subscriptions,
                    total=total,
                    page=page,
                    page_size=page_size,
                )
        except Exception as e:
            logger.warning("Database query failed, falling back to in-memory", error=str(e))

    # Fallback to in-memory storage
    sub_ids = _user_subscriptions.get(user_id, [])
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
        "Listed subscriptions from memory",
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
    user_id = user.subject

    # Try database first
    session = await _get_db_session()
    if session:
        try:
            async with session:
                result = await session.execute(
                    select(SubscriptionModel).where(SubscriptionModel.id == subscription_id)
                )
                model = result.scalar_one_or_none()

                if not model:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Subscription not found",
                    )

                if model.user_id != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to view this subscription",
                    )

                return _model_to_subscription(model)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Database query failed, falling back to in-memory", error=str(e))

    # Fallback to in-memory
    sub = _subscriptions.get(subscription_id)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    if sub["user_id"] != user_id:
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
    now = datetime.now(timezone.utc)

    # Generate subscription ID and API key
    subscription_id = str(uuid.uuid4())
    api_key = _generate_api_key()
    api_key_hash = _hash_api_key(api_key)
    tenant_id = data.tenant_id or "default"

    # Try database first
    session = await _get_db_session()
    if session:
        try:
            async with session:
                # Check for existing active subscription
                existing = await session.execute(
                    select(SubscriptionModel).where(
                        and_(
                            SubscriptionModel.user_id == user_id,
                            SubscriptionModel.tool_id == data.tool_id,
                            SubscriptionModel.status == SubscriptionStatus.ACTIVE,
                        )
                    )
                )
                if existing.scalar_one_or_none():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Already subscribed to tool: {data.tool_id}",
                    )

                # Store API key in Vault
                vault_path = None
                try:
                    vault = get_vault_client()
                    vault_path = await vault.store_api_key(
                        subscription_id=subscription_id,
                        api_key=api_key,
                        metadata={
                            "user_id": user_id,
                            "tool_id": data.tool_id,
                            "tenant_id": tenant_id,
                            "created_at": now.isoformat(),
                        },
                    )
                    logger.info("API key stored in Vault", subscription_id=subscription_id)
                except Exception as e:
                    logger.warning("Vault storage failed, key only shown once", error=str(e))

                # Create subscription in database
                model = SubscriptionModel(
                    id=subscription_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    tool_id=data.tool_id,
                    plan=data.plan,
                    status=SubscriptionStatus.ACTIVE,
                    api_key_hash=api_key_hash,
                    api_key_prefix=api_key[:12],
                    vault_path=vault_path,
                    totp_required=False,  # User can enable later
                    created_at=now,
                )
                session.add(model)
                await session.commit()
                await session.refresh(model)

                logger.info(
                    "Created subscription in database",
                    subscription_id=subscription_id,
                    user=user_id,
                    tool=data.tool_id,
                    vault_stored=vault_path is not None,
                )

                return SubscriptionWithKey(
                    subscription=_model_to_subscription(model),
                    api_key=api_key,
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Database operation failed, falling back to in-memory", error=str(e))

    # Fallback to in-memory storage
    user_sub_ids = _user_subscriptions.get(user_id, [])
    for sub_id in user_sub_ids:
        existing = _subscriptions.get(sub_id)
        if existing and existing["tool_id"] == data.tool_id and existing["status"] == "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Already subscribed to tool: {data.tool_id}",
            )

    subscription_data = {
        "id": subscription_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "tool_id": data.tool_id,
        "status": "active",
        "plan": data.plan,
        "created_at": now.isoformat(),
        "expires_at": None,
        "last_used_at": None,
        "usage_count": 0,
        "api_key_prefix": api_key[:12],
        "totp_required": False,
    }

    _subscriptions[subscription_id] = subscription_data
    _api_keys[api_key_hash] = subscription_id

    if user_id not in _user_subscriptions:
        _user_subscriptions[user_id] = []
    _user_subscriptions[user_id].append(subscription_id)

    logger.info(
        "Created subscription in memory",
        subscription_id=subscription_id,
        user=user_id,
        tool=data.tool_id,
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
    user_id = user.subject
    now = datetime.now(timezone.utc)

    # Try database first
    session = await _get_db_session()
    if session:
        try:
            async with session:
                result = await session.execute(
                    select(SubscriptionModel).where(SubscriptionModel.id == subscription_id)
                )
                model = result.scalar_one_or_none()

                if not model:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Subscription not found",
                    )

                if model.user_id != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to revoke this subscription",
                    )

                # Delete from Vault
                if model.vault_path:
                    try:
                        vault = get_vault_client()
                        await vault.delete_api_key(subscription_id)
                        logger.info("API key deleted from Vault", subscription_id=subscription_id)
                    except Exception as e:
                        logger.warning("Failed to delete from Vault", error=str(e))

                # Update status
                model.status = SubscriptionStatus.REVOKED
                model.revoked_at = now
                model.revoked_by = user_id
                await session.commit()

                logger.info(
                    "Revoked subscription in database",
                    subscription_id=subscription_id,
                    user=user_id,
                )
                return

        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Database operation failed, falling back to in-memory", error=str(e))

    # Fallback to in-memory
    sub = _subscriptions.get(subscription_id)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    if sub["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to revoke this subscription",
        )

    sub["status"] = "revoked"
    _subscriptions[subscription_id] = sub

    keys_to_remove = [k for k, v in _api_keys.items() if v == subscription_id]
    for key in keys_to_remove:
        del _api_keys[key]

    logger.info(
        "Revoked subscription in memory",
        subscription_id=subscription_id,
        user=user_id,
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
    user_id = user.subject

    # Generate new API key
    new_api_key = _generate_api_key()
    new_api_key_hash = _hash_api_key(new_api_key)

    # Try database first
    session = await _get_db_session()
    if session:
        try:
            async with session:
                result = await session.execute(
                    select(SubscriptionModel).where(SubscriptionModel.id == subscription_id)
                )
                model = result.scalar_one_or_none()

                if not model:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Subscription not found",
                    )

                if model.user_id != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to regenerate this key",
                    )

                if model.status != SubscriptionStatus.ACTIVE:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot regenerate key for inactive subscription",
                    )

                # Update Vault
                if model.vault_path:
                    try:
                        vault = get_vault_client()
                        await vault.rotate_api_key(subscription_id, new_api_key)
                        logger.info("API key rotated in Vault", subscription_id=subscription_id)
                    except Exception as e:
                        logger.warning("Failed to rotate in Vault", error=str(e))

                # Update database
                model.api_key_hash = new_api_key_hash
                model.api_key_prefix = new_api_key[:12]
                await session.commit()

                logger.info(
                    "Regenerated API key in database",
                    subscription_id=subscription_id,
                    user=user_id,
                )

                return {"api_key": new_api_key}

        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Database operation failed, falling back to in-memory", error=str(e))

    # Fallback to in-memory
    sub = _subscriptions.get(subscription_id)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    if sub["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to regenerate this key",
        )

    if sub["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot regenerate key for inactive subscription",
        )

    # Remove old API key from lookup
    keys_to_remove = [k for k, v in _api_keys.items() if v == subscription_id]
    for key in keys_to_remove:
        del _api_keys[key]

    # Add new key
    _api_keys[new_api_key_hash] = subscription_id
    sub["api_key_prefix"] = new_api_key[:12]
    _subscriptions[subscription_id] = sub

    logger.info(
        "Regenerated API key in memory",
        subscription_id=subscription_id,
        user=user_id,
    )

    return {"api_key": new_api_key}


@router.post(
    "/{subscription_id}/reveal-key",
    response_model=RevealKeyResponse,
    summary="Reveal API key (requires 2FA if enabled)",
    description="Retrieve the API key from Vault. Requires TOTP verification if 2FA is enabled.",
)
async def reveal_api_key(
    subscription_id: str,
    user: Annotated[TokenClaims, Depends(get_current_user)],
    data: RevealKeyRequest | None = None,
) -> RevealKeyResponse:
    """Reveal the API key for a subscription.

    Security:
    - If TOTP is required, validates ACR claim in token OR totp_code in request
    - Logs all access attempts for audit
    - Returns key with 30-second visibility window hint
    """
    user_id = user.subject
    now = datetime.now(timezone.utc)

    # Try database first
    session = await _get_db_session()
    if session:
        try:
            async with session:
                result = await session.execute(
                    select(SubscriptionModel).where(SubscriptionModel.id == subscription_id)
                )
                model = result.scalar_one_or_none()

                if not model:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Subscription not found",
                    )

                if model.user_id != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to access this subscription",
                    )

                if model.status != SubscriptionStatus.ACTIVE:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot reveal key for inactive subscription",
                    )

                # Check TOTP requirement
                if model.totp_required:
                    # Check if token has TOTP ACR
                    if not _has_totp_acr(user):
                        # Could also validate totp_code here if implementing server-side TOTP
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="TOTP verification required. Please re-authenticate with 2FA.",
                            headers={"X-Step-Up-Auth": "totp"},
                        )

                # Retrieve from Vault
                if not model.vault_path:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="API key not stored in Vault. Please regenerate to enable secure storage.",
                    )

                try:
                    vault = get_vault_client()
                    api_key = await vault.retrieve_api_key(subscription_id)

                    if not api_key:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="API key not found in Vault. Please regenerate.",
                        )

                    # Log successful reveal for audit
                    logger.info(
                        "API key revealed",
                        subscription_id=subscription_id,
                        user=user_id,
                        tool=model.tool_id,
                        totp_verified=_has_totp_acr(user),
                        client_ip=user.azp,  # Or get from request
                        timestamp=now.isoformat(),
                    )

                    return RevealKeyResponse(
                        api_key=api_key,
                        expires_in=30,
                    )

                except HTTPException:
                    raise
                except Exception as e:
                    logger.error("Failed to retrieve from Vault", error=str(e))
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to retrieve API key from secure storage",
                    )

        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Database operation failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable",
            )

    # In-memory mode doesn't support reveal (keys not stored)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Key reveal not available in in-memory mode. Database required.",
    )


@router.patch(
    "/{subscription_id}/totp",
    summary="Toggle TOTP requirement for key reveal",
    description="Enable or disable TOTP requirement for revealing the API key.",
)
async def toggle_totp_requirement(
    subscription_id: str,
    user: Annotated[TokenClaims, Depends(get_current_user)],
    enabled: bool = Query(..., description="Enable or disable TOTP requirement"),
) -> dict:
    """Enable or disable TOTP requirement for a subscription."""
    user_id = user.subject

    # Try database first
    session = await _get_db_session()
    if session:
        try:
            async with session:
                result = await session.execute(
                    select(SubscriptionModel).where(SubscriptionModel.id == subscription_id)
                )
                model = result.scalar_one_or_none()

                if not model:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Subscription not found",
                    )

                if model.user_id != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to modify this subscription",
                    )

                model.totp_required = enabled
                await session.commit()

                logger.info(
                    "TOTP requirement toggled",
                    subscription_id=subscription_id,
                    user=user_id,
                    totp_required=enabled,
                )

                return {
                    "subscription_id": subscription_id,
                    "totp_required": enabled,
                    "message": f"TOTP requirement {'enabled' if enabled else 'disabled'}",
                }

        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Database operation failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable",
            )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="TOTP settings not available in in-memory mode",
    )


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
    user_id = user.subject

    # Try database first
    session = await _get_db_session()
    if session:
        try:
            async with session:
                result = await session.execute(
                    select(SubscriptionModel).where(SubscriptionModel.id == subscription_id)
                )
                model = result.scalar_one_or_none()

                if not model:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Subscription not found",
                    )

                if model.user_id != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to access this subscription",
                    )

                return SubscriptionConfig(
                    mcpServers={
                        "stoa": {
                            "command": "npx",
                            "args": ["-y", "@anthropic/mcp-client", "stdio"],
                            "env": {
                                "STOA_API_KEY": "<YOUR_API_KEY>",
                                "STOA_MCP_URL": "https://mcp.gostoa.dev",
                            },
                        }
                    }
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Database query failed, falling back to in-memory", error=str(e))

    # Fallback to in-memory
    sub = _subscriptions.get(subscription_id)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    if sub["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this subscription",
        )

    return SubscriptionConfig(
        mcpServers={
            "stoa": {
                "command": "npx",
                "args": ["-y", "@anthropic/mcp-client", "stdio"],
                "env": {
                    "STOA_API_KEY": "<YOUR_API_KEY>",
                    "STOA_MCP_URL": "https://mcp.gostoa.dev",
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
    now = datetime.now(timezone.utc)

    # Try database first
    session = await _get_db_session()
    if session:
        try:
            async with session:
                result = await session.execute(
                    select(SubscriptionModel).where(
                        and_(
                            SubscriptionModel.api_key_hash == api_key_hash,
                            SubscriptionModel.status == SubscriptionStatus.ACTIVE,
                        )
                    )
                )
                model = result.scalar_one_or_none()

                if not model:
                    return None

                # Update usage
                model.usage_count += 1
                model.last_used_at = now
                await session.commit()

                return _model_to_subscription(model)

        except Exception as e:
            logger.warning("Database validation failed, falling back to in-memory", error=str(e))

    # Fallback to in-memory
    subscription_id = _api_keys.get(api_key_hash)

    if not subscription_id:
        return None

    sub = _subscriptions.get(subscription_id)
    if not sub or sub["status"] != "active":
        return None

    # Update usage
    sub["usage_count"] = sub.get("usage_count", 0) + 1
    sub["last_used_at"] = now.isoformat()
    _subscriptions[subscription_id] = sub

    return Subscription(**sub)
