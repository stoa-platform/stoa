"""Tests for PortalApplicationRepository (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.portal_application import PortalApplication, PortalAppStatus
from src.repositories.portal_application import PortalApplicationRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_app(**kwargs):
    a = MagicMock(spec=PortalApplication)
    a.id = kwargs.get("id", uuid4())
    a.owner_id = kwargs.get("owner_id", "user-1")
    a.name = kwargs.get("name", "My App")
    a.status = kwargs.get("status", PortalAppStatus.ACTIVE)
    return a


# ── create ──


class TestCreate:
    async def test_create(self):
        db = _mock_db()
        app = _mock_app()
        repo = PortalApplicationRepository(db)
        result = await repo.create(app)
        db.add.assert_called_once_with(app)
        db.flush.assert_called_once()
        assert result is app


# ── get_by_id ──


class TestGetById:
    async def test_found(self):
        db = _mock_db()
        app = _mock_app()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = app
        db.execute = AsyncMock(return_value=mock_result)
        repo = PortalApplicationRepository(db)
        result = await repo.get_by_id(app.id)
        assert result is app

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = PortalApplicationRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


# ── get_by_owner_and_name ──


class TestGetByOwnerAndName:
    async def test_found(self):
        db = _mock_db()
        app = _mock_app()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = app
        db.execute = AsyncMock(return_value=mock_result)
        repo = PortalApplicationRepository(db)
        result = await repo.get_by_owner_and_name("user-1", "My App")
        assert result is app

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = PortalApplicationRepository(db)
        result = await repo.get_by_owner_and_name("user-1", "Missing")
        assert result is None


# ── list_by_owner ──


class TestListByOwner:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_app(), _mock_app()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = PortalApplicationRepository(db)
        items, total = await repo.list_by_owner("user-1")
        assert total == 2
        assert len(items) == 2

    async def test_with_status(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_app()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = PortalApplicationRepository(db)
        items, total = await repo.list_by_owner("user-1", status=PortalAppStatus.ACTIVE)
        assert total == 1

    async def test_empty(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 0
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = PortalApplicationRepository(db)
        items, total = await repo.list_by_owner("user-2")
        assert total == 0
        assert items == []


# ── update / delete ──


class TestUpdateDelete:
    async def test_update(self):
        db = _mock_db()
        app = _mock_app()
        repo = PortalApplicationRepository(db)
        result = await repo.update(app)
        db.flush.assert_called_once()
        assert result is app

    async def test_delete(self):
        db = _mock_db()
        app = _mock_app()
        repo = PortalApplicationRepository(db)
        await repo.delete(app)
        db.delete.assert_called_once_with(app)
        db.flush.assert_called_once()


# ── delete_all_by_owner ──


class TestDeleteAllByOwner:
    async def test_deletes_all(self):
        db = _mock_db()
        apps = [_mock_app(owner_id="user-1") for _ in range(3)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = apps
        db.execute = AsyncMock(return_value=mock_result)
        repo = PortalApplicationRepository(db)
        count = await repo.delete_all_by_owner("user-1")
        assert count == 3
        assert db.delete.call_count == 3

    async def test_no_apps(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        repo = PortalApplicationRepository(db)
        count = await repo.delete_all_by_owner("user-1")
        assert count == 0
