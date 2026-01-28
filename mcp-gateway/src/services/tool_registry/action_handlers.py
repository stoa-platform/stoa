# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Action handlers mixin for core tools.

CAB-841: Extracted from tool_registry.py for modularity.
CAB-660: Real tool action handlers with fallback to stubs.
"""

from typing import TYPE_CHECKING, Any

import structlog

from ...models import (
    ToolResult,
    TextContent,
    ListToolsResponse,
    ListCategoriesResponse,
)
from ..tool_handlers import STOAToolHandlers

if TYPE_CHECKING:
    from . import ToolRegistry

logger = structlog.get_logger(__name__)


class ActionHandlersMixin:
    """Mixin providing action handlers for core tools.

    Requires LookupMixin to be in the inheritance chain for list_tools,
    list_categories, and _get_tool_schema methods.
    """

    # Type hints for methods from LookupMixin (resolved via MRO)
    # Note: Do NOT define stub methods here - they would shadow LookupMixin methods
    list_tools: Any
    list_categories: Any
    _get_tool_schema: Any

    async def _handle_catalog_action(
        self,
        action: str,
        arguments: dict[str, Any],
        user_claims: Any = None,
        handlers: STOAToolHandlers | None = None,
    ) -> ToolResult:
        """Handle stoa_catalog actions.

        CAB-660: Uses real database backend via STOAToolHandlers.
        Falls back to stub if handlers not initialized.
        """
        import json

        if handlers:
            try:
                result = await handlers.handle_catalog(action, arguments, user_claims)
                return ToolResult(content=[TextContent(text=json.dumps(result, default=str))])
            except Exception as e:
                logger.exception("Catalog handler error", error=str(e))
                return ToolResult(
                    content=[TextContent(text=f"Handler error: {str(e)}")],
                    is_error=True,
                )

        # Fallback stub
        if action == "categories":
            categories = self.list_categories()
            return ToolResult(content=[TextContent(text=str({
                "categories": [{"name": c.name, "count": c.count} for c in categories.categories],
            }))])

        return ToolResult(content=[TextContent(text=str({
            "action": action,
            "arguments": arguments,
            "message": "Database handlers not initialized - stub response",
        }))])

    async def _handle_api_spec_action(
        self,
        action: str,
        arguments: dict[str, Any],
        user_claims: Any = None,
        handlers: STOAToolHandlers | None = None,
    ) -> ToolResult:
        """Handle stoa_api_spec actions.

        CAB-660: Uses real database backend via STOAToolHandlers.
        """
        import json

        if handlers:
            try:
                result = await handlers.handle_api_spec(action, arguments, user_claims)
                return ToolResult(content=[TextContent(text=json.dumps(result, default=str))])
            except Exception as e:
                logger.exception("API spec handler error", error=str(e))
                return ToolResult(
                    content=[TextContent(text=f"Handler error: {str(e)}")],
                    is_error=True,
                )

        # Fallback stub
        return ToolResult(content=[TextContent(text=str({
            "action": action,
            "api_id": arguments.get("api_id"),
            "message": "Database handlers not initialized - stub response",
        }))])

    async def _handle_subscription_action(
        self,
        action: str,
        arguments: dict[str, Any],
        user_claims: Any = None,
        handlers: STOAToolHandlers | None = None,
    ) -> ToolResult:
        """Handle stoa_subscription actions.

        CAB-660: Uses real database backend via STOAToolHandlers.
        """
        import json

        if handlers:
            try:
                result = await handlers.handle_subscription(action, arguments, user_claims)
                return ToolResult(content=[TextContent(text=json.dumps(result, default=str))])
            except Exception as e:
                logger.exception("Subscription handler error", error=str(e))
                return ToolResult(
                    content=[TextContent(text=f"Handler error: {str(e)}")],
                    is_error=True,
                )

        # Fallback stub
        return ToolResult(content=[TextContent(text=str({
            "action": action,
            "arguments": arguments,
            "message": "Database handlers not initialized - stub response",
        }))])

    async def _handle_metrics_action(
        self,
        action: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Handle stoa_metrics actions."""
        time_range = arguments.get("time_range", "24h")

        if action == "usage":
            return ToolResult(content=[TextContent(text=str({
                "api_id": arguments.get("api_id"),
                "subscription_id": arguments.get("subscription_id"),
                "time_range": time_range,
                "requests": 0,
                "data_volume_bytes": 0,
                "message": "Usage metrics - coming soon",
            }))])
        elif action == "latency":
            api_id = arguments.get("api_id")
            if not api_id:
                return ToolResult(
                    content=[TextContent(text="api_id is required for latency metrics")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "api_id": api_id,
                "endpoint": arguments.get("endpoint"),
                "time_range": time_range,
                "p50_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
                "message": "Latency metrics - coming soon",
            }))])
        elif action == "errors":
            api_id = arguments.get("api_id")
            if not api_id:
                return ToolResult(
                    content=[TextContent(text="api_id is required for error metrics")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "api_id": api_id,
                "time_range": time_range,
                "error_rate": 0,
                "errors_by_code": {},
                "message": "Error metrics - coming soon",
            }))])
        elif action == "quota":
            subscription_id = arguments.get("subscription_id")
            if not subscription_id:
                return ToolResult(
                    content=[TextContent(text="subscription_id is required for quota")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "subscription_id": subscription_id,
                "used": 0,
                "limit": 0,
                "percentage": 0,
                "message": "Quota usage - coming soon",
            }))])
        else:
            return ToolResult(
                content=[TextContent(text=f"Unknown action: {action}")],
                is_error=True,
            )

    async def _handle_logs_action(
        self,
        action: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Handle stoa_logs actions."""
        if action == "search":
            return ToolResult(content=[TextContent(text=str({
                "api_id": arguments.get("api_id"),
                "query": arguments.get("query"),
                "level": arguments.get("level"),
                "time_range": arguments.get("time_range", "24h"),
                "logs": [],
                "total": 0,
                "message": "Log search - coming soon",
            }))])
        elif action == "recent":
            return ToolResult(content=[TextContent(text=str({
                "api_id": arguments.get("api_id"),
                "subscription_id": arguments.get("subscription_id"),
                "limit": arguments.get("limit", 50),
                "logs": [],
                "message": "Recent logs - coming soon",
            }))])
        else:
            return ToolResult(
                content=[TextContent(text=f"Unknown action: {action}")],
                is_error=True,
            )

    async def _handle_alerts_action(
        self,
        action: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Handle stoa_alerts actions."""
        if action == "list":
            return ToolResult(content=[TextContent(text=str({
                "api_id": arguments.get("api_id"),
                "severity": arguments.get("severity"),
                "status": arguments.get("status", "active"),
                "alerts": [],
                "total": 0,
                "message": "Alert listing - coming soon",
            }))])
        elif action == "acknowledge":
            alert_id = arguments.get("alert_id")
            if not alert_id:
                return ToolResult(
                    content=[TextContent(text="alert_id is required")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "alert_id": alert_id,
                "comment": arguments.get("comment"),
                "acknowledged": True,
                "message": "Alert acknowledged - coming soon",
            }))])
        else:
            return ToolResult(
                content=[TextContent(text=f"Unknown action: {action}")],
                is_error=True,
            )

    async def _handle_tools_action(
        self,
        action: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Handle stoa_tools actions."""
        if action == "list":
            category = arguments.get("category")
            tag = arguments.get("tag")
            include_proxied = arguments.get("include_proxied", True)
            tools_response = self.list_tools(
                category=category,
                tag=tag,
                include_proxied=include_proxied,
            )
            return ToolResult(content=[TextContent(text=str({
                "tools": [{"name": t.name, "description": t.description, "category": t.category} for t in tools_response.tools],
                "total": tools_response.total_count,
            }))])
        elif action == "schema":
            tool_name = arguments.get("tool_name")
            if not tool_name:
                return ToolResult(
                    content=[TextContent(text="tool_name is required")],
                    is_error=True,
                )
            schema_info = self._get_tool_schema(tool_name)
            if schema_info is None:
                return ToolResult(
                    content=[TextContent(text=f"Tool not found: {tool_name}")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str(schema_info))])
        elif action == "search":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 20)
            tools_response = self.list_tools(search=query, limit=limit)
            return ToolResult(content=[TextContent(text=str({
                "query": query,
                "results": [{"name": t.name, "description": t.description} for t in tools_response.tools],
                "total": tools_response.total_count,
            }))])
        else:
            return ToolResult(
                content=[TextContent(text=f"Unknown action: {action}")],
                is_error=True,
            )

    async def _handle_uac_action(
        self,
        action: str,
        arguments: dict[str, Any],
        user_claims: Any = None,
        handlers: STOAToolHandlers | None = None,
    ) -> ToolResult:
        """Handle stoa_uac actions.

        CAB-660: Uses real database backend via STOAToolHandlers.
        """
        import json

        if handlers:
            try:
                result = await handlers.handle_uac(action, arguments, user_claims)
                return ToolResult(content=[TextContent(text=json.dumps(result, default=str))])
            except Exception as e:
                logger.exception("UAC handler error", error=str(e))
                return ToolResult(
                    content=[TextContent(text=f"Handler error: {str(e)}")],
                    is_error=True,
                )

        # Fallback stub
        return ToolResult(content=[TextContent(text=str({
            "action": action,
            "arguments": arguments,
            "message": "Database handlers not initialized - stub response",
        }))])

    async def _handle_security_action(
        self,
        action: str,
        arguments: dict[str, Any],
        user_claims: Any = None,
        handlers: STOAToolHandlers | None = None,
    ) -> ToolResult:
        """Handle stoa_security actions.

        CAB-660: Uses real database backend via STOAToolHandlers.
        """
        import json

        if handlers:
            try:
                result = await handlers.handle_security(action, arguments, user_claims)
                return ToolResult(content=[TextContent(text=json.dumps(result, default=str))])
            except Exception as e:
                logger.exception("Security handler error", error=str(e))
                return ToolResult(
                    content=[TextContent(text=f"Handler error: {str(e)}")],
                    is_error=True,
                )

        # Fallback stub
        return ToolResult(content=[TextContent(text=str({
            "action": action,
            "arguments": arguments,
            "message": "Database handlers not initialized - stub response",
        }))])

    async def _handle_tenants_action(
        self,
        arguments: dict[str, Any],
        user_claims: Any = None,
        handlers: STOAToolHandlers | None = None,
    ) -> ToolResult:
        """Handle stoa_tenants tool.

        CAB-660: Uses real database backend via STOAToolHandlers.
        """
        import json

        if handlers:
            try:
                result = await handlers.handle_tenants(arguments, user_claims)
                return ToolResult(content=[TextContent(text=json.dumps(result, default=str))])
            except Exception as e:
                logger.exception("Tenants handler error", error=str(e))
                return ToolResult(
                    content=[TextContent(text=f"Handler error: {str(e)}")],
                    is_error=True,
                )

        # Fallback stub
        return ToolResult(content=[TextContent(text=str({
            "tenants": [],
            "message": "Database handlers not initialized - stub response",
        }))])
