"""Workflow repository — data access layer (CAB-593)"""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.workflow import (
    WorkflowAuditLog,
    WorkflowInstance,
    WorkflowStepResult,
    WorkflowTemplate,
)

logger = logging.getLogger(__name__)


class WorkflowRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Templates ---

    async def create_template(self, template: WorkflowTemplate) -> WorkflowTemplate:
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def get_template_by_id(self, template_id: UUID) -> WorkflowTemplate | None:
        result = await self.db.execute(select(WorkflowTemplate).where(WorkflowTemplate.id == template_id))
        return result.scalar_one_or_none()

    async def get_template_by_id_and_tenant(self, template_id: UUID, tenant_id: str) -> WorkflowTemplate | None:
        result = await self.db.execute(
            select(WorkflowTemplate).where(
                WorkflowTemplate.id == template_id,
                WorkflowTemplate.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_template(self, tenant_id: str, workflow_type: str) -> WorkflowTemplate | None:
        result = await self.db.execute(
            select(WorkflowTemplate)
            .where(
                WorkflowTemplate.tenant_id == tenant_id,
                WorkflowTemplate.workflow_type == workflow_type,
                WorkflowTemplate.is_active == "true",
            )
            .order_by(WorkflowTemplate.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_template(self, template: WorkflowTemplate) -> WorkflowTemplate:
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def delete_template(self, template: WorkflowTemplate) -> None:
        await self.db.delete(template)
        await self.db.flush()

    async def list_templates(
        self,
        tenant_id: str,
        workflow_type: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WorkflowTemplate], int]:
        query = select(WorkflowTemplate).where(WorkflowTemplate.tenant_id == tenant_id)
        count_query = select(func.count()).select_from(WorkflowTemplate).where(WorkflowTemplate.tenant_id == tenant_id)
        if workflow_type:
            query = query.where(WorkflowTemplate.workflow_type == workflow_type)
            count_query = count_query.where(WorkflowTemplate.workflow_type == workflow_type)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        query = query.order_by(WorkflowTemplate.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    # --- Instances ---

    async def create_instance(self, instance: WorkflowInstance) -> WorkflowInstance:
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def get_instance_by_id(self, instance_id: UUID) -> WorkflowInstance | None:
        result = await self.db.execute(select(WorkflowInstance).where(WorkflowInstance.id == instance_id))
        return result.scalar_one_or_none()

    async def get_instance_by_id_and_tenant(self, instance_id: UUID, tenant_id: str) -> WorkflowInstance | None:
        result = await self.db.execute(
            select(WorkflowInstance).where(
                WorkflowInstance.id == instance_id,
                WorkflowInstance.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_instance(self, instance: WorkflowInstance) -> WorkflowInstance:
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def list_instances(
        self,
        tenant_id: str,
        workflow_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WorkflowInstance], int]:
        query = select(WorkflowInstance).where(WorkflowInstance.tenant_id == tenant_id)
        count_query = select(func.count()).select_from(WorkflowInstance).where(WorkflowInstance.tenant_id == tenant_id)
        if workflow_type:
            query = query.where(WorkflowInstance.workflow_type == workflow_type)
            count_query = count_query.where(WorkflowInstance.workflow_type == workflow_type)
        if status:
            query = query.where(WorkflowInstance.status == status)
            count_query = count_query.where(WorkflowInstance.status == status)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        query = query.order_by(WorkflowInstance.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    # --- Step Results ---

    async def create_step_result(self, step_result: WorkflowStepResult) -> WorkflowStepResult:
        self.db.add(step_result)
        await self.db.flush()
        await self.db.refresh(step_result)
        return step_result

    async def get_step_results(self, instance_id: UUID) -> list[WorkflowStepResult]:
        result = await self.db.execute(
            select(WorkflowStepResult)
            .where(WorkflowStepResult.instance_id == instance_id)
            .order_by(WorkflowStepResult.step_index)
        )
        return list(result.scalars().all())

    # --- Audit Logs ---

    async def create_audit_log(self, audit_log: WorkflowAuditLog) -> WorkflowAuditLog:
        self.db.add(audit_log)
        await self.db.flush()
        return audit_log

    async def list_audit_logs(
        self,
        instance_id: UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WorkflowAuditLog], int]:
        count_query = (
            select(func.count()).select_from(WorkflowAuditLog).where(WorkflowAuditLog.instance_id == instance_id)
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        query = (
            select(WorkflowAuditLog)
            .where(WorkflowAuditLog.instance_id == instance_id)
            .order_by(WorkflowAuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all()), total
