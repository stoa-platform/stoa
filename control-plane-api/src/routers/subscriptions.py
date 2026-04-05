"""Subscriptions router - API subscription management"""

import asyncio
import logging
import math
import uuid as uuid_mod
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..models.portal_application import SecurityProfile
from ..models.subscription import Subscription, SubscriptionStatus
from ..repositories.plan import PlanRepository
from ..repositories.portal_application import PortalApplicationRepository
from ..repositories.subscription import SubscriptionRepository
from ..schemas.subscription import (
    BulkActionFailure,
    BulkActionResult,
    BulkSubscriptionAction,
    KeyRotationRequest,
    KeyRotationResponse,
    SubscriptionApprove,
    SubscriptionCreate,
    SubscriptionListResponse,
    SubscriptionReject,
    SubscriptionResponse,
    SubscriptionRevoke,
    SubscriptionStats,
    SubscriptionStatusEnum,
    SubscriptionValidateOAuthRequest,
    SubscriptionValidateOAuthResponse,
    SubscriptionWithRotationInfo,
    TTLExtendRequest,
    TTLExtendResponse,
)
from ..services.api_key import APIKeyService
from ..services.email import email_service
from ..services.kafka_service import Topics, kafka_service
from ..services.provisioning_service import deprovision_on_revocation, provision_on_approval
from ..services.webhook_service import (
    emit_subscription_approved,
    emit_subscription_created,
    emit_subscription_key_rotated,
    emit_subscription_rejected,
    emit_subscription_revoked,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/subscriptions", tags=["Subscriptions"])


def _extract_auth_token(request: Request) -> str | None:
    """Extract Bearer token from Authorization header if present."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return None


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has read access to a tenant's resources."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


def _has_tenant_admin_access(user: User, tenant_id: str) -> bool:
    """Check if user has admin (write) access to a tenant's resources.

    Unlike _has_tenant_access, this requires an admin role (cpi-admin or
    tenant-admin), not just tenant membership. Viewer and devops roles
    with matching tenant_id are denied.
    """
    if "cpi-admin" in user.roles:
        return True
    return "tenant-admin" in user.roles and user.tenant_id == tenant_id


# ============== Subscriber Endpoints (Developer Portal) ==============


@router.post("", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(
    request: SubscriptionCreate,
    raw_request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new subscription request.

    This endpoint is called by the Developer Portal when a user subscribes
    to an API. The subscription starts in PENDING status and must be
    approved by a tenant admin.

    Uses OAuth2 client_credentials flow — no API key is generated.
    The consumer's Application keycloak_client_id is stored as oauth_client_id.
    """
    repo = SubscriptionRepository(db)

    # Check for existing subscription
    existing = await repo.get_by_application_and_api(request.application_id, request.api_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Subscription already exists for this application and API (status: {existing.status.value})",
        )

    # Look up PortalApplication to get keycloak_client_id (REQUIRED for OAuth2 flow)
    app_repo = PortalApplicationRepository(db)
    try:
        portal_app = await app_repo.get_by_id(UUID(request.application_id))
    except (ValueError, Exception) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid application_id: {e}",
        )

    if not portal_app:
        raise HTTPException(
            status_code=404,
            detail="Application not found. Please create an application first.",
        )

    if portal_app.security_profile == SecurityProfile.API_KEY:
        oauth_client_id = None
    elif not portal_app.keycloak_client_id:
        raise HTTPException(
            status_code=400,
            detail="Application has no OAuth2 client configured. " "Please regenerate credentials in My Applications.",
        )
    else:
        oauth_client_id = portal_app.keycloak_client_id

    # Create subscription (no API key — OAuth2 only)
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
        oauth_client_id=oauth_client_id,
        status=SubscriptionStatus.PENDING,
    )

    try:
        subscription = await repo.create(subscription)
        logger.info(
            f"Created subscription {subscription.id} for app={request.application_name} "
            f"api={request.api_name} user={user.email} oauth_client_id={oauth_client_id}"
        )

        # Emit webhook event (CAB-315)
        try:
            await emit_subscription_created(db, subscription)
        except Exception as e:
            logger.warning(f"Failed to emit subscription.created webhook: {e}")

    except Exception as e:
        logger.error(f"Failed to create subscription: {e}")
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    # Auto-approve logic (CAB-1172): free/standard plans skip admin approval
    should_auto_approve = False
    if request.plan_id:
        try:
            plan_uuid = UUID(request.plan_id)
            plan_repo = PlanRepository(db)
            plan = await plan_repo.get_by_id(plan_uuid)
            if plan is None or not plan.requires_approval:
                should_auto_approve = True
            elif plan.auto_approve_roles:
                should_auto_approve = any(role in plan.auto_approve_roles for role in user.roles)
        except (ValueError, AttributeError) as e:
            # Invalid UUID or lookup error → fail-secure, keep PENDING
            logger.error(f"Plan lookup failed for plan_id={request.plan_id}: {e}")
            should_auto_approve = False
    else:
        # No plan = free/default → auto-approve
        should_auto_approve = True

    if should_auto_approve:
        try:
            subscription = await repo.update_status(
                subscription,
                SubscriptionStatus.ACTIVE,
                actor_id="system:auto-approve",
            )
            logger.info(f"Subscription {subscription.id} auto-approved (CAB-1172)")

            try:
                await emit_subscription_approved(db, subscription)
            except Exception as e:
                logger.warning(f"Failed to emit subscription.approved webhook: {e}")

            correlation_id = str(uuid_mod.uuid4())
            auth_token = _extract_auth_token(raw_request)
            try:
                await asyncio.wait_for(
                    provision_on_approval(db, subscription, auth_token, correlation_id),
                    timeout=10.0,
                )
            except TimeoutError:
                from ..models.subscription import ProvisioningStatus

                subscription.provisioning_status = ProvisioningStatus.FAILED
                subscription.provisioning_error = "Gateway provisioning timed out"
                await db.commit()
                logger.error(f"Provisioning timeout for subscription {subscription.id}")
            except Exception as prov_err:
                logger.warning(f"Provisioning failed for subscription {subscription.id}: {prov_err}")
        except Exception as e:
            logger.warning(f"Auto-approve failed, subscription stays PENDING: {e}")
    else:
        # Subscription requires approval — notify tenant admins
        try:
            asyncio.create_task(_notify_tenant_admins(db, subscription))
        except Exception as e:
            logger.warning(f"Failed to schedule admin notification: {e}")

    return SubscriptionResponse.model_validate(subscription)


async def _notify_tenant_admins(db: AsyncSession, subscription: Subscription) -> None:
    """Send email notification to tenant admins about a pending subscription."""
    try:
        from ..repositories.tenant import TenantRepository

        admin_emails: list[str] = []

        # Try to get tenant admin contact from the tenant record
        try:
            tenant_repo = TenantRepository(db)
            tenant = await tenant_repo.get_by_id(subscription.tenant_id)
            if tenant and getattr(tenant, "admin_email", None):
                admin_emails = [tenant.admin_email]
        except Exception:
            logger.debug(f"Could not look up tenant for {subscription.tenant_id}")

        if admin_emails:
            await email_service.send_subscription_pending_notification(
                to_emails=admin_emails,
                subscription_id=str(subscription.id),
                api_name=subscription.api_name,
                application_name=subscription.application_name,
                subscriber_email=subscription.subscriber_email,
                tenant_id=subscription.tenant_id,
            )
        else:
            logger.info(
                f"No tenant admin emails found for {subscription.tenant_id}. "
                f"Subscription {subscription.id} pending approval (no email sent)."
            )
    except Exception as e:
        logger.warning(f"Failed to notify tenant admins for subscription {subscription.id}: {e}")


@router.get("/my", response_model=SubscriptionListResponse)
async def list_my_subscriptions(
    status: SubscriptionStatusEnum | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    environment: str | None = Query(None, description="Filter by environment"),
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
        environment=environment,
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
        raise HTTPException(status_code=400, detail=f"Cannot cancel subscription in {subscription.status.value} status")

    await repo.update_status(
        subscription,
        SubscriptionStatus.REVOKED,
        reason="Cancelled by subscriber",
        actor_id=user.id,
    )

    logger.info(f"Subscription {subscription_id} cancelled by subscriber {user.email}")


# ============== Key Rotation Endpoint (CAB-314) ==============


@router.post("/{subscription_id}/rotate-key", response_model=KeyRotationResponse, deprecated=True)
async def rotate_api_key(
    subscription_id: UUID,
    response: Response,
    request: KeyRotationRequest = KeyRotationRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Rotate the API key for a subscription with grace period.

    **Deprecated**: API keys are being replaced by OAuth2 client_credentials flow.
    Use Application OAuth2 credentials instead.

    The old key remains valid for the specified grace period (default 24 hours).
    During the grace period, both old and new keys are accepted.
    After the grace period expires, only the new key is valid.

    Returns the new API key (shown only once!) and grace period information.
    An email notification is sent to the subscriber with the new key.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    logger.warning("Deprecated endpoint rotate-key called for subscription %s.", subscription_id)
    repo = SubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Check access: subscriber owns this subscription or is tenant admin
    if subscription.subscriber_id != user.id and not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Can only rotate active subscriptions
    if subscription.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(
            status_code=400, detail=f"Cannot rotate key for subscription in {subscription.status.value} status"
        )

    # Check if there's already an active grace period
    from datetime import datetime

    if subscription.previous_key_expires_at and subscription.previous_key_expires_at > datetime.utcnow():
        raise HTTPException(
            status_code=400,
            detail=f"A key rotation is already in progress. Previous key expires at {subscription.previous_key_expires_at.isoformat()}. Wait for the grace period to end before rotating again.",
        )

    # Generate new API key
    new_api_key, new_api_key_hash, new_api_key_prefix = APIKeyService.generate_key()

    try:
        # Perform key rotation with grace period
        subscription = await repo.rotate_key(
            subscription=subscription,
            new_api_key_hash=new_api_key_hash,
            new_api_key_prefix=new_api_key_prefix,
            grace_period_hours=request.grace_period_hours,
        )

        logger.info(
            f"API key rotated for subscription {subscription_id} by {user.email}. "
            f"Grace period: {request.grace_period_hours}h, expires at: {subscription.previous_key_expires_at}"
        )

        # Send email notification (async, don't wait)
        try:
            await email_service.send_key_rotation_notification(
                to_email=subscription.subscriber_email,
                subscription_id=str(subscription_id),
                api_name=subscription.api_name,
                application_name=subscription.application_name,
                new_api_key=new_api_key,
                old_key_expires_at=subscription.previous_key_expires_at,
                grace_period_hours=request.grace_period_hours,
            )
        except Exception as e:
            # Log but don't fail the rotation if email fails
            logger.warning(f"Failed to send key rotation email: {e}")

        # Emit webhook event (CAB-315)
        try:
            await emit_subscription_key_rotated(db, subscription, request.grace_period_hours)
        except Exception as e:
            logger.warning(f"Failed to emit subscription.key_rotated webhook: {e}")

        return KeyRotationResponse(
            subscription_id=subscription.id,
            new_api_key=new_api_key,
            new_api_key_prefix=new_api_key_prefix,
            old_key_expires_at=subscription.previous_key_expires_at,
            grace_period_hours=request.grace_period_hours,
            rotation_count=subscription.rotation_count,
        )

    except Exception as e:
        logger.error(f"Failed to rotate API key for subscription {subscription_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to rotate API key")


@router.get("/{subscription_id}/rotation-info", response_model=SubscriptionWithRotationInfo)
async def get_subscription_rotation_info(
    subscription_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get subscription details with key rotation information.

    Includes grace period status if a key rotation is in progress.
    """
    repo = SubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Check access
    if subscription.subscriber_id != user.id and not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if there's an active grace period
    from datetime import datetime

    has_active_grace_period = (
        subscription.previous_key_expires_at is not None and subscription.previous_key_expires_at > datetime.utcnow()
    )

    response = SubscriptionWithRotationInfo.model_validate(subscription)
    response.has_active_grace_period = has_active_grace_period

    return response


# ============== TTL Extension Endpoint (CAB-86) ==============


MAX_TTL_EXTENSIONS = 2
MAX_TTL_TOTAL_DAYS = 60


@router.patch("/{subscription_id}/ttl", response_model=TTLExtendResponse)
async def extend_subscription_ttl(
    subscription_id: UUID,
    request: TTLExtendRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Extend the TTL of an active subscription.

    Subscription owners can extend their expiry by 7 or 14 days.
    Limited to 2 extensions and 60 total extended days.
    Tenant admins and cpi-admins can extend any subscription in their scope.
    """
    repo = SubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Tenant access check
    if not _has_tenant_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Ownership check: subscriber OR admin roles
    is_owner = subscription.subscriber_id == user.id
    is_admin = "cpi-admin" in user.roles or "tenant-admin" in user.roles
    if not is_owner and not is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Must be active
    if subscription.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Only active subscriptions can be extended")

    # Must have an expiry date
    if subscription.expires_at is None:
        raise HTTPException(status_code=409, detail="Subscription has no expiry date")

    # Extension count limit
    if subscription.ttl_extension_count >= MAX_TTL_EXTENSIONS:
        raise HTTPException(
            status_code=409,
            detail=f"Maximum extensions reached ({MAX_TTL_EXTENSIONS})",
        )

    # Total days limit
    if subscription.ttl_total_extended_days + request.extend_days > MAX_TTL_TOTAL_DAYS:
        raise HTTPException(
            status_code=409,
            detail=f"Would exceed {MAX_TTL_TOTAL_DAYS}-day maximum total extension",
        )

    # Apply extension
    from datetime import timedelta

    subscription.expires_at = subscription.expires_at + timedelta(days=request.extend_days)
    subscription.ttl_extension_count += 1
    subscription.ttl_total_extended_days += request.extend_days

    await db.flush()

    logger.info(
        f"TTL extended for subscription {subscription_id} by {request.extend_days}d "
        f"(count={subscription.ttl_extension_count}, total={subscription.ttl_total_extended_days}d) "
        f"by {user.email}, reason: {request.reason}"
    )

    # Kafka event
    try:
        await kafka_service.publish(
            topic=Topics.RESOURCE_LIFECYCLE,
            event_type="resource-ttl-extended",
            tenant_id=subscription.tenant_id,
            payload={
                "subscription_id": str(subscription.id),
                "extend_days": request.extend_days,
                "reason": request.reason,
                "new_expires_at": subscription.expires_at.isoformat(),
                "ttl_extension_count": subscription.ttl_extension_count,
                "ttl_total_extended_days": subscription.ttl_total_extended_days,
            },
            user_id=user.id,
        )
    except Exception as e:
        logger.warning(f"Failed to emit resource-ttl-extended Kafka event: {e}")

    return TTLExtendResponse(
        id=subscription.id,
        new_expires_at=subscription.expires_at,
        ttl_extension_count=subscription.ttl_extension_count,
        ttl_total_extended_days=subscription.ttl_total_extended_days,
        remaining_extensions=MAX_TTL_EXTENSIONS - subscription.ttl_extension_count,
    )


# ============== Admin Endpoints (Control Plane) ==============


@router.get("/tenant/{tenant_id}", response_model=SubscriptionListResponse)
async def list_tenant_subscriptions(
    tenant_id: str,
    status: SubscriptionStatusEnum | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    environment: str | None = Query(None, description="Filter by environment"),
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
        environment=environment,
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
    raw_request: Request,
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

    if not _has_tenant_admin_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied — tenant-admin or cpi-admin role required")

    if subscription.status != SubscriptionStatus.PENDING:
        raise HTTPException(
            status_code=400, detail=f"Cannot approve subscription in {subscription.status.value} status"
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

    # Emit webhook event (CAB-315)
    try:
        await emit_subscription_approved(db, subscription)
    except Exception as e:
        logger.warning(f"Failed to emit subscription.approved webhook: {e}")

    # Auto-provision gateway application (CAB-800)
    correlation_id = str(uuid_mod.uuid4())
    auth_token = _extract_auth_token(raw_request)
    asyncio.create_task(provision_on_approval(db, subscription, auth_token, correlation_id))

    return SubscriptionResponse.model_validate(subscription)


@router.post("/{subscription_id}/revoke", response_model=SubscriptionResponse)
async def revoke_subscription(
    subscription_id: UUID,
    request: SubscriptionRevoke,
    raw_request: Request,
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

    if not _has_tenant_admin_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied — tenant-admin or cpi-admin role required")

    if subscription.status == SubscriptionStatus.REVOKED:
        raise HTTPException(status_code=400, detail="Subscription already revoked")

    subscription = await repo.update_status(
        subscription,
        SubscriptionStatus.REVOKED,
        reason=request.reason,
        actor_id=user.id,
    )

    logger.info(f"Subscription {subscription_id} revoked by {user.email} " f"reason={request.reason}")

    # Emit webhook event (CAB-315)
    try:
        await emit_subscription_revoked(db, subscription)
    except Exception as e:
        logger.warning(f"Failed to emit subscription.revoked webhook: {e}")

    # Auto-deprovision gateway application (CAB-800)
    correlation_id = str(uuid_mod.uuid4())
    auth_token = _extract_auth_token(raw_request)
    asyncio.create_task(deprovision_on_revocation(db, subscription, auth_token, correlation_id))

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

    if not _has_tenant_admin_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied — tenant-admin or cpi-admin role required")

    if subscription.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(
            status_code=400, detail=f"Cannot suspend subscription in {subscription.status.value} status"
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

    if not _has_tenant_admin_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied — tenant-admin or cpi-admin role required")

    if subscription.status != SubscriptionStatus.SUSPENDED:
        raise HTTPException(
            status_code=400, detail=f"Cannot reactivate subscription in {subscription.status.value} status"
        )

    subscription = await repo.update_status(
        subscription,
        SubscriptionStatus.ACTIVE,
        reason="Reactivated by admin",
        actor_id=user.id,
    )

    logger.info(f"Subscription {subscription_id} reactivated by {user.email}")

    return SubscriptionResponse.model_validate(subscription)


# ============== Reject, Bulk, Stats Endpoints (CAB-1635) ==============


@router.post("/{subscription_id}/reject", response_model=SubscriptionResponse)
async def reject_subscription(
    subscription_id: UUID,
    request: SubscriptionReject,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Reject a pending subscription request.

    Only pending subscriptions can be rejected. The reason is stored
    for audit purposes.
    """
    repo = SubscriptionRepository(db)
    subscription = await repo.get_by_id(subscription_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if not _has_tenant_admin_access(user, subscription.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied — tenant-admin or cpi-admin role required")

    if subscription.status != SubscriptionStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Cannot reject subscription in {subscription.status.value} status")

    subscription = await repo.update_status(
        subscription,
        SubscriptionStatus.REJECTED,
        reason=request.reason,
        actor_id=user.id,
    )

    logger.info(f"Subscription {subscription_id} rejected by {user.email} " f"reason={request.reason}")

    # Emit webhook event
    try:
        await emit_subscription_rejected(db, subscription)
    except Exception as e:
        logger.warning(f"Failed to emit subscription.rejected webhook: {e}")

    return SubscriptionResponse.model_validate(subscription)


@router.post("/bulk", response_model=BulkActionResult)
async def bulk_subscription_action(
    request: BulkSubscriptionAction,
    raw_request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Perform bulk approve or reject on multiple subscriptions.

    Maximum 50 subscriptions per call. Each subscription is processed
    independently — partial failures are reported.
    """
    if request.action == "reject" and not request.reason:
        raise HTTPException(status_code=400, detail="Reason is required for reject action")

    repo = SubscriptionRepository(db)
    succeeded = 0
    failed: list[BulkActionFailure] = []

    for sub_id in request.ids:
        try:
            subscription = await repo.get_by_id(sub_id)
            if not subscription:
                failed.append(BulkActionFailure(id=sub_id, error="Subscription not found"))
                continue

            if not _has_tenant_admin_access(user, subscription.tenant_id):
                failed.append(BulkActionFailure(id=sub_id, error="Access denied"))
                continue

            if subscription.status != SubscriptionStatus.PENDING:
                failed.append(
                    BulkActionFailure(
                        id=sub_id,
                        error=f"Cannot {request.action} subscription in {subscription.status.value} status",
                    )
                )
                continue

            if request.action == "approve":
                subscription = await repo.update_status(
                    subscription,
                    SubscriptionStatus.ACTIVE,
                    actor_id=user.id,
                )
                try:
                    await emit_subscription_approved(db, subscription)
                except Exception as e:
                    logger.warning(f"Failed to emit webhook for {sub_id}: {e}")

                # Auto-provision gateway
                correlation_id = str(uuid_mod.uuid4())
                auth_token = _extract_auth_token(raw_request)
                asyncio.create_task(provision_on_approval(db, subscription, auth_token, correlation_id))

            else:  # reject
                subscription = await repo.update_status(
                    subscription,
                    SubscriptionStatus.REJECTED,
                    reason=request.reason,
                    actor_id=user.id,
                )
                try:
                    await emit_subscription_rejected(db, subscription)
                except Exception as e:
                    logger.warning(f"Failed to emit webhook for {sub_id}: {e}")

            succeeded += 1
        except Exception as e:
            logger.error(f"Bulk action failed for {sub_id}: {e}")
            failed.append(BulkActionFailure(id=sub_id, error=str(e)))

    return BulkActionResult(succeeded=succeeded, failed=failed)


@router.get("/tenant/{tenant_id}/stats", response_model=SubscriptionStats)
async def get_subscription_stats(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get subscription statistics for a tenant.

    Returns counts by status, recent activity, and average approval time.
    """
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    repo = SubscriptionRepository(db)
    stats = await repo.get_stats(tenant_id)

    return SubscriptionStats(
        total=stats["total"],
        by_status=stats["by_status"],
        by_tenant={tenant_id: stats["total"]},
        recent_24h=stats["recent_24h"],
        avg_approval_time_hours=stats.get("avg_approval_time_hours"),
    )


# ============== API Key Validation Endpoint (Gateway) ==============


class _ValidateKeyBody(BaseModel):
    """Request body for API key validation (preferred over query param)."""

    api_key: str


@router.post("/validate-key", deprecated=True)
async def validate_api_key(
    response: Response,
    body: _ValidateKeyBody | None = None,
    api_key: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Validate an API key (used by the Gateway).

    **Deprecated**: Use POST /validate-subscription with OAuth2 client_id instead.

    This is an internal endpoint for the API Gateway to validate
    incoming API keys and get subscription details.

    Accepts key via JSON body (preferred) or query param (legacy).
    Body is preferred because the PII middleware masks query params
    named ``api_key``.

    Supports grace period: during key rotation, both old and new keys are valid.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = '</v1/subscriptions/validate-subscription>; rel="successor-version"'
    logger.warning("Deprecated endpoint /validate-key called. Migrate to /validate-subscription.")
    # Body takes precedence (query params are masked by PII middleware)
    key = (body.api_key if body else None) or api_key
    if not key:
        raise HTTPException(status_code=400, detail="api_key required in body or query")

    # Validate format
    if not APIKeyService.validate_format(key):
        raise HTTPException(status_code=401, detail="Invalid API key format")

    # Hash and lookup
    api_key_hash = APIKeyService.hash_key(key)

    repo = SubscriptionRepository(db)

    # Try to find by current key first
    subscription = await repo.get_by_api_key_hash(api_key_hash)
    is_previous_key = False

    # If not found, check if it's a previous key during grace period (CAB-314)
    if not subscription:
        subscription = await repo.get_by_previous_key_hash(api_key_hash)
        if subscription:
            is_previous_key = True
            logger.info(
                f"Using previous API key during grace period for subscription {subscription.id}. "
                f"Expires at: {subscription.previous_key_expires_at}"
            )

    if not subscription:
        raise HTTPException(status_code=401, detail="API key not found")

    # Check status
    if subscription.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(status_code=403, detail=f"Subscription is {subscription.status.value}")

    # Check subscription expiration
    from datetime import datetime

    now = datetime.utcnow()

    if subscription.expires_at and now > subscription.expires_at:
        raise HTTPException(status_code=403, detail="Subscription expired")

    # Build result with grace period info
    result = {
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

    # Add grace period warning if using old key
    if is_previous_key:
        result["warning"] = "Using deprecated API key during grace period"
        result["key_expires_at"] = subscription.previous_key_expires_at.isoformat()
        result["using_previous_key"] = True

    return result


# ============== OAuth2 Subscription Validation Endpoint (Gateway) ==============


@router.post("/validate-subscription", response_model=SubscriptionValidateOAuthResponse)
async def validate_subscription_oauth(
    body: SubscriptionValidateOAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate a subscription via OAuth2 client_id (used by the Gateway).

    The Gateway calls this after JWT validation to check if the token's
    ``azp`` (authorized party) claim has an active subscription for the target API.
    """
    repo = SubscriptionRepository(db)

    subscription = await repo.get_by_oauth_client_and_api(body.oauth_client_id, body.api_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found for this client and API")

    # Check subscription expiration
    from datetime import datetime

    now = datetime.utcnow()
    if subscription.expires_at and now > subscription.expires_at:
        raise HTTPException(status_code=403, detail="Subscription expired")

    # Look up security_profile from portal application
    security_profile = "oauth2_public"
    if subscription.application_id:
        from uuid import UUID as _UUID

        from ..repositories.portal_application import PortalApplicationRepository

        app_repo = PortalApplicationRepository(db)
        try:
            portal_app = await app_repo.get_by_id(_UUID(subscription.application_id))
            if portal_app and portal_app.security_profile:
                security_profile = portal_app.security_profile.value
        except (ValueError, Exception):
            pass  # Invalid UUID or DB error — use default

    return SubscriptionValidateOAuthResponse(
        valid=True,
        subscription_id=str(subscription.id),
        application_id=subscription.application_id,
        application_name=subscription.application_name,
        subscriber_id=subscription.subscriber_id,
        api_id=subscription.api_id,
        api_name=subscription.api_name,
        tenant_id=subscription.tenant_id,
        plan_id=subscription.plan_id,
        plan_name=subscription.plan_name,
        security_profile=security_profile,
    )
