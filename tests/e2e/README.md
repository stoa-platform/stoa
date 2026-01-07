# E2E Tests - STOA Platform (CAB-238)

End-to-end tests for the STOA Platform Console using Playwright and pytest.

## Structure

```
tests/e2e/
├── conftest.py           # Pytest fixtures (Keycloak auth)
├── pytest.ini            # Pytest configuration
├── fixtures/
│   └── users.json        # Test user credentials
├── scenarios/
│   └── test_auth_flow.py # Authentication flow tests
└── README.md
```

## Prerequisites

```bash
pip install pytest playwright pytest-playwright pytest-asyncio
playwright install chromium
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KEYCLOAK_URL` | `https://auth.stoa.cab-i.com` | Keycloak server URL |
| `KEYCLOAK_REALM` | `stoa` | Keycloak realm name |
| `CONSOLE_URL` | `https://console.stoa.cab-i.com` | Console application URL |
| `HEADLESS` | `true` | Run browser in headless mode |
| `SLOW_MO` | `0` | Slow down operations (ms) |

### Test User Credentials

Set credentials via environment variables:

```bash
export CPI_ADMIN_PASSWORD="your-admin-password"
export TENANT_ADMIN_PASSWORD="your-tenant-admin-password"
export DEVOPS_PASSWORD="your-devops-password"
export VIEWER_PASSWORD="your-viewer-password"
```

Or create a `.env` file in the `tests/e2e/` directory.

## Running Tests

### All tests

```bash
cd tests/e2e
pytest
```

### Specific markers

```bash
# Auth tests only
pytest -m auth

# Smoke tests only
pytest -m smoke

# Exclude slow tests
pytest -m "not slow"
```

### Debug mode (visible browser)

```bash
HEADLESS=false SLOW_MO=500 pytest -v
```

### Single test

```bash
pytest scenarios/test_auth_flow.py::TestAuthenticationFlow::test_admin_login_success -v
```

## Fixtures

### `keycloak_login`

Factory fixture to perform Keycloak login:

```python
def test_example(keycloak_login):
    result = keycloak_login("admin")  # or "tenant_admin", "devops", "viewer"
    assert result["role"] == "admin"
```

### `authenticated_page`

Page already authenticated as admin:

```python
def test_example(authenticated_page):
    authenticated_page.goto("/dashboard")
```

### `get_token`

Extract access token after login:

```python
def test_example(keycloak_login, get_token):
    keycloak_login("admin")
    token = get_token()
    assert token is not None
```

## Test Roles

| Role | Scopes | Description |
|------|--------|-------------|
| `admin` | `stoa:admin`, `stoa:write`, `stoa:read` | Full platform access |
| `tenant_admin` | `stoa:write`, `stoa:read` | Manage own tenant |
| `devops` | `stoa:write`, `stoa:read` | Deploy and promote APIs |
| `viewer` | `stoa:read` | Read-only access |

## CI/CD Integration

```yaml
# GitLab CI example
e2e-tests:
  stage: test
  image: mcr.microsoft.com/playwright:v1.40.0-jammy
  variables:
    HEADLESS: "true"
    KEYCLOAK_URL: "https://auth.stoa.cab-i.com"
    CONSOLE_URL: "https://console.stoa.cab-i.com"
  script:
    - pip install pytest playwright pytest-playwright
    - cd tests/e2e && pytest --junitxml=report.xml
  artifacts:
    reports:
      junit: tests/e2e/report.xml
```
