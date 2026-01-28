# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Token Counter Middleware (CAB-881).

Async middleware that captures MCP request/response payloads and pushes
them to an in-memory queue for background token counting.
Zero latency impact on the hot path.

Architecture:
  MCP Request → TokenCounterMiddleware (capture & queue) → Response
                         ↓ (async, non-blocking)
                 TokenCounterWorker (count & emit Prometheus metrics)
"""

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Callable

import structlog
from fastapi import Request, Response
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

from ..config import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()
prefix = settings.metrics_prefix

# =============================================================================
# Prometheus Metrics (CAB-881)
# =============================================================================

# Public metrics (exposed on /metrics)
TOKENS_TOTAL = Counter(
    f"{prefix}_tokens_total",
    "Total token count for MCP payloads",
    ["tool_name", "direction"],
)

PAYLOAD_BYTES = Histogram(
    f"{prefix}_payload_bytes",
    "MCP payload size in bytes",
    ["tool_name"],
    buckets=(64, 256, 1024, 4096, 16384, 65536, 262144, 1048576),
)

# Internal metrics (not exposed on public /metrics — scraped by internal Prometheus)
TOKENS_BY_TENANT = Counter(
    f"{prefix}_tokens_by_tenant",
    "Token count per tenant (internal only)",
    ["tenant_id", "tool_name"],
)

TOKEN_SAVINGS_RATIO = Histogram(
    f"{prefix}_token_savings_ratio",
    "Token reduction ratio after optimization (0.0-1.0)",
    ["tool_name"],
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)


# =============================================================================
# Token Counting
# =============================================================================

def _count_tokens_approx(text: str) -> int:
    """Approximate token count: len(text) / 4.

    Standard approximation, zero dependency.
    For precise counting, enable tiktoken via STOA_TOKEN_COUNTER=tiktoken.
    """
    return max(1, len(text) // 4)


def _count_tokens_tiktoken(text: str) -> int:
    """Precise token count using tiktoken (opt-in)."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        logger.warning("tiktoken not installed, falling back to approximation")
        return _count_tokens_approx(text)


def count_tokens(text: str) -> int:
    """Count tokens using configured strategy."""
    strategy = os.environ.get("STOA_TOKEN_COUNTER", "approx")
    if strategy == "tiktoken":
        return _count_tokens_tiktoken(text)
    return _count_tokens_approx(text)


# =============================================================================
# Queue Payload
# =============================================================================

@dataclass
class TokenPayload:
    """Payload queued for background token counting."""
    tool_name: str
    tenant_id: str
    direction: str  # "request" or "response"
    body: str
    timestamp: float = field(default_factory=time.time)


# Global async queue — consumed by TokenCounterWorker
_token_queue: asyncio.Queue[TokenPayload] | None = None


def get_token_queue() -> asyncio.Queue[TokenPayload]:
    """Get or create the global token queue."""
    global _token_queue
    if _token_queue is None:
        _token_queue = asyncio.Queue(maxsize=10_000)
    return _token_queue


# =============================================================================
# Middleware
# =============================================================================

def _extract_tool_name(path: str, body: dict | None) -> str | None:
    """Extract MCP tool name from request path or body."""
    # REST tool call: POST /tools/{tool_name}
    if path.startswith("/tools/") and "/" in path[7:] is False:
        return path[7:]

    # MCP JSON-RPC: tools/call in body
    if body and body.get("method") == "tools/call":
        params = body.get("params", {})
        return params.get("name")

    # REST pattern: POST /tools/{name}
    parts = path.rstrip("/").split("/")
    if len(parts) >= 2 and parts[-2] == "tools":
        return parts[-1]

    return None


def _extract_tenant_id(request: Request) -> str:
    """Extract tenant_id from request headers or auth claims."""
    # X-Tenant-ID header (set by stoactl and gateway)
    tenant = request.headers.get("X-Tenant-ID", "")
    if tenant:
        return tenant

    # Fall back to auth claims if available
    if hasattr(request.state, "user") and request.state.user:
        return getattr(request.state.user, "tenant_id", "unknown")

    return "unknown"


def _hash_for_log(value: str) -> str:
    """Hash a value for safe logging (PII masking)."""
    return hashlib.sha256(value.encode()).hexdigest()[:12]


class TokenCounterMiddleware(BaseHTTPMiddleware):
    """Middleware that captures MCP payloads for async token counting.

    Zero latency impact: captures payload and pushes to asyncio.Queue.
    Background worker (TokenCounterWorker) consumes and counts.
    """

    # Only intercept MCP tool-related paths
    MONITORED_PREFIXES = ("/tools/", "/mcp/")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Capture payload and forward to queue without blocking."""
        path = request.url.path

        # Skip non-MCP paths
        if not any(path.startswith(p) for p in self.MONITORED_PREFIXES):
            return await call_next(request)

        # Read request body
        request_body = await request.body()
        request_text = request_body.decode("utf-8", errors="replace")

        # Parse body for tool name extraction
        parsed_body = None
        if request_text:
            try:
                parsed_body = json.loads(request_text)
            except (json.JSONDecodeError, ValueError):
                pass

        tool_name = _extract_tool_name(path, parsed_body) or "unknown"
        tenant_id = _extract_tenant_id(request)

        # Queue request payload (non-blocking)
        queue = get_token_queue()
        try:
            queue.put_nowait(TokenPayload(
                tool_name=tool_name,
                tenant_id=tenant_id,
                direction="request",
                body=request_text,
            ))
        except asyncio.QueueFull:
            logger.warning(
                "token_counter_queue_full",
                tool_name=tool_name,
                tenant_hash=_hash_for_log(tenant_id),
            )

        # Call downstream
        response = await call_next(request)

        # Capture response body
        response_body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                response_body += chunk.encode("utf-8")
            else:
                response_body += chunk

        response_text = response_body.decode("utf-8", errors="replace")

        # Record payload size (sync — lightweight)
        PAYLOAD_BYTES.labels(tool_name=tool_name).observe(len(response_body))

        # Queue response payload (non-blocking)
        try:
            queue.put_nowait(TokenPayload(
                tool_name=tool_name,
                tenant_id=tenant_id,
                direction="response",
                body=response_text,
            ))
        except asyncio.QueueFull:
            pass  # Already logged above if queue is full

        # Reconstruct response
        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
