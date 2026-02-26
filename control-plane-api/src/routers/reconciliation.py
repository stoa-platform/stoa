"""SCIM↔Gateway reconciliation API endpoints (CAB-1484)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.reconciliation import DriftReport, ReconciliationResult, ReconciliationStatus
from ..services.scim_gateway_reconciliation import ReconciliationService

router = APIRouter(prefix="/v1/tenants/{tenant_id}/reconciliation", tags=["reconciliation"])


def _get_service(db: AsyncSession = Depends(get_db)) -> ReconciliationService:
    return ReconciliationService(db=db)


@router.get("/drift", response_model=DriftReport)
async def check_drift(
    tenant_id: str,
    service: ReconciliationService = Depends(_get_service),
) -> DriftReport:
    """Check drift between SCIM clients and gateway consumers."""
    return await service.check_drift(tenant_id)


@router.post("/sync", response_model=ReconciliationResult)
async def trigger_reconciliation(
    tenant_id: str,
    service: ReconciliationService = Depends(_get_service),
) -> ReconciliationResult:
    """Trigger reconciliation — sync SCIM state to gateway."""
    return await service.reconcile(tenant_id)


@router.get("/status", response_model=ReconciliationStatus)
async def get_status(
    tenant_id: str,
    service: ReconciliationService = Depends(_get_service),
) -> ReconciliationStatus:
    """Get current reconciliation status for a tenant."""
    return await service.get_status(tenant_id)
