"""Tool lookup and listing mixin.

CAB-841: Extracted from tool_registry.py for modularity.
CAB-603: Lookup methods for core, proxied, and legacy tools.
"""

from typing import TYPE_CHECKING, Any

import structlog

from ...config import get_settings
from ...models import (
    Tool,
    CoreTool,
    ProxiedTool,
    ExternalTool,
    AnyTool,
    ListToolsResponse,
    ListCategoriesResponse,
    ListTagsResponse,
    ToolCategory,
)

if TYPE_CHECKING:
    from . import ToolRegistry

logger = structlog.get_logger(__name__)


class LookupMixin:
    """Mixin providing tool lookup and listing methods."""

    # Type hints for attributes from ToolRegistry
    _core_tools: dict[str, CoreTool]
    _proxied_tools: dict[str, ProxiedTool]
    _external_tools: dict[str, ExternalTool]
    _tools: dict[str, Tool]

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

        # External tools: check by name
        external = self.get_external_tool(name)
        if external:
            return external

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

        # Add external tools (from external MCP servers like Linear, GitHub)
        for external_tool in self._external_tools.values():
            tools.append(Tool(
                name=external_tool.name,
                description=external_tool.description,
                input_schema=external_tool.input_schema,
                category=external_tool.category or "External",
                tags=external_tool.tags + [f"server:{external_tool.server_name}"],
                version=external_tool.version,
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

        # Count external tool categories
        for tool in self._external_tools.values():
            cat = tool.category or "External"
            category_counts[cat] = category_counts.get(cat, 0) + 1

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

        # Count external tool tags
        for tool in self._external_tools.values():
            for tag in tool.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            # Also add server tag
            server_tag = f"server:{tool.server_name}"
            tag_counts[server_tag] = tag_counts.get(server_tag, 0) + 1

        return ListTagsResponse(
            tags=sorted(tag_counts.keys()),
            tag_counts=tag_counts,
        )

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

        # Try external tools
        for ext_tool in self._external_tools.values():
            if ext_tool.name == tool_name:
                return {
                    "name": ext_tool.name,
                    "description": ext_tool.description,
                    "input_schema": {
                        "type": "object",
                        "properties": ext_tool.input_schema.properties if ext_tool.input_schema else {},
                        "required": ext_tool.input_schema.required if ext_tool.input_schema else [],
                    },
                    "category": ext_tool.category or "External",
                    "server_name": ext_tool.server_name,
                }

        return None
