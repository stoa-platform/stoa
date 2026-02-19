"""Onboarding admin router — funnel analytics + stalled users (CAB-1325 Phase 3).

All endpoints under /v1/admin/onboarding — cpi-admin only.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.rbac import require_role
from ..database import get_db
from ..repositories.onboarding import OnboardingRepository
from ..schemas.onboarding import FunnelResponse, FunnelStage, StalledUserResponse

router = APIRouter(prefix="/v1/admin/onboarding", tags=["onboarding-admin"])

FUNNEL_STAGES = ["registered", "choose_use_case", "create_app", "subscribe_api", "first_call"]


@router.get("/funnel", response_model=FunnelResponse)
async def get_onboarding_funnel(
    _user=Depends(require_role(["cpi-admin"])),
    db: AsyncSession = Depends(get_db),
) -> FunnelResponse:
    """Get onboarding funnel analytics with conversion rates and TTFTC stats."""
    repo = OnboardingRepository(db)
    stats = await repo.get_funnel_stats()

    total_started = stats["total_started"]
    step_counts = stats["step_counts"]

    stages = []
    for stage_name in FUNNEL_STAGES:
        count = total_started if stage_name == "registered" else step_counts.get(stage_name, 0)
        rate = count / total_started if total_started > 0 else None
        stages.append(FunnelStage(stage=stage_name, count=count, conversion_rate=rate))

    return FunnelResponse(
        stages=stages,
        total_started=total_started,
        total_completed=stats["total_completed"],
        avg_ttftc_seconds=stats["avg_ttftc_seconds"],
        p50_ttftc_seconds=stats["p50_ttftc_seconds"],
        p90_ttftc_seconds=stats["p90_ttftc_seconds"],
    )


@router.get("/stalled", response_model=list[StalledUserResponse])
async def get_stalled_users(
    hours: float = Query(default=24.0, ge=1.0, le=720.0, description="Hours threshold"),
    _user=Depends(require_role(["cpi-admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[StalledUserResponse]:
    """Get users who started onboarding but haven't completed within the threshold."""
    repo = OnboardingRepository(db)
    stalled = await repo.get_stalled_users(stall_hours=hours)

    return [StalledUserResponse(**s) for s in stalled]
