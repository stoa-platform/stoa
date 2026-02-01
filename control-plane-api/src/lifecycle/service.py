"""
Tenant Lifecycle Service - State Machine & Business Logic
CAB-409: Auto-Cleanup & Notifications for demo.gostoa.dev
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    CLEANUP_AFTER_DAYS,
    EXTENSION_DAYS,
    GRACE_PERIOD_DAYS,
    MAX_EXTENSIONS,
    NOTIFICATION_SCHEDULE,
    TRIAL_DURATION_DAYS,
    WARNING_THRESHOLD_DAYS,
    LifecycleCronSummary,
    LifecycleTransitionEvent,
    NotificationType,
    TenantLifecycleState,
    TenantStatusResponse,
    ExtendTrialResponse,
    UpgradeTenantResponse,
)
from .metrics import lifecycle_metrics

logger = logging.getLogger("stoa.lifecycle")


class TenantLifecycleService:
    """
    Manages tenant lifecycle state transitions for demo.gostoa.dev.

    State Machine:
        ACTIVE (0-10d) -> WARNING (11-14d) -> EXPIRED (15-21d) -> DELETED (22d+)
                            |                    |
                         CONVERTED            CONVERTED

    Invariant (COUNCIL #4):
        lifecycle_state in (active, warning, converted) -> status = 'active'
        lifecycle_state == expired                      -> status = 'suspended'
        lifecycle_state == deleted                      -> status = 'archived'
    """

    def __init__(
        self,
        db: AsyncSession,
        notification_service: "NotificationService",
        cleanup_service: "CleanupService",
    ):
        self.db = db
        self.notifications = notification_service
        self.cleanup = cleanup_service

    # ─── Public API ───────────────────────────────────────────────────────

    async def get_status(self, tenant_id: str) -> TenantStatusResponse:
        """Get current lifecycle status for a tenant."""
        tenant = await self._get_tenant(tenant_id)
        return TenantStatusResponse(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            state=tenant.lifecycle_state,
            created_at=tenant.created_at,
            expires_at=tenant.trial_expires_at,
            lifecycle_changed_at=tenant.lifecycle_changed_at,
            _extended_count=tenant.trial_extended_count,
        )

    async def extend_trial(self, tenant_id: str, reason: Optional[str] = None) -> ExtendTrialResponse:
        """Extend a tenant's trial by EXTENSION_DAYS (one-time)."""
        tenant = await self._get_tenant(tenant_id)

        if tenant.lifecycle_state not in (TenantLifecycleState.ACTIVE, TenantLifecycleState.WARNING):
            raise LifecycleError(
                f"Cannot extend: tenant is {tenant.lifecycle_state.value}. "
                f"Only active or warning tenants can extend."
            )
        if tenant.trial_extended_count >= MAX_EXTENSIONS:
            raise LifecycleError(
                f"Extension limit reached ({MAX_EXTENSIONS}). "
                f"Contact sales to upgrade: sales@gostoa.dev"
            )

        old_expires = tenant.trial_expires_at
        tenant.trial_expires_at += timedelta(days=EXTENSION_DAYS)
        tenant.trial_extended_count += 1

        await self._recompute_state(tenant, triggered_by="self-service")
        await self.db.commit()

        logger.info(
            "Trial extended",
            extra={
                "tenant_id": tenant_id,
                "old_expires": old_expires.isoformat(),
                "new_expires": tenant.trial_expires_at.isoformat(),
                "reason": reason,
            },
        )
        lifecycle_metrics.trial_extensions_total.inc()

        return ExtendTrialResponse(
            tenant_id=tenant_id,
            new_expires_at=tenant.trial_expires_at,
            extensions_remaining=MAX_EXTENSIONS - tenant.trial_extended_count,
            message=f"Trial extended by {EXTENSION_DAYS} days. "
                    f"New expiration: {tenant.trial_expires_at.strftime('%Y-%m-%d')}",
        )

    async def upgrade_tenant(self, tenant_id: str, target_tier: str, contact_email: Optional[str] = None) -> UpgradeTenantResponse:
        """Convert a demo tenant to a paid tier."""
        tenant = await self._get_tenant(tenant_id)

        if tenant.lifecycle_state == TenantLifecycleState.DELETED:
            raise LifecycleError("Cannot upgrade a deleted tenant. Data has been purged.")

        previous_state = tenant.lifecycle_state
        owner_email = (tenant.settings or {}).get("owner_email", "")
        await self._transition(
            tenant,
            to_state=TenantLifecycleState.CONVERTED,
            triggered_by="self-service",
            metadata={"target_tier": target_tier, "contact_email": contact_email},
        )
        tenant.converted_at = datetime.now(timezone.utc)
        tenant.trial_expires_at = None  # No more expiration
        await self.db.commit()

        lifecycle_metrics.conversions_total.labels(tier=target_tier).inc()

        return UpgradeTenantResponse(
            tenant_id=tenant_id,
            previous_state=previous_state,
            new_state=TenantLifecycleState.CONVERTED,
            target_tier=target_tier,
            message=f"Tenant upgraded to {target_tier}. "
                    f"Our team will contact you at {contact_email or owner_email} "
                    f"to finalize the migration.",
        )

    # ─── Cron Job Entry Point ─────────────────────────────────────────────

    async def run_lifecycle_check(self) -> LifecycleCronSummary:
        """
        Main cron entry point. Runs daily at 2 AM UTC.
        Processes all non-terminal tenants in order: warnings -> expirations -> cleanups.
        """
        now = datetime.now(timezone.utc)
        summary = LifecycleCronSummary(run_at=now)

        try:
            warned = await self._process_warnings(now)
            summary.tenants_warned = warned

            expired = await self._process_expirations(now)
            summary.tenants_expired = expired

            deleted = await self._process_deletions(now)
            summary.tenants_deleted = deleted

            sent = await self._process_notifications(now)
            summary.notifications_sent = sent

            await self.db.commit()

        except Exception as e:
            summary.errors.append(str(e))
            logger.exception("Lifecycle cron failed", extra={"error": str(e)})

        lifecycle_metrics.cron_runs_total.inc()
        lifecycle_metrics.last_cron_run.set_to_current_time()

        logger.info(
            "Lifecycle cron completed",
            extra={
                "warned": summary.tenants_warned,
                "expired": summary.tenants_expired,
                "deleted": summary.tenants_deleted,
                "notifications": summary.notifications_sent,
                "errors": len(summary.errors),
            },
        )
        return summary

    # ─── Internal: State Transitions ──────────────────────────────────────

    async def _process_warnings(self, now: datetime) -> int:
        threshold = now + timedelta(days=WARNING_THRESHOLD_DAYS)
        tenants = await self._find_tenants(
            state=TenantLifecycleState.ACTIVE,
            expires_before=threshold,
        )
        for tenant in tenants:
            await self._transition(tenant, TenantLifecycleState.WARNING, "cron")
        return len(tenants)

    async def _process_expirations(self, now: datetime) -> int:
        tenants = await self._find_tenants(
            state=TenantLifecycleState.WARNING,
            expires_before=now,
        )
        for tenant in tenants:
            await self._transition(tenant, TenantLifecycleState.EXPIRED, "cron")
        return len(tenants)

    async def _process_deletions(self, now: datetime) -> int:
        cleanup_threshold = now - timedelta(days=CLEANUP_AFTER_DAYS)
        tenants = await self._find_tenants(
            state=TenantLifecycleState.EXPIRED,
            expires_before=cleanup_threshold,
        )
        for tenant in tenants:
            try:
                await self.cleanup.cleanup_tenant(tenant.id)
                await self._transition(tenant, TenantLifecycleState.DELETED, "cron")
                tenant.deleted_at = now
            except Exception as e:
                logger.error(f"Failed to cleanup tenant {tenant.id}: {e}")
                lifecycle_metrics.cleanup_errors_total.inc()
        return len(tenants)

    async def _process_notifications(self, now: datetime) -> int:
        sent = 0
        tenants = await self._find_tenants(
            states=[TenantLifecycleState.ACTIVE, TenantLifecycleState.WARNING, TenantLifecycleState.EXPIRED],
        )
        for tenant in tenants:
            if not tenant.trial_expires_at:
                continue
            days_to_expiry = (tenant.trial_expires_at - now).days
            owner_email = (tenant.settings or {}).get("owner_email", "")

            for notif_type, trigger_day in NOTIFICATION_SCHEDULE.items():
                if days_to_expiry <= -trigger_day:
                    was_sent = await self.notifications.send_if_not_sent(
                        tenant_id=tenant.id,
                        notification_type=notif_type,
                        recipient_email=owner_email,
                        context={
                            "tenant_name": tenant.name,
                            "days_left": max(0, days_to_expiry),
                            "expires_at": tenant.trial_expires_at.strftime("%Y-%m-%d"),
                        },
                    )
                    if was_sent:
                        sent += 1

        return sent

    # ─── Helpers ──────────────────────────────────────────────────────────

    async def _transition(
        self,
        tenant,
        to_state: TenantLifecycleState,
        triggered_by: str,
        metadata: dict | None = None,
    ) -> None:
        """Execute a state transition with audit logging and status invariant enforcement."""
        from_state = tenant.lifecycle_state
        tenant.lifecycle_state = to_state
        tenant.lifecycle_changed_at = datetime.now(timezone.utc)

        # COUNCIL #4: Enforce status/lifecycle_state invariant
        from src.models.tenant import TenantStatus
        if to_state in (TenantLifecycleState.ACTIVE, TenantLifecycleState.WARNING, TenantLifecycleState.CONVERTED):
            tenant.status = TenantStatus.ACTIVE.value
        elif to_state == TenantLifecycleState.EXPIRED:
            tenant.status = TenantStatus.SUSPENDED.value
        elif to_state == TenantLifecycleState.DELETED:
            tenant.status = TenantStatus.ARCHIVED.value

        event = LifecycleTransitionEvent(
            tenant_id=tenant.id,
            from_state=from_state,
            to_state=to_state,
            triggered_by=triggered_by,
            metadata=metadata or {},
        )
        # TODO: Publish to Kafka audit topic
        logger.info(
            f"Lifecycle transition: {from_state.value} -> {to_state.value}",
            extra={"event": event.model_dump()},
        )
        lifecycle_metrics.state_gauge.labels(state=to_state.value).inc()
        lifecycle_metrics.state_gauge.labels(state=from_state.value).dec()

    async def _recompute_state(self, tenant, triggered_by: str) -> None:
        """Recompute state after external change (e.g. extension)."""
        now = datetime.now(timezone.utc)
        if tenant.trial_expires_at is None:
            return

        days_left = (tenant.trial_expires_at - now).days

        if days_left > WARNING_THRESHOLD_DAYS:
            target = TenantLifecycleState.ACTIVE
        elif days_left > 0:
            target = TenantLifecycleState.WARNING
        elif days_left > -CLEANUP_AFTER_DAYS:
            target = TenantLifecycleState.EXPIRED
        else:
            target = TenantLifecycleState.DELETED

        if tenant.lifecycle_state != target:
            await self._transition(tenant, target, triggered_by)

    async def _get_tenant(self, tenant_id: str):
        """Fetch tenant or raise 404."""
        from src.models.tenant import Tenant
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await self.db.execute(stmt)
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundError(tenant_id)
        return tenant

    async def _find_tenants(
        self,
        state: Optional[TenantLifecycleState] = None,
        states: Optional[list[TenantLifecycleState]] = None,
        expires_before: Optional[datetime] = None,
    ) -> Sequence:
        """Query tenants by lifecycle criteria."""
        from src.models.tenant import Tenant
        conditions = []
        if state:
            conditions.append(Tenant.lifecycle_state == state)
        if states:
            conditions.append(Tenant.lifecycle_state.in_(states))
        if expires_before:
            conditions.append(Tenant.trial_expires_at <= expires_before)
            conditions.append(Tenant.trial_expires_at.isnot(None))

        stmt = select(Tenant).where(and_(*conditions))
        result = await self.db.execute(stmt)
        return result.scalars().all()


# ─── Exceptions ───────────────────────────────────────────────────────────────

class LifecycleError(Exception):
    """Business logic error in lifecycle management."""
    pass


class TenantNotFoundError(LifecycleError):
    def __init__(self, tenant_id: str):
        super().__init__(f"Tenant not found: {tenant_id}")
        self.tenant_id = tenant_id
