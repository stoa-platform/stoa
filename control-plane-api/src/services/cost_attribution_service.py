"""Cost attribution service - Phase 8

Queries Prometheus for per-tenant usage metrics:
  - API call counts
  - MCP tool invocations
  - Error rates
  - Latency percentiles
  - Trace span counts
  - Log volume (bytes)

Computes estimated costs and quota utilization per tier.
"""
import logging
from datetime import UTC, datetime, timedelta

from ..schemas.cost_attribution import (
    AdminUsageReport,
    EstimatedCost,
    QuotaUtilization,
    TenantTier,
    TenantUsageBreakdown,
    TenantUsageReport,
    TenantUsageSummary,
    UsageMetric,
)
from .prometheus_client import PrometheusClient, prometheus_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier quota limits (monthly)
# ---------------------------------------------------------------------------
TIER_QUOTAS = {
    TenantTier.DEMO: {"api_calls": 10_000, "tool_calls": 2_000},
    TenantTier.PLATFORM: {"api_calls": 50_000, "tool_calls": 10_000},
    TenantTier.BUSINESS: {"api_calls": 500_000, "tool_calls": 100_000},
    TenantTier.ENTERPRISE: {"api_calls": 5_000_000, "tool_calls": 1_000_000},
}

# ---------------------------------------------------------------------------
# Unit cost schedule (EUR per unit)
# ---------------------------------------------------------------------------
COST_RATES = {
    "api_call": 0.0001,       # EUR 0.10 per 1,000 calls
    "tool_call": 0.0002,      # EUR 0.20 per 1,000 tool calls
    "log_gb": 0.50,           # EUR 0.50 per GB
    "trace_span_1k": 0.002,   # EUR 2.00 per 1M spans
}


def _humanize(value: float, unit: str) -> str:
    """Produce a human-readable display string."""
    if unit == "bytes":
        if value >= 1e12:
            return f"{value / 1e12:.1f} TB"
        if value >= 1e9:
            return f"{value / 1e9:.1f} GB"
        if value >= 1e6:
            return f"{value / 1e6:.1f} MB"
        if value >= 1e3:
            return f"{value / 1e3:.1f} KB"
        return f"{value:.0f} B"
    if value >= 1e6:
        return f"{value / 1e6:.1f}M"
    if value >= 1e3:
        return f"{value / 1e3:.1f}K"
    if unit == "ms":
        return f"{value:.1f}ms"
    return f"{value:.0f}"


class CostAttributionService:
    """Per-tenant usage accounting via Prometheus queries."""

    def __init__(self, prometheus: PrometheusClient = prometheus_client):
        self._prom = prometheus

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def get_tenant_report(
        self,
        tenant_id: str,
        tenant_name: str,
        tier: str,
        days: int = 30,
    ) -> TenantUsageReport:
        """Full usage report for a single tenant."""
        tier_enum = TenantTier(tier)
        now = datetime.now(tz=UTC)
        period_start = now - timedelta(days=days)
        time_range = f"{days}d"

        usage = await self._get_usage_breakdown(tenant_id, time_range)
        quota = self._compute_quota(usage, tier_enum)
        cost = self._compute_cost(usage)

        return TenantUsageReport(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            tier=tier_enum,
            period_start=period_start,
            period_end=now,
            usage=usage,
            quota=quota,
            estimated_cost=cost,
            generated_at=now,
        )

    async def get_tenant_summary(
        self,
        tenant_id: str,
        tenant_name: str,
        tier: str,
    ) -> TenantUsageSummary:
        """Lightweight summary for admin list view."""
        tier_enum = TenantTier(tier)
        api_calls = await self._query_scalar(
            f'sum(increase(stoa_control_plane_http_requests_total{{tenant_id="{tenant_id}"}}[30d]))'
        )
        tool_calls = await self._query_scalar(
            f'sum(increase(stoa_mcp_tool_invocations_total{{tenant_id="{tenant_id}"}}[30d]))'
        )
        error_rate = await self._query_scalar(
            f'sum(rate(stoa_control_plane_http_requests_total{{tenant_id="{tenant_id}",status_code=~"5.."}}[30d]))'
            f' / sum(rate(stoa_control_plane_http_requests_total{{tenant_id="{tenant_id}"}}[30d])) * 100'
        )

        quota_limits = TIER_QUOTAS.get(tier_enum, TIER_QUOTAS[TenantTier.PLATFORM])
        api_limit = quota_limits["api_calls"]
        quota_pct = min(round(api_calls / api_limit * 100, 1), 100.0) if api_limit > 0 else 0.0

        est_cost = (
            api_calls * COST_RATES["api_call"]
            + tool_calls * COST_RATES["tool_call"]
        )

        return TenantUsageSummary(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            tier=tier_enum,
            api_calls_30d=int(api_calls),
            tool_calls_30d=int(tool_calls),
            error_rate_pct=round(error_rate, 2),
            quota_pct=quota_pct,
            estimated_cost=round(est_cost, 2),
        )

    async def get_admin_report(
        self,
        tenants: list[dict],
        days: int = 30,
    ) -> AdminUsageReport:
        """Admin-level report across all tenants.

        Args:
            tenants: List of dicts with keys: id, name, tier
            days: Report period in days
        """
        now = datetime.now(tz=UTC)
        period_start = now - timedelta(days=days)

        summaries = []
        total_api = 0
        total_tool = 0
        total_cost = 0.0
        by_tier: dict[str, int] = {}

        for t in tenants:
            try:
                summary = await self.get_tenant_summary(
                    tenant_id=t["id"],
                    tenant_name=t["name"],
                    tier=t.get("tier", "platform"),
                )
                summaries.append(summary)
                total_api += summary.api_calls_30d
                total_tool += summary.tool_calls_30d
                total_cost += summary.estimated_cost
                by_tier[summary.tier.value] = by_tier.get(summary.tier.value, 0) + 1
            except Exception as e:
                logger.warning("Failed to get usage for tenant %s: %s", t["id"], e)

        # Sort by cost descending
        summaries.sort(key=lambda s: s.estimated_cost, reverse=True)

        return AdminUsageReport(
            total_tenants=len(tenants),
            total_api_calls_30d=total_api,
            total_tool_calls_30d=total_tool,
            total_estimated_cost=round(total_cost, 2),
            by_tier=by_tier,
            tenants=summaries,
            period_start=period_start,
            period_end=now,
            generated_at=now,
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    async def _get_usage_breakdown(
        self,
        tenant_id: str,
        time_range: str,
    ) -> TenantUsageBreakdown:
        """Build detailed usage breakdown from Prometheus queries."""
        api_calls = await self._query_scalar(
            f'sum(increase(stoa_control_plane_http_requests_total{{tenant_id="{tenant_id}"}}[{time_range}]))'
        )
        tool_calls = await self._query_scalar(
            f'sum(increase(stoa_mcp_tool_invocations_total{{tenant_id="{tenant_id}"}}[{time_range}]))'
        )
        errors = await self._query_scalar(
            f'sum(increase(stoa_control_plane_http_requests_total{{tenant_id="{tenant_id}",status_code=~"5.."}}[{time_range}]))'
        )
        avg_latency = await self._query_scalar(
            f'avg(rate(stoa_control_plane_http_request_duration_seconds_sum{{tenant_id="{tenant_id}"}}[{time_range}]))'
            f' / avg(rate(stoa_control_plane_http_request_duration_seconds_count{{tenant_id="{tenant_id}"}}[{time_range}]))'
            f' * 1000'
        )
        p95_latency = await self._query_scalar(
            f'histogram_quantile(0.95, sum by (le) (rate(stoa_control_plane_http_request_duration_seconds_bucket'
            f'{{tenant_id="{tenant_id}"}}[{time_range}]))) * 1000'
        )
        trace_spans = await self._query_scalar(
            f'sum(increase(traces_spanmetrics_calls_total{{tenant="{tenant_id}"}}[{time_range}]))'
        )
        log_bytes = await self._query_scalar(
            f'sum(increase(loki_distributor_bytes_received_total{{tenant_id="{tenant_id}"}}[{time_range}]))'
        )

        return TenantUsageBreakdown(
            api_calls=UsageMetric(value=api_calls, unit="requests", display=_humanize(api_calls, "requests")),
            tool_invocations=UsageMetric(value=tool_calls, unit="calls", display=_humanize(tool_calls, "calls")),
            error_count=UsageMetric(value=errors, unit="errors", display=_humanize(errors, "errors")),
            avg_latency_ms=UsageMetric(value=avg_latency, unit="ms", display=_humanize(avg_latency, "ms")),
            p95_latency_ms=UsageMetric(value=p95_latency, unit="ms", display=_humanize(p95_latency, "ms")),
            trace_spans=UsageMetric(value=trace_spans, unit="spans", display=_humanize(trace_spans, "spans")),
            log_bytes=UsageMetric(value=log_bytes, unit="bytes", display=_humanize(log_bytes, "bytes")),
        )

    def _compute_quota(
        self,
        usage: TenantUsageBreakdown,
        tier: TenantTier,
    ) -> QuotaUtilization:
        """Compute quota utilization for the tier."""
        limits = TIER_QUOTAS.get(tier, TIER_QUOTAS[TenantTier.PLATFORM])
        api_limit = limits["api_calls"]
        tool_limit = limits["tool_calls"]
        api_used = int(usage.api_calls.value)
        tool_used = int(usage.tool_invocations.value)

        return QuotaUtilization(
            api_calls_used=api_used,
            api_calls_limit=api_limit,
            api_calls_pct=min(round(api_used / api_limit * 100, 1), 100.0) if api_limit > 0 else 0.0,
            tool_calls_used=tool_used,
            tool_calls_limit=tool_limit,
            tool_calls_pct=min(round(tool_used / tool_limit * 100, 1), 100.0) if tool_limit > 0 else 0.0,
        )

    def _compute_cost(self, usage: TenantUsageBreakdown) -> EstimatedCost:
        """Compute estimated cost from usage breakdown."""
        api_cost = usage.api_calls.value * COST_RATES["api_call"]
        tool_cost = usage.tool_invocations.value * COST_RATES["tool_call"]
        log_cost = (usage.log_bytes.value / 1e9) * COST_RATES["log_gb"]
        trace_cost = (usage.trace_spans.value / 1000) * COST_RATES["trace_span_1k"]

        return EstimatedCost(
            api_calls_cost=round(api_cost, 2),
            tool_calls_cost=round(tool_cost, 2),
            log_storage_cost=round(log_cost, 2),
            trace_storage_cost=round(trace_cost, 2),
            total_cost=round(api_cost + tool_cost + log_cost + trace_cost, 2),
        )

    async def _query_scalar(self, promql: str) -> float:
        """Execute a PromQL query and return a scalar float (0.0 on failure)."""
        data = await self._prom.query(promql)
        if not data:
            return 0.0
        try:
            result = data.get("result", [])
            if result and len(result) > 0:
                value = result[0].get("value", [None, "0"])
                raw = float(value[1]) if len(value) > 1 else 0.0
                # Handle NaN / Inf from Prometheus
                if raw != raw or raw == float("inf") or raw == float("-inf"):
                    return 0.0
                return raw
        except (IndexError, ValueError, TypeError) as e:
            logger.debug("Error parsing Prometheus result for query %s: %s", promql[:80], e)
        return 0.0


# Global instance
cost_attribution_service = CostAttributionService()
