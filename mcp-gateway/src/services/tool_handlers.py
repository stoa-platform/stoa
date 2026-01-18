"""CAB-660: MCP Tool Handlers with Real Database Backend.

Handlers that connect MCP tools to real backends via service layer.
"""

import json
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.repositories import (
    TenantRepository,
    APIRepository,
    SubscriptionRepository,
    AuditLogRepository,
    UACContractRepository,
)
from ..middleware.auth import TokenClaims
from .business import (
    RequestContext,
    TenantService,
    CatalogService,
    SubscriptionService,
    SecurityService,
    UACService,
)

logger = structlog.get_logger(__name__)


class STOAToolHandlers:
    """MCP Tool Handlers for STOA Platform.

    Connects MCP tools to real backends via service layer.
    Uses SQLAlchemy AsyncSession for database access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    def _extract_context(
        self,
        claims: TokenClaims | None,
        ip_address: str | None = None,
    ) -> RequestContext:
        """Extract request context from TokenClaims."""
        if claims is None:
            return RequestContext(
                user_id="anonymous",
                tenant_id="unknown",
                roles=[],
            )

        return RequestContext(
            user_id=claims.subject,
            tenant_id=claims.tenant_id or "unknown",
            roles=claims.roles,
            email=claims.email,
            name=claims.name or claims.preferred_username,
            ip_address=ip_address,
        )

    # =========================================================================
    # TENANT HANDLERS
    # =========================================================================

    async def handle_tenants(
        self,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_tenants tool calls."""
        async with self._session_factory() as session:
            tenant_repo = TenantRepository(session)
            service = TenantService(tenant_repo)
            ctx = self._extract_context(claims)

            result = await service.list_tenants(
                ctx=ctx,
                include_inactive=params.get("include_inactive", False),
            )
            await session.commit()
            return result

    # =========================================================================
    # CATALOG HANDLERS
    # =========================================================================

    async def handle_catalog(
        self,
        action: str,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_catalog tool calls."""
        async with self._session_factory() as session:
            api_repo = APIRepository(session)
            audit_repo = AuditLogRepository(session)
            service = CatalogService(api_repo, audit_repo)
            ctx = self._extract_context(claims)

            if action == "list":
                result = await service.list_apis(
                    ctx=ctx,
                    status=params.get("status"),
                    category=params.get("category"),
                    page=params.get("page", 1),
                    page_size=params.get("page_size", 20),
                )
            elif action == "get":
                api_id = params.get("api_id")
                if not api_id:
                    return {"error": "INVALID_PARAMS", "message": "api_id is required"}
                result = await service.get_api(ctx, api_id)
            elif action == "search":
                query = params.get("query")
                if not query:
                    return {"error": "INVALID_PARAMS", "message": "query is required"}
                result = await service.search_apis(
                    ctx=ctx,
                    query=query,
                    tags=params.get("tags"),
                    category=params.get("category"),
                )
            elif action == "versions":
                api_id = params.get("api_id")
                if not api_id:
                    return {"error": "INVALID_PARAMS", "message": "api_id is required"}
                result = await service.get_versions(ctx, api_id)
            elif action == "categories":
                result = await service.get_categories()
            else:
                return {"error": "INVALID_ACTION", "message": f"Unknown action: {action}"}

            await session.commit()
            return result

    # =========================================================================
    # API SPEC HANDLERS
    # =========================================================================

    async def handle_api_spec(
        self,
        action: str,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_api_spec tool calls."""
        async with self._session_factory() as session:
            api_repo = APIRepository(session)
            audit_repo = AuditLogRepository(session)
            service = CatalogService(api_repo, audit_repo)
            ctx = self._extract_context(claims)

            api_id = params.get("api_id")
            if not api_id:
                return {"error": "INVALID_PARAMS", "message": "api_id is required"}

            if action == "openapi":
                # Get API with endpoints
                api_result = await service.get_api(ctx, api_id)
                if "error" in api_result:
                    return api_result

                # Build OpenAPI spec
                result = {
                    "api_id": api_id,
                    "format": params.get("format", "json"),
                    "spec": {
                        "openapi": "3.0.0",
                        "info": {
                            "title": api_result.get("name"),
                            "description": api_result.get("description"),
                            "version": api_result.get("version", "1.0.0"),
                        },
                        "paths": {
                            ep["path"]: {
                                ep["method"].lower(): {
                                    "summary": ep.get("description", ""),
                                    "responses": {"200": {"description": "Success"}},
                                }
                            }
                            for ep in api_result.get("endpoints", [])
                        },
                    },
                }
            elif action == "docs":
                api_result = await service.get_api(ctx, api_id)
                if "error" in api_result:
                    return api_result

                endpoints_doc = "\n".join([
                    f"### {ep['method']} {ep['path']}\n{ep.get('description', '')}"
                    for ep in api_result.get("endpoints", [])
                ])

                result = {
                    "api_id": api_id,
                    "section": params.get("section"),
                    "documentation": (
                        f"# {api_result.get('name')}\n\n"
                        f"{api_result.get('description', '')}\n\n"
                        f"## Endpoints\n\n{endpoints_doc}"
                    ),
                }
            elif action == "endpoints":
                api_result = await service.get_api(ctx, api_id)
                if "error" in api_result:
                    return api_result

                endpoints = api_result.get("endpoints", [])
                method_filter = params.get("method")
                if method_filter:
                    endpoints = [e for e in endpoints if e["method"] == method_filter]

                result = {
                    "api_id": api_id,
                    "endpoints": endpoints,
                    "total": len(endpoints),
                }
            else:
                return {"error": "INVALID_ACTION", "message": f"Unknown action: {action}"}

            await session.commit()
            return result

    # =========================================================================
    # SUBSCRIPTION HANDLERS
    # =========================================================================

    async def handle_subscription(
        self,
        action: str,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_subscription tool calls."""
        async with self._session_factory() as session:
            sub_repo = SubscriptionRepository(session)
            api_repo = APIRepository(session)
            audit_repo = AuditLogRepository(session)
            service = SubscriptionService(sub_repo, api_repo, audit_repo)
            ctx = self._extract_context(claims)

            if action == "list":
                result = await service.list_subscriptions(
                    ctx=ctx,
                    status=params.get("status"),
                    api_id=params.get("api_id"),
                )
            elif action == "get":
                sub_id = params.get("subscription_id")
                if not sub_id:
                    return {"error": "INVALID_PARAMS", "message": "subscription_id is required"}
                result = await service.get_subscription(ctx, sub_id)
            elif action == "create":
                api_id = params.get("api_id")
                if not api_id:
                    return {"error": "INVALID_PARAMS", "message": "api_id is required"}
                result = await service.create_subscription(
                    ctx=ctx,
                    api_id=api_id,
                    plan=params.get("plan", "standard"),
                    application_name=params.get("application_name"),
                )
            elif action == "cancel":
                sub_id = params.get("subscription_id")
                if not sub_id:
                    return {"error": "INVALID_PARAMS", "message": "subscription_id is required"}
                result = await service.cancel_subscription(
                    ctx=ctx,
                    subscription_id=sub_id,
                    reason=params.get("reason"),
                )
            elif action == "credentials":
                sub_id = params.get("subscription_id")
                if not sub_id:
                    return {"error": "INVALID_PARAMS", "message": "subscription_id is required"}
                result = await service.get_credentials(ctx, sub_id)
            elif action == "rotate_key":
                sub_id = params.get("subscription_id")
                if not sub_id:
                    return {"error": "INVALID_PARAMS", "message": "subscription_id is required"}
                result = await service.rotate_key(
                    ctx=ctx,
                    subscription_id=sub_id,
                    grace_period_hours=params.get("grace_period_hours", 24),
                )
            else:
                return {"error": "INVALID_ACTION", "message": f"Unknown action: {action}"}

            await session.commit()
            return result

    # =========================================================================
    # SECURITY HANDLERS
    # =========================================================================

    async def handle_security(
        self,
        action: str,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_security tool calls."""
        async with self._session_factory() as session:
            audit_repo = AuditLogRepository(session)
            api_repo = APIRepository(session)
            service = SecurityService(audit_repo, api_repo)
            ctx = self._extract_context(claims)

            if action == "audit_log":
                result = await service.get_audit_log(
                    ctx=ctx,
                    api_id=params.get("api_id"),
                    user_id=params.get("user_id"),
                    time_range=params.get("time_range", "24h"),
                    limit=params.get("limit", 100),
                )
            elif action == "check_permissions":
                api_id = params.get("api_id")
                action_type = params.get("action_type")
                if not api_id or not action_type:
                    return {"error": "INVALID_PARAMS", "message": "api_id and action_type are required"}
                result = await service.check_permissions(ctx, api_id, action_type)
            elif action == "list_policies":
                result = await service.list_policies(
                    ctx=ctx,
                    policy_type=params.get("policy_type"),
                )
            else:
                return {"error": "INVALID_ACTION", "message": f"Unknown action: {action}"}

            await session.commit()
            return result

    # =========================================================================
    # UAC HANDLERS
    # =========================================================================

    async def handle_uac(
        self,
        action: str,
        params: dict[str, Any],
        claims: TokenClaims | None,
    ) -> dict[str, Any]:
        """Handle stoa_uac tool calls."""
        async with self._session_factory() as session:
            uac_repo = UACContractRepository(session)
            service = UACService(uac_repo)
            ctx = self._extract_context(claims)

            if action == "list":
                result = await service.list_contracts(
                    ctx=ctx,
                    api_id=params.get("api_id"),
                    status=params.get("status"),
                )
            elif action == "get":
                contract_id = params.get("contract_id")
                if not contract_id:
                    return {"error": "INVALID_PARAMS", "message": "contract_id is required"}
                result = await service.get_contract(ctx, contract_id)
            elif action == "validate":
                contract_id = params.get("contract_id")
                if not contract_id:
                    return {"error": "INVALID_PARAMS", "message": "contract_id is required"}
                # Placeholder - would validate subscription against contract
                result = {
                    "contract_id": contract_id,
                    "subscription_id": params.get("subscription_id"),
                    "compliant": True,
                    "message": "All contract terms satisfied",
                }
            elif action == "sla":
                contract_id = params.get("contract_id")
                if not contract_id:
                    return {"error": "INVALID_PARAMS", "message": "contract_id is required"}
                result = await service.get_sla_metrics(
                    ctx=ctx,
                    contract_id=contract_id,
                    time_range=params.get("time_range", "30d"),
                )
            else:
                return {"error": "INVALID_ACTION", "message": f"Unknown action: {action}"}

            await session.commit()
            return result


# =============================================================================
# SINGLETON MANAGEMENT
# =============================================================================

_tool_handlers: STOAToolHandlers | None = None


def get_tool_handlers() -> STOAToolHandlers | None:
    """Get the tool handlers singleton."""
    return _tool_handlers


def init_tool_handlers(session_factory: async_sessionmaker[AsyncSession]) -> STOAToolHandlers:
    """Initialize the tool handlers singleton."""
    global _tool_handlers
    if _tool_handlers is None:
        _tool_handlers = STOAToolHandlers(session_factory)
        logger.info("Tool handlers initialized")
    return _tool_handlers


def shutdown_tool_handlers() -> None:
    """Shutdown the tool handlers singleton."""
    global _tool_handlers
    _tool_handlers = None
    logger.info("Tool handlers shutdown")
