# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
Shadow Traffic Middleware for Python → Rust Migration.

Mirrors all MCP requests to the Rust gateway asynchronously.
Python response is authoritative, Rust response is logged for comparison.
"""

import asyncio
import json
import time
from typing import Any, Optional

import httpx
import structlog
from fastapi import Request
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = structlog.get_logger(__name__)

# Prometheus Metrics
SHADOW_REQUESTS_TOTAL = Counter(
    "mcp_shadow_requests_total",
    "Total shadow requests sent to Rust gateway",
    ["status"],  # success, error, timeout
)

SHADOW_LATENCY_SECONDS = Histogram(
    "mcp_shadow_latency_seconds",
    "Latency of shadow requests to Rust gateway",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

SHADOW_MATCH_TOTAL = Counter(
    "mcp_shadow_match_total",
    "Shadow response match results",
    ["result"],  # match, mismatch, error
)


class ShadowMiddleware(BaseHTTPMiddleware):
    """
    Middleware that mirrors requests to Rust gateway in shadow mode.

    - Python gateway handles the actual response (authoritative)
    - Rust gateway receives a copy (fire-and-forget)
    - Responses are compared and logged
    """

    def __init__(
        self,
        app,
        rust_gateway_url: str,
        enabled: bool = True,
        timeout: float = 5.0,
    ):
        super().__init__(app)
        self.rust_gateway_url = rust_gateway_url.rstrip("/")
        self.enabled = enabled
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and optionally mirror to Rust gateway."""
        if not self.enabled:
            return await call_next(request)

        # Only shadow MCP endpoints
        if not request.url.path.startswith("/mcp/"):
            return await call_next(request)

        # Capture request body for shadow (must be done before call_next)
        body = await request.body()

        # Start timing
        start_time = time.perf_counter()

        # Execute on Python (authoritative)
        python_response = await call_next(request)
        python_latency = time.perf_counter() - start_time

        # Read Python response body for comparison
        # Note: body_iterator is consumed, so we must capture it
        python_body = b""
        async for chunk in python_response.body_iterator:
            python_body += chunk

        # Fire async shadow request to Rust (non-blocking)
        asyncio.create_task(
            self._shadow_request(
                request=request,
                body=body,
                python_response_status=python_response.status_code,
                python_response_body=python_body,
                python_latency=python_latency,
            )
        )

        # Reconstruct response for client
        return Response(
            content=python_body,
            status_code=python_response.status_code,
            headers=dict(python_response.headers),
            media_type=python_response.media_type,
        )

    async def _shadow_request(
        self,
        request: Request,
        body: bytes,
        python_response_status: int,
        python_response_body: bytes,
        python_latency: float,
    ) -> None:
        """Send shadow request to Rust gateway and compare responses."""
        start_time = time.perf_counter()
        rust_response_status: Optional[int] = None
        rust_response_body: Optional[bytes] = None
        rust_latency: Optional[float] = None
        error: Optional[str] = None

        try:
            # Build shadow URL
            shadow_url = f"{self.rust_gateway_url}{request.url.path}"
            if request.url.query:
                shadow_url += f"?{request.url.query}"

            # Copy headers (except host and content-length)
            headers = {
                k: v
                for k, v in request.headers.items()
                if k.lower() not in ("host", "content-length")
            }
            headers["X-Shadow-Mode"] = "true"
            headers["X-Shadow-Request-Id"] = request.headers.get(
                "x-request-id", "unknown"
            )

            # Send to Rust gateway
            client = await self._get_client()
            rust_response = await client.request(
                method=request.method,
                url=shadow_url,
                headers=headers,
                content=body,
            )

            rust_latency = time.perf_counter() - start_time
            rust_response_status = rust_response.status_code
            rust_response_body = rust_response.content

            SHADOW_REQUESTS_TOTAL.labels(status="success").inc()
            SHADOW_LATENCY_SECONDS.observe(rust_latency)

        except httpx.TimeoutException:
            error = "timeout"
            SHADOW_REQUESTS_TOTAL.labels(status="timeout").inc()
        except Exception as e:
            error = str(e)
            SHADOW_REQUESTS_TOTAL.labels(status="error").inc()

        # Compare and log
        await self._compare_responses(
            request_path=request.url.path,
            request_method=request.method,
            python_status=python_response_status,
            python_body=python_response_body,
            python_latency=python_latency,
            rust_status=rust_response_status,
            rust_body=rust_response_body,
            rust_latency=rust_latency,
            error=error,
        )

    async def _compare_responses(
        self,
        request_path: str,
        request_method: str,
        python_status: int,
        python_body: bytes,
        python_latency: float,
        rust_status: Optional[int],
        rust_body: Optional[bytes],
        rust_latency: Optional[float],
        error: Optional[str],
    ) -> None:
        """Compare Python and Rust responses, log differences."""
        if error:
            SHADOW_MATCH_TOTAL.labels(result="error").inc()
            logger.warning(
                "Shadow request failed",
                path=request_path,
                method=request_method,
                error=error,
            )
            return

        # Compare status codes
        status_match = python_status == rust_status

        # Compare response bodies (normalize JSON for comparison)
        body_match = self._compare_bodies(python_body, rust_body)

        if status_match and body_match:
            SHADOW_MATCH_TOTAL.labels(result="match").inc()
            logger.debug(
                "Shadow match",
                path=request_path,
                python_latency_ms=round(python_latency * 1000, 2),
                rust_latency_ms=round(rust_latency * 1000, 2) if rust_latency else None,
            )
        else:
            SHADOW_MATCH_TOTAL.labels(result="mismatch").inc()
            logger.warning(
                "Shadow MISMATCH",
                path=request_path,
                method=request_method,
                status_match=status_match,
                body_match=body_match,
                python_status=python_status,
                rust_status=rust_status,
                python_latency_ms=round(python_latency * 1000, 2),
                rust_latency_ms=round(rust_latency * 1000, 2) if rust_latency else None,
                python_body_preview=python_body[:500].decode("utf-8", errors="replace"),
                rust_body_preview=(
                    rust_body[:500].decode("utf-8", errors="replace")
                    if rust_body
                    else None
                ),
            )

    def _compare_bodies(
        self, python_body: bytes, rust_body: Optional[bytes]
    ) -> bool:
        """Compare response bodies, normalizing JSON."""
        if rust_body is None:
            return False

        # Try JSON normalization
        try:
            python_json = json.loads(python_body)
            rust_json = json.loads(rust_body)

            # Remove dynamic fields (timestamps, request IDs)
            self._normalize_json(python_json)
            self._normalize_json(rust_json)

            return python_json == rust_json
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Fall back to byte comparison
            return python_body == rust_body

    def _normalize_json(self, obj: Any) -> None:
        """Remove dynamic fields that will differ between implementations."""
        if isinstance(obj, dict):
            # Remove fields that naturally differ
            for key in ["timestamp", "request_id", "trace_id", "duration_ms"]:
                obj.pop(key, None)
            for value in obj.values():
                self._normalize_json(value)
        elif isinstance(obj, list):
            for item in obj:
                self._normalize_json(item)
