"""LLM Usage & Cost monitoring endpoints (CAB-1487, CAB-1822).

DB-backed endpoints for the Console UI cost dashboard.
Queries usage_summaries table populated by gateway /v1/usage/record metering.
Falls back to Prometheus gateway_llm_* metrics when available.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..repositories.usage_metering import UsageMeteringRepository
from ..schemas.llm_budget import (
    LlmAnomaliesResponse,
    LlmAnomalyEntry,
    LlmProviderBreakdownResponse,
    LlmProviderCostEntry,
    LlmTimeseriesPoint,
    LlmTimeseriesResponse,
    LlmUsageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/llm/usage",
    tags=["LLM Usage & Cost Monitoring"],
)

# Time range mapping: period parameter -> (PromQL range, resolution step, days)
_PERIOD_MAP: dict[str, tuple[str, str, int]] = {
    "hour": ("1h", "5m", 0),
    "day": ("24h", "1h", 1),
    "week": ("7d", "6h", 7),
    "month": ("30d", "1d", 30),
}

# Anthropic Claude pricing (per token, USD) — used to estimate cost from token counts
# Source: https://docs.anthropic.com/en/docs/about-claude/models
_ANTHROPIC_INPUT_COST = 3.0 / 1_000_000  # $3/MTok (Sonnet)
_ANTHROPIC_OUTPUT_COST = 15.0 / 1_000_000  # $15/MTok (Sonnet)
_ANTHROPIC_CACHE_WRITE_COST = 3.75 / 1_000_000  # $3.75/MTok
_ANTHROPIC_CACHE_READ_COST = 0.30 / 1_000_000  # $0.30/MTok


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


def _resolve_period(period: str) -> tuple[str, str, int]:
    """Resolve period name to (PromQL range, step, days)."""
    return _PERIOD_MAP.get(period, _PERIOD_MAP["month"])


def _compute_cost(
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> dict:
    """Compute estimated USD cost from token counts using Anthropic pricing."""
    input_cost = input_tokens * _ANTHROPIC_INPUT_COST
    output_cost = output_tokens * _ANTHROPIC_OUTPUT_COST
    cache_write_cost = cache_creation_input_tokens * _ANTHROPIC_CACHE_WRITE_COST
    cache_read_cost = cache_read_input_tokens * _ANTHROPIC_CACHE_READ_COST
    total_cost = input_cost + output_cost + cache_write_cost + cache_read_cost
    return {
        "total_cost_usd": round(total_cost, 6),
        "cache_write_cost_usd": round(cache_write_cost, 6),
        "cache_read_cost_usd": round(cache_read_cost, 6),
    }


def _period_to_since(period: str) -> datetime:
    """Convert period name to a 'since' datetime (tz-naive for DB comparison)."""
    now = datetime.now(UTC).replace(tzinfo=None)
    _range, _step, days = _resolve_period(period)
    if days == 0:
        return now - timedelta(hours=1)
    return now - timedelta(days=days)


@router.get("", response_model=LlmUsageResponse)
async def get_llm_usage(
    tenant_id: str,
    period: str = Query(default="month", pattern=r"^(hour|day|week|month)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get LLM usage summary: total cost, tokens, avg cost/request, cache savings."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    since = _period_to_since(period)
    repo = UsageMeteringRepository(db)
    totals = await repo.get_llm_usage_totals(tenant_id=tenant_id, since=since)

    costs = _compute_cost(
        input_tokens=totals["input_tokens"],
        output_tokens=totals["output_tokens"],
        cache_creation_input_tokens=totals["cache_creation_input_tokens"],
        cache_read_input_tokens=totals["cache_read_input_tokens"],
    )

    total_requests = totals["total_requests"]
    avg_cost = costs["total_cost_usd"] / total_requests if total_requests > 0 else 0.0

    return LlmUsageResponse(
        total_cost_usd=costs["total_cost_usd"],
        input_tokens=totals["input_tokens"],
        output_tokens=totals["output_tokens"],
        avg_cost_per_request=round(avg_cost, 6),
        cache_read_cost_usd=costs["cache_read_cost_usd"],
        cache_write_cost_usd=costs["cache_write_cost_usd"],
        period=period,
    )


@router.get("/timeseries", response_model=LlmTimeseriesResponse)
async def get_llm_timeseries(
    tenant_id: str,
    period: str = Query(default="week", pattern=r"^(hour|day|week|month)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get LLM cost time-series for charting."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    since = _period_to_since(period)
    _range, step, _days = _resolve_period(period)
    repo = UsageMeteringRepository(db)
    rows = await repo.get_llm_usage_timeseries(tenant_id=tenant_id, since=since)

    points = []
    for row in rows:
        costs = _compute_cost(
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cache_creation_input_tokens=row["cache_creation_input_tokens"],
            cache_read_input_tokens=row["cache_read_input_tokens"],
        )
        points.append(
            LlmTimeseriesPoint(
                timestamp=row["period_start"].isoformat() + "Z",
                value=costs["total_cost_usd"],
            )
        )

    return LlmTimeseriesResponse(
        points=points,
        period=period,
        step=step,
    )


@router.get("/providers", response_model=LlmProviderBreakdownResponse)
async def get_llm_provider_breakdown(
    tenant_id: str,
    period: str = Query(default="month", pattern=r"^(hour|day|week|month)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get LLM cost breakdown by provider and model."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    since = _period_to_since(period)
    repo = UsageMeteringRepository(db)
    totals = await repo.get_llm_usage_totals(tenant_id=tenant_id, since=since)

    costs = _compute_cost(
        input_tokens=totals["input_tokens"],
        output_tokens=totals["output_tokens"],
        cache_creation_input_tokens=totals["cache_creation_input_tokens"],
        cache_read_input_tokens=totals["cache_read_input_tokens"],
    )

    # Usage records from gateway don't carry provider/model labels,
    # so report as single "anthropic" / "claude" entry for now.
    providers = []
    if costs["total_cost_usd"] > 0:
        providers.append(
            LlmProviderCostEntry(
                provider="anthropic",
                model="claude",
                cost_usd=costs["total_cost_usd"],
            )
        )

    return LlmProviderBreakdownResponse(
        providers=providers,
        period=period,
    )


@router.get("/anomalies", response_model=LlmAnomaliesResponse)
async def get_llm_anomalies(
    tenant_id: str,
    period: str = Query(default="month", pattern=r"^(hour|day|week|month)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get LLM latency anomalies per provider (high latency = cost risk)."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    since = _period_to_since(period)
    repo = UsageMeteringRepository(db)
    totals = await repo.get_llm_usage_totals(tenant_id=tenant_id, since=since)

    entries = []
    total_requests = totals["total_requests"]
    if total_requests > 0:
        avg_latency_s = (totals["total_latency_ms"] / total_requests) / 1000.0
        entries.append(
            LlmAnomalyEntry(
                provider="anthropic",
                avg_latency_seconds=round(avg_latency_s, 4),
            )
        )

    return LlmAnomaliesResponse(
        entries=entries,
        period=period,
    )
