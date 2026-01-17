"""MCP Tool Registry Service.

Manages the registration and discovery of MCP tools.
Tools are mapped from STOA API definitions.

CAB-603: Restructured for Core vs Proxied tool separation.
- Core Tools: 35 static platform tools with stoa_{domain}_{action} naming
- Proxied Tools: Dynamic tenant API tools with {tenant}:{api}:{operation} namespace
"""

import time
from typing import Any

import httpx
import structlog

from ..config import get_settings
from ..models import (
    Tool,
    CoreTool,
    ProxiedTool,
    AnyTool,
    ToolType,
    ToolInputSchema,
    ToolInvocation,
    ToolResult,
    TextContent,
    ListToolsResponse,
    ListCategoriesResponse,
    ListTagsResponse,
    ToolCategory,
)
from ..tools import CORE_TOOLS, get_core_tool

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """Registry for MCP Tools.

    Manages tool definitions and provides lookup functionality.
    Tools can be registered from:
    - Static configuration (core tools)
    - STOA Control Plane API (dynamic discovery)
    - Kubernetes CRDs (proxied tools)
    - OpenAPI specifications

    CAB-603: Three-tier storage structure:
    - _core_tools: Static platform tools (stoa_*)
    - _proxied_tools: Dynamic tenant API tools ({tenant}:{api}:{operation})
    - _tools: Legacy tools (backward compatibility)
    """

    def __init__(self) -> None:
        """Initialize the tool registry."""
        # CAB-603: Separate storage for core vs proxied tools
        self._core_tools: dict[str, CoreTool] = {}
        self._proxied_tools: dict[str, ProxiedTool] = {}  # Key: namespaced_name
        self._tools: dict[str, Tool] = {}  # Legacy storage for backward compatibility
        self._http_client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        """Initialize the registry on application startup."""
        settings = get_settings()
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.mcp_timeout_seconds),
            follow_redirects=True,
        )
        logger.info("Tool registry initialized")

        # CAB-603: Register the 35 core tools from the new tools package
        await self._register_core_tools()

        # Register built-in tools (legacy, for backward compatibility)
        await self._register_builtin_tools()

    async def _register_core_tools(self) -> None:
        """Register all 35 core platform tools.

        CAB-603: Core tools are static platform capabilities defined in
        src/tools/core_tools.py with stoa_{domain}_{action} naming.
        """
        for core_tool in CORE_TOOLS:
            self.register_core_tool(core_tool)
        logger.info("Registered core tools", count=len(self._core_tools))

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

        # =====================================================================
        # Ready Player One Demo Tools
        # =====================================================================
        # These tools demonstrate tenant-based ownership for the RPO demo
        # - high-five tenant: Parzival's resistance team
        # - ioi tenant: IOI Corporation (antagonists)

        # High Five Tools (Parzival's team)
        self.register(
            Tool(
                name="artifact_search",
                description="Search OASIS artifacts and easter eggs left by Halliday. Find hidden keys, gates, and rare items across all sectors.",
                input_schema=ToolInputSchema(
                    properties={
                        "query": {
                            "type": "string",
                            "description": "Search query for artifacts (name, type, or keyword)",
                        },
                        "sector": {
                            "type": "string",
                            "description": "OASIS sector to search (e.g., Ludus, Archaide, Middletown)",
                        },
                        "rarity": {
                            "type": "string",
                            "description": "Filter by rarity level",
                            "enum": ["common", "rare", "epic", "legendary", "unique"],
                        },
                    },
                    required=["query"],
                ),
                category="Sales",
                tags=["oasis", "artifacts", "easter-eggs", "hunting"],
                tenant_id="high-five",
            )
        )

        self.register(
            Tool(
                name="scoreboard_tracker",
                description="Track gunter rankings, High Five scores, and leaderboard positions in the hunt for Halliday's Easter Egg.",
                input_schema=ToolInputSchema(
                    properties={
                        "top_n": {
                            "type": "integer",
                            "description": "Number of top gunters to return",
                            "default": 10,
                        },
                        "team": {
                            "type": "string",
                            "description": "Filter by team/clan name",
                        },
                        "gate": {
                            "type": "string",
                            "description": "Filter by gate progress",
                            "enum": ["copper", "jade", "crystal", "complete"],
                        },
                    },
                    required=[],
                ),
                category="Finance",
                tags=["rankings", "scores", "gunters", "leaderboard"],
                tenant_id="high-five",
            )
        )

        # IOI Tools (Corporation)
        self.register(
            Tool(
                name="sixers_inventory",
                description="IOI Sixers equipment and resources inventory. Track weapons, vehicles, armor, and consumables across all IOI warehouses.",
                input_schema=ToolInputSchema(
                    properties={
                        "category": {
                            "type": "string",
                            "description": "Equipment category",
                            "enum": ["weapons", "vehicles", "armor", "consumables", "artifacts"],
                        },
                        "location": {
                            "type": "string",
                            "description": "Warehouse location (e.g., IOI-Tower, Sector-15)",
                        },
                        "min_quantity": {
                            "type": "integer",
                            "description": "Minimum quantity in stock",
                        },
                    },
                    required=[],
                ),
                category="Operations",
                tags=["inventory", "sixers", "equipment", "ioi"],
                tenant_id="ioi",
            )
        )

        self.register(
            Tool(
                name="surveillance_feed",
                description="IOI OASIS surveillance and player monitoring system. Track player movements, activities, and communications across sectors.",
                input_schema=ToolInputSchema(
                    properties={
                        "target": {
                            "type": "string",
                            "description": "Player avatar name or ID to track",
                        },
                        "sector": {
                            "type": "string",
                            "description": "OASIS sector to monitor",
                        },
                        "activity_type": {
                            "type": "string",
                            "description": "Type of activity to monitor",
                            "enum": ["movement", "combat", "trade", "communication", "all"],
                        },
                    },
                    required=[],
                ),
                category="Communications",
                tags=["surveillance", "monitoring", "tracking", "ioi"],
                tenant_id="ioi",
            )
        )

        logger.info("Registered demo tools with categories", count=16)

    # =========================================================================
    # Registration Methods (CAB-603)
    # =========================================================================

    def register_core_tool(self, tool: CoreTool) -> None:
        """Register a core platform tool.

        Args:
            tool: CoreTool instance with stoa_* naming
        """
        if tool.name in self._core_tools:
            logger.warning("Overwriting existing core tool", tool_name=tool.name)
        self._core_tools[tool.name] = tool
        logger.debug("Core tool registered", tool_name=tool.name, domain=tool.domain.value)

    def register_proxied_tool(self, tool: ProxiedTool) -> None:
        """Register a proxied tenant API tool.

        Args:
            tool: ProxiedTool instance with {tenant}:{api}:{operation} namespace
        """
        key = tool.namespaced_name
        if key in self._proxied_tools:
            logger.warning("Overwriting existing proxied tool", tool_name=key)
        self._proxied_tools[key] = tool
        logger.debug(
            "Proxied tool registered",
            tool_name=tool.name,
            namespaced_name=key,
            tenant_id=tool.tenant_id,
        )

    def register(self, tool: Tool) -> None:
        """Register a legacy tool (backward compatibility).

        For new code, prefer register_core_tool() or register_proxied_tool().
        """
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool", tool_name=tool.name)
        self._tools[tool.name] = tool
        logger.debug("Tool registered", tool_name=tool.name)

    def unregister_core_tool(self, name: str) -> bool:
        """Unregister a core tool."""
        if name in self._core_tools:
            del self._core_tools[name]
            logger.debug("Core tool unregistered", tool_name=name)
            return True
        return False

    def unregister_proxied_tool(self, namespaced_name: str) -> bool:
        """Unregister a proxied tool by its namespaced name.

        Args:
            namespaced_name: Full namespace {tenant}:{api}:{operation}
        """
        if namespaced_name in self._proxied_tools:
            del self._proxied_tools[namespaced_name]
            logger.debug("Proxied tool unregistered", namespaced_name=namespaced_name)
            return True
        return False

    def unregister(self, name: str) -> bool:
        """Unregister a legacy tool."""
        if name in self._tools:
            del self._tools[name]
            logger.debug("Tool unregistered", tool_name=name)
            return True
        return False

    # =========================================================================
    # Lookup Methods (CAB-603)
    # =========================================================================

    def get_core_tool(self, name: str) -> CoreTool | None:
        """Get a core tool by name."""
        return self._core_tools.get(name)

    def get_proxied_tool(
        self,
        name: str,
        tenant_id: str | None = None,
    ) -> ProxiedTool | None:
        """Get a proxied tool by name or namespaced name.

        Args:
            name: Tool name or full namespaced name {tenant}:{api}:{operation}
            tenant_id: Optional tenant context for lookup

        Returns:
            ProxiedTool if found, None otherwise
        """
        # Direct lookup by namespaced name (uses __ separator)
        if "__" in name:
            return self._proxied_tools.get(name)

        # Search by operation name within tenant context
        if tenant_id:
            for key, tool in self._proxied_tools.items():
                if tool.tenant_id == tenant_id and tool.operation == name:
                    return tool

        return None

    def get(self, name: str, tenant_id: str | None = None) -> AnyTool | None:
        """Get a tool by name with smart routing.

        CAB-603: Routes lookup based on naming convention:
        - stoa_* -> Core tools
        - {tenant}:{api}:{operation} -> Proxied tools
        - other -> Legacy tools

        Args:
            name: Tool name
            tenant_id: Optional tenant context for proxied tool lookup

        Returns:
            Tool if found, None otherwise
        """
        # Core tools: stoa_* prefix
        if name.startswith("stoa_"):
            return self._core_tools.get(name)

        # Proxied tools: namespaced format (uses __ separator)
        if "__" in name:
            return self._proxied_tools.get(name)

        # Try proxied tool lookup with tenant context
        if tenant_id:
            proxied = self.get_proxied_tool(name, tenant_id)
            if proxied:
                return proxied

        # Legacy tools
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
        include_core: bool = True,
        include_proxied: bool = True,
        include_legacy: bool = True,
    ) -> ListToolsResponse:
        """List all registered tools with optional filtering.

        CAB-603: Aggregates tools from all three storage tiers.

        Args:
            tenant_id: Filter by tenant ID (for proxied and legacy tools)
            tag: Filter by single tag (legacy parameter)
            tags: Filter by multiple tags (AND logic)
            category: Filter by category
            search: Search in name and description
            cursor: Pagination cursor
            limit: Maximum results to return
            include_core: Include core platform tools (default: True)
            include_proxied: Include proxied tenant tools (default: True)
            include_legacy: Include legacy tools (default: True)
        """
        # CAB-603: Aggregate tools from all storage tiers
        tools: list[Tool] = []

        # Add core tools (converted to Tool for response compatibility)
        if include_core:
            for core_tool in self._core_tools.values():
                # Convert CoreTool to Tool for API response
                tools.append(Tool(
                    name=core_tool.name,
                    description=core_tool.description,
                    input_schema=core_tool.input_schema,
                    category=core_tool.category,
                    tags=core_tool.tags,
                    version=core_tool.version,
                ))

        # Add proxied tools (tenant-filtered)
        if include_proxied:
            for proxied_tool in self._proxied_tools.values():
                # Only include tools for the user's tenant or global tools
                if tenant_id is None or proxied_tool.tenant_id == tenant_id:
                    tools.append(Tool(
                        name=proxied_tool.namespaced_name,  # Use namespaced name
                        description=proxied_tool.description,
                        input_schema=proxied_tool.input_schema,
                        api_id=proxied_tool.api_id,
                        tenant_id=proxied_tool.tenant_id,
                        endpoint=proxied_tool.endpoint,
                        method=proxied_tool.method,
                        category=proxied_tool.category,
                        tags=proxied_tool.tags,
                        version=proxied_tool.version,
                    ))

        # Add legacy tools
        if include_legacy:
            for legacy_tool in self._tools.values():
                # Filter legacy tools by tenant
                if tenant_id is None or legacy_tool.tenant_id is None or legacy_tool.tenant_id == tenant_id:
                    tools.append(legacy_tool)

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
        """List all unique categories with tool counts.

        CAB-603: Includes categories from core, proxied, and legacy tools.
        """
        category_counts: dict[str, int] = {}

        # Count core tool categories
        for tool in self._core_tools.values():
            if tool.category:
                category_counts[tool.category] = category_counts.get(tool.category, 0) + 1

        # Count proxied tool categories
        for tool in self._proxied_tools.values():
            if tool.category:
                category_counts[tool.category] = category_counts.get(tool.category, 0) + 1

        # Count legacy tool categories
        for tool in self._tools.values():
            if tool.category:
                category_counts[tool.category] = category_counts.get(tool.category, 0) + 1

        categories = [
            ToolCategory(name=name, count=count)
            for name, count in sorted(category_counts.items())
        ]

        return ListCategoriesResponse(categories=categories)

    def list_tags(self) -> ListTagsResponse:
        """List all unique tags with counts.

        CAB-603: Includes tags from core, proxied, and legacy tools.
        """
        tag_counts: dict[str, int] = {}

        # Count core tool tags
        for tool in self._core_tools.values():
            for tag in tool.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Count proxied tool tags
        for tool in self._proxied_tools.values():
            for tag in tool.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Count legacy tool tags
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
        tenant_id: str | None = None,
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

        Returns:
            Tool execution result
        """
        start_time = time.time()
        tool = self.get(invocation.name, tenant_id)

        if not tool:
            return ToolResult(
                content=[TextContent(text=f"Tool not found: {invocation.name}")],
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
        )

        try:
            # CAB-603: Route by tool type
            if isinstance(tool, CoreTool):
                result = await self._invoke_core_tool(tool, invocation.arguments)
            elif isinstance(tool, ProxiedTool):
                result = await self._invoke_proxied_tool(tool, invocation.arguments, user_token)
            # Legacy: Handle built-in tools (backward compatibility)
            elif tool.name.startswith("stoa_"):
                result = await self._invoke_builtin(tool, invocation.arguments)
            # Legacy: Handle API-backed tools
            elif hasattr(tool, 'endpoint') and tool.endpoint:
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
            latency_ms = int((time.time() - start_time) * 1000)
            logger.exception("Tool invocation failed", tool_name=tool.name, error=str(e))

            # Capture error snapshot (Phase 3)
            try:
                from ..features.error_snapshots import capture_tool_error
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

    # =========================================================================
    # Invocation Methods (CAB-603)
    # =========================================================================

    async def _invoke_core_tool(
        self,
        tool: CoreTool,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Invoke a core platform tool.

        CAB-603: Core tools are handled internally with specific handlers
        based on the tool's domain and action.

        Args:
            tool: CoreTool instance
            arguments: Tool invocation arguments

        Returns:
            ToolResult with execution output
        """
        settings = get_settings()

        # Route to domain-specific handlers
        # For now, use handler reference or fallback to name-based routing
        handler_name = tool.handler or tool.name

        # Platform & Discovery handlers
        if tool.name == "stoa_platform_info":
            info = {
                "platform": "STOA",
                "version": settings.app_version,
                "environment": settings.environment,
                "base_domain": settings.base_domain,
                "core_tools_count": len(self._core_tools),
                "proxied_tools_count": len(self._proxied_tools),
                "legacy_tools_count": len(self._tools),
                "services": {
                    "api": f"https://api.{settings.base_domain}",
                    "gateway": f"https://gateway.{settings.base_domain}",
                    "auth": f"https://auth.{settings.base_domain}",
                    "mcp": f"https://mcp.{settings.base_domain}",
                },
            }
            return ToolResult(content=[TextContent(text=str(info))])

        elif tool.name == "stoa_platform_health":
            components = arguments.get("components", [])
            health_status = await self._check_health(
                "all" if not components else ",".join(components),
                settings,
            )
            return ToolResult(content=[TextContent(text=str(health_status))])

        elif tool.name == "stoa_list_tools":
            category = arguments.get("category")
            tag = arguments.get("tag")
            search = arguments.get("search")
            include_proxied = arguments.get("include_proxied", True)
            tools_response = self.list_tools(
                category=category,
                tag=tag,
                search=search,
                include_proxied=include_proxied,
            )
            return ToolResult(content=[TextContent(text=str({
                "tools": [{"name": t.name, "description": t.description, "category": t.category} for t in tools_response.tools],
                "total": tools_response.total_count,
            }))])

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
            return ToolResult(content=[TextContent(text=str(schema_info))])

        elif tool.name == "stoa_search_tools":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 20)
            tools_response = self.list_tools(search=query, limit=limit)
            return ToolResult(content=[TextContent(text=str({
                "query": query,
                "results": [{"name": t.name, "description": t.description} for t in tools_response.tools],
                "total": tools_response.total_count,
            }))])

        elif tool.name == "stoa_list_tenants":
            # Admin-only tool - implementation stub
            include_inactive = arguments.get("include_inactive", False)
            return ToolResult(content=[TextContent(text=str({
                "tenants": [],
                "message": "Tenant listing requires admin scope - coming soon",
                "include_inactive": include_inactive,
            }))])

        # API Catalog handlers
        elif tool.name in ("stoa_catalog_list_apis", "stoa_list_apis"):
            return ToolResult(content=[TextContent(text=str({
                "apis": [],
                "message": "API catalog integration - coming soon",
                "total": 0,
            }))])

        elif tool.name in ("stoa_catalog_get_api", "stoa_get_api_details"):
            api_id = arguments.get("api_id")
            if not api_id:
                return ToolResult(
                    content=[TextContent(text="api_id is required")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=f"API details for {api_id} - coming soon")])

        elif tool.name == "stoa_catalog_search_apis":
            query = arguments.get("query", "")
            return ToolResult(content=[TextContent(text=str({
                "query": query,
                "results": [],
                "message": "API search - coming soon",
            }))])

        # Default stub for unimplemented core tools
        else:
            return ToolResult(content=[TextContent(text=str({
                "tool": tool.name,
                "domain": tool.domain.value,
                "action": tool.action,
                "arguments": arguments,
                "status": "stub",
                "message": f"Core tool handler for {tool.name} - implementation pending",
            }))])

    async def _invoke_proxied_tool(
        self,
        tool: ProxiedTool,
        arguments: dict[str, Any],
        user_token: str | None = None,
    ) -> ToolResult:
        """Invoke a proxied tenant API tool.

        CAB-603: Proxied tools forward requests to backend APIs
        with proper authentication and header injection.

        Args:
            tool: ProxiedTool instance
            arguments: Tool invocation arguments
            user_token: User JWT for backend authentication

        Returns:
            ToolResult with backend response
        """
        if not self._http_client:
            return ToolResult(
                content=[TextContent(text="HTTP client not initialized")],
                is_error=True,
            )

        if not tool.endpoint:
            return ToolResult(
                content=[TextContent(text=f"Proxied tool {tool.name} has no endpoint configured")],
                is_error=True,
            )

        # Build headers
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-STOA-Tenant-ID": tool.tenant_id,
            "X-STOA-Tool-Name": tool.namespaced_name,
        }

        # Add user token if available
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"

        # Add custom headers from tool definition
        headers.update(tool.headers)

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
            logger.error(
                "Proxied tool request failed",
                tool_name=tool.namespaced_name,
                endpoint=tool.endpoint,
                error=str(e),
            )
            return ToolResult(
                content=[TextContent(text=f"Request to backend failed: {str(e)}")],
                is_error=True,
            )

    # =========================================================================
    # Legacy Invocation Methods (backward compatibility)
    # =========================================================================

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
                    expected_codes = [200]
                elif svc == "gateway":
                    # webMethods API Gateway - root returns 302 redirect to /apigatewayui when healthy
                    url = f"https://gateway.{settings.base_domain}/"
                    expected_codes = [200, 302]
                elif svc == "auth":
                    # Keycloak - use OIDC discovery endpoint (always publicly accessible)
                    url = f"https://auth.{settings.base_domain}/realms/{settings.keycloak_realm}/.well-known/openid-configuration"
                    expected_codes = [200]
                else:
                    continue

                if self._http_client:
                    response = await self._http_client.get(url, timeout=5.0, follow_redirects=False)
                    health["services"][svc] = {
                        "status": "healthy" if response.status_code in expected_codes else "unhealthy",
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
