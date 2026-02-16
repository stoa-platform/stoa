"""Tests for SubscriptionRepository (CAB-1291)"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.models.subscription import SubscriptionStatus
from src.repositories.subscription import SubscriptionRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_sub(**kwargs):
    sub = MagicMock()
    sub.id = kwargs.get("id", uuid4())
    sub.tenant_id = kwargs.get("tenant_id", "acme")
    sub.subscriber_id = kwargs.get("subscriber_id", "user-1")
    sub.application_id = kwargs.get("application_id", "app-1")
    sub.api_id = kwargs.get("api_id", "api-1")
    sub.status = kwargs.get("status", SubscriptionStatus.ACTIVE)
    sub.api_key_hash = kwargs.get("api_key_hash", "hash123")
    sub.api_key_prefix = kwargs.get("api_key_prefix", "sk-test")
    sub.previous_api_key_hash = kwargs.get("previous_api_key_hash", None)
    sub.previous_key_expires_at = kwargs.get("previous_key_expires_at", None)
    sub.rotation_count = kwargs.get("rotation_count", 0)
    sub.created_at = kwargs.get("created_at", datetime(2026, 2, 16))
    sub.updated_at = kwargs.get("updated_at", None)
    sub.approved_at = kwargs.get("approved_at", None)
    sub.approved_by = kwargs.get("approved_by", None)
    sub.revoked_at = kwargs.get("revoked_at", None)
    sub.revoked_by = kwargs.get("revoked_by", None)
    sub.status_reason = kwargs.get("status_reason", None)
    sub.expires_at = kwargs.get("expires_at", None)
    sub.last_rotated_at = kwargs.get("last_rotated_at", None)
    return sub


# ── create ──


class TestCreate:
    async def test_creates(self):
        db = _mock_db()
        repo = SubscriptionRepository(db)
        sub = _mock_sub()
        result = await repo.create(sub)
        db.add.assert_called_once_with(sub)
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once_with(sub)
        assert result is sub


# ── get_by_id ──


class TestGetById:
    async def test_found(self):
        db = _mock_db()
        sub = _mock_sub()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        db.execute = AsyncMock(return_value=mock_result)

        repo = SubscriptionRepository(db)
        result = await repo.get_by_id(sub.id)
        assert result is sub

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = SubscriptionRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


# ── get_by_api_key_hash ──


class TestGetByApiKeyHash:
    async def test_found(self):
        db = _mock_db()
        sub = _mock_sub()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        db.execute = AsyncMock(return_value=mock_result)

        repo = SubscriptionRepository(db)
        result = await repo.get_by_api_key_hash("hash123")
        assert result is sub


# ── get_by_application_and_api ──


class TestGetByApplicationAndApi:
    async def test_found(self):
        db = _mock_db()
        sub = _mock_sub()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        db.execute = AsyncMock(return_value=mock_result)

        repo = SubscriptionRepository(db)
        result = await repo.get_by_application_and_api("app-1", "api-1")
        assert result is sub

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = SubscriptionRepository(db)
        result = await repo.get_by_application_and_api("app-x", "api-x")
        assert result is None


# ── list_by_subscriber ──


class TestListBySubscriber:
    async def test_returns_list(self):
        db = _mock_db()
        subs = [_mock_sub(), _mock_sub()]

        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2

        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = subs

        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = SubscriptionRepository(db)
        items, total = await repo.list_by_subscriber("user-1")
        assert total == 2
        assert len(items) == 2

    async def test_with_status_filter(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_sub()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = SubscriptionRepository(db)
        items, total = await repo.list_by_subscriber("user-1", status=SubscriptionStatus.ACTIVE)
        assert total == 1


# ── list_by_tenant ──


class TestListByTenant:
    async def test_returns_list(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 3
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_sub()] * 3
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = SubscriptionRepository(db)
        items, total = await repo.list_by_tenant("acme")
        assert total == 3
        assert len(items) == 3

    async def test_with_status(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = SubscriptionRepository(db)
        items, total = await repo.list_by_tenant("acme", status=SubscriptionStatus.REVOKED)
        assert total == 0
        assert items == []


# ── list_by_api ──


class TestListByApi:
    async def test_returns_list(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_sub()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = SubscriptionRepository(db)
        items, total = await repo.list_by_api("api-1", "acme")
        assert total == 1

    async def test_with_status(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = SubscriptionRepository(db)
        items, total = await repo.list_by_api("api-1", "acme", status=SubscriptionStatus.PENDING)
        assert total == 0


# ── list_pending ──


class TestListPending:
    async def test_all_tenants(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_sub(), _mock_sub()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = SubscriptionRepository(db)
        items, total = await repo.list_pending()
        assert total == 2

    async def test_by_tenant(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_sub()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = SubscriptionRepository(db)
        items, total = await repo.list_pending(tenant_id="acme")
        assert total == 1


# ── update_status ──


class TestUpdateStatus:
    async def test_active(self):
        db = _mock_db()
        repo = SubscriptionRepository(db)
        sub = _mock_sub(status=SubscriptionStatus.PENDING)

        result = await repo.update_status(sub, SubscriptionStatus.ACTIVE, actor_id="admin")
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.approved_by == "admin"
        db.flush.assert_awaited_once()

    async def test_revoked(self):
        db = _mock_db()
        repo = SubscriptionRepository(db)
        sub = _mock_sub(status=SubscriptionStatus.ACTIVE)

        result = await repo.update_status(
            sub, SubscriptionStatus.REVOKED, reason="violation", actor_id="admin"
        )
        assert sub.status == SubscriptionStatus.REVOKED
        assert sub.revoked_by == "admin"
        assert sub.status_reason == "violation"

    async def test_no_reason(self):
        db = _mock_db()
        repo = SubscriptionRepository(db)
        sub = _mock_sub()
        original_reason = sub.status_reason

        await repo.update_status(sub, SubscriptionStatus.PENDING)
        assert sub.status == SubscriptionStatus.PENDING
        assert sub.status_reason == original_reason


# ── set_expiration ──


class TestSetExpiration:
    async def test_set(self):
        db = _mock_db()
        repo = SubscriptionRepository(db)
        sub = _mock_sub()
        expires = datetime(2026, 12, 31)

        result = await repo.set_expiration(sub, expires)
        assert sub.expires_at == expires
        db.flush.assert_awaited_once()

    async def test_clear(self):
        db = _mock_db()
        repo = SubscriptionRepository(db)
        sub = _mock_sub(expires_at=datetime(2026, 12, 31))

        await repo.set_expiration(sub, None)
        assert sub.expires_at is None


# ── get_stats ──


class TestGetStats:
    async def test_returns_stats(self):
        db = _mock_db()
        # Total count
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 10

        # Per-status counts (one for each status enum value)
        status_mocks = []
        for _ in SubscriptionStatus:
            m = MagicMock()
            m.scalar_one.return_value = 2
            status_mocks.append(m)

        # Recent 24h
        mock_recent = MagicMock()
        mock_recent.scalar_one.return_value = 3

        db.execute = AsyncMock(side_effect=[mock_total] + status_mocks + [mock_recent])

        repo = SubscriptionRepository(db)
        stats = await repo.get_stats()
        assert stats["total"] == 10
        assert stats["recent_24h"] == 3
        assert isinstance(stats["by_status"], dict)

    async def test_with_tenant(self):
        db = _mock_db()
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 5
        status_mocks = []
        for _ in SubscriptionStatus:
            m = MagicMock()
            m.scalar_one.return_value = 1
            status_mocks.append(m)
        mock_recent = MagicMock()
        mock_recent.scalar_one.return_value = 0
        db.execute = AsyncMock(side_effect=[mock_total] + status_mocks + [mock_recent])

        repo = SubscriptionRepository(db)
        stats = await repo.get_stats(tenant_id="acme")
        assert stats["total"] == 5


# ── delete ──


class TestDelete:
    async def test_deletes(self):
        db = _mock_db()
        repo = SubscriptionRepository(db)
        sub = _mock_sub()

        await repo.delete(sub)
        db.delete.assert_awaited_once_with(sub)
        db.flush.assert_awaited_once()


# ── rotate_key ──


class TestRotateKey:
    async def test_rotates(self):
        db = _mock_db()
        repo = SubscriptionRepository(db)
        sub = _mock_sub(api_key_hash="old-hash", api_key_prefix="sk-old", rotation_count=1)

        result = await repo.rotate_key(sub, "new-hash", "sk-new", grace_period_hours=12)
        assert sub.api_key_hash == "new-hash"
        assert sub.api_key_prefix == "sk-new"
        assert sub.previous_api_key_hash == "old-hash"
        assert sub.rotation_count == 2
        db.flush.assert_awaited_once()

    async def test_first_rotation(self):
        db = _mock_db()
        repo = SubscriptionRepository(db)
        sub = _mock_sub(rotation_count=None)

        result = await repo.rotate_key(sub, "new-hash", "sk-new")
        assert sub.rotation_count == 1


# ── get_by_previous_key_hash ──


class TestGetByPreviousKeyHash:
    async def test_found(self):
        db = _mock_db()
        sub = _mock_sub()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        db.execute = AsyncMock(return_value=mock_result)

        repo = SubscriptionRepository(db)
        result = await repo.get_by_previous_key_hash("old-hash")
        assert result is sub


# ── cleanup_expired_previous_keys ──


class TestCleanupExpiredPreviousKeys:
    async def test_cleans_up(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        db.execute = AsyncMock(return_value=mock_result)

        repo = SubscriptionRepository(db)
        count = await repo.cleanup_expired_previous_keys()
        assert count == 3
        db.flush.assert_awaited_once()
