"""API routes for gateway instance management (cpi-admin)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import require_role
from src.database import get_db
from src.models.gateway_instance import GatewayInstance, GatewayInstanceStatus
from src.schemas.gateway import (
    GatewayHealthCheckResponse,
    GatewayInstanceCreate,
    GatewayInstanceResponse,
    GatewayInstanceUpdate,
    GatewayModeStats,
    ModeStatItem,
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
    include_deleted: bool = Query(False, description="Include soft-deleted gateways (cpi-admin only)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """List all registered gateway instances."""
    # Only cpi-admin can see deleted gateways
    show_deleted = include_deleted and "cpi-admin" in user.roles
    svc = GatewayInstanceService(db)
    items, total = await svc.list(
        gateway_type=gateway_type,
        environment=environment,
        tenant_id=tenant_id,
        include_deleted=show_deleted,
        page=page,
        page_size=page_size,
    )
    return PaginatedGatewayInstances(items=items, total=total, page=page, page_size=page_size)


@router.get("/modes/stats", response_model=GatewayModeStats)
async def get_gateway_mode_stats(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Get gateway statistics grouped by mode (ADR-024).

    Returns counts of online/offline/degraded gateways for each STOA mode:
    - edge-mcp: MCP protocol with SSE transport
    - sidecar: Policy enforcement behind existing gateway
    - proxy: Inline request/response transformation
    - shadow: Passive traffic capture and analysis
    - connect: Lightweight agent bridging third-party gateways
    """
    # Query aggregated stats by mode for STOA gateways
    stmt = (
        select(
            GatewayInstance.mode,
            func.count(GatewayInstance.id).label("total"),
            func.count(case((GatewayInstance.status == GatewayInstanceStatus.ONLINE, 1))).label("online"),
            func.count(case((GatewayInstance.status == GatewayInstanceStatus.OFFLINE, 1))).label("offline"),
            func.count(case((GatewayInstance.status == GatewayInstanceStatus.DEGRADED, 1))).label("degraded"),
        )
        .where(
            GatewayInstance.gateway_type.cast(String).like("stoa%"),
            GatewayInstance.deleted_at.is_(None),
        )
        .group_by(GatewayInstance.mode)
    )

    result = await db.execute(stmt)
    rows = result.all()

    # Build response with all 5 modes (even if count is 0)
    mode_data = {row.mode: row for row in rows if row.mode}
    all_modes = ["edge-mcp", "sidecar", "proxy", "shadow", "connect"]

    modes = []
    total_gateways = 0
    for mode in all_modes:
        if mode in mode_data:
            row = mode_data[mode]
            modes.append(
                ModeStatItem(
                    mode=mode,
                    total=row.total,
                    online=row.online,
                    offline=row.offline,
                    degraded=row.degraded,
                )
            )
            total_gateways += row.total
        else:
            modes.append(ModeStatItem(mode=mode, total=0, online=0, offline=0, degraded=0))

    return GatewayModeStats(modes=modes, total_gateways=total_gateways)


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


@router.get("/{gateway_id}/tools")
async def get_gateway_tools(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin", "devops", "viewer"])),
):
    """Proxy to gateway's MCP tools list endpoint.

    Fetches the live tool list from the gateway's /mcp/v1/tools endpoint.
    Returns 503 if the gateway is OFFLINE, 502 if unreachable.
    """
    import httpx

    svc = GatewayInstanceService(db)
    instance = await svc.get_by_id(gateway_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Gateway instance not found")

    if instance.status == GatewayInstanceStatus.OFFLINE:
        raise HTTPException(status_code=503, detail="Gateway is offline")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{instance.base_url}/mcp/v1/tools")
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=502, detail="Gateway did not respond within 5s")
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Gateway is unreachable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Gateway returned {e.response.status_code}")
    except Exception as e:
        logger.error("Failed to proxy tools for gateway %s: %s", gateway_id, e)
        raise HTTPException(status_code=502, detail=f"Gateway error: {e!s}")


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
    """Soft-delete a gateway instance. Protected gateways cannot be deleted."""
    svc = GatewayInstanceService(db)
    try:
        await svc.delete(gateway_id, deleted_by=user.id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{gateway_id}/restore", response_model=GatewayInstanceResponse)
async def restore_gateway(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin"])),
):
    """Restore a soft-deleted gateway instance."""
    svc = GatewayInstanceService(db)
    try:
        instance = await svc.restore(gateway_id)
        await db.commit()
        return instance
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
