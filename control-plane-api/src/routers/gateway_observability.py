"""API routes for gateway observability and metrics.

IMPORTANT: This router uses prefix /v1/admin/gateways (same as gateway_instances).
Static paths like /metrics and /health-summary MUST be registered BEFORE the
gateway_instances router to avoid FastAPI treating them as /{gateway_id} UUID params.

Phase 2 (CAB-1635): per-tenant filtering, adapter operation metrics, health history.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import require_role
from src.database import get_db
from src.services.gateway_metrics_service import GatewayMetricsService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/admin/gateways",
    tags=["Gateway Observability"],
)


def _tenant_filter(user) -> str | None:
    """Return tenant_id for filtering: None for cpi-admin (sees all), user's tenant otherwise."""
    if "cpi-admin" in user.roles:
        return None
    return user.tenant_id


@router.get("/metrics")
async def get_aggregated_metrics(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Aggregated metrics across all gateways (health + sync).

    cpi-admin sees all gateways; tenant-admin sees only own tenant's gateways.
    """
    svc = GatewayMetricsService(db)
    return await svc.get_aggregated_metrics(tenant_id=_tenant_filter(user))


@router.get("/metrics/guardrails/events")
async def get_guardrails_events(
    limit: int = 50,
    time_range_minutes: int = 60,
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Recent guardrails events (blocked, redacted, flagged) from OpenSearch spans.

    Returns per-event: timestamp, tool, action, reason, trace_id.
    """
    from src.opensearch.opensearch_integration import get_opensearch_client

    client = await get_opensearch_client()
    if not client:
        return {"events": [], "total": 0}

    try:
        body = {
            "query": {
                "bool": {
                    "filter": [
                        {"range": {"startTime": {"gte": f"now-{time_range_minutes}m"}}},
                        {"term": {"name": "policy.guardrails"}},
                        {"exists": {"field": "span.attributes.guardrails@action"}},
                    ],
                    "must_not": [
                        {"term": {"span.attributes.guardrails@action": "pass"}},
                    ],
                }
            },
            "sort": [{"startTime": {"order": "desc"}}],
            "size": limit,
            "_source": [
                "startTime",
                "traceId",
                "spanId",
                "span.attributes.guardrails@tool",
                "span.attributes.guardrails@action",
                "span.attributes.guardrails@reason",
            ],
        }
        resp = await client.search(index="otel-v1-apm-span-*", body=body)
        hits = resp.get("hits", {}).get("hits", [])
        events = []
        for hit in hits:
            src = hit["_source"]
            events.append({
                "timestamp": src.get("startTime", ""),
                "trace_id": src.get("traceId", ""),
                "span_id": src.get("spanId", ""),
                "tool": src.get("span.attributes.guardrails@tool", "unknown"),
                "action": src.get("span.attributes.guardrails@action", "unknown"),
                "reason": src.get("span.attributes.guardrails@reason", ""),
            })
        return {"events": events, "total": len(events)}
    except Exception:
        logger.exception("Failed to fetch guardrails events")
        return {"events": [], "total": 0}


@router.get("/health-summary")
async def get_health_summary(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Gateway health status counts.

    cpi-admin sees all gateways; tenant-admin sees only own tenant's gateways.
    """
    svc = GatewayMetricsService(db)
    return await svc.get_health_summary(tenant_id=_tenant_filter(user))


@router.get("/metrics/operations")
async def get_adapter_operation_metrics(
    user=Depends(require_role(["cpi-admin"])),
):
    """Adapter operation metrics from in-process Prometheus registry.

    Returns per-gateway-type: total_ops, success_rate, avg_latency_ms.
    cpi-admin only (process-wide metrics, not tenant-scoped).
    """
    svc = GatewayMetricsService(db=None)  # type: ignore[arg-type]
    return svc.get_adapter_operation_metrics()


@router.get("/{gateway_id}/health-history")
async def get_health_history(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Health check details for a specific gateway.

    Returns current status, last check time, and health_details (check_method,
    consecutive_failures, last_error, etc.).
    """
    svc = GatewayMetricsService(db)
    result = await svc.get_health_history(gateway_id, tenant_id=_tenant_filter(user))
    if not result:
        raise HTTPException(status_code=404, detail="Gateway instance not found")
    return result


@router.get("/{gateway_id}/metrics")
async def get_gateway_metrics(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Per-gateway detailed metrics.

    cpi-admin sees any gateway; tenant-admin only sees own tenant's gateways.
    """
    svc = GatewayMetricsService(db)
    result = await svc.get_gateway_metrics(gateway_id, tenant_id=_tenant_filter(user))
    if not result:
        raise HTTPException(status_code=404, detail="Gateway instance not found")
    return result
