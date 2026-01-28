# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""CAB-660: MCP Tool Handlers with Real Database Backend.

Handlers that connect MCP tools to real backends via service layer.

ADR-001 Compliance (CAB-672):
- Uses CoreAPIClient to access data via Control-Plane-API
- No direct database access

CAB-659: Uses standardized error codes from src/errors.py
"""

import json
from typing import Any

import structlog

from ..clients import get_core_api_client, CoreAPIClient
from ..errors import (
    STOAErrorCode,
    error_result,
    AuthRequiredError,
    InvalidActionError,
    InvalidParamsError,
    APINotFoundError,
    SubscriptionNotFoundError,
    BackendError,
)
from ..middleware.auth import TokenClaims

logger = structlog.get_logger(__name__)


class STOAToolHandlers:
    """MCP Tool Handlers for STOA Platform.

    ADR-001 Compliant: Uses CoreAPIClient to access data via Control-Plane-API.
    No direct database access.
    """

    def __init__(self):
        """Initialize tool handlers.

        CoreAPIClient must be initialized before using handlers.
        """
        pass

    def _get_token(self, claims: TokenClaims | None) -> str:
        """Extract bearer token from claims for Core API calls."""
        if claims is None or not claims.raw_token:
            logger.warning("No token available for Core API call")
            raise ValueError("Authentication required")
        return claims.raw_token

    def _get_token_optional(self, claims: TokenClaims | None) -> str | None:
        """Extract bearer token from claims, returning None if not available.

        Used for read-only operations that can fall back to demo data.
        """
        if claims is None or not claims.raw_token:
            return None
        return claims.raw_token

    def _is_platform_admin(self, claims: TokenClaims | None) -> bool:
        """Check if user is platform admin."""
        if claims is None:
            return False
        return any(role in claims.roles for role in ["cpi-admin", "platform-admin", "admin"])

    def _is_tenant_admin(self, claims: TokenClaims | None) -> bool:
        """Check if user is tenant admin."""
        if claims is None:
            return False
        return any(role in claims.roles for role in ["tenant-admin"]) or self._is_platform_admin(claims)

    # =========================================================================
    # TENANT HANDLERS
    # =========================================================================

    async def handle_tenants(
        self,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_tenants tool calls via Core API.

        Falls back to demo data when no token is available (public read mode).
        """
        token = self._get_token_optional(claims)

        if token:
            # Authenticated mode: use Core API
            try:
                client = get_core_api_client()
                tenants = await client.list_tenants(token)

                logger.info(
                    "Listed tenants via Core API",
                    user_id=claims.subject if claims else "anonymous",
                    count=len(tenants),
                )

                return {
                    "tenants": tenants,
                    "total": len(tenants),
                }
            except Exception as e:
                logger.error("Failed to list tenants", error=str(e))
                return error_result(
                    STOAErrorCode.BACKEND_ERROR,
                    "Failed to list tenants from backend",
                    details={"backend_error": str(e)},
                )
        else:
            # Public mode: return demo tenants (RPO demo)
            logger.info("Returning demo tenants (no auth)")
            demo_tenants = [
                {
                    "id": "high-five",
                    "name": "High Five",
                    "display_name": "High Five - The Resistance",
                    "description": "Parzival's team of elite gunters hunting for Halliday's Easter Egg",
                    "status": "active",
                },
                {
                    "id": "ioi",
                    "name": "IOI",
                    "display_name": "Innovative Online Industries",
                    "description": "The corporate antagonist seeking to monetize the OASIS",
                    "status": "active",
                },
                {
                    "id": "oasis",
                    "name": "OASIS",
                    "display_name": "OASIS Platform Administration",
                    "description": "Platform-level administration by Halliday's legacy",
                    "status": "active",
                },
            ]
            return {
                "tenants": demo_tenants,
                "total": len(demo_tenants),
                "mode": "demo",
                "note": "Showing demo data. Authenticate for full access.",
            }

    # =========================================================================
    # CATALOG HANDLERS
    # =========================================================================

    async def handle_catalog(
        self,
        action: str,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_catalog tool calls via Core API.

        Falls back to demo data when no token is available (public read mode).
        """
        token = self._get_token_optional(claims)
        tenant_id = claims.tenant_id if claims else None

        # Demo APIs for public mode (RPO themed)
        demo_apis = [
            {
                "id": "avatar-search-api",
                "name": "Avatar Search API",
                "description": "Search OASIS players by gamertag, clan, or achievements",
                "version": "1.0.0",
                "status": "published",
                "category": "Avatar",
                "tenant_id": "oasis",
            },
            {
                "id": "economy-transfer-api",
                "name": "Economy Transfer API",
                "description": "Transfer OASIS coins between players",
                "version": "1.0.0",
                "status": "published",
                "category": "Economy",
                "tenant_id": "oasis",
            },
            {
                "id": "inventory-artifacts-api",
                "name": "Inventory Artifacts API",
                "description": "Check artifact ownership and provenance history",
                "version": "1.0.0",
                "status": "published",
                "category": "Inventory",
                "tenant_id": "oasis",
            },
            {
                "id": "quests-api",
                "name": "Quests API",
                "description": "Create and manage OASIS quests",
                "version": "1.0.0",
                "status": "published",
                "category": "Quests",
                "tenant_id": "oasis",
            },
            {
                "id": "events-api",
                "name": "Events API",
                "description": "Broadcast announcements to OASIS players",
                "version": "1.0.0",
                "status": "published",
                "category": "Events",
                "tenant_id": "oasis",
            },
        ]

        if action == "list":
            if token:
                try:
                    client = get_core_api_client()
                    apis = await client.list_apis(
                        token=token,
                        tenant_id=tenant_id,
                        status=params.get("status"),
                        category=params.get("category"),
                    )
                    return {
                        "apis": apis,
                        "total": len(apis),
                        "page": params.get("page", 1),
                        "page_size": params.get("page_size", 20),
                    }
                except Exception as e:
                    logger.error("Failed to list APIs", error=str(e))
                    return error_result(
                        STOAErrorCode.BACKEND_ERROR,
                        "Failed to list APIs from backend",
                        details={"backend_error": str(e)},
                    )
            else:
                # Public mode: return demo APIs
                logger.info("Returning demo APIs (no auth)")
                return {
                    "apis": demo_apis,
                    "total": len(demo_apis),
                    "page": 1,
                    "page_size": 20,
                    "mode": "demo",
                    "note": "Showing demo APIs. Authenticate for full access.",
                }

        elif action == "get":
            api_id = params.get("api_id")
            if not api_id:
                return error_result(
                    STOAErrorCode.INVALID_PARAMS,
                    "Parameter 'api_id' is required",
                    details={"parameter": "api_id", "action": action},
                )
            if token:
                try:
                    client = get_core_api_client()
                    api = await client.get_api(api_id, token)
                    return api
                except Exception as e:
                    logger.error("Failed to get API", api_id=api_id, error=str(e))
                    return error_result(
                        STOAErrorCode.API_NOT_FOUND,
                        f"API '{api_id}' not found",
                        details={"api_id": api_id, "backend_error": str(e)},
                    )
            else:
                # Try to find in demo APIs
                for api in demo_apis:
                    if api["id"] == api_id:
                        return api
                return error_result(
                    STOAErrorCode.API_NOT_FOUND,
                    f"API '{api_id}' not found",
                    details={"api_id": api_id, "mode": "demo"},
                )

        elif action == "search":
            query = params.get("query")
            if not query:
                return error_result(
                    STOAErrorCode.INVALID_PARAMS,
                    "Parameter 'query' is required",
                    details={"parameter": "query", "action": action},
                )

            if token:
                try:
                    client = get_core_api_client()
                    apis = await client.list_apis(token=token, tenant_id=tenant_id)
                except Exception as e:
                    logger.error("Failed to search APIs", error=str(e))
                    return error_result(
                        STOAErrorCode.BACKEND_ERROR,
                        "Failed to search APIs",
                        details={"backend_error": str(e)},
                    )
            else:
                apis = demo_apis

            # Filter locally
            query_lower = query.lower()
            filtered = [
                api for api in apis
                if query_lower in api.get("name", "").lower()
                or query_lower in api.get("description", "").lower()
            ]
            result = {
                "apis": filtered,
                "total": len(filtered),
                "query": query,
            }
            if not token:
                result["mode"] = "demo"
            return result

        elif action == "versions":
            api_id = params.get("api_id")
            if not api_id:
                return error_result(
                    STOAErrorCode.INVALID_PARAMS,
                    "Parameter 'api_id' is required",
                    details={"parameter": "api_id", "action": action},
                )
            if token:
                try:
                    client = get_core_api_client()
                    api = await client.get_api(api_id, token)
                    return {
                        "api_id": api_id,
                        "versions": [
                            {
                                "version": api.get("version", "1.0.0"),
                                "status": api.get("status"),
                            }
                        ],
                    }
                except Exception as e:
                    logger.error("Failed to get API versions", api_id=api_id, error=str(e))
                    return error_result(
                        STOAErrorCode.API_NOT_FOUND,
                        f"API '{api_id}' not found",
                        details={"api_id": api_id, "backend_error": str(e)},
                    )
            else:
                # Demo mode
                for api in demo_apis:
                    if api["id"] == api_id:
                        return {
                            "api_id": api_id,
                            "versions": [{"version": api["version"], "status": api["status"]}],
                            "mode": "demo",
                        }
                return error_result(
                    STOAErrorCode.API_NOT_FOUND,
                    f"API '{api_id}' not found",
                    details={"api_id": api_id, "mode": "demo"},
                )

        elif action == "categories":
            if token:
                try:
                    client = get_core_api_client()
                    apis = await client.list_apis(token=token)
                except Exception as e:
                    logger.error("Failed to get categories", error=str(e))
                    return error_result(
                        STOAErrorCode.BACKEND_ERROR,
                        "Failed to get API categories",
                        details={"backend_error": str(e)},
                    )
            else:
                apis = demo_apis

            categories = {}
            for api in apis:
                cat = api.get("category", "uncategorized")
                categories[cat] = categories.get(cat, 0) + 1
            result = {
                "categories": [
                    {"name": name, "count": count}
                    for name, count in categories.items()
                ]
            }
            if not token:
                result["mode"] = "demo"
            return result

        else:
            return error_result(
                STOAErrorCode.INVALID_ACTION,
                f"Unknown action: '{action}'",
                details={"action": action, "valid_actions": ["list", "get", "search", "versions", "categories"]},
            )

    # =========================================================================
    # API SPEC HANDLERS
    # =========================================================================

    async def handle_api_spec(
        self,
        action: str,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_api_spec tool calls via Core API."""
        try:
            token = self._get_token(claims)
            client = get_core_api_client()

            api_id = params.get("api_id")
            if not api_id:
                return error_result(
                    STOAErrorCode.INVALID_PARAMS,
                    "Parameter 'api_id' is required",
                    details={"parameter": "api_id", "action": action},
                )

            if action == "openapi":
                try:
                    spec = await client.get_api_spec(api_id, token)
                    return {
                        "api_id": api_id,
                        "format": params.get("format", "json"),
                        "spec": spec,
                    }
                except Exception:
                    # Fallback: build spec from API metadata
                    api = await client.get_api(api_id, token)
                    return {
                        "api_id": api_id,
                        "format": params.get("format", "json"),
                        "spec": {
                            "openapi": "3.0.0",
                            "info": {
                                "title": api.get("name"),
                                "description": api.get("description"),
                                "version": api.get("version", "1.0.0"),
                            },
                            "paths": {},
                        },
                    }

            elif action == "docs":
                api = await client.get_api(api_id, token)
                return {
                    "api_id": api_id,
                    "section": params.get("section"),
                    "documentation": (
                        f"# {api.get('name')}\n\n"
                        f"{api.get('description', '')}\n\n"
                        f"## Details\n\n"
                        f"- Status: {api.get('status')}\n"
                        f"- Version: {api.get('version')}\n"
                    ),
                }

            elif action == "endpoints":
                api = await client.get_api(api_id, token)
                endpoints = api.get("endpoints", [])
                method_filter = params.get("method")
                if method_filter:
                    endpoints = [e for e in endpoints if e.get("method") == method_filter]
                return {
                    "api_id": api_id,
                    "endpoints": endpoints,
                    "total": len(endpoints),
                }

            else:
                return error_result(
                    STOAErrorCode.INVALID_ACTION,
                    f"Unknown action: '{action}'",
                    details={"action": action, "valid_actions": ["openapi", "docs", "endpoints"]},
                )

        except ValueError as e:
            return error_result(
                STOAErrorCode.AUTH_REQUIRED,
                str(e),
            )
        except Exception as e:
            logger.error("Failed to handle api_spec action", action=action, error=str(e))
            return error_result(
                STOAErrorCode.BACKEND_ERROR,
                f"Failed to handle api_spec action: {action}",
                details={"action": action, "backend_error": str(e)},
            )

    # =========================================================================
    # SUBSCRIPTION HANDLERS (MCP Subscriptions via Core API)
    # =========================================================================

    async def handle_subscription(
        self,
        action: str,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_subscription tool calls via Core API."""
        try:
            token = self._get_token(claims)
            client = get_core_api_client()
            user_id = claims.subject if claims else None
            tenant_id = claims.tenant_id if claims else None

            if action == "list":
                subs = await client.list_mcp_subscriptions(
                    token=token,
                    user_id=user_id if not self._is_tenant_admin(claims) else None,
                    tenant_id=tenant_id,
                    status=params.get("status"),
                )
                return {
                    "subscriptions": subs,
                    "total": len(subs),
                }

            elif action == "get":
                sub_id = params.get("subscription_id")
                if not sub_id:
                    return error_result(
                        STOAErrorCode.INVALID_PARAMS,
                        "Parameter 'subscription_id' is required",
                        details={"parameter": "subscription_id", "action": action},
                    )
                sub = await client.get_mcp_subscription(sub_id, token)
                return sub

            elif action == "create":
                server_id = params.get("server_id") or params.get("api_id")
                if not server_id:
                    return error_result(
                        STOAErrorCode.INVALID_PARAMS,
                        "Parameter 'server_id' is required",
                        details={"parameter": "server_id", "action": action},
                    )
                sub = await client.create_mcp_subscription(
                    data={
                        "server_id": server_id,
                        "plan": params.get("plan", "standard"),
                    },
                    token=token,
                )
                return {
                    "subscription_id": sub.get("id"),
                    "server_id": server_id,
                    "status": sub.get("status"),
                    "api_key": sub.get("api_key", ""),
                    "message": "Store your API key securely. It won't be shown again.",
                }

            elif action == "cancel":
                sub_id = params.get("subscription_id")
                if not sub_id:
                    return error_result(
                        STOAErrorCode.INVALID_PARAMS,
                        "Parameter 'subscription_id' is required",
                        details={"parameter": "subscription_id", "action": action},
                    )
                await client.delete_mcp_subscription(sub_id, token)
                return {
                    "subscription_id": sub_id,
                    "status": "cancelled",
                    "message": "Subscription cancelled successfully",
                }

            elif action == "credentials":
                sub_id = params.get("subscription_id")
                if not sub_id:
                    return error_result(
                        STOAErrorCode.INVALID_PARAMS,
                        "Parameter 'subscription_id' is required",
                        details={"parameter": "subscription_id", "action": action},
                    )
                sub = await client.get_mcp_subscription(sub_id, token)
                return {
                    "subscription_id": sub_id,
                    "server_id": sub.get("server_id"),
                    "status": sub.get("status"),
                    "api_key_prefix": sub.get("api_key_prefix", "stoa_mcp_****"),
                    "message": "API key is masked for security. Use rotate_key to generate a new one.",
                }

            elif action == "rotate_key":
                sub_id = params.get("subscription_id")
                if not sub_id:
                    return error_result(
                        STOAErrorCode.INVALID_PARAMS,
                        "Parameter 'subscription_id' is required",
                        details={"parameter": "subscription_id", "action": action},
                    )
                result = await client.rotate_api_key(
                    subscription_id=sub_id,
                    token=token,
                    grace_period_hours=params.get("grace_period_hours", 24),
                )
                return {
                    "subscription_id": sub_id,
                    "new_api_key": result.get("new_api_key"),
                    "grace_period_hours": params.get("grace_period_hours", 24),
                    "message": f"New API key generated. Old key valid for {params.get('grace_period_hours', 24)}h.",
                }

            else:
                return error_result(
                    STOAErrorCode.INVALID_ACTION,
                    f"Unknown action: '{action}'",
                    details={"action": action, "valid_actions": ["list", "get", "create", "cancel", "credentials", "rotate_key"]},
                )

        except ValueError as e:
            return error_result(
                STOAErrorCode.AUTH_REQUIRED,
                str(e),
            )
        except Exception as e:
            logger.error("Failed to handle subscription action", action=action, error=str(e))
            return error_result(
                STOAErrorCode.BACKEND_ERROR,
                f"Failed to handle subscription action: {action}",
                details={"action": action, "backend_error": str(e)},
            )

    # =========================================================================
    # SECURITY HANDLERS
    # =========================================================================

    async def handle_security(
        self,
        action: str,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_security tool calls.

        Note: Some security operations may need additional Core API endpoints.
        """
        try:
            token = self._get_token(claims)
            client = get_core_api_client()

            if action == "audit_log":
                # Audit logs would require a Core API endpoint
                # For now, return a placeholder
                return {
                    "audit_logs": [],
                    "total": 0,
                    "time_range": params.get("time_range", "24h"),
                    "message": "Audit logs available via Core API /v1/audit/logs",
                }

            elif action == "check_permissions":
                api_id = params.get("api_id")
                action_type = params.get("action_type")
                if not api_id or not action_type:
                    return error_result(
                        STOAErrorCode.INVALID_PARAMS,
                        "Parameters 'api_id' and 'action_type' are required",
                        details={"required_params": ["api_id", "action_type"], "action": action},
                    )

                # Check if user can access the API
                try:
                    api = await client.get_api(api_id, token)
                    allowed = True
                    reason = "Access granted"
                except Exception:
                    allowed = False
                    reason = "API not found or access denied"

                return {
                    "api_id": api_id,
                    "action": action_type,
                    "allowed": allowed,
                    "reason": reason,
                    "your_roles": claims.roles if claims else [],
                }

            elif action == "list_policies":
                # Return standard policies
                return {
                    "policies": [
                        {
                            "id": "pol-rate-limit-default",
                            "type": "rate_limit",
                            "name": "Default Rate Limit",
                            "description": "1000 requests per hour per API key",
                            "status": "active",
                        },
                        {
                            "id": "pol-jwt-validation",
                            "type": "jwt",
                            "name": "JWT Validation",
                            "description": "Validate JWT tokens from Keycloak",
                            "status": "active",
                        },
                        {
                            "id": "pol-tenant-isolation",
                            "type": "rbac",
                            "name": "Tenant Isolation",
                            "description": "Enforce multi-tenant data isolation",
                            "status": "active",
                        },
                    ],
                    "total": 3,
                }

            else:
                return error_result(
                    STOAErrorCode.INVALID_ACTION,
                    f"Unknown action: '{action}'",
                    details={"action": action, "valid_actions": ["audit_log", "check_permissions", "list_policies"]},
                )

        except ValueError as e:
            return error_result(
                STOAErrorCode.AUTH_REQUIRED,
                str(e),
            )
        except Exception as e:
            logger.error("Failed to handle security action", action=action, error=str(e))
            return error_result(
                STOAErrorCode.BACKEND_ERROR,
                f"Failed to handle security action: {action}",
                details={"action": action, "backend_error": str(e)},
            )

    # =========================================================================
    # UAC HANDLERS
    # =========================================================================

    async def handle_uac(
        self,
        action: str,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_uac tool calls.

        Note: UAC contracts may need additional Core API endpoints.
        """
        try:
            self._get_token(claims)  # Validate auth

            if action == "list":
                # UAC contracts would require a Core API endpoint
                return {
                    "contracts": [],
                    "total": 0,
                    "message": "UAC contracts available via Core API /v1/uac/contracts",
                }

            elif action == "get":
                contract_id = params.get("contract_id")
                if not contract_id:
                    return error_result(
                        STOAErrorCode.INVALID_PARAMS,
                        "Parameter 'contract_id' is required",
                        details={"parameter": "contract_id", "action": action},
                    )
                return error_result(
                    STOAErrorCode.NOT_IMPLEMENTED,
                    "UAC contract retrieval requires Core API endpoint",
                    details={"contract_id": contract_id},
                )

            elif action == "validate":
                contract_id = params.get("contract_id")
                if not contract_id:
                    return error_result(
                        STOAErrorCode.INVALID_PARAMS,
                        "Parameter 'contract_id' is required",
                        details={"parameter": "contract_id", "action": action},
                    )
                return {
                    "contract_id": contract_id,
                    "subscription_id": params.get("subscription_id"),
                    "compliant": True,
                    "message": "All contract terms satisfied (placeholder)",
                }

            elif action == "sla":
                contract_id = params.get("contract_id")
                if not contract_id:
                    return error_result(
                        STOAErrorCode.INVALID_PARAMS,
                        "Parameter 'contract_id' is required",
                        details={"parameter": "contract_id", "action": action},
                    )
                return {
                    "contract_id": contract_id,
                    "time_range": params.get("time_range", "30d"),
                    "metrics": {
                        "uptime": {"target": "99.9%", "actual": "99.97%", "status": "met"},
                        "latency_p99": {"target": "500ms", "actual": "234ms", "status": "met"},
                        "error_rate": {"target": "0.1%", "actual": "0.03%", "status": "met"},
                    },
                    "overall_status": "compliant",
                }

            else:
                return error_result(
                    STOAErrorCode.INVALID_ACTION,
                    f"Unknown action: '{action}'",
                    details={"action": action, "valid_actions": ["list", "get", "validate", "sla"]},
                )

        except ValueError as e:
            return error_result(
                STOAErrorCode.AUTH_REQUIRED,
                str(e),
            )
        except Exception as e:
            logger.error("Failed to handle uac action", action=action, error=str(e))
            return error_result(
                STOAErrorCode.BACKEND_ERROR,
                f"Failed to handle UAC action: {action}",
                details={"action": action, "backend_error": str(e)},
            )


# =============================================================================
# SINGLETON MANAGEMENT
# =============================================================================

_tool_handlers: STOAToolHandlers | None = None


def get_tool_handlers() -> STOAToolHandlers | None:
    """Get the tool handlers singleton."""
    return _tool_handlers


def init_tool_handlers() -> STOAToolHandlers:
    """Initialize the tool handlers singleton.

    ADR-001: No longer requires session_factory - uses CoreAPIClient.
    """
    global _tool_handlers
    if _tool_handlers is None:
        _tool_handlers = STOAToolHandlers()
        logger.info("Tool handlers initialized (ADR-001 compliant)")
    return _tool_handlers


def shutdown_tool_handlers() -> None:
    """Shutdown the tool handlers singleton."""
    global _tool_handlers
    _tool_handlers = None
    logger.info("Tool handlers shutdown")
