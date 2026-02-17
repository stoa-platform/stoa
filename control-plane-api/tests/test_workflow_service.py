"""Tests for workflow service state machine (CAB-593)"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.models.workflow import (
    WorkflowInstance,
    WorkflowMode,
    WorkflowStatus,
    WorkflowTemplate,
    WorkflowType,
)
from src.services.workflow_service import WorkflowService


def _make_template(
    mode: str = WorkflowMode.AUTO.value,
    auto_provision: str = "true",
    approval_steps: list | None = None,
) -> WorkflowTemplate:
    t = WorkflowTemplate()
    t.id = uuid.uuid4()
    t.tenant_id = "tenant-1"
    t.workflow_type = WorkflowType.USER_REGISTRATION.value
    t.name = "Test Template"
    t.mode = mode
    t.approval_steps = approval_steps or []
    t.auto_provision = auto_provision
    t.notification_config = {}
    t.sector = None
    t.is_active = "true"
    t.created_at = datetime.utcnow()
    t.updated_at = datetime.utcnow()
    t.created_by = "admin"
    return t


def _make_instance(template: WorkflowTemplate, status: str = WorkflowStatus.PENDING.value) -> WorkflowInstance:
    inst = WorkflowInstance()
    inst.id = uuid.uuid4()
    inst.template_id = template.id
    inst.tenant_id = template.tenant_id
    inst.workflow_type = template.workflow_type
    inst.subject_id = "user-123"
    inst.subject_email = "user@example.com"
    inst.status = status
    inst.current_step_index = 0
    inst.context = {}
    inst.initiated_by = "admin"
    inst.completed_at = None
    inst.created_at = datetime.utcnow()
    inst.updated_at = datetime.utcnow()
    return inst


@pytest.fixture()
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture()
def mock_provisioner():
    provisioner = AsyncMock()
    provisioner.provision = AsyncMock(return_value=True)
    return provisioner


@pytest.fixture()
def service(mock_db, mock_provisioner):
    svc = WorkflowService(mock_db, provisioner=mock_provisioner)
    svc.repo = AsyncMock()
    return svc


class TestAutoMode:
    @pytest.mark.asyncio()
    async def test_auto_mode_completes_immediately(self, service, mock_provisioner):
        template = _make_template(mode=WorkflowMode.AUTO.value, auto_provision="true")
        instance = _make_instance(template)

        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)
        service.repo.get_template_by_id = AsyncMock(return_value=template)
        service.repo.create_instance = AsyncMock(return_value=instance)
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            result = await service.start_workflow(
                tenant_id="tenant-1",
                template_id=template.id,
                subject_id="user-123",
                user_id="admin",
            )

        assert result.status == WorkflowStatus.COMPLETED.value
        mock_provisioner.provision.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_auto_mode_no_provision(self, service, mock_provisioner):
        template = _make_template(mode=WorkflowMode.AUTO.value, auto_provision="false")
        instance = _make_instance(template)

        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)
        service.repo.create_instance = AsyncMock(return_value=instance)
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            result = await service.start_workflow(
                tenant_id="tenant-1",
                template_id=template.id,
                subject_id="user-123",
                user_id="admin",
            )

        assert result.status == WorkflowStatus.APPROVED.value
        mock_provisioner.provision.assert_not_awaited()


class TestManualMode:
    @pytest.mark.asyncio()
    async def test_manual_mode_goes_to_in_progress(self, service):
        template = _make_template(mode=WorkflowMode.MANUAL.value)
        instance = _make_instance(template)

        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)
        service.repo.create_instance = AsyncMock(return_value=instance)
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            result = await service.start_workflow(
                tenant_id="tenant-1",
                template_id=template.id,
                subject_id="user-123",
                user_id="admin",
            )

        assert result.status == WorkflowStatus.IN_PROGRESS.value

    @pytest.mark.asyncio()
    async def test_manual_approve_completes(self, service, mock_provisioner):
        template = _make_template(mode=WorkflowMode.MANUAL.value, auto_provision="true")
        instance = _make_instance(template, status=WorkflowStatus.IN_PROGRESS.value)

        service.repo.get_instance_by_id_and_tenant = AsyncMock(return_value=instance)
        service.repo.get_template_by_id = AsyncMock(return_value=template)
        service.repo.create_step_result = AsyncMock()
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            result = await service.approve_step(
                tenant_id="tenant-1",
                instance_id=instance.id,
                approver_id="admin",
            )

        assert result.status == WorkflowStatus.COMPLETED.value
        mock_provisioner.provision.assert_awaited_once()


class TestApprovalChainMode:
    @pytest.mark.asyncio()
    async def test_chain_advances_steps(self, service):
        steps = [
            {"step_index": 0, "role": "tenant-admin", "label": "Manager Review"},
            {"step_index": 1, "role": "cpi-admin", "label": "Platform Review"},
        ]
        template = _make_template(mode=WorkflowMode.APPROVAL_CHAIN.value, approval_steps=steps)
        instance = _make_instance(template, status=WorkflowStatus.IN_PROGRESS.value)

        service.repo.get_instance_by_id_and_tenant = AsyncMock(return_value=instance)
        service.repo.get_template_by_id = AsyncMock(return_value=template)
        service.repo.create_step_result = AsyncMock()
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            result = await service.approve_step(
                tenant_id="tenant-1",
                instance_id=instance.id,
                approver_id="admin",
            )

        assert result.current_step_index == 1
        assert result.status == WorkflowStatus.IN_PROGRESS.value

    @pytest.mark.asyncio()
    async def test_chain_last_step_completes(self, service, mock_provisioner):
        steps = [{"step_index": 0, "role": "tenant-admin", "label": "Review"}]
        template = _make_template(
            mode=WorkflowMode.APPROVAL_CHAIN.value,
            approval_steps=steps,
            auto_provision="true",
        )
        instance = _make_instance(template, status=WorkflowStatus.IN_PROGRESS.value)

        service.repo.get_instance_by_id_and_tenant = AsyncMock(return_value=instance)
        service.repo.get_template_by_id = AsyncMock(return_value=template)
        service.repo.create_step_result = AsyncMock()
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            result = await service.approve_step(
                tenant_id="tenant-1",
                instance_id=instance.id,
                approver_id="admin",
            )

        assert result.status == WorkflowStatus.COMPLETED.value
        mock_provisioner.provision.assert_awaited_once()


class TestRejection:
    @pytest.mark.asyncio()
    async def test_reject_sets_rejected(self, service):
        template = _make_template(mode=WorkflowMode.MANUAL.value)
        instance = _make_instance(template, status=WorkflowStatus.IN_PROGRESS.value)

        service.repo.get_instance_by_id_and_tenant = AsyncMock(return_value=instance)
        service.repo.create_step_result = AsyncMock()
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            result = await service.reject_step(
                tenant_id="tenant-1",
                instance_id=instance.id,
                approver_id="admin",
                comment="Not eligible",
            )

        assert result.status == WorkflowStatus.REJECTED.value

    @pytest.mark.asyncio()
    async def test_reject_non_in_progress_fails(self, service):
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.APPROVED.value)

        service.repo.get_instance_by_id_and_tenant = AsyncMock(return_value=instance)

        with pytest.raises(ValueError, match="Cannot reject"):
            await service.reject_step(
                tenant_id="tenant-1",
                instance_id=instance.id,
                approver_id="admin",
            )


class TestProvisioningFailure:
    @pytest.mark.asyncio()
    async def test_provisioning_failure_sets_failed(self, service, mock_provisioner):
        mock_provisioner.provision = AsyncMock(return_value=False)

        template = _make_template(mode=WorkflowMode.AUTO.value, auto_provision="true")
        instance = _make_instance(template)

        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)
        service.repo.get_template_by_id = AsyncMock(return_value=template)
        service.repo.create_instance = AsyncMock(return_value=instance)
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            result = await service.start_workflow(
                tenant_id="tenant-1",
                template_id=template.id,
                subject_id="user-123",
                user_id="admin",
            )

        assert result.status == WorkflowStatus.FAILED.value

    @pytest.mark.asyncio()
    async def test_provisioning_exception_sets_failed(self, service, mock_provisioner):
        mock_provisioner.provision = AsyncMock(side_effect=RuntimeError("KC unavailable"))

        template = _make_template(mode=WorkflowMode.AUTO.value, auto_provision="true")
        instance = _make_instance(template)

        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)
        service.repo.get_template_by_id = AsyncMock(return_value=template)
        service.repo.create_instance = AsyncMock(return_value=instance)
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            result = await service.start_workflow(
                tenant_id="tenant-1",
                template_id=template.id,
                subject_id="user-123",
                user_id="admin",
            )

        assert result.status == WorkflowStatus.FAILED.value


class TestTemplateNotFound:
    @pytest.mark.asyncio()
    async def test_start_with_missing_template_fails(self, service):
        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await service.start_workflow(
                tenant_id="tenant-1",
                template_id=uuid.uuid4(),
                subject_id="user-123",
                user_id="admin",
            )


class TestApproveValidation:
    @pytest.mark.asyncio()
    async def test_approve_pending_instance_fails(self, service):
        """Cannot approve an instance that is still in PENDING (not yet started)."""
        template = _make_template(mode=WorkflowMode.MANUAL.value)
        instance = _make_instance(template, status=WorkflowStatus.PENDING.value)

        service.repo.get_instance_by_id_and_tenant = AsyncMock(return_value=instance)

        with pytest.raises(ValueError, match="Cannot approve"):
            await service.approve_step(
                tenant_id="tenant-1",
                instance_id=instance.id,
                approver_id="admin",
            )

    @pytest.mark.asyncio()
    async def test_approve_completed_instance_fails(self, service):
        """Cannot approve an already completed instance."""
        template = _make_template(mode=WorkflowMode.MANUAL.value)
        instance = _make_instance(template, status=WorkflowStatus.COMPLETED.value)

        service.repo.get_instance_by_id_and_tenant = AsyncMock(return_value=instance)

        with pytest.raises(ValueError, match="Cannot approve"):
            await service.approve_step(
                tenant_id="tenant-1",
                instance_id=instance.id,
                approver_id="admin",
            )


class TestInactiveTemplate:
    @pytest.mark.asyncio()
    async def test_start_with_inactive_template_fails(self, service):
        """Cannot start a workflow from a deactivated template."""
        template = _make_template(mode=WorkflowMode.AUTO.value)
        template.is_active = "false"

        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)

        with pytest.raises(ValueError, match="not active"):
            await service.start_workflow(
                tenant_id="tenant-1",
                template_id=template.id,
                subject_id="user-123",
                user_id="admin",
            )


class TestAuditTrail:
    @pytest.mark.asyncio()
    async def test_auto_mode_creates_audit_entries(self, service, mock_provisioner):
        """Auto mode should create at least 2 audit log entries (created + completed)."""
        template = _make_template(mode=WorkflowMode.AUTO.value, auto_provision="true")
        instance = _make_instance(template)

        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)
        service.repo.get_template_by_id = AsyncMock(return_value=template)
        service.repo.create_instance = AsyncMock(return_value=instance)
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            await service.start_workflow(
                tenant_id="tenant-1",
                template_id=template.id,
                subject_id="user-123",
                user_id="admin",
            )

        assert service.repo.create_audit_log.await_count >= 2

    @pytest.mark.asyncio()
    async def test_rejection_creates_audit_entry(self, service):
        """Rejecting an instance should create an audit log entry."""
        template = _make_template(mode=WorkflowMode.MANUAL.value)
        instance = _make_instance(template, status=WorkflowStatus.IN_PROGRESS.value)

        service.repo.get_instance_by_id_and_tenant = AsyncMock(return_value=instance)
        service.repo.create_step_result = AsyncMock()
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            await service.reject_step(
                tenant_id="tenant-1",
                instance_id=instance.id,
                approver_id="admin",
                comment="Denied",
            )

        service.repo.create_audit_log.assert_awaited()
