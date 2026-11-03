"""Exercise policy versions against the actual PostgreSQL migration."""

import asyncio
import os
import runpy
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.models.tenant_tool_permission import TenantToolPermission
from src.models.tool_policy_version import ToolPolicyVersion
from src.schemas.tenant_tool_permission import TenantToolPermissionCreate

pytestmark = pytest.mark.integration
MIGRATION = Path(__file__).parents[1] / "alembic/versions/109_tool_policy_versions.py"


def migrate(connection: Connection, direction: str = "upgrade") -> None:
    with Operations.context(MigrationContext.configure(connection)):
        runpy.run_path(str(MIGRATION))[direction]()


def permission(tenant: str = "tenant-a", tool: str = "read") -> TenantToolPermission:
    return TenantToolPermission(tenant_id=tenant, mcp_server_id=uuid4(), tool_name=tool, created_by="test")


@pytest.fixture
async def policy_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    schema = f"policy_test_{uuid4().hex}"
    engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"server_settings": {"search_path": schema}})
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.run_sync(TenantToolPermission.__table__.create)
        await connection.execute(
            TenantToolPermission.__table__.insert().values(
                tenant_id="existing", mcp_server_id=uuid4(), tool_name="read", created_by="test"
            )
        )
        await connection.run_sync(migrate)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def version(session: AsyncSession, tenant: str = "tenant-a") -> int:
    return await session.scalar(select(ToolPolicyVersion.version).where(ToolPolicyVersion.tenant_id == tenant)) or 1


async def test_mutations_increment_and_preserve_tenant_isolation(policy_db) -> None:
    async with policy_db.begin() as session:
        backfilled = await session.get(ToolPolicyVersion, "existing")
        assert backfilled is not None and backfilled.version == 1
        row = permission()
        session.add(row)
        await session.flush()
        assert await version(session) == 2
        row.allowed = False
        await session.flush()
        assert await version(session) == 3
        await session.delete(row)
        await session.flush()
        assert await version(session) == 4
        assert await version(session, "existing") == 1
    async with policy_db() as session:
        assert await version(session) == 4
        assert (
            await session.scalar(select(TenantToolPermission).where(TenantToolPermission.tenant_id == "tenant-a"))
            is None
        )


@pytest.mark.parametrize("existing", [False, True])
async def test_rollback_reverts_permission_and_version(policy_db, existing: bool) -> None:
    tenant = "existing" if existing else "tenant-a"
    async with policy_db() as session:
        before = await version(session, tenant)
        session.add(permission(tenant, "write"))
        await session.flush()
        assert await version(session, tenant) == before + 1
        await session.rollback()
    async with policy_db() as session:
        assert await version(session, tenant) == before
        assert (
            await session.scalar(select(TenantToolPermission).where(TenantToolPermission.tool_name == "write")) is None
        )


@pytest.mark.parametrize("tenant", ["tenant-a", "existing"])
async def test_concurrent_mutations_get_distinct_versions(policy_db, tenant: str) -> None:
    barrier = asyncio.Barrier(2)

    async def mutate(tool: str) -> int:
        async with policy_db.begin() as session:
            session.add(permission(tenant, tool))
            await barrier.wait()
            await session.flush()
            return await version(session, tenant)

    assert sorted(await asyncio.wait_for(asyncio.gather(mutate("read"), mutate("write")), timeout=10)) == [2, 3]
    async with policy_db() as session:
        assert await version(session, tenant) == 3


@pytest.mark.parametrize(
    "operation", ["decrement", "rekey", "delete", "truncate", "truncate_permissions", "move_permission"]
)
async def test_no_counter_reset_or_decrement_path(policy_db, operation: str) -> None:
    tenant = ToolPolicyVersion.tenant_id == "tenant-a"
    statements = {
        "decrement": update(ToolPolicyVersion).where(tenant).values(version=1),
        "rekey": update(ToolPolicyVersion).where(tenant).values(tenant_id="other"),
        "delete": delete(ToolPolicyVersion).where(tenant),
        "truncate": text("TRUNCATE tool_policy_versions"),
        "truncate_permissions": text("TRUNCATE tenant_tool_permissions"),
        "move_permission": update(TenantToolPermission).values(tenant_id="other"),
    }
    async with policy_db.begin() as session:
        session.add(permission())
    async with policy_db() as session:
        with pytest.raises(DBAPIError, match=r"policy version|permission tenant"):
            await session.execute(statements[operation])
        await session.rollback()
        assert await version(session) == 2
    assert "version" not in TenantToolPermissionCreate.model_fields


async def test_migration_downgrade_and_upgrade(policy_db) -> None:
    engine: AsyncEngine = policy_db.kw["bind"]
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "downgrade")
        assert await connection.scalar(text("SELECT to_regclass('tool_policy_versions')")) is None
        await connection.execute(
            TenantToolPermission.__table__.insert().values(
                tenant_id="downgraded", mcp_server_id=uuid4(), tool_name="read", created_by="test"
            )
        )
        await connection.run_sync(migrate)
    async with policy_db() as session:
        assert await version(session, "downgraded") == 1
        session.add(permission("downgraded", "write"))
        await session.flush()
        assert await version(session, "downgraded") == 2
