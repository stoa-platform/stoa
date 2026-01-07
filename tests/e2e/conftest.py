"""
E2E Test Fixtures for STOA Platform (CAB-238)
Keycloak authentication fixtures for console.stoa.cab-i.com
"""

import json
import os
import re
from pathlib import Path
from typing import Generator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

# Configuration
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://auth.stoa.cab-i.com")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "stoa")
CONSOLE_URL = os.getenv("CONSOLE_URL", "https://console.stoa.cab-i.com")
KEYCLOAK_AUTH_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect"
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")
E2E_CREDENTIALS_SECRET = os.getenv("E2E_CREDENTIALS_SECRET", "stoa/e2e-test-credentials")


def get_credentials_from_aws() -> dict | None:
    """
    Fetch E2E test credentials from AWS Secrets Manager.

    Returns:
        dict with user credentials or None if not available
    """
    try:
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client("secretsmanager", region_name=AWS_REGION)
        response = client.get_secret_value(SecretId=E2E_CREDENTIALS_SECRET)
        return json.loads(response["SecretString"])
    except ImportError:
        print("boto3 not installed, falling back to local credentials")
        return None
    except ClientError as e:
        print(f"Failed to fetch credentials from AWS: {e}")
        return None
    except Exception as e:
        print(f"Error fetching AWS credentials: {e}")
        return None


def load_users_data(fixtures_path: Path) -> dict:
    """
    Load test users, preferring AWS Secrets Manager over local file.

    Priority:
    1. AWS Secrets Manager (stoa/e2e-test-credentials)
    2. Environment variables (E2E_ADMIN_PASSWORD, etc.)
    3. Local fixtures/users.json (for development)
    """
    # Try AWS Secrets Manager first
    aws_credentials = get_credentials_from_aws()

    if aws_credentials:
        # Build users dict from AWS credentials
        users = {
            "users": {
                "admin": {
                    "username": aws_credentials["admin"]["username"],
                    "password": aws_credentials["admin"]["password"],
                    "scopes": ["stoa:admin", "stoa:write", "stoa:read"],
                    "role": "cpi-admin",
                },
                "tenant_admin": {
                    "username": aws_credentials["tenant_admin"]["username"],
                    "password": aws_credentials["tenant_admin"]["password"],
                    "scopes": ["stoa:write", "stoa:read"],
                    "role": "tenant-admin",
                },
                "devops": {
                    "username": aws_credentials["devops"]["username"],
                    "password": aws_credentials["devops"]["password"],
                    "scopes": ["stoa:write", "stoa:read"],
                    "role": "devops",
                },
                "viewer": {
                    "username": aws_credentials["viewer"]["username"],
                    "password": aws_credentials["viewer"]["password"],
                    "scopes": ["stoa:read"],
                    "role": "viewer",
                },
            }
        }
        print("Loaded credentials from AWS Secrets Manager")
        return users

    # Fallback to local file with environment variable substitution
    users_file = fixtures_path / "users.json"
    with open(users_file) as f:
        users = json.load(f)

    # Substitute environment variables in passwords
    env_mapping = {
        "admin": "E2E_ADMIN_PASSWORD",
        "tenant_admin": "E2E_TENANT_ADMIN_PASSWORD",
        "devops": "E2E_DEVOPS_PASSWORD",
        "viewer": "E2E_VIEWER_PASSWORD",
    }

    for role, env_var in env_mapping.items():
        if role in users.get("users", {}):
            env_password = os.getenv(env_var)
            if env_password:
                users["users"][role]["password"] = env_password

    print("Loaded credentials from local file/environment")
    return users


@pytest.fixture(scope="session")
def fixtures_path() -> Path:
    """Return path to fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def users_data(fixtures_path: Path) -> dict:
    """Load test users from AWS Secrets Manager or fixtures/users.json."""
    return load_users_data(fixtures_path)


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

        # Navigate to console (will redirect to /login page)
        page.goto(CONSOLE_URL)

        # Wait for login page or Keycloak form
        # Console has a "Login with Keycloak" button on /login page
        page.wait_for_selector(
            "#username, button:has-text('Login with Keycloak'), button:has-text('Login')",
            timeout=15000
        )

        # If we're on console /login page, click the login button to redirect to Keycloak
        login_button = page.locator("button:has-text('Login with Keycloak'), button:has-text('Login')")
        if login_button.count() > 0 and "/login" in page.url:
            login_button.first.click()
            page.wait_for_selector("#username", timeout=10000)

        # Fill login form
        page.locator("#username").fill(user["username"])
        page.locator("#password").fill(user["password"])
        page.locator("#kc-login").click()

        # Wait for redirect back to console (not on login or auth pages)
        page.wait_for_function(
            f"""() => {{
                const url = window.location.href;
                return url.startsWith('{CONSOLE_URL}') &&
                       !url.includes('/login') &&
                       !url.includes('auth.stoa.cab-i.com');
            }}""",
            timeout=15000
        )

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

    Supports multiple OIDC libraries:
    - react-oidc-context / oidc-client-ts (uses oidc.user:* keys)
    - keycloak-js (uses kc-* keys)

    Args:
        page: Playwright page after successful login

    Returns:
        Access token string or None if not found
    """
    token = page.evaluate("""
        () => {
            // Helper to search in a storage object
            function searchStorage(storage) {
                const keys = Object.keys(storage);
                for (const key of keys) {
                    const value = storage.getItem(key);
                    if (!value) continue;

                    // oidc-client-ts format: oidc.user:https://auth.example.com:client_id
                    if (key.startsWith('oidc.user:')) {
                        try {
                            const data = JSON.parse(value);
                            if (data && data.access_token) {
                                return data.access_token;
                            }
                        } catch {}
                    }

                    // Generic search for token/kc patterns
                    if (key.includes('token') || key.includes('kc-') || key.includes('oidc')) {
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

            // Try sessionStorage first (default for oidc-client-ts)
            let token = searchStorage(sessionStorage);
            if (token) return token;

            // Try localStorage
            token = searchStorage(localStorage);
            return token;
        }
    """)

    return token


@pytest.fixture
def get_token(page: Page):
    """Fixture to extract token after login."""
    return lambda: get_access_token_from_storage(page)
