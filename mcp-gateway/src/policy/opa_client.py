"""OPA Policy Engine Client.

Integrates Open Policy Agent for fine-grained access control.
Supports both embedded evaluation and remote OPA sidecar.

CAB-603: Updated for Core vs Proxied tool authorization.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import structlog

from ..config import get_settings
from ..models import ToolType, ToolDomain

logger = structlog.get_logger(__name__)


@dataclass
class PolicyDecision:
    """Result of a policy evaluation."""

    allowed: bool
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.allowed


class EmbeddedEvaluator:
    """Embedded policy evaluator using Python rules.

    This is a simplified evaluator for MVP that doesn't require
    OPA sidecar. Policies are defined in Python for simplicity.
    For production, use OPA sidecar with Rego policies.

    CAB-603: Updated with Core Tool categories by scope.
    """

    def __init__(self) -> None:
        # =====================================================================
        # CAB-603: Core Tool Authorization by Scope
        # =====================================================================

        # Core tools requiring stoa:read scope (Platform, Catalog, Observability read ops)
        self.read_only_tools = {
            # Platform & Discovery (read)
            "stoa_platform_info",
            "stoa_platform_health",
            "stoa_list_tools",
            "stoa_get_tool_schema",
            "stoa_search_tools",
            # API Catalog (read)
            "stoa_catalog_list_apis",
            "stoa_catalog_get_api",
            "stoa_catalog_search_apis",
            "stoa_catalog_get_openapi",
            "stoa_catalog_list_versions",
            "stoa_catalog_get_documentation",
            "stoa_catalog_list_categories",
            "stoa_catalog_get_endpoints",
            # Subscriptions (read)
            "stoa_subscription_list",
            "stoa_subscription_get",
            "stoa_subscription_get_credentials",
            # Observability (read)
            "stoa_metrics_get_usage",
            "stoa_metrics_get_latency",
            "stoa_metrics_get_errors",
            "stoa_metrics_get_quota",
            "stoa_logs_search",
            "stoa_logs_get_recent",
            "stoa_alerts_list",
            # UAC (read)
            "stoa_uac_list_contracts",
            "stoa_uac_get_contract",
            "stoa_uac_get_sla",
            # Security (read)
            "stoa_security_check_permissions",
            "stoa_security_list_policies",
            # Legacy tools (backward compatibility)
            "stoa_list_apis",
            "stoa_health_check",
            "stoa_search_apis",
            "stoa_get_api_details",
        }

        # Core tools requiring stoa:write scope (Subscriptions write, Observability ack)
        self.write_tools = {
            # Subscriptions (write)
            "stoa_subscription_create",
            "stoa_subscription_cancel",
            "stoa_subscription_rotate_key",
            # Observability (write)
            "stoa_alerts_acknowledge",
            # UAC (write)
            "stoa_uac_validate_contract",
            # Legacy tools
            "stoa_create_api",
            "stoa_update_api",
            "stoa_deploy_api",
        }

        # Core tools requiring stoa:admin scope (Platform admin, Security audit)
        self.admin_tools = {
            # Platform (admin)
            "stoa_list_tenants",
            # Security (admin)
            "stoa_security_audit_log",
            # Legacy tools
            "stoa_delete_api",
            "stoa_delete_tool",
        }

        # Role to scope mapping (aligned with Keycloak roles)
        self.role_scopes = {
            "cpi-admin": {"stoa:admin", "stoa:write", "stoa:read"},
            "tenant-admin": {"stoa:write", "stoa:read"},
            "devops": {"stoa:write", "stoa:read"},
            "viewer": {"stoa:read"},
        }

        # =====================================================================
        # CAB-603: Tool Type Detection Patterns
        # =====================================================================
        self.core_tool_prefix = "stoa_"
        self.proxied_tool_separator = ":"

    def get_user_scopes(self, user: dict[str, Any]) -> set[str]:
        """Extract scopes from user claims."""
        scopes = set()

        # Check explicit scopes in token
        if "scope" in user:
            scope_str = user.get("scope", "")
            if isinstance(scope_str, str):
                scopes.update(scope_str.split())

        # Map roles to scopes
        roles = []
        if "realm_access" in user and "roles" in user["realm_access"]:
            roles = user["realm_access"]["roles"]
        elif "roles" in user:
            roles = user["roles"]

        for role in roles:
            if role in self.role_scopes:
                scopes.update(self.role_scopes[role])

        return scopes

    def _get_tool_type(self, tool_name: str) -> str:
        """Determine tool type from name.

        CAB-603: Classify tool by naming convention.

        Args:
            tool_name: Tool name

        Returns:
            "core", "proxied", or "legacy"
        """
        if tool_name.startswith(self.core_tool_prefix):
            return "core"
        elif self.proxied_tool_separator in tool_name:
            return "proxied"
        return "legacy"

    def _parse_proxied_tool_namespace(self, tool_name: str) -> dict[str, str]:
        """Parse proxied tool namespace {tenant}:{api}:{operation}.

        Args:
            tool_name: Namespaced tool name

        Returns:
            Dict with tenant_id, api_id, operation
        """
        parts = tool_name.split(self.proxied_tool_separator)
        if len(parts) >= 3:
            return {
                "tenant_id": parts[0],
                "api_id": parts[1],
                "operation": parts[2],
            }
        elif len(parts) == 2:
            return {
                "tenant_id": parts[0],
                "api_id": parts[1],
                "operation": "",
            }
        return {"tenant_id": "", "api_id": "", "operation": ""}

    def evaluate_authz(
        self,
        user: dict[str, Any],
        tool: dict[str, Any],
        action: str = "invoke",
    ) -> PolicyDecision:
        """Evaluate authorization policy.

        CAB-603: Routes authorization based on tool type:
        - Core tools: Check against read_only_tools, write_tools, admin_tools
        - Proxied tools: Check tenant membership + stoa:read scope
        - Legacy tools: Existing behavior

        Args:
            user: User claims from JWT
            tool: Tool information (name, tenant_id, arguments)
            action: Action being performed

        Returns:
            PolicyDecision with authorization result
        """
        tool_name = tool.get("name", "")
        tool_tenant_id = tool.get("tenant_id")
        user_tenant_id = user.get("tenant_id")
        scopes = self.get_user_scopes(user)
        tool_type = self._get_tool_type(tool_name)

        # Admin can do everything
        if "stoa:admin" in scopes:
            return PolicyDecision(
                allowed=True,
                reason="Admin access granted",
                metadata={"scope": "stoa:admin", "tool_type": tool_type},
            )

        # =====================================================================
        # CAB-603: Proxied Tool Authorization
        # =====================================================================
        if tool_type == "proxied":
            # Parse namespace to get tenant
            namespace = self._parse_proxied_tool_namespace(tool_name)
            proxied_tenant_id = namespace.get("tenant_id") or tool_tenant_id

            # Tenant isolation check for proxied tools
            if proxied_tenant_id and user_tenant_id:
                if proxied_tenant_id != user_tenant_id:
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Tenant mismatch: user={user_tenant_id}, tool={proxied_tenant_id}",
                        metadata={"tool_type": "proxied"},
                    )

            # Proxied tools require stoa:read scope + tenant membership
            if "stoa:read" in scopes:
                return PolicyDecision(
                    allowed=True,
                    reason="Proxied tool access granted",
                    metadata={"scope": "stoa:read", "tool_type": "proxied", "tenant_id": proxied_tenant_id},
                )

            return PolicyDecision(
                allowed=False,
                reason=f"Missing scope stoa:read for proxied tool {tool_name}",
                metadata={"tool_type": "proxied"},
            )

        # =====================================================================
        # Core Tool and Legacy Tool Authorization
        # =====================================================================

        # Check tenant isolation (if tool has tenant_id)
        if tool_tenant_id and user_tenant_id:
            if tool_tenant_id != user_tenant_id:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Tenant mismatch: user={user_tenant_id}, tool={tool_tenant_id}",
                    metadata={"tool_type": tool_type},
                )

        # Read-only tools require stoa:read
        if tool_name in self.read_only_tools:
            if "stoa:read" in scopes:
                return PolicyDecision(
                    allowed=True,
                    reason="Read access granted",
                    metadata={"scope": "stoa:read", "tool_type": tool_type},
                )
            return PolicyDecision(
                allowed=False,
                reason=f"Missing scope stoa:read for tool {tool_name}",
                metadata={"tool_type": tool_type},
            )

        # Write tools require stoa:write
        if tool_name in self.write_tools:
            if "stoa:write" in scopes:
                return PolicyDecision(
                    allowed=True,
                    reason="Write access granted",
                    metadata={"scope": "stoa:write", "tool_type": tool_type},
                )
            return PolicyDecision(
                allowed=False,
                reason=f"Missing scope stoa:write for tool {tool_name}",
                metadata={"tool_type": tool_type},
            )

        # Admin tools require stoa:admin
        if tool_name in self.admin_tools:
            return PolicyDecision(
                allowed=False,
                reason=f"Tool {tool_name} requires admin scope",
                metadata={"tool_type": tool_type},
            )

        # Unknown core tools (new stoa_* tools not yet categorized)
        # Default to read scope requirement for safety
        if tool_type == "core":
            if "stoa:read" in scopes:
                return PolicyDecision(
                    allowed=True,
                    reason="Default read access for uncategorized core tool",
                    metadata={"scope": "stoa:read", "tool_type": "core"},
                )
            return PolicyDecision(
                allowed=False,
                reason=f"Missing scope stoa:read for core tool {tool_name}",
                metadata={"tool_type": "core"},
            )

        # Legacy tools - allow if user has at least read scope
        # This allows dynamically registered API tools to work
        if "stoa:read" in scopes:
            return PolicyDecision(
                allowed=True,
                reason="Default read access for legacy tool",
                metadata={"scope": "stoa:read", "tool_type": "legacy"},
            )

        return PolicyDecision(
            allowed=False,
            reason="No valid scope for tool access",
            metadata={"tool_type": tool_type},
        )

    def evaluate_tenant_isolation(
        self,
        user: dict[str, Any],
        tool: dict[str, Any],
    ) -> PolicyDecision:
        """Check tenant isolation policy.

        Args:
            user: User claims
            tool: Tool information

        Returns:
            PolicyDecision
        """
        tool_tenant_id = tool.get("tenant_id")
        user_tenant_id = user.get("tenant_id")

        # Global tools (no tenant) are accessible to all
        if not tool_tenant_id:
            return PolicyDecision(
                allowed=True,
                reason="Global tool access",
            )

        # Admin bypass
        scopes = self.get_user_scopes(user)
        if "stoa:admin" in scopes:
            return PolicyDecision(
                allowed=True,
                reason="Admin bypass tenant isolation",
            )

        # Tenant must match
        if user_tenant_id == tool_tenant_id:
            return PolicyDecision(
                allowed=True,
                reason="Tenant match",
            )

        return PolicyDecision(
            allowed=False,
            reason=f"Tenant isolation: user={user_tenant_id}, tool={tool_tenant_id}",
        )


class OPAClient:
    """Client for OPA policy evaluation.

    Supports both embedded evaluation (Python rules) and
    remote OPA sidecar (Rego policies).
    """

    def __init__(
        self,
        opa_url: str | None = None,
        embedded: bool | None = None,
        timeout: float = 5.0,
    ) -> None:
        """Initialize the OPA client.

        Args:
            opa_url: OPA server URL for sidecar mode
            embedded: Use embedded evaluator instead of OPA sidecar
            timeout: Request timeout in seconds
        """
        settings = get_settings()
        self.opa_url = opa_url or settings.opa_url
        self.timeout = timeout
        self._enabled = settings.opa_enabled
        self._embedded = embedded if embedded is not None else settings.opa_embedded
        self._http_client: httpx.AsyncClient | None = None
        self._evaluator: EmbeddedEvaluator | None = None

    async def startup(self) -> None:
        """Initialize the client."""
        if self._embedded:
            self._evaluator = EmbeddedEvaluator()
            logger.info("OPA embedded evaluator initialized")
        else:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                base_url=self.opa_url,
            )
            logger.info("OPA HTTP client initialized", opa_url=self.opa_url)

    async def shutdown(self) -> None:
        """Cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()
        logger.info("OPA client shutdown")

    @property
    def enabled(self) -> bool:
        """Check if OPA is enabled."""
        return self._enabled

    async def check_authorization(
        self,
        user: dict[str, Any],
        tool: dict[str, Any],
        action: str = "invoke",
    ) -> tuple[bool, str]:
        """Check if user is authorized to perform action on tool.

        Args:
            user: User claims from JWT
            tool: Tool information (name, tenant_id, arguments)
            action: Action being performed

        Returns:
            Tuple of (allowed, reason)
        """
        if not self._enabled:
            return True, "OPA disabled"

        start_time = time.time()

        try:
            if self._embedded:
                decision = self._evaluator.evaluate_authz(user, tool, action)
            else:
                decision = await self._check_authorization_remote(user, tool, action)

            latency_ms = int((time.time() - start_time) * 1000)
            logger.debug(
                "Policy evaluated",
                tool_name=tool.get("name"),
                allowed=decision.allowed,
                reason=decision.reason,
                latency_ms=latency_ms,
            )

            return decision.allowed, decision.reason

        except Exception as e:
            logger.error("Policy evaluation failed", error=str(e))
            # Fail-open for availability
            return True, f"Policy error (fail-open): {e}"

    async def _check_authorization_remote(
        self,
        user: dict[str, Any],
        tool: dict[str, Any],
        action: str,
    ) -> PolicyDecision:
        """Evaluate authorization via OPA sidecar."""
        if not self._http_client:
            return PolicyDecision(allowed=True, reason="HTTP client not initialized")

        input_data = {
            "user": user,
            "tool": tool,
            "action": action,
        }

        try:
            response = await self._http_client.post(
                "/v1/data/stoa/authz/allow",
                json={"input": input_data},
            )
            response.raise_for_status()
            result = response.json()

            allowed = result.get("result", False)
            return PolicyDecision(
                allowed=allowed,
                reason="Policy allowed" if allowed else "Policy denied",
            )

        except httpx.HTTPError as e:
            logger.error("OPA request failed", error=str(e))
            return PolicyDecision(allowed=True, reason=f"OPA error (fail-open): {e}")

    async def check_tenant_isolation(
        self,
        user: dict[str, Any],
        tool: dict[str, Any],
    ) -> tuple[bool, str]:
        """Check tenant isolation policy.

        Args:
            user: User claims
            tool: Tool information

        Returns:
            Tuple of (allowed, reason)
        """
        if not self._enabled:
            return True, "OPA disabled"

        if self._embedded:
            decision = self._evaluator.evaluate_tenant_isolation(user, tool)
            return decision.allowed, decision.reason

        # For remote OPA, use authz policy which includes tenant checks
        return await self.check_authorization(user, tool, "access")


# Singleton instance
_opa_client: OPAClient | None = None


async def get_opa_client() -> OPAClient:
    """Get the OPA client singleton."""
    global _opa_client
    if _opa_client is None:
        _opa_client = OPAClient()
        await _opa_client.startup()
    return _opa_client


async def shutdown_opa_client() -> None:
    """Shutdown the OPA client."""
    global _opa_client
    if _opa_client:
        await _opa_client.shutdown()
        _opa_client = None
