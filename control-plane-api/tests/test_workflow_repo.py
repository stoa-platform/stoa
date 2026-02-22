"""Tests for WorkflowRepository (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.workflow import WorkflowAuditLog, WorkflowInstance, WorkflowStepResult, WorkflowTemplate
from src.repositories.workflow import WorkflowRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_template(**kwargs):
    t = MagicMock(spec=WorkflowTemplate)
    t.id = kwargs.get("id", uuid4())
    t.tenant_id = kwargs.get("tenant_id", "acme")
    t.workflow_type = kwargs.get("workflow_type", "onboarding")
    t.is_active = kwargs.get("is_active", "true")
    return t


def _mock_instance(**kwargs):
    i = MagicMock(spec=WorkflowInstance)
    i.id = kwargs.get("id", uuid4())
    i.tenant_id = kwargs.get("tenant_id", "acme")
    i.workflow_type = kwargs.get("workflow_type", "onboarding")
    i.status = kwargs.get("status", "running")
    return i


def _mock_step_result(**kwargs):
    s = MagicMock(spec=WorkflowStepResult)
    s.id = kwargs.get("id", uuid4())
    s.instance_id = kwargs.get("instance_id", uuid4())
    s.step_index = kwargs.get("step_index", 0)
    return s


def _mock_audit_log(**kwargs):
    a = MagicMock(spec=WorkflowAuditLog)
    a.id = kwargs.get("id", uuid4())
    a.instance_id = kwargs.get("instance_id", uuid4())
    return a


# ── Template CRUD ──


class TestTemplates:
    async def test_create_template(self):
        db = _mock_db()
        t = _mock_template()
        repo = WorkflowRepository(db)
        result = await repo.create_template(t)
        db.add.assert_called_once_with(t)
        assert result is t

    async def test_get_template_by_id_found(self):
        db = _mock_db()
        t = _mock_template()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = t
        db.execute = AsyncMock(return_value=mock_result)
        repo = WorkflowRepository(db)
        result = await repo.get_template_by_id(t.id)
        assert result is t

    async def test_get_template_by_id_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = WorkflowRepository(db)
        result = await repo.get_template_by_id(uuid4())
        assert result is None

    async def test_get_template_by_id_and_tenant(self):
        db = _mock_db()
        t = _mock_template()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = t
        db.execute = AsyncMock(return_value=mock_result)
        repo = WorkflowRepository(db)
        result = await repo.get_template_by_id_and_tenant(t.id, "acme")
        assert result is t

    async def test_get_active_template(self):
        db = _mock_db()
        t = _mock_template(is_active="true")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = t
        db.execute = AsyncMock(return_value=mock_result)
        repo = WorkflowRepository(db)
        result = await repo.get_active_template("acme", "onboarding")
        assert result is t

    async def test_get_active_template_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = WorkflowRepository(db)
        result = await repo.get_active_template("acme", "offboarding")
        assert result is None

    async def test_update_template(self):
        db = _mock_db()
        t = _mock_template()
        repo = WorkflowRepository(db)
        result = await repo.update_template(t)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(t)
        assert result is t

    async def test_delete_template(self):
        db = _mock_db()
        t = _mock_template()
        repo = WorkflowRepository(db)
        await repo.delete_template(t)
        db.delete.assert_called_once_with(t)
        db.flush.assert_called_once()

    async def test_list_templates_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_template(), _mock_template()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = WorkflowRepository(db)
        items, total = await repo.list_templates("acme")
        assert total == 2

    async def test_list_templates_with_type(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_template()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = WorkflowRepository(db)
        items, total = await repo.list_templates("acme", workflow_type="onboarding")
        assert total == 1


# ── Instance CRUD ──


class TestInstances:
    async def test_create_instance(self):
        db = _mock_db()
        instance = _mock_instance()
        repo = WorkflowRepository(db)
        result = await repo.create_instance(instance)
        db.add.assert_called_once_with(instance)
        assert result is instance

    async def test_get_instance_by_id(self):
        db = _mock_db()
        instance = _mock_instance()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = instance
        db.execute = AsyncMock(return_value=mock_result)
        repo = WorkflowRepository(db)
        result = await repo.get_instance_by_id(instance.id)
        assert result is instance

    async def test_get_instance_by_id_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = WorkflowRepository(db)
        result = await repo.get_instance_by_id(uuid4())
        assert result is None

    async def test_get_instance_by_id_and_tenant(self):
        db = _mock_db()
        instance = _mock_instance()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = instance
        db.execute = AsyncMock(return_value=mock_result)
        repo = WorkflowRepository(db)
        result = await repo.get_instance_by_id_and_tenant(instance.id, "acme")
        assert result is instance

    async def test_update_instance(self):
        db = _mock_db()
        instance = _mock_instance()
        repo = WorkflowRepository(db)
        result = await repo.update_instance(instance)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(instance)
        assert result is instance

    async def test_list_instances(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_instance()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = WorkflowRepository(db)
        items, total = await repo.list_instances("acme")
        assert total == 1

    async def test_list_instances_with_filters(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_instance(status="completed")]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = WorkflowRepository(db)
        items, total = await repo.list_instances("acme", workflow_type="onboarding", status="completed")
        assert total == 1


# ── Step Results ──


class TestStepResults:
    async def test_create_step_result(self):
        db = _mock_db()
        step = _mock_step_result()
        repo = WorkflowRepository(db)
        result = await repo.create_step_result(step)
        db.add.assert_called_once_with(step)
        assert result is step

    async def test_get_step_results(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_step_result(), _mock_step_result()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = WorkflowRepository(db)
        results = await repo.get_step_results(uuid4())
        assert len(results) == 2


# ── Audit Logs ──


class TestAuditLogs:
    async def test_create_audit_log(self):
        db = _mock_db()
        log = _mock_audit_log()
        repo = WorkflowRepository(db)
        result = await repo.create_audit_log(log)
        db.add.assert_called_once_with(log)
        assert result is log

    async def test_list_audit_logs(self):
        db = _mock_db()
        instance_id = uuid4()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [
            _mock_audit_log(instance_id=instance_id),
            _mock_audit_log(instance_id=instance_id),
        ]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = WorkflowRepository(db)
        items, total = await repo.list_audit_logs(instance_id)
        assert total == 2
        assert len(items) == 2

    async def test_list_audit_logs_empty(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar.return_value = 0
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = WorkflowRepository(db)
        items, total = await repo.list_audit_logs(uuid4())
        assert total == 0
        assert items == []
