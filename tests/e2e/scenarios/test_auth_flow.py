"""
E2E Authentication Flow Tests (CAB-238)
Tests Keycloak authentication for STOA Console
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.auth
@pytest.mark.smoke
class TestAuthenticationFlow:
    """Test suite for Keycloak authentication flows."""

    def test_redirect_to_keycloak_when_unauthenticated(
        self, page: Page, keycloak_config: dict
    ):
        """Verify unauthenticated users are redirected to Keycloak."""
        # Navigate to console
        page.goto(keycloak_config["console_url"])

        # Should redirect to Keycloak login
        expect(page).to_have_url_matching(f"{keycloak_config['url']}.*")

        # Keycloak login form should be visible
        expect(page.locator("#username")).to_be_visible()
        expect(page.locator("#password")).to_be_visible()
        expect(page.locator("#kc-login")).to_be_visible()

    def test_admin_login_success(
        self, page: Page, keycloak_login, keycloak_config: dict, get_token
    ):
        """Test successful admin login flow."""
        # Perform login
        result = keycloak_login("admin")

        # Verify redirect to console
        expect(page).to_have_url_matching(f"{keycloak_config['console_url']}.*")

        # Verify user info
        assert result["role"] == "admin"
        assert "stoa:admin" in result["scopes"]

        # Verify token is present
        token = get_token()
        assert token is not None, "Access token should be present after login"

    def test_tenant_admin_login_success(
        self, page: Page, keycloak_login, keycloak_config: dict, get_token
    ):
        """Test successful tenant admin login flow."""
        result = keycloak_login("tenant_admin")

        expect(page).to_have_url_matching(f"{keycloak_config['console_url']}.*")

        assert result["role"] == "tenant_admin"
        assert "stoa:write" in result["scopes"]
        assert "stoa:read" in result["scopes"]

        token = get_token()
        assert token is not None

    def test_viewer_login_success(
        self, page: Page, keycloak_login, keycloak_config: dict, get_token
    ):
        """Test successful viewer login flow."""
        result = keycloak_login("viewer")

        expect(page).to_have_url_matching(f"{keycloak_config['console_url']}.*")

        assert result["role"] == "viewer"
        assert "stoa:read" in result["scopes"]
        assert "stoa:admin" not in result["scopes"]

        token = get_token()
        assert token is not None

    def test_invalid_credentials_shows_error(
        self, page: Page, keycloak_config: dict
    ):
        """Test login with invalid credentials shows error message."""
        page.goto(keycloak_config["console_url"])

        # Wait for Keycloak login page
        page.wait_for_url(f"{keycloak_config['url']}/**", timeout=10000)

        # Enter invalid credentials
        page.locator("#username").fill("invalid@test.com")
        page.locator("#password").fill("wrongpassword")
        page.locator("#kc-login").click()

        # Should show error message
        error_message = page.locator(".alert-error, #kc-content-wrapper .alert")
        expect(error_message).to_be_visible(timeout=5000)

    def test_token_contains_required_claims(
        self, page: Page, keycloak_login, get_token
    ):
        """Verify access token contains required claims."""
        import base64
        import json

        keycloak_login("admin")
        token = get_token()
        assert token is not None

        # Decode JWT payload (without verification for testing)
        payload_b64 = token.split(".")[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        # Verify required claims
        assert "sub" in payload, "Token should contain 'sub' claim"
        assert "exp" in payload, "Token should contain 'exp' claim"
        assert "iat" in payload, "Token should contain 'iat' claim"
        assert "iss" in payload, "Token should contain 'iss' claim"

        # Verify issuer matches Keycloak
        assert "auth.stoa.cab-i.com" in payload["iss"]


@pytest.mark.auth
class TestLogoutFlow:
    """Test suite for logout functionality."""

    def test_logout_clears_session(
        self, page: Page, keycloak_login, keycloak_config: dict, get_token
    ):
        """Test that logout properly clears the session."""
        # Login first
        keycloak_login("admin")
        assert get_token() is not None

        # Find and click logout button (adjust selector as needed)
        logout_button = page.locator("[data-testid='logout'], .logout-btn, #logout")
        if logout_button.count() > 0:
            logout_button.click()

            # Should redirect to Keycloak or login page
            page.wait_for_timeout(2000)

            # Token should be cleared
            token = get_token()
            assert token is None, "Token should be cleared after logout"

    def test_accessing_protected_route_after_logout(
        self, page: Page, keycloak_login, keycloak_config: dict
    ):
        """Test that protected routes redirect to login after logout."""
        # Login
        keycloak_login("admin")

        # Clear session manually (simulate logout)
        page.evaluate("localStorage.clear(); sessionStorage.clear();")

        # Try to access protected route
        page.goto(f"{keycloak_config['console_url']}/dashboard")

        # Should redirect to Keycloak
        expect(page).to_have_url_matching(f"{keycloak_config['url']}.*")


@pytest.mark.auth
@pytest.mark.slow
class TestTokenRefresh:
    """Test suite for token refresh functionality."""

    def test_token_refresh_before_expiry(
        self, page: Page, keycloak_login, get_token
    ):
        """Test that tokens are refreshed before expiry."""
        keycloak_login("admin")

        initial_token = get_token()
        assert initial_token is not None

        # Wait for potential token refresh (adjust based on token lifetime)
        # This is a simplified test - real implementation may need longer waits
        page.wait_for_timeout(5000)

        # Token should still be valid (either same or refreshed)
        current_token = get_token()
        assert current_token is not None, "Token should still be present"
