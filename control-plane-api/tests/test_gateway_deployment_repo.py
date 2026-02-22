"""Tests for GatewayDeploymentRepository (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.repositories.gateway_deployment import GatewayDeploymentRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_gd(**kwargs):
    d = MagicMock(spec=GatewayDeployment)
    d.id = kwargs.get("id", uuid4())
    d.api_catalog_id = kwargs.get("api_catalog_id", uuid4())
    d.gateway_instance_id = kwargs.get("gateway_instance_id", uuid4())
    d.sync_status = kwargs.get("sync_status", DeploymentSyncStatus.SYNCED)
    return d


# ── create ──


class TestCreate:
    async def test_create(self):
        db = _mock_db()
        gd = _mock_gd()
        repo = GatewayDeploymentRepository(db)
        result = await repo.create(gd)
        db.add.assert_called_once_with(gd)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(gd)
        assert result is gd


# ── get_by_id ──


class TestGetById:
    async def test_found(self):
        db = _mock_db()
        gd = _mock_gd()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = gd
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayDeploymentRepository(db)
        result = await repo.get_by_id(gd.id)
        assert result is gd

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayDeploymentRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


# ── get_by_api_and_gateway ──


class TestGetByApiAndGateway:
    async def test_found(self):
        db = _mock_db()
        gd = _mock_gd()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = gd
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayDeploymentRepository(db)
        result = await repo.get_by_api_and_gateway(gd.api_catalog_id, gd.gateway_instance_id)
        assert result is gd

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayDeploymentRepository(db)
        result = await repo.get_by_api_and_gateway(uuid4(), uuid4())
        assert result is None


# ── list_by_api ──


class TestListByApi:
    async def test_returns_list(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_gd(), _mock_gd()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayDeploymentRepository(db)
        result = await repo.list_by_api(uuid4())
        assert len(result) == 2

    async def test_empty(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayDeploymentRepository(db)
        result = await repo.list_by_api(uuid4())
        assert result == []


# ── list_by_gateway ──


class TestListByGateway:
    async def test_all_statuses(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_gd()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayDeploymentRepository(db)
        result = await repo.list_by_gateway(uuid4())
        assert len(result) == 1

    async def test_with_sync_status(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_gd(sync_status=DeploymentSyncStatus.PENDING)]
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayDeploymentRepository(db)
        result = await repo.list_by_gateway(uuid4(), sync_status=DeploymentSyncStatus.PENDING)
        assert len(result) == 1


# ── list_all ──


class TestListAll:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_gd(), _mock_gd()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = GatewayDeploymentRepository(db)
        items, total = await repo.list_all()
        assert total == 2

    async def test_with_sync_status_filter(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_gd()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = GatewayDeploymentRepository(db)
        items, total = await repo.list_all(sync_status=DeploymentSyncStatus.SYNCED)
        assert total == 1


# ── list_by_statuses ──


class TestListByStatuses:
    async def test_returns_matching(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_gd(), _mock_gd()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayDeploymentRepository(db)
        result = await repo.list_by_statuses([DeploymentSyncStatus.PENDING, DeploymentSyncStatus.DRIFTED])
        assert len(result) == 2


# ── list_pending_sync / list_synced ──


class TestListPendingAndSynced:
    async def test_list_pending_sync(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_gd(sync_status=DeploymentSyncStatus.PENDING)]
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayDeploymentRepository(db)
        result = await repo.list_pending_sync()
        assert len(result) == 1

    async def test_list_synced(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_gd(sync_status=DeploymentSyncStatus.SYNCED)]
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayDeploymentRepository(db)
        result = await repo.list_synced()
        assert len(result) == 1


# ── get_status_summary ──


class TestGetStatusSummary:
    async def test_returns_all_statuses(self):
        db = _mock_db()
        status_mocks = [MagicMock() for _ in DeploymentSyncStatus]
        for i, m in enumerate(status_mocks):
            m.scalar_one.return_value = i
        db.execute = AsyncMock(side_effect=status_mocks)
        repo = GatewayDeploymentRepository(db)
        summary = await repo.get_status_summary()
        assert len(summary) == len(DeploymentSyncStatus)


# ── update / delete ──


class TestUpdateDelete:
    async def test_update(self):
        db = _mock_db()
        gd = _mock_gd()
        repo = GatewayDeploymentRepository(db)
        result = await repo.update(gd)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(gd)
        assert result is gd

    async def test_delete(self):
        db = _mock_db()
        gd = _mock_gd()
        repo = GatewayDeploymentRepository(db)
        await repo.delete(gd)
        db.delete.assert_called_once_with(gd)
        db.flush.assert_called_once()
