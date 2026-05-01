"""API routes for gateway deployment management (cpi-admin)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import require_role
from src.database import get_db
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.repositories.gateway_deployment import GatewayDeploymentRepository
from src.schemas.gateway import (
    DeploymentStatusSummary,
    GatewayDeploymentCreate,
    GatewayDeploymentResponse,
    PaginatedConsoleDeployments,
    PaginatedGatewayDeployments,
)
from src.services.deployment_orchestration_service import DeploymentOrchestrationService
from src.services.gateway_deployment_service import GatewayDeploymentService

logger = logging.getLogger(__name__)


def _deployment_to_dict(dep) -> dict:
    """Convert a GatewayDeployment ORM object to a dict compatible with GatewayDeploymentResponse."""
    desired_state = dep.desired_state or {}
    return {
        "id": dep.id,
        "api_catalog_id": dep.api_catalog_id,
        "gateway_instance_id": dep.gateway_instance_id,
        "desired_state": desired_state,
        "desired_source": desired_state.get("desired_source"),
        "git_sync_status": desired_state.get("git_sync_status"),
        "desired_commit_sha": desired_state.get("desired_commit_sha"),
        "desired_git_path": desired_state.get("desired_git_path"),
        "desired_at": dep.desired_at,
        "actual_state": dep.actual_state,
        "actual_at": dep.actual_at,
        "sync_status": dep.sync_status.value if hasattr(dep.sync_status, "value") else dep.sync_status,
        "last_sync_attempt": dep.last_sync_attempt,
        "last_sync_success": dep.last_sync_success,
        "sync_error": dep.sync_error,
        "sync_attempts": dep.sync_attempts,
        "sync_steps": dep.sync_steps,
        "gateway_resource_id": dep.gateway_resource_id,
        "created_at": dep.created_at,
        "updated_at": dep.updated_at,
        "gateway_name": None,
        "gateway_display_name": None,
        "gateway_type": None,
        "gateway_environment": None,
    }


class CatalogEntry(BaseModel):
    """API catalog entry for deploy dialog."""

    id: str
    api_name: str
    tenant_id: str
    version: str | None = None


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
    """Deploy an API to one or more gateways. Rejects if any target gateway is disabled (409)."""
    orch = DeploymentOrchestrationService(db)
    try:
        preflight = await orch.preflight_api_to_gateways(data.api_catalog_id, data.gateway_instance_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    failed = [result for result in preflight if not result.deployable]
    if failed:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "deployment_preflight_failed",
                "message": "Deployment preflight failed before GatewayDeployment creation",
                "targets": [result.as_dict() for result in failed],
            },
        )

    svc = GatewayDeploymentService(db)
    try:
        deployments = await svc.deploy_api(data.api_catalog_id, data.gateway_instance_ids)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await db.commit()
    for dep in deployments:
        await db.refresh(dep)
    return [_deployment_to_dict(dep) for dep in deployments]


@router.get("", response_model=PaginatedGatewayDeployments)
async def list_deployments(
    sync_status: str | None = Query(None, description="Filter by sync status"),
    gateway_instance_id: UUID | None = Query(None),
    environment: str | None = Query(None, description="Filter by gateway environment (dev/staging/prod)"),
    gateway_type: str | None = Query(None, description="Filter by gateway type (stoa, kong, gravitee, etc.)"),
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
        environment=environment,
        gateway_type=gateway_type,
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


@router.get("/console", response_model=PaginatedConsoleDeployments)
async def list_console_deployments(
    environment: str | None = Query(None, description="Filter by gateway environment (dev/staging/production)"),
    gateway_instance_id: UUID | None = Query(None),
    tenant_id: str | None = Query(None, description="Filter by API tenant id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """List the aggregated Console contract for /api-deployments.

    This endpoint intentionally exposes deployment status and gateway health as
    separate fields so transient gateway connectivity does not overwrite the
    runtime reconciliation state.
    """
    deploy_repo = GatewayDeploymentRepository(db)
    items, total = await deploy_repo.list_console_contract(
        environment=environment,
        gateway_instance_id=gateway_instance_id,
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedConsoleDeployments(items=items, total=total, page=page, page_size=page_size)


@router.get("/catalog-entries", response_model=list[CatalogEntry])
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
    return [{"id": str(r.id), "api_name": r.api_name, "tenant_id": r.tenant_id, "version": r.version} for r in rows]


@router.get("/{deployment_id}", response_model=GatewayDeploymentResponse)
async def get_deployment(
    deployment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Get deployment details with gateway info."""
    from src.models.gateway_instance import GatewayInstance

    result = await db.execute(
        select(
            GatewayDeployment,
            GatewayInstance.name.label("gateway_name"),
            GatewayInstance.display_name.label("gateway_display_name"),
            GatewayInstance.gateway_type.label("gateway_type"),
            GatewayInstance.environment.label("gateway_environment"),
        )
        .join(GatewayInstance, GatewayDeployment.gateway_instance_id == GatewayInstance.id)
        .where(GatewayDeployment.id == deployment_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Deployment not found")

    dep = row.GatewayDeployment
    d = _deployment_to_dict(dep)
    d["gateway_name"] = row.gateway_name
    d["gateway_display_name"] = row.gateway_display_name
    d["gateway_type"] = row.gateway_type.value if hasattr(row.gateway_type, "value") else row.gateway_type
    d["gateway_environment"] = row.gateway_environment
    return d


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
    return _deployment_to_dict(deployment)


class TestResult(BaseModel):
    """Result of a deployment connectivity test."""

    reachable: bool
    status_code: int | None = None
    latency_ms: float | None = None
    error: str | None = None
    gateway_url: str | None = None
    path: str | None = None


@router.post("/{deployment_id}/test", response_model=TestResult)
async def test_deployment(
    deployment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Test that a deployment is actually reachable through its gateway.

    Sends a HEAD request to the gateway at the expected API path and
    reports back status code, latency, and any errors.
    """
    import time

    import httpx

    from src.models.gateway_instance import GatewayInstance
    from src.services.credential_resolver import (
        _PULL_MODEL_GATEWAY_TYPES,
        AGENT_MANAGED_MESSAGE,
    )

    result = await db.execute(
        select(
            GatewayDeployment,
            GatewayInstance.base_url,
            GatewayInstance.auth_config,
            GatewayInstance.source,
            GatewayInstance.gateway_type,
        )
        .join(GatewayInstance, GatewayDeployment.gateway_instance_id == GatewayInstance.id)
        .where(GatewayDeployment.id == deployment_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Deployment not found")

    dep = row.GatewayDeployment
    base_url = row.base_url
    auth_config = row.auth_config or {}
    gw_type = row.gateway_type.value if hasattr(row.gateway_type, "value") else str(row.gateway_type)

    if row.source == "self_register" and gw_type in _PULL_MODEL_GATEWAY_TYPES:
        return TestResult(reachable=False, error=AGENT_MANAGED_MESSAGE, gateway_url=base_url)

    ds = dep.desired_state or {}
    tenant_id = ds.get("tenant_id", "")
    api_name = ds.get("api_name", ds.get("api_id", ""))
    path = f"/apis/{tenant_id}/{api_name}"

    headers = {}
    admin_token = auth_config.get("admin_token", "") if isinstance(auth_config, dict) else ""
    if admin_token:
        headers["Authorization"] = f"Bearer {admin_token}"

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}{path}", headers=headers)
        latency = (time.monotonic() - start) * 1000

        return TestResult(
            reachable=resp.status_code < 400,
            status_code=resp.status_code,
            latency_ms=round(latency, 1),
            gateway_url=base_url,
            path=path,
        )
    except Exception as e:
        error_msg = str(e) or f"{type(e).__name__}"
        return TestResult(
            reachable=False,
            error=error_msg,
            gateway_url=base_url,
            path=path,
        )
