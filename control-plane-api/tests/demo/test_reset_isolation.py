"""Evidence tests for the deterministic demo reset/seed (CAB-2149).

These tests back the DoD of CAB-2149:

* Two cold ``reset + seed`` cycles produce byte-identical catalogue state.
* No tenant/persona leakage — reset stays scoped to demo tenants.
* Reset contract holds on an empty schema (idempotent for cold starts).

Regression markers follow the ``test_regression_cab_2149_*`` convention so the
regression-guard workflow treats them as permanent fix guards.
"""

from __future__ import annotations

import json
import time

import pytest
from sqlalchemy import text

from src.db.reset_service import DEMO_SEED_EPOCH, DemoResetService
from src.seed.demo_fixtures import (
    CUSTOMER_API_ID,
    CUSTOMER_API_NAME,
    CUSTOMER_API_VERSION,
    DEMO_FIXTURES,
    DEMO_TENANTS,
    default_bundle,
)

# ---------------------------------------------------------------------------
# Fixture invariants (pure unit — no DB)
# ---------------------------------------------------------------------------


class TestDemoFixtureInvariants:
    """Guard the deterministic contract of the fixture module."""

    def test_four_tenants_placeholders_only(self) -> None:
        ids = [t["id"] for t in DEMO_TENANTS]
        assert ids == ["tenant-a", "tenant-b", "tenant-c", "tenant-d"]

    def test_fixtures_sorted_by_tenant_id(self) -> None:
        ids = [t.id for t in DEMO_FIXTURES]
        assert ids == sorted(ids)

    def test_every_tenant_has_customer_api(self) -> None:
        for tenant in DEMO_FIXTURES:
            assert tenant.api.api_id == CUSTOMER_API_ID
            assert tenant.api.version == CUSTOMER_API_VERSION

    def test_deterministic_uuid_stable_across_builds(self) -> None:
        first = default_bundle().tenants[0].api.deterministic_uuid
        second = default_bundle().tenants[0].api.deterministic_uuid
        assert first == second

    def test_deterministic_uuid_differs_per_tenant(self) -> None:
        uuids = {t.api.deterministic_uuid for t in DEMO_FIXTURES}
        assert len(uuids) == len(DEMO_FIXTURES)

    def test_metadata_is_json_serialisable(self) -> None:
        for tenant in DEMO_FIXTURES:
            payload = json.dumps(tenant.api.metadata(), sort_keys=True)
            assert CUSTOMER_API_NAME in payload
            assert "demo-seeder" in payload

    def test_seed_epoch_is_timezone_aware(self) -> None:
        assert DEMO_SEED_EPOCH.tzinfo is not None


# ---------------------------------------------------------------------------
# DB-backed reset + seed contract
# ---------------------------------------------------------------------------


async def _insert_foreign_rows(session, foreign_tenant_rows: list[dict[str, str]]) -> None:
    """Populate non-demo tenants so we can prove reset is scoped."""
    for row in foreign_tenant_rows:
        await session.execute(
            text("INSERT INTO tenants (id, name, description, settings) " "VALUES (:id, :name, 'foreign', '{}')"),
            {"id": row["id"], "name": row["name"]},
        )
        await session.execute(
            text(
                "INSERT INTO api_catalog (id, tenant_id, api_id, api_name, "
                "version, tags, metadata) "
                "VALUES (:id, :tid, :api_id, 'Foreign API', '1.0.0', '[]', '{}')"
            ),
            {"id": f"foreign-{row['id']}", "tid": row["id"], "api_id": row["api_id"]},
        )


@pytest.mark.asyncio
class TestResetSeedCycle:
    """Spec: deterministic reset + seed, byte-identical across cycles."""

    async def test_regression_cab_2149_two_cycles_byte_identical(self, demo_session) -> None:
        service = DemoResetService(demo_session)

        await service.run_cycle()
        snapshot_a = await service.snapshot()

        await service.run_cycle()
        snapshot_b = await service.snapshot()

        # Serialise deterministically and compare bytes.
        payload_a = json.dumps(snapshot_a, sort_keys=True, default=str).encode()
        payload_b = json.dumps(snapshot_b, sort_keys=True, default=str).encode()
        assert payload_a == payload_b, "two cold cycles must produce byte-identical catalogue"

    async def test_regression_cab_2149_seed_inserts_one_api_per_tenant(self, demo_session) -> None:
        service = DemoResetService(demo_session)
        await service.run_cycle()
        rows = await demo_session.execute(text("SELECT tenant_id, api_id FROM api_catalog ORDER BY tenant_id"))
        pairs = [(r[0], r[1]) for r in rows]
        assert pairs == [(t, CUSTOMER_API_ID) for t in ("tenant-a", "tenant-b", "tenant-c", "tenant-d")]

    async def test_regression_cab_2149_reset_is_tenant_scoped(self, demo_session, foreign_tenant_rows) -> None:
        await _insert_foreign_rows(demo_session, foreign_tenant_rows)
        service = DemoResetService(demo_session)
        await service.run_cycle()
        await service.reset()

        # Foreign rows survive; demo rows are gone.
        tenants_row = await demo_session.execute(text("SELECT id FROM tenants ORDER BY id"))
        remaining_tenants = [r[0] for r in tenants_row]
        assert remaining_tenants == ["oasis", "prod-acme"]
        apis_row = await demo_session.execute(text("SELECT tenant_id FROM api_catalog ORDER BY tenant_id"))
        remaining_api_tenants = [r[0] for r in apis_row]
        assert remaining_api_tenants == ["oasis", "prod-acme"]

    async def test_regression_cab_2149_no_cross_tenant_uuid_collision(self, demo_session) -> None:
        service = DemoResetService(demo_session)
        await service.run_cycle()
        row = await demo_session.execute(text("SELECT COUNT(DISTINCT id) FROM api_catalog"))
        assert row.scalar_one() == len(DEMO_FIXTURES)

    async def test_regression_cab_2149_reset_on_empty_schema_is_noop(self, demo_session) -> None:
        service = DemoResetService(demo_session)
        result = await service.reset()
        assert result.tenants_deleted == 0
        assert result.apis_deleted == 0

    async def test_regression_cab_2149_cycle_budget_under_60s_on_small_fixture(self, demo_session) -> None:
        service = DemoResetService(demo_session)
        start = time.perf_counter()
        await service.run_cycle()
        elapsed = time.perf_counter() - start
        # DoD budget is 60s on k3d. On an in-memory SQLite it must be far below
        # that — this guard catches quadratic regressions in the seeder.
        assert elapsed < 5.0, f"demo cycle took {elapsed:.2f}s, budget is 60s"

    async def test_regression_cab_2149_snapshot_sorted_for_diffing(self, demo_session) -> None:
        service = DemoResetService(demo_session)
        await service.run_cycle()
        snapshot = await service.snapshot()
        tenant_ids = [row["tenant_id"] for row in snapshot]
        assert tenant_ids == sorted(tenant_ids)
