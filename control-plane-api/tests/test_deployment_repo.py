"""Tests for DeploymentRepository (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.deployment import Deployment, DeploymentStatus
from src.repositories.deployment import DeploymentRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _mock_deployment(**kwargs):
    d = MagicMock(spec=Deployment)
    d.id = kwargs.get("id", uuid4())
    d.tenant_id = kwargs.get("tenant_id", "acme")
    d.api_id = kwargs.get("api_id", "weather-api")
    d.environment = kwargs.get("environment", "prod")
    d.status = kwargs.get("status", DeploymentStatus.SUCCESS.value)
    return d


# ── create ──


class TestCreate:
    async def test_create(self):
        db = _mock_db()
        deployment = _mock_deployment()
        repo = DeploymentRepository(db)
        result = await repo.create(deployment)
        db.add.assert_called_once_with(deployment)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(deployment)
        assert result is deployment


# ── get_by_id ──


class TestGetById:
    async def test_found(self):
        db = _mock_db()
        dep = _mock_deployment()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dep
        db.execute = AsyncMock(return_value=mock_result)
        repo = DeploymentRepository(db)
        result = await repo.get_by_id(dep.id)
        assert result is dep

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = DeploymentRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


# ── get_by_id_and_tenant ──


class TestGetByIdAndTenant:
    async def test_found(self):
        db = _mock_db()
        dep = _mock_deployment()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dep
        db.execute = AsyncMock(return_value=mock_result)
        repo = DeploymentRepository(db)
        result = await repo.get_by_id_and_tenant(dep.id, "acme")
        assert result is dep

    async def test_wrong_tenant(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = DeploymentRepository(db)
        result = await repo.get_by_id_and_tenant(uuid4(), "other-tenant")
        assert result is None


# ── update ──


class TestUpdate:
    async def test_update(self):
        db = _mock_db()
        dep = _mock_deployment()
        repo = DeploymentRepository(db)
        result = await repo.update(dep)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(dep)
        assert result is dep


# ── list_by_tenant ──


class TestListByTenant:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_deployment(), _mock_deployment()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = DeploymentRepository(db)
        items, total = await repo.list_by_tenant("acme")
        assert total == 2

    async def test_with_api_id(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_deployment()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = DeploymentRepository(db)
        items, total = await repo.list_by_tenant("acme", api_id="weather-api")
        assert total == 1

    async def test_with_environment(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_deployment()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = DeploymentRepository(db)
        items, total = await repo.list_by_tenant("acme", environment="prod")
        assert total == 1

    async def test_with_status(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_deployment()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = DeploymentRepository(db)
        items, total = await repo.list_by_tenant("acme", status="success")
        assert total == 1

    async def test_empty(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 0
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = DeploymentRepository(db)
        items, total = await repo.list_by_tenant("acme")
        assert total == 0


# ── get_latest_success ──


class TestGetLatestSuccess:
    async def test_found(self):
        db = _mock_db()
        dep = _mock_deployment(status=DeploymentStatus.SUCCESS.value)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dep
        db.execute = AsyncMock(return_value=mock_result)
        repo = DeploymentRepository(db)
        result = await repo.get_latest_success("acme", "weather-api", "prod")
        assert result is dep

    async def test_none(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = DeploymentRepository(db)
        result = await repo.get_latest_success("acme", "weather-api", "staging")
        assert result is None


# ── get_environment_summary ──


class TestGetEnvironmentSummary:
    async def test_returns_list(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_deployment(), _mock_deployment()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = DeploymentRepository(db)
        result = await repo.get_environment_summary("acme", "prod")
        assert len(result) == 2

    async def test_empty(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        repo = DeploymentRepository(db)
        result = await repo.get_environment_summary("acme", "staging")
        assert result == []
