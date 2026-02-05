"""Pydantic schemas for Cost Attribution API endpoints - Phase 8

Per-tenant usage accounting: call counts, bandwidth, trace spans,
log volume, estimated cost, quota utilization.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.tenant import TenantTier


class UsageMetric(BaseModel):
    """Single usage metric with value and unit."""
    value: float = Field(..., ge=0, description="Metric value")
    unit: str = Field(..., description="Unit of measurement")
    display: str = Field(..., description="Human-readable display value")


class TenantUsageBreakdown(BaseModel):
    """Detailed usage breakdown for a tenant."""
    api_calls: UsageMetric = Field(..., description="Total API requests")
    tool_invocations: UsageMetric = Field(..., description="MCP tool invocations")
    error_count: UsageMetric = Field(..., description="5xx error count")
    avg_latency_ms: UsageMetric = Field(..., description="Average response latency")
    p95_latency_ms: UsageMetric = Field(..., description="p95 response latency")
    trace_spans: UsageMetric = Field(..., description="Distributed trace spans generated")
    log_bytes: UsageMetric = Field(..., description="Log volume ingested")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "api_calls": {"value": 125430, "unit": "requests", "display": "125.4K"},
                "tool_invocations": {"value": 43210, "unit": "calls", "display": "43.2K"},
                "error_count": {"value": 12, "unit": "errors", "display": "12"},
                "avg_latency_ms": {"value": 142.5, "unit": "ms", "display": "142.5ms"},
                "p95_latency_ms": {"value": 380.0, "unit": "ms", "display": "380ms"},
                "trace_spans": {"value": 890120, "unit": "spans", "display": "890.1K"},
                "log_bytes": {"value": 2147483648, "unit": "bytes", "display": "2.0 GB"},
            }
        }
    )


class QuotaUtilization(BaseModel):
    """Quota usage against limits for a tier."""
    api_calls_used: int = Field(..., ge=0, description="API calls used in period")
    api_calls_limit: int = Field(..., ge=0, description="API call limit for tier")
    api_calls_pct: float = Field(..., ge=0, le=100, description="Percentage used")
    tool_calls_used: int = Field(..., ge=0, description="Tool calls used in period")
    tool_calls_limit: int = Field(..., ge=0, description="Tool call limit for tier")
    tool_calls_pct: float = Field(..., ge=0, le=100, description="Percentage used")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "api_calls_used": 125430,
                "api_calls_limit": 500000,
                "api_calls_pct": 25.1,
                "tool_calls_used": 43210,
                "tool_calls_limit": 100000,
                "tool_calls_pct": 43.2,
            }
        }
    )


class EstimatedCost(BaseModel):
    """Estimated cost breakdown."""
    api_calls_cost: float = Field(..., ge=0, description="Cost for API calls")
    tool_calls_cost: float = Field(..., ge=0, description="Cost for tool invocations")
    log_storage_cost: float = Field(..., ge=0, description="Cost for log storage")
    trace_storage_cost: float = Field(..., ge=0, description="Cost for trace storage")
    total_cost: float = Field(..., ge=0, description="Total estimated cost")
    currency: str = Field(default="EUR", description="Currency code")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "api_calls_cost": 12.54,
                "tool_calls_cost": 8.64,
                "log_storage_cost": 2.15,
                "trace_storage_cost": 0.89,
                "total_cost": 24.22,
                "currency": "EUR",
            }
        }
    )


class TenantUsageReport(BaseModel):
    """Complete usage report for a tenant."""
    tenant_id: str = Field(..., description="Tenant identifier")
    tenant_name: str = Field(..., description="Tenant display name")
    tier: TenantTier = Field(..., description="Tenant commercial tier")
    period_start: datetime = Field(..., description="Report period start")
    period_end: datetime = Field(..., description="Report period end")
    usage: TenantUsageBreakdown = Field(..., description="Usage metrics breakdown")
    quota: QuotaUtilization = Field(..., description="Quota utilization")
    estimated_cost: EstimatedCost = Field(..., description="Estimated cost")
    generated_at: datetime = Field(..., description="Report generation timestamp")


class TenantUsageSummary(BaseModel):
    """Lightweight tenant usage summary for admin list view."""
    tenant_id: str = Field(..., description="Tenant identifier")
    tenant_name: str = Field(..., description="Tenant display name")
    tier: TenantTier = Field(..., description="Tenant commercial tier")
    api_calls_30d: int = Field(..., ge=0, description="API calls in last 30 days")
    tool_calls_30d: int = Field(..., ge=0, description="Tool calls in last 30 days")
    error_rate_pct: float = Field(..., ge=0, le=100, description="Error rate percentage")
    quota_pct: float = Field(..., ge=0, le=100, description="Quota utilization percentage")
    estimated_cost: float = Field(..., ge=0, description="Estimated monthly cost")
    currency: str = Field(default="EUR", description="Currency code")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "acme-corp",
                "tenant_name": "ACME Corporation",
                "tier": "enterprise",
                "api_calls_30d": 125430,
                "tool_calls_30d": 43210,
                "error_rate_pct": 0.1,
                "quota_pct": 25.1,
                "estimated_cost": 24.22,
                "currency": "EUR",
            }
        }
    )


class AdminUsageReport(BaseModel):
    """Admin-level usage report across all tenants."""
    total_tenants: int = Field(..., ge=0, description="Total number of tenants")
    total_api_calls_30d: int = Field(..., ge=0, description="Total API calls across all tenants")
    total_tool_calls_30d: int = Field(..., ge=0, description="Total tool calls across all tenants")
    total_estimated_cost: float = Field(..., ge=0, description="Total estimated cost")
    currency: str = Field(default="EUR", description="Currency code")
    by_tier: dict[str, int] = Field(
        default_factory=dict,
        description="Tenant count by tier"
    )
    tenants: list[TenantUsageSummary] = Field(
        default_factory=list,
        description="Per-tenant usage summaries"
    )
    period_start: datetime = Field(..., description="Report period start")
    period_end: datetime = Field(..., description="Report period end")
    generated_at: datetime = Field(..., description="Report generation timestamp")
