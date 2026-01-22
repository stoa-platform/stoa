"""
Pytest configuration and fixtures for Control Plane API tests.

CAB-839: Enhanced fixtures for router testing with 80% coverage target.
"""

# IMPORTANT: Fix sys.path to ensure control-plane-api's src is found first
# This is needed because mcp-gateway is installed as editable and adds its path
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).parent
_PROJECT_ROOT = _THIS_DIR.parent

# Insert at the beginning of sys.path
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Remove any cached 'src' modules to force reload from the correct path
_modules_to_remove = [key for key in sys.modules if key == 'src' or key.startswith('src.')]
for mod in _modules_to_remove:
    del sys.modules[mod]

# ============== Mock External Services Before App Import ==============
# This prevents connection attempts to Kafka, GitLab, Keycloak, etc. during testing
from unittest.mock import AsyncMock, MagicMock, patch
import os

# Set environment variables to disable workers before any imports
os.environ["ENABLE_DEPLOYMENT_WORKER"] = "false"
os.environ["ENABLE_SNAPSHOT_CONSUMER"] = "false"

# Create mock services that will be patched into src.main
_mock_kafka_service = MagicMock()
_mock_kafka_service.connect = AsyncMock()
_mock_kafka_service.disconnect = AsyncMock()
_mock_kafka_service.publish = AsyncMock()
_mock_kafka_service.emit_audit_event = AsyncMock()

_mock_git_service = MagicMock()
_mock_git_service.connect = AsyncMock()
_mock_git_service.disconnect = AsyncMock()
_mock_git_service._project = None
_mock_git_service.get_tenant = AsyncMock(return_value=None)
_mock_git_service.list_apis = AsyncMock(return_value=[])

_mock_awx_service = MagicMock()
_mock_awx_service.connect = AsyncMock()
_mock_awx_service.disconnect = AsyncMock()

_mock_keycloak_service = MagicMock()
_mock_keycloak_service.connect = AsyncMock()
_mock_keycloak_service.disconnect = AsyncMock()

_mock_gateway_service = MagicMock()
_mock_gateway_service.connect = AsyncMock()
_mock_gateway_service.disconnect = AsyncMock()

_mock_argocd_service = MagicMock()
_mock_argocd_service.connect = AsyncMock()
_mock_argocd_service.disconnect = AsyncMock()

# Patch services in the main module where they're imported and used
# These patches target 'src.main.<service>' because main.py does:
#   from .services import kafka_service, git_service, ...
patch('src.main.kafka_service', _mock_kafka_service).start()
patch('src.main.git_service', _mock_git_service).start()
patch('src.main.awx_service', _mock_awx_service).start()
patch('src.main.keycloak_service', _mock_keycloak_service).start()
patch('src.main.gateway_service', _mock_gateway_service).start()
patch('src.main.argocd_service', _mock_argocd_service).start()

# Also patch at service module level for routers that import directly
patch('src.services.kafka_service.kafka_service', _mock_kafka_service).start()
patch('src.services.git_service.git_service', _mock_git_service).start()
patch('src.services.keycloak_service.keycloak_service', _mock_keycloak_service).start()

# Patch OpenSearch setup
patch('src.main.setup_opensearch', AsyncMock()).start()

# Patch error snapshots
patch('src.main.connect_error_snapshots', AsyncMock(return_value=None)).start()
patch('src.main.add_error_snapshot_middleware', MagicMock()).start()

import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel


# ============== Mock User Model ==============
# Define User locally to avoid import conflicts with mcp-gateway
class User(BaseModel):
    """Mock User model matching src.auth.dependencies.User"""
    id: str
    email: str
    username: str
    roles: List[str]
    tenant_id: Optional[str] = None


# ============== Mock SubscriptionStatus Enum ==============
class SubscriptionStatus(str, Enum):
    """Mock SubscriptionStatus for fixtures - mirrors src.models.subscription.SubscriptionStatus"""
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"


# ============== Session & Backend Fixtures ==============

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio backend for anyio."""
    return "asyncio"


# ============== User Fixtures (RBAC Testing) ==============

@pytest.fixture
def mock_user_cpi_admin():
    """Mock CPI Admin user with full platform access."""
    return User(
        id="admin-user-id",
        email="admin@stoa.cab-i.com",
        username="cpi-admin",
        roles=["cpi-admin"],
        tenant_id=None,
    )


@pytest.fixture
def mock_user_tenant_admin():
    """Mock Tenant Admin user for tenant 'acme'."""
    return User(
        id="tenant-admin-user-id",
        email="admin@acme.com",
        username="tenant-admin",
        roles=["tenant-admin"],
        tenant_id="acme",
    )


@pytest.fixture
def mock_user_viewer():
    """Mock Viewer user with read-only access."""
    return User(
        id="viewer-user-id",
        email="viewer@acme.com",
        username="viewer",
        roles=["viewer"],
        tenant_id="acme",
    )


@pytest.fixture
def mock_user_other_tenant():
    """Mock user from a different tenant (for isolation tests)."""
    return User(
        id="other-tenant-user-id",
        email="user@other-tenant.com",
        username="other-user",
        roles=["tenant-admin"],
        tenant_id="other-tenant",
    )


@pytest.fixture
def mock_user_no_tenant():
    """Mock user without tenant assignment."""
    return User(
        id="no-tenant-user-id",
        email="orphan@example.com",
        username="orphan-user",
        roles=["viewer"],
        tenant_id=None,
    )


# ============== Legacy Token Fixtures ==============

@pytest.fixture
def mock_keycloak_token() -> dict[str, Any]:
    """Mock Keycloak token payload."""
    return {
        "sub": "test-user-id",
        "email": "test@stoa.cab-i.com",
        "preferred_username": "test-user",
        "realm_access": {"roles": ["cpi-admin"]},
        "resource_access": {},
        "scope": "openid profile email stoa:admin stoa:write stoa:read",
        "tenant_id": "test-tenant",
    }


@pytest.fixture
def auth_headers(mock_keycloak_token: dict[str, Any]) -> dict[str, str]:
    """Generate authorization headers with mock token."""
    return {"Authorization": "Bearer mock-token-for-testing"}


# ============== Database Mock Fixtures ==============

@pytest.fixture
def mock_db_session():
    """Create a mock AsyncSession for database operations."""
    from sqlalchemy.ext.asyncio import AsyncSession
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.close = AsyncMock()
    session.delete = AsyncMock()
    session.add = MagicMock()
    return session


# ============== Sample Data Fixtures ==============

@pytest.fixture
def sample_subscription_id():
    """Generate a consistent subscription ID for tests."""
    return uuid4()


@pytest.fixture
def sample_subscription_data(sample_subscription_id):
    """Sample subscription data for testing."""
    return {
        "id": sample_subscription_id,
        "application_id": "app-test-123",
        "application_name": "Test Application",
        "subscriber_id": "tenant-admin-user-id",
        "subscriber_email": "admin@acme.com",
        "api_id": "api-weather-456",
        "api_name": "Weather API",
        "api_version": "1.0",
        "tenant_id": "acme",
        "plan_id": "basic",
        "plan_name": "Basic Plan",
        "api_key_hash": "hashed_key_test_123",
        "api_key_prefix": "stoa_sk_tes",
        "status": SubscriptionStatus.PENDING,
        "status_reason": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "approved_at": None,
        "expires_at": None,
        "revoked_at": None,
        "approved_by": None,
        "revoked_by": None,
        "previous_api_key_hash": None,
        "previous_key_expires_at": None,
        "last_rotated_at": None,
        "rotation_count": 0,
    }


@pytest.fixture
def sample_contract_id():
    """Generate a consistent contract ID for tests."""
    return uuid4()


@pytest.fixture
def sample_contract_data(sample_contract_id):
    """Sample contract data for testing."""
    return {
        "id": sample_contract_id,
        "tenant_id": "acme",
        "name": "payment-service",
        "display_name": "Payment Service API",
        "description": "API for processing payments",
        "version": "1.0.0",
        "status": "draft",
        "openapi_spec_url": None,
        "schema_hash": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "created_by": "tenant-admin-user-id",
    }


@pytest.fixture
def sample_tenant_data():
    """Sample tenant data for GitOps responses."""
    return {
        "id": "acme",
        "name": "acme",
        "display_name": "ACME Corporation",
        "description": "Test tenant for unit tests",
        "owner_email": "admin@acme.com",
        "status": "active",
        "api_count": 2,
        "application_count": 1,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }


# ============== App & Client Fixtures ==============

@pytest.fixture
def app():
    """Get the FastAPI application instance."""
    from src.main import app
    return app


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    """Create a test client for synchronous tests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ============== App with Dependency Overrides ==============

@pytest.fixture
def app_with_tenant_admin(app, mock_user_tenant_admin, mock_db_session):
    """App with tenant-admin auth and db overrides."""
    from src.auth.dependencies import get_current_user
    from src.database import get_db

    async def override_get_current_user():
        return mock_user_tenant_admin

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
def app_with_cpi_admin(app, mock_user_cpi_admin, mock_db_session):
    """App with cpi-admin auth and db overrides."""
    from src.auth.dependencies import get_current_user
    from src.database import get_db

    async def override_get_current_user():
        return mock_user_cpi_admin

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
def app_with_other_tenant(app, mock_user_other_tenant, mock_db_session):
    """App with other-tenant user auth for isolation tests."""
    from src.auth.dependencies import get_current_user
    from src.database import get_db

    async def override_get_current_user():
        return mock_user_other_tenant

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
def app_with_no_tenant_user(app, mock_user_no_tenant, mock_db_session):
    """App with user that has no tenant assignment."""
    from src.auth.dependencies import get_current_user
    from src.database import get_db

    async def override_get_current_user():
        return mock_user_no_tenant

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
def client_as_tenant_admin(app_with_tenant_admin) -> Generator[TestClient, None, None]:
    """Test client authenticated as tenant-admin."""
    with TestClient(app_with_tenant_admin) as c:
        yield c


@pytest.fixture
def client_as_cpi_admin(app_with_cpi_admin) -> Generator[TestClient, None, None]:
    """Test client authenticated as cpi-admin."""
    with TestClient(app_with_cpi_admin) as c:
        yield c


@pytest.fixture
def client_as_other_tenant(app_with_other_tenant) -> Generator[TestClient, None, None]:
    """Test client authenticated as user from different tenant."""
    with TestClient(app_with_other_tenant) as c:
        yield c


@pytest.fixture
def client_as_no_tenant_user(app_with_no_tenant_user) -> Generator[TestClient, None, None]:
    """Test client authenticated as user without tenant."""
    with TestClient(app_with_no_tenant_user) as c:
        yield c


# ============== Autouse Reset Fixture ==============

@pytest.fixture(autouse=True)
def reset_app_overrides(app):
    """Ensure dependency overrides are cleared after each test."""
    yield
    app.dependency_overrides.clear()
