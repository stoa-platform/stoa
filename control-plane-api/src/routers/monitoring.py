# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""API Monitoring endpoints for transaction tracking and analytics."""
import random
import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel

from ..auth import get_current_user, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/monitoring", tags=["Monitoring"])


# =============================================================================
# MODELS
# =============================================================================

class TransactionSpan(BaseModel):
    name: str
    service: str
    start_offset_ms: int
    duration_ms: int
    status: str  # success, error
    metadata: dict = {}


class APITransactionSummary(BaseModel):
    id: str
    trace_id: str
    api_name: str
    method: str
    path: str
    status_code: int
    status: str  # success, error, timeout, pending
    started_at: str
    total_duration_ms: int
    spans_count: int


class APITransaction(BaseModel):
    id: str
    trace_id: str
    api_name: str
    tenant_id: str
    method: str
    path: str
    status_code: int
    status: str
    client_ip: Optional[str] = None
    user_id: Optional[str] = None
    started_at: str
    total_duration_ms: int
    spans: List[TransactionSpan]
    request_headers: Optional[dict] = None
    response_headers: Optional[dict] = None
    error_message: Optional[str] = None


class APITransactionStats(BaseModel):
    total_requests: int
    success_count: int
    error_count: int
    timeout_count: int
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    requests_per_minute: float
    by_api: dict
    by_status_code: dict


# =============================================================================
# DEMO DATA GENERATOR
# =============================================================================

def generate_demo_transactions(count: int = 50, tenant_id: Optional[str] = None) -> List[APITransactionSummary]:
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
        status_choice = random.choices(
            status_configs,
            weights=[s[2] for s in status_configs]
        )[0]
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

        transactions.append(APITransactionSummary(
            id=tx_id,
            trace_id=trace_id,
            api_name=api["name"],
            method=method,
            path=random.choice(api["paths"]),
            status_code=status_code,
            status=status,
            started_at=started_at.isoformat() + "Z",
            total_duration_ms=latency,
            spans_count=random.randint(3, 8),
        ))

    # Sort by time, most recent first
    transactions.sort(key=lambda x: x.started_at, reverse=True)
    return transactions


def generate_transaction_detail(tx_id: str, tenant_id: str = "demo") -> APITransaction:
    """Generate detailed transaction data."""
    apis = ["customer-api", "order-api", "inventory-api", "payment-api"]
    api_name = random.choice(apis)

    base_time = datetime.utcnow() - timedelta(minutes=random.randint(1, 30))
    is_error = random.random() < 0.1

    # Generate spans for the transaction
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
        span_status = "error" if is_error and name == "backend_call" else "success"

        spans.append(TransactionSpan(
            name=name,
            service=service,
            start_offset_ms=current_offset,
            duration_ms=duration,
            status=span_status,
            metadata={"processed": True}
        ))
        current_offset += duration

    total_duration = current_offset
    status_code = 500 if is_error else 200
    status = "error" if is_error else "success"

    return APITransaction(
        id=tx_id,
        trace_id=f"trace-{random.randint(100000, 999999)}",
        api_name=api_name,
        tenant_id=tenant_id,
        method=random.choice(["GET", "POST", "PUT"]),
        path=f"/{api_name.replace('-api', '')}s/12345",
        status_code=status_code,
        status=status,
        client_ip=f"10.0.{random.randint(1, 255)}.{random.randint(1, 255)}",
        user_id=f"user-{random.randint(1000, 9999)}",
        started_at=base_time.isoformat() + "Z",
        total_duration_ms=total_duration,
        spans=spans,
        request_headers={"Content-Type": "application/json", "Authorization": "Bearer ***"},
        response_headers={"Content-Type": "application/json"},
        error_message="Internal server error" if is_error else None,
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


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/transactions")
async def list_transactions(
    limit: int = Query(50, ge=1, le=200),
    tenant_id: Optional[str] = None,
    api_name: Optional[str] = None,
    status: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """
    List recent API transactions.

    Returns transaction summaries for efficient list display.
    """
    # Use user's tenant if not CPI admin
    effective_tenant = tenant_id or user.tenant_id or "demo"

    transactions = generate_demo_transactions(limit, effective_tenant)

    # Filter by api_name if provided
    if api_name:
        transactions = [t for t in transactions if t.api_name == api_name]

    # Filter by status if provided
    if status:
        transactions = [t for t in transactions if t.status == status]

    return {
        "transactions": [t.model_dump() for t in transactions],
        "total": len(transactions),
    }


@router.get("/transactions/stats")
async def get_transaction_stats(
    user: User = Depends(get_current_user),
):
    """
    Get API transaction statistics.

    Returns aggregated metrics about API calls.
    """
    return generate_stats().model_dump()


@router.get("/transactions/{transaction_id}")
async def get_transaction(
    transaction_id: str,
    user: User = Depends(get_current_user),
):
    """
    Get detailed information about a specific transaction.

    Includes all spans with timing and metadata.
    """
    tenant_id = user.tenant_id or "demo"
    transaction = generate_transaction_detail(transaction_id, tenant_id)
    return transaction.model_dump()
