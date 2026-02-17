"""Onboarding Workflows router — configurable approval engine (CAB-593)"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Permission, User, get_current_user, require_permission, require_tenant_access
from ..database import get_db
from ..schemas.workflow import (
    AuditListResponse,
    AuditResponse,
    InstanceCreate,
    InstanceListResponse,
    InstanceResponse,
    StepActionRequest,
    TemplateCreate,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
from ..services.workflow_service import WorkflowService

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/workflows",
    tags=["Onboarding Workflows"],
)


# --- Templates CRUD ---


@router.get("/templates", response_model=TemplateListResponse)
@require_permission(Permission.WORKFLOWS_READ)
@require_tenant_access
async def list_templates(
    tenant_id: str,
    workflow_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List workflow templates for a tenant."""
    service = WorkflowService(db)
    items, total = await service.list_templates(tenant_id, workflow_type=workflow_type, page=page, page_size=page_size)
    return TemplateListResponse(
        items=[TemplateResponse.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/templates", response_model=TemplateResponse, status_code=201)
@require_permission(Permission.WORKFLOWS_MANAGE)
@require_tenant_access
async def create_template(
    tenant_id: str,
    payload: TemplateCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workflow template."""
    service = WorkflowService(db)
    template = await service.create_template(
        tenant_id=tenant_id,
        workflow_type=payload.workflow_type,
        name=payload.name,
        mode=payload.mode,
        created_by=user.id,
        description=payload.description,
        approval_steps=[s.model_dump() for s in payload.approval_steps],
        auto_provision=payload.auto_provision,
        notification_config=payload.notification_config,
        sector=payload.sector,
    )
    return TemplateResponse.model_validate(template)


@router.get("/templates/{template_id}", response_model=TemplateResponse)
@require_permission(Permission.WORKFLOWS_READ)
@require_tenant_access
async def get_template(
    tenant_id: str,
    template_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a workflow template by ID."""
    service = WorkflowService(db)
    template = await service.get_template(tenant_id, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=TemplateResponse)
@require_permission(Permission.WORKFLOWS_MANAGE)
@require_tenant_access
async def update_template(
    tenant_id: str,
    template_id: UUID,
    payload: TemplateUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a workflow template."""
    service = WorkflowService(db)
    updates = payload.model_dump(exclude_unset=True)
    if "approval_steps" in updates and updates["approval_steps"] is not None:
        updates["approval_steps"] = [
            s.model_dump() if hasattr(s, "model_dump") else s for s in updates["approval_steps"]
        ]
    try:
        template = await service.update_template(tenant_id, template_id, **updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return TemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}", status_code=204)
@require_permission(Permission.WORKFLOWS_MANAGE)
@require_tenant_access
async def delete_template(
    tenant_id: str,
    template_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a workflow template."""
    service = WorkflowService(db)
    try:
        await service.delete_template(tenant_id, template_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- Instances ---


@router.post("/instances", response_model=InstanceResponse, status_code=201)
@require_permission(Permission.WORKFLOWS_MANAGE)
@require_tenant_access
async def start_workflow(
    tenant_id: str,
    payload: InstanceCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new workflow instance from a template."""
    service = WorkflowService(db)
    try:
        instance = await service.start_workflow(
            tenant_id=tenant_id,
            template_id=payload.template_id,
            subject_id=payload.subject_id,
            user_id=user.id,
            subject_email=payload.subject_email,
            context=payload.context,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return InstanceResponse.model_validate(instance)


@router.get("/instances", response_model=InstanceListResponse)
@require_permission(Permission.WORKFLOWS_READ)
@require_tenant_access
async def list_instances(
    tenant_id: str,
    workflow_type: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List workflow instances for a tenant."""
    service = WorkflowService(db)
    items, total = await service.list_instances(
        tenant_id,
        workflow_type=workflow_type,
        status=status,
        page=page,
        page_size=page_size,
    )
    return InstanceListResponse(
        items=[InstanceResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/instances/{instance_id}", response_model=InstanceResponse)
@require_permission(Permission.WORKFLOWS_READ)
@require_tenant_access
async def get_instance(
    tenant_id: str,
    instance_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a workflow instance by ID."""
    service = WorkflowService(db)
    instance = await service.get_instance(tenant_id, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Workflow instance not found")
    return InstanceResponse.model_validate(instance)


# --- Actions: Approve / Reject ---


@router.post("/instances/{instance_id}/approve", response_model=InstanceResponse)
@require_permission(Permission.WORKFLOWS_MANAGE)
@require_tenant_access
async def approve_step(
    tenant_id: str,
    instance_id: UUID,
    payload: StepActionRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve the current step of a workflow instance."""
    service = WorkflowService(db)
    comment = payload.comment if payload else None
    try:
        instance = await service.approve_step(tenant_id, instance_id, user.id, comment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return InstanceResponse.model_validate(instance)


@router.post("/instances/{instance_id}/reject", response_model=InstanceResponse)
@require_permission(Permission.WORKFLOWS_MANAGE)
@require_tenant_access
async def reject_step(
    tenant_id: str,
    instance_id: UUID,
    payload: StepActionRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject the current step of a workflow instance."""
    service = WorkflowService(db)
    comment = payload.comment if payload else None
    try:
        instance = await service.reject_step(tenant_id, instance_id, user.id, comment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return InstanceResponse.model_validate(instance)


# --- Audit Trail ---


@router.get("/audit/{instance_id}", response_model=AuditListResponse)
@require_permission(Permission.WORKFLOWS_READ)
@require_tenant_access
async def get_audit_trail(
    tenant_id: str,
    instance_id: UUID,
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the audit trail for a workflow instance."""
    service = WorkflowService(db)
    items, total = await service.get_audit_log(instance_id, page=page, page_size=page_size)
    return AuditListResponse(
        items=[AuditResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )
