"""Tests for ExecutionLogRepository (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.execution_log import ErrorCategory, ExecutionLog, ExecutionStatus
from src.repositories.execution_log import ExecutionLogRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _mock_log(**kwargs):
    log = MagicMock(spec=ExecutionLog)
    log.id = kwargs.get("id", "log-001")
    log.tenant_id = kwargs.get("tenant_id", "acme")
    log.consumer_id = kwargs.get("consumer_id", "consumer-1")
    log.api_id = kwargs.get("api_id", "weather-api")
    log.status = kwargs.get("status", ExecutionStatus.SUCCESS)
    log.error_category = kwargs.get("error_category", None)
    log.duration_ms = kwargs.get("duration_ms", 120.5)
    return log


# ── get_by_id ──


class TestGetById:
    async def test_found(self):
        db = _mock_db()
        log = _mock_log()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = log
        db.execute = AsyncMock(return_value=mock_result)
        repo = ExecutionLogRepository(db)
        result = await repo.get_by_id("log-001")
        assert result is log

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = ExecutionLogRepository(db)
        result = await repo.get_by_id("missing")
        assert result is None


# ── list_by_tenant ──


class TestListByTenant:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 3
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_log()] * 3
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ExecutionLogRepository(db)
        items, total = await repo.list_by_tenant("acme")
        assert total == 3
        assert len(items) == 3

    async def test_with_status(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_log(status=ExecutionStatus.ERROR)]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ExecutionLogRepository(db)
        items, total = await repo.list_by_tenant("acme", status=ExecutionStatus.ERROR)
        assert total == 1

    async def test_with_error_category(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_log(error_category=ErrorCategory.AUTH)]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ExecutionLogRepository(db)
        items, total = await repo.list_by_tenant("acme", error_category=ErrorCategory.AUTH)
        assert total == 1

    async def test_with_consumer_id(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_log()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ExecutionLogRepository(db)
        items, total = await repo.list_by_tenant("acme", consumer_id="consumer-1")
        assert total == 1

    async def test_with_api_id(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_log()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ExecutionLogRepository(db)
        items, total = await repo.list_by_tenant("acme", api_id="weather-api")
        assert total == 1

    async def test_empty(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ExecutionLogRepository(db)
        items, total = await repo.list_by_tenant("acme")
        assert total == 0
        assert items == []


# ── list_by_consumer ──


class TestListByConsumer:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_log(), _mock_log()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ExecutionLogRepository(db)
        items, total = await repo.list_by_consumer("consumer-1")
        assert total == 2

    async def test_with_status(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_log(status=ExecutionStatus.SUCCESS)]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ExecutionLogRepository(db)
        items, total = await repo.list_by_consumer("consumer-1", status=ExecutionStatus.SUCCESS)
        assert total == 1


# ── get_taxonomy ──


class TestGetTaxonomy:
    async def test_with_errors(self):
        db = _mock_db()
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 100

        # Mock taxonomy rows
        row1 = MagicMock()
        row1.error_category = ErrorCategory.AUTH
        row1.count = 30
        row1.avg_duration_ms = 500.0

        row2 = MagicMock()
        row2.error_category = ErrorCategory.TIMEOUT
        row2.count = 20
        row2.avg_duration_ms = 2000.0

        mock_taxonomy = MagicMock()
        mock_taxonomy.all.return_value = [row1, row2]

        db.execute = AsyncMock(side_effect=[mock_total, mock_taxonomy])
        repo = ExecutionLogRepository(db)
        items, total_errors, total_exec = await repo.get_taxonomy("acme")
        assert total_exec == 100
        assert total_errors == 50
        assert len(items) == 2
        assert items[0]["category"] == ErrorCategory.AUTH.value
        assert items[0]["percentage"] == 60.0

    async def test_no_errors(self):
        db = _mock_db()
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 50

        mock_taxonomy = MagicMock()
        mock_taxonomy.all.return_value = []

        db.execute = AsyncMock(side_effect=[mock_total, mock_taxonomy])
        repo = ExecutionLogRepository(db)
        items, total_errors, total_exec = await repo.get_taxonomy("acme")
        assert total_exec == 50
        assert total_errors == 0
        assert items == []

    async def test_with_consumer_filter(self):
        db = _mock_db()
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 10

        row = MagicMock()
        row.error_category = ErrorCategory.AUTH
        row.count = 3
        row.avg_duration_ms = 100.0

        mock_taxonomy = MagicMock()
        mock_taxonomy.all.return_value = [row]

        db.execute = AsyncMock(side_effect=[mock_total, mock_taxonomy])
        repo = ExecutionLogRepository(db)
        items, total_errors, total_exec = await repo.get_taxonomy("acme", consumer_id="consumer-1")
        assert total_exec == 10
        assert total_errors == 3
