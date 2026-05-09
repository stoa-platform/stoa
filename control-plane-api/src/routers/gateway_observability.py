"""API routes for gateway observability and metrics.

IMPORTANT: This router uses prefix /v1/admin/gateways (same as gateway_instances).
Static paths like /metrics and /health-summary MUST be registered BEFORE the
gateway_instances router to avoid FastAPI treating them as /{gateway_id} UUID params.

Phase 2 (CAB-1635): per-tenant filtering, adapter operation metrics, health history.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import require_role
from src.database import get_db
from src.services.gateway_metrics_service import GatewayMetricsService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/admin/gateways",
    tags=["Gateway Observability"],
)

GuardrailsConfigSource = Literal["env", "runtime", "config-service"]
TimeRange = Literal["1h", "6h", "24h", "7d"]


class GuardrailsConfigResponse(BaseModel):
    """Effective guardrails runtime/config state per PR-3A contract."""

    pii_enabled: bool
    injection_detection_enabled: bool
    prompt_guard_enabled: bool
    content_filter_enabled: bool
    rate_limit_enabled: bool
    opa_policy_enabled: bool
    source: GuardrailsConfigSource
    updated_at: datetime


def _tenant_filter(user) -> str | None:
    """Return tenant_id for filtering: None for cpi-admin (sees all), user's tenant otherwise."""
    if "cpi-admin" in user.roles:
        return None
    return cast(str | None, user.tenant_id)


def _read_bool_env(name: str) -> bool:
    """Read a required boolean env value without guessing absent runtime state."""
    raw = os.environ.get(name)
    if raw is None:
        raise HTTPException(status_code=503, detail=f"Guardrails config env missing: {name}")

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False

    raise HTTPException(status_code=503, detail=f"Guardrails config env invalid: {name}")


def _read_rate_limit_enabled() -> bool:
    """Read rate-limit enablement from explicit bool or numeric gateway default."""
    if os.environ.get("STOA_RATE_LIMIT_ENABLED") is not None:
        return _read_bool_env("STOA_RATE_LIMIT_ENABLED")

    raw = os.environ.get("STOA_RATE_LIMIT_DEFAULT")
    if raw is None:
        raise HTTPException(status_code=503, detail="Guardrails config env missing: STOA_RATE_LIMIT_DEFAULT")

    try:
        return int(raw.strip()) > 0
    except ValueError:
        raise HTTPException(status_code=503, detail="Guardrails config env invalid: STOA_RATE_LIMIT_DEFAULT")


def _guardrails_config_from_env() -> GuardrailsConfigResponse:
    """Build the config response from gateway/control-plane visible env."""
    return GuardrailsConfigResponse(
        pii_enabled=_read_bool_env("STOA_GUARDRAILS_PII_ENABLED"),
        injection_detection_enabled=_read_bool_env("STOA_GUARDRAILS_INJECTION_ENABLED"),
        prompt_guard_enabled=_read_bool_env("STOA_PROMPT_GUARD_ENABLED"),
        content_filter_enabled=_read_bool_env("STOA_GUARDRAILS_CONTENT_FILTER_ENABLED"),
        rate_limit_enabled=_read_rate_limit_enabled(),
        opa_policy_enabled=_read_bool_env("STOA_POLICY_ENABLED"),
        source="env",
        updated_at=datetime.now(UTC),
    )


@router.get("/guardrails/config", response_model=GuardrailsConfigResponse)
async def get_guardrails_config(
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
) -> GuardrailsConfigResponse:
    """Effective Guardrails config state for /observability/security."""
    return _guardrails_config_from_env()


@router.get("/metrics")
async def get_aggregated_metrics(
    time_range: TimeRange = Query("1h", alias="range"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Aggregated metrics across all gateways (health + sync).

    cpi-admin sees all gateways; tenant-admin sees only own tenant's gateways.
    """
    svc = GatewayMetricsService(db)
    return await svc.get_aggregated_metrics(tenant_id=_tenant_filter(user), time_range=time_range)


@router.get("/metrics/guardrails/events")
async def get_guardrails_events(
    limit: int = 50,
    time_range: TimeRange = Query("1h", alias="range"),
    time_range_minutes: int | None = None,
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Recent guardrails events (blocked, redacted, flagged) from OpenSearch spans.

    Returns per-event: timestamp, tool, action, reason, trace_id.
    """
    from src.opensearch.opensearch_integration import get_opensearch_client

    client = await get_opensearch_client()
    if not client:
        return {"events": [], "total": 0}

    tenant_id = _tenant_filter(user)
    range_minutes = {"1h": 60, "6h": 360, "24h": 1440, "7d": 10080}[time_range]

    try:
        filters: list[dict] = [
            {"range": {"startTime": {"gte": f"now-{time_range_minutes if time_range_minutes is not None else range_minutes}m"}}},
            {"term": {"name": "policy.guardrails"}},
            {"exists": {"field": "span.attributes.guardrails@action"}},
        ]
        # CAB-2031: tenant-admin sees only own tenant's guardrails events
        if tenant_id:
            filters.append({"term": {"resource.attributes.tenant@id": tenant_id}})

        body = {
            "query": {
                "bool": {
                    "filter": filters,
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
            events.append(
                {
                    "timestamp": src.get("startTime", ""),
                    "trace_id": src.get("traceId", ""),
                    "span_id": src.get("spanId", ""),
                    "tool": src.get("span.attributes.guardrails@tool", "unknown"),
                    "action": src.get("span.attributes.guardrails@action", "unknown"),
                    "reason": src.get("span.attributes.guardrails@reason", ""),
                }
            )
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
    svc = GatewayMetricsService(db=None)
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
