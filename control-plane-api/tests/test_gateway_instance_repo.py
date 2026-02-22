"""Tests for GatewayInstanceRepository (CAB-1388)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.gateway_instance import GatewayInstance, GatewayInstanceStatus, GatewayType
from src.repositories.gateway_instance import GatewayInstanceRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_instance(**kwargs):
    i = MagicMock(spec=GatewayInstance)
    i.id = kwargs.get("id", uuid4())
    i.name = kwargs.get("name", "kong-prod")
    i.gateway_type = kwargs.get("gateway_type", GatewayType.KONG)
    i.environment = kwargs.get("environment", "prod")
    i.tenant_id = kwargs.get("tenant_id", None)
    i.status = kwargs.get("status", GatewayInstanceStatus.ONLINE)
    i.health_details = kwargs.get("health_details", {})
    i.last_health_check = kwargs.get("last_health_check", None)
    i.created_at = kwargs.get("created_at", datetime.utcnow())
    return i


# ── create ──


class TestCreate:
    async def test_create(self):
        db = _mock_db()
        instance = _mock_instance()
        repo = GatewayInstanceRepository(db)
        result = await repo.create(instance)
        db.add.assert_called_once_with(instance)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(instance)
        assert result is instance


# ── get_by_id ──


class TestGetById:
    async def test_found(self):
        db = _mock_db()
        instance = _mock_instance()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = instance
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayInstanceRepository(db)
        result = await repo.get_by_id(instance.id)
        assert result is instance

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayInstanceRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


# ── get_by_name ──


class TestGetByName:
    async def test_found(self):
        db = _mock_db()
        instance = _mock_instance()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = instance
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayInstanceRepository(db)
        result = await repo.get_by_name("kong-prod")
        assert result is instance

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayInstanceRepository(db)
        result = await repo.get_by_name("missing")
        assert result is None


# ── list_all ──


class TestListAll:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 3
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_instance()] * 3
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = GatewayInstanceRepository(db)
        items, total = await repo.list_all()
        assert total == 3

    async def test_with_type_filter(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_instance()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = GatewayInstanceRepository(db)
        items, total = await repo.list_all(gateway_type=GatewayType.KONG)
        assert total == 1

    async def test_with_environment_filter(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_instance()] * 2
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = GatewayInstanceRepository(db)
        items, total = await repo.list_all(environment="prod")
        assert total == 2

    async def test_with_tenant_filter(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_instance(tenant_id="acme")]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = GatewayInstanceRepository(db)
        items, total = await repo.list_all(tenant_id="acme")
        assert total == 1


# ── update ──


class TestUpdate:
    async def test_update(self):
        db = _mock_db()
        instance = _mock_instance()
        repo = GatewayInstanceRepository(db)
        result = await repo.update(instance)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(instance)
        assert result is instance


# ── update_status ──


class TestUpdateStatus:
    async def test_update_status(self):
        db = _mock_db()
        instance = _mock_instance()
        repo = GatewayInstanceRepository(db)
        result = await repo.update_status(
            instance, GatewayInstanceStatus.OFFLINE, health_details={"error": "timeout"}
        )
        assert instance.status == GatewayInstanceStatus.OFFLINE
        assert instance.health_details == {"error": "timeout"}
        db.flush.assert_called_once()

    async def test_update_status_no_details(self):
        db = _mock_db()
        instance = _mock_instance()
        repo = GatewayInstanceRepository(db)
        result = await repo.update_status(instance, GatewayInstanceStatus.ONLINE)
        assert instance.status == GatewayInstanceStatus.ONLINE


# ── delete ──


class TestDelete:
    async def test_delete(self):
        db = _mock_db()
        instance = _mock_instance()
        repo = GatewayInstanceRepository(db)
        await repo.delete(instance)
        db.delete.assert_called_once_with(instance)
        db.flush.assert_called_once()
