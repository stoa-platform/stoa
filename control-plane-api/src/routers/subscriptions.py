"""Subscriptions router - API subscription management"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
import math

from ..auth import get_current_user, User, require_permission, Permission
from ..database import get_db
from ..models.subscription import Subscription, SubscriptionStatus
from ..repositories.subscription import SubscriptionRepository
from ..services.api_key import APIKeyService
from ..schemas.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionListResponse,
    SubscriptionApprove,
    SubscriptionRevoke,
    SubscriptionStatusEnum,
    APIKeyResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/subscriptions", tags=["Subscriptions"])


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant"""
    if "cpi-admin" in user.roles:
        return True
    if user.tenant_id == tenant_id:
        return True
    return False


# ============== Subscriber Endpoints (Developer Portal) ==============

@router.post("", response_model=APIKeyResponse, status_code=201)
async def create_subscription(
    request: SubscriptionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new subscription request.

    This endpoint is called by the Developer Portal when a user subscribes
    to an API. The subscription starts in PENDING status and must be
    approved by an API admin.

    Returns the API key (shown only once!).
    """
    repo = SubscriptionRepository(db)

    # Check for existing subscription
    existing = await repo.get_by_application_and_api(
        request.application_id,
        request.api_id
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Subscription already exists for this application and API (status: {existing.status.value})"
        )

    # Generate API key
    api_key, api_key_hash, api_key_prefix = APIKeyService.generate_key()

    # Create subscription
    subscription = Subscription(
        application_id=request.application_id,
        application_name=request.application_name,
        subscriber_id=user.id,
        subscriber_email=user.email,
        api_id=request.api_id,
        api_name=request.api_name,
        api_version=request.api_version,
        tenant_id=request.tenant_id,
        plan_id=request.plan_id,
        plan_name=request.plan_name,
        api_key_hash=api_key_hash,
        api_key_prefix=api_key_prefix,
        status=SubscriptionStatus.PENDING,
    )

    try:
        subscription = await repo.create(subscription)
        logger.info(
            f"Created subscription {subscription.id} for app={request.application_name} "
            f"api={request.api_name} user={user.email}"
        )
    except Exception as e:
        logger.error(f"Failed to create subscription: {e}")
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    # Return API key (shown only once!)
    return APIKeyResponse(
        subscription_id=subscription.id,
        api_key=api_key,
        api_key_prefix=api_key_prefix,
        expires_at=subscription.expires_at,
    )


@router.get("/my", response_model=SubscriptionListResponse)
async def list_my_subscriptions(
    status: Optional[SubscriptionStatusEnum] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List current user's subscriptions.

    Used by the Developer Portal to show user's subscribed APIs.
    """
    repo = SubscriptionRepository(db)

    db_status = SubscriptionStatus(status.value) if status else None
    subscriptions, total = await repo.list_by_subscriber(
        subscriber_id=user.id,
        status=db_status,
        page=page,
        page_size=page_size,
    )

    return SubscriptionListResponse(
        items=[SubscriptionResponse.model_validate(s) for s in subscriptions],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get subscription details by ID"""
    repo = SubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Check access: subscriber or tenant admin
    if subscription.subscriber_id != user.id and not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    return SubscriptionResponse.model_validate(subscription)


@router.delete("/{subscription_id}", status_code=204)
async def cancel_subscription(
    subscription_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel a subscription (subscriber action).

    Subscribers can cancel their own subscriptions.
    """
    repo = SubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Only subscriber can cancel their own subscription
    if subscription.subscriber_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if subscription.status not in [SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel subscription in {subscription.status.value} status"
        )

    await repo.update_status(
        subscription,
        SubscriptionStatus.REVOKED,
        reason="Cancelled by subscriber",
        actor_id=user.id,
    )

    logger.info(f"Subscription {subscription_id} cancelled by subscriber {user.email}")


# ============== Admin Endpoints (Control Plane) ==============

@router.get("/tenant/{tenant_id}", response_model=SubscriptionListResponse)
async def list_tenant_subscriptions(
    tenant_id: str,
    status: Optional[SubscriptionStatusEnum] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all subscriptions for a tenant.

    Used by tenant admins to view and manage subscriptions.
    """
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = SubscriptionRepository(db)

    db_status = SubscriptionStatus(status.value) if status else None
    subscriptions, total = await repo.list_by_tenant(
        tenant_id=tenant_id,
        status=db_status,
        page=page,
        page_size=page_size,
    )

    return SubscriptionListResponse(
        items=[SubscriptionResponse.model_validate(s) for s in subscriptions],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/tenant/{tenant_id}/pending", response_model=SubscriptionListResponse)
async def list_pending_subscriptions(
    tenant_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List pending subscriptions awaiting approval.

    Used by tenant admins to see subscription requests.
    """
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = SubscriptionRepository(db)

    subscriptions, total = await repo.list_pending(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
    )

    return SubscriptionListResponse(
        items=[SubscriptionResponse.model_validate(s) for s in subscriptions],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.post("/{subscription_id}/approve", response_model=SubscriptionResponse)
async def approve_subscription(
    subscription_id: UUID,
    request: SubscriptionApprove,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a pending subscription.

    Tenant admins approve subscription requests.
    """
    repo = SubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if subscription.status != SubscriptionStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve subscription in {subscription.status.value} status"
        )

    # Set expiration if provided
    if request.expires_at:
        await repo.set_expiration(subscription, request.expires_at)

    # Approve
    subscription = await repo.update_status(
        subscription,
        SubscriptionStatus.ACTIVE,
        actor_id=user.id,
    )

    logger.info(
        f"Subscription {subscription_id} approved by {user.email} "
        f"for app={subscription.application_name} api={subscription.api_name}"
    )

    return SubscriptionResponse.model_validate(subscription)


@router.post("/{subscription_id}/revoke", response_model=SubscriptionResponse)
async def revoke_subscription(
    subscription_id: UUID,
    request: SubscriptionRevoke,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke an active subscription.

    Tenant admins can revoke subscriptions for policy violations.
    """
    repo = SubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if subscription.status == SubscriptionStatus.REVOKED:
        raise HTTPException(status_code=400, detail="Subscription already revoked")

    subscription = await repo.update_status(
        subscription,
        SubscriptionStatus.REVOKED,
        reason=request.reason,
        actor_id=user.id,
    )

    logger.info(
        f"Subscription {subscription_id} revoked by {user.email} "
        f"reason={request.reason}"
    )

    return SubscriptionResponse.model_validate(subscription)


@router.post("/{subscription_id}/suspend", response_model=SubscriptionResponse)
async def suspend_subscription(
    subscription_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Temporarily suspend a subscription.

    Can be reactivated later.
    """
    repo = SubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if subscription.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot suspend subscription in {subscription.status.value} status"
        )

    subscription = await repo.update_status(
        subscription,
        SubscriptionStatus.SUSPENDED,
        reason="Suspended by admin",
        actor_id=user.id,
    )

    logger.info(f"Subscription {subscription_id} suspended by {user.email}")

    return SubscriptionResponse.model_validate(subscription)


@router.post("/{subscription_id}/reactivate", response_model=SubscriptionResponse)
async def reactivate_subscription(
    subscription_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Reactivate a suspended subscription.
    """
    repo = SubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if subscription.status != SubscriptionStatus.SUSPENDED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reactivate subscription in {subscription.status.value} status"
        )

    subscription = await repo.update_status(
        subscription,
        SubscriptionStatus.ACTIVE,
        reason="Reactivated by admin",
        actor_id=user.id,
    )

    logger.info(f"Subscription {subscription_id} reactivated by {user.email}")

    return SubscriptionResponse.model_validate(subscription)


# ============== API Key Validation Endpoint (Gateway) ==============

@router.post("/validate-key")
async def validate_api_key(
    api_key: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate an API key (used by the Gateway).

    This is an internal endpoint for the API Gateway to validate
    incoming API keys and get subscription details.
    """
    # Validate format
    if not APIKeyService.validate_format(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key format")

    # Hash and lookup
    api_key_hash = APIKeyService.hash_key(api_key)

    repo = SubscriptionRepository(db)
    subscription = await repo.get_by_api_key_hash(api_key_hash)

    if not subscription:
        raise HTTPException(status_code=401, detail="API key not found")

    # Check status
    if subscription.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(
            status_code=403,
            detail=f"Subscription is {subscription.status.value}"
        )

    # Check expiration
    if subscription.expires_at:
        from datetime import datetime
        if datetime.utcnow() > subscription.expires_at:
            raise HTTPException(status_code=403, detail="Subscription expired")

    return {
        "valid": True,
        "subscription_id": str(subscription.id),
        "application_id": subscription.application_id,
        "application_name": subscription.application_name,
        "subscriber_id": subscription.subscriber_id,
        "api_id": subscription.api_id,
        "api_name": subscription.api_name,
        "tenant_id": subscription.tenant_id,
        "plan_id": subscription.plan_id,
        "plan_name": subscription.plan_name,
    }
