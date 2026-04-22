"""Invariant tests for the deterministic demo fixtures (CAB-2149).

These tests guard the pure-Python contract of
:mod:`src.seed.demo_fixtures` — no DB involved. They protect the downstream
reset service (PR B) and CLI (PR C) from fixture regressions that would
break byte-identical cold-run snapshots.
"""

from __future__ import annotations

import json
from datetime import datetime

from src.seed.demo_fixtures import (
    CUSTOMER_API_ID,
    CUSTOMER_API_NAME,
    CUSTOMER_API_VERSION,
    DEMO_FIXTURES,
    DEMO_TENANTS,
    default_bundle,
)


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

    def test_bundle_tenant_ids_stable(self) -> None:
        bundle = default_bundle()
        assert bundle.tenant_ids == ("tenant-a", "tenant-b", "tenant-c", "tenant-d")
        # apis_for is tenant-scoped and returns the Customer API row.
        apis = bundle.apis_for("tenant-a")
        assert len(apis) == 1
        assert apis[0].api_id == CUSTOMER_API_ID

    def test_fixture_tuples_are_immutable(self) -> None:
        # Tuple vs list guard — downstream snapshot stability depends on this.
        assert isinstance(DEMO_FIXTURES, tuple)
        assert isinstance(DEMO_FIXTURES[0].api.tags, tuple)

    def test_fixtures_carry_no_wallclock_timestamps(self) -> None:
        # Fixture dataclasses must not embed datetime fields — the reset
        # service owns the single frozen epoch. Catching drift here prevents
        # silent snapshot divergence.
        for tenant in DEMO_FIXTURES:
            for value in (tenant.id, tenant.name, tenant.description, tenant.api):
                assert not isinstance(value, datetime)
