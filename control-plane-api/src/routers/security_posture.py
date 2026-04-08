"""Security Posture Dashboard endpoints (CAB-1461, CAB-438).

Provides REST API for:
- Security score (0-100) per tenant
- Findings CRUD (list, ingest, resolve)
- Scan management (create, history)
- Golden state drift detection
- Compliance scoring (DORA, NIS2)
- Secrets health tracking
- Token binding status (DPoP / mTLS)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel as _BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import User, get_current_user
from ..auth.rbac import require_tenant_access
from ..config import settings
from ..database import get_db
from ..opensearch.opensearch_integration import OpenSearchService
from ..schemas.security_posture import (
    FindingSeverity,
    IngestFindingsRequest,
    SetBaselineRequest,
)
from ..services.security_aggregation_service import security_aggregation_service
from ..services.security_scanner_service import security_scanner_service


class SecurityScoreResponse(_BaseModel):
    """Security score result."""

    score: int = 0
    grade: str = ""
    breakdown: dict = {}


class StatusResponse(_BaseModel):
    """Simple status response."""

    status: str


class CountResponse(_BaseModel):
    """Count response."""

    ingested: int = 0


class ScanIdResponse(_BaseModel):
    """Scan creation response."""

    scan_id: str


class TokenBindingResponse(_BaseModel):
    """Token binding status."""

    strategy: str
    label: str
    description: str
    dpop_enforced: bool = False
    mtls_enforced: bool = False
    dpop_available: bool = True
    mtls_available: bool = True
    replay_protection: bool = False


router = APIRouter(prefix="/v1/security", tags=["Security Posture"])


# --- Score ---


@router.get("/{tenant_id}/score")
@require_tenant_access
async def get_security_score(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current security score for a tenant (aggregated from all sources)."""
    os_client = None
    try:
        service = OpenSearchService.get_instance()
        if service.client:
            os_client = service.client
    except Exception:
        pass
    return await security_aggregation_service.calculate_aggregated_score(tenant_id, db, os_client)


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
    """List security findings from all sources (aggregated)."""
    os_client = None
    try:
        service = OpenSearchService.get_instance()
        if service.client:
            os_client = service.client
    except Exception:
        pass
    return await security_aggregation_service.list_aggregated_findings(
        tenant_id,
        db,
        os_client,
        page=page,
        page_size=page_size,
        severity=severity.value if severity else None,
        status=status,
        scanner=scanner,
    )


@router.post("/{tenant_id}/findings/ingest", status_code=201, response_model=CountResponse)
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


@router.post("/{tenant_id}/findings/{finding_id}/resolve", response_model=StatusResponse)
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


@router.post("/{tenant_id}/scans", status_code=201, response_model=ScanIdResponse)
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


@router.put("/{tenant_id}/baseline", response_model=StatusResponse)
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


# --- Token Binding (CAB-438) ---


@router.get("/{tenant_id}/token-binding", response_model=TokenBindingResponse)
@require_tenant_access
async def get_token_binding_status(
    tenant_id: str,
    user: User = Depends(get_current_user),
):
    """Get token binding configuration and status (DPoP / mTLS).

    Returns the current sender-constrained token strategy and
    a summary of binding modes available for this tenant.
    """
    strategy = settings.SENDER_CONSTRAINED_STRATEGY

    strategies_info = {
        "auto": {
            "label": "Auto (Migration)",
            "description": "Unbound tokens accepted. DPoP and mTLS validated when present.",
            "dpop_enforced": False,
            "mtls_enforced": False,
        },
        "require-any": {
            "label": "Require Any Binding",
            "description": "Tokens must be bound via either DPoP or mTLS.",
            "dpop_enforced": True,
            "mtls_enforced": True,
        },
        "mtls-only": {
            "label": "mTLS Only",
            "description": "Tokens must be certificate-bound (RFC 8705).",
            "dpop_enforced": False,
            "mtls_enforced": True,
        },
        "dpop-only": {
            "label": "DPoP Only",
            "description": "Tokens must include DPoP proof (RFC 9449).",
            "dpop_enforced": True,
            "mtls_enforced": False,
        },
    }

    info = strategies_info.get(strategy, strategies_info["auto"])

    return {
        "strategy": strategy,
        "label": info["label"],
        "description": info["description"],
        "dpop_enforced": info["dpop_enforced"],
        "mtls_enforced": info["mtls_enforced"],
        "dpop_available": True,
        "mtls_available": True,
        "replay_protection": strategy != "auto",
    }
