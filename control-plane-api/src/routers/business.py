"""
Business Analytics API Router - CAB-Observability

Endpoints for the Business Dashboard (Console UI).
Provides business metrics combining database and Prometheus data.

Routes:
- GET /v1/business/metrics - Business analytics metrics
- GET /v1/business/top-apis - Top APIs by usage
"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User
from ..auth.rbac import require_role
from ..database import get_db
from ..models.tenant import Tenant, TenantStatus
from ..services.prometheus_client import prometheus_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/business", tags=["Business Analytics"])


class BusinessMetrics(BaseModel):
    """Business dashboard metrics response."""

    active_tenants: int  # Count of active tenants
    new_tenants_30d: int  # New tenants in last 30 days
    tenant_growth: float  # Growth percentage
    apdex_score: float  # Platform APDEX score (0-1)
    total_tokens: int  # Total tokens consumed
    total_calls: int  # Total API calls


class TopAPI(BaseModel):
    """Top API/tool by usage."""

    tool_name: str  # Internal tool name
    display_name: str  # Human-readable name
    calls: int  # Number of calls


def _extract_scalar(result: dict | None, default: float = 0.0) -> float:
    """Extract scalar value from Prometheus result."""
    if not result:
        return default
    try:
        if result.get("resultType") == "vector":
            values = result.get("result", [])
            if values:
                raw_value = float(values[0].get("value", [0, 0])[1])
                # Handle NaN and Inf
                if raw_value != raw_value or raw_value == float("inf"):
                    return default
                return raw_value
        return default
    except (IndexError, ValueError, TypeError):
        return default


def _humanize_tool_name(tool_name: str) -> str:
    """Convert tool_name to a human-readable display name."""
    # Remove common prefixes
    name = tool_name
    for prefix in ["mcp_", "stoa_", "api_"]:
        if name.lower().startswith(prefix):
            name = name[len(prefix):]

    # Convert snake_case to Title Case
    return " ".join(word.capitalize() for word in name.split("_"))


@router.get("/metrics", response_model=BusinessMetrics)
async def get_business_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["cpi-admin", "admin"])),
) -> BusinessMetrics:
    """
    Get business analytics metrics.

    Requires cpi-admin or admin role.

    Returns:
    - active_tenants: Number of active tenants in the platform
    - new_tenants_30d: Tenants created in the last 30 days
    - tenant_growth: Growth rate percentage
    - apdex_score: Platform APDEX score (from Prometheus)
    - total_tokens: Total tokens consumed (from Prometheus)
    - total_calls: Total API calls (from Prometheus)
    """
    logger.info(f"Fetching business metrics for user={current_user.id}")

    try:
        # Get tenant counts from database
        active_result = await db.execute(
            select(func.count(Tenant.id)).where(
                Tenant.status == TenantStatus.ACTIVE.value
            )
        )
        active_tenants = active_result.scalar_one() or 0

        # New tenants in last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        new_result = await db.execute(
            select(func.count(Tenant.id)).where(
                Tenant.created_at >= thirty_days_ago
            )
        )
        new_tenants = new_result.scalar_one() or 0

        # Calculate growth (new / (active - new) * 100)
        previous_count = active_tenants - new_tenants
        tenant_growth = (
            round((new_tenants / previous_count) * 100, 1)
            if previous_count > 0
            else 0.0
        )

    except Exception as e:
        logger.error(f"Database query failed: {e}")
        active_tenants = 0
        new_tenants = 0
        tenant_growth = 0.0

    # Get metrics from Prometheus
    apdex_score = 0.92  # Default
    total_tokens = 0
    total_calls = 0

    if prometheus_client.is_enabled:
        try:
            # APDEX from recording rule
            apdex_result = await prometheus_client.query(
                "slo:apdex:platform_score or vector(0.92)"
            )
            apdex_score = _extract_scalar(apdex_result, 0.92)

            # Total tokens
            tokens_result = await prometheus_client.query(
                "sum(stoa_mcp_gateway_tokens_total) or vector(0)"
            )
            total_tokens = int(_extract_scalar(tokens_result, 0))

            # Total calls
            calls_result = await prometheus_client.query(
                "sum(stoa_mcp_gateway_http_requests_total) or vector(0)"
            )
            total_calls = int(_extract_scalar(calls_result, 0))

        except Exception as e:
            logger.warning(f"Prometheus query failed: {e}")

    return BusinessMetrics(
        active_tenants=active_tenants,
        new_tenants_30d=new_tenants,
        tenant_growth=tenant_growth,
        apdex_score=round(apdex_score, 3),
        total_tokens=total_tokens,
        total_calls=total_calls,
    )


@router.get("/top-apis", response_model=list[TopAPI])
async def get_top_apis(
    limit: int = Query(default=10, ge=1, le=50, description="Number of top APIs"),
    current_user: User = Depends(require_role(["cpi-admin", "admin"])),
) -> list[TopAPI]:
    """
    Get top APIs/tools by usage.

    Requires cpi-admin or admin role.

    Returns top N tools by invocation count over the last 30 days.
    """
    logger.info(f"Fetching top {limit} APIs for user={current_user.id}")

    if not prometheus_client.is_enabled:
        logger.warning("Prometheus not available")
        return []

    try:
        # Query top tools by invocation count
        result = await prometheus_client.query(
            f"""
            topk({limit},
              sum by (tool_name) (
                increase(stoa_mcp_gateway_mcp_tool_invocations_total[30d])
              )
            )
            """.strip().replace("\n", " ").replace("  ", " ")
        )

        if not result:
            return []

        apis = []
        for item in result.get("result", []):
            metric = item.get("metric", {})
            tool_name = metric.get("tool_name", "unknown")
            raw_value = float(item.get("value", [0, 0])[1])

            # Skip NaN values
            if raw_value != raw_value:
                continue

            apis.append(
                TopAPI(
                    tool_name=tool_name,
                    display_name=_humanize_tool_name(tool_name),
                    calls=int(raw_value),
                )
            )

        # Sort by calls descending (topk should already do this, but ensure order)
        apis.sort(key=lambda x: x.calls, reverse=True)
        return apis[:limit]

    except Exception as e:
        logger.error(f"Failed to fetch top APIs: {e}")
        return []
