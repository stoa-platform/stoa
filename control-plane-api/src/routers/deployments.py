"""Deployments router — API deployment management (CAB-1353)"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Permission, User, get_current_user, require_permission, require_tenant_access
from ..database import get_db
from ..schemas.deployment import (
    DeploymentCreate,
    DeploymentListResponse,
    DeploymentLogListResponse,
    DeploymentLogResponse,
    DeploymentResponse,
    DeploymentStatusUpdate,
    EnvironmentEnum,
    EnvironmentStatusResponse,
    RollbackCreate,
)
from ..services.deployment_service import DeploymentService
from ..services.git_service import git_service

router = APIRouter(prefix="/v1/tenants/{tenant_id}/deployments", tags=["Deployments"])


@router.get("", response_model=DeploymentListResponse)
@require_tenant_access
async def list_deployments(
    tenant_id: str,
    api_id: str | None = None,
    environment: EnvironmentEnum | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List deployment history for a tenant"""
    service = DeploymentService(db)
    env_val = environment.value if environment else None
    items, total = await service.list_deployments(
        tenant_id, api_id=api_id, environment=env_val,
        status=status, page=page, page_size=page_size,
    )
    return DeploymentListResponse(
        items=[DeploymentResponse.model_validate(d) for d in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{deployment_id}", response_model=DeploymentResponse)
@require_tenant_access
async def get_deployment(
    tenant_id: str,
    deployment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get deployment details"""
    service = DeploymentService(db)
    deployment = await service.get_deployment(tenant_id, deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return DeploymentResponse.model_validate(deployment)


@router.post("", response_model=DeploymentResponse, status_code=201)
@require_permission(Permission.APIS_DEPLOY)
@require_tenant_access
async def create_deployment(
    tenant_id: str,
    request: DeploymentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deploy an API to an environment.

    Creates a deployment record, emits a deploy-request Kafka event,
    and triggers webhook notifications.
    """
    api_name = request.api_name or request.api_id
    version = request.version or "1.0.0"

    try:
        api_info = await git_service.get_api(tenant_id, request.api_id)
        if api_info:
            api_name = request.api_name or api_info.get("name", request.api_id)
            version = request.version or api_info.get("version", "1.0.0")
    except Exception:
        pass

    service = DeploymentService(db)
    deployment = await service.create_deployment(
        tenant_id=tenant_id, api_id=request.api_id, api_name=api_name,
        environment=request.environment.value, version=version,
        deployed_by=user.username, user_id=user.id,
        gateway_id=request.gateway_id,
    )
    await db.commit()
    return DeploymentResponse.model_validate(deployment)


@router.post("/{deployment_id}/rollback", response_model=DeploymentResponse, status_code=201)
@require_permission(Permission.APIS_DEPLOY)
@require_tenant_access
async def rollback_deployment(
    tenant_id: str,
    deployment_id: UUID,
    request: RollbackCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rollback a deployment to a previous version"""
    service = DeploymentService(db)
    try:
        rollback = await service.rollback_deployment(
            tenant_id=tenant_id, deployment_id=deployment_id,
            target_version=request.target_version,
            deployed_by=user.username, user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return DeploymentResponse.model_validate(rollback)


@router.patch("/{deployment_id}/status", response_model=DeploymentResponse)
@require_tenant_access
async def update_deployment_status(
    tenant_id: str,
    deployment_id: UUID,
    request: DeploymentStatusUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update deployment status (gateway callback endpoint)"""
    service = DeploymentService(db)
    try:
        deployment = await service.update_status(
            tenant_id=tenant_id, deployment_id=deployment_id,
            status=request.status.value, error_message=request.error_message,
            spec_hash=request.spec_hash, commit_sha=request.commit_sha,
            metadata=request.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return DeploymentResponse.model_validate(deployment)


@router.get("/{deployment_id}/logs", response_model=DeploymentLogListResponse)
@require_tenant_access
async def get_deployment_logs(
    tenant_id: str,
    deployment_id: UUID,
    after_seq: int = 0,
    limit: int = 200,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get deployment logs with optional cursor-based pagination.

    Query params:
        after_seq: Return logs with seq > this value (for polling).
        limit: Max entries to return (default 200).
    """
    service = DeploymentService(db)
    deployment = await service.get_deployment(tenant_id, deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    logs = await service.get_logs(deployment_id, tenant_id, after_seq=after_seq, limit=limit)
    return DeploymentLogListResponse(
        deployment_id=deployment_id,
        logs=[DeploymentLogResponse.model_validate(log) for log in logs],
        total=len(logs),
    )


@router.get("/environments/{environment}/status", response_model=EnvironmentStatusResponse)
@require_tenant_access
async def get_environment_status(
    tenant_id: str,
    environment: EnvironmentEnum,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get status of all APIs deployed in an environment"""
    service = DeploymentService(db)
    deployments, healthy = await service.get_environment_status(
        tenant_id, environment.value,
    )
    return EnvironmentStatusResponse(
        environment=environment.value, healthy=healthy,
        deployments=[
            {"api_id": d.api_id, "api_name": d.api_name, "version": d.version,
             "status": d.status, "deployed_at": d.completed_at or d.created_at}
            for d in deployments
        ],
    )
