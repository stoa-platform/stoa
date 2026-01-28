"""Last Gasp Middleware — CAB-957 Anti-Zombie Node Pattern.

Ensures requests are logged and properly rejected when the node is not ready.
This middleware MUST be added LAST in the chain (executed FIRST in FastAPI).

Key features:
- Logs all requests received while not ready (diagnostic visibility)
- Returns 503 with X-STOA-Node-Status: degraded header
- Preserves/generates correlation ID for tracing
- Increments Prometheus metric for alerting
"""

import uuid
from typing import Callable

import structlog
from fastapi import Request, Response
from prometheus_client import Counter
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()
prefix = settings.metrics_prefix

# =============================================================================
# Metrics
# =============================================================================

REQUESTS_REJECTED_TOTAL = Counter(
    f"{prefix}_requests_rejected_total",
    "Requests rejected by gateway",
    ["reason"],
)


# =============================================================================
# Middleware
# =============================================================================


class LastGaspMiddleware(BaseHTTPMiddleware):
    """Middleware for handling requests when node is not ready.

    When the node is not ready (app_state["ready"] = False), this middleware:
    1. Logs the request with correlation ID (Last Gasp Logging)
    2. Increments the rejection metric
    3. Returns 503 with diagnostic headers

    This ensures no request goes untracked, even during degraded state.
    """

    def __init__(self, app, app_state: dict):
        """Initialize middleware with reference to app state.

        Args:
            app: The FastAPI/Starlette application
            app_state: Dictionary containing "ready" boolean flag
        """
        super().__init__(app)
        self._app_state = app_state

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process request, rejecting if node not ready."""
        # Check readiness state
        if not self._app_state.get("ready", False):
            return await self._handle_not_ready(request)

        # Node is ready — proceed normally
        return await call_next(request)

    async def _handle_not_ready(self, request: Request) -> Response:
        """Handle request when node is not ready.

        Implements "Last Gasp Logging" pattern:
        - Log the request for diagnostic purposes
        - Increment metric for alerting
        - Return proper 503 response
        """
        # Extract or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Log the rejected request (Last Gasp)
        logger.warning(
            "request_rejected_not_ready",
            correlation_id=correlation_id,
            method=request.method,
            path=str(request.url.path),
            query=str(request.url.query) if request.url.query else None,
            client_host=request.client.host if request.client else None,
        )

        # Increment Prometheus metric
        REQUESTS_REJECTED_TOTAL.labels(reason="not_ready").inc()

        # Return 503 with diagnostic headers
        return Response(
            content="Service temporarily unavailable - node initializing",
            status_code=503,
            headers={
                "X-STOA-Node-Status": "degraded",
                "X-Correlation-ID": correlation_id,
                "Retry-After": "5",
            },
            media_type="text/plain",
        )


# =============================================================================
# Helper Functions
# =============================================================================


def record_request_rejected(reason: str) -> None:
    """Record a rejected request metric.

    Args:
        reason: Rejection reason (not_ready, rate_limited, etc.)
    """
    REQUESTS_REJECTED_TOTAL.labels(reason=reason).inc()
