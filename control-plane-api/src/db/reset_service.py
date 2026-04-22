"""Deterministic demo reset/seed service (CAB-2149).

Tenant-scoped purge + re-seed helper. Guarantees two cold cycles produce
byte-identical catalogue state with zero tenant leakage. Driver-agnostic:
asyncpg/PostgreSQL in prod, aiosqlite/SQLite in tests. Uses portable
``text()`` SQL with bound parameters — no JSONB operators.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from src.seed.demo_fixtures import DemoFixtureBundle, default_bundle

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("stoa.demo.reset")

# Frozen timestamp — ``created_at``/``updated_at`` must not vary between runs.
DEMO_SEED_EPOCH = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

_SEED_TENANT_SQL = """
INSERT INTO tenants (id, name, description, status, provisioning_status,
                     settings, created_at, updated_at)
VALUES (:id, :name, :description, 'active', 'ready', :settings,
        :created_at, :updated_at)
"""

_SEED_API_SQL = """
INSERT INTO api_catalog (id, tenant_id, api_id, api_name, version, status,
                         category, tags, portal_published, audience, metadata,
                         target_gateways, synced_at)
VALUES (:id, :tenant_id, :api_id, :api_name, :version, 'active', :category,
        :tags, 1, :audience, :metadata, :target_gateways, :synced_at)
"""

_SNAPSHOT_SQL = (
    "SELECT tenant_id, api_id, api_name, version, category, audience, tags, "
    "metadata FROM api_catalog WHERE tenant_id IN ({placeholders}) "
    "ORDER BY tenant_id, api_id, version"
)


@dataclass
class DemoResetResult:
    """Summary of a single reset/seed cycle."""

    tenants_deleted: int = 0
    apis_deleted: int = 0
    tenants_created: int = 0
    apis_created: int = 0
    tenant_ids: tuple[str, ...] = field(default_factory=tuple)


class DemoResetService:
    """Tenant-scoped purge + deterministic re-seed for the demo catalogue.

    Args:
        session: Async SQLAlchemy session. Caller owns commit/rollback.
        bundle: Optional fixture override (defaults to canonical bundle).
    """

    def __init__(
        self,
        session: AsyncSession,
        bundle: DemoFixtureBundle | None = None,
    ) -> None:
        self._session = session
        self._bundle = bundle or default_bundle()

    @property
    def bundle(self) -> DemoFixtureBundle:
        return self._bundle

    async def reset(self, tenant_ids: tuple[str, ...] | None = None) -> DemoResetResult:
        """Delete catalogue rows for the given tenants (defaults to demo tenants)."""
        targets = tenant_ids or self._bundle.tenant_ids
        result = DemoResetResult(tenant_ids=targets)
        for tenant_id in targets:
            apis_row = await self._session.execute(
                text("DELETE FROM api_catalog WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
            result.apis_deleted += getattr(apis_row, "rowcount", 0) or 0
            tenants_row = await self._session.execute(
                text("DELETE FROM tenants WHERE id = :tid"),
                {"tid": tenant_id},
            )
            result.tenants_deleted += getattr(tenants_row, "rowcount", 0) or 0
        logger.info(
            "demo reset: tenants_deleted=%d apis_deleted=%d targets=%s",
            result.tenants_deleted,
            result.apis_deleted,
            targets,
        )
        return result

    async def seed(self) -> DemoResetResult:
        """Insert the deterministic demo fixtures. Idempotent after ``reset``."""
        result = DemoResetResult(tenant_ids=self._bundle.tenant_ids)
        for tenant in self._bundle.tenants:
            await self._session.execute(
                text(_SEED_TENANT_SQL),
                {
                    "id": tenant.id,
                    "name": tenant.name,
                    "description": tenant.description,
                    "settings": json.dumps({"source": "demo-seeder", "demo": True}),
                    "created_at": DEMO_SEED_EPOCH,
                    "updated_at": DEMO_SEED_EPOCH,
                },
            )
            result.tenants_created += 1

            api = tenant.api
            await self._session.execute(
                text(_SEED_API_SQL),
                {
                    "id": str(api.deterministic_uuid),
                    "tenant_id": api.tenant_id,
                    "api_id": api.api_id,
                    "api_name": api.api_name,
                    "version": api.version,
                    "category": api.category,
                    "tags": json.dumps(list(api.tags)),
                    "audience": api.audience,
                    "metadata": json.dumps(api.metadata()),
                    "target_gateways": json.dumps([]),
                    "synced_at": DEMO_SEED_EPOCH,
                },
            )
            result.apis_created += 1
        logger.info(
            "demo seed: tenants_created=%d apis_created=%d",
            result.tenants_created,
            result.apis_created,
        )
        return result

    async def run_cycle(self) -> DemoResetResult:
        """Convenience: ``reset`` followed by ``seed`` in a single call."""
        reset_result = await self.reset()
        seed_result = await self.seed()
        return DemoResetResult(
            tenants_deleted=reset_result.tenants_deleted,
            apis_deleted=reset_result.apis_deleted,
            tenants_created=seed_result.tenants_created,
            apis_created=seed_result.apis_created,
            tenant_ids=self._bundle.tenant_ids,
        )

    async def snapshot(self) -> list[dict[str, object]]:
        """Return a deterministic snapshot of the demo catalogue (for diff/evidence)."""
        tenant_ids = list(self._bundle.tenant_ids)
        placeholders = ", ".join(f":t{i}" for i in range(len(tenant_ids)))
        params: dict[str, object] = {f"t{i}": tid for i, tid in enumerate(tenant_ids)}
        # placeholders is ``":t0, :t1, ..."`` derived from the internal fixture
        # tuple — no user input. Tenant ids are bound as parameters. Safe SQL.
        query = _SNAPSHOT_SQL.format(placeholders=placeholders)
        rows = await self._session.execute(text(query), params)
        return [dict(r._mapping) for r in rows]
