"""API Monitoring endpoints for transaction tracking and analytics."""

import logging
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth import User, get_current_user
from ..schemas.monitoring import (
    APITransaction,
    APITransactionStats,
    APITransactionSummary,
    TransactionSpan,
)
from ..services.monitoring_service import MonitoringService, _error_source, _status_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/monitoring", tags=["Monitoring"])

# In-memory cache for demo transactions so detail is coherent with list
_demo_cache: dict[str, APITransactionSummary] = {}


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
        logger.debug("OpenSearch not available, will use demo data")
    return None


# =============================================================================
# DEMO DATA GENERATORS (fallback when OpenSearch is unavailable)
# =============================================================================


def generate_demo_transactions(count: int = 50, tenant_id: str | None = None) -> list[APITransactionSummary]:
    """Generate realistic demo transaction data."""
    apis = [
        {"name": "customer-api", "paths": ["/customers", "/customers/{id}", "/customers/{id}/orders"]},
        {"name": "order-api", "paths": ["/orders", "/orders/{id}", "/orders/{id}/status"]},
        {"name": "inventory-api", "paths": ["/products", "/products/{id}", "/stock/{id}"]},
        {"name": "payment-api", "paths": ["/payments", "/payments/{id}", "/refunds"]},
        {"name": "artifact-search", "paths": ["/search", "/artifacts/{id}", "/sectors"]},
        {"name": "scoreboard-tracker", "paths": ["/rankings", "/scores", "/gunters"]},
    ]

    methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    method_weights = [60, 20, 10, 5, 5]  # GET is most common

    status_configs = [
        (200, "success", 70),
        (201, "success", 10),
        (204, "success", 5),
        (400, "error", 5),
        (401, "error", 3),
        (404, "error", 4),
        (500, "error", 2),
        (504, "timeout", 1),
    ]

    transactions = []
    base_time = datetime.utcnow()

    for i in range(count):
        api = random.choice(apis)
        method = random.choices(methods, weights=method_weights)[0]

        # Select status based on weights
        status_choice = random.choices(status_configs, weights=[s[2] for s in status_configs])[0]
        status_code, status, _ = status_choice

        # Random time within last hour
        time_offset = timedelta(minutes=random.randint(0, 60))
        started_at = base_time - time_offset

        # Latency varies by status
        if status == "success":
            latency = random.randint(15, 300)
        elif status == "timeout":
            latency = random.randint(5000, 30000)
        else:
            latency = random.randint(50, 500)

        tx_id = f"tx-{i:06d}-{random.randint(1000, 9999)}"
        trace_id = f"trace-{random.randint(100000, 999999)}"

        path = random.choice(api["paths"])
        full_path = f"/v1/{api['name']}{path}"
        transactions.append(
            APITransactionSummary(
                id=tx_id,
                trace_id=trace_id,
                api_name=api["name"],
                method=method,
                path=full_path,
                status_code=status_code,
                status=status,
                status_text=_status_text(status_code),
                error_source=_error_source(full_path, status_code),
                started_at=started_at.isoformat() + "Z",
                total_duration_ms=latency,
                spans_count=random.randint(3, 8),
            )
        )

    # Sort by time, most recent first
    transactions.sort(key=lambda x: x.started_at, reverse=True)

    # Cache for coherent detail lookups
    _demo_cache.clear()
    for t in transactions:
        _demo_cache[t.id] = t

    return transactions


def _error_span_name(status_code: int) -> str:
    """Determine which span should show the error based on status code."""
    if status_code == 401:
        return "auth_validation"
    if status_code == 403:
        return "auth_validation"
    if status_code == 429:
        return "rate_limiting"
    if status_code in (502, 503, 504):
        return "gateway_ingress"
    # 400, 404, 500, 501, etc. → backend
    return "backend_call"


def generate_transaction_detail(tx_id: str, tenant_id: str = "demo") -> APITransaction:
    """Generate detailed transaction data, coherent with the list cache."""
    # Use cached summary if available (same process, same demo session)
    cached = _demo_cache.get(tx_id)

    if cached:
        api_name = cached.api_name
        status_code = cached.status_code
        status = cached.status
        method = cached.method
        path = cached.path
        started_at = cached.started_at
        total_hint = cached.total_duration_ms
    else:
        apis = ["customer-api", "order-api", "inventory-api", "payment-api"]
        api_name = random.choice(apis)
        status_code = 200
        status = "success"
        method = random.choice(["GET", "POST", "PUT"])
        path = f"/v1/{api_name}/{api_name.replace('-api', '')}s/12345"
        started_at = (datetime.utcnow() - timedelta(minutes=random.randint(1, 30))).isoformat() + "Z"
        total_hint = 0

    is_error = status_code >= 400
    error_at = _error_span_name(status_code) if is_error else ""

    # Generate spans — error span stops the chain (later spans skipped)
    spans = []
    current_offset = 0
    span_configs = [
        ("gateway_ingress", "api-gateway", 5, 20),
        ("auth_validation", "auth-service", 10, 50),
        ("rate_limiting", "rate-limiter", 2, 10),
        ("backend_call", api_name, 50, 200),
        ("database_query", "postgres", 20, 100),
        ("response_transform", "api-gateway", 5, 15),
    ]

    for name, service, min_ms, max_ms in span_configs:
        duration = random.randint(min_ms, max_ms)
        if name == error_at:
            # This span failed — mark error, chain stops here
            spans.append(
                TransactionSpan(
                    name=name,
                    service=service,
                    start_offset_ms=current_offset,
                    duration_ms=duration,
                    status="error",
                    metadata={"status_code": status_code, "error": _status_text(status_code)},
                )
            )
            current_offset += duration
            break
        else:
            spans.append(
                TransactionSpan(
                    name=name,
                    service=service,
                    start_offset_ms=current_offset,
                    duration_ms=duration,
                    status="success",
                    metadata={"processed": True},
                )
            )
            current_offset += duration

    total_duration = total_hint if total_hint else current_offset

    return APITransaction(
        id=tx_id,
        trace_id=cached.trace_id if cached else f"trace-{random.randint(100000, 999999)}",
        api_name=api_name,
        tenant_id=tenant_id,
        method=method,
        path=path,
        status_code=status_code,
        status=status,
        status_text=_status_text(status_code),
        error_source=_error_source(path, status_code),
        client_ip=f"10.0.{random.randint(1, 255)}.{random.randint(1, 255)}",
        user_id=f"user-{random.randint(1000, 9999)}",
        started_at=started_at,
        total_duration_ms=total_duration,
        spans=spans,
        request_headers={"Content-Type": "application/json", "Authorization": "Bearer ***"},
        response_headers={"Content-Type": "application/json"},
        error_message=_status_text(status_code) if is_error else None,
    )


def generate_stats() -> APITransactionStats:
    """Generate realistic monitoring statistics."""
    total = random.randint(5000, 15000)
    error_rate = random.uniform(0.01, 0.05)
    timeout_rate = random.uniform(0.001, 0.01)

    errors = int(total * error_rate)
    timeouts = int(total * timeout_rate)
    successes = total - errors - timeouts

    apis = ["customer-api", "order-api", "inventory-api", "payment-api", "artifact-search", "scoreboard-tracker"]
    by_api = {}
    for api in apis:
        api_total = random.randint(500, 3000)
        api_errors = int(api_total * random.uniform(0.01, 0.08))
        by_api[api] = {
            "total": api_total,
            "success": api_total - api_errors,
            "errors": api_errors,
            "avg_latency_ms": random.randint(30, 150),
        }

    return APITransactionStats(
        total_requests=total,
        success_count=successes,
        error_count=errors,
        timeout_count=timeouts,
        avg_latency_ms=random.uniform(45, 120),
        p95_latency_ms=random.uniform(200, 400),
        p99_latency_ms=random.uniform(500, 1000),
        requests_per_minute=random.uniform(50, 200),
        by_api=by_api,
        by_status_code={
            200: int(successes * 0.8),
            201: int(successes * 0.15),
            204: int(successes * 0.05),
            400: int(errors * 0.3),
            401: int(errors * 0.2),
            404: int(errors * 0.3),
            500: int(errors * 0.15),
            504: timeouts,
        },
    )


class TransactionListResponse(BaseModel):
    """Transaction list with demo mode indicator."""

    transactions: list[dict] = []
    total: int = 0
    demo_mode: bool = False


class TransactionStatsWithDemoResponse(APITransactionStats):
    """Transaction stats with demo mode indicator."""

    demo_mode: bool = False


class TransactionDetailWithDemoResponse(APITransaction):
    """Transaction detail with demo mode indicator."""

    demo_mode: bool = False


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    limit: int = Query(50, ge=1, le=200),
    api_name: str | None = None,
    status: str | None = None,
    time_range: int = Query(60, ge=1, le=1440),
    user: User = Depends(get_current_user),
):
    """
    List recent API transactions.

    Returns transaction summaries for efficient list display.
    Uses real OpenSearch data when available, falls back to demo data.
    """
    tenant_id = user.tenant_id

    # Try real data from OpenSearch
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
            return {
                "transactions": [t.model_dump() for t in result],
                "total": len(result),
                "demo_mode": False,
            }

    # Fallback to demo data
    transactions = generate_demo_transactions(limit, tenant_id)
    if api_name:
        transactions = [t for t in transactions if t.api_name == api_name]
    if status:
        transactions = [t for t in transactions if t.status == status]

    return {
        "transactions": [t.model_dump() for t in transactions],
        "total": len(transactions),
        "demo_mode": True,
    }


@router.get("/transactions/stats", response_model=TransactionStatsWithDemoResponse)
async def get_transaction_stats(
    time_range: int = Query(60, ge=1, le=1440),
    user: User = Depends(get_current_user),
):
    """
    Get API transaction statistics.

    Returns aggregated metrics about API calls.
    Uses real OpenSearch data when available, falls back to demo data.
    """
    tenant_id = user.tenant_id

    # Try real data from OpenSearch
    svc = _get_monitoring_service()
    if svc:
        result = await svc.get_transaction_stats(tenant_id=tenant_id, time_range_minutes=time_range)
        if result is not None:
            return {**result.model_dump(), "demo_mode": False}

    # Fallback to demo data
    return {**generate_stats().model_dump(), "demo_mode": True}


@router.get("/transactions/{transaction_id}", response_model=TransactionDetailWithDemoResponse)
async def get_transaction(
    transaction_id: str,
    user: User = Depends(get_current_user),
):
    """
    Get detailed information about a specific transaction.

    Includes all spans with timing and metadata.
    Uses real OpenSearch data when available, falls back to demo data.
    """
    tenant_id = user.tenant_id

    # Try real data from OpenSearch
    svc = _get_monitoring_service()
    if svc:
        result = await svc.get_transaction(event_id=transaction_id, tenant_id=tenant_id)
        if result is not None:
            return {**result.model_dump(), "demo_mode": False}

    # Fallback to demo data
    transaction = generate_transaction_detail(transaction_id, tenant_id)
    return {**transaction.model_dump(), "demo_mode": True}
