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


# ===========================================================================
# Scenario 1: create_template — builds WorkflowTemplate correctly
# ===========================================================================


class TestCreateTemplate:
    @pytest.mark.asyncio()
    async def test_create_template_builds_correctly(self, service):
        """create_template constructs a WorkflowTemplate with all provided fields."""
        template = _make_template()
        service.repo.create_template = AsyncMock(return_value=template)

        result = await service.create_template(
            tenant_id="tenant-1",
            workflow_type=WorkflowType.USER_REGISTRATION.value,
            name="My Template",
            mode=WorkflowMode.MANUAL.value,
            created_by="admin",
            description="Onboarding",
            approval_steps=[{"role": "admin"}],
            auto_provision=True,
            notification_config={"email": True},
            sector="fintech",
        )

        service.repo.create_template.assert_called_once()
        built: WorkflowTemplate = service.repo.create_template.call_args[0][0]
        assert built.tenant_id == "tenant-1"
        assert built.workflow_type == WorkflowType.USER_REGISTRATION.value
        assert built.name == "My Template"
        assert built.mode == WorkflowMode.MANUAL.value
        assert built.description == "Onboarding"
        assert built.approval_steps == [{"role": "admin"}]
        assert built.auto_provision == "true"  # bool True → "true"
        assert built.notification_config == {"email": True}
        assert built.sector == "fintech"
        assert built.created_by == "admin"
        assert result is template

    @pytest.mark.asyncio()
    async def test_create_template_defaults(self, service):
        """Omitted optional params produce sane defaults."""
        template = _make_template()
        service.repo.create_template = AsyncMock(return_value=template)

        await service.create_template(
            tenant_id="tenant-1",
            workflow_type=WorkflowType.CONSUMER_REGISTRATION.value,
            name="Minimal",
            mode=WorkflowMode.AUTO.value,
        )

        built: WorkflowTemplate = service.repo.create_template.call_args[0][0]
        assert built.approval_steps == []
        assert built.notification_config == {}
        assert built.description is None
        assert built.sector is None
        assert built.created_by is None


# ===========================================================================
# Scenario 2: get_template — delegates to repo
# ===========================================================================


class TestGetTemplate:
    @pytest.mark.asyncio()
    async def test_get_template_delegates_to_repo(self, service):
        template = _make_template()
        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)

        result = await service.get_template("tenant-1", template.id)

        service.repo.get_template_by_id_and_tenant.assert_called_once_with(template.id, "tenant-1")
        assert result is template

    @pytest.mark.asyncio()
    async def test_get_template_not_found_returns_none(self, service):
        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=None)

        result = await service.get_template("tenant-1", uuid.uuid4())

        assert result is None


# ===========================================================================
# Scenarios 3 & 4: update_template
# ===========================================================================


class TestUpdateTemplate:
    @pytest.mark.asyncio()
    async def test_update_template_found_and_updated(self, service):
        """update_template mutates the ORM object and calls repo.update_template."""
        template = _make_template()
        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)
        service.repo.update_template = AsyncMock(return_value=template)

        result = await service.update_template("tenant-1", template.id, name="Updated Name")

        assert template.name == "Updated Name"
        service.repo.update_template.assert_called_once_with(template)
        assert result is template

    @pytest.mark.asyncio()
    async def test_update_template_not_found_raises(self, service):
        tid = uuid.uuid4()
        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match=str(tid)):
            await service.update_template("tenant-1", tid, name="Irrelevant")

    @pytest.mark.asyncio()
    async def test_update_template_auto_provision_true_stored_as_string(self, service):
        """auto_provision=True kwarg must be stored as 'true'."""
        template = _make_template()
        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)
        service.repo.update_template = AsyncMock(return_value=template)

        await service.update_template("tenant-1", template.id, auto_provision=True)

        assert template.auto_provision == "true"

    @pytest.mark.asyncio()
    async def test_update_template_auto_provision_false_stored_as_string(self, service):
        """auto_provision=False kwarg must be stored as 'false'."""
        template = _make_template()
        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)
        service.repo.update_template = AsyncMock(return_value=template)

        await service.update_template("tenant-1", template.id, auto_provision=False)

        assert template.auto_provision == "false"

    @pytest.mark.asyncio()
    async def test_update_template_none_values_skipped(self, service):
        """Kwargs with None value must not overwrite existing field values."""
        template = _make_template()
        template.name = "Original"
        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)
        service.repo.update_template = AsyncMock(return_value=template)

        await service.update_template("tenant-1", template.id, name=None)

        assert template.name == "Original"


# ===========================================================================
# Scenario 5: delete_template
# ===========================================================================


class TestDeleteTemplate:
    @pytest.mark.asyncio()
    async def test_delete_template_found_and_deleted(self, service):
        template = _make_template()
        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=template)
        service.repo.delete_template = AsyncMock()

        await service.delete_template("tenant-1", template.id)

        service.repo.delete_template.assert_called_once_with(template)

    @pytest.mark.asyncio()
    async def test_delete_template_not_found_raises(self, service):
        tid = uuid.uuid4()
        service.repo.get_template_by_id_and_tenant = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match=str(tid)):
            await service.delete_template("tenant-1", tid)


# ===========================================================================
# Scenario 6: list_templates — returns tuple
# ===========================================================================


class TestListTemplates:
    @pytest.mark.asyncio()
    async def test_list_templates_returns_tuple(self, service):
        templates = [_make_template(), _make_template()]
        service.repo.list_templates = AsyncMock(return_value=(templates, 2))

        items, total = await service.list_templates(
            "tenant-1", workflow_type="user_registration", page=1, page_size=10
        )

        service.repo.list_templates.assert_called_once_with(
            "tenant-1", workflow_type="user_registration", page=1, page_size=10
        )
        assert items is templates
        assert total == 2

    @pytest.mark.asyncio()
    async def test_list_templates_empty(self, service):
        service.repo.list_templates = AsyncMock(return_value=([], 0))

        items, total = await service.list_templates("tenant-1")
        assert items == []
        assert total == 0


# ===========================================================================
# Scenarios 9 & 10: start_workflow AUTO and MANUAL modes
# ===========================================================================


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


# ===========================================================================
# Scenarios 13 & 14: approval_chain mode
# ===========================================================================


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


# ===========================================================================
# Scenario 15: reject_step
# ===========================================================================


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


# ===========================================================================
# Scenarios 19 & 20: provisioning failure / exception
# ===========================================================================


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


# ===========================================================================
# Scenarios 7 & 8: template not found / inactive
# ===========================================================================


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


# ===========================================================================
# Scenarios 11 & 12: approve_step validation
# ===========================================================================


class TestApproveValidation:
    @pytest.mark.asyncio()
    async def test_approve_step_instance_not_found_raises(self, service):
        """Cannot approve an instance that does not exist."""
        service.repo.get_instance_by_id_and_tenant = AsyncMock(return_value=None)
        iid = uuid.uuid4()

        with pytest.raises(ValueError, match=str(iid)):
            await service.approve_step("tenant-1", iid, "admin")

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


# ===========================================================================
# Scenario 8: inactive template
# ===========================================================================


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


# ===========================================================================
# Scenarios 16 & 17: _transition — invalid transitions + terminal completed_at
# ===========================================================================


class TestTransition:
    @pytest.mark.asyncio()
    async def test_valid_transition_pending_to_in_progress(self, service):
        """PENDING → IN_PROGRESS is valid."""
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.PENDING.value)
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            await service._transition(instance, WorkflowStatus.IN_PROGRESS, "admin")

        assert instance.status == WorkflowStatus.IN_PROGRESS.value

    @pytest.mark.asyncio()
    async def test_invalid_transition_completed_to_in_progress_raises(self, service):
        """COMPLETED → IN_PROGRESS is not in VALID_TRANSITIONS → ValueError."""
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.COMPLETED.value)

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            with pytest.raises(ValueError, match="Invalid transition"):
                await service._transition(instance, WorkflowStatus.IN_PROGRESS, "admin")

    @pytest.mark.asyncio()
    async def test_invalid_transition_from_terminal_rejected(self, service):
        """REJECTED (terminal) → any state raises ValueError."""
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.REJECTED.value)

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            with pytest.raises(ValueError, match="Invalid transition"):
                await service._transition(instance, WorkflowStatus.APPROVED, "admin")

    @pytest.mark.asyncio()
    async def test_invalid_transition_in_progress_to_provisioning(self, service):
        """IN_PROGRESS → PROVISIONING skips APPROVED — not allowed."""
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.IN_PROGRESS.value)

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            with pytest.raises(ValueError, match="Invalid transition"):
                await service._transition(instance, WorkflowStatus.PROVISIONING, "admin")

    @pytest.mark.asyncio()
    async def test_transition_to_rejected_sets_completed_at(self, service):
        """REJECTED is a terminal state — completed_at must be set."""
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.IN_PROGRESS.value)
        instance.completed_at = None
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            await service._transition(instance, WorkflowStatus.REJECTED, "admin")

        assert instance.status == WorkflowStatus.REJECTED.value
        assert instance.completed_at is not None

    @pytest.mark.asyncio()
    async def test_transition_to_failed_sets_completed_at(self, service):
        """FAILED is a terminal state — completed_at must be set."""
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.PROVISIONING.value)
        instance.completed_at = None
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            await service._transition(instance, WorkflowStatus.FAILED, "admin")

        assert instance.status == WorkflowStatus.FAILED.value
        assert instance.completed_at is not None

    @pytest.mark.asyncio()
    async def test_transition_to_completed_sets_completed_at(self, service):
        """COMPLETED is a terminal state — completed_at must be set."""
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.PROVISIONING.value)
        instance.completed_at = None
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            await service._transition(instance, WorkflowStatus.COMPLETED, "admin")

        assert instance.status == WorkflowStatus.COMPLETED.value
        assert instance.completed_at is not None

    @pytest.mark.asyncio()
    async def test_transition_non_terminal_does_not_set_completed_at(self, service):
        """Non-terminal transitions must NOT set completed_at."""
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.PENDING.value)
        instance.completed_at = None
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            await service._transition(instance, WorkflowStatus.IN_PROGRESS, "admin")

        assert instance.completed_at is None

    @pytest.mark.asyncio()
    async def test_transition_writes_audit_log(self, service):
        """_transition must create one audit log entry."""
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.PENDING.value)
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            await service._transition(instance, WorkflowStatus.IN_PROGRESS, "admin")

        service.repo.create_audit_log.assert_called_once()


# ===========================================================================
# Scenario 18: _run_provisioning — success → COMPLETED
# ===========================================================================


class TestRunProvisioningDirect:
    @pytest.mark.asyncio()
    async def test_run_provisioning_success_completes(self, service, mock_provisioner):
        """Provisioner returns True → APPROVED → PROVISIONING → COMPLETED."""
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.APPROVED.value)
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()
        mock_provisioner.provision = AsyncMock(return_value=True)

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            await service._run_provisioning(instance, template, "admin")

        mock_provisioner.provision.assert_awaited_once_with(
            workflow_type=instance.workflow_type,
            subject_id=instance.subject_id,
            tenant_id=instance.tenant_id,
            context=instance.context or {},
        )
        assert instance.status == WorkflowStatus.COMPLETED.value
        assert instance.completed_at is not None

    @pytest.mark.asyncio()
    async def test_run_provisioning_transitions_through_provisioning_state(self, service, mock_provisioner):
        """_run_provisioning must pass through PROVISIONING before COMPLETED."""
        template = _make_template()
        instance = _make_instance(template, status=WorkflowStatus.APPROVED.value)
        service.repo.create_audit_log = AsyncMock()

        status_history: list[str] = []

        async def capture(*_args, **_kwargs):
            status_history.append(instance.status)
            return instance

        service.repo.update_instance = AsyncMock(side_effect=capture)
        mock_provisioner.provision = AsyncMock(return_value=True)

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            await service._run_provisioning(instance, template, "admin")

        assert WorkflowStatus.PROVISIONING.value in status_history
        assert instance.status == WorkflowStatus.COMPLETED.value


# ===========================================================================
# Audit trail
# ===========================================================================


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


# ===========================================================================
# Parameterized VALID_TRANSITIONS matrix
# ===========================================================================


class TestValidTransitionsMatrix:
    """Exhaustive check of VALID_TRANSITIONS — all allowed and disallowed pairs."""

    @pytest.mark.parametrize(
        "from_status, to_status, should_pass",
        [
            # --- Allowed ---
            (WorkflowStatus.PENDING, WorkflowStatus.IN_PROGRESS, True),
            (WorkflowStatus.PENDING, WorkflowStatus.APPROVED, True),
            (WorkflowStatus.IN_PROGRESS, WorkflowStatus.APPROVED, True),
            (WorkflowStatus.IN_PROGRESS, WorkflowStatus.REJECTED, True),
            (WorkflowStatus.APPROVED, WorkflowStatus.PROVISIONING, True),
            (WorkflowStatus.PROVISIONING, WorkflowStatus.COMPLETED, True),
            (WorkflowStatus.PROVISIONING, WorkflowStatus.FAILED, True),
            # --- Disallowed ---
            (WorkflowStatus.PENDING, WorkflowStatus.COMPLETED, False),
            (WorkflowStatus.PENDING, WorkflowStatus.PROVISIONING, False),
            (WorkflowStatus.COMPLETED, WorkflowStatus.PENDING, False),
            (WorkflowStatus.COMPLETED, WorkflowStatus.IN_PROGRESS, False),
            (WorkflowStatus.FAILED, WorkflowStatus.PROVISIONING, False),
            (WorkflowStatus.REJECTED, WorkflowStatus.IN_PROGRESS, False),
            (WorkflowStatus.IN_PROGRESS, WorkflowStatus.PROVISIONING, False),
        ],
    )
    @pytest.mark.asyncio()
    async def test_transition_matrix(
        self,
        service,
        from_status: WorkflowStatus,
        to_status: WorkflowStatus,
        should_pass: bool,
    ):
        template = _make_template()
        instance = _make_instance(template, status=from_status.value)
        service.repo.update_instance = AsyncMock(return_value=instance)
        service.repo.create_audit_log = AsyncMock()

        with patch("src.services.workflow_service.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            if should_pass:
                await service._transition(instance, to_status, "admin")
                assert instance.status == to_status.value
            else:
                with pytest.raises(ValueError, match="Invalid transition"):
                    await service._transition(instance, to_status, "admin")
