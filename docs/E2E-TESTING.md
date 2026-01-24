# E2E Testing Guide - STOA Platform (CAB-238)

This document describes the end-to-end testing framework for the STOA Platform Console.

## Overview

The E2E test suite validates critical user flows including authentication, authorization, and core console functionality using **Playwright** and **pytest**.

### Stack

| Component | Technology |
|-----------|------------|
| Test Framework | pytest |
| Browser Automation | Playwright |
| Authentication | Keycloak (OIDC) |
| Target Application | console.gostoa.dev |

## Directory Structure

```
tests/e2e/
├── conftest.py              # Shared fixtures and configuration
├── pytest.ini               # pytest settings and markers
├── fixtures/
│   └── users.json           # Test user credentials and roles
├── scenarios/
│   └── test_auth_flow.py    # Authentication flow tests
├── scripts/
│   └── setup_test_users.sh  # Script to create Keycloak users & AWS secrets
└── README.md                # Quick reference guide
```

## Installation

### Prerequisites

- Python 3.11+
- Access to Keycloak (auth.gostoa.dev)
- Access to Console (console.gostoa.dev)

### Setup

```bash
# Install dependencies
pip install pytest playwright pytest-playwright pytest-asyncio boto3

# Install browser binaries
playwright install chromium

# Optional: Install all browsers
playwright install
```

### Setup Test Users (First Time Only)

Test user credentials are stored in AWS Secrets Manager. To create the test users in Keycloak and store their credentials:

```bash
# Set Keycloak admin credentials
export KEYCLOAK_ADMIN_USER=admin
export KEYCLOAK_ADMIN_PASSWORD=<keycloak-admin-password>

# Run setup script
cd tests/e2e
./scripts/setup_test_users.sh
```

This creates 4 test users in Keycloak and stores their credentials in AWS Secrets Manager (`stoa/e2e-test-credentials`).

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KEYCLOAK_URL` | `https://auth.gostoa.dev` | Keycloak server URL |
| `KEYCLOAK_REALM` | `stoa` | Keycloak realm |
| `CONSOLE_URL` | `https://console.gostoa.dev` | Console application URL |
| `HEADLESS` | `true` | Run browser headlessly |
| `SLOW_MO` | `0` | Milliseconds to slow down actions |
| `AWS_REGION` | `eu-west-1` | AWS region for Secrets Manager |
| `E2E_CREDENTIALS_SECRET` | `stoa/e2e-test-credentials` | AWS secret name |

### Test User Credentials

Credentials are automatically fetched from AWS Secrets Manager. The fixture supports three sources (in order of priority):

1. **AWS Secrets Manager** (recommended for CI/CD)
   - Secret: `stoa/e2e-test-credentials`
   - Requires `boto3` and AWS credentials

2. **Environment variables** (for local development without AWS)
   ```bash
   export E2E_ADMIN_PASSWORD="password"
   export E2E_TENANT_ADMIN_PASSWORD="password"
   export E2E_DEVOPS_PASSWORD="password"
   export E2E_VIEWER_PASSWORD="password"
   ```

3. **Local fixtures/users.json** (fallback with placeholders)

## Test Users and Roles

The test suite covers all four RBAC roles:

| Role | Username | Scopes | Access Level |
|------|----------|--------|--------------|
| `admin` | e2e-admin | `stoa:admin`, `stoa:write`, `stoa:read` | Full platform |
| `tenant_admin` | e2e-tenant-admin | `stoa:write`, `stoa:read` | Own tenant |
| `devops` | e2e-devops | `stoa:write`, `stoa:read` | Deploy/promote |
| `viewer` | e2e-viewer | `stoa:read` | Read-only |

## Running Tests

### Basic Commands

```bash
cd tests/e2e

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest scenarios/test_auth_flow.py

# Run specific test class
pytest scenarios/test_auth_flow.py::TestAuthenticationFlow

# Run specific test
pytest scenarios/test_auth_flow.py::TestAuthenticationFlow::test_admin_login_success
```

### Using Markers

```bash
# Run only auth tests
pytest -m auth

# Run smoke tests (quick validation)
pytest -m smoke

# Skip slow tests
pytest -m "not slow"

# Combine markers
pytest -m "auth and smoke"
```

### Debug Mode

```bash
# Visible browser with slow motion
HEADLESS=false SLOW_MO=500 pytest -v

# Stop on first failure
pytest -x

# Show print statements
pytest -s
```

## Available Fixtures

### `keycloak_login`

Factory fixture to authenticate as any test user:

```python
def test_admin_access(keycloak_login):
    result = keycloak_login("admin")
    assert result["role"] == "admin"
    assert "stoa:admin" in result["scopes"]
```

### `authenticated_page`

Pre-authenticated page (as admin):

```python
def test_dashboard(authenticated_page):
    authenticated_page.goto("/dashboard")
    # Already logged in as admin
```

### `get_token`

Extract JWT access token after login:

```python
def test_token_present(keycloak_login, get_token):
    keycloak_login("admin")
    token = get_token()
    assert token is not None
```

### `keycloak_config`

Access Keycloak configuration:

```python
def test_redirect(page, keycloak_config):
    page.goto(keycloak_config["console_url"])
    # Verify redirect to keycloak_config["url"]
```

## Test Scenarios

### Authentication Flow Tests (`test_auth_flow.py`)

| Test | Description | Marker |
|------|-------------|--------|
| `test_redirect_to_keycloak_when_unauthenticated` | Unauthenticated users redirected to Keycloak | `auth`, `smoke` |
| `test_admin_login_success` | Admin can login and receives valid token | `auth`, `smoke` |
| `test_tenant_admin_login_success` | Tenant admin login flow | `auth`, `smoke` |
| `test_viewer_login_success` | Viewer login with limited scopes | `auth`, `smoke` |
| `test_invalid_credentials_shows_error` | Invalid credentials show error | `auth`, `smoke` |
| `test_token_contains_required_claims` | JWT has required claims (sub, exp, iat, iss) | `auth`, `smoke` |
| `test_logout_clears_session` | Logout clears tokens/session | `auth` |
| `test_accessing_protected_route_after_logout` | Protected routes redirect after logout | `auth` |
| `test_token_refresh_before_expiry` | Token refresh mechanism works | `auth`, `slow` |

## Writing New Tests

### Basic Test Structure

```python
import pytest
from playwright.sync_api import Page, expect

@pytest.mark.auth
class TestMyFeature:
    """Test suite for my feature."""

    def test_something(self, page: Page, keycloak_login):
        # 1. Login
        keycloak_login("admin")

        # 2. Navigate
        page.goto("https://console.gostoa.dev/my-feature")

        # 3. Interact
        page.locator("#my-button").click()

        # 4. Assert
        expect(page.locator(".result")).to_contain_text("Success")
```

### Best Practices

1. **Use appropriate markers** - Add `@pytest.mark.auth`, `@pytest.mark.smoke`, or `@pytest.mark.slow`
2. **Login with correct role** - Use the role with minimum required permissions
3. **Use Playwright's expect** - Prefer `expect(locator).to_be_visible()` over manual waits
4. **Clean up state** - Each test gets a fresh browser context via fixtures

## CI/CD Integration

### GitLab CI

```yaml
e2e-tests:
  stage: test
  image: mcr.microsoft.com/playwright:v1.40.0-jammy
  variables:
    HEADLESS: "true"
    KEYCLOAK_URL: "https://auth.gostoa.dev"
    CONSOLE_URL: "https://console.gostoa.dev"
  before_script:
    - pip install pytest playwright pytest-playwright
  script:
    - cd tests/e2e
    - pytest --junitxml=report.xml -m "not slow"
  artifacts:
    when: always
    reports:
      junit: tests/e2e/report.xml
    paths:
      - tests/e2e/screenshots/
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == "main"
```

### GitHub Actions

```yaml
e2e-tests:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        pip install pytest playwright pytest-playwright
        playwright install chromium --with-deps
    - name: Run E2E tests
      env:
        HEADLESS: "true"
        CPI_ADMIN_PASSWORD: ${{ secrets.CPI_ADMIN_PASSWORD }}
      run: |
        cd tests/e2e
        pytest --junitxml=report.xml -m smoke
    - uses: actions/upload-artifact@v4
      if: always()
      with:
        name: test-results
        path: tests/e2e/report.xml
```

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `TimeoutError` on login | Check Keycloak URL and network access |
| `Element not found` | Update selectors, use `HEADLESS=false` to debug |
| Tests pass locally but fail in CI | Ensure CI has network access to auth/console URLs |
| Token extraction fails | Check browser storage keys in `conftest.py` |

### Debug Tips

```bash
# Run with visible browser
HEADLESS=false pytest -v -x

# Capture screenshots on failure (add to conftest.py)
@pytest.fixture(autouse=True)
def screenshot_on_failure(request, page):
    yield
    if request.node.rep_call.failed:
        page.screenshot(path=f"screenshots/{request.node.name}.png")

# Enable Playwright debug logs
DEBUG=pw:api pytest -v
```

## Related Documentation

- [ARCHITECTURE-PRESENTATION.md](./ARCHITECTURE-PRESENTATION.md) - Platform architecture
- [Control Plane UI](../control-plane-ui/README.md) - Console application
- [Keycloak Setup](./runbooks/) - Authentication configuration
