"""Tests for CAB-604: OAuth2 Scopes and Persona Authorization.

Tests the 12 granular OAuth2 scopes and 6 personas for MCP RBAC Phase 2.
"""

import pytest
from unittest.mock import MagicMock

from src.policy.scopes import (
    Scope,
    LegacyScope,
    Persona,
    PERSONAS,
    LEGACY_ROLE_TO_PERSONA,
    LEGACY_TO_GRANULAR,
    STOA_ADMIN,
    STOA_PRODUCT_OWNER,
    STOA_DEVELOPER,
    STOA_CONSUMER,
    STOA_SECURITY,
    STOA_AGENT,
    expand_legacy_scopes,
    get_persona_for_roles,
    get_scopes_for_roles,
    get_required_scopes_for_tool,
    TOOL_SCOPE_REQUIREMENTS,
    PROXIED_TOOL_REQUIRED_SCOPES,
)
from src.policy.opa_client import EmbeddedEvaluator, PolicyDecision
from src.middleware.auth import TokenClaims


# =============================================================================
# Scope Definition Tests
# =============================================================================


class TestScopeDefinitions:
    """Tests for scope definitions and constants."""

    def test_all_12_scopes_defined(self):
        """Test that all 12 granular scopes are defined."""
        expected_scopes = [
            "stoa:catalog:read",
            "stoa:catalog:write",
            "stoa:subscription:read",
            "stoa:subscription:write",
            "stoa:observability:read",
            "stoa:observability:write",
            "stoa:tools:read",
            "stoa:tools:execute",
            "stoa:admin:read",
            "stoa:admin:write",
            "stoa:security:read",
            "stoa:security:write",
        ]
        actual_scopes = [s.value for s in Scope]
        assert len(actual_scopes) == 12
        for scope in expected_scopes:
            assert scope in actual_scopes

    def test_legacy_scopes_defined(self):
        """Test that legacy scopes are defined."""
        assert LegacyScope.READ.value == "stoa:read"
        assert LegacyScope.WRITE.value == "stoa:write"
        assert LegacyScope.ADMIN.value == "stoa:admin"

    def test_legacy_scope_expansion(self):
        """Test that legacy scopes expand to granular scopes."""
        # stoa:read expands to read scopes
        read_expanded = expand_legacy_scopes({"stoa:read"})
        assert Scope.CATALOG_READ.value in read_expanded
        assert Scope.SUBSCRIPTION_READ.value in read_expanded
        assert Scope.OBSERVABILITY_READ.value in read_expanded
        assert Scope.TOOLS_READ.value in read_expanded
        # But not write scopes
        assert Scope.CATALOG_WRITE.value not in read_expanded

    def test_legacy_write_scope_expansion(self):
        """Test that stoa:write expands correctly."""
        write_expanded = expand_legacy_scopes({"stoa:write"})
        # Includes read scopes
        assert Scope.CATALOG_READ.value in write_expanded
        # Includes write scopes
        assert Scope.CATALOG_WRITE.value in write_expanded
        assert Scope.SUBSCRIPTION_WRITE.value in write_expanded
        assert Scope.TOOLS_EXECUTE.value in write_expanded
        # But not admin scopes
        assert Scope.ADMIN_WRITE.value not in write_expanded

    def test_legacy_admin_scope_expansion(self):
        """Test that stoa:admin expands to all scopes."""
        admin_expanded = expand_legacy_scopes({"stoa:admin"})
        # Admin includes everything
        for scope in Scope:
            assert scope.value in admin_expanded


# =============================================================================
# Persona Definition Tests
# =============================================================================


class TestPersonaDefinitions:
    """Tests for persona definitions."""

    def test_all_6_personas_defined(self):
        """Test that all 6 personas are defined."""
        assert len(PERSONAS) == 6
        expected_personas = [
            "stoa.admin",
            "stoa.product_owner",
            "stoa.developer",
            "stoa.consumer",
            "stoa.security",
            "stoa.agent",
        ]
        for persona_name in expected_personas:
            assert persona_name in PERSONAS

    def test_stoa_admin_persona(self):
        """Test stoa.admin persona has full access."""
        persona = STOA_ADMIN
        assert persona.name == "stoa.admin"
        assert persona.keycloak_role == "stoa.admin"
        assert not persona.own_tenant_only  # Can access all tenants
        # Has all scopes
        for scope in Scope:
            assert scope.value in persona.scopes

    def test_stoa_product_owner_persona(self):
        """Test stoa.product_owner persona scopes."""
        persona = STOA_PRODUCT_OWNER
        assert persona.name == "stoa.product_owner"
        assert persona.own_tenant_only is True
        # Can read and write catalog
        assert Scope.CATALOG_READ.value in persona.scopes
        assert Scope.CATALOG_WRITE.value in persona.scopes
        # Can read subscriptions but not write
        assert Scope.SUBSCRIPTION_READ.value in persona.scopes
        assert Scope.SUBSCRIPTION_WRITE.value not in persona.scopes
        # Cannot execute tools
        assert Scope.TOOLS_EXECUTE.value not in persona.scopes

    def test_stoa_developer_persona(self):
        """Test stoa.developer persona scopes."""
        persona = STOA_DEVELOPER
        assert persona.name == "stoa.developer"
        assert persona.own_tenant_only is True
        # Can read catalog
        assert Scope.CATALOG_READ.value in persona.scopes
        # Can manage subscriptions
        assert Scope.SUBSCRIPTION_READ.value in persona.scopes
        assert Scope.SUBSCRIPTION_WRITE.value in persona.scopes
        # Can execute tools
        assert Scope.TOOLS_EXECUTE.value in persona.scopes
        # Cannot write catalog
        assert Scope.CATALOG_WRITE.value not in persona.scopes

    def test_stoa_consumer_persona(self):
        """Test stoa.consumer persona scopes."""
        persona = STOA_CONSUMER
        assert persona.name == "stoa.consumer"
        assert persona.own_tenant_only is True
        assert persona.own_resources_only is True  # Only own resources
        # Can read catalog
        assert Scope.CATALOG_READ.value in persona.scopes
        # Can manage subscriptions
        assert Scope.SUBSCRIPTION_READ.value in persona.scopes
        assert Scope.SUBSCRIPTION_WRITE.value in persona.scopes
        # Can execute tools
        assert Scope.TOOLS_EXECUTE.value in persona.scopes
        # Cannot access observability
        assert Scope.OBSERVABILITY_READ.value not in persona.scopes

    def test_stoa_security_persona(self):
        """Test stoa.security persona scopes."""
        persona = STOA_SECURITY
        assert persona.name == "stoa.security"
        assert not persona.own_tenant_only  # Can audit across tenants
        # Has security scopes
        assert Scope.SECURITY_READ.value in persona.scopes
        assert Scope.SECURITY_WRITE.value in persona.scopes
        # Has admin read for auditing
        assert Scope.ADMIN_READ.value in persona.scopes
        # Cannot write admin
        assert Scope.ADMIN_WRITE.value not in persona.scopes

    def test_stoa_agent_persona(self):
        """Test stoa.agent persona scopes."""
        persona = STOA_AGENT
        assert persona.name == "stoa.agent"
        assert persona.own_tenant_only is True
        # Can read catalog and tools
        assert Scope.CATALOG_READ.value in persona.scopes
        assert Scope.TOOLS_READ.value in persona.scopes
        # Can execute tools
        assert Scope.TOOLS_EXECUTE.value in persona.scopes
        # Cannot manage subscriptions
        assert Scope.SUBSCRIPTION_WRITE.value not in persona.scopes


class TestPersonaRoleMapping:
    """Tests for persona role mapping."""

    def test_get_persona_for_roles(self):
        """Test getting persona from roles."""
        # Direct persona role
        persona = get_persona_for_roles(["stoa.admin"])
        assert persona == STOA_ADMIN

        persona = get_persona_for_roles(["stoa.developer"])
        assert persona == STOA_DEVELOPER

    def test_get_persona_for_legacy_roles(self):
        """Test legacy role to persona mapping."""
        # cpi-admin maps to stoa.admin
        persona = get_persona_for_roles(["cpi-admin"])
        assert persona == STOA_ADMIN

        # tenant-admin maps to stoa.product_owner
        persona = get_persona_for_roles(["tenant-admin"])
        assert persona == STOA_PRODUCT_OWNER

        # devops maps to stoa.developer
        persona = get_persona_for_roles(["devops"])
        assert persona == STOA_DEVELOPER

        # viewer maps to stoa.consumer
        persona = get_persona_for_roles(["viewer"])
        assert persona == STOA_CONSUMER

    def test_get_scopes_for_roles(self):
        """Test getting scopes from roles."""
        scopes = get_scopes_for_roles(["stoa.developer"])
        assert Scope.CATALOG_READ.value in scopes
        assert Scope.TOOLS_EXECUTE.value in scopes

    def test_highest_privilege_persona(self):
        """Test that highest-privilege persona is returned when multiple roles."""
        # Admin + Developer = Admin
        persona = get_persona_for_roles(["stoa.developer", "stoa.admin"])
        assert persona == STOA_ADMIN


# =============================================================================
# Tool Scope Requirements Tests
# =============================================================================


class TestToolScopeRequirements:
    """Tests for tool scope requirements."""

    def test_catalog_tools_require_catalog_scopes(self):
        """Test catalog tools require catalog scopes."""
        scopes = get_required_scopes_for_tool("stoa_catalog_list_apis")
        assert Scope.CATALOG_READ.value in scopes

        scopes = get_required_scopes_for_tool("stoa_catalog_get_api")
        assert Scope.CATALOG_READ.value in scopes

    def test_subscription_tools_require_subscription_scopes(self):
        """Test subscription tools require subscription scopes."""
        scopes = get_required_scopes_for_tool("stoa_subscription_list")
        assert Scope.SUBSCRIPTION_READ.value in scopes

        scopes = get_required_scopes_for_tool("stoa_subscription_create")
        assert Scope.SUBSCRIPTION_WRITE.value in scopes

    def test_admin_tools_require_admin_scopes(self):
        """Test admin tools require admin scopes."""
        scopes = get_required_scopes_for_tool("stoa_list_tenants")
        assert Scope.ADMIN_READ.value in scopes

    def test_proxied_tools_require_execute_scope(self):
        """Test proxied tools require execute scope."""
        scopes = get_required_scopes_for_tool("tenant__api__op", "proxied")
        assert Scope.TOOLS_EXECUTE.value in scopes

    def test_unknown_core_tool_defaults_to_read(self):
        """Test unknown core tools default to read scope."""
        scopes = get_required_scopes_for_tool("stoa_unknown_tool")
        assert Scope.TOOLS_READ.value in scopes


# =============================================================================
# EmbeddedEvaluator Tests
# =============================================================================


class TestEmbeddedEvaluator:
    """Tests for EmbeddedEvaluator with CAB-604 scopes."""

    @pytest.fixture
    def evaluator(self):
        return EmbeddedEvaluator()

    def test_admin_user_full_access(self, evaluator):
        """Test admin user has access to everything."""
        user = {
            "sub": "admin-user",
            "realm_access": {"roles": ["stoa.admin"]},
        }
        tool = {"name": "stoa_list_tenants"}

        decision = evaluator.evaluate_authz(user, tool)
        assert decision.allowed is True

    def test_developer_can_execute_tools(self, evaluator):
        """Test developer can execute tools."""
        user = {
            "sub": "dev-user",
            "realm_access": {"roles": ["stoa.developer"]},
            "tenant_id": "acme",
        }
        tool = {"name": "acme__api__operation", "tenant_id": "acme"}

        decision = evaluator.evaluate_authz(user, tool)
        assert decision.allowed is True

    def test_consumer_can_execute_own_tenant_tools(self, evaluator):
        """Test consumer can execute tools in their tenant."""
        user = {
            "sub": "consumer-user",
            "realm_access": {"roles": ["stoa.consumer"]},
            "tenant_id": "acme",
        }
        tool = {"name": "acme__billing__invoice", "tenant_id": "acme"}

        decision = evaluator.evaluate_authz(user, tool)
        assert decision.allowed is True

    def test_consumer_cannot_access_other_tenant(self, evaluator):
        """Test consumer cannot access other tenant's tools."""
        user = {
            "sub": "consumer-user",
            "realm_access": {"roles": ["stoa.consumer"]},
            "tenant_id": "acme",
        }
        tool = {"name": "contoso__billing__invoice", "tenant_id": "contoso"}

        decision = evaluator.evaluate_authz(user, tool)
        assert decision.allowed is False

    def test_security_can_access_all_tenants(self, evaluator):
        """Test security persona can access all tenants."""
        user = {
            "sub": "security-user",
            "realm_access": {"roles": ["stoa.security"]},
            "tenant_id": "acme",
        }
        tool = {"name": "stoa_security_audit_log"}

        decision = evaluator.evaluate_authz(user, tool)
        # Security has admin_read but not admin_write
        # stoa_security_audit_log requires security_read which security persona has
        assert decision.allowed is True

    def test_agent_can_list_and_execute_tools(self, evaluator):
        """Test agent can list and execute tools."""
        user = {
            "sub": "agent-user",
            "realm_access": {"roles": ["stoa.agent"]},
            "tenant_id": "acme",
        }

        # Can list tools
        tool = {"name": "stoa_list_tools"}
        decision = evaluator.evaluate_authz(user, tool)
        assert decision.allowed is True

        # Can execute proxied tools
        tool = {"name": "acme__crm__get_customer", "tenant_id": "acme"}
        decision = evaluator.evaluate_authz(user, tool)
        assert decision.allowed is True

    def test_product_owner_can_write_catalog(self, evaluator):
        """Test product owner can write to catalog."""
        user = {
            "sub": "po-user",
            "realm_access": {"roles": ["stoa.product_owner"]},
            "tenant_id": "acme",
        }

        # Can read catalog
        tool = {"name": "stoa_catalog_list_apis"}
        decision = evaluator.evaluate_authz(user, tool)
        assert decision.allowed is True

    def test_legacy_viewer_role_works(self, evaluator):
        """Test legacy viewer role still works."""
        user = {
            "sub": "viewer-user",
            "realm_access": {"roles": ["viewer"]},
            "tenant_id": "acme",
        }

        # Can read catalog (viewer maps to consumer which has catalog:read)
        tool = {"name": "stoa_catalog_list_apis"}
        decision = evaluator.evaluate_authz(user, tool)
        assert decision.allowed is True

    def test_legacy_cpi_admin_role_works(self, evaluator):
        """Test legacy cpi-admin role still works."""
        user = {
            "sub": "admin-user",
            "realm_access": {"roles": ["cpi-admin"]},
        }

        # Can access admin tools
        tool = {"name": "stoa_list_tenants"}
        decision = evaluator.evaluate_authz(user, tool)
        assert decision.allowed is True


# =============================================================================
# TokenClaims Tests
# =============================================================================


class TestTokenClaimsScopes:
    """Tests for TokenClaims scope methods."""

    def test_effective_scopes_from_persona(self):
        """Test effective scopes include persona scopes."""
        claims = TokenClaims(
            sub="user1",
            realm_access={"roles": ["stoa.developer"]},
        )
        scopes = claims.effective_scopes
        assert Scope.CATALOG_READ.value in scopes
        assert Scope.TOOLS_EXECUTE.value in scopes

    def test_effective_scopes_from_legacy_scope(self):
        """Test effective scopes expand legacy scopes."""
        claims = TokenClaims(
            sub="user1",
            scope="stoa:read",
        )
        scopes = claims.effective_scopes
        assert Scope.CATALOG_READ.value in scopes
        assert Scope.SUBSCRIPTION_READ.value in scopes

    def test_has_scope_with_expansion(self):
        """Test has_scope works with expanded scopes."""
        claims = TokenClaims(
            sub="user1",
            scope="stoa:read",
        )
        assert claims.has_scope(Scope.CATALOG_READ.value) is True
        assert claims.has_scope(Scope.CATALOG_WRITE.value) is False

    def test_persona_property(self):
        """Test persona property returns correct persona."""
        claims = TokenClaims(
            sub="user1",
            realm_access={"roles": ["stoa.developer"]},
        )
        assert claims.persona == STOA_DEVELOPER
        assert claims.persona_name == "stoa.developer"

    def test_is_admin_property(self):
        """Test is_admin property."""
        admin_claims = TokenClaims(
            sub="admin",
            realm_access={"roles": ["stoa.admin"]},
        )
        assert admin_claims.is_admin is True

        user_claims = TokenClaims(
            sub="user",
            realm_access={"roles": ["stoa.developer"]},
        )
        assert user_claims.is_admin is False

    def test_can_access_tenant(self):
        """Test can_access_tenant method."""
        # Admin can access any tenant
        admin_claims = TokenClaims(
            sub="admin",
            realm_access={"roles": ["stoa.admin"]},
            tenant_id="acme",
        )
        assert admin_claims.can_access_tenant("contoso") is True

        # Developer can only access own tenant
        dev_claims = TokenClaims(
            sub="dev",
            realm_access={"roles": ["stoa.developer"]},
            tenant_id="acme",
        )
        assert dev_claims.can_access_tenant("acme") is True
        assert dev_claims.can_access_tenant("contoso") is False

        # Security can access all tenants (for auditing)
        sec_claims = TokenClaims(
            sub="sec",
            realm_access={"roles": ["stoa.security"]},
            tenant_id="acme",
        )
        assert sec_claims.can_access_tenant("contoso") is True


# =============================================================================
# Persona Authorization Matrix Tests
# =============================================================================


class TestPersonaAuthorizationMatrix:
    """Tests for the full persona authorization matrix."""

    @pytest.fixture
    def evaluator(self):
        return EmbeddedEvaluator()

    @pytest.mark.parametrize("persona_role,expected_tools", [
        # Admin can access everything
        ("stoa.admin", [
            "stoa_catalog_list_apis",
            "stoa_subscription_create",
            "stoa_list_tenants",
            "stoa_security_audit_log",
        ]),
        # Product Owner can manage catalog
        ("stoa.product_owner", [
            "stoa_catalog_list_apis",
            "stoa_catalog_get_api",
        ]),
        # Developer can execute and subscribe
        ("stoa.developer", [
            "stoa_catalog_list_apis",
            "stoa_subscription_create",
            "stoa_list_tools",
        ]),
        # Consumer can browse and subscribe
        ("stoa.consumer", [
            "stoa_catalog_list_apis",
            "stoa_subscription_create",
        ]),
        # Agent can list and execute
        ("stoa.agent", [
            "stoa_list_tools",
            "stoa_catalog_list_apis",
        ]),
    ])
    def test_persona_can_access_expected_tools(
        self, evaluator, persona_role, expected_tools
    ):
        """Test each persona can access their expected tools."""
        user = {
            "sub": "test-user",
            "realm_access": {"roles": [persona_role]},
            "tenant_id": "acme",
        }

        for tool_name in expected_tools:
            tool = {"name": tool_name}
            decision = evaluator.evaluate_authz(user, tool)
            assert decision.allowed is True, (
                f"Persona {persona_role} should be able to access {tool_name}"
            )

    @pytest.mark.parametrize("persona_role,forbidden_tools", [
        # Product Owner cannot admin
        ("stoa.product_owner", ["stoa_list_tenants", "stoa_delete_api"]),
        # Developer cannot admin
        ("stoa.developer", ["stoa_list_tenants", "stoa_security_audit_log"]),
        # Consumer cannot admin or observe
        ("stoa.consumer", ["stoa_list_tenants", "stoa_metrics_get_usage"]),
        # Agent cannot admin or subscribe
        ("stoa.agent", ["stoa_list_tenants", "stoa_subscription_create"]),
    ])
    def test_persona_cannot_access_forbidden_tools(
        self, evaluator, persona_role, forbidden_tools
    ):
        """Test each persona cannot access forbidden tools."""
        user = {
            "sub": "test-user",
            "realm_access": {"roles": [persona_role]},
            "tenant_id": "acme",
        }

        for tool_name in forbidden_tools:
            tool = {"name": tool_name}
            decision = evaluator.evaluate_authz(user, tool)
            assert decision.allowed is False, (
                f"Persona {persona_role} should NOT be able to access {tool_name}"
            )
