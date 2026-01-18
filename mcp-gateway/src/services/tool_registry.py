"""MCP Tool Registry Service.

Manages the registration and discovery of MCP tools.
Tools are mapped from STOA API definitions.

CAB-603: Restructured for Core vs Proxied tool separation.
- Core Tools: 35 static platform tools with stoa_{domain}_{action} naming
- Proxied Tools: Dynamic tenant API tools with {tenant}:{api}:{operation} namespace

CAB-605 Phase 3: Tool consolidation with deprecation layer.
- Action-based tools: Single tool with action enum parameter
- Deprecation aliases: Backward compatibility for 60 days
"""

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
from ..tools import CORE_TOOLS, DEPRECATION_MAPPINGS, get_core_tool
from .health import HealthChecker, PlatformHealth, HealthStatus

logger = structlog.get_logger(__name__)


# =============================================================================
# CAB-605 Phase 3: Deprecation Layer
# =============================================================================


class ToolNotFoundError(Exception):
    """Raised when a tool is not found or has been permanently removed."""

    pass


@dataclass
class DeprecatedToolAlias:
    """Alias for backward compatibility during deprecation period.

    CAB-605: When old tools are renamed/consolidated, aliases allow
    existing clients to continue working for 60 days with warnings.

    Attributes:
        old_name: The deprecated tool name
        new_name: The replacement tool name
        new_args: Arguments to inject when redirecting
        deprecated_at: When the deprecation started
        remove_after: When the alias will stop working (60 days default)
    """

    old_name: str
    new_name: str
    new_args: dict[str, Any] = field(default_factory=dict)
    deprecated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    remove_after: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=60)
    )

    def is_expired(self) -> bool:
        """Check if the deprecation period has ended."""
        return datetime.now(timezone.utc) > self.remove_after

    def days_until_removal(self) -> int:
        """Get days remaining until removal."""
        remaining = self.remove_after - datetime.now(timezone.utc)
        return max(0, remaining.days)


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

        # CAB-605 Phase 3: Deprecation aliases for backward compatibility
        self._deprecated_aliases: dict[str, DeprecatedToolAlias] = {}

    async def startup(self) -> None:
        """Initialize the registry on application startup."""
        settings = get_settings()
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.mcp_timeout_seconds),
            follow_redirects=True,
        )
        logger.info("Tool registry initialized")

        # CAB-605: Register consolidated core tools (12 action-based tools)
        await self._register_core_tools()

        # CAB-605: Register deprecation aliases for backward compatibility
        await self._register_deprecation_aliases()

        # Register built-in tools (legacy, for backward compatibility)
        await self._register_builtin_tools()

    async def _register_core_tools(self) -> None:
        """Register consolidated core platform tools.

        CAB-605 Phase 3: Consolidated action-based tools (12 total).
        Tools are defined in src/tools/consolidated_tools.py.
        """
        for core_tool in CORE_TOOLS:
            self.register_core_tool(core_tool)
        logger.info("Registered core tools", count=len(self._core_tools))

    async def _register_deprecation_aliases(self) -> None:
        """Register deprecation aliases for legacy tool names.

        CAB-605 Phase 3: Maps old tool names to new consolidated tools
        with appropriate action parameters.
        """
        for old_name, (new_name, new_args) in DEPRECATION_MAPPINGS.items():
            self.register_deprecation(old_name, new_name, new_args)
        logger.info(
            "Registered deprecation aliases",
            count=len(self._deprecated_aliases),
        )

    async def shutdown(self) -> None:
        """Cleanup on application shutdown."""
        if self._http_client:
            await self._http_client.aclose()
        logger.info("Tool registry shutdown")

    async def _register_builtin_tools(self) -> None:
        """Register built-in platform tools.

        CAB-605: Legacy duplicate tools removed. Use core tools instead:
        - stoa_platform_info -> Core stoa_platform_info
        - stoa_list_apis -> Core stoa_catalog_list_apis
        - stoa_get_api_details -> Core stoa_catalog_get_api
        - stoa_health_check -> Core stoa_platform_health
        - stoa_list_tools -> Core stoa_list_tools
        - stoa_get_tool_schema -> Core stoa_get_tool_schema
        - stoa_search_apis -> Core stoa_catalog_search_apis
        """
        # CAB-605: Register demo tools with categories (feature-flagged)
        await self._register_demo_tools()

        logger.info("Registered builtin tools", count=len(self._tools))

    async def _register_demo_tools(self) -> None:
        """Register demo tools with categories.

        CAB-605: Backend-less demo tools removed. They returned "no backend configured".
        Removed tools:
        - crm_search, sales_pipeline, lead_scoring (Sales)
        - billing_invoice, expense_report, revenue_analytics (Finance)
        - inventory_lookup, order_tracking, supply_chain_status (Operations)
        - notifications_send, email_templates, chat_integration (Communications)

        RPO Easter eggs are feature-flagged via enable_demo_tools setting.
        """
        settings = get_settings()

        # CAB-605: Only register RPO Easter eggs if feature flag is enabled
        if settings.enable_demo_tools:
            await self._register_rpo_easter_eggs()
        else:
            logger.debug("Demo tools disabled (enable_demo_tools=false)")

    async def _register_rpo_easter_eggs(self) -> None:
        """Register Ready Player One Easter egg tools (demo only).

        CAB-605: These tools are feature-flagged and hidden in production.
        Set ENABLE_DEMO_TOOLS=true to enable.

        - high-five tenant: Parzival's resistance team
        - ioi tenant: IOI Corporation (antagonists)
        """
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
                category="Demo",
                tags=["oasis", "artifacts", "easter-eggs", "hunting", "demo"],
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
                category="Demo",
                tags=["rankings", "scores", "gunters", "leaderboard", "demo"],
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
                category="Demo",
                tags=["inventory", "sixers", "equipment", "ioi", "demo"],
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
                category="Demo",
                tags=["surveillance", "monitoring", "tracking", "ioi", "demo"],
                tenant_id="ioi",
            )
        )

        logger.info("Registered RPO Easter egg tools (demo mode)", count=4)

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

        CAB-605 Phase 2: Uses internal_key for storage to handle collisions
        when multiple tenants have APIs with the same name.

        Args:
            tool: ProxiedTool instance with tenant_id, api_id, and operation
        """
        # CAB-605: Use internal_key for storage (always includes tenant)
        key = tool.internal_key
        if key in self._proxied_tools:
            logger.info("Updating existing proxied tool", internal_key=key)
        self._proxied_tools[key] = tool
        logger.debug(
            "Proxied tool registered",
            tool_name=tool.name,
            display_name=tool.namespaced_name,  # May or may not include tenant
            internal_key=key,
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

    def unregister_proxied_tool(self, key: str) -> bool:
        """Unregister a proxied tool by its key.

        CAB-605 Phase 2: Accepts either internal_key (tenant::api__op) or
        legacy namespaced_name (tenant__api__op) for backward compatibility.

        Args:
            key: Internal key or namespaced name
        """
        # Try direct lookup first (internal_key format)
        if key in self._proxied_tools:
            del self._proxied_tools[key]
            logger.debug("Proxied tool unregistered", key=key)
            return True

        # CAB-605: Also try finding by legacy namespaced_name for backward compat
        for internal_key, tool in list(self._proxied_tools.items()):
            if tool.namespaced_name == key:
                del self._proxied_tools[internal_key]
                logger.debug("Proxied tool unregistered (by namespaced_name)", key=key)
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
    # Deprecation Methods (CAB-605 Phase 3)
    # =========================================================================

    def register_deprecation(
        self,
        old_name: str,
        new_name: str,
        new_args: dict[str, Any] | None = None,
        deprecation_days: int = 60,
    ) -> None:
        """Register a deprecated tool alias for backward compatibility.

        CAB-605: When consolidating tools, register deprecations to maintain
        backward compatibility. Clients calling the old tool name will be
        redirected to the new tool with appropriate arguments.

        Args:
            old_name: The deprecated tool name
            new_name: The replacement tool name
            new_args: Arguments to inject (e.g., {"action": "list"})
            deprecation_days: Days until the alias expires (default: 60)
        """
        now = datetime.now(timezone.utc)
        alias = DeprecatedToolAlias(
            old_name=old_name,
            new_name=new_name,
            new_args=new_args or {},
            deprecated_at=now,
            remove_after=now + timedelta(days=deprecation_days),
        )
        self._deprecated_aliases[old_name] = alias
        logger.info(
            "Registered deprecation alias",
            old_name=old_name,
            new_name=new_name,
            new_args=new_args,
            remove_after=alias.remove_after.isoformat(),
        )

    def resolve_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        tenant_id: str | None = None,
    ) -> tuple[AnyTool, dict[str, Any], bool]:
        """Resolve tool name, handling deprecations.

        CAB-605 Phase 3: Checks for deprecated aliases and redirects to
        new tools while logging deprecation warnings.

        Args:
            name: Tool name (may be deprecated)
            arguments: Original arguments from client
            tenant_id: Tenant context for tool lookup

        Returns:
            Tuple of (tool, merged_arguments, is_deprecated)

        Raises:
            ToolNotFoundError: If tool not found or deprecation expired
        """
        # Check for deprecated alias first
        if name in self._deprecated_aliases:
            alias = self._deprecated_aliases[name]

            # Check if past removal date
            if alias.is_expired():
                raise ToolNotFoundError(
                    f"Tool '{name}' has been removed. "
                    f"Use '{alias.new_name}' instead."
                )

            # Log deprecation warning
            days_left = alias.days_until_removal()
            logger.warning(
                "Deprecated tool called",
                old_name=name,
                new_name=alias.new_name,
                days_until_removal=days_left,
                deprecated_at=alias.deprecated_at.isoformat(),
            )

            # Merge arguments (alias args first, client args override)
            merged_args = {**alias.new_args, **arguments}

            # Lookup the new tool
            tool = self.get(alias.new_name, tenant_id)
            if not tool:
                raise ToolNotFoundError(
                    f"Replacement tool '{alias.new_name}' not found"
                )

            return tool, merged_args, True

        # Normal lookup
        tool = self.get(name, tenant_id)
        if not tool:
            raise ToolNotFoundError(f"Tool '{name}' not found")

        return tool, arguments, False

    def list_deprecated_tools(self) -> list[dict[str, Any]]:
        """List all deprecated tool aliases.

        Returns:
            List of deprecation information dictionaries
        """
        return [
            {
                "old_name": alias.old_name,
                "new_name": alias.new_name,
                "new_args": alias.new_args,
                "deprecated_at": alias.deprecated_at.isoformat(),
                "remove_after": alias.remove_after.isoformat(),
                "days_until_removal": alias.days_until_removal(),
                "is_expired": alias.is_expired(),
            }
            for alias in self._deprecated_aliases.values()
        ]

    def clear_expired_deprecations(self) -> int:
        """Remove expired deprecation aliases.

        Returns:
            Number of aliases removed
        """
        expired = [
            name for name, alias in self._deprecated_aliases.items()
            if alias.is_expired()
        ]
        for name in expired:
            del self._deprecated_aliases[name]
            logger.info("Removed expired deprecation alias", old_name=name)
        return len(expired)

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
        """Get a proxied tool by name with tenant-scoped lookup.

        CAB-605 Phase 2: When use_tenant_scoped_tools is enabled, tools are
        looked up by {api}__{operation} name within the tenant's scope.

        Args:
            name: Tool name (api__op format or full tenant__api__op)
            tenant_id: Tenant ID from JWT (required for Phase 2 lookup)

        Returns:
            ProxiedTool if found and accessible, None otherwise
        """
        settings = get_settings()
        use_tenant_scoped = getattr(settings, 'use_tenant_scoped_tools', False)

        # Phase 2: Tenant-scoped lookup
        if use_tenant_scoped and tenant_id:
            # Try internal_key lookup: tenant::api__op
            internal_key = f"{tenant_id}::{name}"
            if internal_key in self._proxied_tools:
                return self._proxied_tools[internal_key]

            # Also search by display name match
            for key, tool in self._proxied_tools.items():
                if tool.tenant_id == tenant_id and tool.namespaced_name == name:
                    return tool

        # Legacy: Direct lookup by internal_key or namespaced_name
        if name in self._proxied_tools:
            tool = self._proxied_tools[name]
            # Apply tenant filter if provided
            if tenant_id and tool.tenant_id != tenant_id:
                logger.warning(
                    "Tenant attempted to access tool from another tenant",
                    requesting_tenant=tenant_id,
                    tool_tenant=tool.tenant_id,
                    tool_name=name,
                )
                return None
            return tool

        # Search by namespaced_name in all tools
        for key, tool in self._proxied_tools.items():
            if tool.namespaced_name == name:
                # Apply tenant filter if provided
                if tenant_id and tool.tenant_id != tenant_id:
                    logger.warning(
                        "Tenant attempted to access tool from another tenant",
                        requesting_tenant=tenant_id,
                        tool_tenant=tool.tenant_id,
                        tool_name=name,
                    )
                    return None
                return tool

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
        - {api}__{operation} or {tenant}__{api}__{operation} -> Proxied tools
        - other -> Legacy tools

        CAB-605 Phase 2: tenant_id is required for proxied tool lookup when
        use_tenant_scoped_tools is enabled. The tenant is used to filter
        which tools the user can access.

        Args:
            name: Tool name
            tenant_id: Tenant context for proxied tool lookup (from JWT)

        Returns:
            Tool if found and accessible, None otherwise
        """
        # Core tools: stoa_* prefix
        if name.startswith("stoa_"):
            return self._core_tools.get(name)

        # Proxied tools: namespaced format (uses __ separator)
        if "__" in name:
            # CAB-605: Use tenant-scoped lookup
            return self.get_proxied_tool(name, tenant_id)

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

        # CAB-605: Safety net - deduplicate by name (first occurrence wins)
        # This prevents duplicate tools from being returned if registered in multiple tiers
        seen_names: set[str] = set()
        deduplicated: list[Tool] = []
        for tool in tools:
            if tool.name not in seen_names:
                seen_names.add(tool.name)
                deduplicated.append(tool)
            else:
                logger.warning(
                    "Duplicate tool filtered out",
                    tool_name=tool.name,
                    category=tool.category,
                )
        tools = deduplicated

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
                result = await self._invoke_core_tool(tool, arguments)
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

        CAB-605 Phase 3: Handles consolidated action-based tools and legacy tools.
        Action-based tools use the 'action' parameter to dispatch to specific handlers.

        Args:
            tool: CoreTool instance
            arguments: Tool invocation arguments

        Returns:
            ToolResult with execution output
        """
        settings = get_settings()

        # =====================================================================
        # CAB-605 Phase 3: Consolidated Action-Based Tools
        # =====================================================================

        # stoa_catalog - API catalog operations
        if tool.name == "stoa_catalog":
            action = arguments.get("action")
            if not action:
                return ToolResult(
                    content=[TextContent(text="action is required (list, get, search, versions, categories)")],
                    is_error=True,
                )
            return await self._handle_catalog_action(action, arguments)

        # stoa_api_spec - API specification retrieval
        elif tool.name == "stoa_api_spec":
            action = arguments.get("action")
            api_id = arguments.get("api_id")
            if not action or not api_id:
                return ToolResult(
                    content=[TextContent(text="action and api_id are required")],
                    is_error=True,
                )
            return await self._handle_api_spec_action(action, arguments)

        # stoa_subscription - Subscription management
        elif tool.name == "stoa_subscription":
            action = arguments.get("action")
            if not action:
                return ToolResult(
                    content=[TextContent(text="action is required (list, get, create, cancel, credentials, rotate_key)")],
                    is_error=True,
                )
            return await self._handle_subscription_action(action, arguments)

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
            return await self._handle_uac_action(action, arguments)

        # stoa_security - Security operations
        elif tool.name == "stoa_security":
            action = arguments.get("action")
            if not action:
                return ToolResult(
                    content=[TextContent(text="action is required (audit_log, check_permissions, list_policies)")],
                    is_error=True,
                )
            return await self._handle_security_action(action, arguments)

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
            include_inactive = arguments.get("include_inactive", False)
            return ToolResult(content=[TextContent(text=str({
                "tenants": [],
                "message": "Tenant listing requires admin scope - coming soon",
                "include_inactive": include_inactive,
            }))])

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

    # =========================================================================
    # CAB-605 Phase 3: Consolidated Tool Action Handlers
    # =========================================================================

    async def _handle_catalog_action(
        self,
        action: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Handle stoa_catalog actions."""
        if action == "list":
            return ToolResult(content=[TextContent(text=str({
                "apis": [],
                "total": 0,
                "page": arguments.get("page", 1),
                "page_size": arguments.get("page_size", 20),
                "message": "API catalog integration - coming soon",
            }))])
        elif action == "get":
            api_id = arguments.get("api_id")
            if not api_id:
                return ToolResult(
                    content=[TextContent(text="api_id is required for 'get' action")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "api_id": api_id,
                "message": f"API details for {api_id} - coming soon",
            }))])
        elif action == "search":
            query = arguments.get("query", "")
            return ToolResult(content=[TextContent(text=str({
                "query": query,
                "results": [],
                "total": 0,
                "message": "API search - coming soon",
            }))])
        elif action == "versions":
            api_id = arguments.get("api_id")
            if not api_id:
                return ToolResult(
                    content=[TextContent(text="api_id is required for 'versions' action")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "api_id": api_id,
                "versions": [],
                "message": f"Versions for {api_id} - coming soon",
            }))])
        elif action == "categories":
            categories = self.list_categories()
            return ToolResult(content=[TextContent(text=str({
                "categories": [{"name": c.name, "count": c.count} for c in categories.categories],
            }))])
        else:
            return ToolResult(
                content=[TextContent(text=f"Unknown action: {action}")],
                is_error=True,
            )

    async def _handle_api_spec_action(
        self,
        action: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Handle stoa_api_spec actions."""
        api_id = arguments.get("api_id")
        version = arguments.get("version", "latest")

        if action == "openapi":
            format_ = arguments.get("format", "json")
            return ToolResult(content=[TextContent(text=str({
                "api_id": api_id,
                "version": version,
                "format": format_,
                "spec": {},
                "message": f"OpenAPI spec for {api_id} - coming soon",
            }))])
        elif action == "docs":
            section = arguments.get("section")
            return ToolResult(content=[TextContent(text=str({
                "api_id": api_id,
                "section": section,
                "documentation": "",
                "message": f"Documentation for {api_id} - coming soon",
            }))])
        elif action == "endpoints":
            method = arguments.get("method")
            return ToolResult(content=[TextContent(text=str({
                "api_id": api_id,
                "method_filter": method,
                "endpoints": [],
                "message": f"Endpoints for {api_id} - coming soon",
            }))])
        else:
            return ToolResult(
                content=[TextContent(text=f"Unknown action: {action}")],
                is_error=True,
            )

    async def _handle_subscription_action(
        self,
        action: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Handle stoa_subscription actions."""
        if action == "list":
            return ToolResult(content=[TextContent(text=str({
                "subscriptions": [],
                "total": 0,
                "message": "Subscription listing - coming soon",
            }))])
        elif action == "get":
            subscription_id = arguments.get("subscription_id")
            if not subscription_id:
                return ToolResult(
                    content=[TextContent(text="subscription_id is required")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "subscription_id": subscription_id,
                "message": f"Subscription details - coming soon",
            }))])
        elif action == "create":
            api_id = arguments.get("api_id")
            if not api_id:
                return ToolResult(
                    content=[TextContent(text="api_id is required")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "api_id": api_id,
                "plan": arguments.get("plan"),
                "message": "Subscription creation - coming soon",
            }))])
        elif action == "cancel":
            subscription_id = arguments.get("subscription_id")
            if not subscription_id:
                return ToolResult(
                    content=[TextContent(text="subscription_id is required")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "subscription_id": subscription_id,
                "message": "Subscription cancellation - coming soon",
            }))])
        elif action == "credentials":
            subscription_id = arguments.get("subscription_id")
            if not subscription_id:
                return ToolResult(
                    content=[TextContent(text="subscription_id is required")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "subscription_id": subscription_id,
                "message": "Credentials retrieval - coming soon",
            }))])
        elif action == "rotate_key":
            subscription_id = arguments.get("subscription_id")
            if not subscription_id:
                return ToolResult(
                    content=[TextContent(text="subscription_id is required")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "subscription_id": subscription_id,
                "grace_period_hours": arguments.get("grace_period_hours", 24),
                "message": "Key rotation - coming soon",
            }))])
        else:
            return ToolResult(
                content=[TextContent(text=f"Unknown action: {action}")],
                is_error=True,
            )

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
    ) -> ToolResult:
        """Handle stoa_uac actions."""
        if action == "list":
            return ToolResult(content=[TextContent(text=str({
                "api_id": arguments.get("api_id"),
                "status": arguments.get("status"),
                "contracts": [],
                "total": 0,
                "message": "UAC contracts listing - coming soon",
            }))])
        elif action == "get":
            contract_id = arguments.get("contract_id")
            if not contract_id:
                return ToolResult(
                    content=[TextContent(text="contract_id is required")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "contract_id": contract_id,
                "message": "UAC contract details - coming soon",
            }))])
        elif action == "validate":
            contract_id = arguments.get("contract_id")
            if not contract_id:
                return ToolResult(
                    content=[TextContent(text="contract_id is required")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "contract_id": contract_id,
                "subscription_id": arguments.get("subscription_id"),
                "compliant": True,
                "message": "UAC validation - coming soon",
            }))])
        elif action == "sla":
            contract_id = arguments.get("contract_id")
            if not contract_id:
                return ToolResult(
                    content=[TextContent(text="contract_id is required")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "contract_id": contract_id,
                "time_range": arguments.get("time_range", "30d"),
                "uptime_percentage": 0,
                "latency_compliance": 0,
                "message": "SLA metrics - coming soon",
            }))])
        else:
            return ToolResult(
                content=[TextContent(text=f"Unknown action: {action}")],
                is_error=True,
            )

    async def _handle_security_action(
        self,
        action: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Handle stoa_security actions."""
        if action == "audit_log":
            return ToolResult(content=[TextContent(text=str({
                "api_id": arguments.get("api_id"),
                "user_id": arguments.get("user_id"),
                "time_range": arguments.get("time_range", "7d"),
                "limit": arguments.get("limit", 100),
                "entries": [],
                "total": 0,
                "message": "Audit log - coming soon",
            }))])
        elif action == "check_permissions":
            api_id = arguments.get("api_id")
            action_type = arguments.get("action_type")
            if not api_id or not action_type:
                return ToolResult(
                    content=[TextContent(text="api_id and action_type are required")],
                    is_error=True,
                )
            return ToolResult(content=[TextContent(text=str({
                "api_id": api_id,
                "action": action_type,
                "user_id": arguments.get("user_id"),
                "allowed": True,
                "message": "Permission check - coming soon",
            }))])
        elif action == "list_policies":
            return ToolResult(content=[TextContent(text=str({
                "api_id": arguments.get("api_id"),
                "policy_type": arguments.get("policy_type"),
                "policies": [],
                "total": 0,
                "message": "Policy listing - coming soon",
            }))])
        else:
            return ToolResult(
                content=[TextContent(text=f"Unknown action: {action}")],
                is_error=True,
            )

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

    async def _check_platform_health(
        self,
        components: list[str],
        settings: Any,
    ) -> dict[str, Any]:
        """Check health of platform components with latency tracking.

        CAB-658: Enhanced health check with:
        - Per-component latency measurement (ms)
        - Tri-state status: healthy / degraded / down / unknown
        - Async parallel checks for performance
        - Configurable thresholds per component
        """
        # Create health checker with environment-based configuration
        # Components without URLs configured will be skipped
        checker = HealthChecker(
            gateway_url=os.getenv("STOA_GATEWAY_URL", f"https://gateway.{settings.base_domain}"),
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
                    "latency_ms": comp.latency_ms,
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
            "api": "gateway",  # API is checked via gateway
            "gateway": "gateway",
            "auth": "keycloak",
        }

        if service == "all":
            components = ["gateway", "keycloak", "database", "kafka"]
        else:
            components = [component_map.get(service, service)]

        return await self._check_platform_health(components, settings)

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
        """Get the schema for a specific tool.

        CAB-605: Searches all three storage tiers:
        1. Core tools (_core_tools)
        2. Proxied tools (_proxied_tools)
        3. Legacy tools (_tools)
        """
        # Try core tools first (stoa_* prefix)
        tool = self._core_tools.get(tool_name)
        if tool:
            return {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema.model_dump() if hasattr(tool.input_schema, 'model_dump') else {
                    "type": "object",
                    "properties": tool.input_schema.properties,
                    "required": tool.input_schema.required,
                },
                "category": tool.category,
                "domain": tool.domain.value,
            }

        # Try proxied tools
        tool = self._proxied_tools.get(tool_name)
        if tool:
            return {
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": tool.input_schema.properties,
                    "required": tool.input_schema.required,
                },
                "category": tool.category,
                "tenant_id": tool.tenant_id,
            }

        # Try legacy tools
        tool = self._tools.get(tool_name)
        if tool:
            return {
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": tool.input_schema.properties,
                    "required": tool.input_schema.required,
                },
            }

        return None

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
