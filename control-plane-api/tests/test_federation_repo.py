"""Tests for MasterAccountRepository and SubAccountRepository (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.federation import (
    MasterAccount,
    MasterAccountStatus,
    SubAccount,
    SubAccountStatus,
    SubAccountTool,
)
from src.repositories.federation import MasterAccountRepository, SubAccountRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_master(**kwargs):
    m = MagicMock(spec=MasterAccount)
    m.id = kwargs.get("id", uuid4())
    m.tenant_id = kwargs.get("tenant_id", "acme")
    m.name = kwargs.get("name", "master-01")
    m.status = kwargs.get("status", MasterAccountStatus.ACTIVE)
    return m


def _mock_sub(**kwargs):
    s = MagicMock(spec=SubAccount)
    s.id = kwargs.get("id", uuid4())
    s.master_account_id = kwargs.get("master_account_id", uuid4())
    s.name = kwargs.get("name", "sub-01")
    s.status = kwargs.get("status", SubAccountStatus.ACTIVE)
    s.api_key_prefix = kwargs.get("api_key_prefix", "sk-abc")
    return s


# ── MasterAccountRepository ──


class TestMasterCreate:
    async def test_create(self):
        db = _mock_db()
        master = _mock_master()
        repo = MasterAccountRepository(db)
        result = await repo.create(master)
        db.add.assert_called_once_with(master)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(master)
        assert result is master


class TestMasterGetById:
    async def test_found(self):
        db = _mock_db()
        master = _mock_master()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = master
        db.execute = AsyncMock(return_value=mock_result)
        repo = MasterAccountRepository(db)
        result = await repo.get_by_id(master.id)
        assert result is master

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = MasterAccountRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


class TestMasterGetByTenantAndName:
    async def test_found(self):
        db = _mock_db()
        master = _mock_master()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = master
        db.execute = AsyncMock(return_value=mock_result)
        repo = MasterAccountRepository(db)
        result = await repo.get_by_tenant_and_name("acme", "master-01")
        assert result is master

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = MasterAccountRepository(db)
        result = await repo.get_by_tenant_and_name("acme", "missing")
        assert result is None


class TestMasterListByTenant:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_master(), _mock_master()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = MasterAccountRepository(db)
        items, total = await repo.list_by_tenant("acme")
        assert total == 2
        assert len(items) == 2

    async def test_with_status_filter(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_master(status=MasterAccountStatus.SUSPENDED)]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = MasterAccountRepository(db)
        items, total = await repo.list_by_tenant("acme", status=MasterAccountStatus.SUSPENDED)
        assert total == 1

    async def test_empty(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = MasterAccountRepository(db)
        items, total = await repo.list_by_tenant("acme")
        assert total == 0
        assert items == []


class TestMasterUpdate:
    async def test_update(self):
        db = _mock_db()
        master = _mock_master()
        repo = MasterAccountRepository(db)
        result = await repo.update(master)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(master)
        assert result is master


class TestMasterDelete:
    async def test_delete(self):
        db = _mock_db()
        master = _mock_master()
        repo = MasterAccountRepository(db)
        await repo.delete(master)
        db.delete.assert_called_once_with(master)
        db.flush.assert_called_once()


class TestMasterCountSubAccounts:
    async def test_count(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        db.execute = AsyncMock(return_value=mock_result)
        repo = MasterAccountRepository(db)
        count = await repo.count_sub_accounts(uuid4())
        assert count == 5


# ── SubAccountRepository ──


class TestSubCreate:
    async def test_create(self):
        db = _mock_db()
        sub = _mock_sub()
        repo = SubAccountRepository(db)
        result = await repo.create(sub)
        db.add.assert_called_once_with(sub)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(sub)
        assert result is sub


class TestSubGetById:
    async def test_found(self):
        db = _mock_db()
        sub = _mock_sub()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        db.execute = AsyncMock(return_value=mock_result)
        repo = SubAccountRepository(db)
        result = await repo.get_by_id(sub.id)
        assert result is sub

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = SubAccountRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


class TestSubGetByMasterAndName:
    async def test_found(self):
        db = _mock_db()
        sub = _mock_sub()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        db.execute = AsyncMock(return_value=mock_result)
        repo = SubAccountRepository(db)
        result = await repo.get_by_master_and_name(uuid4(), "sub-01")
        assert result is sub


class TestSubListByMaster:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 3
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_sub()] * 3
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = SubAccountRepository(db)
        items, total = await repo.list_by_master(uuid4())
        assert total == 3
        assert len(items) == 3

    async def test_with_status(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_sub(status=SubAccountStatus.REVOKED)]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = SubAccountRepository(db)
        items, total = await repo.list_by_master(uuid4(), status=SubAccountStatus.REVOKED)
        assert total == 1


class TestSubGetByKeyPrefix:
    async def test_found(self):
        db = _mock_db()
        sub = _mock_sub()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        db.execute = AsyncMock(return_value=mock_result)
        repo = SubAccountRepository(db)
        result = await repo.get_by_key_prefix("sk-abc")
        assert result is sub

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = SubAccountRepository(db)
        result = await repo.get_by_key_prefix("sk-xyz")
        assert result is None


class TestSubUpdate:
    async def test_update(self):
        db = _mock_db()
        sub = _mock_sub()
        repo = SubAccountRepository(db)
        result = await repo.update(sub)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(sub)
        assert result is sub


class TestSubBulkRevoke:
    async def test_bulk_revoke(self):
        db = _mock_db()
        mock_already = MagicMock()
        mock_already.scalar_one.return_value = 1  # 1 already revoked
        mock_stmt = MagicMock()
        mock_stmt.rowcount = 3  # 3 newly revoked
        db.execute = AsyncMock(side_effect=[mock_already, mock_stmt])
        repo = SubAccountRepository(db)
        newly_revoked, already_revoked = await repo.bulk_revoke(uuid4())
        assert newly_revoked == 3
        assert already_revoked == 1


class TestSubToolAllowList:
    async def test_set_tool_allow_list(self):
        db = _mock_db()
        # delete + add items
        db.execute = AsyncMock()
        repo = SubAccountRepository(db)
        sub_id = uuid4()
        result = await repo.set_tool_allow_list(sub_id, ["tool-b", "tool-a", "tool-a"])
        # Deduplication + sort
        assert result == ["tool-a", "tool-b"]
        assert db.execute.called

    async def test_get_tool_allow_list(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["tool-a", "tool-b"]
        db.execute = AsyncMock(return_value=mock_result)
        repo = SubAccountRepository(db)
        tools = await repo.get_tool_allow_list(uuid4())
        assert tools == ["tool-a", "tool-b"]
