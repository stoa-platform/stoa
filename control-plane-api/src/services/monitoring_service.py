"""Monitoring service — queries audit index in OpenSearch for real transaction data."""

import logging

from opensearchpy import AsyncOpenSearch

from ..schemas.monitoring import (
    APITransaction,
    APITransactionStats,
    APITransactionSummary,
    TransactionSpan,
)

logger = logging.getLogger(__name__)


HTTP_STATUS_TEXT: dict[int, str] = {
    200: "OK",
    201: "Created",
    204: "No Content",
    301: "Moved Permanently",
    304: "Not Modified",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}

# Map path prefixes to error source labels
_ERROR_SOURCE_PATTERNS: list[tuple[str, str]] = [
    ("/v1/certificates", "certificates"),
    ("/v1/monitoring", "monitoring"),
    ("/v1/gateways", "gateway-adapter"),
    ("/v1/deployments", "deployment"),
    ("/v1/tenants", "tenant-mgmt"),
    ("/v1/portal", "portal"),
    ("/v1/subscriptions", "subscriptions"),
    ("/v1/api-keys", "api-keys"),
    ("/v1/applications", "applications"),
    ("/v1/apis", "api-catalog"),
]


def _status_text(code: int) -> str:
    """Return human-readable HTTP status text."""
    return HTTP_STATUS_TEXT.get(code, f"HTTP {code}")


def _error_source(path: str, code: int) -> str | None:
    """Identify the origin of an error from the HTTP status code and request path.

    Uses status code semantics first (certain codes always come from a specific
    layer regardless of path), then falls back to path-based detection.

    Returns None for successful responses (no error source needed).
    """
    if code < 400:
        return None

    # --- Layer-based detection (code semantics override path) ---

    # Auth layer: 401 is always the auth middleware (Keycloak JWT validation)
    if code == 401:
        return "auth"

    # RBAC layer: 403 is always the authorization/permission check
    if code == 403:
        return "rbac"

    # Rate limiting: 429 is always the rate-limiter middleware
    if code == 429:
        return "rate-limiter"

    # Gateway/proxy errors: 502/503/504 indicate upstream failure
    if code in (502, 503, 504):
        return "gateway"

    # --- Path-based detection (for codes where the endpoint matters) ---

    # 501 Not Implemented = the endpoint itself doesn't support the operation
    # 400/404/405/409/422 = the endpoint rejected the request
    # 500 = the endpoint crashed
    for prefix, source in _ERROR_SOURCE_PATTERNS:
        if path.startswith(prefix):
            return source

    # Fallback for unrecognized paths
    if code >= 500:
        return "backend"
    return "api"


def _status_from_code(code: int) -> str:
    """Derive transaction status from HTTP status code."""
    if code == 504:
        return "timeout"
    if code >= 400:
        return "error"
    return "success"


def _extract_api_name(path: str) -> str:
    """Extract API name from request path (first segment after /v1/)."""
    parts = path.strip("/").split("/")
    try:
        idx = parts.index("v1")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    except ValueError:
        pass
    # Fallback: use first meaningful segment
    return parts[0] if parts else "unknown"


def _build_spans_from_timings(
    gateway_timings: dict[str, float],
    total_latency_ms: int,
    status_code: int,
    path: str,
) -> list[TransactionSpan]:
    """Build ordered TransactionSpan list from gateway Server-Timing data.

    Maps gateway timing stages to spans with computed start offsets.
    Stages are ordered by the gateway middleware chain execution order:
    identity → auth → quota → supervision → policy_eval → routing → backend_call → transport
    """
    # Ordered stages matching the gateway middleware chain
    stage_order = [
        ("identity", "gateway-identity"),
        ("auth", "gateway-auth"),
        ("quota", "gateway-quota"),
        ("supervision", "gateway-supervision"),
        ("policy_eval", "gateway-policy"),
        ("routing", "gateway-routing"),
        ("backend_call", "gateway-backend"),
        ("serialization", "gateway-serialization"),
    ]

    spans: list[TransactionSpan] = []
    offset_ms = 0
    status = _status_from_code(status_code)

    for stage_name, service_name in stage_order:
        dur = gateway_timings.get(stage_name)
        if dur is None:
            continue
        dur_int = max(round(dur), 0)
        spans.append(
            TransactionSpan(
                name=stage_name,
                service=service_name,
                start_offset_ms=offset_ms,
                duration_ms=dur_int,
                status="success" if status_code < 400 else status,
                metadata={},
            )
        )
        offset_ms += dur_int

    # If no gateway spans but we have total, add a single span as fallback
    if not spans:
        source = _error_source(path, status_code) or "control-plane-api"
        spans.append(
            TransactionSpan(
                name="api_request",
                service=source if status_code >= 400 else "control-plane-api",
                start_offset_ms=0,
                duration_ms=total_latency_ms,
                status=status,
                metadata={},
            )
        )

    return spans


# Map OTLP span names → UI-expected names (TraceDetail.tsx, LiveTraces.tsx)
_OTEL_TO_UI_SPAN_NAME: dict[str, str] = {
    "auth.profile": "auth_validation",
    "auth.jwt": "auth_validation",
    "auth.subscription": "subscription_check",
    "auth.mtls.extract": "tls_termination",
    "auth.mtls.binding": "mtls_binding",
    "auth.sender_constraint": "sender_constraint",
    "policy.quota": "rate_limiting",
    "policy.supervision": "policy_eval",
    "policy.guardrails": "guardrails",
    "policy.opa": "policy_eval",
    "proxy.dynamic": "routing",
    "upstream.call": "backend_call",
    "upstream.retry": "backend_retry",
    "http.request": "http_request",
    "mcp.tools.list": "mcp_discovery",
    "mcp.tools.call": "mcp_tool_call",
    "cache.semantic": "cache_lookup",
    "metering.emit": "metering",
    "resilience.circuit_breaker": "circuit_breaker",
    "optimization.token": "token_optimization",
}

# Map OTLP span names → service labels for the UI
_OTEL_TO_UI_SERVICE: dict[str, str] = {
    "auth.profile": "keycloak",
    "auth.jwt": "keycloak",
    "auth.subscription": "stoa-gateway",
    "auth.mtls.extract": "stoa-gateway",
    "auth.mtls.binding": "stoa-gateway",
    "auth.sender_constraint": "stoa-gateway",
    "policy.quota": "stoa-gateway",
    "policy.supervision": "stoa-gateway",
    "proxy.dynamic": "stoa-gateway",
    "upstream.call": "upstream-api",
    "upstream.retry": "upstream-api",
    "http.request": "stoa-gateway",
}


def _span_status_from_otel(status: dict, attrs: dict) -> str:
    """Derive transaction status from OTel span status and attributes."""
    http_code = attrs.get("http@status_code")
    if http_code is not None:
        code = int(http_code)
        if code == 504:
            return "timeout"
        if code >= 400:
            return "error"
        return "success"
    if status.get("code") == 2:
        return "error"
    return "success"


class MonitoringService:
    """Queries OpenSearch audit-* index for transaction analytics."""

    def __init__(self, client: AsyncOpenSearch):
        self.client = client

    # =========================================================================
    # OTEL SPAN QUERIES (CAB-1997 — Data Prepper otel-v1-apm-span-*)
    # =========================================================================

    SERVICE_TYPE_FILTERS: dict[str, dict] = {
        "gateway": {"bool": {"must": [
            {"term": {"serviceName": "stoa-gateway"}},
            {"term": {"resource.attributes.stoa@deployment_mode": "edge-mcp"}},
        ]}},
        "link": {"bool": {"must": [
            {"term": {"serviceName": "stoa-gateway"}},
            {"term": {"resource.attributes.stoa@deployment_mode": "sidecar"}},
        ]}},
        "connect": {"term": {"serviceName": "stoa-connect"}},
    }

    async def list_transactions_from_spans(
        self,
        limit: int = 50,
        api_name: str | None = None,
        status: str | None = None,
        status_code: int | None = None,
        time_range_minutes: int = 60,
        service_type: str | None = None,
    ) -> list[APITransactionSummary] | None:
        """List recent transactions from OTel span index (root spans only).

        Data Prepper flattens span attributes as top-level dot-keys
        (e.g. ``span.attributes.http@method``).  Root spans are internal
        middleware stages (``policy.supervision``) and carry no HTTP
        attributes.  We use ``traceGroupFields`` for overall trace
        duration/status and enrich with HTTP info from child spans.
        """
        try:
            # Query request-level spans (not internal middleware heartbeats).
            # http.request root spans are not exported by tracing-opentelemetry,
            # so we target the handler spans that carry HTTP status codes.
            request_span_names = [
                "mcp.tools.call",
                "mcp.tools.list",
                "proxy.dynamic",
                "http.request",
                "stoa-connect.routes.fetch",
                "stoa-connect.routes.sync",
                "stoa-connect.heartbeat",
                "stoa-connect.discovery",
                "stoa-connect.sync",
                "stoa-connect.register",
                "HTTP GET",
                "HTTP POST",
            ]
            filters: list[dict] = [
                {"range": {"startTime": {"gte": f"now-{time_range_minutes}m"}}},
                {"terms": {"name": request_span_names}},
            ]
            if api_name:
                filters.append({"term": {"serviceName": api_name}})
            if service_type and service_type in self.SERVICE_TYPE_FILTERS:
                filters.append(self.SERVICE_TYPE_FILTERS[service_type])
            if status_code is not None:
                filters.append({"term": {"span.attributes.http@status_code": status_code}})
            elif status == "error":
                filters.append(
                    {
                        "bool": {
                            "should": [
                                {"range": {"span.attributes.http@status_code": {"gte": 400}}},
                                {"term": {"traceGroupFields.statusCode": 2}},
                            ],
                            "minimum_should_match": 1,
                        }
                    }
                )
            elif status == "success":
                filters.append(
                    {
                        "bool": {
                            "must_not": [
                                {"range": {"span.attributes.http@status_code": {"gte": 400}}},
                                {"term": {"traceGroupFields.statusCode": 2}},
                            ]
                        }
                    }
                )
            elif status == "timeout":
                filters.append({"term": {"span.attributes.http@status_code": 504}})

            body = {
                "query": {"bool": {"filter": filters}},
                "sort": [{"startTime": {"order": "desc"}}],
                "size": limit,
            }

            resp = await self.client.search(index="otel-v1-apm-span-*", body=body)
            hits = resp.get("hits", {}).get("hits", [])

            if not hits:
                return None

            transactions: list[APITransactionSummary] = []
            for hit in hits:
                src = hit["_source"]
                tgf = src.get("traceGroupFields", {}) or {}
                otel_status_code = int(tgf.get("statusCode", 0) or 0)

                # Use traceGroupFields for overall trace duration
                trace_dur_nanos = int(tgf.get("durationInNanos", 0) or 0)
                if trace_dur_nanos == 0:
                    trace_dur_nanos = int(src.get("durationInNanos", 0))
                duration_ms = round(trace_dur_nanos / 1_000_000, 3)

                # Real HTTP status code from span attribute (gateway Phase 3A)
                http_code_raw = src.get("span.attributes.http@status_code")
                if http_code_raw is not None:
                    http_code = int(http_code_raw)
                    tx_status = _status_from_code(http_code)
                else:
                    # Fallback for spans without http.status_code (pre-Phase 3A)
                    tx_status = "error" if otel_status_code == 2 else "success"
                    http_code = 500 if tx_status == "error" else 200

                # HTTP method from child span attribute (flattened)
                method = src.get("span.attributes.http@method", "POST")
                route = src.get("span.attributes.http@route", "")
                span_name = route or src.get("traceGroup") or src.get("name", "unknown")

                # Prefer tool_name from span attributes for api_name (CAB-1997)
                tool_name = src.get("span.attributes.tool_name") or src.get("span.attributes.tool")
                api_name = tool_name or _extract_api_name(span_name)

                transactions.append(
                    APITransactionSummary(
                        id=src.get("spanId", hit["_id"]),
                        trace_id=src.get("traceId", ""),
                        api_name=api_name,
                        method=method,
                        path=span_name,
                        status_code=http_code,
                        status=tx_status,
                        status_text=_status_text(http_code),
                        error_source=_error_source(span_name, http_code) if http_code >= 400 else None,
                        started_at=src.get("startTime", ""),
                        total_duration_ms=duration_ms,
                        spans_count=1,
                        deployment_mode=src.get(
                            "resource.attributes.stoa@deployment_mode",
                            src.get("span.attributes.stoa@deployment_mode", "edge-mcp"),
                        ),
                    )
                )
            # Fetch child spans for all traces in a single query
            trace_ids = [t.trace_id for t in transactions if t.trace_id]
            if trace_ids:
                child_body = {
                    "query": {
                        "bool": {
                            "filter": [
                                {"terms": {"traceId": trace_ids}},
                            ],
                            "must_not": [
                                {"terms": {"name": request_span_names}},
                            ],
                        }
                    },
                    "sort": [{"startTime": {"order": "asc"}}],
                    "size": limit * 10,
                }
                child_resp = await self.client.search(index="otel-v1-apm-span-*", body=child_body)
                child_hits = child_resp.get("hits", {}).get("hits", [])

                # Group child spans by traceId
                children_by_trace: dict[str, list[TransactionSpan]] = {}
                for hit in child_hits:
                    src = hit["_source"]
                    tid = src.get("traceId", "")
                    otel_name = src.get("name", "unknown")
                    ui_name = _OTEL_TO_UI_SPAN_NAME.get(otel_name, otel_name)
                    ui_service = _OTEL_TO_UI_SERVICE.get(otel_name, src.get("serviceName", "unknown"))
                    dur_nanos = int(src.get("durationInNanos", 0))
                    dur_ms = round(dur_nanos / 1_000_000, 3)
                    otel_code = int(src.get("status.code", 0) or 0)
                    span_status = "error" if otel_code == 2 else "success"
                    children_by_trace.setdefault(tid, []).append(
                        TransactionSpan(
                            name=ui_name,
                            service=ui_service,
                            start_offset_ms=0,
                            duration_ms=dur_ms,
                            status=span_status,
                            metadata={},
                        )
                    )

                # Chain spans sequentially and attach to transactions
                for tx in transactions:
                    child_spans = children_by_trace.get(tx.trace_id, [])
                    offset = 0.0
                    for i, span in enumerate(child_spans):
                        child_spans[i] = TransactionSpan(
                            name=span.name,
                            service=span.service,
                            start_offset_ms=round(offset, 3),
                            duration_ms=span.duration_ms,
                            status=span.status,
                            metadata={},
                        )
                        offset += span.duration_ms
                    tx.spans = child_spans
                    tx.spans_count = len(child_spans) + 1  # +1 for parent

            return transactions

        except Exception:
            logger.exception("Failed to list transactions from otel spans")
            return None

    async def get_transaction_from_spans(
        self,
        trace_id: str,
    ) -> APITransaction | None:
        """Get detailed transaction with waterfall from OTel span index.

        ``trace_id`` can be either a traceId or a spanId (the Console
        passes spanId from the list view).  We resolve to the full
        trace by looking up the spanId first if the traceId query
        returns no results.
        """
        try:
            # Try as traceId first
            body = {
                "query": {"bool": {"filter": [{"term": {"traceId": trace_id}}]}},
                "sort": [{"startTime": {"order": "asc"}}],
                "size": 200,
            }
            resp = await self.client.search(index="otel-v1-apm-span-*", body=body)
            hits = resp.get("hits", {}).get("hits", [])

            # If no hits, the ID might be a spanId — resolve to traceId
            if not hits:
                span_body = {
                    "query": {"term": {"spanId": trace_id}},
                    "size": 1,
                    "_source": ["traceId"],
                }
                span_resp = await self.client.search(index="otel-v1-apm-span-*", body=span_body)
                span_hits = span_resp.get("hits", {}).get("hits", [])
                if not span_hits:
                    return None
                real_trace_id = span_hits[0]["_source"]["traceId"]
                body["query"] = {"bool": {"filter": [{"term": {"traceId": real_trace_id}}]}}
                resp = await self.client.search(index="otel-v1-apm-span-*", body=body)
                hits = resp.get("hits", {}).get("hits", [])
                trace_id = real_trace_id

            if not hits:
                return None

            # First pass: collect all spans, find root, find HTTP info
            spans: list[TransactionSpan] = []
            root_src: dict | None = None
            http_method: str = "POST"
            http_route: str = ""

            for hit in hits:
                src = hit["_source"]
                duration_nanos = int(src.get("durationInNanos", 0))
                duration_ms = round(duration_nanos / 1_000_000, 3)
                otel_name = src.get("name", "unknown")

                otel_code = int(src.get("status.code", 0) or 0)
                span_status = "error" if otel_code == 2 else "success"

                # Collect metadata from flattened span attributes.
                # Data Prepper flattens OTLP dots to @ separator:
                #   http.method → span.attributes.http@method
                #   upstream.rtt_ms → span.attributes.upstream@rtt_ms
                # http@ keeps bare keys (backward compat); others get prefixed.
                _ATTR_PREFIXES = [
                    ("span.attributes.http@", None),
                    ("span.attributes.upstream@", "upstream"),
                    ("span.attributes.process@", "process"),
                ]
                metadata: dict = {}
                for key, val in src.items():
                    for prefix, category in _ATTR_PREFIXES:
                        if key.startswith(prefix):
                            short_key = key[len(prefix) :]
                            if category:
                                metadata[f"{category}.{short_key}"] = val
                            else:
                                metadata[short_key] = val
                            break

                # Map OTLP names → UI-expected names
                ui_name = _OTEL_TO_UI_SPAN_NAME.get(otel_name, otel_name)
                ui_service = _OTEL_TO_UI_SERVICE.get(otel_name, src.get("serviceName", "unknown"))

                spans.append(
                    TransactionSpan(
                        name=ui_name,
                        service=ui_service,
                        start_offset_ms=0,  # recomputed below
                        duration_ms=duration_ms,
                        status=span_status,
                        metadata=metadata,
                    )
                )

                # Identify root span
                parent_id = src.get("parentSpanId", "")
                if not parent_id:
                    root_src = src

                # Collect HTTP info from child spans
                if src.get("span.attributes.http@method"):
                    http_method = str(src["span.attributes.http@method"])
                if src.get("span.attributes.http@route"):
                    http_route = str(src["span.attributes.http@route"])
            # Recompute start_offset_ms as a sequential pipeline.
            # The parent span (http_request / mcp.tools.call) stays at offset 0
            # and covers the full duration.  Child spans are chained so that
            # each one starts where the previous one ended.
            _PARENT_SPAN_NAMES = {"http_request", "mcp_tool_call", "mcp_discovery"}
            if spans:
                offset_cursor = 0.0
                for i, span in enumerate(spans):
                    if span.name in _PARENT_SPAN_NAMES:
                        # Parent span: offset 0, full duration
                        spans[i] = TransactionSpan(
                            name=span.name,
                            service=span.service,
                            start_offset_ms=0,
                            duration_ms=span.duration_ms,
                            status=span.status,
                            metadata=span.metadata,
                        )
                    else:
                        spans[i] = TransactionSpan(
                            name=span.name,
                            service=span.service,
                            start_offset_ms=round(offset_cursor, 3),
                            duration_ms=span.duration_ms,
                            status=span.status,
                            metadata=span.metadata,
                        )
                        offset_cursor += span.duration_ms

            if root_src is None:
                root_src = hits[0]["_source"]

            # Find the primary request span (the one with http.status_code).
            # http.request root spans are not exported, so the request-level span
            # is typically mcp.tools.call, proxy.dynamic, or mcp.tools.list.
            _REQUEST_SPAN_NAMES = {
                "mcp.tools.call",
                "mcp.tools.list",
                "proxy.dynamic",
                "http.request",
            }
            primary_src = root_src
            for hit in hits:
                src = hit["_source"]
                if src.get("name") in _REQUEST_SPAN_NAMES:
                    primary_src = src
                    break
                # Fallback: any span with http.status_code
                if src.get("span.attributes.http@status_code") is not None:
                    primary_src = src

            # Duration: use primary span duration (actual request time)
            trace_dur_nanos = int(primary_src.get("durationInNanos", 0))
            if trace_dur_nanos == 0:
                tgf = root_src.get("traceGroupFields", {}) or {}
                trace_dur_nanos = int(tgf.get("durationInNanos", 0) or 0)
            total_ms = round(trace_dur_nanos / 1_000_000, 3)

            # Real HTTP status code from primary span
            http_code_raw = primary_src.get("span.attributes.http@status_code")
            if http_code_raw is not None:
                http_code = int(http_code_raw)
                tx_status = _status_from_code(http_code)
            else:
                otel_code = int(primary_src.get("status.code", 0) or 0)
                tx_status = "error" if otel_code == 2 else "success"
                http_code = 500 if tx_status == "error" else 200

            path = http_route or primary_src.get("name", root_src.get("name", ""))

            error_msg = None
            if tx_status == "error":
                error_msg = _status_text(http_code)

            # Build request/response headers from available span attributes
            req_headers: dict[str, str] = {}
            res_headers: dict[str, str] = {}
            for hit in hits:
                src = hit["_source"]
                if src.get("span.attributes.http@method"):
                    req_headers.setdefault("method", str(src["span.attributes.http@method"]))
                if src.get("span.attributes.http@route"):
                    req_headers.setdefault("path", str(src["span.attributes.http@route"]))
                if src.get("span.attributes.http@url"):
                    req_headers.setdefault("upstream-url", str(src["span.attributes.http@url"]))
                if src.get("span.attributes.http@client_ip"):
                    req_headers.setdefault("x-forwarded-for", str(src["span.attributes.http@client_ip"]))
                if src.get("span.attributes.net@peer@ip"):
                    req_headers.setdefault("x-real-ip", str(src["span.attributes.net@peer@ip"]))
                if src.get("span.attributes.stoa@deployment_mode"):
                    res_headers.setdefault("x-stoa-mode", str(src["span.attributes.stoa@deployment_mode"]))
                if src.get("span.attributes.tenant_id"):
                    req_headers.setdefault("x-tenant-id", str(src["span.attributes.tenant_id"]))

            # Add trace context
            req_headers["x-trace-id"] = trace_id
            res_version = primary_src.get("resource.attributes.service@version")
            if res_version:
                res_headers["x-stoa-version"] = str(res_version)

            # Prefer tool_name from span attributes for api_name (CAB-1997)
            detail_tool_name = None
            for hit in hits:
                src = hit["_source"]
                detail_tool_name = src.get("span.attributes.tool_name") or src.get("span.attributes.tool")
                if detail_tool_name:
                    break
            detail_api_name = detail_tool_name or _extract_api_name(path)

            return APITransaction(
                id=trace_id,
                trace_id=trace_id,
                api_name=detail_api_name,
                tenant_id=primary_src.get("span.attributes.tenant_id"),
                method=http_method,
                path=path,
                status_code=http_code,
                status=tx_status,
                status_text=_status_text(http_code),
                error_source=_error_source(path, http_code) if http_code >= 400 else None,
                client_ip=primary_src.get("span.attributes.http@client_ip"),
                user_id=primary_src.get("span.attributes.user_id"),
                started_at=primary_src.get("startTime", ""),
                total_duration_ms=total_ms,
                spans=spans,
                request_headers=req_headers or None,
                response_headers=res_headers or None,
                error_message=error_msg,
            )

        except Exception:
            logger.exception("Failed to get transaction from otel spans")
            return None

    async def get_transaction_stats_from_spans(
        self,
        time_range_minutes: int = 60,
    ) -> APITransactionStats | None:
        """Get aggregated transaction statistics from OTel span index."""
        try:
            body = {
                "size": 0,
                "query": {
                    "bool": {
                        "filter": [
                            {"range": {"startTime": {"gte": f"now-{time_range_minutes}m"}}},
                            {
                                "terms": {
                                    "name": [
                                        "mcp.tools.call",
                                        "mcp.tools.list",
                                        "proxy.dynamic",
                                        "http.request",
                                    ]
                                }
                            },
                        ]
                    }
                },
                "aggs": {
                    "success_count": {
                        "filter": {
                            "bool": {"must_not": [{"range": {"span.attributes.http@status_code": {"gte": 400}}}]}
                        }
                    },
                    "error_count": {"filter": {"range": {"span.attributes.http@status_code": {"gte": 400}}}},
                    "timeout_count": {"filter": {"term": {"span.attributes.http@status_code": 504}}},
                    "latency_stats": {"stats": {"field": "durationInNanos"}},
                    "latency_percentiles": {
                        "percentiles": {
                            "field": "durationInNanos",
                            "percents": [95, 99],
                        }
                    },
                    "by_tool": {
                        "terms": {
                            "field": "span.attributes.tool_name",
                            "missing": "unknown",
                            "size": 20,
                        },
                        "aggs": {
                            "avg_latency": {"avg": {"field": "durationInNanos"}},
                            "errors": {"filter": {"range": {"span.attributes.http@status_code": {"gte": 400}}}},
                        },
                    },
                    "by_span_name": {
                        "terms": {"field": "name", "size": 10},
                        "aggs": {
                            "avg_latency": {"avg": {"field": "durationInNanos"}},
                            "errors": {"filter": {"range": {"span.attributes.http@status_code": {"gte": 400}}}},
                        },
                    },
                    "by_status_code": {"terms": {"field": "span.attributes.http@status_code", "size": 20}},
                    "by_auth_type": {
                        "terms": {"field": "span.attributes.auth_type", "size": 10},
                        "aggs": {
                            "avg_latency": {"avg": {"field": "durationInNanos"}},
                            "errors": {"filter": {"range": {"span.attributes.http@status_code": {"gte": 400}}}},
                        },
                    },
                    "by_deployment_mode": {
                        "terms": {"field": "resource.attributes.stoa@deployment_mode", "size": 10},
                        "aggs": {
                            "avg_latency": {"avg": {"field": "durationInNanos"}},
                            "errors": {"filter": {"range": {"span.attributes.http@status_code": {"gte": 400}}}},
                        },
                    },
                },
            }

            resp = await self.client.search(index="otel-v1-apm-span-*", body=body)
            total = resp["hits"]["total"]["value"]
            aggs = resp["aggregations"]

            # Convert nanos to ms for percentiles and averages
            nanos_to_ms = 1_000_000
            percentiles = aggs["latency_percentiles"]["values"]
            avg_nanos = aggs["latency_stats"]["avg"] or 0

            # Build by_api dict — tool_name for MCP, span name for proxy
            by_api: dict = {}
            for bucket in aggs["by_tool"]["buckets"]:
                name = bucket["key"]
                if name == "unknown":
                    continue  # Skip unknown tools, use span name instead
                avg_lat = (bucket["avg_latency"]["value"] or 0) / nanos_to_ms
                by_api[name] = {
                    "total": bucket["doc_count"],
                    "errors": bucket["errors"]["doc_count"],
                    "success": bucket["doc_count"] - bucket["errors"]["doc_count"],
                    "avg_latency_ms": round(avg_lat, 1),
                }
            # Add span name breakdown for non-tool spans (proxy.dynamic, mcp.tools.list)
            for bucket in aggs["by_span_name"]["buckets"]:
                name = bucket["key"]
                if name in by_api:
                    continue  # Already covered by tool_name
                avg_lat = (bucket["avg_latency"]["value"] or 0) / nanos_to_ms
                by_api[name] = {
                    "total": bucket["doc_count"],
                    "errors": bucket["errors"]["doc_count"],
                    "success": bucket["doc_count"] - bucket["errors"]["doc_count"],
                    "avg_latency_ms": round(avg_lat, 1),
                }

            # Build by_status_code dict
            by_status_code: dict = {}
            for bucket in aggs["by_status_code"]["buckets"]:
                by_status_code[bucket["key"]] = bucket["doc_count"]

            # Build by_auth_type dict
            by_auth_type: dict = {}
            for bucket in aggs.get("by_auth_type", {}).get("buckets", []):
                avg_lat = (bucket["avg_latency"]["value"] or 0) / nanos_to_ms
                by_auth_type[bucket["key"]] = {
                    "total": bucket["doc_count"],
                    "errors": bucket["errors"]["doc_count"],
                    "success": bucket["doc_count"] - bucket["errors"]["doc_count"],
                    "avg_latency_ms": round(avg_lat, 1),
                }

            # Build by_deployment_mode dict
            by_deployment_mode: dict = {}
            for bucket in aggs.get("by_deployment_mode", {}).get("buckets", []):
                avg_lat = (bucket["avg_latency"]["value"] or 0) / nanos_to_ms
                by_deployment_mode[bucket["key"]] = {
                    "total": bucket["doc_count"],
                    "errors": bucket["errors"]["doc_count"],
                    "success": bucket["doc_count"] - bucket["errors"]["doc_count"],
                    "avg_latency_ms": round(avg_lat, 1),
                }

            return APITransactionStats(
                total_requests=total,
                success_count=aggs["success_count"]["doc_count"],
                error_count=aggs["error_count"]["doc_count"],
                timeout_count=aggs["timeout_count"]["doc_count"],
                avg_latency_ms=round(avg_nanos / nanos_to_ms, 2),
                p95_latency_ms=round((percentiles.get("95.0", 0) or 0) / nanos_to_ms, 2),
                p99_latency_ms=round((percentiles.get("99.0", 0) or 0) / nanos_to_ms, 2),
                requests_per_minute=round(total / max(time_range_minutes, 1), 2),
                by_api=by_api,
                by_status_code=by_status_code,
                by_auth_type=by_auth_type,
                by_deployment_mode=by_deployment_mode,
            )

        except Exception:
            logger.exception("Failed to get transaction stats from otel spans")
            return None

    # =========================================================================
    # AUDIT INDEX QUERIES (legacy audit-* index)
    # =========================================================================

    async def list_transactions(
        self,
        tenant_id: str | None,
        limit: int = 50,
        api_name: str | None = None,
        status: str | None = None,
        time_range_minutes: int = 60,
    ) -> list[APITransactionSummary] | None:
        """List recent transactions from audit index."""
        try:
            filters: list[dict] = [
                {"range": {"@timestamp": {"gte": f"now-{time_range_minutes}m"}}},
            ]
            if tenant_id:
                filters.append({"term": {"tenant_id.keyword": tenant_id}})
            if api_name:
                filters.append({"wildcard": {"request.path": f"*/{api_name}/*"}})
            if status:
                if status == "timeout":
                    filters.append({"term": {"response.status_code": 504}})
                elif status == "error":
                    filters.append({"range": {"response.status_code": {"gte": 400, "lt": 504}}})
                elif status == "success":
                    filters.append({"range": {"response.status_code": {"lt": 400}}})

            body = {
                "query": {"bool": {"filter": filters}},
                "sort": [{"@timestamp": {"order": "desc"}}],
                "size": limit,
            }

            resp = await self.client.search(index="audit*", body=body)
            hits = resp.get("hits", {}).get("hits", [])

            transactions = []
            for hit in hits:
                src = hit["_source"]
                req = src.get("request", {})
                res = src.get("response", {})
                code = res.get("status_code", 0)
                path = req.get("path", "")

                # Count gateway spans from Server-Timing data (CAB-1790)
                gateway_timings = res.get("gateway_timings", {})
                spans_count = len(gateway_timings) if gateway_timings else 1

                transactions.append(
                    APITransactionSummary(
                        id=src.get("event_id", hit["_id"]),
                        trace_id=src.get("correlation_id", ""),
                        api_name=_extract_api_name(path),
                        method=req.get("method", "GET"),
                        path=path,
                        status_code=code,
                        status=_status_from_code(code),
                        status_text=_status_text(code),
                        error_source=_error_source(path, code),
                        started_at=src.get("@timestamp", ""),
                        total_duration_ms=int(res.get("latency_ms", 0)),
                        spans_count=spans_count,
                    )
                )
            return transactions

        except Exception:
            logger.exception("Failed to list transactions from OpenSearch")
            return None

    async def get_transaction_stats(
        self,
        tenant_id: str | None,
        time_range_minutes: int = 60,
    ) -> APITransactionStats | None:
        """Get aggregated transaction statistics from audit index."""
        try:
            stat_filters: list[dict] = [
                {"range": {"@timestamp": {"gte": f"now-{time_range_minutes}m"}}},
            ]
            if tenant_id:
                stat_filters.append({"term": {"tenant_id.keyword": tenant_id}})
            body = {
                "size": 0,
                "query": {"bool": {"filter": stat_filters}},
                "aggs": {
                    "success_count": {"filter": {"range": {"response.status_code": {"lt": 400}}}},
                    "error_count": {
                        "filter": {
                            "bool": {
                                "filter": [
                                    {"range": {"response.status_code": {"gte": 400}}},
                                    {"range": {"response.status_code": {"lt": 504}}},
                                ]
                            }
                        }
                    },
                    "timeout_count": {"filter": {"term": {"response.status_code": 504}}},
                    "latency_stats": {"stats": {"field": "response.latency_ms"}},
                    "latency_percentiles": {
                        "percentiles": {
                            "field": "response.latency_ms",
                            "percents": [95, 99],
                        }
                    },
                    "by_api": {
                        "terms": {"field": "request.path", "size": 20},
                        "aggs": {
                            "avg_latency": {"avg": {"field": "response.latency_ms"}},
                            "errors": {"filter": {"range": {"response.status_code": {"gte": 400}}}},
                        },
                    },
                    "by_status_code": {"terms": {"field": "response.status_code", "size": 20}},
                },
            }

            resp = await self.client.search(index="audit*", body=body)
            total = resp["hits"]["total"]["value"]
            aggs = resp["aggregations"]

            percentiles = aggs["latency_percentiles"]["values"]

            # Build by_api dict
            by_api: dict = {}
            for bucket in aggs["by_api"]["buckets"]:
                name = _extract_api_name(bucket["key"])
                entry = by_api.get(name, {"total": 0, "success": 0, "errors": 0, "avg_latency_ms": 0})
                entry["total"] += bucket["doc_count"]
                entry["errors"] += bucket["errors"]["doc_count"]
                entry["success"] = entry["total"] - entry["errors"]
                entry["avg_latency_ms"] = round(bucket["avg_latency"]["value"] or 0, 1)
                by_api[name] = entry

            # Build by_status_code dict
            by_status_code: dict = {}
            for bucket in aggs["by_status_code"]["buckets"]:
                by_status_code[bucket["key"]] = bucket["doc_count"]

            return APITransactionStats(
                total_requests=total,
                success_count=aggs["success_count"]["doc_count"],
                error_count=aggs["error_count"]["doc_count"],
                timeout_count=aggs["timeout_count"]["doc_count"],
                avg_latency_ms=round(aggs["latency_stats"]["avg"] or 0, 2),
                p95_latency_ms=round(percentiles.get("95.0", 0), 2),
                p99_latency_ms=round(percentiles.get("99.0", 0), 2),
                requests_per_minute=round(total / max(time_range_minutes, 1), 2),
                by_api=by_api,
                by_status_code=by_status_code,
            )

        except Exception:
            logger.exception("Failed to get transaction stats from OpenSearch")
            return None

    async def get_transaction(
        self,
        event_id: str,
        tenant_id: str | None,
    ) -> APITransaction | None:
        """Get detailed transaction by event_id or OpenSearch _id."""
        try:
            tenant_filter: list[dict] = [{"term": {"tenant_id.keyword": tenant_id}}] if tenant_id else []

            # Try event_id.keyword first (event_id is mapped as text, term needs keyword subfield)
            body = {
                "query": {"bool": {"filter": [{"term": {"event_id.keyword": event_id}}, *tenant_filter]}},
                "size": 1,
            }
            resp = await self.client.search(index="audit*", body=body)
            hits = resp.get("hits", {}).get("hits", [])

            # Fallback: try OpenSearch _id (used when event_id field is absent)
            if not hits:
                body = {
                    "query": {"bool": {"filter": [{"ids": {"values": [event_id]}}, *tenant_filter]}},
                    "size": 1,
                }
                resp = await self.client.search(index="audit*", body=body)
                hits = resp.get("hits", {}).get("hits", [])

            if not hits:
                return None

            src = hits[0]["_source"]
            req = src.get("request", {})
            res = src.get("response", {})
            actor = src.get("actor", {})
            code = res.get("status_code", 0)
            latency = int(res.get("latency_ms", 0))
            path = req.get("path", "")

            # Build spans from gateway Server-Timing data (CAB-1790)
            gateway_timings = res.get("gateway_timings", {})
            spans = _build_spans_from_timings(gateway_timings, latency, code, path)

            error_msg = None
            if code >= 400:
                detail_error = src.get("details", {}).get("error")
                error_msg = f"{_status_text(code)}: {detail_error}" if detail_error else _status_text(code)

            return APITransaction(
                id=src.get("event_id", hits[0]["_id"]),
                trace_id=src.get("correlation_id", ""),
                api_name=_extract_api_name(path),
                tenant_id=src.get("tenant_id", tenant_id),
                method=req.get("method", "GET"),
                path=path,
                status_code=code,
                status=_status_from_code(code),
                status_text=_status_text(code),
                error_source=_error_source(path, code),
                client_ip=actor.get("ip_address"),
                user_id=actor.get("id"),
                started_at=src.get("@timestamp", ""),
                total_duration_ms=latency,
                spans=spans,
                error_message=error_msg,
            )

        except Exception:
            logger.exception("Failed to get transaction detail from OpenSearch")
            return None
