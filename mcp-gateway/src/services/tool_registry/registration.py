"""Tool registration mixin.

CAB-841: Extracted from tool_registry.py for modularity.
CAB-603: Registration methods for core, proxied, and legacy tools.
CAB-605: Tool consolidation and RPO Easter eggs.
"""

from typing import TYPE_CHECKING, Any

import structlog

from ...config import get_settings
from ...models import (
    Tool,
    CoreTool,
    ProxiedTool,
    ToolInputSchema,
)
from ...tools import CORE_TOOLS

if TYPE_CHECKING:
    from . import ToolRegistry

logger = structlog.get_logger(__name__)


class RegistrationMixin:
    """Mixin providing tool registration methods."""

    # Type hints for attributes from ToolRegistry
    _core_tools: dict[str, CoreTool]
    _proxied_tools: dict[str, ProxiedTool]
    _tools: dict[str, Tool]

    async def _register_core_tools(self) -> None:
        """Register consolidated core platform tools.

        CAB-605 Phase 3: Consolidated action-based tools (12 total).
        Tools are defined in src/tools/consolidated_tools.py.
        """
        for core_tool in CORE_TOOLS:
            self.register_core_tool(core_tool)
        logger.info("Registered core tools", count=len(self._core_tools))

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
