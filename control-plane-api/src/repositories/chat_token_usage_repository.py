"""Repository for ChatTokenUsage — daily aggregated token metering (CAB-288)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.chat_token_usage import ChatTokenUsage


class ChatTokenUsageRepository:
    """Data-access layer for chat token usage counters."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def increment(
        self,
        *,
        tenant_id: str,
        user_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> ChatTokenUsage:
        """Atomic upsert: increment daily counters for a tenant/user/model."""
        today = datetime.now(UTC).date()
        stmt = (
            insert(ChatTokenUsage)
            .values(
                tenant_id=tenant_id,
                user_id=user_id,
                model=model,
                period_date=today,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                request_count=1,
            )
            .on_conflict_do_update(
                constraint="uq_chat_token_usage_tenant_user_model_date",
                set_={
                    "input_tokens": ChatTokenUsage.input_tokens + input_tokens,
                    "output_tokens": ChatTokenUsage.output_tokens + output_tokens,
                    "total_tokens": ChatTokenUsage.total_tokens + input_tokens + output_tokens,
                    "request_count": ChatTokenUsage.request_count + 1,
                    "updated_at": func.now(),
                },
            )
            .returning(ChatTokenUsage)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one()

    async def get_daily_user_usage(self, tenant_id: str, user_id: str) -> int:
        """Return total tokens consumed today by a specific user."""
        today = datetime.now(UTC).date()
        stmt = select(func.coalesce(func.sum(ChatTokenUsage.total_tokens), 0)).where(
            ChatTokenUsage.tenant_id == tenant_id,
            ChatTokenUsage.user_id == user_id,
            ChatTokenUsage.period_date == today,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_daily_tenant_usage(self, tenant_id: str) -> int:
        """Return total tokens consumed today across all users in a tenant."""
        today = datetime.now(UTC).date()
        stmt = select(func.coalesce(func.sum(ChatTokenUsage.total_tokens), 0)).where(
            ChatTokenUsage.tenant_id == tenant_id,
            ChatTokenUsage.period_date == today,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_budget_status(self, tenant_id: str, user_id: str, *, daily_budget: int) -> dict[str, Any]:
        """Compute budget status for a user."""
        user_today = await self.get_daily_user_usage(tenant_id, user_id)
        tenant_today = await self.get_daily_tenant_usage(tenant_id)

        remaining = max(0, daily_budget - user_today)
        usage_percent = min(100.0, (user_today / daily_budget * 100) if daily_budget > 0 else 0.0)

        return {
            "user_tokens_today": user_today,
            "tenant_tokens_today": tenant_today,
            "daily_budget": daily_budget,
            "remaining": remaining,
            "budget_exceeded": user_today >= daily_budget,
            "usage_percent": usage_percent,
        }

    async def get_usage_stats(self, tenant_id: str, *, days: int = 30) -> dict[str, Any]:
        """Aggregate token usage statistics over a period."""
        start_date = (datetime.now(UTC) - timedelta(days=days)).date()

        # Totals
        totals_stmt = select(
            func.coalesce(func.sum(ChatTokenUsage.total_tokens), 0),
            func.coalesce(func.sum(ChatTokenUsage.input_tokens), 0),
            func.coalesce(func.sum(ChatTokenUsage.output_tokens), 0),
            func.coalesce(func.sum(ChatTokenUsage.request_count), 0),
        ).where(
            ChatTokenUsage.tenant_id == tenant_id,
            ChatTokenUsage.period_date >= start_date,
        )
        totals_result = await self.session.execute(totals_stmt)
        total_tokens, total_input, total_output, total_requests = totals_result.one()

        # Today
        today = datetime.now(UTC).date()
        today_stmt = select(func.coalesce(func.sum(ChatTokenUsage.total_tokens), 0)).where(
            ChatTokenUsage.tenant_id == tenant_id,
            ChatTokenUsage.period_date == today,
        )
        today_result = await self.session.execute(today_stmt)
        today_tokens = today_result.scalar_one()

        # Top users
        top_users_stmt = (
            select(
                ChatTokenUsage.user_id,
                func.sum(ChatTokenUsage.total_tokens).label("tokens"),
            )
            .where(
                ChatTokenUsage.tenant_id == tenant_id,
                ChatTokenUsage.period_date >= start_date,
            )
            .group_by(ChatTokenUsage.user_id)
            .order_by(func.sum(ChatTokenUsage.total_tokens).desc())
            .limit(10)
        )
        top_result = await self.session.execute(top_users_stmt)
        top_users = [{"user_id": r.user_id, "tokens": r.tokens} for r in top_result.all()]

        # Daily breakdown
        daily_stmt = (
            select(
                ChatTokenUsage.period_date.label("day"),
                func.sum(ChatTokenUsage.total_tokens).label("tokens"),
                func.sum(ChatTokenUsage.request_count).label("requests"),
            )
            .where(
                ChatTokenUsage.tenant_id == tenant_id,
                ChatTokenUsage.period_date >= start_date,
            )
            .group_by(ChatTokenUsage.period_date)
            .order_by(ChatTokenUsage.period_date)
        )
        daily_result = await self.session.execute(daily_stmt)
        daily_breakdown = [{"date": str(r.day), "tokens": r.tokens, "requests": r.requests} for r in daily_result.all()]

        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_tokens": total_tokens,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_requests": total_requests,
            "today_tokens": today_tokens,
            "top_users": top_users,
            "daily_breakdown": daily_breakdown,
        }
