"""Integration smoke test — verify database tables can be created from models."""
import pytest
from sqlalchemy import text

from src.database import Base


@pytest.mark.integration
class TestMigrationSmoke:
    async def test_all_tables_created(self, integration_db):
        """Verify that Base.metadata.create_all created all expected tables."""
        result = await integration_db.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        )
        tables = [row[0] for row in result.fetchall()]

        expected_tables = [
            "contracts",
            "gateway_instances",
            "protocol_bindings",
            "subscriptions",
            "tenants",
        ]

        for table in expected_tables:
            assert table in tables, f"Expected table '{table}' not found. Found: {tables}"

    async def test_table_count_reasonable(self, integration_db):
        """Verify a reasonable number of tables exist (catches missing model imports)."""
        result = await integration_db.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        )
        count = result.scalar_one()

        # We have ~15+ models, so at least 10 tables should exist
        assert count >= 10, f"Only {count} tables found — possible missing model imports"
