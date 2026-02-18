"""Onboarding router — zero-touch trial endpoints (CAB-1325).

All endpoints under /v1/me/onboarding — uses get_current_user dep.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import User, get_current_user
from ..database import get_db
from ..repositories.onboarding import OnboardingRepository
from ..schemas.onboarding import OnboardingCompleteResponse, OnboardingProgressResponse

router = APIRouter(prefix="/v1/me/onboarding", tags=["onboarding"])

VALID_STEPS = ["choose_use_case", "subscribe_api", "create_app", "first_call"]


@router.get("", response_model=OnboardingProgressResponse)
async def get_onboarding_progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingProgressResponse:
    """Get current user's onboarding progress (creates if none exists)."""
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no tenant. Provision a tenant first.",
        )

    repo = OnboardingRepository(db)
    progress = await repo.get_or_create(current_user.tenant_id, current_user.id)
    await db.commit()

    return OnboardingProgressResponse(
        id=str(progress.id),
        tenant_id=progress.tenant_id,
        user_id=progress.user_id,
        steps_completed=progress.steps_completed or {},
        started_at=progress.started_at,
        completed_at=progress.completed_at,
        ttftc_seconds=progress.ttftc_seconds,
        is_complete=progress.completed_at is not None,
    )


@router.put("/steps/{step_name}", response_model=OnboardingProgressResponse)
async def mark_step_completed(
    step_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingProgressResponse:
    """Mark a specific onboarding step as completed (idempotent)."""
    if step_name not in VALID_STEPS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid step: {step_name}. Valid: {VALID_STEPS}",
        )

    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no tenant.",
        )

    repo = OnboardingRepository(db)
    progress = await repo.get_or_create(current_user.tenant_id, current_user.id)
    progress = await repo.upsert_step(progress, step_name)
    await db.commit()

    return OnboardingProgressResponse(
        id=str(progress.id),
        tenant_id=progress.tenant_id,
        user_id=progress.user_id,
        steps_completed=progress.steps_completed or {},
        started_at=progress.started_at,
        completed_at=progress.completed_at,
        ttftc_seconds=progress.ttftc_seconds,
        is_complete=progress.completed_at is not None,
    )


@router.post("/complete", response_model=OnboardingCompleteResponse)
async def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingCompleteResponse:
    """Mark onboarding as fully complete."""
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no tenant.",
        )

    repo = OnboardingRepository(db)
    progress = await repo.get_or_create(current_user.tenant_id, current_user.id)
    progress = await repo.mark_complete(progress)
    await db.commit()

    return OnboardingCompleteResponse(
        completed_at=progress.completed_at,
        ttftc_seconds=progress.ttftc_seconds,
    )
