"""Tests for PlanRepository (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.plan import Plan, PlanStatus
from src.repositories.plan import PlanRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_plan(**kwargs):
    p = MagicMock(spec=Plan)
    p.id = kwargs.get("id", uuid4())
    p.tenant_id = kwargs.get("tenant_id", "acme")
    p.slug = kwargs.get("slug", "starter")
    p.status = kwargs.get("status", PlanStatus.ACTIVE)
    return p


# ── create ──


class TestCreate:
    async def test_create(self):
        db = _mock_db()
        plan = _mock_plan()
        repo = PlanRepository(db)
        result = await repo.create(plan)
        db.add.assert_called_once_with(plan)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(plan)
        assert result is plan


# ── get_by_id ──


class TestGetById:
    async def test_found(self):
        db = _mock_db()
        plan = _mock_plan()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = plan
        db.execute = AsyncMock(return_value=mock_result)
        repo = PlanRepository(db)
        result = await repo.get_by_id(plan.id)
        assert result is plan

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = PlanRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


# ── get_by_slug ──


class TestGetBySlug:
    async def test_found(self):
        db = _mock_db()
        plan = _mock_plan()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = plan
        db.execute = AsyncMock(return_value=mock_result)
        repo = PlanRepository(db)
        result = await repo.get_by_slug("acme", "starter")
        assert result is plan

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = PlanRepository(db)
        result = await repo.get_by_slug("acme", "enterprise")
        assert result is None


# ── list_by_tenant ──


class TestListByTenant:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_plan(), _mock_plan()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = PlanRepository(db)
        items, total = await repo.list_by_tenant("acme")
        assert total == 2
        assert len(items) == 2

    async def test_with_status_filter(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_plan()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = PlanRepository(db)
        items, total = await repo.list_by_tenant("acme", status=PlanStatus.ACTIVE)
        assert total == 1

    async def test_pagination_page_2(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 10
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_plan()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = PlanRepository(db)
        items, total = await repo.list_by_tenant("acme", page=2, page_size=5)
        assert total == 10


# ── update ──


class TestUpdate:
    async def test_update(self):
        db = _mock_db()
        plan = _mock_plan()
        repo = PlanRepository(db)
        result = await repo.update(plan)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(plan)
        assert result is plan


# ── delete ──


class TestDelete:
    async def test_delete(self):
        db = _mock_db()
        plan = _mock_plan()
        repo = PlanRepository(db)
        await repo.delete(plan)
        db.delete.assert_called_once_with(plan)
        db.flush.assert_called_once()
