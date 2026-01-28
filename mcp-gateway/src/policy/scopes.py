# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""CAB-604: OAuth2 Scopes and Persona Definitions for MCP RBAC Phase 2.

Defines the 12 granular OAuth2 scopes and 6 personas for fine-grained
access control in the MCP Gateway.

Scope Naming Convention:
    stoa:{domain}:{action}
    - domain: catalog, subscription, observability, tools, admin
    - action: read, write, admin, execute

Personas map to Keycloak realm roles with assigned scopes.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet


# =============================================================================
# CAB-604: OAuth2 Scopes (12 granular scopes)
# =============================================================================


class Scope(str, Enum):
    """OAuth2 scopes for MCP Gateway.

    12 granular scopes organized by domain and action.
    """

    # API Catalog
    CATALOG_READ = "stoa:catalog:read"       # Browse APIs, view specs
    CATALOG_WRITE = "stoa:catalog:write"     # Create/modify API entries

    # Subscriptions
    SUBSCRIPTION_READ = "stoa:subscription:read"    # View own subscriptions
    SUBSCRIPTION_WRITE = "stoa:subscription:write"  # Subscribe/unsubscribe

    # Observability
    OBSERVABILITY_READ = "stoa:observability:read"      # View metrics, logs
    OBSERVABILITY_WRITE = "stoa:observability:write"    # Configure alerts

    # MCP Tools
    TOOLS_READ = "stoa:tools:read"       # List/discover tools
    TOOLS_EXECUTE = "stoa:tools:execute" # Execute tools (invoke APIs)

    # Administration
    ADMIN_READ = "stoa:admin:read"     # View all tenants, global metrics
    ADMIN_WRITE = "stoa:admin:write"   # Manage tenants, platform config

    # Security
    SECURITY_READ = "stoa:security:read"    # View audit logs, policies
    SECURITY_WRITE = "stoa:security:write"  # Manage security policies


# Legacy scope names for backward compatibility
class LegacyScope(str, Enum):
    """Legacy OAuth2 scopes for backward compatibility.

    These map to the new granular scopes.
    """
    READ = "stoa:read"
    WRITE = "stoa:write"
    ADMIN = "stoa:admin"


# =============================================================================
# Legacy to Granular Scope Mapping
# =============================================================================

# Map legacy scopes to their equivalent granular scopes
LEGACY_TO_GRANULAR: dict[str, FrozenSet[str]] = {
    LegacyScope.READ.value: frozenset({
        Scope.CATALOG_READ.value,
        Scope.SUBSCRIPTION_READ.value,
        Scope.OBSERVABILITY_READ.value,
        Scope.TOOLS_READ.value,
    }),
    LegacyScope.WRITE.value: frozenset({
        # Write includes all read scopes
        Scope.CATALOG_READ.value,
        Scope.CATALOG_WRITE.value,
        Scope.SUBSCRIPTION_READ.value,
        Scope.SUBSCRIPTION_WRITE.value,
        Scope.OBSERVABILITY_READ.value,
        Scope.OBSERVABILITY_WRITE.value,
        Scope.TOOLS_READ.value,
        Scope.TOOLS_EXECUTE.value,
    }),
    LegacyScope.ADMIN.value: frozenset({
        # Admin includes all scopes
        Scope.CATALOG_READ.value,
        Scope.CATALOG_WRITE.value,
        Scope.SUBSCRIPTION_READ.value,
        Scope.SUBSCRIPTION_WRITE.value,
        Scope.OBSERVABILITY_READ.value,
        Scope.OBSERVABILITY_WRITE.value,
        Scope.TOOLS_READ.value,
        Scope.TOOLS_EXECUTE.value,
        Scope.ADMIN_READ.value,
        Scope.ADMIN_WRITE.value,
        Scope.SECURITY_READ.value,
        Scope.SECURITY_WRITE.value,
    }),
}


def expand_legacy_scopes(scopes: set[str]) -> set[str]:
    """Expand legacy scopes to their granular equivalents.

    This enables backward compatibility: users with stoa:read will
    automatically have stoa:catalog:read, stoa:subscription:read, etc.

    Args:
        scopes: Set of scope strings (may include legacy and/or granular)

    Returns:
        Expanded set including all granular scopes implied by legacy scopes
    """
    expanded = set(scopes)

    for legacy_scope, granular_scopes in LEGACY_TO_GRANULAR.items():
        if legacy_scope in scopes:
            expanded.update(granular_scopes)

    return expanded


# =============================================================================
# CAB-604: Persona Definitions (6 personas)
# =============================================================================


@dataclass(frozen=True)
class Persona:
    """Persona definition with role name and assigned scopes.

    Personas are mapped to Keycloak realm roles.
    """
    name: str
    description: str
    keycloak_role: str  # Realm role name in Keycloak
    scopes: FrozenSet[str]

    # Constraints for tenant isolation
    own_tenant_only: bool = True  # Can only access own tenant resources
    own_resources_only: bool = False  # Can only access own resources (not all tenant)


# Define the 6 personas
STOA_ADMIN = Persona(
    name="stoa.admin",
    description="Platform administrator with full access",
    keycloak_role="stoa.admin",
    scopes=frozenset({
        Scope.CATALOG_READ.value,
        Scope.CATALOG_WRITE.value,
        Scope.SUBSCRIPTION_READ.value,
        Scope.SUBSCRIPTION_WRITE.value,
        Scope.OBSERVABILITY_READ.value,
        Scope.OBSERVABILITY_WRITE.value,
        Scope.TOOLS_READ.value,
        Scope.TOOLS_EXECUTE.value,
        Scope.ADMIN_READ.value,
        Scope.ADMIN_WRITE.value,
        Scope.SECURITY_READ.value,
        Scope.SECURITY_WRITE.value,
    }),
    own_tenant_only=False,  # Can access all tenants
    own_resources_only=False,
)

STOA_PRODUCT_OWNER = Persona(
    name="stoa.product_owner",
    description="API Product Owner - manages API catalog for tenant",
    keycloak_role="stoa.product_owner",
    scopes=frozenset({
        Scope.CATALOG_READ.value,
        Scope.CATALOG_WRITE.value,
        Scope.SUBSCRIPTION_READ.value,
        Scope.OBSERVABILITY_READ.value,
        Scope.TOOLS_READ.value,
    }),
    own_tenant_only=True,
    own_resources_only=False,
)

STOA_DEVELOPER = Persona(
    name="stoa.developer",
    description="API Developer - develops and tests APIs for tenant",
    keycloak_role="stoa.developer",
    scopes=frozenset({
        Scope.CATALOG_READ.value,
        Scope.SUBSCRIPTION_READ.value,
        Scope.SUBSCRIPTION_WRITE.value,
        Scope.OBSERVABILITY_READ.value,
        Scope.TOOLS_READ.value,
        Scope.TOOLS_EXECUTE.value,
    }),
    own_tenant_only=True,
    own_resources_only=False,
)

STOA_CONSUMER = Persona(
    name="stoa.consumer",
    description="API Consumer - discovers and uses APIs",
    keycloak_role="stoa.consumer",
    scopes=frozenset({
        Scope.CATALOG_READ.value,
        Scope.SUBSCRIPTION_READ.value,
        Scope.SUBSCRIPTION_WRITE.value,
        Scope.TOOLS_READ.value,
        Scope.TOOLS_EXECUTE.value,
    }),
    own_tenant_only=True,
    own_resources_only=True,  # Can only see own subscriptions
)

STOA_SECURITY = Persona(
    name="stoa.security",
    description="Security Officer - audits and monitors platform",
    keycloak_role="stoa.security",
    scopes=frozenset({
        Scope.CATALOG_READ.value,
        Scope.SUBSCRIPTION_READ.value,
        Scope.OBSERVABILITY_READ.value,
        Scope.SECURITY_READ.value,
        Scope.SECURITY_WRITE.value,
        Scope.ADMIN_READ.value,
        Scope.TOOLS_READ.value,
    }),
    own_tenant_only=False,  # Can audit across tenants
    own_resources_only=False,
)

STOA_AGENT = Persona(
    name="stoa.agent",
    description="MCP Agent - AI agents executing tools",
    keycloak_role="stoa.agent",
    scopes=frozenset({
        Scope.CATALOG_READ.value,
        Scope.TOOLS_READ.value,
        Scope.TOOLS_EXECUTE.value,
    }),
    own_tenant_only=True,
    own_resources_only=False,
)


# All personas by role name
PERSONAS: dict[str, Persona] = {
    persona.keycloak_role: persona
    for persona in [
        STOA_ADMIN,
        STOA_PRODUCT_OWNER,
        STOA_DEVELOPER,
        STOA_CONSUMER,
        STOA_SECURITY,
        STOA_AGENT,
    ]
}

# Legacy role to persona mapping (backward compatibility)
LEGACY_ROLE_TO_PERSONA: dict[str, Persona] = {
    "cpi-admin": STOA_ADMIN,
    "tenant-admin": STOA_PRODUCT_OWNER,  # Maps to product owner (tenant-level)
    "devops": STOA_DEVELOPER,  # Maps to developer
    "viewer": STOA_CONSUMER,  # Maps to consumer (read-only)
}


def get_persona_for_roles(roles: list[str]) -> Persona | None:
    """Get the highest-privilege persona for a list of roles.

    Args:
        roles: List of Keycloak realm roles

    Returns:
        Highest-privilege persona, or None if no matching persona
    """
    # Priority order (highest to lowest privilege)
    priority = [
        STOA_ADMIN,
        STOA_SECURITY,
        STOA_PRODUCT_OWNER,
        STOA_DEVELOPER,
        STOA_CONSUMER,
        STOA_AGENT,
    ]

    for persona in priority:
        if persona.keycloak_role in roles:
            return persona
        # Check legacy role mapping
        for legacy_role, mapped_persona in LEGACY_ROLE_TO_PERSONA.items():
            if legacy_role in roles and mapped_persona == persona:
                return persona

    return None


def get_scopes_for_roles(roles: list[str]) -> set[str]:
    """Get all scopes granted by a list of roles.

    Includes both direct persona scopes and legacy role expansions.

    Args:
        roles: List of Keycloak realm roles

    Returns:
        Set of all granted scopes
    """
    scopes: set[str] = set()

    # Add scopes from matching personas
    for role in roles:
        if role in PERSONAS:
            scopes.update(PERSONAS[role].scopes)
        elif role in LEGACY_ROLE_TO_PERSONA:
            scopes.update(LEGACY_ROLE_TO_PERSONA[role].scopes)

    return scopes


# =============================================================================
# Tool to Scope Mapping
# =============================================================================

# Map tool name patterns to required scopes
TOOL_SCOPE_REQUIREMENTS: dict[str, set[str]] = {
    # Platform & Discovery - read scopes
    "stoa_platform_info": {Scope.TOOLS_READ.value},
    "stoa_platform_health": {Scope.TOOLS_READ.value},
    "stoa_list_tools": {Scope.TOOLS_READ.value},
    "stoa_get_tool_schema": {Scope.TOOLS_READ.value},
    "stoa_search_tools": {Scope.TOOLS_READ.value},
    "stoa_list_tenants": {Scope.ADMIN_READ.value},  # Admin only

    # API Catalog - catalog scopes
    "stoa_catalog_list_apis": {Scope.CATALOG_READ.value},
    "stoa_catalog_get_api": {Scope.CATALOG_READ.value},
    "stoa_catalog_search_apis": {Scope.CATALOG_READ.value},
    "stoa_catalog_get_openapi": {Scope.CATALOG_READ.value},
    "stoa_catalog_list_versions": {Scope.CATALOG_READ.value},
    "stoa_catalog_get_documentation": {Scope.CATALOG_READ.value},
    "stoa_catalog_list_categories": {Scope.CATALOG_READ.value},
    "stoa_catalog_get_endpoints": {Scope.CATALOG_READ.value},

    # Subscriptions - subscription scopes
    "stoa_subscription_list": {Scope.SUBSCRIPTION_READ.value},
    "stoa_subscription_get": {Scope.SUBSCRIPTION_READ.value},
    "stoa_subscription_create": {Scope.SUBSCRIPTION_WRITE.value},
    "stoa_subscription_cancel": {Scope.SUBSCRIPTION_WRITE.value},
    "stoa_subscription_get_credentials": {Scope.SUBSCRIPTION_READ.value},
    "stoa_subscription_rotate_key": {Scope.SUBSCRIPTION_WRITE.value},

    # Observability - observability scopes
    "stoa_metrics_get_usage": {Scope.OBSERVABILITY_READ.value},
    "stoa_metrics_get_latency": {Scope.OBSERVABILITY_READ.value},
    "stoa_metrics_get_errors": {Scope.OBSERVABILITY_READ.value},
    "stoa_metrics_get_quota": {Scope.OBSERVABILITY_READ.value},
    "stoa_logs_search": {Scope.OBSERVABILITY_READ.value},
    "stoa_logs_get_recent": {Scope.OBSERVABILITY_READ.value},
    "stoa_alerts_list": {Scope.OBSERVABILITY_READ.value},
    "stoa_alerts_acknowledge": {Scope.OBSERVABILITY_WRITE.value},

    # UAC Contracts
    "stoa_uac_list_contracts": {Scope.CATALOG_READ.value},
    "stoa_uac_get_contract": {Scope.CATALOG_READ.value},
    "stoa_uac_validate_contract": {Scope.CATALOG_WRITE.value},
    "stoa_uac_get_sla": {Scope.OBSERVABILITY_READ.value},

    # Security - security scopes
    "stoa_security_audit_log": {Scope.SECURITY_READ.value},
    "stoa_security_check_permissions": {Scope.SECURITY_READ.value},
    "stoa_security_list_policies": {Scope.SECURITY_READ.value},

    # Legacy tools (backward compatibility)
    "stoa_list_apis": {Scope.CATALOG_READ.value},
    "stoa_health_check": {Scope.TOOLS_READ.value},
    "stoa_search_apis": {Scope.CATALOG_READ.value},
    "stoa_get_api_details": {Scope.CATALOG_READ.value},
    "stoa_create_api": {Scope.CATALOG_WRITE.value},
    "stoa_update_api": {Scope.CATALOG_WRITE.value},
    "stoa_deploy_api": {Scope.CATALOG_WRITE.value},
    "stoa_delete_api": {Scope.ADMIN_WRITE.value},
    "stoa_delete_tool": {Scope.ADMIN_WRITE.value},
}

# Proxied tools require tools:execute scope + tenant membership
PROXIED_TOOL_REQUIRED_SCOPES = {Scope.TOOLS_EXECUTE.value}


def get_required_scopes_for_tool(tool_name: str, tool_type: str = "core") -> set[str]:
    """Get required scopes to invoke a tool.

    Args:
        tool_name: Tool name (e.g., stoa_catalog_list_apis, tenant__api__op)
        tool_type: Tool type (core, proxied, legacy)

    Returns:
        Set of required scope strings
    """
    # Proxied tools require execute scope
    if tool_type == "proxied" or "__" in tool_name:
        return PROXIED_TOOL_REQUIRED_SCOPES.copy()

    # Core tools have specific requirements
    if tool_name in TOOL_SCOPE_REQUIREMENTS:
        return TOOL_SCOPE_REQUIREMENTS[tool_name].copy()

    # Unknown core tools default to read
    if tool_name.startswith("stoa_"):
        return {Scope.TOOLS_READ.value}

    # Legacy/unknown tools default to execute
    return {Scope.TOOLS_EXECUTE.value}
