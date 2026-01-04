"""MCP Tool Registry Service.

Manages the registration and discovery of MCP tools.
Tools are mapped from STOA API definitions.
"""

import time
from typing import Any

import httpx
import structlog

from ..config import get_settings
from ..models import (
    Tool,
    ToolInputSchema,
    ToolInvocation,
    ToolResult,
    TextContent,
    ListToolsResponse,
)

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """Registry for MCP Tools.

    Manages tool definitions and provides lookup functionality.
    Tools can be registered from:
    - Static configuration
    - STOA Control Plane API (dynamic discovery)
    - OpenAPI specifications
    """

    def __init__(self) -> None:
        """Initialize the tool registry."""
        self._tools: dict[str, Tool] = {}
        self._http_client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        """Initialize the registry on application startup."""
        settings = get_settings()
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.mcp_timeout_seconds),
            follow_redirects=True,
        )
        logger.info("Tool registry initialized")

        # Register built-in tools
        await self._register_builtin_tools()

    async def shutdown(self) -> None:
        """Cleanup on application shutdown."""
        if self._http_client:
            await self._http_client.aclose()
        logger.info("Tool registry shutdown")

    async def _register_builtin_tools(self) -> None:
        """Register built-in platform tools."""
        # Platform info tool
        self.register(
            Tool(
                name="stoa_platform_info",
                description="Get information about the STOA API Management Platform",
                input_schema=ToolInputSchema(
                    properties={},
                    required=[],
                ),
                tags=["platform", "info"],
            )
        )

        # API catalog tool
        self.register(
            Tool(
                name="stoa_list_apis",
                description="List available APIs in the STOA catalog",
                input_schema=ToolInputSchema(
                    properties={
                        "tenant_id": {
                            "type": "string",
                            "description": "Filter by tenant ID",
                        },
                        "tag": {
                            "type": "string",
                            "description": "Filter by tag",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results",
                            "default": 20,
                        },
                    },
                    required=[],
                ),
                tags=["platform", "catalog"],
            )
        )

        # API details tool
        self.register(
            Tool(
                name="stoa_get_api_details",
                description="Get detailed information about a specific API",
                input_schema=ToolInputSchema(
                    properties={
                        "api_id": {
                            "type": "string",
                            "description": "The API identifier",
                        },
                    },
                    required=["api_id"],
                ),
                tags=["platform", "catalog"],
            )
        )

        # Health check tool
        self.register(
            Tool(
                name="stoa_health_check",
                description="Check the health status of STOA platform services",
                input_schema=ToolInputSchema(
                    properties={
                        "service": {
                            "type": "string",
                            "description": "Specific service to check (api, gateway, auth, all)",
                            "enum": ["api", "gateway", "auth", "all"],
                            "default": "all",
                        },
                    },
                    required=[],
                ),
                tags=["platform", "health"],
            )
        )

        # List available tools
        self.register(
            Tool(
                name="stoa_list_tools",
                description="List all available MCP tools with their descriptions",
                input_schema=ToolInputSchema(
                    properties={
                        "tag": {
                            "type": "string",
                            "description": "Filter tools by tag",
                        },
                        "include_schema": {
                            "type": "boolean",
                            "description": "Include input schema in response",
                            "default": False,
                        },
                    },
                    required=[],
                ),
                tags=["platform", "discovery"],
            )
        )

        # Get tool schema
        self.register(
            Tool(
                name="stoa_get_tool_schema",
                description="Get the input schema for a specific tool",
                input_schema=ToolInputSchema(
                    properties={
                        "tool_name": {
                            "type": "string",
                            "description": "Name of the tool to get schema for",
                        },
                    },
                    required=["tool_name"],
                ),
                tags=["platform", "discovery"],
            )
        )

        # Search APIs
        self.register(
            Tool(
                name="stoa_search_apis",
                description="Search for APIs by keyword in name or description",
                input_schema=ToolInputSchema(
                    properties={
                        "query": {
                            "type": "string",
                            "description": "Search query string",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Filter by tenant ID",
                        },
                    },
                    required=["query"],
                ),
                tags=["platform", "search"],
            )
        )

        logger.info("Registered builtin tools", count=len(self._tools))

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool", tool_name=tool.name)
        self._tools[tool.name] = tool
        logger.debug("Tool registered", tool_name=tool.name)

    def unregister(self, name: str) -> bool:
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            logger.debug("Tool unregistered", tool_name=name)
            return True
        return False

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(
        self,
        tenant_id: str | None = None,
        tag: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> ListToolsResponse:
        """List all registered tools with optional filtering."""
        tools = list(self._tools.values())

        # Filter by tenant
        if tenant_id:
            tools = [t for t in tools if t.tenant_id == tenant_id or t.tenant_id is None]

        # Filter by tag
        if tag:
            tools = [t for t in tools if tag in t.tags]

        # Pagination (simple offset-based for now)
        start_idx = 0
        if cursor:
            try:
                start_idx = int(cursor)
            except ValueError:
                pass

        end_idx = start_idx + limit
        paginated = tools[start_idx:end_idx]
        next_cursor = str(end_idx) if end_idx < len(tools) else None

        return ListToolsResponse(
            tools=paginated,
            next_cursor=next_cursor,
            total_count=len(tools),
        )

    async def invoke(
        self,
        invocation: ToolInvocation,
        user_token: str | None = None,
    ) -> ToolResult:
        """Invoke a tool.

        Args:
            invocation: Tool invocation request
            user_token: Optional user JWT for backend authentication

        Returns:
            Tool execution result
        """
        start_time = time.time()
        tool = self.get(invocation.name)

        if not tool:
            return ToolResult(
                content=[TextContent(text=f"Tool not found: {invocation.name}")],
                is_error=True,
                request_id=invocation.request_id,
            )

        logger.info(
            "Invoking tool",
            tool_name=tool.name,
            request_id=invocation.request_id,
        )

        try:
            # Handle built-in tools
            if tool.name.startswith("stoa_"):
                result = await self._invoke_builtin(tool, invocation.arguments)
            # Handle API-backed tools
            elif tool.endpoint:
                result = await self._invoke_api(tool, invocation.arguments, user_token)
            else:
                result = ToolResult(
                    content=[TextContent(text=f"Tool {tool.name} has no backend configured")],
                    is_error=True,
                )

            # Add latency
            latency_ms = int((time.time() - start_time) * 1000)
            result.latency_ms = latency_ms
            result.request_id = invocation.request_id

            return result

        except Exception as e:
            logger.exception("Tool invocation failed", tool_name=tool.name, error=str(e))
            return ToolResult(
                content=[TextContent(text=f"Tool invocation failed: {str(e)}")],
                is_error=True,
                request_id=invocation.request_id,
                latency_ms=int((time.time() - start_time) * 1000),
            )

    async def _invoke_builtin(
        self,
        tool: Tool,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Invoke a built-in platform tool."""
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

    async def _check_health(
        self,
        service: str,
        settings: Any,
    ) -> dict[str, Any]:
        """Check health of platform services."""
        health: dict[str, Any] = {
            "status": "healthy",
            "services": {},
        }

        services_to_check = []
        if service == "all":
            services_to_check = ["api", "gateway", "auth"]
        else:
            services_to_check = [service]

        for svc in services_to_check:
            try:
                if svc == "api":
                    url = f"https://api.{settings.base_domain}/health"
                elif svc == "gateway":
                    url = f"https://gateway.{settings.base_domain}/health"
                elif svc == "auth":
                    url = f"https://auth.{settings.base_domain}/health"
                else:
                    continue

                if self._http_client:
                    response = await self._http_client.get(url, timeout=5.0)
                    health["services"][svc] = {
                        "status": "healthy" if response.status_code == 200 else "unhealthy",
                        "status_code": response.status_code,
                    }
                else:
                    health["services"][svc] = {"status": "unknown", "error": "HTTP client not initialized"}
            except Exception as e:
                health["services"][svc] = {"status": "unhealthy", "error": str(e)}
                health["status"] = "degraded"

        return health

    def _get_tools_info(
        self,
        tag: str | None,
        include_schema: bool,
    ) -> dict[str, Any]:
        """Get information about available tools."""
        tools_list = []
        for tool in self._tools.values():
            if tag and tag not in tool.tags:
                continue
            tool_info: dict[str, Any] = {
                "name": tool.name,
                "description": tool.description,
                "tags": tool.tags,
            }
            if include_schema:
                tool_info["input_schema"] = {
                    "properties": tool.input_schema.properties,
                    "required": tool.input_schema.required,
                }
            tools_list.append(tool_info)

        return {
            "tools": tools_list,
            "total": len(tools_list),
        }

    def _get_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        """Get the schema for a specific tool."""
        tool = self._tools.get(tool_name)
        if not tool:
            return None
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": {
                "type": "object",
                "properties": tool.input_schema.properties,
                "required": tool.input_schema.required,
            },
        }

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


# Singleton instance
_registry: ToolRegistry | None = None


async def get_tool_registry() -> ToolRegistry:
    """Get the tool registry singleton."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        await _registry.startup()
    return _registry


async def shutdown_tool_registry() -> None:
    """Shutdown the tool registry."""
    global _registry
    if _registry:
        await _registry.shutdown()
        _registry = None
