"""Repository for onboarding progress CRUD (CAB-1325)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.onboarding_progress import OnboardingProgress


class OnboardingRepository:
    """Repository for onboarding progress database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user(self, tenant_id: str, user_id: str) -> OnboardingProgress | None:
        result = await self.session.execute(
            select(OnboardingProgress).where(
                OnboardingProgress.tenant_id == tenant_id,
                OnboardingProgress.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, tenant_id: str, user_id: str) -> OnboardingProgress:
        progress = OnboardingProgress(
            tenant_id=tenant_id,
            user_id=user_id,
            steps_completed={},
        )
        self.session.add(progress)
        await self.session.flush()
        await self.session.refresh(progress)
        return progress

    async def get_or_create(self, tenant_id: str, user_id: str) -> OnboardingProgress:
        existing = await self.get_by_user(tenant_id, user_id)
        if existing:
            return existing
        return await self.create(tenant_id, user_id)

    async def upsert_step(
        self, progress: OnboardingProgress, step_name: str
    ) -> OnboardingProgress:
        """Mark a step as completed. Idempotent — re-marking is a no-op."""
        steps = dict(progress.steps_completed or {})
        if step_name in steps:
            return progress  # Already completed — no-op

        now = datetime.now(UTC)
        steps[step_name] = now.isoformat()
        progress.steps_completed = steps

        # Compute TTFTC on first_call step
        if step_name == "first_call" and progress.started_at and not progress.ttftc_seconds:
            started = progress.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            delta = now - started
            progress.ttftc_seconds = int(delta.total_seconds())

        await self.session.flush()
        await self.session.refresh(progress)
        return progress

    async def mark_complete(self, progress: OnboardingProgress) -> OnboardingProgress:
        """Mark onboarding as fully completed."""
        if not progress.completed_at:
            progress.completed_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(progress)
        return progress
