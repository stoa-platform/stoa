# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Invocation mixin providing the main invoke() entry point.

CAB-841: Extracted from tool_registry.py for modularity.
CAB-603: Routes invocation based on tool type.
CAB-605 Phase 3: Deprecation handling in invoke flow.
"""

import time
from typing import TYPE_CHECKING, Any

import structlog

from ...models import (
    Tool,
    CoreTool,
    ProxiedTool,
    ExternalTool,
    ToolType,
    ToolInvocation,
    ToolResult,
    TextContent,
)
from .exceptions import ToolNotFoundError
from .models import DeprecatedToolAlias

if TYPE_CHECKING:
    from . import ToolRegistry

logger = structlog.get_logger(__name__)


class InvocationMixin:
    """Mixin providing the main invoke() entry point.

    Requires DeprecationMixin, CoreRoutingMixin, ProxiedMixin, and LegacyMixin
    to be in the inheritance chain.
    """

    # Type hints for attributes from ToolRegistry
    _deprecated_aliases: dict[str, DeprecatedToolAlias]

    # Type hints for methods from other mixins (resolved via MRO)
    # Note: Do NOT define stub methods here - they would shadow the real implementations
    resolve_tool: Any
    _invoke_core_tool: Any
    _invoke_proxied_tool: Any
    _invoke_external_tool: Any
    _invoke_builtin: Any
    _invoke_api: Any

    async def invoke(
        self,
        invocation: ToolInvocation,
        user_token: str | None = None,
        tenant_id: str | None = None,
        user_claims: Any = None,  # CAB-660: TokenClaims for real handlers
    ) -> ToolResult:
        """Invoke a tool.

        CAB-603: Routes invocation based on tool type:
        - CoreTool: Internal handler execution
        - ProxiedTool: HTTP forwarding to backend API
        - Legacy Tool: Existing behavior

        Args:
            invocation: Tool invocation request
            user_token: Optional user JWT for backend authentication
            tenant_id: Optional tenant context for tool lookup
            user_claims: Optional TokenClaims for CAB-660 real handlers

        Returns:
            Tool execution result
        """
        start_time = time.time()
        is_deprecated = False
        deprecation_warning: str | None = None
        arguments = invocation.arguments

        # CAB-605 Phase 3: Use resolve_tool for deprecation handling
        try:
            tool, arguments, is_deprecated = self.resolve_tool(
                invocation.name,
                invocation.arguments,
                tenant_id,
            )
            if is_deprecated:
                alias = self._deprecated_aliases.get(invocation.name)
                if alias:
                    deprecation_warning = (
                        f"Tool '{invocation.name}' is deprecated and will be removed "
                        f"in {alias.days_until_removal()} days. Use '{alias.new_name}' instead."
                    )
        except ToolNotFoundError as e:
            return ToolResult(
                content=[TextContent(text=str(e))],
                is_error=True,
                request_id=invocation.request_id,
            )

        # CAB-603: Determine tool type for routing
        tool_type = tool.tool_type if hasattr(tool, 'tool_type') else ToolType.LEGACY

        logger.info(
            "Invoking tool",
            tool_name=tool.name,
            tool_type=tool_type.value if hasattr(tool_type, 'value') else str(tool_type),
            request_id=invocation.request_id,
            is_deprecated=is_deprecated,
            original_name=invocation.name if is_deprecated else None,
        )

        try:
            # CAB-603: Route by tool type
            if isinstance(tool, CoreTool):
                result = await self._invoke_core_tool(tool, arguments, user_claims)
            elif isinstance(tool, ExternalTool):
                result = await self._invoke_external_tool(tool, arguments, user_token)
            elif isinstance(tool, ProxiedTool):
                result = await self._invoke_proxied_tool(tool, arguments, user_token)
            # Legacy: Handle built-in tools (backward compatibility)
            elif tool.name.startswith("stoa_"):
                result = await self._invoke_builtin(tool, arguments)
            # Legacy: Handle API-backed tools
            elif hasattr(tool, 'endpoint') and tool.endpoint:
                result = await self._invoke_api(tool, arguments, user_token)
            else:
                result = ToolResult(
                    content=[TextContent(text=f"Tool {tool.name} has no backend configured")],
                    is_error=True,
                )

            # Add latency
            latency_ms = int((time.time() - start_time) * 1000)
            result.latency_ms = latency_ms
            result.request_id = invocation.request_id

            # CAB-605: Add deprecation warning to result metadata
            if is_deprecated and deprecation_warning:
                result.metadata = result.metadata or {}
                result.metadata["_deprecation_warning"] = deprecation_warning

            return result

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.exception("Tool invocation failed", tool_name=tool.name, error=str(e))

            # Capture error snapshot (Phase 3)
            try:
                from ...features.error_snapshots import capture_tool_error
                await capture_tool_error(
                    tool_name=tool.name,
                    input_params=invocation.arguments,
                    error=e,
                    duration_ms=latency_ms,
                )
            except Exception as snapshot_error:
                logger.warning("Failed to capture tool error snapshot", error=str(snapshot_error))

            return ToolResult(
                content=[TextContent(text=f"Tool invocation failed: {str(e)}")],
                is_error=True,
                request_id=invocation.request_id,
                latency_ms=latency_ms,
            )
