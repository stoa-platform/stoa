"""Workflow service — state machine + business logic (CAB-593)"""

import logging
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.workflow import (
    WorkflowAuditLog,
    WorkflowInstance,
    WorkflowMode,
    WorkflowStatus,
    WorkflowStepResult,
    WorkflowTemplate,
)
from src.repositories.workflow import WorkflowRepository
from src.services.kafka_service import Topics, kafka_service

logger = logging.getLogger(__name__)

# Valid state transitions
VALID_TRANSITIONS: dict[str, list[str]] = {
    WorkflowStatus.PENDING: [WorkflowStatus.IN_PROGRESS, WorkflowStatus.APPROVED],
    WorkflowStatus.IN_PROGRESS: [WorkflowStatus.APPROVED, WorkflowStatus.REJECTED],
    WorkflowStatus.APPROVED: [WorkflowStatus.PROVISIONING],
    WorkflowStatus.PROVISIONING: [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED],
    WorkflowStatus.REJECTED: [],
    WorkflowStatus.COMPLETED: [],
    WorkflowStatus.FAILED: [],
}


class Provisioner(Protocol):
    """Interface for workflow provisioning — stubbed for follow-up ticket."""

    async def provision(self, workflow_type: str, subject_id: str, tenant_id: str, context: dict) -> bool: ...


class StubProvisioner:
    """Default provisioner — logs and returns success."""

    async def provision(self, workflow_type: str, subject_id: str, tenant_id: str, context: dict) -> bool:
        logger.info(
            "Stub provisioning: type=%s subject=%s tenant=%s",
            workflow_type,
            subject_id,
            tenant_id,
        )
        return True


class WorkflowService:
    def __init__(self, db: AsyncSession, provisioner: Provisioner | None = None):
        self.db = db
        self.repo = WorkflowRepository(db)
        self.provisioner = provisioner or StubProvisioner()

    # --- Templates ---

    async def create_template(
        self,
        tenant_id: str,
        workflow_type: str,
        name: str,
        mode: str,
        created_by: str | None = None,
        description: str | None = None,
        approval_steps: list | None = None,
        auto_provision: bool = True,
        notification_config: dict | None = None,
        sector: str | None = None,
    ) -> WorkflowTemplate:
        template = WorkflowTemplate(
            tenant_id=tenant_id,
            workflow_type=workflow_type,
            name=name,
            mode=mode,
            description=description,
            approval_steps=approval_steps or [],
            auto_provision="true" if auto_provision else "false",
            notification_config=notification_config or {},
            sector=sector,
            created_by=created_by,
        )
        return await self.repo.create_template(template)

    async def get_template(self, tenant_id: str, template_id: UUID) -> WorkflowTemplate | None:
        return await self.repo.get_template_by_id_and_tenant(template_id, tenant_id)

    async def update_template(self, tenant_id: str, template_id: UUID, **updates: object) -> WorkflowTemplate:
        template = await self.repo.get_template_by_id_and_tenant(template_id, tenant_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        for key, value in updates.items():
            if value is not None:
                if key in ("auto_provision", "is_active"):
                    setattr(template, key, "true" if value else "false")
                else:
                    setattr(template, key, value)
        template.updated_at = datetime.utcnow()
        return await self.repo.update_template(template)

    async def delete_template(self, tenant_id: str, template_id: UUID) -> None:
        template = await self.repo.get_template_by_id_and_tenant(template_id, tenant_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        await self.repo.delete_template(template)

    async def list_templates(
        self, tenant_id: str, workflow_type: str | None = None, page: int = 1, page_size: int = 50
    ) -> tuple[list[WorkflowTemplate], int]:
        return await self.repo.list_templates(tenant_id, workflow_type=workflow_type, page=page, page_size=page_size)

    # --- Instances + State Machine ---

    async def start_workflow(
        self,
        tenant_id: str,
        template_id: UUID,
        subject_id: str,
        user_id: str,
        subject_email: str | None = None,
        context: dict | None = None,
    ) -> WorkflowInstance:
        template = await self.repo.get_template_by_id_and_tenant(template_id, tenant_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        if template.is_active != "true":
            raise ValueError(f"Template {template_id} is not active")

        instance = WorkflowInstance(
            template_id=template_id,
            tenant_id=tenant_id,
            workflow_type=template.workflow_type,
            subject_id=subject_id,
            subject_email=subject_email,
            status=WorkflowStatus.PENDING.value,
            current_step_index=0,
            context=context or {},
            initiated_by=user_id,
        )
        instance = await self.repo.create_instance(instance)

        await self._audit(instance.id, "workflow.created", user_id, {"template_id": str(template_id)})
        await self._emit_kafka(tenant_id, "workflow.created", instance, user_id)

        # Auto mode: skip straight to approved → provisioning → completed
        if template.mode == WorkflowMode.AUTO.value:
            await self._transition(instance, WorkflowStatus.APPROVED, user_id)
            if template.auto_provision == "true":
                await self._run_provisioning(instance, template, user_id)
        else:
            # Manual or approval_chain: move to in_progress
            await self._transition(instance, WorkflowStatus.IN_PROGRESS, user_id)

        return instance

    async def approve_step(
        self,
        tenant_id: str,
        instance_id: UUID,
        approver_id: str,
        comment: str | None = None,
    ) -> WorkflowInstance:
        instance = await self.repo.get_instance_by_id_and_tenant(instance_id, tenant_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")
        if instance.status != WorkflowStatus.IN_PROGRESS.value:
            raise ValueError(f"Cannot approve: instance status is {instance.status}")

        template = await self.repo.get_template_by_id(instance.template_id)
        if not template:
            raise ValueError("Template not found for instance")

        # Record step result
        step_result = WorkflowStepResult(
            instance_id=instance_id,
            step_index=instance.current_step_index,
            approver_id=approver_id,
            action="approved",
            comment=comment,
        )
        await self.repo.create_step_result(step_result)
        await self._audit(
            instance_id,
            "workflow.step_completed",
            approver_id,
            {"step_index": instance.current_step_index, "action": "approved"},
        )
        await self._emit_kafka(tenant_id, "workflow.step_completed", instance, approver_id)

        # Check if more steps remain (approval_chain)
        if template.mode == WorkflowMode.APPROVAL_CHAIN.value:
            total_steps = len(template.approval_steps or [])
            next_step = instance.current_step_index + 1
            if next_step < total_steps:
                instance.current_step_index = next_step
                instance.updated_at = datetime.utcnow()
                instance = await self.repo.update_instance(instance)
                return instance

        # All steps done → APPROVED
        await self._transition(instance, WorkflowStatus.APPROVED, approver_id)

        if template.auto_provision == "true":
            await self._run_provisioning(instance, template, approver_id)

        return instance

    async def reject_step(
        self,
        tenant_id: str,
        instance_id: UUID,
        approver_id: str,
        comment: str | None = None,
    ) -> WorkflowInstance:
        instance = await self.repo.get_instance_by_id_and_tenant(instance_id, tenant_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")
        if instance.status != WorkflowStatus.IN_PROGRESS.value:
            raise ValueError(f"Cannot reject: instance status is {instance.status}")

        step_result = WorkflowStepResult(
            instance_id=instance_id,
            step_index=instance.current_step_index,
            approver_id=approver_id,
            action="rejected",
            comment=comment,
        )
        await self.repo.create_step_result(step_result)

        await self._transition(instance, WorkflowStatus.REJECTED, approver_id)
        await self._emit_kafka(tenant_id, "workflow.rejected", instance, approver_id)

        return instance

    async def get_instance(self, tenant_id: str, instance_id: UUID) -> WorkflowInstance | None:
        return await self.repo.get_instance_by_id_and_tenant(instance_id, tenant_id)

    async def list_instances(
        self,
        tenant_id: str,
        workflow_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WorkflowInstance], int]:
        return await self.repo.list_instances(
            tenant_id, workflow_type=workflow_type, status=status, page=page, page_size=page_size
        )

    async def get_audit_log(
        self, instance_id: UUID, page: int = 1, page_size: int = 50
    ) -> tuple[list[WorkflowAuditLog], int]:
        return await self.repo.list_audit_logs(instance_id, page=page, page_size=page_size)

    async def get_step_results(self, instance_id: UUID) -> list[WorkflowStepResult]:
        return await self.repo.get_step_results(instance_id)

    # --- Internal ---

    async def _transition(self, instance: WorkflowInstance, new_status: WorkflowStatus, actor_id: str) -> None:
        current = instance.status
        valid_next = VALID_TRANSITIONS.get(current, [])
        if new_status.value not in [s.value if isinstance(s, WorkflowStatus) else s for s in valid_next]:
            raise ValueError(f"Invalid transition: {current} → {new_status.value}")

        old_status = instance.status
        instance.status = new_status.value
        instance.updated_at = datetime.utcnow()
        if new_status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.REJECTED):
            instance.completed_at = datetime.utcnow()
        await self.repo.update_instance(instance)
        await self._audit(
            instance.id,
            "workflow.status_changed",
            actor_id,
            {"from": old_status, "to": new_status.value},
        )

    async def _run_provisioning(self, instance: WorkflowInstance, template: WorkflowTemplate, actor_id: str) -> None:
        await self._transition(instance, WorkflowStatus.PROVISIONING, actor_id)
        try:
            success = await self.provisioner.provision(
                workflow_type=instance.workflow_type,
                subject_id=instance.subject_id,
                tenant_id=instance.tenant_id,
                context=instance.context or {},
            )
            if success:
                await self._transition(instance, WorkflowStatus.COMPLETED, actor_id)
            else:
                await self._transition(instance, WorkflowStatus.FAILED, actor_id)
        except Exception as e:
            logger.error("Provisioning failed for instance %s: %s", instance.id, e)
            await self._transition(instance, WorkflowStatus.FAILED, actor_id)

    async def _audit(
        self, instance_id: UUID, event_type: str, actor_id: str | None, details: dict | None = None
    ) -> None:
        audit_log = WorkflowAuditLog(
            instance_id=instance_id,
            event_type=event_type,
            actor_id=actor_id,
            details=details or {},
        )
        await self.repo.create_audit_log(audit_log)

    async def _emit_kafka(self, tenant_id: str, event_type: str, instance: WorkflowInstance, user_id: str) -> None:
        await kafka_service.publish(
            topic=Topics.WORKFLOW_EVENTS,
            event_type=event_type,
            tenant_id=tenant_id,
            payload={
                "instance_id": str(instance.id),
                "workflow_type": instance.workflow_type,
                "subject_id": instance.subject_id,
                "status": instance.status,
            },
            user_id=user_id,
        )
