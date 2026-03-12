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


class MonitoringService:
    """Queries OpenSearch audit-* index for transaction analytics."""

    def __init__(self, client: AsyncOpenSearch):
        self.client = client

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
                filters.append({"term": {"tenant_id": tenant_id}})
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
                        spans_count=1,
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
                stat_filters.append({"term": {"tenant_id": tenant_id}})
            body = {
                "size": 0,
                "query": {
                    "bool": {
                        "filter": stat_filters
                    }
                },
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
            tenant_filter: list[dict] = (
                [{"term": {"tenant_id": tenant_id}}] if tenant_id else []
            )

            # Try event_id.keyword first (event_id is mapped as text, term needs keyword subfield)
            body = {
                "query": {
                    "bool": {
                        "filter": [{"term": {"event_id.keyword": event_id}}, *tenant_filter]
                    }
                },
                "size": 1,
            }
            resp = await self.client.search(index="audit*", body=body)
            hits = resp.get("hits", {}).get("hits", [])

            # Fallback: try OpenSearch _id (used when event_id field is absent)
            if not hits:
                body = {
                    "query": {
                        "bool": {
                            "filter": [{"ids": {"values": [event_id]}}, *tenant_filter]
                        }
                    },
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

            source = _error_source(path, code) or "control-plane-api"
            span = TransactionSpan(
                name="api_request",
                service=source if code >= 400 else "control-plane-api",
                start_offset_ms=0,
                duration_ms=latency,
                status=_status_from_code(code),
                metadata={"correlation_id": src.get("correlation_id", "")},
            )

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
                spans=[span],
                error_message=error_msg,
            )

        except Exception:
            logger.exception("Failed to get transaction detail from OpenSearch")
            return None
