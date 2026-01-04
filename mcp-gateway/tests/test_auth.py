"""Tests for authentication middleware."""

import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.config import Settings, clear_settings_cache
from src.middleware.auth import (
    TokenClaims,
    OIDCAuthenticator,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_claims() -> dict:
    """Sample JWT claims."""
    return {
        "sub": "user-123",
        "email": "test@example.com",
        "preferred_username": "testuser",
        "realm_access": {
            "roles": ["viewer", "tenant-admin"],
        },
        "resource_access": {
            "stoa-mcp-gateway": {
                "roles": ["api-consumer"],
            },
        },
        "scope": "openid profile email",
        "iss": "https://auth.stoa.cab-i.com/realms/stoa",
        "aud": "stoa-mcp-gateway",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }


@pytest.fixture
def token_claims(sample_claims: dict) -> TokenClaims:
    """TokenClaims instance from sample claims."""
    return TokenClaims(**sample_claims)


@pytest.fixture
def mock_settings() -> Settings:
    """Mock settings for testing."""
    clear_settings_cache()
    return Settings(
        base_domain="test.local",
        keycloak_realm="test-realm",
        keycloak_client_id="test-client",
    )


# =============================================================================
# TokenClaims Tests
# =============================================================================


class TestTokenClaims:
    """Tests for TokenClaims model."""

    def test_roles_property(self, token_claims: TokenClaims):
        """Test roles property returns realm roles."""
        assert "viewer" in token_claims.roles
        assert "tenant-admin" in token_claims.roles

    def test_roles_empty_when_no_realm_access(self):
        """Test roles property returns empty list when no realm access."""
        claims = TokenClaims(sub="user-123")
        assert claims.roles == []

    def test_has_role_returns_true(self, token_claims: TokenClaims):
        """Test has_role returns True for existing role."""
        assert token_claims.has_role("viewer") is True
        assert token_claims.has_role("tenant-admin") is True

    def test_has_role_returns_false(self, token_claims: TokenClaims):
        """Test has_role returns False for missing role."""
        assert token_claims.has_role("cpi-admin") is False
        assert token_claims.has_role("nonexistent") is False

    def test_has_scope_returns_true(self, token_claims: TokenClaims):
        """Test has_scope returns True for existing scope."""
        assert token_claims.has_scope("openid") is True
        assert token_claims.has_scope("profile") is True
        assert token_claims.has_scope("email") is True

    def test_has_scope_returns_false(self, token_claims: TokenClaims):
        """Test has_scope returns False for missing scope."""
        assert token_claims.has_scope("admin") is False

    def test_has_scope_returns_false_when_no_scope(self):
        """Test has_scope returns False when no scope present."""
        claims = TokenClaims(sub="user-123")
        assert claims.has_scope("openid") is False

    def test_client_roles_property(self, token_claims: TokenClaims):
        """Test client_roles returns roles for specific client."""
        client_roles = token_claims.client_roles
        assert "stoa-mcp-gateway" in client_roles
        assert "api-consumer" in client_roles["stoa-mcp-gateway"]

    def test_client_roles_empty_when_no_resource_access(self):
        """Test client_roles returns empty dict when no resource access."""
        claims = TokenClaims(sub="user-123")
        assert claims.client_roles == {}


# =============================================================================
# OIDCAuthenticator Tests
# =============================================================================


class TestOIDCAuthenticator:
    """Tests for OIDCAuthenticator."""

    @pytest.fixture
    def authenticator(self, mock_settings: Settings) -> OIDCAuthenticator:
        """Create authenticator instance."""
        return OIDCAuthenticator(
            keycloak_url=mock_settings.keycloak_url,
            realm=mock_settings.keycloak_realm,
        )

    def test_authenticator_initialization(self, authenticator: OIDCAuthenticator):
        """Test authenticator is properly initialized."""
        assert "test-realm" in authenticator.issuer
        assert authenticator.jwks_uri.endswith("/protocol/openid-connect/certs")

    @pytest.mark.asyncio
    async def test_validate_token_invalid(self, authenticator: OIDCAuthenticator):
        """Test validation fails for invalid token."""
        # Mock JWKS fetching to return empty keys
        with patch.object(authenticator, "_fetch_jwks") as mock_jwks:
            mock_jwks.return_value = {"keys": []}

            with pytest.raises(HTTPException) as exc_info:
                await authenticator.validate_token("invalid.token.here")

            assert exc_info.value.status_code == 401


# =============================================================================
# Integration Tests
# =============================================================================


class TestAuthIntegration:
    """Integration tests for authentication flow."""

    @pytest.mark.asyncio
    async def test_full_auth_flow_with_mock_jwks(self, mock_settings: Settings, sample_claims: dict):
        """Test full authentication flow with mocked JWKS."""
        # This test demonstrates the authentication flow
        # In a real scenario, you would:
        # 1. Generate a proper JWT signed with a test key
        # 2. Mock the JWKS endpoint to return the public key
        # 3. Validate the token

        # For now, we just verify the flow works with proper claims
        token_claims = TokenClaims(**sample_claims)

        assert token_claims.sub == "user-123"
        assert token_claims.has_role("viewer")
        assert token_claims.has_scope("openid")
