"""Quota check dependency for request-level enforcement (CAB-1121 Phase 4).

Called per-request by endpoints that need quota enforcement.
Reads the consumer's plan limits (with 30s TTL cache), compares
against current counters, and either increments or raises 429.
"""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.plan import Plan
from ..models.subscription import Subscription
from ..repositories.quota_usage import QuotaUsageRepository
from ..services.cache_service import quota_plan_cache

logger = logging.getLogger(__name__)


async def _get_plan_limits(consumer_id: UUID, tenant_id: str, db: AsyncSession) -> dict | None:
    """Fetch plan limits for a consumer, with TTL cache."""
    cache_key = f"quota_plan:{consumer_id}:{tenant_id}"
    cached = await quota_plan_cache.get(cache_key)
    if cached is not None:
        return cached

    # Look up the consumer's active subscription → plan
    result = await db.execute(
        select(Subscription.plan_id)
        .where(
            Subscription.consumer_id == consumer_id,
            Subscription.tenant_id == tenant_id,
            Subscription.status == "active",
        )
        .limit(1)
    )
    row = result.first()
    if not row or not row.plan_id:
        return None

    plan_result = await db.execute(select(Plan).where(Plan.id == row.plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        return None

    limits = {
        "daily_request_limit": plan.daily_request_limit,
        "monthly_request_limit": plan.monthly_request_limit,
    }
    await quota_plan_cache.set(cache_key, limits)
    return limits


def _seconds_until_daily_reset() -> int:
    """Seconds until midnight UTC."""
    now = datetime.utcnow()
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((midnight - now).total_seconds())


def _seconds_until_monthly_reset() -> int:
    """Seconds until the 1st of next month UTC."""
    now = datetime.utcnow()
    if now.month == 12:
        first_next = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        first_next = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return int((first_next - now).total_seconds())


async def check_quota(
    consumer_id: UUID,
    tenant_id: str,
    db: AsyncSession,
    bandwidth_bytes: int = 0,
) -> None:
    """Check and increment quota for a consumer.

    Raises HTTPException(429) if quota is exceeded.
    """
    limits = await _get_plan_limits(consumer_id, tenant_id, db)
    if not limits:
        # No plan attached — no quota enforcement
        return

    daily_limit = limits.get("daily_request_limit")
    monthly_limit = limits.get("monthly_request_limit")

    if not daily_limit and not monthly_limit:
        # Plan has no limits defined
        return

    repo = QuotaUsageRepository(db)
    usage = await repo.get_or_create(consumer_id, tenant_id)

    # Check daily limit
    if daily_limit and usage.request_count_daily >= daily_limit:
        retry_after = _seconds_until_daily_reset()
        raise HTTPException(
            status_code=429,
            detail={
                "error": "quota_exceeded",
                "detail": "Daily request limit exceeded",
                "limit": daily_limit,
                "current": usage.request_count_daily,
                "resets_at": (datetime.utcnow() + timedelta(seconds=retry_after)).isoformat(),
            },
            headers={"Retry-After": str(retry_after)},
        )

    # Check monthly limit
    if monthly_limit and usage.request_count_monthly >= monthly_limit:
        retry_after = _seconds_until_monthly_reset()
        raise HTTPException(
            status_code=429,
            detail={
                "error": "quota_exceeded",
                "detail": "Monthly request limit exceeded",
                "limit": monthly_limit,
                "current": usage.request_count_monthly,
                "resets_at": (datetime.utcnow() + timedelta(seconds=retry_after)).isoformat(),
            },
            headers={"Retry-After": str(retry_after)},
        )

    # Under limit — increment atomically
    await repo.increment(consumer_id, tenant_id, bandwidth_bytes)
