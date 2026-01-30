# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Response Transformer Middleware (CAB-881 — Step 2/4).

Intercepts MCP tool responses and applies field selection, truncation,
and pagination to reduce token consumption.

Pipeline position:
  Request → ... → ResponseTransformer → TokenCounter → ...
  (Transformer runs BEFORE TokenCounter so counts reflect transformed payload)

Audit: SHA-256 hash of original payload logged for traceability.
"""

import hashlib
import json
from typing import Any, Callable

import structlog
from fastapi import Request, Response
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import get_settings
from ..transformer.capper import CapEngine, CapResult
from ..transformer.config import TransformConfig
from ..transformer.engine import TransformEngine
from ..transformer.registry import get_adapter, get_config_for_tool

logger = structlog.get_logger(__name__)

settings = get_settings()
prefix = settings.metrics_prefix

# =============================================================================
# Prometheus Metrics
# =============================================================================

TRANSFORMER_REDUCTION_RATIO = Histogram(
    f"{prefix}_transformer_reduction_ratio",
    "Payload reduction ratio after transformation (0.0 = no reduction, 1.0 = 100% reduced)",
    ["tool_name"],
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

TRANSFORMER_APPLIED_TOTAL = Counter(
    f"{prefix}_transformer_applied_total",
    "Total transformations applied",
    ["tool_name", "result"],  # result: "transformed", "passthrough", "error"
)

RESPONSE_CAPPED_TOTAL = Counter(
    f"{prefix}_response_capped_total",
    "Total responses capped by token limit (CAB-874)",
    ["tool_name"],
)


# =============================================================================
# Helpers
# =============================================================================

def _extract_tool_name_from_path(path: str) -> str | None:
    """Extract tool name from REST path /tools/{name}."""
    parts = path.rstrip("/").split("/")
    if len(parts) >= 2 and parts[-2] == "tools":
        return parts[-1]
    return None


def _hash_payload(payload: bytes) -> str:
    """SHA-256 hash of original payload for audit trail."""
    return hashlib.sha256(payload).hexdigest()


def _extract_tenant_id(request: Request) -> str:
    """Extract tenant_id from request."""
    tenant = request.headers.get("X-Tenant-ID", "")
    if tenant:
        return tenant
    if hasattr(request.state, "user") and request.state.user:
        return getattr(request.state.user, "tenant_id", "unknown")
    return "unknown"


# =============================================================================
# Middleware
# =============================================================================

class ResponseTransformerMiddleware(BaseHTTPMiddleware):
    """Middleware that transforms MCP tool responses to reduce payload size.

    Only processes:
    - POST /tools/{name} responses (REST tool calls)
    - Responses with JSON content type
    - Successful responses (2xx)
    """

    MONITORED_PREFIXES = ("/tools/",)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        path = request.url.path

        # Only intercept tool call responses
        if not any(path.startswith(p) for p in self.MONITORED_PREFIXES):
            return await call_next(request)

        # Only transform POST responses (tool invocations)
        if request.method != "POST":
            return await call_next(request)

        tool_name = _extract_tool_name_from_path(path) or "unknown"

        # Get transform config (tenant-specific or default)
        config = get_config_for_tool(tool_name)
        if config is None or not config.enabled:
            TRANSFORMER_APPLIED_TOTAL.labels(
                tool_name=tool_name, result="passthrough"
            ).inc()
            return await call_next(request)

        # Execute downstream
        response = await call_next(request)

        # Only transform successful JSON responses
        content_type = response.headers.get("content-type", "")
        if response.status_code >= 300 or "json" not in content_type:
            TRANSFORMER_APPLIED_TOTAL.labels(
                tool_name=tool_name, result="passthrough"
            ).inc()
            return response

        # Read response body
        original_body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                original_body += chunk.encode("utf-8")
            else:
                original_body += chunk

        # Audit: hash original payload
        original_hash = _hash_payload(original_body)
        original_size = len(original_body)

        try:
            payload = json.loads(original_body)
        except (json.JSONDecodeError, ValueError):
            TRANSFORMER_APPLIED_TOTAL.labels(
                tool_name=tool_name, result="passthrough"
            ).inc()
            return Response(
                content=original_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # Apply transformation
        try:
            # Transform the response content
            transformed = self._transform_response(payload, tool_name, config)

            # CAB-874: Apply token capping after transformation
            cap_result = self._apply_capping(transformed, tool_name, config)
            if cap_result.was_capped:
                transformed = cap_result.payload
                RESPONSE_CAPPED_TOTAL.labels(tool_name=tool_name).inc()

            transformed_body = json.dumps(transformed, separators=(",", ":")).encode("utf-8")
            transformed_size = len(transformed_body)

            # Calculate reduction ratio
            if original_size > 0:
                ratio = 1.0 - (transformed_size / original_size)
            else:
                ratio = 0.0

            TRANSFORMER_REDUCTION_RATIO.labels(tool_name=tool_name).observe(ratio)
            TRANSFORMER_APPLIED_TOTAL.labels(
                tool_name=tool_name, result="transformed"
            ).inc()

            logger.info(
                "response_transformed",
                tool_name=tool_name,
                original_hash=original_hash,
                original_size=original_size,
                transformed_size=transformed_size,
                reduction_pct=f"{ratio * 100:.1f}%",
                capped=cap_result.was_capped,
                tenant_hash=hashlib.sha256(
                    _extract_tenant_id(request).encode()
                ).hexdigest()[:12],
            )

            headers_dict = dict(response.headers)
            if cap_result.was_capped:
                headers_dict["X-Stoa-Truncated"] = "true"
                headers_dict["X-Stoa-Original-Tokens"] = str(cap_result.original_tokens)

            return Response(
                content=transformed_body,
                status_code=response.status_code,
                headers=headers_dict,
                media_type="application/json",
            )

        except Exception:
            logger.exception(
                "response_transform_error",
                tool_name=tool_name,
                original_hash=original_hash,
            )
            TRANSFORMER_APPLIED_TOTAL.labels(
                tool_name=tool_name, result="error"
            ).inc()
            # On error, return original untransformed response
            return Response(
                content=original_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

    def _transform_response(
        self,
        payload: Any,
        tool_name: str,
        config: TransformConfig,
    ) -> Any:
        """Apply transformation to the MCP response payload.

        MCP tool responses have the shape:
        { "content": [{"type": "text", "text": "..."}], "isError": false }

        We transform the JSON inside content[].text.
        """
        # Handle MCP response envelope
        if isinstance(payload, dict) and "content" in payload:
            content = payload.get("content", [])
            if isinstance(content, list):
                transformed_content = []
                for item in content:
                    if (isinstance(item, dict)
                            and item.get("type") == "text"
                            and isinstance(item.get("text"), str)):
                        try:
                            inner = json.loads(item["text"])
                            transformed_inner = TransformEngine.apply(inner, config)
                            transformed_content.append({
                                "type": "text",
                                "text": json.dumps(transformed_inner, separators=(",", ":")),
                            })
                        except (json.JSONDecodeError, ValueError):
                            # Not JSON text, pass through
                            transformed_content.append(item)
                    else:
                        transformed_content.append(item)
                return {**payload, "content": transformed_content}

        # Direct JSON response (non-MCP envelope)
        return TransformEngine.apply(payload, config)

    def _apply_capping(
        self,
        payload: Any,
        tool_name: str,
        config: TransformConfig,
    ) -> CapResult:
        """Apply token capping to transformed payload (CAB-874).

        Resolves max_tokens from per-tool config or global setting.
        Handles MCP envelope by capping inner content[].text JSON.
        """
        max_tokens = config.max_response_tokens or settings.max_response_tokens

        # Handle MCP envelope: cap inner JSON in content[].text
        if isinstance(payload, dict) and "content" in payload:
            content = payload.get("content", [])
            if isinstance(content, list):
                capped_content = []
                was_capped = False
                original_tokens = 0

                for item in content:
                    if (isinstance(item, dict)
                            and item.get("type") == "text"
                            and isinstance(item.get("text"), str)):
                        try:
                            inner = json.loads(item["text"])
                            result = CapEngine.cap_response(
                                inner, max_tokens, tool_name
                            )
                            was_capped = was_capped or result.was_capped
                            original_tokens = max(original_tokens, result.original_tokens)
                            capped_content.append({
                                "type": "text",
                                "text": json.dumps(
                                    result.payload, separators=(",", ":")
                                ),
                            })
                        except (json.JSONDecodeError, ValueError):
                            capped_content.append(item)
                    else:
                        capped_content.append(item)

                return CapResult(
                    payload={**payload, "content": capped_content},
                    was_capped=was_capped,
                    original_tokens=original_tokens,
                    final_tokens=max_tokens if was_capped else original_tokens,
                )

        # Direct JSON response (non-MCP envelope)
        return CapEngine.cap_response(payload, max_tokens, tool_name)
