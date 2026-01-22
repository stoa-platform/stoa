"""Core tool routing mixin.

CAB-841: Extracted from tool_registry.py for modularity.
CAB-605 Phase 3: Routes to consolidated action-based tools.
CAB-660: Uses real PostgreSQL backend via STOAToolHandlers.
"""

from typing import TYPE_CHECKING, Any

import structlog

from ...config import get_settings
from ...models import (
    CoreTool,
    ToolResult,
    TextContent,
)
from ..tool_handlers import get_tool_handlers

if TYPE_CHECKING:
    from . import ToolRegistry

logger = structlog.get_logger(__name__)


class CoreRoutingMixin:
    """Mixin providing core tool routing logic.

    Requires ActionHandlersMixin and LegacyMixin to be in the inheritance chain.
    """

    # Type hints for attributes from ToolRegistry
    _core_tools: dict[str, CoreTool]
    _proxied_tools: dict
    _deprecated_aliases: dict

    # Type hints for methods from other mixins (resolved via MRO)
    # Note: Do NOT define stub methods here - they would shadow the real implementations
    _handle_catalog_action: Any
    _handle_api_spec_action: Any
    _handle_subscription_action: Any
    _handle_metrics_action: Any
    _handle_logs_action: Any
    _handle_alerts_action: Any
    _handle_tools_action: Any
    _handle_uac_action: Any
    _handle_security_action: Any
    _handle_tenants_action: Any
    _check_platform_health: Any

    async def _invoke_core_tool(
        self,
        tool: CoreTool,
        arguments: dict[str, Any],
        user_claims: Any = None,  # CAB-660: TokenClaims for real handlers
    ) -> ToolResult:
        """Invoke a core platform tool.

        CAB-605 Phase 3: Handles consolidated action-based tools and legacy tools.
        Action-based tools use the 'action' parameter to dispatch to specific handlers.

        CAB-660: Now uses real PostgreSQL backend via STOAToolHandlers.

        Args:
            tool: CoreTool instance
            arguments: Tool invocation arguments
            user_claims: Optional TokenClaims for authorization

        Returns:
            ToolResult with execution output
        """
        settings = get_settings()

        # =====================================================================
        # CAB-605 Phase 3: Consolidated Action-Based Tools
        # =====================================================================

        # CAB-660: Use real handlers if available
        handlers = get_tool_handlers()

        # stoa_catalog - API catalog operations
        if tool.name == "stoa_catalog":
            action = arguments.get("action")
            if not action:
                return ToolResult(
                    content=[TextContent(text="action is required (list, get, search, versions, categories)")],
                    is_error=True,
                )
            return await self._handle_catalog_action(action, arguments, user_claims, handlers)

        # stoa_api_spec - API specification retrieval
        elif tool.name == "stoa_api_spec":
            action = arguments.get("action")
            api_id = arguments.get("api_id")
            if not action or not api_id:
                return ToolResult(
                    content=[TextContent(text="action and api_id are required")],
                    is_error=True,
                )
            return await self._handle_api_spec_action(action, arguments, user_claims, handlers)

        # stoa_subscription - Subscription management
        elif tool.name == "stoa_subscription":
            action = arguments.get("action")
            if not action:
                return ToolResult(
                    content=[TextContent(text="action is required (list, get, create, cancel, credentials, rotate_key)")],
                    is_error=True,
                )
            return await self._handle_subscription_action(action, arguments, user_claims, handlers)

        # stoa_metrics - Metrics retrieval
        elif tool.name == "stoa_metrics":
            action = arguments.get("action")
            if not action:
                return ToolResult(
                    content=[TextContent(text="action is required (usage, latency, errors, quota)")],
                    is_error=True,
                )
            return await self._handle_metrics_action(action, arguments)

        # stoa_logs - Log search and retrieval
        elif tool.name == "stoa_logs":
            action = arguments.get("action")
            if not action:
                return ToolResult(
                    content=[TextContent(text="action is required (search, recent)")],
                    is_error=True,
                )
            return await self._handle_logs_action(action, arguments)

        # stoa_alerts - Alert management
        elif tool.name == "stoa_alerts":
            action = arguments.get("action")
            if not action:
                return ToolResult(
                    content=[TextContent(text="action is required (list, acknowledge)")],
                    is_error=True,
                )
            return await self._handle_alerts_action(action, arguments)

        # stoa_tools - Tool discovery
        elif tool.name == "stoa_tools":
            action = arguments.get("action")
            if not action:
                return ToolResult(
                    content=[TextContent(text="action is required (list, schema, search)")],
                    is_error=True,
                )
            return await self._handle_tools_action(action, arguments)

        # stoa_uac - UAC contract management
        elif tool.name == "stoa_uac":
            action = arguments.get("action")
            if not action:
                return ToolResult(
                    content=[TextContent(text="action is required (list, get, validate, sla)")],
                    is_error=True,
                )
            return await self._handle_uac_action(action, arguments, user_claims, handlers)

        # stoa_security - Security operations
        elif tool.name == "stoa_security":
            action = arguments.get("action")
            if not action:
                return ToolResult(
                    content=[TextContent(text="action is required (audit_log, check_permissions, list_policies)")],
                    is_error=True,
                )
            return await self._handle_security_action(action, arguments, user_claims, handlers)

        # =====================================================================
        # Standalone Platform Tools (not consolidated)
        # =====================================================================

        # stoa_platform_info
        elif tool.name == "stoa_platform_info":
            info = {
                "platform": "STOA",
                "version": settings.app_version,
                "environment": settings.environment,
                "base_domain": settings.base_domain,
                "core_tools_count": len(self._core_tools),
                "proxied_tools_count": len(self._proxied_tools),
                "deprecated_aliases_count": len(self._deprecated_aliases),
                "services": {
                    "api": f"https://api.{settings.base_domain}",
                    "gateway": f"https://gateway.{settings.base_domain}",
                    "auth": f"https://auth.{settings.base_domain}",
                    "mcp": f"https://mcp.{settings.base_domain}",
                },
            }
            return ToolResult(content=[TextContent(text=str(info))])

        # stoa_platform_health (CAB-658: Enhanced with latency tracking)
        elif tool.name == "stoa_platform_health":
            components = arguments.get("components", [])
            health_result = await self._check_platform_health(components, settings)
            return ToolResult(content=[TextContent(text=str(health_result))])

        # stoa_tenants (renamed from stoa_list_tenants)
        elif tool.name == "stoa_tenants":
            return await self._handle_tenants_action(arguments, user_claims, handlers)

        # =====================================================================
        # Legacy Tools (for deprecation period - handled via aliases)
        # =====================================================================

        # Default stub for unhandled tools
        else:
            return ToolResult(content=[TextContent(text=str({
                "tool": tool.name,
                "domain": tool.domain.value,
                "action": tool.action,
                "arguments": arguments,
                "status": "stub",
                "message": f"Core tool handler for {tool.name} - implementation pending",
            }))])
