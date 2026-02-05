"""API routes for gateway instance management (cpi-admin)."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import require_role
from src.database import get_db
from src.schemas.gateway import (
    GatewayHealthCheckResponse,
    GatewayInstanceCreate,
    GatewayInstanceResponse,
    GatewayInstanceUpdate,
    PaginatedGatewayInstances,
)
from src.schemas.gateway_import import ImportPreviewResponse, ImportResultResponse
from src.services.gateway_import_service import GatewayImportService
from src.services.gateway_instance_service import GatewayInstanceService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/admin/gateways",
    tags=["Gateways"],
)


@router.post("", response_model=GatewayInstanceResponse, status_code=201)
async def register_gateway(
    data: GatewayInstanceCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin"])),
):
    """Register a new gateway instance."""
    svc = GatewayInstanceService(db)
    try:
        instance = await svc.create(data)
        await db.commit()
        return instance
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=PaginatedGatewayInstances)
async def list_gateways(
    gateway_type: str | None = Query(None, description="Filter by type"),
    environment: str | None = Query(None, description="Filter by environment"),
    tenant_id: str | None = Query(None, description="Filter by tenant"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """List all registered gateway instances."""
    svc = GatewayInstanceService(db)
    items, total = await svc.list(
        gateway_type=gateway_type,
        environment=environment,
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedGatewayInstances(items=items, total=total, page=page, page_size=page_size)


@router.get("/{gateway_id}", response_model=GatewayInstanceResponse)
async def get_gateway(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Get gateway instance details."""
    svc = GatewayInstanceService(db)
    instance = await svc.get_by_id(gateway_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Gateway instance not found")
    return instance


@router.put("/{gateway_id}", response_model=GatewayInstanceResponse)
async def update_gateway(
    gateway_id: UUID,
    data: GatewayInstanceUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin"])),
):
    """Update a gateway instance configuration."""
    svc = GatewayInstanceService(db)
    try:
        instance = await svc.update(gateway_id, data)
        await db.commit()
        return instance
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{gateway_id}", status_code=204)
async def delete_gateway(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin"])),
):
    """Deregister a gateway instance."""
    svc = GatewayInstanceService(db)
    try:
        await svc.delete(gateway_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{gateway_id}/health", response_model=GatewayHealthCheckResponse)
async def check_gateway_health(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Trigger a health check on a gateway instance."""
    svc = GatewayInstanceService(db)
    try:
        result = await svc.health_check(gateway_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{gateway_id}/import/preview",
    response_model=list[ImportPreviewResponse],
)
async def preview_import(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin"])),
):
    """Dry-run: preview what would be imported from a gateway."""
    svc = GatewayImportService(db)
    try:
        return await svc.preview_import(gateway_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/{gateway_id}/import",
    response_model=ImportResultResponse,
)
async def import_from_gateway(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin"])),
):
    """Import APIs from a gateway into the STOA catalog."""
    svc = GatewayImportService(db)
    try:
        result = await svc.import_from_gateway(gateway_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
