"""Billing service — cost computation + department budget alerts (CAB-1457).

compute_cost is the sole financial source of truth for tool-call pricing.
All costs are in micro-cents (1 USD = 100_000_000 micro-cents) to prevent
floating-point drift in aggregate sums.

Webhook payloads contain NO PII — only department-level aggregates.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.billing_ledger import BillingLedger
from ..models.department_budget import DepartmentBudget

logger = logging.getLogger(__name__)

# 1 USD = 100_000_000 micro-cents
MICROCENTS_PER_USD = 100_000_000

# Pricing constants (micro-cents)
BASE_COST = 100  # flat per-call
TOKEN_COST_PER_TOKEN = 1
LATENCY_COST_PER_MS = 0.1
PREMIUM_MULTIPLIER = 2


class BillingService:
    """Stateless billing operations — receives a DB session per call."""

    # ------------------------------------------------------------------
    # Cost computation (pure, no I/O)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_cost(token_count: int, latency_ms: int, tool_tier: str) -> int:
        """Return cost in micro-cents for a single tool invocation.

        Formula:
            base_cost (100) + token_cost (1 * tokens) + latency_cost (0.1 * ms)
            Premium tier applies a 2x multiplier.
        """
        raw = BASE_COST + (TOKEN_COST_PER_TOKEN * token_count) + (LATENCY_COST_PER_MS * latency_ms)
        if tool_tier == "premium":
            raw *= PREMIUM_MULTIPLIER
        return int(raw)

    # ------------------------------------------------------------------
    # Spend aggregation
    # ------------------------------------------------------------------

    @staticmethod
    async def get_department_spend(db: AsyncSession, department_id: str, period_month: str) -> float:
        """Sum cost_microcents for a department/month and return USD."""
        result = await db.execute(
            select(func.coalesce(func.sum(BillingLedger.cost_microcents), 0)).where(
                BillingLedger.department_id == department_id,
                BillingLedger.period_month == period_month,
            )
        )
        total_microcents: int = result.scalar_one()
        return total_microcents / MICROCENTS_PER_USD

    # ------------------------------------------------------------------
    # Alert engine
    # ------------------------------------------------------------------

    @staticmethod
    async def check_alerts(db: AsyncSession, department_id: str, tenant_id: str) -> None:
        """Fire webhook alerts when spend crosses configured thresholds.

        Only fires once per threshold per month (idempotent).
        Webhook payload contains NO PII — department aggregates only.
        """
        now = datetime.now(UTC)
        period = now.strftime("%Y-%m")

        # Fetch budget config
        result = await db.execute(
            select(DepartmentBudget).where(
                DepartmentBudget.department_id == department_id,
                DepartmentBudget.tenant_id == tenant_id,
            )
        )
        budget = result.scalar_one_or_none()
        if budget is None or not budget.alert_webhook_url:
            return

        spend_usd = await BillingService.get_department_spend(db, department_id, period)
        budget_usd = float(budget.monthly_budget_usd)
        if budget_usd <= 0:
            return

        pct_used = (spend_usd / budget_usd) * 100
        thresholds: dict = budget.alert_thresholds or {}
        fired: dict = budget.alerts_fired_this_month or {}

        for threshold_str, enabled in thresholds.items():
            threshold_pct = int(threshold_str)
            if not enabled:
                continue
            if fired.get(threshold_str):
                continue  # already fired this month
            if pct_used < threshold_pct:
                continue

            # Fire webhook — no PII, department aggregates only
            payload = {
                "department_id": department_id,
                "threshold_pct": threshold_pct,
                "spend_usd": round(spend_usd, 2),
                "budget_usd": round(budget_usd, 2),
                "period": period,
            }
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(budget.alert_webhook_url, json=payload)
                    resp.raise_for_status()
                fired[threshold_str] = True
                logger.info("Budget alert fired: dept=%s threshold=%s%%", department_id, threshold_pct)
            except Exception:
                logger.warning(
                    "Failed to fire budget alert: dept=%s threshold=%s%%",
                    department_id,
                    threshold_pct,
                    exc_info=True,
                )

        # Persist which thresholds have been fired
        if fired != (budget.alerts_fired_this_month or {}):
            await db.execute(
                update(DepartmentBudget).where(DepartmentBudget.id == budget.id).values(alerts_fired_this_month=fired)
            )
            await db.flush()

    # ------------------------------------------------------------------
    # Monthly reset
    # ------------------------------------------------------------------

    @staticmethod
    async def reset_monthly_alerts(db: AsyncSession) -> None:
        """Clear alerts_fired_this_month for all departments (new month boundary)."""
        await db.execute(update(DepartmentBudget).values(alerts_fired_this_month={}))
        await db.flush()
