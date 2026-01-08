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
    ListCategoriesResponse,
    ListTagsResponse,
    ToolCategory,
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

        # Register demo tools with categories
        await self._register_demo_tools()

        logger.info("Registered builtin tools", count=len(self._tools))

    async def _register_demo_tools(self) -> None:
        """Register demo tools with categories for CAB-311."""
        # Sales category tools
        self.register(
            Tool(
                name="crm_search",
                description="Search customer records in the CRM database by name, email, or account ID",
                input_schema=ToolInputSchema(
                    properties={
                        "query": {
                            "type": "string",
                            "description": "Search query (name, email, or account ID)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results to return",
                            "default": 10,
                        },
                    },
                    required=["query"],
                ),
                category="Sales",
                tags=["crm", "customer", "search"],
            )
        )

        self.register(
            Tool(
                name="sales_pipeline",
                description="Get current sales pipeline status and opportunities",
                input_schema=ToolInputSchema(
                    properties={
                        "stage": {
                            "type": "string",
                            "description": "Filter by pipeline stage",
                            "enum": ["prospect", "qualified", "proposal", "negotiation", "closed"],
                        },
                        "min_value": {
                            "type": "number",
                            "description": "Minimum deal value",
                        },
                    },
                    required=[],
                ),
                category="Sales",
                tags=["crm", "pipeline", "opportunities"],
            )
        )

        self.register(
            Tool(
                name="lead_scoring",
                description="Calculate lead score based on engagement and profile data",
                input_schema=ToolInputSchema(
                    properties={
                        "lead_id": {
                            "type": "string",
                            "description": "Lead identifier",
                        },
                    },
                    required=["lead_id"],
                ),
                category="Sales",
                tags=["crm", "leads", "scoring"],
            )
        )

        # Finance category tools
        self.register(
            Tool(
                name="billing_invoice",
                description="Create, retrieve, or update billing invoices",
                input_schema=ToolInputSchema(
                    properties={
                        "action": {
                            "type": "string",
                            "description": "Action to perform",
                            "enum": ["create", "get", "list", "update"],
                        },
                        "invoice_id": {
                            "type": "string",
                            "description": "Invoice ID (for get/update)",
                        },
                        "customer_id": {
                            "type": "string",
                            "description": "Customer ID (for create/list)",
                        },
                    },
                    required=["action"],
                ),
                category="Finance",
                tags=["billing", "invoice", "accounting"],
            )
        )

        self.register(
            Tool(
                name="expense_report",
                description="Submit or review expense reports",
                input_schema=ToolInputSchema(
                    properties={
                        "action": {
                            "type": "string",
                            "description": "Action to perform",
                            "enum": ["submit", "approve", "reject", "list"],
                        },
                        "report_id": {
                            "type": "string",
                            "description": "Expense report ID",
                        },
                    },
                    required=["action"],
                ),
                category="Finance",
                tags=["expense", "finance", "reporting"],
            )
        )

        self.register(
            Tool(
                name="revenue_analytics",
                description="Get revenue analytics and financial metrics",
                input_schema=ToolInputSchema(
                    properties={
                        "period": {
                            "type": "string",
                            "description": "Time period",
                            "enum": ["daily", "weekly", "monthly", "quarterly", "yearly"],
                        },
                        "metric": {
                            "type": "string",
                            "description": "Metric to retrieve",
                            "enum": ["revenue", "mrr", "arr", "churn"],
                        },
                    },
                    required=["period"],
                ),
                category="Finance",
                tags=["analytics", "revenue", "metrics"],
            )
        )

        # Operations category tools
        self.register(
            Tool(
                name="inventory_lookup",
                description="Check inventory levels and stock availability",
                input_schema=ToolInputSchema(
                    properties={
                        "product_id": {
                            "type": "string",
                            "description": "Product identifier",
                        },
                        "warehouse": {
                            "type": "string",
                            "description": "Warehouse location",
                        },
                    },
                    required=["product_id"],
                ),
                category="Operations",
                tags=["inventory", "warehouse", "stock"],
            )
        )

        self.register(
            Tool(
                name="order_tracking",
                description="Track order status and shipment information",
                input_schema=ToolInputSchema(
                    properties={
                        "order_id": {
                            "type": "string",
                            "description": "Order identifier",
                        },
                    },
                    required=["order_id"],
                ),
                category="Operations",
                tags=["orders", "shipping", "tracking"],
            )
        )

        self.register(
            Tool(
                name="supply_chain_status",
                description="Get supply chain status and supplier information",
                input_schema=ToolInputSchema(
                    properties={
                        "supplier_id": {
                            "type": "string",
                            "description": "Supplier identifier",
                        },
                        "category": {
                            "type": "string",
                            "description": "Product category",
                        },
                    },
                    required=[],
                ),
                category="Operations",
                tags=["supply-chain", "suppliers", "logistics"],
            )
        )

        # Communications category tools
        self.register(
            Tool(
                name="notifications_send",
                description="Send notifications via email, SMS, or push",
                input_schema=ToolInputSchema(
                    properties={
                        "channel": {
                            "type": "string",
                            "description": "Notification channel",
                            "enum": ["email", "sms", "push", "slack"],
                        },
                        "recipient": {
                            "type": "string",
                            "description": "Recipient identifier or address",
                        },
                        "message": {
                            "type": "string",
                            "description": "Message content",
                        },
                        "template_id": {
                            "type": "string",
                            "description": "Optional template ID",
                        },
                    },
                    required=["channel", "recipient", "message"],
                ),
                category="Communications",
                tags=["notifications", "email", "messaging"],
            )
        )

        self.register(
            Tool(
                name="email_templates",
                description="Manage email templates for communications",
                input_schema=ToolInputSchema(
                    properties={
                        "action": {
                            "type": "string",
                            "description": "Action to perform",
                            "enum": ["list", "get", "preview"],
                        },
                        "template_id": {
                            "type": "string",
                            "description": "Template identifier",
                        },
                        "variables": {
                            "type": "object",
                            "description": "Template variables for preview",
                        },
                    },
                    required=["action"],
                ),
                category="Communications",
                tags=["email", "templates", "marketing"],
            )
        )

        self.register(
            Tool(
                name="chat_integration",
                description="Send messages to team chat platforms (Slack, Teams)",
                input_schema=ToolInputSchema(
                    properties={
                        "platform": {
                            "type": "string",
                            "description": "Chat platform",
                            "enum": ["slack", "teams", "discord"],
                        },
                        "channel": {
                            "type": "string",
                            "description": "Channel or conversation ID",
                        },
                        "message": {
                            "type": "string",
                            "description": "Message to send",
                        },
                    },
                    required=["platform", "channel", "message"],
                ),
                category="Communications",
                tags=["chat", "slack", "teams", "messaging"],
            )
        )

        logger.info("Registered demo tools with categories", count=12)

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
        tags: list[str] | None = None,
        category: str | None = None,
        search: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> ListToolsResponse:
        """List all registered tools with optional filtering.

        Args:
            tenant_id: Filter by tenant ID
            tag: Filter by single tag (legacy parameter)
            tags: Filter by multiple tags (AND logic)
            category: Filter by category
            search: Search in name and description
            cursor: Pagination cursor
            limit: Maximum results to return
        """
        tools = list(self._tools.values())

        # Filter by tenant
        if tenant_id:
            tools = [t for t in tools if t.tenant_id == tenant_id or t.tenant_id is None]

        # Filter by single tag (legacy)
        if tag:
            tools = [t for t in tools if tag in t.tags]

        # Filter by multiple tags (AND logic - all tags must match)
        if tags:
            tools = [t for t in tools if all(tg in t.tags for tg in tags)]

        # Filter by category
        if category:
            tools = [t for t in tools if t.category and t.category.lower() == category.lower()]

        # Search in name and description
        if search:
            search_lower = search.lower()
            tools = [
                t for t in tools
                if search_lower in t.name.lower() or search_lower in t.description.lower()
            ]

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

    def list_categories(self) -> ListCategoriesResponse:
        """List all unique categories with tool counts."""
        category_counts: dict[str, int] = {}

        for tool in self._tools.values():
            if tool.category:
                cat = tool.category
                category_counts[cat] = category_counts.get(cat, 0) + 1

        categories = [
            ToolCategory(name=name, count=count)
            for name, count in sorted(category_counts.items())
        ]

        return ListCategoriesResponse(categories=categories)

    def list_tags(self) -> ListTagsResponse:
        """List all unique tags with counts."""
        tag_counts: dict[str, int] = {}

        for tool in self._tools.values():
            for tag in tool.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return ListTagsResponse(
            tags=sorted(tag_counts.keys()),
            tag_counts=tag_counts,
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
