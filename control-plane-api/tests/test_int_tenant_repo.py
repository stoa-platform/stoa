"""Integration tests for TenantRepository with real PostgreSQL."""
import pytest

from src.models.tenant import Tenant, TenantStatus
from src.repositories.tenant import TenantRepository


@pytest.mark.integration
class TestTenantRepositoryIntegration:
    async def test_create_tenant(self, integration_db):
        repo = TenantRepository(integration_db)
        tenant = Tenant(
            id="int-test-acme",
            name="ACME Corporation",
            description="Integration test tenant",
            status=TenantStatus.ACTIVE.value,
            settings={"owner_email": "admin@acme.test"},
        )
        created = await repo.create(tenant)

        assert created.id == "int-test-acme"
        assert created.name == "ACME Corporation"
        assert created.created_at is not None

    async def test_get_by_id(self, integration_db):
        repo = TenantRepository(integration_db)
        tenant = Tenant(
            id="int-test-lookup",
            name="Lookup Corp",
            status=TenantStatus.ACTIVE.value,
            settings={},
        )
        await repo.create(tenant)

        found = await repo.get_by_id("int-test-lookup")
        assert found is not None
        assert found.name == "Lookup Corp"

    async def test_get_by_id_not_found(self, integration_db):
        repo = TenantRepository(integration_db)
        found = await repo.get_by_id("nonexistent-tenant-id")
        assert found is None

    async def test_list_excludes_archived(self, integration_db):
        repo = TenantRepository(integration_db)

        await repo.create(Tenant(
            id="int-active-1", name="Active One",
            status=TenantStatus.ACTIVE.value, settings={},
        ))
        await repo.create(Tenant(
            id="int-archived-1", name="Archived One",
            status=TenantStatus.ARCHIVED.value, settings={},
        ))

        tenants = await repo.list_all(include_archived=False)
        ids = [t.id for t in tenants]
        assert "int-active-1" in ids
        assert "int-archived-1" not in ids

    async def test_update_tenant(self, integration_db):
        repo = TenantRepository(integration_db)
        tenant = Tenant(
            id="int-test-update",
            name="Before Update",
            status=TenantStatus.ACTIVE.value,
            settings={},
        )
        await repo.create(tenant)

        tenant.name = "After Update"
        updated = await repo.update(tenant)
        assert updated.name == "After Update"
