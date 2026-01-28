# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Trace ID middleware - propagates and generates trace IDs.

CAB-1018: Mock APIs for Central Bank Demo
Ensures all requests have a trace ID for correlation.
"""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

import structlog

# Context variable for trace ID (accessible throughout request lifecycle)
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    """Get the current trace ID from context."""
    return trace_id_var.get()


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Middleware to handle trace ID propagation.

    - Extracts X-Trace-Id from incoming request headers
    - Generates a new trace ID if not present
    - Adds trace ID to response headers
    - Binds trace ID to structlog context
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract or generate trace ID
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())

        # Store in context variable
        trace_id_var.set(trace_id)

        # Bind to structlog context for all logs in this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            path=request.url.path,
            method=request.method,
        )

        # Process request
        response = await call_next(request)

        # Add trace ID to response headers
        response.headers["X-Trace-Id"] = trace_id

        return response
