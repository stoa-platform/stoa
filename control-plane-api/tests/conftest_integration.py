"""
Integration test fixtures — real PostgreSQL database.

Requires DATABASE_URL environment variable pointing to a PostgreSQL instance.
Used by tests marked with @pytest.mark.integration.

Usage:
    DATABASE_URL=postgresql+asyncpg://stoa_test:stoa_test@localhost:5432/stoa_test \
      pytest -m integration -v
"""
import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import Base

# Import ALL models so Base.metadata knows about all tables
from src.models.catalog import APICatalog, CatalogSyncStatus, MCPToolsCatalog  # noqa: F401
from src.models.contract import Contract, ProtocolBinding  # noqa: F401
from src.models.external_mcp_server import ExternalMCPServer, ExternalMCPServerTool  # noqa: F401
from src.models.gateway_deployment import GatewayDeployment  # noqa: F401
from src.models.gateway_instance import GatewayInstance  # noqa: F401
from src.models.gateway_policy import GatewayPolicy, GatewayPolicyBinding  # noqa: F401
from src.models.mcp_subscription import MCPServer, MCPServerSubscription, MCPServerTool, MCPToolAccess  # noqa: F401
from src.models.subscription import Subscription  # noqa: F401
from src.models.tenant import Tenant  # noqa: F401


@pytest.fixture(scope="session")
def integration_engine():
    """Create async engine for integration tests (session-scoped)."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping integration tests")
    engine = create_async_engine(url, echo=False)
    yield engine


@pytest.fixture(scope="session")
async def _create_tables(integration_engine):
    """Create all tables before integration tests, drop after."""
    async with integration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with integration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def integration_db(_create_tables, integration_engine):
    """Provide a real AsyncSession that rolls back after each test."""
    session_factory = async_sessionmaker(
        integration_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        async with session.begin():
            yield session
            # Rollback ensures test isolation — no data leaks between tests
            await session.rollback()
