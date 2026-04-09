"""API Monitoring endpoints for transaction tracking and analytics (CAB-1984, CAB-1997).

Data sources (priority order):
1. OpenSearch otel-v1-apm-span-* (OTLP traces via Data Prepper — CAB-1997)
2. Tempo (distributed traces — fallback)
3. Empty response (no data source available)
"""

import logging

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


def _tenant_filter(user: User) -> str | None:
    """Extract tenant_id for filtering. cpi-admin sees all (None)."""
    if "cpi-admin" in user.roles:
        return None
    return user.tenant_id


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
    route: str | None = Query(None, description="Filter by route path (e.g. /mcp/tools/call)"),
    status: str | None = None,
    status_code: int | None = Query(None, description="Filter by exact HTTP status code (e.g. 401, 404, 500)"),
    service_type: str | None = Query(None, description="Filter: gateway, link, connect"),
    time_range: int = Query(60, ge=1, le=10080),
    cursor: str | None = Query(None, description="Pagination cursor from previous response"),
    user: User = Depends(get_current_user),
):
    """List recent API transactions.

    Returns transaction summaries from OpenSearch or Tempo.
    Falls back to empty list when no data source is available.
    """
    svc = _get_monitoring_service()
    tenant_id = _tenant_filter(user)

    # Source 1: OpenSearch otel-v1-apm-span-* (Data Prepper OTLP — CAB-1997)
    if svc and settings.OPENSEARCH_TRACES_ENABLED:
        result = await svc.list_transactions_from_spans(
            limit=limit,
            api_name=api_name,
            route=route,
            status=status,
            status_code=status_code,
            time_range_minutes=time_range,
            service_type=service_type,
            tenant_id=tenant_id,
        )
        if result is not None:
            return TransactionListResponse(
                transactions=[t.model_dump() for t in result],
                total=len(result),
                demo_mode=False,
                source="opensearch",
            )

    # Source 2: Tempo (fallback)
    tempo_result = await tempo_service.search_traces(
        limit=limit,
        api_name=api_name,
        status=status,
        time_range_minutes=time_range,
        cursor=cursor,
        tenant_id=tenant_id,
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
    time_range: int = Query(60, ge=1, le=10080),
    user: User = Depends(get_current_user),
):
    """Get API transaction statistics.

    Returns aggregated metrics from OpenSearch.
    Tempo does not support aggregation — returns zeroed stats with source indicator.
    """
    tenant_id = _tenant_filter(user)
    svc = _get_monitoring_service()

    # Source 1: OpenSearch otel-v1-apm-span-* (CAB-1997)
    if svc and settings.OPENSEARCH_TRACES_ENABLED:
        result = await svc.get_transaction_stats_from_spans(
            time_range_minutes=time_range,
            tenant_id=tenant_id,
        )
        if result is not None:
            return TransactionStatsWithDemoResponse(
                **result.model_dump(),
                demo_mode=False,
                source="opensearch",
            )

    # Source 2: OpenSearch audit-* (legacy)
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
    svc = _get_monitoring_service()
    tenant_id = _tenant_filter(user)

    # Source 1: OpenSearch otel-v1-apm-span-* (Data Prepper OTLP — CAB-1997)
    if svc and settings.OPENSEARCH_TRACES_ENABLED:
        result = await svc.get_transaction_from_spans(trace_id=transaction_id, tenant_id=tenant_id)
        if result is not None:
            return TransactionDetailWithDemoResponse(
                **result.model_dump(),
                demo_mode=False,
                source="opensearch",
            )

    # Source 2: Tempo (fallback — trace_id lookup)
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
