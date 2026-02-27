"""Trial plan enforcement service (CAB-1549).

Pure functions that check tenant trial limits:
- API creation cap (default 3)
- Trial expiry (30 days + 1 day grace)
- Grace period warning (day 25+)

Trial metadata is stored in tenant.settings:
    {
        "is_trial": true,
        "trial_started_at": "2026-02-27T00:00:00+00:00",
        "max_apis": 3,
        "max_daily_requests": 100
    }
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Trial plan defaults
TRIAL_MAX_APIS = 3
TRIAL_MAX_DAILY_REQUESTS = 100
TRIAL_DURATION_DAYS = 30
TRIAL_GRACE_DAYS = 1  # Block at day 32 (30d trial + 1d grace)


def check_trial_expiry(settings: dict) -> None:
    """Check if a trial tenant's period has expired.

    Raises HTTPException 402 if trial expired (past grace period).
    No-op for non-trial tenants.
    """
    if not settings.get("is_trial"):
        return

    trial_started = settings.get("trial_started_at")
    if not trial_started:
        return

    started = datetime.fromisoformat(trial_started)
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)

    now = datetime.now(UTC)
    days_elapsed = (now - started).days
    expires_at = started + timedelta(days=TRIAL_DURATION_DAYS + TRIAL_GRACE_DAYS)

    if days_elapsed > TRIAL_DURATION_DAYS + TRIAL_GRACE_DAYS:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "trial_expired",
                "detail": "Trial period has expired. Please upgrade to continue.",
                "trial_started_at": trial_started,
                "expired_at": expires_at.isoformat(),
            },
        )


def check_trial_api_limit(settings: dict, current_api_count: int) -> None:
    """Check if a trial tenant can create more APIs.

    Raises HTTPException 403 if API creation limit reached.
    No-op for non-trial tenants.
    """
    if not settings.get("is_trial"):
        return

    max_apis = settings.get("max_apis", TRIAL_MAX_APIS)

    if current_api_count >= max_apis:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "trial_api_limit",
                "detail": f"Trial plan limited to {max_apis} APIs. Please upgrade to create more.",
                "limit": max_apis,
                "current": current_api_count,
            },
        )


def get_trial_status(settings: dict) -> dict | None:
    """Return trial status info including warnings.

    Returns None for non-trial tenants.
    Returns dict with trial state, days remaining, and optional warning.
    """
    if not settings.get("is_trial"):
        return None

    trial_started = settings.get("trial_started_at")
    if not trial_started:
        return {"is_trial": True, "warning": "trial_started_at not set"}

    started = datetime.fromisoformat(trial_started)
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)

    now = datetime.now(UTC)
    days_elapsed = (now - started).days
    days_remaining = max(0, TRIAL_DURATION_DAYS - days_elapsed)
    expires_at = started + timedelta(days=TRIAL_DURATION_DAYS)

    result: dict = {
        "is_trial": True,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "expires_at": expires_at.isoformat(),
        "max_apis": settings.get("max_apis", TRIAL_MAX_APIS),
        "max_daily_requests": settings.get("max_daily_requests", TRIAL_MAX_DAILY_REQUESTS),
    }

    if days_elapsed >= 25:
        result["warning"] = "trial_expiring_soon"

    if days_elapsed >= TRIAL_DURATION_DAYS + TRIAL_GRACE_DAYS:
        result["expired"] = True

    return result
