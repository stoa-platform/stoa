"""Chat tool definitions and executor for the agentic loop (CAB-287).

Provides CHAT_TOOLS (Anthropic tools format) and execute_tool() which
dispatches tool calls to the appropriate repository queries.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic tools format)
# ---------------------------------------------------------------------------

CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_tenants",
        "description": "List all tenants accessible to the current user. Returns tenant names, IDs, and status.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_apis",
        "description": "List APIs in the catalog. Optionally filter by category or search term.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Search term to filter APIs by name or description.",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by API category.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_api_detail",
        "description": "Get detailed information about a specific API by its ID, including endpoints and version.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {
                    "type": "string",
                    "description": "The tenant ID that owns the API.",
                },
                "api_id": {
                    "type": "string",
                    "description": "The unique API identifier.",
                },
            },
            "required": ["tenant_id", "api_id"],
        },
    },
    {
        "name": "list_gateway_instances",
        "description": "List all gateway instances and their current status (online/offline).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_deployments",
        "description": "List API deployments across gateways with their sync status.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "platform_info",
        "description": "Get STOA platform information including version, features, and overall status.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


async def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    session: AsyncSession,
) -> str:
    """Execute a tool call and return the result as a JSON string."""
    try:
        if tool_name == "list_tenants":
            return await _exec_list_tenants(session)
        elif tool_name == "list_apis":
            return await _exec_list_apis(session, tool_input)
        elif tool_name == "get_api_detail":
            return await _exec_get_api_detail(session, tool_input)
        elif tool_name == "list_gateway_instances":
            return await _exec_list_gateway_instances(session)
        elif tool_name == "list_deployments":
            return await _exec_list_deployments(session)
        elif tool_name == "platform_info":
            return _exec_platform_info()
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as exc:
        logger.warning("Tool execution failed: %s — %s", tool_name, exc, exc_info=True)
        return json.dumps({"error": f"Tool {tool_name} failed: {exc!s}"})


# ---------------------------------------------------------------------------
# Individual tool handlers
# ---------------------------------------------------------------------------


async def _exec_list_tenants(session: AsyncSession) -> str:
    from ..repositories.tenant import TenantRepository

    repo = TenantRepository(session)
    tenants = await repo.list_all()
    return json.dumps(
        [
            {
                "id": t.id,
                "name": t.name,
                "display_name": getattr(t, "display_name", t.name),
                "status": getattr(t, "status", "active"),
            }
            for t in tenants
        ]
    )


async def _exec_list_apis(session: AsyncSession, tool_input: dict[str, Any]) -> str:
    from ..repositories.catalog import CatalogRepository

    repo = CatalogRepository(session)
    apis, total = await repo.get_portal_apis(
        search=tool_input.get("search"),
        category=tool_input.get("category"),
        page=1,
        page_size=20,
    )
    return json.dumps(
        {
            "total": total,
            "apis": [
                {
                    "id": str(a.id),
                    "name": a.name,
                    "version": getattr(a, "version", None),
                    "status": getattr(a, "status", None),
                    "category": getattr(a, "category", None),
                    "tenant_id": getattr(a, "tenant_id", None),
                }
                for a in apis
            ],
        }
    )


async def _exec_get_api_detail(session: AsyncSession, tool_input: dict[str, Any]) -> str:
    from ..repositories.catalog import CatalogRepository

    repo = CatalogRepository(session)
    api = await repo.get_api_by_id(
        tenant_id=tool_input["tenant_id"],
        api_id=tool_input["api_id"],
    )
    if api is None:
        return json.dumps({"error": "API not found"})
    return json.dumps(
        {
            "id": str(api.id),
            "name": api.name,
            "version": getattr(api, "version", None),
            "description": getattr(api, "description", None),
            "status": getattr(api, "status", None),
            "category": getattr(api, "category", None),
            "tenant_id": getattr(api, "tenant_id", None),
            "base_url": getattr(api, "base_url", None),
        }
    )


async def _exec_list_gateway_instances(session: AsyncSession) -> str:
    from ..repositories.gateway_instance import GatewayInstanceRepository

    repo = GatewayInstanceRepository(session)
    instances, total = await repo.list_all(page=1, page_size=50)
    return json.dumps(
        {
            "total": total,
            "instances": [
                {
                    "id": str(i.id),
                    "name": i.name,
                    "display_name": getattr(i, "display_name", i.name),
                    "gateway_type": str(getattr(i, "gateway_type", "unknown")),
                    "status": str(getattr(i, "status", "unknown")),
                    "base_url": getattr(i, "base_url", None),
                }
                for i in instances
            ],
        }
    )


async def _exec_list_deployments(session: AsyncSession) -> str:
    from ..repositories.gateway_deployment import GatewayDeploymentRepository

    repo = GatewayDeploymentRepository(session)
    deployments, total = await repo.list_all(page=1, page_size=50)
    return json.dumps(
        {
            "total": total,
            "deployments": [
                {
                    "id": str(d.id),
                    "api_catalog_id": str(getattr(d, "api_catalog_id", "")),
                    "gateway_instance_id": str(getattr(d, "gateway_instance_id", "")),
                    "sync_status": str(getattr(d, "sync_status", "unknown")),
                }
                for d in deployments
            ],
        }
    )


def _exec_platform_info() -> str:
    return json.dumps(
        {
            "name": "STOA Platform",
            "version": "1.0.0",
            "description": "The European Agent Gateway — AI-Native API Management",
            "features": [
                "Universal API Contract (UAC)",
                "Multi-gateway orchestration",
                "MCP protocol support",
                "RBAC with Keycloak",
                "GitOps deployments",
            ],
            "status": "operational",
        }
    )
