"""Demo-test fixtures — in-memory aiosqlite session with a minimal schema.

We cannot reuse the full ``integration_db`` fixture here (it needs a real
PostgreSQL and auto-skips without ``DATABASE_URL``). The reset service is
driver-agnostic, so we stand up a tiny SQLite schema that mirrors just the
columns it touches. Boundary under test = the real SQLAlchemy engine, the real
text() SQL — we do NOT AsyncMock the session (per control-plane-api CLAUDE.md).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DEMO_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        provisioning_status TEXT NOT NULL DEFAULT 'ready',
        settings TEXT NOT NULL DEFAULT '{}',
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_catalog (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        api_id TEXT NOT NULL,
        api_name TEXT NOT NULL,
        version TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        category TEXT,
        tags TEXT NOT NULL DEFAULT '[]',
        portal_published INTEGER NOT NULL DEFAULT 0,
        audience TEXT NOT NULL DEFAULT 'public',
        metadata TEXT NOT NULL DEFAULT '{}',
        target_gateways TEXT NOT NULL DEFAULT '[]',
        synced_at TIMESTAMP,
        deleted_at TIMESTAMP
    )
    """,
)


@pytest_asyncio.fixture
async def demo_session() -> AsyncIterator[AsyncSession]:
    """Provide an in-memory aiosqlite AsyncSession with the demo schema."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        for ddl in _DEMO_SCHEMA_SQL:
            await conn.execute(text(ddl))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def foreign_tenant_rows() -> list[dict[str, str]]:
    """Canary rows used to assert reset never touches non-demo tenants."""
    return [
        {"id": "prod-acme", "name": "Production Acme", "api_id": "billing-api-v1"},
        {"id": "oasis", "name": "OASIS", "api_id": "petstore-v1"},
    ]
