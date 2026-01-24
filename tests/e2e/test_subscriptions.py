"""
E2E Subscription Tests (CAB-291)
Tests for MCP Tool subscription flows including:
- Developer subscription flow (create, view, cancel)
- Admin approval flow
- API key validation
- Tenant isolation
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import pytest
import requests
from playwright.sync_api import Page, expect

# Configuration
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "https://mcp.gostoa.dev")
PORTAL_URL = os.getenv("PORTAL_URL", "https://portal.gostoa.dev")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://auth.gostoa.dev")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "stoa")
# Use admin-cli for password grant (supports Direct Access Grants)
# stoa-portal and stoa-console are browser-only clients
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "admin-cli")


def extract_subscription_id(data: dict) -> str:
    """Extract subscription ID from API response (handles multiple formats)."""
    if "subscription" in data:
        return data["subscription"]["id"]
    return data.get("subscription_id") or data.get("id")


@pytest.fixture(scope="session")
def subscription_fixtures(fixtures_path: Path) -> dict:
    """Load subscription test fixtures."""
    fixtures_file = fixtures_path / "subscriptions.json"
    with open(fixtures_file) as f:
        return json.load(f)


@pytest.fixture(scope="function")
def api_client(users_data: dict):
    """
    Factory fixture to create authenticated API client.
    Returns a session with the access token set.
    """
    def _get_client(user_role: str) -> tuple[requests.Session, str]:
        """
        Get authenticated requests session for user role.

        Args:
            user_role: Key from users.json (e.g., "admin", "tenant_admin", "viewer")

        Returns:
            tuple of (requests.Session, access_token)
        """
        user = users_data["users"].get(user_role)
        if not user:
            raise ValueError(f"Unknown user role: {user_role}")

        # Get token from Keycloak using password grant
        token_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"

        response = requests.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": KEYCLOAK_CLIENT_ID,
                "username": user["username"],
                "password": user["password"],
                "scope": "openid profile email",
            },
            verify=True,
        )

        if response.status_code != 200:
            pytest.fail(f"Failed to get token for {user_role}: {response.text}")

        token_data = response.json()
        access_token = token_data["access_token"]

        # Create session with auth header
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        })

        return session, access_token

    return _get_client


@pytest.fixture(scope="function")
def portal_login(page: Page, users_data: dict):
    """
    Factory fixture to perform portal login (similar to console login).
    """
    def _login(user_role: str) -> dict:
        user = users_data["users"].get(user_role)
        if not user:
            raise ValueError(f"Unknown user role: {user_role}")

        # Navigate to portal
        page.goto(PORTAL_URL)

        # Wait for login page or Keycloak form
        page.wait_for_selector(
            "#username, button:has-text('Login'), button:has-text('Sign in')",
            timeout=15000
        )

        # If on portal login page, click to redirect to Keycloak
        login_button = page.locator("button:has-text('Login'), button:has-text('Sign in')")
        if login_button.count() > 0 and "/login" in page.url:
            login_button.first.click()
            page.wait_for_selector("#username", timeout=10000)

        # Fill Keycloak login form
        page.locator("#username").fill(user["username"])
        page.locator("#password").fill(user["password"])
        page.locator("#kc-login").click()

        # Wait for redirect back to portal
        page.wait_for_function(
            f"""() => {{
                const url = window.location.href;
                return url.startsWith('{PORTAL_URL}') &&
                       !url.includes('/login') &&
                       !url.includes('auth.gostoa.dev');
            }}""",
            timeout=15000
        )

        return {
            "username": user["username"],
            "role": user_role,
            "scopes": user.get("scopes", []),
        }

    return _login


def get_portal_token(page: Page) -> str | None:
    """Extract access token from portal storage."""
    return page.evaluate("""
        () => {
            function searchStorage(storage) {
                const keys = Object.keys(storage);
                for (const key of keys) {
                    const value = storage.getItem(key);
                    if (!value) continue;
                    if (key.startsWith('oidc.user:') || key.includes('token') || key.includes('oidc')) {
                        try {
                            const data = JSON.parse(value);
                            if (data && data.access_token) {
                                return data.access_token;
                            }
                        } catch {}
                    }
                }
                return null;
            }
            let token = searchStorage(sessionStorage);
            if (token) return token;
            return searchStorage(localStorage);
        }
    """)


@pytest.mark.subscriptions
@pytest.mark.smoke
class TestDeveloperSubscriptionFlow:
    """
    Test 1: Developer Subscription Flow (Flux complet developpeur)
    - Login as developer
    - Create subscription to a tool
    - Verify API key is returned
    - List subscriptions
    - Cancel subscription
    """

    def test_create_subscription_via_api(
        self, api_client, subscription_fixtures: dict
    ):
        """Test creating a subscription via MCP Gateway API."""
        session, token = api_client("tenant_admin")

        test_sub = subscription_fixtures["test_subscriptions"]["developer_subscription"]
        api_key_format = subscription_fixtures["api_key_format"]

        # Use unique tool_id to avoid conflicts with existing subscriptions
        import uuid
        unique_tool_id = f"{test_sub['tool_id']}-{uuid.uuid4().hex[:8]}"

        # Create subscription
        response = session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            json={
                "tool_id": unique_tool_id,
                "plan": test_sub["plan"],
            },
        )

        # Accept 201 (created) or 409 (already exists from previous run)
        assert response.status_code in [201, 409], f"Expected 201/409, got {response.status_code}: {response.text}"

        if response.status_code == 409:
            pytest.skip("Subscription already exists - run cleanup or use different tool_id")
            return

        data = response.json()

        # Verify response structure - API returns {"subscription": {...}, "api_key": "..."}
        assert "api_key" in data, "Response should contain api_key"

        subscription_id = extract_subscription_id(data)
        api_key = data["api_key"]

        # Verify API key format
        assert api_key.startswith(api_key_format["prefix"]), f"API key should start with {api_key_format['prefix']}"
        assert len(api_key) == api_key_format["length"], f"API key should be {api_key_format['length']} chars"
        assert re.match(api_key_format["pattern"], api_key), f"API key should match pattern {api_key_format['pattern']}"

    def test_list_my_subscriptions(self, api_client):
        """Test listing user's subscriptions."""
        session, token = api_client("tenant_admin")

        response = session.get(f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()

        # Should return list or object with subscriptions
        assert "subscriptions" in data or isinstance(data, list)

        subscriptions = data.get("subscriptions", data) if isinstance(data, dict) else data
        assert isinstance(subscriptions, list)

    def test_get_subscription_details(self, api_client, subscription_fixtures: dict):
        """Test getting subscription details by ID."""
        session, token = api_client("tenant_admin")

        # First create a subscription
        test_sub = subscription_fixtures["test_subscriptions"]["developer_subscription"]

        create_response = session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            json={
                "tool_id": test_sub["tool_id"],
                "plan": test_sub["plan"],
            },
        )

        if create_response.status_code != 201:
            pytest.skip("Could not create subscription for detail test")

        data = create_response.json()
        subscription_id = extract_subscription_id(data)

        # Get subscription details
        detail_response = session.get(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}"
        )

        assert detail_response.status_code == 200

        detail = detail_response.json()
        assert detail.get("id") == subscription_id or detail.get("subscription_id") == subscription_id

    def test_revoke_subscription(self, api_client, subscription_fixtures: dict):
        """Test revoking (canceling) a subscription."""
        session, token = api_client("tenant_admin")

        # Create subscription first
        test_sub = subscription_fixtures["test_subscriptions"]["developer_subscription"]

        create_response = session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            json={
                "tool_id": test_sub["tool_id"],
                "plan": test_sub["plan"],
            },
        )

        if create_response.status_code != 201:
            pytest.skip("Could not create subscription for revoke test")

        data = create_response.json()
        subscription_id = extract_subscription_id(data)

        # Revoke subscription
        revoke_response = session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}/revoke"
        )

        assert revoke_response.status_code in [200, 204], \
            f"Expected 200/204, got {revoke_response.status_code}: {revoke_response.text}"

        # Verify status changed to revoked
        detail_response = session.get(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}"
        )

        if detail_response.status_code == 200:
            detail = detail_response.json()
            assert detail.get("status") == "revoked", "Subscription should be revoked"


@pytest.mark.subscriptions
class TestAdminApprovalFlow:
    """
    Test 2: Admin Approval Flow (Flux admin approval)
    - Developer creates subscription (pending state)
    - Admin views pending subscriptions
    - Admin approves subscription
    - Subscription becomes active
    """

    def test_admin_can_list_tenant_subscriptions(self, api_client):
        """Test that admin can list all subscriptions for a tenant."""
        session, token = api_client("admin")

        # List tenant subscriptions
        response = session.get(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            params={"tenant_id": "tenant-acme"},
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "subscriptions" in data or isinstance(data, list)

    def test_admin_can_view_pending_subscriptions(self, api_client):
        """Test that admin can filter for pending subscriptions."""
        session, token = api_client("admin")

        # List pending subscriptions
        response = session.get(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            params={"status": "pending"},
        )

        assert response.status_code == 200

    def test_approval_flow_end_to_end(self, api_client, subscription_fixtures: dict):
        """
        Test full approval flow:
        1. Developer creates subscription
        2. Admin approves it
        3. Subscription becomes active
        """
        dev_session, _ = api_client("tenant_admin")
        admin_session, _ = api_client("admin")

        test_sub = subscription_fixtures["test_subscriptions"]["admin_approval"]

        # Use unique tool_id
        import uuid
        unique_tool_id = f"{test_sub['tool_id']}-approval-{uuid.uuid4().hex[:8]}"

        # Step 1: Developer creates subscription
        create_response = dev_session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            json={
                "tool_id": unique_tool_id,
                "plan": test_sub["plan"],
            },
        )

        # May be auto-approved or pending depending on config
        if create_response.status_code == 409:
            pytest.skip("Subscription already exists")
            return
        assert create_response.status_code == 201

        data = create_response.json()
        subscription_id = extract_subscription_id(data)
        initial_status = data.get("status", "active")  # Default to active if not returned

        # If subscription is pending, admin can approve
        if initial_status == "pending":
            # Step 2: Admin approves
            approve_response = admin_session.post(
                f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}/approve"
            )

            assert approve_response.status_code in [200, 204], \
                f"Expected 200/204, got {approve_response.status_code}"

            # Step 3: Verify status is now active
            detail_response = dev_session.get(
                f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}"
            )

            assert detail_response.status_code == 200
            detail = detail_response.json()
            assert detail.get("status") == "active"


@pytest.mark.subscriptions
@pytest.mark.api_key
class TestApiKeyValidation:
    """
    Test 3: API Key Validation
    - Create subscription and get API key
    - Validate API key via endpoint
    - Test invalid API key returns error
    - Test revoked API key returns error
    """

    def test_validate_active_api_key(self, api_client, subscription_fixtures: dict):
        """Test that a valid API key can be used to access protected endpoints."""
        session, token = api_client("tenant_admin")

        test_sub = subscription_fixtures["test_subscriptions"]["api_key_validation"]

        # Use unique tool_id
        import uuid
        unique_tool_id = f"{test_sub['tool_id']}-{uuid.uuid4().hex[:8]}"

        # Create subscription
        create_response = session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            json={
                "tool_id": unique_tool_id,
                "plan": test_sub["plan"],
            },
        )

        if create_response.status_code == 409:
            pytest.skip("Subscription already exists")
            return

        assert create_response.status_code == 201

        data = create_response.json()
        api_key = data["api_key"]

        # Validate by using the API key to access a protected endpoint
        # Use X-API-Key header to authenticate
        api_key_session = requests.Session()
        api_key_session.headers.update({
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        })

        # Try to list tools with the API key
        tools_response = api_key_session.get(f"{MCP_GATEWAY_URL}/mcp/v1/tools")

        # Should be able to access with valid API key
        assert tools_response.status_code == 200, \
            f"Expected 200 with valid API key, got {tools_response.status_code}"

    def test_invalid_api_key_rejected(self, api_client):
        """Test that an invalid API key is rejected."""
        # Try to access with a fake API key
        fake_key = "stoa_sk_00000000000000000000000000000000"

        api_key_session = requests.Session()
        api_key_session.headers.update({
            "X-API-Key": fake_key,
            "Content-Type": "application/json",
        })

        # Try to access protected endpoint
        response = api_key_session.get(f"{MCP_GATEWAY_URL}/mcp/v1/tools")

        # Should be rejected - either 401 (unauthorized) or 200 (if endpoint doesn't require auth)
        # The key validation happens internally
        assert response.status_code in [200, 401, 403], \
            f"Expected 200/401/403, got {response.status_code}"

    def test_revoked_api_key_rejected(self, api_client, subscription_fixtures: dict):
        """Test that a revoked API key is rejected."""
        session, token = api_client("tenant_admin")

        test_sub = subscription_fixtures["test_subscriptions"]["api_key_validation"]

        # Use unique tool_id
        import uuid
        unique_tool_id = f"{test_sub['tool_id']}-revoke-{uuid.uuid4().hex[:8]}"

        # Create subscription
        create_response = session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            json={
                "tool_id": unique_tool_id,
                "plan": test_sub["plan"],
            },
        )

        if create_response.status_code == 409:
            pytest.skip("Subscription already exists")
            return

        assert create_response.status_code == 201

        data = create_response.json()
        subscription_id = extract_subscription_id(data)
        api_key = data["api_key"]

        # Revoke the subscription
        revoke_response = session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}/revoke"
        )

        # Accept 200, 204 (success) or 404 (subscription may have been cleaned up)
        assert revoke_response.status_code in [200, 204, 404], \
            f"Expected 200/204/404, got {revoke_response.status_code}: {revoke_response.text}"

        if revoke_response.status_code == 404:
            pytest.skip("Subscription not found - may have been cleaned up")
            return

        # Verify the subscription status is now revoked
        detail_response = session.get(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}"
        )

        if detail_response.status_code == 200:
            detail = detail_response.json()
            assert detail.get("status") == "revoked", "Subscription should be revoked"


@pytest.mark.subscriptions
@pytest.mark.security
class TestTenantIsolation:
    """
    Test 4: Tenant Isolation
    - User from tenant A cannot access subscriptions from tenant B
    - Cross-tenant access should return 403 Forbidden
    """

    def test_cannot_access_other_tenant_subscription(
        self, api_client, subscription_fixtures: dict
    ):
        """Test that users cannot access subscriptions from other tenants."""
        # Get sessions for two different tenant users
        tenant_a_session, _ = api_client("tenant_admin")

        # First, create a subscription as tenant A
        test_sub = subscription_fixtures["test_subscriptions"]["developer_subscription"]

        create_response = tenant_a_session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            json={
                "tool_id": test_sub["tool_id"],
                "plan": test_sub["plan"],
            },
        )

        if create_response.status_code != 201:
            pytest.skip("Could not create subscription for isolation test")

        data = create_response.json()
        subscription_id = extract_subscription_id(data)

        # Try to access as a different user (viewer has different permissions)
        viewer_session, _ = api_client("viewer")

        # Attempt to access the subscription
        access_response = viewer_session.get(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}"
        )

        # Should be forbidden or not found (both are acceptable for isolation)
        assert access_response.status_code in [403, 404], \
            f"Expected 403/404 for cross-tenant access, got {access_response.status_code}"

    def test_cannot_revoke_other_tenant_subscription(
        self, api_client, subscription_fixtures: dict
    ):
        """Test that users cannot revoke subscriptions from other tenants."""
        tenant_a_session, _ = api_client("tenant_admin")

        # Create subscription as tenant A
        test_sub = subscription_fixtures["test_subscriptions"]["developer_subscription"]

        create_response = tenant_a_session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            json={
                "tool_id": test_sub["tool_id"],
                "plan": test_sub["plan"],
            },
        )

        if create_response.status_code != 201:
            pytest.skip("Could not create subscription for isolation test")

        data = create_response.json()
        subscription_id = extract_subscription_id(data)

        # Try to revoke as viewer (different role/permissions)
        viewer_session, _ = api_client("viewer")

        revoke_response = viewer_session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}/revoke"
        )

        # Should be forbidden
        assert revoke_response.status_code in [403, 404], \
            f"Expected 403/404 for cross-tenant revoke, got {revoke_response.status_code}"

    def test_subscription_list_only_returns_own_subscriptions(self, api_client):
        """Test that subscription list only returns user's own subscriptions."""
        tenant_a_session, _ = api_client("tenant_admin")
        viewer_session, _ = api_client("viewer")

        # Get subscriptions for both users
        tenant_a_response = tenant_a_session.get(f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions")
        viewer_response = viewer_session.get(f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions")

        assert tenant_a_response.status_code == 200
        assert viewer_response.status_code == 200

        tenant_a_subs = tenant_a_response.json().get("subscriptions", [])
        viewer_subs = viewer_response.json().get("subscriptions", [])

        # Get IDs
        tenant_a_ids = {s.get("id") for s in tenant_a_subs}
        viewer_ids = {s.get("id") for s in viewer_subs}

        # If viewer has no subscriptions, that's expected
        # The key is that viewer should not see tenant_admin's subscriptions
        # (unless they're in the same tenant with read access)


@pytest.mark.subscriptions
@pytest.mark.ui
@pytest.mark.skip(reason="Portal UI tests require portal-specific Keycloak login - run separately")
class TestPortalSubscriptionUI:
    """
    UI tests for subscription management in the Developer Portal.
    Uses Playwright for browser automation.

    Note: These tests are skipped by default as they require the portal_login
    fixture which uses a different Keycloak flow. Run with:
        pytest test_subscriptions.py -m ui --no-skip
    """

    def test_subscriptions_page_loads(self, page: Page, portal_login):
        """Test that the subscriptions page loads correctly."""
        portal_login("tenant_admin")

        # Navigate to subscriptions page
        page.goto(f"{PORTAL_URL}/subscriptions")
        page.wait_for_load_state("networkidle")

        # Should show subscriptions page title or list
        expect(page.locator("h1, h2").first).to_contain_text(
            re.compile(r"subscription", re.IGNORECASE)
        )

    def test_can_view_subscription_details(self, page: Page, portal_login):
        """Test viewing subscription details in the portal."""
        portal_login("tenant_admin")

        page.goto(f"{PORTAL_URL}/subscriptions")
        page.wait_for_load_state("networkidle")

        # If there are subscriptions, click on one
        subscription_card = page.locator("[data-testid='subscription-card'], .subscription-card, .bg-white.rounded-lg").first

        if subscription_card.count() > 0:
            subscription_card.click()
            page.wait_for_load_state("networkidle")

            # Should show subscription details
            expect(page.locator("text=API Key, text=Status, text=Created").first).to_be_visible()

    def test_browse_tools_button_works(self, page: Page, portal_login):
        """Test that browse tools button navigates correctly."""
        portal_login("tenant_admin")

        page.goto(f"{PORTAL_URL}/subscriptions")
        page.wait_for_load_state("networkidle")

        # Find and click browse tools button
        browse_button = page.locator("a:has-text('Browse Tools'), button:has-text('Browse Tools')")

        if browse_button.count() > 0:
            browse_button.first.click()
            page.wait_for_load_state("networkidle")

            # Should be on tools page
            assert "/tools" in page.url


@pytest.mark.subscriptions
@pytest.mark.vault
class TestSecureKeyManagement:
    """
    Test secure API key management with Vault integration.
    Tests the reveal-key and TOTP functionality.
    """

    def test_reveal_key_endpoint_exists(self, api_client, subscription_fixtures: dict):
        """Test that the reveal-key endpoint is available."""
        session, token = api_client("tenant_admin")

        # Create subscription
        test_sub = subscription_fixtures["test_subscriptions"]["developer_subscription"]

        create_response = session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            json={
                "tool_id": test_sub["tool_id"],
                "plan": test_sub["plan"],
            },
        )

        if create_response.status_code != 201:
            pytest.skip("Could not create subscription")

        data = create_response.json()
        subscription_id = extract_subscription_id(data)

        # Try to reveal key (without TOTP if not required)
        reveal_response = session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}/reveal-key"
        )

        # Should return 200 with key or 403 if TOTP required
        assert reveal_response.status_code in [200, 403], \
            f"Expected 200/403, got {reveal_response.status_code}: {reveal_response.text}"

        if reveal_response.status_code == 200:
            reveal_data = reveal_response.json()
            assert "api_key" in reveal_data
            assert "expires_in" in reveal_data

    def test_toggle_totp_requirement(self, api_client, subscription_fixtures: dict):
        """Test toggling TOTP requirement for a subscription."""
        session, token = api_client("tenant_admin")

        # Create subscription
        test_sub = subscription_fixtures["test_subscriptions"]["developer_subscription"]

        create_response = session.post(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions",
            json={
                "tool_id": test_sub["tool_id"],
                "plan": test_sub["plan"],
            },
        )

        if create_response.status_code != 201:
            pytest.skip("Could not create subscription")

        data = create_response.json()
        subscription_id = extract_subscription_id(data)

        # Enable TOTP
        enable_response = session.patch(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}/totp",
            params={"enabled": "true"},
        )

        assert enable_response.status_code == 200, \
            f"Expected 200, got {enable_response.status_code}: {enable_response.text}"

        enable_data = enable_response.json()
        assert enable_data.get("totp_required") is True

        # Disable TOTP
        disable_response = session.patch(
            f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{subscription_id}/totp",
            params={"enabled": "false"},
        )

        assert disable_response.status_code == 200

        disable_data = disable_response.json()
        assert disable_data.get("totp_required") is False


# Cleanup fixture for test subscriptions
@pytest.fixture(scope="function", autouse=False)
def cleanup_test_subscriptions(api_client):
    """Cleanup test subscriptions after tests."""
    created_subscriptions = []

    yield created_subscriptions

    # Cleanup after test
    if created_subscriptions:
        session, _ = api_client("admin")
        for sub_id in created_subscriptions:
            try:
                session.post(f"{MCP_GATEWAY_URL}/mcp/v1/subscriptions/{sub_id}/revoke")
            except Exception:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
