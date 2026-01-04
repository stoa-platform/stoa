"""Tests for OPA Policy Engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.policy.opa_client import (
    OPAClient,
    PolicyDecision,
    EmbeddedEvaluator,
    get_opa_client,
    shutdown_opa_client,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def evaluator() -> EmbeddedEvaluator:
    """Create a fresh embedded evaluator."""
    return EmbeddedEvaluator()


@pytest.fixture
def admin_user() -> dict:
    """Create an admin user claims dict."""
    return {
        "sub": "admin-123",
        "email": "admin@example.com",
        "realm_access": {"roles": ["cpi-admin"]},
        "tenant_id": "tenant-a",
    }


@pytest.fixture
def tenant_admin_user() -> dict:
    """Create a tenant admin user claims dict."""
    return {
        "sub": "tenant-admin-123",
        "email": "tenant-admin@example.com",
        "realm_access": {"roles": ["tenant-admin"]},
        "tenant_id": "tenant-a",
    }


@pytest.fixture
def devops_user() -> dict:
    """Create a devops user claims dict."""
    return {
        "sub": "devops-123",
        "email": "devops@example.com",
        "realm_access": {"roles": ["devops"]},
        "tenant_id": "tenant-a",
    }


@pytest.fixture
def viewer_user() -> dict:
    """Create a viewer user claims dict."""
    return {
        "sub": "viewer-123",
        "email": "viewer@example.com",
        "realm_access": {"roles": ["viewer"]},
        "tenant_id": "tenant-a",
    }


@pytest.fixture
def no_role_user() -> dict:
    """Create a user with no roles."""
    return {
        "sub": "norole-123",
        "email": "norole@example.com",
        "realm_access": {"roles": []},
        "tenant_id": "tenant-a",
    }


# =============================================================================
# EmbeddedEvaluator Tests
# =============================================================================


class TestEmbeddedEvaluatorScopes:
    """Tests for scope extraction."""

    def test_get_scopes_from_roles(self, evaluator: EmbeddedEvaluator, admin_user: dict):
        """Test extracting scopes from roles."""
        scopes = evaluator.get_user_scopes(admin_user)
        assert "stoa:admin" in scopes
        assert "stoa:write" in scopes
        assert "stoa:read" in scopes

    def test_get_scopes_viewer(self, evaluator: EmbeddedEvaluator, viewer_user: dict):
        """Test viewer only has read scope."""
        scopes = evaluator.get_user_scopes(viewer_user)
        assert "stoa:read" in scopes
        assert "stoa:write" not in scopes
        assert "stoa:admin" not in scopes

    def test_get_scopes_from_explicit_scope(self, evaluator: EmbeddedEvaluator):
        """Test extracting scopes from explicit scope claim."""
        user = {
            "sub": "test",
            "scope": "stoa:read stoa:write",
            "realm_access": {"roles": []},
        }
        scopes = evaluator.get_user_scopes(user)
        assert "stoa:read" in scopes
        assert "stoa:write" in scopes

    def test_get_scopes_no_roles(self, evaluator: EmbeddedEvaluator, no_role_user: dict):
        """Test user with no roles has no scopes."""
        scopes = evaluator.get_user_scopes(no_role_user)
        assert len(scopes) == 0


class TestEmbeddedEvaluatorAuthz:
    """Tests for authorization policy."""

    def test_admin_can_access_all_tools(self, evaluator: EmbeddedEvaluator, admin_user: dict):
        """Test admin can access any tool."""
        # Read-only tool
        decision = evaluator.evaluate_authz(
            admin_user,
            {"name": "stoa_platform_info"},
        )
        assert decision.allowed is True

        # Admin tool
        decision = evaluator.evaluate_authz(
            admin_user,
            {"name": "stoa_delete_api"},
        )
        assert decision.allowed is True

    def test_viewer_can_access_read_tools(self, evaluator: EmbeddedEvaluator, viewer_user: dict):
        """Test viewer can access read-only tools."""
        decision = evaluator.evaluate_authz(
            viewer_user,
            {"name": "stoa_platform_info"},
        )
        assert decision.allowed is True

        decision = evaluator.evaluate_authz(
            viewer_user,
            {"name": "stoa_list_apis"},
        )
        assert decision.allowed is True

    def test_viewer_cannot_access_write_tools(self, evaluator: EmbeddedEvaluator, viewer_user: dict):
        """Test viewer cannot access write tools."""
        decision = evaluator.evaluate_authz(
            viewer_user,
            {"name": "stoa_create_api"},
        )
        assert decision.allowed is False
        assert "stoa:write" in decision.reason

    def test_viewer_cannot_access_admin_tools(self, evaluator: EmbeddedEvaluator, viewer_user: dict):
        """Test viewer cannot access admin tools."""
        decision = evaluator.evaluate_authz(
            viewer_user,
            {"name": "stoa_delete_api"},
        )
        assert decision.allowed is False
        assert "admin" in decision.reason

    def test_devops_can_access_write_tools(self, evaluator: EmbeddedEvaluator, devops_user: dict):
        """Test devops can access write tools."""
        decision = evaluator.evaluate_authz(
            devops_user,
            {"name": "stoa_create_api"},
        )
        assert decision.allowed is True

    def test_devops_cannot_access_admin_tools(self, evaluator: EmbeddedEvaluator, devops_user: dict):
        """Test devops cannot access admin tools."""
        decision = evaluator.evaluate_authz(
            devops_user,
            {"name": "stoa_delete_api"},
        )
        assert decision.allowed is False

    def test_no_role_user_denied(self, evaluator: EmbeddedEvaluator, no_role_user: dict):
        """Test user with no roles is denied."""
        decision = evaluator.evaluate_authz(
            no_role_user,
            {"name": "stoa_platform_info"},
        )
        assert decision.allowed is False


class TestEmbeddedEvaluatorTenantIsolation:
    """Tests for tenant isolation."""

    def test_tenant_isolation_same_tenant(
        self, evaluator: EmbeddedEvaluator, viewer_user: dict
    ):
        """Test user can access tools from same tenant."""
        decision = evaluator.evaluate_authz(
            viewer_user,
            {"name": "stoa_list_apis", "tenant_id": "tenant-a"},
        )
        assert decision.allowed is True

    def test_tenant_isolation_different_tenant(
        self, evaluator: EmbeddedEvaluator, viewer_user: dict
    ):
        """Test user cannot access tools from different tenant."""
        decision = evaluator.evaluate_authz(
            viewer_user,
            {"name": "stoa_list_apis", "tenant_id": "tenant-b"},
        )
        assert decision.allowed is False
        assert "Tenant mismatch" in decision.reason

    def test_admin_bypasses_tenant_isolation(
        self, evaluator: EmbeddedEvaluator, admin_user: dict
    ):
        """Test admin can access tools from any tenant."""
        decision = evaluator.evaluate_authz(
            admin_user,
            {"name": "stoa_list_apis", "tenant_id": "tenant-b"},
        )
        assert decision.allowed is True

    def test_global_tools_accessible_to_all(
        self, evaluator: EmbeddedEvaluator, viewer_user: dict
    ):
        """Test global tools (no tenant_id) are accessible."""
        decision = evaluator.evaluate_authz(
            viewer_user,
            {"name": "stoa_platform_info"},  # No tenant_id
        )
        assert decision.allowed is True

    def test_tenant_isolation_method(self, evaluator: EmbeddedEvaluator, viewer_user: dict):
        """Test tenant isolation helper method."""
        # Same tenant
        decision = evaluator.evaluate_tenant_isolation(
            viewer_user,
            {"name": "test", "tenant_id": "tenant-a"},
        )
        assert decision.allowed is True

        # Different tenant
        decision = evaluator.evaluate_tenant_isolation(
            viewer_user,
            {"name": "test", "tenant_id": "tenant-b"},
        )
        assert decision.allowed is False


class TestEmbeddedEvaluatorDynamicTools:
    """Tests for dynamically registered tools."""

    def test_dynamic_tool_allowed_with_read(
        self, evaluator: EmbeddedEvaluator, viewer_user: dict
    ):
        """Test unknown tools are allowed with read scope."""
        decision = evaluator.evaluate_authz(
            viewer_user,
            {"name": "api_tool_petstore_listpets"},  # Dynamic tool
        )
        assert decision.allowed is True
        assert decision.metadata.get("tool_type") == "dynamic"

    def test_dynamic_tool_denied_without_scope(
        self, evaluator: EmbeddedEvaluator, no_role_user: dict
    ):
        """Test unknown tools denied without any scope."""
        decision = evaluator.evaluate_authz(
            no_role_user,
            {"name": "api_tool_petstore_listpets"},
        )
        assert decision.allowed is False


# =============================================================================
# OPAClient Tests
# =============================================================================


class TestOPAClient:
    """Tests for OPA client."""

    @pytest.mark.asyncio
    async def test_client_startup_embedded(self):
        """Test client startup in embedded mode."""
        client = OPAClient(embedded=True)
        await client.startup()
        assert client._evaluator is not None
        await client.shutdown()

    @pytest.mark.asyncio
    async def test_client_startup_sidecar(self):
        """Test client startup in sidecar mode."""
        client = OPAClient(embedded=False, opa_url="http://localhost:8181")
        await client.startup()
        assert client._http_client is not None
        await client.shutdown()

    @pytest.mark.asyncio
    async def test_check_authorization_embedded(self, admin_user: dict):
        """Test authorization check in embedded mode."""
        client = OPAClient(embedded=True)
        await client.startup()

        allowed, reason = await client.check_authorization(
            admin_user,
            {"name": "stoa_platform_info"},
        )
        assert allowed is True

        await client.shutdown()

    @pytest.mark.asyncio
    async def test_check_authorization_disabled(self):
        """Test authorization when OPA is disabled."""
        with patch("src.policy.opa_client.get_settings") as mock_settings:
            mock_settings.return_value.opa_enabled = False
            mock_settings.return_value.opa_url = "http://localhost:8181"
            mock_settings.return_value.opa_embedded = True

            client = OPAClient()
            await client.startup()

            allowed, reason = await client.check_authorization(
                {"sub": "test"},
                {"name": "stoa_delete_api"},
            )
            assert allowed is True
            assert "disabled" in reason

            await client.shutdown()

    @pytest.mark.asyncio
    async def test_check_tenant_isolation(self, viewer_user: dict):
        """Test tenant isolation check."""
        client = OPAClient(embedded=True)
        await client.startup()

        # Same tenant
        allowed, reason = await client.check_tenant_isolation(
            viewer_user,
            {"name": "test", "tenant_id": "tenant-a"},
        )
        assert allowed is True

        # Different tenant
        allowed, reason = await client.check_tenant_isolation(
            viewer_user,
            {"name": "test", "tenant_id": "tenant-b"},
        )
        assert allowed is False

        await client.shutdown()


class TestOPAClientRemote:
    """Tests for OPA client in remote/sidecar mode."""

    @pytest.mark.asyncio
    async def test_remote_authorization_success(self):
        """Test remote authorization with mocked OPA response."""
        client = OPAClient(embedded=False, opa_url="http://localhost:8181")
        await client.startup()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": True}

        with patch.object(
            client._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            allowed, reason = await client.check_authorization(
                {"sub": "test", "realm_access": {"roles": ["viewer"]}},
                {"name": "stoa_list_apis"},
            )
            assert allowed is True
            mock_post.assert_called_once()

        await client.shutdown()

    @pytest.mark.asyncio
    async def test_remote_authorization_denied(self):
        """Test remote authorization denied."""
        client = OPAClient(embedded=False, opa_url="http://localhost:8181")
        await client.startup()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": False}

        with patch.object(
            client._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            allowed, reason = await client.check_authorization(
                {"sub": "test"},
                {"name": "stoa_delete_api"},
            )
            assert allowed is False

        await client.shutdown()

    @pytest.mark.asyncio
    async def test_remote_authorization_error_failopen(self):
        """Test remote authorization fails open on error."""
        client = OPAClient(embedded=False, opa_url="http://localhost:8181")
        await client.startup()

        with patch.object(
            client._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.side_effect = Exception("Connection refused")

            allowed, reason = await client.check_authorization(
                {"sub": "test"},
                {"name": "stoa_platform_info"},
            )
            # Should fail open
            assert allowed is True
            assert "error" in reason.lower()

        await client.shutdown()


# =============================================================================
# Singleton Tests
# =============================================================================


class TestOPAClientSingleton:
    """Tests for OPA client singleton."""

    @pytest.mark.asyncio
    async def test_get_opa_client_singleton(self):
        """Test get_opa_client returns singleton."""
        await shutdown_opa_client()  # Clean up

        client1 = await get_opa_client()
        client2 = await get_opa_client()
        assert client1 is client2

        await shutdown_opa_client()

    @pytest.mark.asyncio
    async def test_shutdown_clears_singleton(self):
        """Test shutdown clears the singleton."""
        client1 = await get_opa_client()
        await shutdown_opa_client()

        client2 = await get_opa_client()
        assert client1 is not client2

        await shutdown_opa_client()


# =============================================================================
# PolicyDecision Tests
# =============================================================================


class TestPolicyDecision:
    """Tests for PolicyDecision dataclass."""

    def test_policy_decision_bool_allowed(self):
        """Test PolicyDecision bool when allowed."""
        decision = PolicyDecision(allowed=True, reason="OK")
        assert bool(decision) is True

    def test_policy_decision_bool_denied(self):
        """Test PolicyDecision bool when denied."""
        decision = PolicyDecision(allowed=False, reason="Denied")
        assert bool(decision) is False

    def test_policy_decision_with_metadata(self):
        """Test PolicyDecision with metadata."""
        decision = PolicyDecision(
            allowed=True,
            reason="OK",
            metadata={"scope": "stoa:admin"},
        )
        assert decision.metadata["scope"] == "stoa:admin"
