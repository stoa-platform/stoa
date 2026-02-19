"""Onboarding repository — data access + analytics for onboarding progress (CAB-1325)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
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

    # ============== Phase 3: Analytics ==============

    async def get_funnel_stats(self) -> dict:
        """Compute onboarding funnel metrics across all users.

        Returns dict with: total_started, total_completed, step_counts,
        avg_ttftc_seconds, p50_ttftc_seconds, p90_ttftc_seconds.
        """
        result = await self.session.execute(select(OnboardingProgress))
        all_records = list(result.scalars().all())

        total_started = len(all_records)
        total_completed = sum(1 for r in all_records if r.completed_at is not None)

        # Count users who reached each step
        step_names = ["choose_use_case", "create_app", "subscribe_api", "first_call"]
        step_counts: dict[str, int] = {}
        for step in step_names:
            step_counts[step] = sum(
                1 for r in all_records if (r.steps_completed or {}).get(step) is not None
            )

        # TTFTC percentiles from completed users
        ttftc_values = sorted(r.ttftc_seconds for r in all_records if r.ttftc_seconds is not None)
        avg_ttftc = sum(ttftc_values) / len(ttftc_values) if ttftc_values else None
        p50_ttftc = _percentile(ttftc_values, 50) if ttftc_values else None
        p90_ttftc = _percentile(ttftc_values, 90) if ttftc_values else None

        return {
            "total_started": total_started,
            "total_completed": total_completed,
            "step_counts": step_counts,
            "avg_ttftc_seconds": avg_ttftc,
            "p50_ttftc_seconds": p50_ttftc,
            "p90_ttftc_seconds": p90_ttftc,
        }

    async def get_stalled_users(self, stall_hours: float = 24.0) -> list[dict]:
        """Find users who started onboarding but haven't completed within the threshold."""
        cutoff = datetime.now(UTC) - timedelta(hours=stall_hours)
        result = await self.session.execute(
            select(OnboardingProgress).where(
                OnboardingProgress.completed_at.is_(None),
                OnboardingProgress.started_at < cutoff,
            )
        )
        stalled = result.scalars().all()

        now = datetime.now(UTC)
        return [
            {
                "user_id": r.user_id,
                "tenant_id": r.tenant_id,
                "last_step": _last_step(r.steps_completed),
                "started_at": r.started_at,
                "hours_stalled": (now - (r.started_at.replace(tzinfo=UTC) if r.started_at.tzinfo is None else r.started_at)).total_seconds() / 3600,
            }
            for r in stalled
        ]

    async def count_all(self) -> int:
        """Count total onboarding records."""
        result = await self.session.execute(
            select(func.count()).select_from(OnboardingProgress)
        )
        return result.scalar_one()


def _percentile(sorted_values: list[int | float], pct: int) -> float:
    """Simple percentile from a sorted list."""
    if not sorted_values:
        return 0.0
    idx = (len(sorted_values) - 1) * pct / 100
    lower = int(idx)
    upper = lower + 1
    if upper >= len(sorted_values):
        return float(sorted_values[lower])
    frac = idx - lower
    return float(sorted_values[lower] * (1 - frac) + sorted_values[upper] * frac)


def _last_step(steps_completed: dict | None) -> str | None:
    """Find the most recently completed step by timestamp."""
    if not steps_completed:
        return None
    latest_step = None
    latest_ts = ""
    for step, ts in steps_completed.items():
        if ts and ts > latest_ts:
            latest_ts = ts
            latest_step = step
    return latest_step
