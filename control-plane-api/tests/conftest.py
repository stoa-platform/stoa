"""
Pytest configuration and fixtures for Control Plane API tests.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient


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
    # In real tests, you would create a proper JWT
    return {"Authorization": "Bearer mock-token-for-testing"}


# Import app lazily to avoid initialization issues
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
