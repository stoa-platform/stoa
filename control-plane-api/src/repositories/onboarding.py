"""Onboarding repository — data access for onboarding progress (CAB-1325)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.onboarding_progress import OnboardingProgress


class OnboardingRepository:
    """CRUD operations for onboarding progress."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user(self, tenant_id: str, user_id: str) -> OnboardingProgress | None:
        """Get onboarding progress for a specific user."""
        result = await self.session.execute(
            select(OnboardingProgress).where(
                OnboardingProgress.tenant_id == tenant_id,
                OnboardingProgress.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, tenant_id: str, user_id: str) -> OnboardingProgress:
        """Create a new onboarding progress record."""
        progress = OnboardingProgress(
            tenant_id=tenant_id,
            user_id=user_id,
            steps_completed={},
            started_at=datetime.now(UTC),
        )
        self.session.add(progress)
        await self.session.flush()
        return progress

    async def get_or_create(self, tenant_id: str, user_id: str) -> OnboardingProgress:
        """Get existing progress or create a new one."""
        existing = await self.get_by_user(tenant_id, user_id)
        if existing:
            return existing
        return await self.create(tenant_id, user_id)

    async def upsert_step(
        self, progress: OnboardingProgress, step_name: str
    ) -> OnboardingProgress:
        """Mark a step as completed (idempotent — re-marking is a no-op)."""
        steps = dict(progress.steps_completed or {})
        if steps.get(step_name):
            # Already completed — idempotent
            return progress

        now = datetime.now(UTC)
        steps[step_name] = now.isoformat()
        progress.steps_completed = steps

        # Compute TTFTC on first_call step
        if step_name == "first_call" and progress.ttftc_seconds is None and progress.started_at:
            delta = now - progress.started_at.replace(tzinfo=UTC) if progress.started_at.tzinfo is None else now - progress.started_at
            progress.ttftc_seconds = int(delta.total_seconds())

        await self.session.flush()
        return progress

    async def mark_complete(self, progress: OnboardingProgress) -> OnboardingProgress:
        """Mark onboarding as fully completed."""
        if progress.completed_at:
            # Already completed — idempotent
            return progress

        now = datetime.now(UTC)
        progress.completed_at = now

        # Compute TTFTC if not already set
        if progress.ttftc_seconds is None and progress.started_at:
            started = progress.started_at.replace(tzinfo=UTC) if progress.started_at.tzinfo is None else progress.started_at
            progress.ttftc_seconds = int((now - started).total_seconds())

        await self.session.flush()
        return progress
