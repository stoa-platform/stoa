"""Integration tests for SubscriptionRepository with real PostgreSQL."""
import hashlib
import uuid

import pytest

from src.models.subscription import Subscription, SubscriptionStatus
from src.models.tenant import Tenant, TenantStatus
from src.repositories.subscription import SubscriptionRepository
from src.repositories.tenant import TenantRepository


def _make_api_key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@pytest.mark.integration
class TestSubscriptionRepositoryIntegration:
    async def _seed_tenant(self, db, tenant_id: str = "int-sub-tenant"):
        repo = TenantRepository(db)
        tenant = Tenant(
            id=tenant_id, name="Sub Test Tenant",
            status=TenantStatus.ACTIVE.value, settings={},
        )
        await repo.create(tenant)
        return tenant

    async def test_create_subscription(self, integration_db):
        await self._seed_tenant(integration_db)
        repo = SubscriptionRepository(integration_db)

        sub = Subscription(
            id=uuid.uuid4(),
            application_id="app-001",
            application_name="Test App",
            subscriber_id="user-001",
            subscriber_email="user@test.com",
            api_id="api-001",
            api_name="Test API",
            api_version="1.0",
            tenant_id="int-sub-tenant",
            api_key_hash=_make_api_key_hash("test-key-001"),
            api_key_prefix="test-key",
            status=SubscriptionStatus.PENDING,
        )
        created = await repo.create(sub)

        assert created.id is not None
        assert created.status == SubscriptionStatus.PENDING
        assert created.api_key_prefix == "test-key"

    async def test_approve_subscription(self, integration_db):
        await self._seed_tenant(integration_db, "int-sub-approve")
        repo = SubscriptionRepository(integration_db)

        sub = Subscription(
            id=uuid.uuid4(),
            application_id="app-002",
            application_name="Approve App",
            subscriber_id="user-002",
            subscriber_email="approver@test.com",
            api_id="api-002",
            api_name="Approve API",
            api_version="1.0",
            tenant_id="int-sub-approve",
            api_key_hash=_make_api_key_hash("test-key-002"),
            api_key_prefix="test-key",
            status=SubscriptionStatus.PENDING,
        )
        await repo.create(sub)

        updated = await repo.update_status(
            sub, SubscriptionStatus.ACTIVE, actor_id="admin-001"
        )
        assert updated.status == SubscriptionStatus.ACTIVE
        assert updated.approved_at is not None
        assert updated.approved_by == "admin-001"

    async def test_list_by_tenant(self, integration_db):
        await self._seed_tenant(integration_db, "int-sub-list")
        repo = SubscriptionRepository(integration_db)

        for i in range(3):
            sub = Subscription(
                id=uuid.uuid4(),
                application_id=f"app-list-{i}",
                application_name=f"List App {i}",
                subscriber_id="user-list",
                subscriber_email="list@test.com",
                api_id=f"api-list-{i}",
                api_name=f"List API {i}",
                api_version="1.0",
                tenant_id="int-sub-list",
                api_key_hash=_make_api_key_hash(f"list-key-{i}"),
                api_key_prefix=f"list-{i}",
                status=SubscriptionStatus.ACTIVE,
            )
            await repo.create(sub)

        subs, total = await repo.list_by_tenant("int-sub-list")
        assert total == 3
        assert len(subs) == 3

    async def test_key_rotation(self, integration_db):
        await self._seed_tenant(integration_db, "int-sub-rotate")
        repo = SubscriptionRepository(integration_db)

        original_hash = _make_api_key_hash("original-key")
        sub = Subscription(
            id=uuid.uuid4(),
            application_id="app-rotate",
            application_name="Rotate App",
            subscriber_id="user-rotate",
            subscriber_email="rotate@test.com",
            api_id="api-rotate",
            api_name="Rotate API",
            api_version="1.0",
            tenant_id="int-sub-rotate",
            api_key_hash=original_hash,
            api_key_prefix="orig-key",
            status=SubscriptionStatus.ACTIVE,
        )
        await repo.create(sub)

        new_hash = _make_api_key_hash("new-rotated-key")
        rotated = await repo.rotate_key(
            sub, new_api_key_hash=new_hash, new_api_key_prefix="new-key", grace_period_hours=24
        )

        assert rotated.api_key_hash == new_hash
        assert rotated.api_key_prefix == "new-key"
        assert rotated.previous_api_key_hash == original_hash
        assert rotated.previous_key_expires_at is not None
        assert rotated.rotation_count == 1

    async def test_get_by_api_key_hash(self, integration_db):
        await self._seed_tenant(integration_db, "int-sub-keyhash")
        repo = SubscriptionRepository(integration_db)

        key_hash = _make_api_key_hash("lookup-by-hash-key")
        sub = Subscription(
            id=uuid.uuid4(),
            application_id="app-hash",
            application_name="Hash App",
            subscriber_id="user-hash",
            subscriber_email="hash@test.com",
            api_id="api-hash",
            api_name="Hash API",
            api_version="1.0",
            tenant_id="int-sub-keyhash",
            api_key_hash=key_hash,
            api_key_prefix="hash-key",
            status=SubscriptionStatus.ACTIVE,
        )
        await repo.create(sub)

        found = await repo.get_by_api_key_hash(key_hash)
        assert found is not None
        assert found.application_name == "Hash App"
