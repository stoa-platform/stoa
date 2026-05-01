"""Regression tests for Portal provider plan discovery.

The Developer Portal can show APIs from provider tenants other than the
consumer's tenant. Plan selection must therefore use a read-only Portal surface
instead of the tenant-admin plans endpoint.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.models.plan import PlanStatus


def _make_plan(**overrides):
    plan = MagicMock()
    now = datetime.now(UTC).replace(tzinfo=None)
    defaults = {
        "id": uuid4(),
        "slug": "portal-standard",
        "name": "Portal Standard",
        "description": "Self-service plan",
        "tenant_id": "acme",
        "rate_limit_per_second": 10,
        "rate_limit_per_minute": 600,
        "daily_request_limit": 50_000,
        "monthly_request_limit": 1_000_000,
        "burst_limit": 20,
        "requires_approval": False,
        "auto_approve_roles": None,
        "status": PlanStatus.ACTIVE,
        "pricing_metadata": {"source": "test"},
        "created_at": now,
        "updated_at": now,
        "created_by": "test",
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(plan, key, value)
    return plan


class TestPortalProviderPlans:
    def test_portal_plans_allows_visible_cross_tenant_provider(self, client_as_other_tenant):
        catalog_repo = MagicMock()
        catalog_repo.get_portal_apis = AsyncMock(return_value=([MagicMock()], 1))
        plan_repo = MagicMock()
        plan_repo.list_by_tenant = AsyncMock(return_value=([_make_plan()], 1))

        with (
            patch("src.routers.portal.CatalogRepository", return_value=catalog_repo),
            patch("src.routers.portal.PlanRepository", return_value=plan_repo),
        ):
            response = client_as_other_tenant.get("/v1/portal/plans/acme")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["slug"] == "portal-standard"
        plan_repo.list_by_tenant.assert_awaited_once_with(
            tenant_id="acme",
            status=PlanStatus.ACTIVE,
            page=1,
            page_size=50,
        )

    def test_portal_plans_hide_tenants_without_visible_portal_api(self, client_as_other_tenant):
        catalog_repo = MagicMock()
        catalog_repo.get_portal_apis = AsyncMock(return_value=([], 0))
        plan_repo = MagicMock()
        plan_repo.list_by_tenant = AsyncMock()

        with (
            patch("src.routers.portal.CatalogRepository", return_value=catalog_repo),
            patch("src.routers.portal.PlanRepository", return_value=plan_repo),
        ):
            response = client_as_other_tenant.get("/v1/portal/plans/acme")

        assert response.status_code == 404
        plan_repo.list_by_tenant.assert_not_awaited()


_MIGRATION_PATH = Path(__file__).parent.parent / "alembic" / "versions" / "101_seed_portal_subscription_plans.py"
_SPEC = importlib.util.spec_from_file_location("migration_101", _MIGRATION_PATH)
_MIGRATION = importlib.util.module_from_spec(_SPEC)
sys.modules["migration_101"] = _MIGRATION
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MIGRATION)


class TestPortalPlanSeedMigration:
    def test_seed_migration_chains_after_current_head(self):
        assert _MIGRATION.down_revision == "100_fix_webmethods_nonprod_urls"

    def test_seed_migration_targets_only_published_tenants_without_active_plans(self):
        source = _MIGRATION_PATH.read_text(encoding="utf-8")
        assert "c.portal_published IS TRUE" in source
        assert "c.deleted_at IS NULL" in source
        assert "NOT EXISTS" in source
        assert "p.status = 'active'" in source
        assert "portal-standard" in source
        assert "portal-premium" in source

    def test_seed_plan_ids_are_deterministic_per_tenant_and_slug(self):
        first = _MIGRATION._plan_id("high-five", "portal-standard")
        second = _MIGRATION._plan_id("high-five", "portal-standard")
        other = _MIGRATION._plan_id("ioi", "portal-standard")

        assert first == second
        assert first != other
