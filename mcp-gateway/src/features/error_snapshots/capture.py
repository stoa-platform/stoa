"""
MCP Error Snapshot Capture Functions

Core capture logic for MCP Gateway errors.
"""

import asyncio
import time
from datetime import datetime
from typing import Any, Optional

import structlog
from fastapi import Request

from .config import get_mcp_snapshot_settings
from .models import (
    MCPErrorSnapshot,
    MCPErrorType,
    MCPServerContext,
    ToolInvocation,
    LLMContext,
    RetryContext,
    RequestContext,
    UserContext,
    estimate_llm_cost,
)
from .masking import mask_tool_params, mask_headers, mask_url, mask_error_message
from .publisher import get_snapshot_publisher

logger = structlog.get_logger(__name__)


async def capture_mcp_error(
    request: Request,
    response_status: int,
    error_type: MCPErrorType,
    error_message: str,
    *,
    mcp_server: Optional[MCPServerContext] = None,
    tool_invocation: Optional[ToolInvocation] = None,
    llm_context: Optional[LLMContext] = None,
    retry_context: Optional[RetryContext] = None,
    conversation_id: Optional[str] = None,
    message_index: Optional[int] = None,
    exception: Optional[Exception] = None,
) -> Optional[MCPErrorSnapshot]:
    """
    Capture an MCP error snapshot.

    This is the main entry point for capturing errors in the MCP Gateway.
    Should be called from middleware or exception handlers.
    """
    settings = get_mcp_snapshot_settings()

    if not settings.enabled:
        return None

    # Check if this path should be excluded
    path = request.url.path
    if any(path.startswith(exclude) for exclude in settings.exclude_paths):
        return None

    # Check if we should capture based on status code
    if response_status < 400:
        return None
    if 400 <= response_status < 500 and not settings.capture_on_4xx:
        return None
    if response_status >= 500 and not settings.capture_on_5xx:
        return None

    try:
        start_time = time.perf_counter()

        # Build request context
        request_context = await _build_request_context(request)

        # Build user context from request state
        user_context = _build_user_context(request)

        # Calculate costs
        total_cost = 0.0
        tokens_wasted = 0

        if llm_context:
            total_cost = llm_context.estimated_cost_usd
            tokens_wasted = llm_context.tokens_input + llm_context.tokens_output

        # Get trace context
        trace_id = request.headers.get("x-trace-id") or request.headers.get("traceparent", "").split("-")[1] if "-" in request.headers.get("traceparent", "") else None
        span_id = request.headers.get("x-span-id")

        # Collect masked fields
        masked_fields = []
        if request_context.headers:
            # Headers were already masked in _build_request_context
            masked_fields.extend([f"request.headers.{k}" for k in settings.sensitive_headers if k.lower() in [h.lower() for h in request_context.headers]])

        if tool_invocation and tool_invocation.input_params_masked:
            masked_fields.extend([f"tool_invocation.input_params.{k}" for k in tool_invocation.input_params_masked])

        # Create snapshot
        snapshot = MCPErrorSnapshot(
            timestamp=datetime.utcnow(),
            error_type=error_type,
            error_message=mask_error_message(error_message),
            request=request_context,
            response_status=response_status,
            user=user_context,
            mcp_server=mcp_server,
            tool_invocation=tool_invocation,
            llm_context=llm_context,
            retry_context=retry_context,
            conversation_id=conversation_id,
            message_index=message_index,
            total_cost_usd=total_cost,
            tokens_wasted=tokens_wasted,
            trace_id=trace_id,
            span_id=span_id,
            masked_fields=masked_fields,
            environment=_get_environment(),
        )

        # Publish to Kafka
        if settings.kafka_enabled:
            publisher = get_snapshot_publisher()
            if settings.async_capture:
                asyncio.create_task(_publish_safe(publisher, snapshot))
            else:
                await _publish_safe(publisher, snapshot)

        capture_duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "mcp_error_snapshot_captured",
            snapshot_id=snapshot.id,
            error_type=error_type.value,
            capture_duration_ms=capture_duration_ms,
        )

        return snapshot

    except Exception as e:
        logger.warning("mcp_error_snapshot_capture_failed", error=str(e))
        return None


async def capture_tool_error(
    tool_name: str,
    input_params: dict[str, Any],
    error: Exception,
    *,
    duration_ms: int = 0,
    backend_status: Optional[int] = None,
    backend_response: Optional[str] = None,
    request: Optional[Request] = None,
    mcp_server: Optional[MCPServerContext] = None,
    retry_context: Optional[RetryContext] = None,
) -> Optional[MCPErrorSnapshot]:
    """
    Capture an error from tool execution.

    Called from the tool registry when a tool invocation fails.
    """
    settings = get_mcp_snapshot_settings()

    if not settings.enabled or not settings.capture_tool_errors:
        return None

    try:
        # Mask tool parameters
        masked_params, masked_keys = mask_tool_params(input_params)

        # Determine error type
        error_type = _classify_tool_error(error, backend_status)

        # Build tool invocation context
        tool_invocation = ToolInvocation(
            tool_name=tool_name,
            input_params=masked_params,
            input_params_masked=masked_keys,
            started_at=datetime.utcnow(),
            duration_ms=duration_ms,
            error_type=type(error).__name__,
            error_message=mask_error_message(str(error)),
            error_retryable=_is_retryable_error(error, backend_status),
            backend_status_code=backend_status,
            backend_response_preview=backend_response[:settings.max_response_preview_length] if backend_response else None,
        )

        # If we have a request, use the full capture
        if request:
            return await capture_mcp_error(
                request=request,
                response_status=backend_status or 500,
                error_type=error_type,
                error_message=str(error),
                tool_invocation=tool_invocation,
                mcp_server=mcp_server,
                retry_context=retry_context,
                exception=error,
            )

        # Otherwise create a minimal snapshot
        snapshot = MCPErrorSnapshot(
            timestamp=datetime.utcnow(),
            error_type=error_type,
            error_message=mask_error_message(str(error)),
            request=RequestContext(method="POST", path=f"/mcp/v1/tools/{tool_name}/invoke"),
            response_status=backend_status or 500,
            tool_invocation=tool_invocation,
            mcp_server=mcp_server,
            retry_context=retry_context,
            masked_fields=[f"tool_invocation.input_params.{k}" for k in masked_keys],
            environment=_get_environment(),
        )

        # Publish
        if settings.kafka_enabled:
            publisher = get_snapshot_publisher()
            if settings.async_capture:
                asyncio.create_task(_publish_safe(publisher, snapshot))
            else:
                await _publish_safe(publisher, snapshot)

        logger.info(
            "mcp_tool_error_captured",
            snapshot_id=snapshot.id,
            tool_name=tool_name,
            error_type=error_type.value,
        )

        return snapshot

    except Exception as e:
        logger.warning("mcp_tool_error_capture_failed", error=str(e))
        return None


async def _build_request_context(request: Request) -> RequestContext:
    """Build request context with masking"""
    settings = get_mcp_snapshot_settings()

    # Get headers and mask sensitive ones
    headers_dict = dict(request.headers)
    masked_headers, _ = mask_headers(headers_dict)

    return RequestContext(
        method=request.method,
        path=request.url.path,
        query_params=dict(request.query_params),
        headers=masked_headers if settings.mask_headers else headers_dict,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def _build_user_context(request: Request) -> Optional[UserContext]:
    """Extract user context from request state"""
    # Check if we have token claims in request state (set by auth middleware)
    if not hasattr(request.state, "user") or request.state.user is None:
        return None

    user = request.state.user

    return UserContext(
        user_id=getattr(user, "sub", None) or getattr(user, "subject", None),
        tenant_id=getattr(user, "tenant_id", None),
        client_id=getattr(user, "client_id", None),
        roles=list(getattr(user, "roles", [])) if hasattr(user, "roles") else [],
        scopes=getattr(user, "scope", "").split() if hasattr(user, "scope") else [],
    )


def _classify_tool_error(error: Exception, status_code: Optional[int]) -> MCPErrorType:
    """Classify error into MCPErrorType"""
    error_name = type(error).__name__.lower()

    if "timeout" in error_name or "timedout" in str(error).lower():
        return MCPErrorType.TOOL_TIMEOUT

    if "notfound" in error_name or status_code == 404:
        return MCPErrorType.TOOL_NOT_FOUND

    if "validation" in error_name or status_code == 422:
        return MCPErrorType.TOOL_VALIDATION_ERROR

    if status_code == 429:
        return MCPErrorType.SERVER_RATE_LIMITED

    if status_code == 401 or status_code == 403:
        return MCPErrorType.SERVER_AUTH_FAILURE

    if status_code and status_code >= 500:
        return MCPErrorType.SERVER_INTERNAL_ERROR

    return MCPErrorType.TOOL_EXECUTION_ERROR


def _is_retryable_error(error: Exception, status_code: Optional[int]) -> bool:
    """Determine if an error is retryable"""
    # Rate limits are retryable
    if status_code == 429:
        return True

    # Server errors may be retryable
    if status_code and status_code >= 500 and status_code != 501:
        return True

    # Timeouts are retryable
    if "timeout" in type(error).__name__.lower():
        return True

    # Connection errors are retryable
    if "connection" in type(error).__name__.lower():
        return True

    return False


def _get_environment() -> str:
    """Get current environment"""
    import os
    return os.getenv("ENVIRONMENT", os.getenv("ENV", "production"))


async def _publish_safe(publisher, snapshot: MCPErrorSnapshot) -> None:
    """Safely publish snapshot, catching any errors"""
    try:
        await publisher.publish(snapshot)
    except Exception as e:
        logger.warning("mcp_snapshot_publish_failed", snapshot_id=snapshot.id, error=str(e))
