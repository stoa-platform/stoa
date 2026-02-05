"""API routes for gateway deployment management (cpi-admin)."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import require_role
from src.database import get_db
from src.models.gateway_deployment import DeploymentSyncStatus
from src.repositories.gateway_deployment import GatewayDeploymentRepository
from src.schemas.gateway import (
    DeploymentStatusSummary,
    GatewayDeploymentCreate,
    GatewayDeploymentResponse,
    PaginatedGatewayDeployments,
)
from src.services.gateway_deployment_service import GatewayDeploymentService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/admin/deployments",
    tags=["Gateway Deployments"],
)


@router.post("", response_model=list[GatewayDeploymentResponse], status_code=201)
async def deploy_api(
    data: GatewayDeploymentCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin"])),
):
    """Deploy an API to one or more gateways."""
    svc = GatewayDeploymentService(db)
    try:
        deployments = await svc.deploy_api(data.api_catalog_id, data.gateway_instance_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await db.commit()
    for dep in deployments:
        await db.refresh(dep)
    return deployments


@router.get("", response_model=PaginatedGatewayDeployments)
async def list_deployments(
    sync_status: str | None = Query(None, description="Filter by sync status"),
    gateway_instance_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """List all gateway deployments."""
    deploy_repo = GatewayDeploymentRepository(db)
    status_filter = DeploymentSyncStatus(sync_status) if sync_status else None
    items, total = await deploy_repo.list_all(
        sync_status=status_filter,
        gateway_instance_id=gateway_instance_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedGatewayDeployments(items=items, total=total, page=page, page_size=page_size)


@router.get("/status", response_model=DeploymentStatusSummary)
async def get_deployment_status(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Get sync status summary across all deployments."""
    deploy_repo = GatewayDeploymentRepository(db)
    counts = await deploy_repo.get_status_summary()
    return DeploymentStatusSummary(
        **counts,
        total=sum(counts.values()),
    )


@router.get("/catalog-entries")
async def list_catalog_entries(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin"])),
):
    """List API catalog entries for the deploy dialog."""
    from src.models.catalog import APICatalog

    result = await db.execute(
        select(APICatalog.id, APICatalog.api_name, APICatalog.tenant_id, APICatalog.version)
        .where(APICatalog.status == "active")
        .order_by(APICatalog.api_name)
        .limit(200)
    )
    rows = result.all()
    return [
        {"id": str(r.id), "api_name": r.api_name, "tenant_id": r.tenant_id, "version": r.version}
        for r in rows
    ]


@router.get("/{deployment_id}", response_model=GatewayDeploymentResponse)
async def get_deployment(
    deployment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Get deployment details."""
    deploy_repo = GatewayDeploymentRepository(db)
    deployment = await deploy_repo.get_by_id(deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


@router.delete("/{deployment_id}", status_code=204)
async def undeploy(
    deployment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin"])),
):
    """Undeploy an API from a gateway (marks for deletion)."""
    svc = GatewayDeploymentService(db)
    try:
        await svc.undeploy(deployment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()


@router.post("/{deployment_id}/sync", response_model=GatewayDeploymentResponse)
async def force_sync(
    deployment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin"])),
):
    """Force re-sync a deployment."""
    svc = GatewayDeploymentService(db)
    try:
        deployment = await svc.force_sync(deployment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    await db.refresh(deployment)
    return deployment
