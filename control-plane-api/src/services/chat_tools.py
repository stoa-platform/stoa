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
# RBAC — per-tool role enforcement (CAB-1652)
# ---------------------------------------------------------------------------

# Mapping of tool name → list of roles allowed to use it.
# Roles: cpi-admin, tenant-admin, devops, viewer
TOOL_RBAC: dict[str, list[str]] = {
    "list_tenants": ["cpi-admin"],
    "list_apis": ["cpi-admin", "tenant-admin", "devops", "viewer"],
    "get_api_detail": ["cpi-admin", "tenant-admin", "devops", "viewer"],
    "list_gateway_instances": ["cpi-admin", "tenant-admin", "devops"],
    "list_deployments": ["cpi-admin", "tenant-admin", "devops"],
    "platform_info": ["cpi-admin", "tenant-admin", "devops", "viewer"],
    "search_docs": ["cpi-admin", "tenant-admin", "devops", "viewer"],
    "list_my_subscriptions": ["cpi-admin", "tenant-admin", "devops", "viewer"],
    "subscribe_api": ["cpi-admin", "tenant-admin", "devops"],
    "revoke_subscription": ["cpi-admin", "tenant-admin"],
}

# Tools that modify state and require explicit user confirmation before execution.
MUTATION_TOOLS: set[str] = {"subscribe_api", "revoke_subscription"}


def filter_tools_for_role(tools: list[dict[str, Any]], user_roles: list[str]) -> list[dict[str, Any]]:
    """Return only the tools the user's roles are allowed to use.

    A tool is included if any of the user's roles appears in its RBAC list.
    Unknown tools (not in TOOL_RBAC) are excluded by default.
    """
    return [t for t in tools if _role_allowed(t["name"], user_roles)]


def _role_allowed(tool_name: str, user_roles: list[str]) -> bool:
    """Check if any of the user's roles is allowed to use the given tool."""
    allowed = TOOL_RBAC.get(tool_name)
    if allowed is None:
        return False
    return any(r in allowed for r in user_roles)


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
    {
        "name": "search_docs",
        "description": (
            "Search STOA platform documentation, guides, ADRs, and blog posts. "
            "Returns matching articles with titles, URLs, and snippets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (1-20)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_my_subscriptions",
        "description": "List the current user's API subscriptions with their status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: active, pending, revoked, suspended.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "subscribe_api",
        "description": (
            "Subscribe to an API. This is a MUTATION that requires user confirmation. "
            "Always present the details and ask the user to confirm before calling this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "api_id": {
                    "type": "string",
                    "description": "The API ID to subscribe to.",
                },
                "tenant_id": {
                    "type": "string",
                    "description": "The tenant that owns the API.",
                },
            },
            "required": ["api_id", "tenant_id"],
        },
    },
    {
        "name": "revoke_subscription",
        "description": (
            "Revoke an active subscription. This is a MUTATION that requires user confirmation. "
            "Always present the details and ask the user to confirm before calling this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subscription_id": {
                    "type": "string",
                    "description": "The subscription ID to revoke.",
                },
            },
            "required": ["subscription_id"],
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
    *,
    user_roles: list[str] | None = None,
    user_id: str | None = None,
) -> str:
    """Execute a tool call and return the result as a JSON string.

    If *user_roles* is provided the call is rejected when the user lacks
    permission — defence-in-depth alongside ``filter_tools_for_role``.
    """
    if user_roles is not None and not _role_allowed(tool_name, user_roles):
        logger.warning("RBAC denied tool %s for roles %s", tool_name, user_roles)
        return json.dumps({"error": f"Access denied: insufficient permissions for tool '{tool_name}'"})

    # Input validation and sanitization (CAB-1656)
    from ..services.chat_security import validate_tool_input

    tool_input, violations = validate_tool_input(tool_input)
    if violations:
        logger.info("Tool input sanitized for %s: %s", tool_name, violations)

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
        elif tool_name == "search_docs":
            return await _exec_search_docs(tool_input)
        elif tool_name == "list_my_subscriptions":
            return await _exec_list_my_subscriptions(session, tool_input, user_id=user_id)
        elif tool_name == "subscribe_api":
            return await _exec_subscribe_api(session, tool_input, user_id=user_id)
        elif tool_name == "revoke_subscription":
            return await _exec_revoke_subscription(session, tool_input, user_id=user_id)
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
            "tagline": "The European Agent Gateway",
            "description": (
                "Open-source, AI-native API management platform (Apache 2.0) "
                "that bridges traditional APIs and AI agents through the Model Context Protocol (MCP)."
            ),
            "license": "Apache 2.0",
            "documentation": "https://docs.gostoa.dev",
            "architecture": {
                "control_plane": {
                    "api": "Python 3.11, FastAPI",
                    "console_ui": "React 18, TypeScript",
                    "developer_portal": "React, Vite, TypeScript",
                    "auth": "Keycloak (OIDC, SAML, OAuth 2.1)",
                },
                "data_plane": {
                    "stoa_gateway": "Rust (Tokio, axum) — high-performance, MCP-native",
                    "deployment_modes": [
                        "edge-mcp (production)",
                        "sidecar (planned)",
                        "proxy (planned)",
                        "shadow (planned)",
                    ],
                },
            },
            "supported_gateways": [
                {"name": "STOA Gateway", "technology": "Rust", "role": "Primary, MCP-native"},
                {"name": "Kong", "technology": "DB-less", "role": "Legacy adapter"},
                {"name": "Gravitee", "technology": "APIM v4", "role": "Legacy adapter"},
                {"name": "webMethods", "technology": "IBM/Software AG", "role": "Legacy adapter"},
                {"name": "Apigee", "technology": "Google Cloud", "role": "Legacy adapter"},
                {"name": "Azure APIM", "technology": "Microsoft", "role": "Legacy adapter"},
                {"name": "AWS API Gateway", "technology": "Amazon", "role": "Legacy adapter"},
            ],
            "key_features": [
                "MCP Gateway — AI agents discover and call APIs via Model Context Protocol",
                "Universal API Contract (UAC) — define once, expose everywhere",
                "Multi-tenant architecture — hard isolation per tenant",
                "AI Gateway — token metering, semantic caching, smart LLM routing",
                "GitOps Native — ArgoCD-based declarative provisioning",
                "Legacy Bridge — migration paths from 7+ enterprise gateways",
                "European Sovereign — EU hosting, NIS2/DORA supportive",
                "RBAC — 4 roles (cpi-admin, tenant-admin, devops, viewer) via Keycloak",
            ],
            "rbac_roles": {
                "cpi-admin": "Full platform administration",
                "tenant-admin": "Own tenant management",
                "devops": "Deploy and promote APIs",
                "viewer": "Read-only access",
            },
            "status": "operational",
        }
    )


async def _exec_list_my_subscriptions(
    session: AsyncSession, tool_input: dict[str, Any], *, user_id: str | None = None
) -> str:
    if not user_id:
        return json.dumps({"error": "User context required"})

    from ..repositories.subscription import SubscriptionRepository

    repo = SubscriptionRepository(session)
    status_filter = tool_input.get("status")
    subs, total = await repo.list_by_subscriber(
        subscriber_id=user_id,
        status=status_filter,
        page=1,
        page_size=20,
    )
    return json.dumps(
        {
            "total": total,
            "subscriptions": [
                {
                    "id": str(s.id),
                    "api_name": getattr(s, "api_name", None),
                    "api_id": str(getattr(s, "api_id", "")),
                    "status": str(getattr(s, "status", "unknown")),
                    "tenant_id": getattr(s, "tenant_id", None),
                    "created_at": str(getattr(s, "created_at", "")),
                }
                for s in subs
            ],
        }
    )


async def _exec_subscribe_api(session: AsyncSession, tool_input: dict[str, Any], *, user_id: str | None = None) -> str:
    if not user_id:
        return json.dumps({"error": "User context required"})

    from ..models.subscription import Subscription
    from ..repositories.subscription import SubscriptionRepository

    api_id = tool_input.get("api_id", "")
    tenant_id = tool_input.get("tenant_id", "")
    if not api_id or not tenant_id:
        return json.dumps({"error": "api_id and tenant_id are required"})

    repo = SubscriptionRepository(session)

    # Check for existing active/pending subscription
    existing = await repo.get_by_application_and_api(user_id, api_id)
    if existing and existing.status in ("active", "pending"):
        return json.dumps(
            {
                "status": "already_subscribed",
                "subscription_id": str(existing.id),
                "subscription_status": str(existing.status),
                "message": f"You already have an {existing.status} subscription to this API.",
            }
        )

    # Create the subscription in PENDING status
    sub = Subscription(
        subscriber_id=user_id,
        api_id=api_id,
        tenant_id=tenant_id,
        status="pending",
    )
    created = await repo.create(sub)
    return json.dumps(
        {
            "status": "created",
            "subscription_id": str(created.id),
            "subscription_status": "pending",
            "message": "Subscription request created. It will be reviewed by a tenant admin.",
        }
    )


async def _exec_revoke_subscription(
    session: AsyncSession, tool_input: dict[str, Any], *, user_id: str | None = None
) -> str:
    if not user_id:
        return json.dumps({"error": "User context required"})

    from ..repositories.subscription import SubscriptionRepository

    subscription_id = tool_input.get("subscription_id", "")
    if not subscription_id:
        return json.dumps({"error": "subscription_id is required"})

    repo = SubscriptionRepository(session)
    sub = await repo.get_by_id(subscription_id)
    if sub is None:
        return json.dumps({"error": "Subscription not found"})

    # Only the subscriber or an admin can revoke
    if sub.subscriber_id != user_id:
        return json.dumps({"error": "You can only revoke your own subscriptions"})

    if sub.status not in ("active", "pending"):
        return json.dumps(
            {"error": f"Cannot revoke subscription in '{sub.status}' status. Only active or pending can be revoked."}
        )

    await repo.update_status(sub, "revoked", reason="Revoked via chat assistant", actor_id=user_id)
    return json.dumps(
        {
            "status": "revoked",
            "subscription_id": str(sub.id),
            "message": "Subscription has been revoked successfully.",
        }
    )


async def _exec_search_docs(tool_input: dict[str, Any]) -> str:
    from ..routers.docs_search import get_docs_search_service

    service = get_docs_search_service()
    query = tool_input.get("query", "")
    limit = min(max(tool_input.get("limit", 5), 1), 20)

    response = await service.search(query=query, limit=limit)
    return json.dumps(
        {
            "query": response.query,
            "total": response.total,
            "results": [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "category": r.category,
                }
                for r in response.results
            ],
        }
    )
