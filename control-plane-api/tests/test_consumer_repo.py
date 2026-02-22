"""Tests for ConsumerRepository (CAB-1388)."""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.consumer import CertificateStatus, Consumer, ConsumerStatus
from src.repositories.consumer import ConsumerRepository, escape_like


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_consumer(**kwargs):
    c = MagicMock(spec=Consumer)
    c.id = kwargs.get("id", uuid4())
    c.tenant_id = kwargs.get("tenant_id", "acme")
    c.name = kwargs.get("name", "Test Consumer")
    c.email = kwargs.get("email", "consumer@acme.com")
    c.external_id = kwargs.get("external_id", "ext-001")
    c.company = kwargs.get("company", "Acme Corp")
    c.status = kwargs.get("status", ConsumerStatus.ACTIVE)
    c.certificate_fingerprint = kwargs.get("certificate_fingerprint", None)
    c.certificate_fingerprint_previous = kwargs.get("certificate_fingerprint_previous", None)
    c.certificate_status = kwargs.get("certificate_status", CertificateStatus.ACTIVE)
    c.certificate_not_after = kwargs.get("certificate_not_after", None)
    c.updated_at = kwargs.get("updated_at", datetime.utcnow())
    c.created_at = kwargs.get("created_at", datetime.utcnow())
    return c


# ── escape_like ──


class TestEscapeLike:
    def test_no_special(self):
        assert escape_like("hello") == "hello"

    def test_percent(self):
        assert escape_like("50%") == "50\\%"

    def test_underscore(self):
        assert escape_like("a_b") == "a\\_b"

    def test_backslash(self):
        assert escape_like("a\\b") == "a\\\\b"

    def test_all_specials(self):
        assert escape_like("%_\\") == "\\%\\_\\\\"


# ── create ──


class TestCreate:
    async def test_create_returns_consumer(self):
        db = _mock_db()
        consumer = _mock_consumer()
        db.refresh = AsyncMock(side_effect=lambda c: c)
        repo = ConsumerRepository(db)
        result = await repo.create(consumer)
        db.add.assert_called_once_with(consumer)
        assert result is consumer


# ── get_by_id ──


class TestGetById:
    async def test_found(self):
        db = _mock_db()
        consumer = _mock_consumer()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = consumer
        db.execute = AsyncMock(return_value=mock_result)
        repo = ConsumerRepository(db)
        result = await repo.get_by_id(consumer.id)
        assert result is consumer

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = ConsumerRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


# ── get_by_external_id ──


class TestGetByExternalId:
    async def test_found(self):
        db = _mock_db()
        consumer = _mock_consumer()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = consumer
        db.execute = AsyncMock(return_value=mock_result)
        repo = ConsumerRepository(db)
        result = await repo.get_by_external_id("acme", "ext-001")
        assert result is consumer

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = ConsumerRepository(db)
        result = await repo.get_by_external_id("acme", "missing")
        assert result is None


# ── get_by_fingerprint ──


class TestGetByFingerprint:
    async def test_found_current(self):
        db = _mock_db()
        consumer = _mock_consumer(certificate_fingerprint="fp1")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = consumer
        db.execute = AsyncMock(return_value=mock_result)
        repo = ConsumerRepository(db)
        result = await repo.get_by_fingerprint("acme", "fp1")
        assert result is consumer

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = ConsumerRepository(db)
        result = await repo.get_by_fingerprint("acme", "missing")
        assert result is None


# ── list_by_tenant ──


class TestListByTenant:
    async def test_basic_list(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_consumer(), _mock_consumer()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ConsumerRepository(db)
        items, total = await repo.list_by_tenant("acme")
        assert total == 2
        assert len(items) == 2

    async def test_with_status_filter(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_consumer()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ConsumerRepository(db)
        items, total = await repo.list_by_tenant("acme", status=ConsumerStatus.ACTIVE)
        assert total == 1

    async def test_with_search(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_consumer()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ConsumerRepository(db)
        items, total = await repo.list_by_tenant("acme", search="Test")
        assert total == 1

    async def test_whitespace_search_ignored(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ConsumerRepository(db)
        items, total = await repo.list_by_tenant("acme", search="   ")
        assert total == 0

    async def test_pagination(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 5
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_consumer()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = ConsumerRepository(db)
        items, total = await repo.list_by_tenant("acme", page=2, page_size=2)
        assert total == 5


# ── update / update_status ──


class TestUpdate:
    async def test_update(self):
        db = _mock_db()
        consumer = _mock_consumer()
        repo = ConsumerRepository(db)
        result = await repo.update(consumer)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(consumer)

    async def test_update_status(self):
        db = _mock_db()
        consumer = _mock_consumer()
        repo = ConsumerRepository(db)
        result = await repo.update_status(consumer, ConsumerStatus.SUSPENDED)
        assert consumer.status == ConsumerStatus.SUSPENDED
        db.flush.assert_called_once()


# ── delete ──


class TestDelete:
    async def test_delete(self):
        db = _mock_db()
        consumer = _mock_consumer()
        repo = ConsumerRepository(db)
        await repo.delete(consumer)
        db.delete.assert_called_once_with(consumer)
        db.flush.assert_called_once()


# ── list_expiring ──


class TestListExpiring:
    async def test_returns_expiring(self):
        db = _mock_db()
        mock_result = MagicMock()
        expiring = _mock_consumer(
            certificate_not_after=datetime.now(UTC) + timedelta(days=10),
            certificate_status=CertificateStatus.ACTIVE,
        )
        mock_result.scalars.return_value.all.return_value = [expiring]
        db.execute = AsyncMock(return_value=mock_result)
        repo = ConsumerRepository(db)
        result = await repo.list_expiring("acme", days=30)
        assert len(result) == 1

    async def test_empty(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        repo = ConsumerRepository(db)
        result = await repo.list_expiring("acme")
        assert result == []


# ── expire_overdue_certificates ──


class TestExpireOverdueCertificates:
    async def test_marks_expired(self):
        db = _mock_db()
        mock_result = MagicMock()
        consumer = _mock_consumer(
            certificate_not_after=datetime.now(UTC) - timedelta(days=1),
            certificate_status=CertificateStatus.ACTIVE,
        )
        mock_result.scalars.return_value.all.return_value = [consumer]
        db.execute = AsyncMock(return_value=mock_result)
        repo = ConsumerRepository(db)
        count = await repo.expire_overdue_certificates("acme")
        assert count == 1
        assert consumer.certificate_status == CertificateStatus.EXPIRED

    async def test_no_overdue(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        repo = ConsumerRepository(db)
        count = await repo.expire_overdue_certificates("acme")
        assert count == 0


# ── get_stats ──


class TestGetStats:
    async def test_stats_all_tenants(self):
        db = _mock_db()
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 5
        status_results = [MagicMock() for _ in ConsumerStatus]
        for i, r in enumerate(status_results):
            r.scalar_one.return_value = i
        db.execute = AsyncMock(side_effect=[mock_total, *status_results])
        repo = ConsumerRepository(db)
        stats = await repo.get_stats()
        assert stats["total"] == 5
        assert "by_status" in stats

    async def test_stats_with_tenant_id(self):
        db = _mock_db()
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 3
        status_results = [MagicMock() for _ in ConsumerStatus]
        for r in status_results:
            r.scalar_one.return_value = 1
        db.execute = AsyncMock(side_effect=[mock_total, *status_results])
        repo = ConsumerRepository(db)
        stats = await repo.get_stats(tenant_id="acme")
        assert stats["total"] == 3
