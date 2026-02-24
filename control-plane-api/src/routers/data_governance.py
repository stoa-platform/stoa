"""Data governance router — source-of-truth matrix, drift report, reconciliation (CAB-1324).

Admin-only endpoints that provide a unified view of all governed entities,
their drift status, and the ability to trigger reconciliation.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import User
from src.auth.rbac import require_role
from src.database import get_db
from src.schemas.data_governance import (
    DriftReportResponse,
    GovernanceMatrixResponse,
    ReconcileRequest,
    ReconcileResponse,
)
from src.services.data_governance_service import DataGovernanceService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/admin/governance",
    tags=["Data Governance"],
)

VALID_ENTITY_TYPES = {"api_catalog", "mcp_servers", "gateway_deployments"}


@router.get("/matrix", response_model=GovernanceMatrixResponse)
async def get_governance_matrix(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["cpi-admin"])),
) -> GovernanceMatrixResponse:
    """Return the full governance matrix with live drift counts.

    Classifies every governed entity type by source-of-truth, sync direction,
    and current drift status.  Admin-only (cpi-admin).
    """
    svc = DataGovernanceService(db)
    return await svc.get_governance_matrix()


@router.get("/drift", response_model=DriftReportResponse)
async def get_drift_report(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["cpi-admin"])),
) -> DriftReportResponse:
    """Cross-entity drift report with per-item details.

    Lists every drifted item across all governed entity types: orphan MCP
    servers, never-synced APIs, drifted gateway deployments, etc.
    Limited to 50 items per entity type.  Admin-only (cpi-admin).
    """
    svc = DataGovernanceService(db)
    return await svc.get_drift_report()


@router.post("/reconcile/{entity_type}", response_model=ReconcileResponse)
async def reconcile_entity(
    entity_type: str = Path(description="Entity type to reconcile"),
    body: ReconcileRequest = ReconcileRequest(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["cpi-admin"])),
) -> ReconcileResponse:
    """Trigger reconciliation for a specific entity type.

    By default runs in dry_run mode (preview only).  Set `dry_run: false`
    in the request body to apply changes.

    Supported entity types: api_catalog, mcp_servers, gateway_deployments.
    Admin-only (cpi-admin).
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity type '{entity_type}'. Valid: {sorted(VALID_ENTITY_TYPES)}",
        )

    logger.info(
        "User %s triggered reconciliation for %s (dry_run=%s)",
        user.username,
        entity_type,
        body.dry_run,
    )

    svc = DataGovernanceService(db)
    return await svc.reconcile(entity_type, dry_run=body.dry_run)
