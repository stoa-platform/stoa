"""Prometheus Metrics Middleware.

Collects and exposes metrics for the MCP Gateway.
"""

import time
from collections.abc import Callable

from fastapi import Request, Response
from prometheus_client import Counter, Gauge, Histogram, Info
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import get_settings
from ..tracing_config import get_current_trace_id

settings = get_settings()
prefix = settings.metrics_prefix


# =============================================================================
# Metrics Definitions
# =============================================================================

# HTTP Metrics
HTTP_REQUESTS_TOTAL = Counter(
    f"{prefix}_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    f"{prefix}_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    f"{prefix}_http_requests_in_progress",
    "Number of HTTP requests in progress",
    ["method", "endpoint"],
)

# MCP Tool Metrics
MCP_TOOL_INVOCATIONS_TOTAL = Counter(
    f"{prefix}_mcp_tool_invocations_total",
    "Total MCP tool invocations",
    ["tool_name", "status"],
)

MCP_TOOL_INVOCATION_DURATION_SECONDS = Histogram(
    f"{prefix}_mcp_tool_invocation_duration_seconds",
    "MCP tool invocation duration in seconds",
    ["tool_name"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

MCP_TOOLS_REGISTERED = Gauge(
    f"{prefix}_mcp_tools_registered",
    "Number of registered MCP tools",
)

# Authentication Metrics
AUTH_REQUESTS_TOTAL = Counter(
    f"{prefix}_auth_requests_total",
    "Total authentication attempts",
    ["status", "reason"],
)

AUTH_TOKEN_VALIDATION_DURATION_SECONDS = Histogram(
    f"{prefix}_auth_token_validation_duration_seconds",
    "JWT token validation duration in seconds",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
)

# Backend Metrics
BACKEND_REQUESTS_TOTAL = Counter(
    f"{prefix}_backend_requests_total",
    "Total backend API requests",
    ["backend", "method", "status_code"],
)

BACKEND_REQUEST_DURATION_SECONDS = Histogram(
    f"{prefix}_backend_request_duration_seconds",
    "Backend API request duration in seconds",
    ["backend", "method"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Service Info
SERVICE_INFO = Info(
    f"{prefix}_service",
    "Service information",
)

# Initialize service info
SERVICE_INFO.info({
    "name": "stoa-mcp-gateway",
    "version": settings.app_version,
    "environment": settings.environment,
})

# =============================================================================
# APDEX Metrics (CAB-Observability)
# =============================================================================

# APDEX thresholds: T = 500ms (satisfied < T, tolerating < 4T, frustrated >= 4T)
APDEX_THRESHOLD_T = 0.5  # 500ms
APDEX_THRESHOLD_4T = 2.0  # 2000ms

APDEX_SATISFIED_TOTAL = Counter(
    f"{prefix}_apdex_satisfied_total",
    "Requests with response time < T (satisfied users)",
    ["tenant_id"],
)

APDEX_TOLERATING_TOTAL = Counter(
    f"{prefix}_apdex_tolerating_total",
    "Requests with response time between T and 4T (tolerating users)",
    ["tenant_id"],
)

APDEX_FRUSTRATED_TOTAL = Counter(
    f"{prefix}_apdex_frustrated_total",
    "Requests with response time >= 4T (frustrated users)",
    ["tenant_id"],
)

# =============================================================================
# Billing/Usage Metrics (CAB-Observability)
# =============================================================================

BILLABLE_REQUESTS_TOTAL = Counter(
    f"{prefix}_billable_requests_total",
    "Total billable API requests",
    ["tenant_id", "tool_name"],
)

TOKENS_CONSUMED_TOTAL = Counter(
    f"{prefix}_tokens_consumed_total",
    "Total tokens consumed",
    ["tenant_id", "tool_name", "direction"],  # direction: input/output
)

TOKENS_COST_TOTAL = Counter(
    f"{prefix}_tokens_cost_total",
    "Estimated cost of tokens consumed (in micro-cents)",
    ["tenant_id"],
)

# =============================================================================
# Business Metrics (CAB-Observability)
# =============================================================================

UNIQUE_USERS_TOTAL = Gauge(
    f"{prefix}_unique_users_total",
    "Number of unique active users",
    ["tenant_id", "period"],  # period: 1h, 24h, 7d
)

SESSIONS_TOTAL = Counter(
    f"{prefix}_sessions_total",
    "Total user sessions",
    ["tenant_id"],
)


# =============================================================================
# Middleware
# =============================================================================


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware for collecting HTTP metrics."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process request and collect metrics."""
        method = request.method
        # Normalize endpoint for metrics (remove IDs, etc.)
        endpoint = self._normalize_path(request.url.path)

        # Track in-progress requests
        HTTP_REQUESTS_IN_PROGRESS.labels(
            method=method,
            endpoint=endpoint,
        ).inc()

        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            # Record duration with trace_id exemplar for metrics→traces (CAB-1088)
            duration = time.time() - start_time
            trace_id = get_current_trace_id()
            if trace_id:
                HTTP_REQUEST_DURATION_SECONDS.labels(
                    method=method,
                    endpoint=endpoint,
                ).observe(duration, exemplar={"trace_id": trace_id})
            else:
                HTTP_REQUEST_DURATION_SECONDS.labels(
                    method=method,
                    endpoint=endpoint,
                ).observe(duration)

            # Record request count
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code),
            ).inc()

            # Record APDEX metrics (CAB-Observability)
            # Extract tenant_id from request state if available
            tenant_id = getattr(request.state, "tenant_id", None) or "default"
            record_apdex(duration, tenant_id)

            # Decrease in-progress counter
            HTTP_REQUESTS_IN_PROGRESS.labels(
                method=method,
                endpoint=endpoint,
            ).dec()

        return response

    def _normalize_path(self, path: str) -> str:
        """Normalize path for metrics labels.

        Replaces dynamic segments (UUIDs, IDs) with placeholders
        to prevent high cardinality.
        """
        import re

        # Replace UUIDs
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{id}",
            path,
            flags=re.IGNORECASE,
        )

        # Replace numeric IDs
        path = re.sub(r"/\d+(?=/|$)", "/{id}", path)

        return path


# =============================================================================
# Metric Recording Functions
# =============================================================================


def record_tool_invocation(
    tool_name: str,
    duration_seconds: float,
    success: bool,
) -> None:
    """Record metrics for a tool invocation."""
    status = "success" if success else "error"
    MCP_TOOL_INVOCATIONS_TOTAL.labels(
        tool_name=tool_name,
        status=status,
    ).inc()
    # Attach trace_id exemplar for metrics→traces navigation (CAB-1088)
    trace_id = get_current_trace_id()
    if trace_id:
        MCP_TOOL_INVOCATION_DURATION_SECONDS.labels(
            tool_name=tool_name,
        ).observe(duration_seconds, exemplar={"trace_id": trace_id})
    else:
        MCP_TOOL_INVOCATION_DURATION_SECONDS.labels(
            tool_name=tool_name,
        ).observe(duration_seconds)


def record_auth_attempt(
    success: bool,
    reason: str = "",
) -> None:
    """Record metrics for an authentication attempt."""
    status = "success" if success else "failure"
    AUTH_REQUESTS_TOTAL.labels(
        status=status,
        reason=reason,
    ).inc()


def record_backend_request(
    backend: str,
    method: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record metrics for a backend API request."""
    BACKEND_REQUESTS_TOTAL.labels(
        backend=backend,
        method=method,
        status_code=str(status_code),
    ).inc()
    BACKEND_REQUEST_DURATION_SECONDS.labels(
        backend=backend,
        method=method,
    ).observe(duration_seconds)


def update_tools_registered(count: int) -> None:
    """Update the count of registered tools."""
    MCP_TOOLS_REGISTERED.set(count)


# =============================================================================
# APDEX & Billing Recording Functions (CAB-Observability)
# =============================================================================


def record_apdex(
    duration_seconds: float,
    tenant_id: str = "default",
) -> None:
    """Record APDEX satisfaction level based on response time.

    APDEX thresholds:
    - Satisfied: < T (500ms)
    - Tolerating: T to 4T (500ms to 2s)
    - Frustrated: >= 4T (>= 2s)
    """
    if duration_seconds < APDEX_THRESHOLD_T:
        APDEX_SATISFIED_TOTAL.labels(tenant_id=tenant_id).inc()
    elif duration_seconds < APDEX_THRESHOLD_4T:
        APDEX_TOLERATING_TOTAL.labels(tenant_id=tenant_id).inc()
    else:
        APDEX_FRUSTRATED_TOTAL.labels(tenant_id=tenant_id).inc()


def record_billable_request(
    tenant_id: str,
    tool_name: str,
) -> None:
    """Record a billable API request."""
    BILLABLE_REQUESTS_TOTAL.labels(
        tenant_id=tenant_id,
        tool_name=tool_name,
    ).inc()


def record_tokens_consumed(
    tenant_id: str,
    tool_name: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_micro_cents: int = 0,
) -> None:
    """Record token consumption for billing.

    Args:
        tenant_id: The tenant identifier
        tool_name: The MCP tool name
        input_tokens: Number of input tokens consumed
        output_tokens: Number of output tokens generated
        cost_micro_cents: Estimated cost in micro-cents (1/10000 of a cent)
    """
    if input_tokens > 0:
        TOKENS_CONSUMED_TOTAL.labels(
            tenant_id=tenant_id,
            tool_name=tool_name,
            direction="input",
        ).inc(input_tokens)
    if output_tokens > 0:
        TOKENS_CONSUMED_TOTAL.labels(
            tenant_id=tenant_id,
            tool_name=tool_name,
            direction="output",
        ).inc(output_tokens)
    if cost_micro_cents > 0:
        TOKENS_COST_TOTAL.labels(tenant_id=tenant_id).inc(cost_micro_cents)


def record_session(tenant_id: str) -> None:
    """Record a new user session."""
    SESSIONS_TOTAL.labels(tenant_id=tenant_id).inc()


def update_unique_users(
    tenant_id: str,
    count: int,
    period: str = "24h",
) -> None:
    """Update the count of unique active users.

    Args:
        tenant_id: The tenant identifier
        count: Number of unique users
        period: Time period (1h, 24h, 7d)
    """
    UNIQUE_USERS_TOTAL.labels(
        tenant_id=tenant_id,
        period=period,
    ).set(count)
