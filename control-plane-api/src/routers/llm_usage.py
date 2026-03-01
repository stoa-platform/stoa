"""LLM Usage & Cost monitoring endpoints (CAB-1487).

Prometheus-backed endpoints for the Console UI cost dashboard.
Queries gateway_llm_* metrics emitted by the Rust gateway.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import User, get_current_user
from ..schemas.llm_budget import (
    LlmAnomaliesResponse,
    LlmAnomalyEntry,
    LlmProviderBreakdownResponse,
    LlmProviderCostEntry,
    LlmTimeseriesPoint,
    LlmTimeseriesResponse,
    LlmUsageResponse,
)
from ..services.prometheus_client import prometheus_client

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/llm/usage",
    tags=["LLM Usage & Cost Monitoring"],
)

# Time range mapping: period parameter -> PromQL range + resolution step
_PERIOD_MAP: dict[str, tuple[str, str, int]] = {
    "hour": ("1h", "5m", 0),
    "day": ("24h", "1h", 1),
    "week": ("7d", "6h", 7),
    "month": ("30d", "1d", 30),
}


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


def _resolve_period(period: str) -> tuple[str, str, int]:
    """Resolve period name to (PromQL range, step, days)."""
    return _PERIOD_MAP.get(period, _PERIOD_MAP["month"])


@router.get("", response_model=LlmUsageResponse)
async def get_llm_usage(
    tenant_id: str,
    period: str = Query(default="month", pattern=r"^(hour|day|week|month)$"),
    user: User = Depends(get_current_user),
):
    """Get LLM usage summary: total cost, tokens, avg cost/request, cache savings."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    if not prometheus_client.is_enabled:
        raise HTTPException(status_code=503, detail="Prometheus not available")

    time_range, _step, _days = _resolve_period(period)

    cost = await prometheus_client.get_llm_cost_total(tenant_id=tenant_id, time_range=time_range)
    tokens = await prometheus_client.get_llm_token_totals(tenant_id=tenant_id, time_range=time_range)
    avg_cost = await prometheus_client.get_llm_avg_cost_per_request(tenant_id=tenant_id, time_range=time_range)
    cache = await prometheus_client.get_llm_cache_savings(tenant_id=tenant_id, time_range=time_range)

    return LlmUsageResponse(
        total_cost_usd=round(cost, 6),
        input_tokens=tokens["input_tokens"],
        output_tokens=tokens["output_tokens"],
        avg_cost_per_request=avg_cost,
        cache_read_cost_usd=cache["cache_read_cost_usd"],
        cache_write_cost_usd=cache["cache_write_cost_usd"],
        period=period,
    )


@router.get("/timeseries", response_model=LlmTimeseriesResponse)
async def get_llm_timeseries(
    tenant_id: str,
    period: str = Query(default="week", pattern=r"^(hour|day|week|month)$"),
    user: User = Depends(get_current_user),
):
    """Get LLM cost time-series for charting."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    if not prometheus_client.is_enabled:
        raise HTTPException(status_code=503, detail="Prometheus not available")

    _range, step, days = _resolve_period(period)
    raw_points = await prometheus_client.get_llm_cost_timeseries(tenant_id=tenant_id, days=max(days, 1), step=step)

    return LlmTimeseriesResponse(
        points=[LlmTimeseriesPoint(**p) for p in raw_points],
        period=period,
        step=step,
    )


@router.get("/providers", response_model=LlmProviderBreakdownResponse)
async def get_llm_provider_breakdown(
    tenant_id: str,
    period: str = Query(default="month", pattern=r"^(hour|day|week|month)$"),
    user: User = Depends(get_current_user),
):
    """Get LLM cost breakdown by provider and model."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    if not prometheus_client.is_enabled:
        raise HTTPException(status_code=503, detail="Prometheus not available")

    time_range, _step, _days = _resolve_period(period)
    raw = await prometheus_client.get_llm_provider_breakdown(tenant_id=tenant_id, time_range=time_range)

    return LlmProviderBreakdownResponse(
        providers=[LlmProviderCostEntry(**e) for e in raw],
        period=period,
    )


@router.get("/anomalies", response_model=LlmAnomaliesResponse)
async def get_llm_anomalies(
    tenant_id: str,
    period: str = Query(default="month", pattern=r"^(hour|day|week|month)$"),
    user: User = Depends(get_current_user),
):
    """Get LLM latency anomalies per provider (high latency = cost risk)."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    if not prometheus_client.is_enabled:
        raise HTTPException(status_code=503, detail="Prometheus not available")

    time_range, _step, _days = _resolve_period(period)
    raw = await prometheus_client.get_llm_latency_by_provider(tenant_id=tenant_id, time_range=time_range)

    return LlmAnomaliesResponse(
        entries=[LlmAnomalyEntry(**e) for e in raw],
        period=period,
    )
