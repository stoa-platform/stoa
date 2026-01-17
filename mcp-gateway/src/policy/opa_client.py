"""OPA Policy Engine Client.

Integrates Open Policy Agent for fine-grained access control.
Supports both embedded evaluation and remote OPA sidecar.

CAB-603: Updated for Core vs Proxied tool authorization.
CAB-604: Updated with 12 granular OAuth2 scopes and 6 personas.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import structlog

from ..config import get_settings
from ..models import ToolType, ToolDomain
from .scopes import (
    Scope,
    LegacyScope,
    PERSONAS,
    LEGACY_ROLE_TO_PERSONA,
    expand_legacy_scopes,
    get_scopes_for_roles,
    get_required_scopes_for_tool,
    TOOL_SCOPE_REQUIREMENTS,
    PROXIED_TOOL_REQUIRED_SCOPES,
)

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
    CAB-604: Updated with 12 granular OAuth2 scopes and 6 personas.
    """

    def __init__(self) -> None:
        # =====================================================================
        # CAB-604: Granular Scope Configuration (from scopes.py)
        # =====================================================================
        # Tool scope requirements are now defined in scopes.py
        # This class uses the centralized definitions

        # Legacy role to scope mapping (backward compatibility)
        # These roles grant legacy scopes which are then expanded
        self.legacy_role_scopes = {
            "cpi-admin": {LegacyScope.ADMIN.value, LegacyScope.WRITE.value, LegacyScope.READ.value},
            "tenant-admin": {LegacyScope.WRITE.value, LegacyScope.READ.value},
            "devops": {LegacyScope.WRITE.value, LegacyScope.READ.value},
            "viewer": {LegacyScope.READ.value},
        }

        # =====================================================================
        # CAB-603: Tool Type Detection Patterns
        # =====================================================================
        self.core_tool_prefix = "stoa_"
        self.proxied_tool_separator = "__"

    def get_user_scopes(self, user: dict[str, Any]) -> set[str]:
        """Extract and expand scopes from user claims.

        CAB-604: Now supports both legacy scopes and granular scopes.
        Legacy scopes are automatically expanded to their granular equivalents.

        Args:
            user: User claims from JWT

        Returns:
            Set of all effective scopes (legacy + expanded granular)
        """
        scopes: set[str] = set()

        # 1. Check explicit scopes in token
        if "scope" in user:
            scope_str = user.get("scope", "")
            if isinstance(scope_str, str):
                scopes.update(scope_str.split())

        # 2. Extract roles from token
        roles: list[str] = []
        if "realm_access" in user and "roles" in user["realm_access"]:
            roles = user["realm_access"]["roles"]
        elif "roles" in user:
            roles = user["roles"]

        # 3. CAB-604: Map persona roles to scopes
        role_scopes = get_scopes_for_roles(roles)
        scopes.update(role_scopes)

        # 4. Map legacy roles to legacy scopes (backward compat)
        for role in roles:
            if role in self.legacy_role_scopes:
                scopes.update(self.legacy_role_scopes[role])

        # 5. Expand legacy scopes to granular scopes
        expanded_scopes = expand_legacy_scopes(scopes)

        return expanded_scopes

    def get_user_persona(self, user: dict[str, Any]) -> str | None:
        """Get the user's persona from their roles.

        CAB-604: Returns the highest-privilege persona for the user.

        Args:
            user: User claims from JWT

        Returns:
            Persona name or None if no matching persona
        """
        roles: list[str] = []
        if "realm_access" in user and "roles" in user["realm_access"]:
            roles = user["realm_access"]["roles"]
        elif "roles" in user:
            roles = user["roles"]

        # Check for persona roles
        for role in roles:
            if role in PERSONAS:
                return role
            if role in LEGACY_ROLE_TO_PERSONA:
                return LEGACY_ROLE_TO_PERSONA[role].keycloak_role

        return None

    def check_tenant_constraint(self, user: dict[str, Any], resource_tenant_id: str | None) -> bool:
        """Check if user can access resources in a tenant.

        CAB-604: Personas may be constrained to own tenant only.

        Args:
            user: User claims from JWT
            resource_tenant_id: Tenant ID of the resource

        Returns:
            True if access is allowed
        """
        if not resource_tenant_id:
            return True  # Global resources accessible to all

        user_tenant_id = user.get("tenant_id")
        scopes = self.get_user_scopes(user)

        # Admin scope bypasses tenant isolation
        if LegacyScope.ADMIN.value in scopes or Scope.ADMIN_READ.value in scopes:
            return True

        # Check persona constraints
        persona_name = self.get_user_persona(user)
        if persona_name and persona_name in PERSONAS:
            persona = PERSONAS[persona_name]
            if not persona.own_tenant_only:
                return True  # Persona can access all tenants

        # Otherwise, must match tenant
        return user_tenant_id == resource_tenant_id

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
        - Core tools: Check against TOOL_SCOPE_REQUIREMENTS from scopes.py
        - Proxied tools: Check tenant membership + stoa:tools:execute scope
        - Legacy tools: Backward compatible behavior

        CAB-604: Uses granular OAuth2 scopes with legacy scope expansion.

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

        # Admin scopes grant full access (legacy or granular)
        if LegacyScope.ADMIN.value in scopes or Scope.ADMIN_WRITE.value in scopes:
            return PolicyDecision(
                allowed=True,
                reason="Admin access granted",
                metadata={"scope": "admin", "tool_type": tool_type},
            )

        # =====================================================================
        # CAB-604: Proxied Tool Authorization (requires tools:execute)
        # =====================================================================
        if tool_type == "proxied":
            # Parse namespace to get tenant
            namespace = self._parse_proxied_tool_namespace(tool_name)
            proxied_tenant_id = namespace.get("tenant_id") or tool_tenant_id

            # Tenant isolation check for proxied tools
            if not self.check_tenant_constraint(user, proxied_tenant_id):
                return PolicyDecision(
                    allowed=False,
                    reason=f"Tenant mismatch: user={user_tenant_id}, tool={proxied_tenant_id}",
                    metadata={"tool_type": "proxied"},
                )

            # CAB-604: Proxied tools require tools:execute scope
            required_scopes = PROXIED_TOOL_REQUIRED_SCOPES
            if required_scopes.issubset(scopes):
                return PolicyDecision(
                    allowed=True,
                    reason="Proxied tool access granted",
                    metadata={
                        "scopes": list(required_scopes),
                        "tool_type": "proxied",
                        "tenant_id": proxied_tenant_id,
                    },
                )

            # Also accept legacy stoa:read for backward compatibility
            if LegacyScope.READ.value in scopes:
                return PolicyDecision(
                    allowed=True,
                    reason="Proxied tool access granted (legacy scope)",
                    metadata={
                        "scope": LegacyScope.READ.value,
                        "tool_type": "proxied",
                        "tenant_id": proxied_tenant_id,
                    },
                )

            return PolicyDecision(
                allowed=False,
                reason=f"Missing scope {Scope.TOOLS_EXECUTE.value} for proxied tool {tool_name}",
                metadata={"tool_type": "proxied", "required_scopes": list(required_scopes)},
            )

        # =====================================================================
        # CAB-604: Core Tool Authorization (granular scopes)
        # =====================================================================

        # Check tenant isolation (if tool has tenant_id)
        if not self.check_tenant_constraint(user, tool_tenant_id):
            return PolicyDecision(
                allowed=False,
                reason=f"Tenant mismatch: user={user_tenant_id}, tool={tool_tenant_id}",
                metadata={"tool_type": tool_type},
            )

        # Get required scopes for the tool
        required_scopes = get_required_scopes_for_tool(tool_name, tool_type)

        # Check if user has any of the required scopes
        if required_scopes.issubset(scopes):
            return PolicyDecision(
                allowed=True,
                reason="Access granted",
                metadata={"scopes": list(required_scopes), "tool_type": tool_type},
            )

        # CAB-604: Check legacy scopes for backward compatibility
        # Legacy read grants basic tool access
        if LegacyScope.READ.value in scopes:
            # Check if this is a read-only operation
            read_scopes = {
                Scope.CATALOG_READ.value,
                Scope.SUBSCRIPTION_READ.value,
                Scope.OBSERVABILITY_READ.value,
                Scope.TOOLS_READ.value,
                Scope.SECURITY_READ.value,
                Scope.ADMIN_READ.value,
            }
            if required_scopes.issubset(read_scopes | {Scope.TOOLS_EXECUTE.value}):
                return PolicyDecision(
                    allowed=True,
                    reason="Access granted (legacy read scope)",
                    metadata={"scope": LegacyScope.READ.value, "tool_type": tool_type},
                )

        # Legacy write grants write operations
        if LegacyScope.WRITE.value in scopes:
            write_scopes = {
                Scope.CATALOG_WRITE.value,
                Scope.SUBSCRIPTION_WRITE.value,
                Scope.OBSERVABILITY_WRITE.value,
            }
            if required_scopes.issubset(write_scopes):
                return PolicyDecision(
                    allowed=True,
                    reason="Access granted (legacy write scope)",
                    metadata={"scope": LegacyScope.WRITE.value, "tool_type": tool_type},
                )

        # Admin tools require admin scopes
        admin_required = {Scope.ADMIN_READ.value, Scope.ADMIN_WRITE.value, Scope.SECURITY_WRITE.value}
        if required_scopes & admin_required:
            return PolicyDecision(
                allowed=False,
                reason=f"Tool {tool_name} requires admin scope",
                metadata={"tool_type": tool_type, "required_scopes": list(required_scopes)},
            )

        return PolicyDecision(
            allowed=False,
            reason=f"Missing required scopes for tool {tool_name}",
            metadata={"tool_type": tool_type, "required_scopes": list(required_scopes)},
        )

    def evaluate_tenant_isolation(
        self,
        user: dict[str, Any],
        tool: dict[str, Any],
    ) -> PolicyDecision:
        """Check tenant isolation policy.

        CAB-604: Uses persona-based tenant constraints.

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

        # Use the new tenant constraint check
        if self.check_tenant_constraint(user, tool_tenant_id):
            return PolicyDecision(
                allowed=True,
                reason="Tenant access granted",
                metadata={"user_tenant": user_tenant_id, "tool_tenant": tool_tenant_id},
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
