"""API routes for API gateway assignments and environment-aware deployment (CAB-1888)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import require_role
from src.database import get_db
from src.models.api_gateway_assignment import ApiGatewayAssignment
from src.repositories.api_gateway_assignment import ApiGatewayAssignmentRepository
from src.schemas.api_gateway_assignment import (
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentResponse,
)
from src.services.deployment_orchestration_service import DeploymentOrchestrationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/apis/{api_id}",
    tags=["API Deployments"],
)


# --- Gateway Assignments ---


@router.post("/gateway-assignments", response_model=AssignmentResponse, status_code=201)
async def create_assignment(
    tenant_id: str,
    api_id: UUID,
    data: AssignmentCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Assign a default gateway target for an API in a specific environment."""
    repo = ApiGatewayAssignmentRepository(db)

    assignment = ApiGatewayAssignment(
        api_id=api_id,
        gateway_id=data.gateway_id,
        environment=data.environment,
        auto_deploy=data.auto_deploy,
    )
    try:
        assignment = await repo.create(assignment)
        await db.commit()
        await db.refresh(assignment)
    except Exception as e:
        await db.rollback()
        if "uq_api_gateway_env" in str(e):
            raise HTTPException(
                status_code=409,
                detail="Assignment already exists for this API/gateway/environment",
            )
        raise

    return AssignmentResponse(
        id=assignment.id,
        api_id=assignment.api_id,
        gateway_id=assignment.gateway_id,
        environment=assignment.environment,
        auto_deploy=assignment.auto_deploy,
        created_at=assignment.created_at,
    )


@router.get("/gateway-assignments", response_model=AssignmentListResponse)
async def list_assignments(
    tenant_id: str,
    api_id: UUID,
    environment: str | None = Query(None, pattern="^(dev|staging|production)$"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin", "devops", "viewer"])),
):
    """List gateway assignments for an API, optionally filtered by environment."""
    repo = ApiGatewayAssignmentRepository(db)
    items = await repo.list_for_api(api_id, environment=environment)
    return AssignmentListResponse(items=items, total=len(items))


@router.delete("/gateway-assignments/{assignment_id}", status_code=204)
async def delete_assignment(
    tenant_id: str,
    api_id: UUID,
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Remove a gateway assignment."""
    repo = ApiGatewayAssignmentRepository(db)
    deleted = await repo.delete_by_id(assignment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Assignment not found")
    await db.commit()


# --- Environment-Aware Deployment ---


class DeployToEnvRequest(BaseModel):
    """Request to deploy an API to gateways in a specific environment."""

    environment: str = Field(pattern="^(dev|staging|production)$")
    gateway_ids: list[UUID] | None = None  # None = use auto-deploy assignments


@router.post("/deploy", status_code=201)
async def deploy_to_environment(
    tenant_id: str,
    api_id: UUID,
    data: DeployToEnvRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Deploy an API to gateways in a specific environment.

    Validates promotion prerequisites (staging/prod require active promotion).
    If gateway_ids is omitted, uses auto-deploy assignments for the environment.
    """
    svc = DeploymentOrchestrationService(db)
    try:
        deployments = await svc.deploy_api_to_env(
            api_catalog_id=api_id,
            environment=data.environment,
            gateway_ids=data.gateway_ids,
            deployed_by=getattr(user, "preferred_username", "system"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    return {
        "deployed": len(deployments),
        "environment": data.environment,
        "deployment_ids": [str(d.id) for d in deployments],
    }


@router.get("/deployable-environments")
async def get_deployable_environments(
    tenant_id: str,
    api_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin", "devops", "viewer"])),
):
    """Get environments where this API can be deployed.

    Dev is always available. Staging/prod require an active promotion.
    """
    svc = DeploymentOrchestrationService(db)
    environments = await svc.get_deployable_environments(api_id)
    return {"environments": environments}
