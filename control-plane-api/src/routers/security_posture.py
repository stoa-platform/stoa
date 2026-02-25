"""Security Posture Dashboard endpoints (CAB-1461).

Provides REST API for:
- Security score (0-100) per tenant
- Findings CRUD (list, ingest, resolve)
- Scan management (create, history)
- Golden state drift detection
- Compliance scoring (DORA, NIS2)
- Secrets health tracking
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import User, get_current_user
from ..auth.rbac import require_tenant_access
from ..database import get_db
from ..schemas.security_posture import (
    FindingSeverity,
    IngestFindingsRequest,
    SetBaselineRequest,
)
from ..services.security_scanner_service import security_scanner_service

router = APIRouter(prefix="/v1/security", tags=["Security Posture"])


# --- Score ---


@router.get("/{tenant_id}/score")
@require_tenant_access
async def get_security_score(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current security score for a tenant."""
    return await security_scanner_service.calculate_score(tenant_id, db)


# --- Findings ---


@router.get("/{tenant_id}/findings")
@require_tenant_access
async def list_findings(
    tenant_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    severity: FindingSeverity | None = None,
    status: str | None = None,
    scanner: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List security findings with optional filters."""
    return await security_scanner_service.list_findings(
        tenant_id,
        db,
        page=page,
        page_size=page_size,
        severity=severity.value if severity else None,
        status=status,
        scanner=scanner,
    )


@router.post("/{tenant_id}/findings/ingest", status_code=201)
@require_tenant_access
async def ingest_findings(
    tenant_id: str,
    request: IngestFindingsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk ingest findings from a scanner. Requires cpi-admin or devops role."""
    count = await security_scanner_service.ingest_findings(
        tenant_id,
        request.scan_id,
        request.scanner.value,
        request.findings,
        db,
    )
    await db.commit()
    return {"ingested": count}


@router.post("/{tenant_id}/findings/{finding_id}/resolve")
@require_tenant_access
async def resolve_finding(
    tenant_id: str,
    finding_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a finding as resolved."""
    resolved = await security_scanner_service.resolve_finding(finding_id, db)
    if not resolved:
        raise HTTPException(status_code=404, detail="Finding not found")
    await db.commit()
    return {"status": "resolved"}


# --- Scans ---


@router.get("/{tenant_id}/scans")
@require_tenant_access
async def get_scan_history(
    tenant_id: str,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get scan history for a tenant."""
    return await security_scanner_service.get_scan_history(tenant_id, db, limit=limit)


@router.post("/{tenant_id}/scans", status_code=201)
@require_tenant_access
async def create_scan(
    tenant_id: str,
    scanner: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new scan record. Requires cpi-admin or devops role."""
    scan_id = await security_scanner_service.create_scan(tenant_id, scanner, db)
    await db.commit()
    return {"scan_id": scan_id}


# --- Drift Detection ---


@router.get("/{tenant_id}/drift")
@require_tenant_access
async def get_drift_report(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare current findings against golden state baseline."""
    return await security_scanner_service.detect_drift(tenant_id, db)


@router.put("/{tenant_id}/baseline")
@require_tenant_access
async def set_baseline(
    tenant_id: str,
    request: SetBaselineRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set or update golden state baseline for a tenant."""
    await security_scanner_service.set_baseline(tenant_id, request.baseline, db)
    await db.commit()
    return {"status": "baseline_updated"}


# --- Compliance ---


@router.get("/{tenant_id}/compliance/{framework}")
@require_tenant_access
async def get_compliance_score(
    tenant_id: str,
    framework: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get compliance score for a framework (DORA, NIS2)."""
    framework_upper = framework.upper()
    if framework_upper not in ("DORA", "NIS2"):
        raise HTTPException(status_code=400, detail="Unsupported framework. Use DORA or NIS2.")
    return await security_scanner_service.get_compliance_score(tenant_id, framework, db)


# --- Secrets Health ---


@router.get("/{tenant_id}/secrets/health")
@require_tenant_access
async def get_secrets_health(
    tenant_id: str,
    user: User = Depends(get_current_user),
):
    """Check secrets health via Infisical (graceful degradation)."""
    return await security_scanner_service.get_secrets_health(tenant_id)
