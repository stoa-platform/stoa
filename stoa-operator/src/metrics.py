"""Prometheus metrics for the STOA operator."""

from prometheus_client import Counter, Gauge, Histogram

# --- Reconciliation metrics ---

RECONCILIATIONS_TOTAL = Counter(
    "stoa_operator_reconciliations_total",
    "Total reconciliation handler calls",
    ["kind", "action", "result"],
)

RECONCILIATION_DURATION = Histogram(
    "stoa_operator_reconciliation_duration_seconds",
    "Reconciliation handler execution time",
    ["kind", "action"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# --- CP API client metrics ---

CP_API_REQUESTS_TOTAL = Counter(
    "stoa_operator_cp_api_requests_total",
    "Total CP API HTTP calls",
    ["method", "endpoint", "status"],
)

CP_API_DURATION = Histogram(
    "stoa_operator_cp_api_duration_seconds",
    "CP API call latency",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# --- Operator health ---

RESOURCES_MANAGED = Gauge(
    "stoa_operator_resources_managed",
    "Current count of managed resources",
    ["kind"],
)

OPERATOR_UP = Gauge(
    "stoa_operator_up",
    "1 when operator is running",
)


def record_reconciliation(kind: str, action: str, result: str, duration: float) -> None:
    """Record a reconciliation event with timing."""
    RECONCILIATIONS_TOTAL.labels(kind=kind, action=action, result=result).inc()
    RECONCILIATION_DURATION.labels(kind=kind, action=action).observe(duration)


def record_cp_api_call(method: str, endpoint: str, status: str, duration: float) -> None:
    """Record a CP API call with timing."""
    CP_API_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status=status).inc()
    CP_API_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
