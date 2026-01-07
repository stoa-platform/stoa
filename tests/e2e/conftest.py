"""
E2E Test Fixtures for STOA Platform (CAB-238)
Keycloak authentication fixtures for console.stoa.cab-i.com
"""

import json
import os
from pathlib import Path
from typing import Generator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

# Configuration
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://auth.stoa.cab-i.com")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "stoa")
CONSOLE_URL = os.getenv("CONSOLE_URL", "https://console.stoa.cab-i.com")
KEYCLOAK_AUTH_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect"


@pytest.fixture(scope="session")
def fixtures_path() -> Path:
    """Return path to fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def users_data(fixtures_path: Path) -> dict:
    """Load test users from fixtures/users.json."""
    users_file = fixtures_path / "users.json"
    with open(users_file) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def playwright_instance() -> Generator[Playwright, None, None]:
    """Create Playwright instance for the test session."""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Generator[Browser, None, None]:
    """Launch browser for the test session."""
    browser = playwright_instance.chromium.launch(
        headless=os.getenv("HEADLESS", "true").lower() == "true",
        slow_mo=int(os.getenv("SLOW_MO", "0")),
    )
    yield browser
    browser.close()


@pytest.fixture(scope="function")
def context(browser: Browser) -> Generator[BrowserContext, None, None]:
    """Create a new browser context for each test."""
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
    )
    yield context
    context.close()


@pytest.fixture(scope="function")
def page(context: BrowserContext) -> Generator[Page, None, None]:
    """Create a new page for each test."""
    page = context.new_page()
    yield page
    page.close()


@pytest.fixture(scope="function")
def keycloak_login(page: Page, users_data: dict):
    """
    Factory fixture to perform Keycloak login.

    Usage:
        def test_something(keycloak_login):
            keycloak_login("admin")  # Login as admin user
    """
    def _login(user_role: str) -> dict:
        """
        Perform Keycloak login for the specified user role.

        Args:
            user_role: Key from users.json (e.g., "admin", "tenant_admin", "viewer")

        Returns:
            dict with user info and tokens
        """
        user = users_data["users"].get(user_role)
        if not user:
            raise ValueError(f"Unknown user role: {user_role}")

        # Navigate to console (will redirect to Keycloak)
        page.goto(CONSOLE_URL)

        # Wait for Keycloak login page
        page.wait_for_url(f"{KEYCLOAK_URL}/**", timeout=10000)

        # Fill login form
        page.locator("#username").fill(user["username"])
        page.locator("#password").fill(user["password"])
        page.locator("#kc-login").click()

        # Wait for redirect back to console
        page.wait_for_url(f"{CONSOLE_URL}/**", timeout=15000)

        return {
            "username": user["username"],
            "role": user_role,
            "scopes": user.get("scopes", []),
        }

    return _login


@pytest.fixture(scope="function")
def authenticated_page(page: Page, keycloak_login, users_data: dict) -> Page:
    """
    Provide a page already authenticated as the default admin user.
    """
    keycloak_login("admin")
    return page


@pytest.fixture(scope="session")
def keycloak_config() -> dict:
    """Return Keycloak configuration."""
    return {
        "url": KEYCLOAK_URL,
        "realm": KEYCLOAK_REALM,
        "auth_url": KEYCLOAK_AUTH_URL,
        "console_url": CONSOLE_URL,
    }


def get_access_token_from_storage(page: Page) -> str | None:
    """
    Extract access token from browser storage after login.

    Args:
        page: Playwright page after successful login

    Returns:
        Access token string or None if not found
    """
    # Try localStorage first (common for Keycloak-js)
    token = page.evaluate("""
        () => {
            const keys = Object.keys(localStorage);
            for (const key of keys) {
                if (key.includes('token') || key.includes('kc-')) {
                    try {
                        const data = JSON.parse(localStorage.getItem(key));
                        if (data && data.access_token) {
                            return data.access_token;
                        }
                    } catch {}
                }
            }
            return null;
        }
    """)

    if token:
        return token

    # Try sessionStorage
    token = page.evaluate("""
        () => {
            const keys = Object.keys(sessionStorage);
            for (const key of keys) {
                if (key.includes('token') || key.includes('kc-')) {
                    try {
                        const data = JSON.parse(sessionStorage.getItem(key));
                        if (data && data.access_token) {
                            return data.access_token;
                        }
                    } catch {}
                }
            }
            return null;
        }
    """)

    return token


@pytest.fixture
def get_token(page: Page):
    """Fixture to extract token after login."""
    return lambda: get_access_token_from_storage(page)
