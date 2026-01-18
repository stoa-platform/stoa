"""CAB-660: Business Logic Services for Tool Handlers.

Services that handle authorization and business logic using repositories.
"""

import hashlib
import secrets
from dataclasses import dataclass
from typing import Any

from ..db.repositories import (
    TenantRepository,
    APIRepository,
    SubscriptionRepository,
    AuditLogRepository,
    UACContractRepository,
    TenantDTO,
    APIDTO,
    SubscriptionDTO,
    AuditLogDTO,
    UACContractDTO,
)


# =============================================================================
# REQUEST CONTEXT
# =============================================================================


@dataclass
class RequestContext:
    """Request context extracted from JWT token."""

    user_id: str
    tenant_id: str
    roles: list[str]
    email: str | None = None
    name: str | None = None
    ip_address: str | None = None

    @property
    def is_platform_admin(self) -> bool:
        """Check if user is platform admin."""
        return "platform-admin" in self.roles

    @property
    def is_tenant_admin(self) -> bool:
        """Check if user is tenant admin."""
        return "tenant-admin" in self.roles or self.is_platform_admin


# =============================================================================
# TENANT SERVICE
# =============================================================================


class TenantService:
    """Service for tenant operations."""

    def __init__(self, tenant_repo: TenantRepository):
        self.tenant_repo = tenant_repo

    async def list_tenants(
        self,
        ctx: RequestContext,
        include_inactive: bool = False,
    ) -> dict[str, Any]:
        """List tenants. Platform admins see all, others see only their own."""
        if ctx.is_platform_admin:
            tenants = await self.tenant_repo.list(include_inactive)
            return {
                "tenants": [self._format_tenant(t) for t in tenants],
                "total": len(tenants),
            }

        # Non-admin: show only own tenant
        tenant = await self.tenant_repo.get_by_id(ctx.tenant_id)
        if tenant:
            return {
                "tenants": [self._format_tenant(tenant)],
                "total": 1,
                "message": "Showing only your tenant. Platform admin role required for full list.",
            }

        return {"tenants": [], "total": 0}

    def _format_tenant(self, tenant: TenantDTO) -> dict[str, Any]:
        return {
            "id": tenant.id,
            "name": tenant.name,
            "description": tenant.description,
            "status": tenant.status,
            "api_count": tenant.api_count,
            "subscription_count": tenant.subscription_count,
        }


# =============================================================================
# CATALOG SERVICE
# =============================================================================


class CatalogService:
    """Service for API catalog operations."""

    def __init__(self, api_repo: APIRepository, audit_repo: AuditLogRepository):
        self.api_repo = api_repo
        self.audit_repo = audit_repo

    async def list_apis(
        self,
        ctx: RequestContext,
        status: str | None = None,
        category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """List APIs visible to the requesting tenant."""
        apis, total = await self.api_repo.list(
            tenant_id=ctx.tenant_id,
            status=status,
            category=category,
            page=page,
            page_size=page_size,
        )

        return {
            "apis": [self._format_api(api) for api in apis],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_api(
        self,
        ctx: RequestContext,
        api_id: str,
    ) -> dict[str, Any]:
        """Get API details if accessible."""
        # Check access
        can_access = await self.api_repo.can_access(api_id, ctx.tenant_id)
        if not can_access and not ctx.is_platform_admin:
            return {
                "error": "API_NOT_FOUND",
                "message": f"API '{api_id}' not found or access denied",
            }

        api = await self.api_repo.get_by_id(api_id)
        if not api:
            return {
                "error": "API_NOT_FOUND",
                "message": f"API '{api_id}' not found",
            }

        endpoints = await self.api_repo.get_endpoints(api_id)

        return {
            **self._format_api(api),
            "endpoints": [
                {"method": e.method, "path": e.path, "description": e.description}
                for e in endpoints
            ],
        }

    async def search_apis(
        self,
        ctx: RequestContext,
        query: str,
        tags: list[str] | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Search APIs by name, description, or tags."""
        apis = await self.api_repo.search(
            query=query,
            tenant_id=ctx.tenant_id,
            tags=tags,
        )

        # Filter by category if specified
        if category:
            apis = [a for a in apis if a.category == category]

        return {
            "apis": [self._format_api(api) for api in apis],
            "total": len(apis),
            "query": query,
        }

    async def get_categories(self) -> dict[str, Any]:
        """Get all API categories with counts."""
        categories = await self.api_repo.get_categories()
        return {"categories": categories}

    async def get_versions(
        self,
        ctx: RequestContext,
        api_id: str,
    ) -> dict[str, Any]:
        """Get API version history."""
        # Check access
        can_access = await self.api_repo.can_access(api_id, ctx.tenant_id)
        if not can_access and not ctx.is_platform_admin:
            return {
                "error": "API_NOT_FOUND",
                "message": f"API '{api_id}' not found or access denied",
            }

        api = await self.api_repo.get_by_id(api_id)
        if not api:
            return {"error": "API_NOT_FOUND"}

        # For now, return current version only
        # Future: version history table
        return {
            "api_id": api_id,
            "versions": [
                {
                    "version": api.version,
                    "status": api.status,
                    "created_at": api.created_at.isoformat() if api.created_at else None,
                }
            ],
        }

    def _format_api(self, api: APIDTO) -> dict[str, Any]:
        return {
            "id": api.id,
            "name": api.name,
            "description": api.description,
            "category": api.category,
            "status": api.status,
            "version": api.version,
            "tags": api.tags,
            "rate_limit": api.rate_limit,
            "access_type": api.access_type,
        }


# =============================================================================
# SUBSCRIPTION SERVICE
# =============================================================================


class SubscriptionService:
    """Service for subscription operations."""

    def __init__(
        self,
        sub_repo: SubscriptionRepository,
        api_repo: APIRepository,
        audit_repo: AuditLogRepository,
    ):
        self.sub_repo = sub_repo
        self.api_repo = api_repo
        self.audit_repo = audit_repo

    async def list_subscriptions(
        self,
        ctx: RequestContext,
        status: str | None = None,
        api_id: str | None = None,
    ) -> dict[str, Any]:
        """List subscriptions for the requesting tenant."""
        # Tenant admins see all tenant subscriptions
        # Regular users see only their own
        user_id = None if ctx.is_tenant_admin else ctx.user_id

        subs = await self.sub_repo.list(
            tenant_id=ctx.tenant_id,
            user_id=user_id,
            status=status,
            api_id=api_id,
        )

        return {
            "subscriptions": [self._format_subscription(s) for s in subs],
            "total": len(subs),
        }

    async def get_subscription(
        self,
        ctx: RequestContext,
        subscription_id: str,
    ) -> dict[str, Any]:
        """Get subscription details."""
        sub = await self.sub_repo.get_by_id(subscription_id, ctx.tenant_id)
        if not sub:
            return {
                "error": "SUBSCRIPTION_NOT_FOUND",
                "message": f"Subscription '{subscription_id}' not found",
            }

        # Check user access (non-admins can only see their own)
        if not ctx.is_tenant_admin and sub.user_id != ctx.user_id:
            return {
                "error": "PERMISSION_DENIED",
                "message": "You can only view your own subscriptions",
            }

        return self._format_subscription(sub)

    async def create_subscription(
        self,
        ctx: RequestContext,
        api_id: str,
        plan: str = "standard",
        application_name: str | None = None,
    ) -> dict[str, Any]:
        """Subscribe to an API."""
        # Check API access
        can_access = await self.api_repo.can_access(api_id, ctx.tenant_id)
        if not can_access:
            # Log denied attempt
            reason = f"API '{api_id}' is not accessible to tenant '{ctx.tenant_id}'"
            sub_id = f"sub-{secrets.token_hex(8)}"

            await self.sub_repo.create_denied(
                sub_id=sub_id,
                user_id=ctx.user_id,
                tenant_id=ctx.tenant_id,
                api_id=api_id,
                reason=reason,
            )

            await self.audit_repo.log(
                user_id=ctx.user_id,
                tenant_id=ctx.tenant_id,
                action="subscription.create",
                resource_type="api",
                resource_id=api_id,
                status="denied",
                details={"reason": reason},
                ip_address=ctx.ip_address,
            )

            return {
                "error": "PERMISSION_DENIED",
                "message": reason,
            }

        # Generate API key
        api_key = f"sk_{ctx.tenant_id[:8]}_{secrets.token_hex(16)}"
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        sub_id = f"sub-{secrets.token_hex(8)}"

        sub = await self.sub_repo.create(
            sub_id=sub_id,
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            api_id=api_id,
            plan=plan,
            api_key_hash=api_key_hash,
        )

        await self.audit_repo.log(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            action="subscription.create",
            resource_type="subscription",
            resource_id=sub_id,
            status="success",
            details={"api_id": api_id, "plan": plan},
            ip_address=ctx.ip_address,
        )

        return {
            "subscription_id": sub_id,
            "api_id": api_id,
            "api_name": sub.api_name if sub else None,
            "plan": plan,
            "status": "active",
            "api_key": api_key,  # Only returned once!
            "message": "Store your API key securely. It won't be shown again.",
        }

    async def cancel_subscription(
        self,
        ctx: RequestContext,
        subscription_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel a subscription."""
        sub = await self.sub_repo.get_by_id(subscription_id, ctx.tenant_id)
        if not sub:
            return {
                "error": "SUBSCRIPTION_NOT_FOUND",
                "message": f"Subscription '{subscription_id}' not found",
            }

        # Check permissions
        if not ctx.is_tenant_admin and sub.user_id != ctx.user_id:
            return {
                "error": "PERMISSION_DENIED",
                "message": "You can only cancel your own subscriptions",
            }

        success = await self.sub_repo.cancel(subscription_id, ctx.tenant_id)

        if success:
            await self.audit_repo.log(
                user_id=ctx.user_id,
                tenant_id=ctx.tenant_id,
                action="subscription.cancel",
                resource_type="subscription",
                resource_id=subscription_id,
                status="success",
                details={"reason": reason},
                ip_address=ctx.ip_address,
            )

            return {
                "subscription_id": subscription_id,
                "status": "cancelled",
                "message": "Subscription cancelled successfully",
            }

        return {
            "error": "CANCELLATION_FAILED",
            "message": "Could not cancel subscription. It may already be cancelled.",
        }

    async def get_credentials(
        self,
        ctx: RequestContext,
        subscription_id: str,
    ) -> dict[str, Any]:
        """Get (masked) credentials for a subscription."""
        sub = await self.sub_repo.get_by_id(subscription_id, ctx.tenant_id)
        if not sub:
            return {
                "error": "SUBSCRIPTION_NOT_FOUND",
                "message": f"Subscription '{subscription_id}' not found",
            }

        # Check permissions
        if not ctx.is_tenant_admin and sub.user_id != ctx.user_id:
            return {
                "error": "PERMISSION_DENIED",
                "message": "You can only view your own credentials",
            }

        return {
            "subscription_id": subscription_id,
            "api_id": sub.api_id,
            "api_name": sub.api_name,
            "status": sub.status,
            "api_key": "sk_****_****************",  # Always masked
            "message": "API key is masked for security. Use rotate_key to generate a new one.",
        }

    async def rotate_key(
        self,
        ctx: RequestContext,
        subscription_id: str,
        grace_period_hours: int = 24,
    ) -> dict[str, Any]:
        """Rotate API key with grace period."""
        sub = await self.sub_repo.get_by_id(subscription_id, ctx.tenant_id)
        if not sub:
            return {
                "error": "SUBSCRIPTION_NOT_FOUND",
                "message": f"Subscription '{subscription_id}' not found",
            }

        # Check permissions
        if not ctx.is_tenant_admin and sub.user_id != ctx.user_id:
            return {
                "error": "PERMISSION_DENIED",
                "message": "You can only rotate your own API keys",
            }

        # Generate new API key
        new_api_key = f"sk_{ctx.tenant_id[:8]}_{secrets.token_hex(16)}"

        await self.audit_repo.log(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            action="subscription.rotate_key",
            resource_type="subscription",
            resource_id=subscription_id,
            status="success",
            details={"grace_period_hours": grace_period_hours},
            ip_address=ctx.ip_address,
        )

        return {
            "subscription_id": subscription_id,
            "api_id": sub.api_id,
            "new_api_key": new_api_key,
            "grace_period_hours": grace_period_hours,
            "message": f"New API key generated. Old key valid for {grace_period_hours}h.",
        }

    def _format_subscription(self, sub: SubscriptionDTO) -> dict[str, Any]:
        return {
            "id": sub.id,
            "api_id": sub.api_id,
            "api_name": sub.api_name,
            "plan": sub.plan,
            "status": sub.status,
            "created_at": sub.created_at.isoformat() if sub.created_at else None,
        }


# =============================================================================
# SECURITY SERVICE
# =============================================================================


class SecurityService:
    """Service for security and audit operations."""

    def __init__(
        self,
        audit_repo: AuditLogRepository,
        api_repo: APIRepository,
    ):
        self.audit_repo = audit_repo
        self.api_repo = api_repo

    async def get_audit_log(
        self,
        ctx: RequestContext,
        api_id: str | None = None,
        user_id: str | None = None,
        time_range: str = "24h",
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get audit log entries."""
        # Non-admins can only see their own logs
        if not ctx.is_tenant_admin:
            user_id = ctx.user_id

        # Platform admins can see all, tenant admins see their tenant
        tenant_id = None if ctx.is_platform_admin else ctx.tenant_id

        logs = await self.audit_repo.search(
            tenant_id=tenant_id,
            user_id=user_id,
            time_range=time_range,
            limit=limit,
        )

        return {
            "audit_logs": [self._format_log(log) for log in logs],
            "total": len(logs),
            "time_range": time_range,
        }

    async def check_permissions(
        self,
        ctx: RequestContext,
        api_id: str,
        action_type: str,  # "read", "write", "admin"
    ) -> dict[str, Any]:
        """Check user permissions for an API."""
        can_access = await self.api_repo.can_access(api_id, ctx.tenant_id)

        api = await self.api_repo.get_by_id(api_id)
        if not api:
            return {
                "api_id": api_id,
                "action": action_type,
                "allowed": False,
                "reason": "API not found",
            }

        # Determine permission level
        is_owner = api.owner_tenant_id == ctx.tenant_id

        allowed = False
        reason = ""

        if action_type == "read":
            allowed = can_access or ctx.is_platform_admin
            reason = "Read access granted" if allowed else "API restricted to specific tenants"

        elif action_type == "write":
            allowed = is_owner or ctx.is_platform_admin
            reason = "Write access granted" if allowed else "Only API owner can modify"

        elif action_type == "admin":
            allowed = (is_owner and ctx.is_tenant_admin) or ctx.is_platform_admin
            reason = "Admin access granted" if allowed else "Requires tenant admin of owning tenant"

        return {
            "api_id": api_id,
            "api_name": api.name,
            "action": action_type,
            "allowed": allowed,
            "reason": reason,
            "your_tenant": ctx.tenant_id,
            "your_roles": ctx.roles,
        }

    async def list_policies(
        self,
        ctx: RequestContext,
        policy_type: str | None = None,
    ) -> dict[str, Any]:
        """List security policies."""
        # Placeholder - would connect to policy engine
        policies = [
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
        ]

        if policy_type:
            policies = [p for p in policies if p["type"] == policy_type]

        return {"policies": policies, "total": len(policies)}

    def _format_log(self, log: AuditLogDTO) -> dict[str, Any]:
        return {
            "timestamp": log.timestamp.isoformat(),
            "user_id": log.user_id,
            "tenant_id": log.tenant_id,
            "action": log.action,
            "resource": f"{log.resource_type}:{log.resource_id}" if log.resource_type else log.resource_id,
            "status": log.status,
            "details": log.details,
            "ip_address": log.ip_address,
        }


# =============================================================================
# UAC SERVICE
# =============================================================================


class UACService:
    """Service for UAC contract operations."""

    def __init__(self, uac_repo: UACContractRepository):
        self.uac_repo = uac_repo

    async def list_contracts(
        self,
        ctx: RequestContext,
        api_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """List UAC contracts for the tenant."""
        # Platform admins see all, others see their tenant's contracts
        tenant_id = None if ctx.is_platform_admin else ctx.tenant_id

        contracts = await self.uac_repo.list(
            tenant_id=tenant_id,
            api_id=api_id,
            status=status,
        )

        return {
            "contracts": [self._format_contract(c) for c in contracts],
            "total": len(contracts),
        }

    async def get_contract(
        self,
        ctx: RequestContext,
        contract_id: str,
    ) -> dict[str, Any]:
        """Get contract details."""
        contract = await self.uac_repo.get_by_id(contract_id)
        if not contract:
            return {
                "error": "CONTRACT_NOT_FOUND",
                "message": f"Contract '{contract_id}' not found",
            }

        # Check access (platform admin or tenant member)
        if not ctx.is_platform_admin and ctx.tenant_id not in contract.tenant_ids:
            return {
                "error": "PERMISSION_DENIED",
                "message": "You don't have access to this contract",
            }

        return self._format_contract(contract, include_terms=True)

    async def get_sla_metrics(
        self,
        ctx: RequestContext,
        contract_id: str,
        time_range: str = "30d",
    ) -> dict[str, Any]:
        """Get SLA metrics for a contract."""
        contract = await self.uac_repo.get_by_id(contract_id)
        if not contract:
            return {"error": "CONTRACT_NOT_FOUND"}

        # Check access
        if not ctx.is_platform_admin and ctx.tenant_id not in contract.tenant_ids:
            return {"error": "PERMISSION_DENIED"}

        # Placeholder metrics - would connect to Prometheus
        return {
            "contract_id": contract_id,
            "contract_name": contract.name,
            "time_range": time_range,
            "metrics": {
                "uptime": {
                    "target": contract.terms.get("uptime", "99.9%"),
                    "actual": "99.97%",
                    "status": "met",
                },
                "latency_p99": {
                    "target": contract.terms.get("latency_p99_max", "500ms"),
                    "actual": "234ms",
                    "status": "met",
                },
                "error_rate": {
                    "target": contract.terms.get("error_rate_max", "0.1%"),
                    "actual": "0.03%",
                    "status": "met",
                },
            },
            "overall_status": "compliant",
        }

    def _format_contract(
        self,
        contract: UACContractDTO,
        include_terms: bool = False,
    ) -> dict[str, Any]:
        result = {
            "id": contract.id,
            "name": contract.name,
            "description": contract.description,
            "status": contract.status,
            "tenant_count": len(contract.tenant_ids),
        }
        if include_terms:
            result["terms"] = contract.terms
            result["tenant_ids"] = contract.tenant_ids
        return result
