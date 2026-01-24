"""Legacy invocation methods mixin.

CAB-841: Extracted from tool_registry.py for modularity.
Legacy methods for backward compatibility.
"""

import os
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from ...config import get_settings
from ...models import (
    Tool,
    ToolResult,
    TextContent,
)
from ..health import HealthChecker

if TYPE_CHECKING:
    from . import ToolRegistry

logger = structlog.get_logger(__name__)


class LegacyMixin:
    """Mixin providing legacy invocation methods for backward compatibility.

    Requires LookupMixin to be in the inheritance chain for _get_tools_info
    and _get_tool_schema methods.
    """

    # Type hints for attributes from ToolRegistry
    _http_client: httpx.AsyncClient | None
    _tools: dict[str, Tool]

    # Type hints for methods from LookupMixin (resolved via MRO)
    # Note: Do NOT define stub methods here - they would shadow LookupMixin methods
    _get_tools_info: Any
    _get_tool_schema: Any

    async def _invoke_builtin(
        self,
        tool: Tool,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Invoke a built-in platform tool (legacy).

        Deprecated: Use _invoke_core_tool for new CoreTool instances.
        """
        settings = get_settings()

        if tool.name == "stoa_platform_info":
            info = {
                "platform": "STOA",
                "version": settings.app_version,
                "environment": settings.environment,
                "base_domain": settings.base_domain,
                "services": {
                    "api": f"https://api.{settings.base_domain}",
                    "gateway": f"https://gateway.{settings.base_domain}",
                    "auth": f"https://auth.{settings.base_domain}",
                },
            }
            return ToolResult(
                content=[TextContent(text=str(info))],
            )

        elif tool.name == "stoa_list_apis":
            # TODO: Fetch from Control Plane API
            apis = {
                "apis": [],
                "message": "API catalog integration coming soon",
                "total": 0,
            }
            return ToolResult(
                content=[TextContent(text=str(apis))],
            )

        elif tool.name == "stoa_get_api_details":
            api_id = arguments.get("api_id")
            if not api_id:
                return ToolResult(
                    content=[TextContent(text="api_id is required")],
                    is_error=True,
                )
            # TODO: Fetch from Control Plane API
            return ToolResult(
                content=[TextContent(text=f"API details for {api_id} - coming soon")],
            )

        elif tool.name == "stoa_health_check":
            service = arguments.get("service", "all")
            health_status = await self._check_health(service, settings)
            return ToolResult(
                content=[TextContent(text=str(health_status))],
            )

        elif tool.name == "stoa_list_tools":
            tag = arguments.get("tag")
            include_schema = arguments.get("include_schema", False)
            tools_info = self._get_tools_info(tag, include_schema)
            return ToolResult(
                content=[TextContent(text=str(tools_info))],
            )

        elif tool.name == "stoa_get_tool_schema":
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
            return ToolResult(
                content=[TextContent(text=str(schema_info))],
            )

        elif tool.name == "stoa_search_apis":
            query = arguments.get("query")
            if not query:
                return ToolResult(
                    content=[TextContent(text="query is required")],
                    is_error=True,
                )
            # TODO: Implement full-text search via Control Plane API
            search_results = {
                "query": query,
                "results": [],
                "total": 0,
                "message": "API search integration coming soon",
            }
            return ToolResult(
                content=[TextContent(text=str(search_results))],
            )

        return ToolResult(
            content=[TextContent(text=f"Unknown builtin tool: {tool.name}")],
            is_error=True,
        )

    async def _check_platform_health(
        self,
        components: list[str],
        settings: Any,
    ) -> dict[str, Any]:
        """Check health of platform components with latency tracking.

        CAB-658: Enhanced health check with:
        - Per-component latency measurement (ms)
        - Tri-state status: healthy / degraded / down / unknown / not_configured
        - Async parallel checks for performance
        - Configurable thresholds per component

        Environment Variables:
        - STOA_MCP_URL: MCP Server URL (default: https://mcp.{base_domain})
        - STOA_WEBMETHODS_URL: webMethods Gateway URL (default: https://gateway.{base_domain})
        - STOA_KEYCLOAK_URL: Keycloak URL (default: https://auth.{base_domain})
        - STOA_KEYCLOAK_REALM: Keycloak realm (default: stoa)
        - STOA_DATABASE_URL: PostgreSQL connection string
        - STOA_KAFKA_BOOTSTRAP: Kafka bootstrap servers
        - STOA_OPENSEARCH_URL: OpenSearch URL
        - STOA_HEALTH_TIMEOUT: Health check timeout in seconds (default: 5.0)
        """
        # Create health checker with environment-based configuration
        # Components without URLs configured will show as not_configured
        checker = HealthChecker(
            mcp_url=os.getenv("STOA_MCP_URL", f"https://mcp.{settings.base_domain}"),
            webmethods_url=os.getenv("STOA_WEBMETHODS_URL", f"https://gateway.{settings.base_domain}"),
            keycloak_url=os.getenv("STOA_KEYCLOAK_URL", f"https://auth.{settings.base_domain}"),
            keycloak_realm=os.getenv("STOA_KEYCLOAK_REALM", getattr(settings, "keycloak_realm", "stoa")),
            database_url=os.getenv("STOA_DATABASE_URL", os.getenv("DATABASE_URL", "")),
            kafka_bootstrap=os.getenv("STOA_KAFKA_BOOTSTRAP", os.getenv("KAFKA_BOOTSTRAP_SERVERS", "")),
            opensearch_url=os.getenv("STOA_OPENSEARCH_URL", ""),
            timeout_seconds=float(os.getenv("STOA_HEALTH_TIMEOUT", "5.0")),
        )

        # Check requested components or all
        if components:
            health = await checker.check_components(components)
        else:
            health = await checker.check_all()

        # Convert to dict format for response
        return {
            "overall": health.overall.value,
            "summary": health.summary,
            "components": {
                name: {
                    "status": comp.status.value,
                    **({"latency_ms": comp.latency_ms} if comp.latency_ms is not None else {}),
                    **({"description": comp.description} if comp.description else {}),
                    **({"message": comp.message} if comp.message else {}),
                    **({"error": comp.error} if comp.error else {}),
                    **({"details": comp.details} if comp.details else {}),
                }
                for name, comp in health.components.items()
            },
            "checked_at": health.checked_at,
        }

    async def _check_health(
        self,
        service: str,
        settings: Any,
    ) -> dict[str, Any]:
        """Legacy health check - redirects to new implementation.

        Deprecated: Use _check_platform_health instead.
        """
        # Map legacy service names to new component names
        component_map = {
            "api": "webmethods",  # API is checked via webMethods gateway
            "gateway": "webmethods",  # Legacy gateway -> webmethods
            "webmethods": "webmethods",
            "auth": "keycloak",
            "mcp": "mcp",
        }

        if service == "all":
            components = ["mcp", "webmethods", "keycloak", "database", "kafka", "opensearch"]
        else:
            components = [component_map.get(service, service)]

        return await self._check_platform_health(components, settings)

    async def _invoke_api(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        user_token: str | None = None,
    ) -> ToolResult:
        """Invoke an API-backed tool."""
        if not self._http_client:
            return ToolResult(
                content=[TextContent(text="HTTP client not initialized")],
                is_error=True,
            )

        if not tool.endpoint:
            return ToolResult(
                content=[TextContent(text="Tool has no endpoint configured")],
                is_error=True,
            )

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"

        try:
            method = tool.method.upper()

            if method == "GET":
                response = await self._http_client.get(
                    tool.endpoint,
                    params=arguments,
                    headers=headers,
                )
            elif method == "POST":
                response = await self._http_client.post(
                    tool.endpoint,
                    json=arguments,
                    headers=headers,
                )
            elif method == "PUT":
                response = await self._http_client.put(
                    tool.endpoint,
                    json=arguments,
                    headers=headers,
                )
            elif method == "DELETE":
                response = await self._http_client.delete(
                    tool.endpoint,
                    params=arguments,
                    headers=headers,
                )
            elif method == "PATCH":
                response = await self._http_client.patch(
                    tool.endpoint,
                    json=arguments,
                    headers=headers,
                )
            else:
                return ToolResult(
                    content=[TextContent(text=f"Unsupported HTTP method: {method}")],
                    is_error=True,
                )

            # Return result
            is_error = response.status_code >= 400
            return ToolResult(
                content=[TextContent(text=response.text)],
                is_error=is_error,
                backend_status=response.status_code,
            )

        except httpx.RequestError as e:
            return ToolResult(
                content=[TextContent(text=f"Request failed: {str(e)}")],
                is_error=True,
            )
