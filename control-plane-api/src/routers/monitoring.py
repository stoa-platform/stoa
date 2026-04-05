"""API Monitoring endpoints for transaction tracking and analytics (CAB-1984).

Data sources (priority order):
1. OpenSearch (full-text search, aggregations)
2. Tempo (distributed traces from gateway OTLP)
3. Empty response (no mock fallback)
"""

import logging

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth import User, get_current_user
from ..config import settings
from ..schemas.monitoring import (
    APITransaction,
    APITransactionStats,
)
from ..services import tempo_service
from ..services.monitoring_service import MonitoringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/monitoring", tags=["Monitoring"])


# =============================================================================
# OPENSEARCH SERVICE DEPENDENCY
# =============================================================================


def _get_monitoring_service() -> MonitoringService | None:
    """Return a MonitoringService if OpenSearch is available, else None."""
    try:
        from ..opensearch.opensearch_integration import OpenSearchService

        instance = OpenSearchService.get_instance()
        if instance and instance.client:
            return MonitoringService(instance.client)
    except Exception:
        logger.debug("OpenSearch not available")
    return None


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class TransactionListResponse(BaseModel):
    """Transaction list with data source indicator."""

    transactions: list[dict] = []
    total: int = 0
    demo_mode: bool = False
    source: str = "none"  # opensearch, tempo, none
    next_cursor: str | None = None


class TransactionStatsWithDemoResponse(APITransactionStats):
    """Transaction stats with data source indicator."""

    demo_mode: bool = False
    source: str = "none"


class TransactionDetailWithDemoResponse(APITransaction):
    """Transaction detail with data source indicator."""

    demo_mode: bool = False
    source: str = "none"


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    limit: int = Query(50, ge=1, le=200),
    api_name: str | None = None,
    status: str | None = None,
    time_range: int = Query(60, ge=1, le=1440),
    cursor: str | None = Query(None, description="Pagination cursor from previous response"),
    user: User = Depends(get_current_user),
):
    """List recent API transactions.

    Returns transaction summaries from OpenSearch or Tempo.
    Falls back to empty list when no data source is available.
    """
    tenant_id = user.tenant_id

    # Source 1: OpenSearch
    svc = _get_monitoring_service()
    if svc:
        result = await svc.list_transactions(
            tenant_id=tenant_id,
            limit=limit,
            api_name=api_name,
            status=status,
            time_range_minutes=time_range,
        )
        if result is not None:
            return TransactionListResponse(
                transactions=[t.model_dump() for t in result],
                total=len(result),
                demo_mode=False,
                source="opensearch",
            )

    # Source 2: Tempo
    tempo_result = await tempo_service.search_traces(
        limit=limit,
        api_name=api_name,
        status=status,
        time_range_minutes=time_range,
        cursor=cursor,
    )
    if tempo_result is not None:
        traces, next_cursor = tempo_result
        return TransactionListResponse(
            transactions=[t.model_dump() for t in traces],
            total=len(traces),
            demo_mode=False,
            source="tempo",
            next_cursor=next_cursor,
        )

    # No data source available — return empty
    return TransactionListResponse(
        transactions=[],
        total=0,
        demo_mode=False,
        source="none",
    )


@router.get("/transactions/stats", response_model=TransactionStatsWithDemoResponse)
async def get_transaction_stats(
    time_range: int = Query(60, ge=1, le=1440),
    user: User = Depends(get_current_user),
):
    """Get API transaction statistics.

    Returns aggregated metrics from OpenSearch.
    Tempo does not support aggregation — returns zeroed stats with source indicator.
    """
    tenant_id = user.tenant_id

    # Source 1: OpenSearch (only source that supports aggregation)
    svc = _get_monitoring_service()
    if svc:
        result = await svc.get_transaction_stats(tenant_id=tenant_id, time_range_minutes=time_range)
        if result is not None:
            return TransactionStatsWithDemoResponse(
                **result.model_dump(),
                demo_mode=False,
                source="opensearch",
            )

    # No aggregation source — return zeroed stats
    return TransactionStatsWithDemoResponse(
        total_requests=0,
        success_count=0,
        error_count=0,
        timeout_count=0,
        avg_latency_ms=0,
        p95_latency_ms=0,
        p99_latency_ms=0,
        requests_per_minute=0,
        by_api={},
        by_status_code={},
        demo_mode=False,
        source="none",
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionDetailWithDemoResponse)
async def get_transaction(
    transaction_id: str,
    user: User = Depends(get_current_user),
):
    """Get detailed information about a specific transaction.

    Includes all spans with timing and metadata.
    Checks OpenSearch first, then Tempo for trace detail.
    """
    tenant_id = user.tenant_id

    # Source 1: OpenSearch
    svc = _get_monitoring_service()
    if svc:
        result = await svc.get_transaction(event_id=transaction_id, tenant_id=tenant_id)
        if result is not None:
            return TransactionDetailWithDemoResponse(
                **result.model_dump(),
                demo_mode=False,
                source="opensearch",
            )

    # Source 2: Tempo (trace_id lookup)
    trace = await tempo_service.get_trace(transaction_id)
    if trace is not None:
        return TransactionDetailWithDemoResponse(
            **trace.model_dump(),
            demo_mode=False,
            source="tempo",
        )

    # Not found in any source — return minimal empty response
    return TransactionDetailWithDemoResponse(
        id=transaction_id,
        trace_id=transaction_id,
        api_name="unknown",
        method="GET",
        path="",
        status_code=0,
        status="unknown",
        started_at="",
        total_duration_ms=0,
        spans=[],
        demo_mode=False,
        source="none",
    )


@router.get("/kernel-metrics")
async def get_kernel_metrics(
    user: User = Depends(get_current_user),
) -> dict:
    """Proxy kernel metrics from the gateway (CAB-1976)."""
    gateway_url = settings.MCP_GATEWAY_URL
    if not gateway_url:
        return {"source": "unavailable", "error": "MCP_GATEWAY_URL not configured"}
    try:
        headers = {}
        admin_token = getattr(settings, "STOA_ADMIN_API_TOKEN", "")
        if admin_token:
            headers["Authorization"] = f"Bearer {admin_token}"
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{gateway_url}/admin/kernel-metrics", headers=headers)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("kernel-metrics gateway call failed: %s", e)
        return {
            "source": "unavailable",
            "process": {},
            "network": {},
            "dns_tls": {},
            "upstream_pod": {"available": False, "note": str(e)},
        }
