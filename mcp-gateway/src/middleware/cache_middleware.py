# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Semantic Cache Middleware — CAB-881 Step 4/4.

Intercepts POST /tools/{name} requests:
1. On request: check cache for hit (fast path + semantic)
2. On miss: forward to upstream, cache the response
3. Respects Cache-Control: no-cache header for bypass

Prometheus metrics:
- stoa_cache_hits_total
- stoa_cache_misses_total
- stoa_cache_latency_seconds
"""

import json
import time

import structlog
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from ..cache.semantic_cache import SemanticCache
from ..cache.embedder import Embedder
from ..services.database import get_db_session

logger = structlog.get_logger(__name__)

# Prometheus metrics
CACHE_HITS = Counter(
    "stoa_cache_hits_total",
    "Total semantic cache hits",
    ["tool_name"],
)
CACHE_MISSES = Counter(
    "stoa_cache_misses_total",
    "Total semantic cache misses",
    ["tool_name"],
)
CACHE_LATENCY = Histogram(
    "stoa_cache_latency_seconds",
    "Cache lookup latency",
    ["path"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)

# Shared instances
_embedder = Embedder()
_cache = SemanticCache(embedder=_embedder)


def get_semantic_cache() -> SemanticCache:
    """Get the shared SemanticCache instance."""
    return _cache


class SemanticCacheMiddleware(BaseHTTPMiddleware):
    """Middleware that intercepts tool calls for cache lookup/store."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Only intercept POST /tools/{name}
        if request.method != "POST" or not request.url.path.startswith("/tools/"):
            return await call_next(request)

        # Extract tool name
        path_parts = request.url.path.strip("/").split("/")
        if len(path_parts) < 2:
            return await call_next(request)
        tool_name = path_parts[1]

        # Respect Cache-Control: no-cache
        if request.headers.get("cache-control", "").lower() == "no-cache":
            logger.debug("cache_bypass", tool=tool_name)
            return await call_next(request)

        # Extract tenant_id
        tenant_id = request.headers.get("x-tenant-id", "")
        if not tenant_id:
            return await call_next(request)

        # Parse request body for arguments
        try:
            body = await request.body()
            body_json = json.loads(body) if body else {}
            arguments = body_json.get("arguments", {})
        except (json.JSONDecodeError, UnicodeDecodeError):
            return await call_next(request)

        # --- Cache lookup ---
        start = time.monotonic()
        try:
            async with get_db_session() as session:
                cached = await _cache.lookup(session, tenant_id, tool_name, arguments)
        except Exception as e:
            logger.warning("cache_lookup_error", tool=tool_name, error=str(e))
            cached = None

        elapsed = time.monotonic() - start
        CACHE_LATENCY.labels(path=request.url.path).observe(elapsed)

        if cached is not None:
            CACHE_HITS.labels(tool_name=tool_name).inc()
            return Response(
                content=json.dumps(cached),
                status_code=200,
                media_type="application/json",
                headers={"X-Cache": "HIT"},
            )

        CACHE_MISSES.labels(tool_name=tool_name).inc()

        # --- Forward to upstream ---
        response = await call_next(request)

        # Store response in cache (only on success)
        if response.status_code == 200:
            try:
                resp_body = b""
                async for chunk in response.body_iterator:
                    if isinstance(chunk, str):
                        resp_body += chunk.encode("utf-8")
                    else:
                        resp_body += chunk

                resp_json = json.loads(resp_body)

                # Don't cache error responses
                if not resp_json.get("isError", False):
                    async with get_db_session() as session:
                        await _cache.store(session, tenant_id, tool_name, arguments, resp_json)

                # Rebuild response since we consumed body_iterator
                return Response(
                    content=resp_body,
                    status_code=response.status_code,
                    media_type=response.media_type,
                    headers=dict(response.headers) | {"X-Cache": "MISS"},
                )
            except Exception as e:
                logger.warning("cache_store_error", tool=tool_name, error=str(e))
                # Return original response on store error
                return Response(
                    content=resp_body,
                    status_code=response.status_code,
                    media_type=response.media_type,
                    headers=dict(response.headers) | {"X-Cache": "MISS"},
                )

        return response
