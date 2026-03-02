"""Pydantic schemas for monitoring endpoints."""

from pydantic import BaseModel


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
    client_ip: str | None = None
    user_id: str | None = None
    started_at: str
    total_duration_ms: int
    spans: list[TransactionSpan]
    request_headers: dict | None = None
    response_headers: dict | None = None
    error_message: str | None = None


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
