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
from sqlalchemy import text
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


@pytest.fixture
async def integration_db():
    """Provide a real AsyncSession with auto-created tables, rolls back after each test.

    Function-scoped to avoid event loop conflicts between session-scoped async
    fixtures and function-scoped tests (pytest-asyncio >= 0.23).
    create_all is idempotent (IF NOT EXISTS), so the per-test overhead is minimal.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping integration tests")

    engine = create_async_engine(url, echo=False)

    # Create schema + tables (idempotent — safe to call per test)
    async with engine.begin() as conn:
        # Some models (Invite, ProspectEvent) use schema="stoa"
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS stoa"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        async with session.begin():
            yield session
            # Rollback ensures test isolation — no data leaks between tests
            await session.rollback()

    await engine.dispose()
