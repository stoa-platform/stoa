"""Tests for TenantRepository (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.tenant import Tenant, TenantStatus
from src.repositories.tenant import TenantRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_tenant(**kwargs):
    t = MagicMock(spec=Tenant)
    t.id = kwargs.get("id", "acme")
    t.name = kwargs.get("name", "Acme Corp")
    t.status = kwargs.get("status", TenantStatus.ACTIVE.value)
    return t


# ── create ──


class TestCreate:
    async def test_create(self):
        db = _mock_db()
        tenant = _mock_tenant()
        repo = TenantRepository(db)
        result = await repo.create(tenant)
        db.add.assert_called_once_with(tenant)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(tenant)
        assert result is tenant


# ── get_by_id ──


class TestGetById:
    async def test_found(self):
        db = _mock_db()
        tenant = _mock_tenant()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        db.execute = AsyncMock(return_value=mock_result)
        repo = TenantRepository(db)
        result = await repo.get_by_id("acme")
        assert result is tenant

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = TenantRepository(db)
        result = await repo.get_by_id("missing")
        assert result is None


# ── list_all ──


class TestListAll:
    async def test_active_only(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_tenant(), _mock_tenant()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = TenantRepository(db)
        result = await repo.list_all()
        assert len(result) == 2

    async def test_include_archived(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_tenant(status=TenantStatus.ARCHIVED.value)]
        db.execute = AsyncMock(return_value=mock_result)
        repo = TenantRepository(db)
        result = await repo.list_all(include_archived=True)
        assert len(result) == 1


# ── list_for_user ──


class TestListForUser:
    async def test_admin_sees_all(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_tenant(), _mock_tenant()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = TenantRepository(db)
        result = await repo.list_for_user(is_admin=True)
        assert len(result) == 2

    async def test_user_sees_own_tenant(self):
        db = _mock_db()
        tenant = _mock_tenant(status=TenantStatus.ACTIVE.value)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        db.execute = AsyncMock(return_value=mock_result)
        repo = TenantRepository(db)
        result = await repo.list_for_user(tenant_id="acme", is_admin=False)
        assert len(result) == 1

    async def test_user_archived_tenant_hidden(self):
        db = _mock_db()
        tenant = _mock_tenant(status=TenantStatus.ARCHIVED.value)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        db.execute = AsyncMock(return_value=mock_result)
        repo = TenantRepository(db)
        result = await repo.list_for_user(tenant_id="acme", is_admin=False)
        assert result == []

    async def test_user_no_tenant_id(self):
        db = _mock_db()
        repo = TenantRepository(db)
        result = await repo.list_for_user(is_admin=False)
        assert result == []


# ── update / delete ──


class TestUpdateDelete:
    async def test_update(self):
        db = _mock_db()
        tenant = _mock_tenant()
        repo = TenantRepository(db)
        result = await repo.update(tenant)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(tenant)
        assert result is tenant

    async def test_delete(self):
        db = _mock_db()
        tenant = _mock_tenant()
        repo = TenantRepository(db)
        await repo.delete(tenant)
        db.delete.assert_called_once_with(tenant)
        db.flush.assert_called_once()


# ── count ──


class TestCount:
    async def test_count_active(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3
        db.execute = AsyncMock(return_value=mock_result)
        repo = TenantRepository(db)
        count = await repo.count()
        assert count == 3

    async def test_count_with_archived(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        db.execute = AsyncMock(return_value=mock_result)
        repo = TenantRepository(db)
        count = await repo.count(include_archived=True)
        assert count == 5


# ── get_stats ──


class TestGetStats:
    async def test_stats(self):
        db = _mock_db()
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 4
        status_mocks = [MagicMock() for _ in TenantStatus]
        for i, m in enumerate(status_mocks):
            m.scalar_one.return_value = i + 1
        db.execute = AsyncMock(side_effect=[mock_total, *status_mocks])
        repo = TenantRepository(db)
        stats = await repo.get_stats()
        assert stats["total"] == 4
        assert "by_status" in stats
        assert "active" in stats
