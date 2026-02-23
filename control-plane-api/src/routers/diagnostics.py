"""Diagnostic endpoints for auto-RCA and connectivity checks (CAB-1316)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import require_role
from src.database import get_db
from src.schemas.diagnostic import ConnectivityResult, DiagnosticListResponse, DiagnosticReport
from src.services.diagnostic_service import DiagnosticService

router = APIRouter(
    prefix="/v1/admin/diagnostics",
    tags=["Diagnostics"],
)


@router.get("/{gateway_id}", response_model=DiagnosticReport)
async def run_diagnostic(
    gateway_id: UUID,
    time_range_minutes: int = Query(default=60, ge=1, le=1440),
    request_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role(["cpi-admin", "tenant-admin"])),
) -> DiagnosticReport:
    """Run auto-RCA on recent errors for a gateway."""
    svc = DiagnosticService(db)
    tenant_id = user.get("tenant_id", "")
    return await svc.diagnose(
        tenant_id=tenant_id,
        gateway_id=str(gateway_id),
        request_id=request_id,
        time_range_minutes=time_range_minutes,
    )


@router.get("/{gateway_id}/connectivity", response_model=ConnectivityResult)
async def check_connectivity(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role(["cpi-admin", "tenant-admin"])),
) -> ConnectivityResult:
    """Test connectivity chain: DNS → TCP → TLS → HTTP health."""
    svc = DiagnosticService(db)
    tenant_id = user.get("tenant_id", "")
    return await svc.check_connectivity(tenant_id=tenant_id, gateway_id=str(gateway_id))


@router.get("/{gateway_id}/history", response_model=DiagnosticListResponse)
async def get_diagnostic_history(
    gateway_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role(["cpi-admin", "tenant-admin"])),
) -> DiagnosticListResponse:
    """Past diagnostic reports for a gateway."""
    svc = DiagnosticService(db)
    tenant_id = user.get("tenant_id", "")
    return await svc.get_history(tenant_id=tenant_id, gateway_id=str(gateway_id), limit=limit)
