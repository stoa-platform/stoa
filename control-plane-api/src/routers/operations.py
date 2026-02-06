"""
Operations Dashboard API Router - CAB-Observability

Endpoints for the Operations Dashboard (Console UI).
Provides real-time platform health metrics from Prometheus.

Routes:
- GET /v1/operations/metrics - Platform operations metrics
"""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import User
from ..auth.rbac import require_role
from ..services.prometheus_client import prometheus_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/operations", tags=["Operations"])


class OperationsMetrics(BaseModel):
    """Operations dashboard metrics response."""

    error_rate: float  # percentage (e.g., 0.02 = 0.02%)
    p95_latency_ms: float  # milliseconds
    requests_per_minute: float  # RPS * 60
    active_alerts: int  # Alertmanager firing count
    uptime: float  # percentage (e.g., 99.95)


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


@router.get("/metrics", response_model=OperationsMetrics)
async def get_operations_metrics(
    current_user: User = Depends(require_role(["cpi-admin", "devops", "admin"])),
) -> OperationsMetrics:
    """
    Get real-time operations metrics from Prometheus.

    Requires admin, cpi-admin, or devops role.

    Returns platform-wide metrics:
    - error_rate: 5-minute error rate percentage
    - p95_latency_ms: 95th percentile latency
    - requests_per_minute: Current request rate
    - active_alerts: Number of firing alerts
    - uptime: Platform availability percentage
    """
    logger.info(f"Fetching operations metrics for user={current_user.id}")

    if not prometheus_client.is_enabled:
        logger.warning("Prometheus not available, returning defaults")
        return OperationsMetrics(
            error_rate=0.0,
            p95_latency_ms=0.0,
            requests_per_minute=0.0,
            active_alerts=0,
            uptime=100.0,
        )

    try:
        # Use recording rules for efficient queries (deployed with stoa-slo.yaml)
        # These recording rules are pre-computed by Prometheus
        error_rate_result = await prometheus_client.query(
            "slo:error_rate:5m or vector(0)"
        )
        p95_result = await prometheus_client.query(
            "slo:latency_p95:5m or vector(0)"
        )
        rps_result = await prometheus_client.query(
            "slo:requests_per_minute or vector(0)"
        )
        uptime_result = await prometheus_client.query(
            "slo:availability:5m or vector(1)"
        )

        # Query Alertmanager for active alerts count
        alerts_result = await prometheus_client.query(
            'count(ALERTS{alertstate="firing"}) or vector(0)'
        )

        # Extract values with defaults
        error_rate = _extract_scalar(error_rate_result, 0.0) * 100  # Convert to percentage
        p95_latency = _extract_scalar(p95_result, 0.0) * 1000  # Convert to ms
        rps = _extract_scalar(rps_result, 0.0)
        uptime = _extract_scalar(uptime_result, 1.0) * 100  # Convert to percentage
        alerts = int(_extract_scalar(alerts_result, 0.0))

        return OperationsMetrics(
            error_rate=round(error_rate, 3),
            p95_latency_ms=round(p95_latency, 1),
            requests_per_minute=round(rps, 1),
            active_alerts=alerts,
            uptime=round(uptime, 3),
        )

    except Exception as e:
        logger.error(f"Failed to fetch operations metrics: {e}")
        # Return defaults on error (graceful degradation)
        return OperationsMetrics(
            error_rate=0.0,
            p95_latency_ms=0.0,
            requests_per_minute=0.0,
            active_alerts=0,
            uptime=100.0,
        )
