"""Exercise the tenant UUID column against the actual PostgreSQL migration."""

import os
import runpy
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.models.tenant import Tenant

pytestmark = pytest.mark.integration
MIGRATION = Path(__file__).parents[1] / "alembic/versions/110_tenant_uuid.py"
SEEDED = [f"tenant-{index}" for index in range(5)]
# Raw SQL seeds (demo reset, seeders) never name the uuid column.
SEED = text(
    "INSERT INTO tenants (id, name, status, provisioning_status, settings) VALUES (:id, :id, 'active', 'ready', '{}')"
)
COLUMNS = text(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_schema = current_schema() AND table_name = 'tenants'"
)


def migrate(connection: Connection, direction: str = "upgrade") -> None:
    with Operations.context(MigrationContext.configure(connection)):
        runpy.run_path(str(MIGRATION))[direction]()


@pytest.fixture
async def tenant_db() -> AsyncIterator[AsyncEngine]:
    schema = f"tenant_uuid_test_{uuid4().hex}"
    engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"server_settings": {"search_path": schema}})
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        # Start from the pre-migration shape: the model's table minus the column under test.
        await connection.run_sync(Tenant.__table__.create)
        await connection.run_sync(migrate, "downgrade")
        for tenant in SEEDED:
            await connection.execute(SEED, {"id": tenant})
        await connection.run_sync(migrate)
    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def test_upgrade_backfills_existing_rows_with_distinct_uuids(tenant_db: AsyncEngine) -> None:
    async with tenant_db.connect() as connection:
        rows = (await connection.execute(text("SELECT id, uuid FROM tenants ORDER BY id"))).all()
    assert [tenant for tenant, _ in rows] == SEEDED
    assert all(isinstance(value, UUID) for _, value in rows)
    assert len({value for _, value in rows}) == len(SEEDED)


@pytest.mark.parametrize(
    "value", ["NULL", "(SELECT uuid FROM tenants WHERE id = 'tenant-0')"], ids=["null", "duplicate"]
)
async def test_null_and_duplicate_uuids_are_rejected(tenant_db: AsyncEngine, value: str) -> None:
    statement = f"INSERT INTO tenants (id, name, status, provisioning_status, settings, uuid) VALUES ('late', 'late', 'active', 'ready', '{{}}', {value})"  # noqa: S608 - Fixed test literals.
    async with tenant_db.begin() as connection:
        with pytest.raises(IntegrityError):
            await connection.execute(text(statement))


async def test_raw_insert_without_uuid_gets_a_fresh_one(tenant_db: AsyncEngine) -> None:
    async with tenant_db.begin() as connection:
        await connection.execute(SEED, {"id": "late"})
        late = await connection.scalar(text("SELECT uuid FROM tenants WHERE id = 'late'"))
        assert isinstance(late, UUID)
        assert await connection.scalar(text("SELECT count(*) FROM tenants WHERE uuid = :late"), {"late": late}) == 1


async def test_upgrade_downgrade_upgrade_round_trip(tenant_db: AsyncEngine) -> None:
    # The fixture already ran the first upgrade over the seeded rows.
    async with tenant_db.begin() as connection:
        await connection.run_sync(migrate, "downgrade")
        assert "uuid" not in (await connection.execute(COLUMNS)).scalars().all()
        await connection.execute(SEED, {"id": "downgraded"})
        await connection.run_sync(migrate)
        assert "uuid" in (await connection.execute(COLUMNS)).scalars().all()
        uuids = (await connection.execute(text("SELECT uuid FROM tenants"))).scalars().all()
    assert len(uuids) == len(SEEDED) + 1
    assert len(set(uuids)) == len(uuids)
