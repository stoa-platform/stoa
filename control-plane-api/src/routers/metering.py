"""Usage Metering Router — admin-facing aggregated usage endpoints (CAB-1334 Phase 1).

Routes:
- GET /v1/metering/summary — Aggregated usage summary per tenant
- GET /v1/metering/details — Detailed usage breakdown with pagination
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import User
from src.auth.rbac import require_role
from src.database import get_db
from src.schemas.metering import UsageDetailResponse, UsageSummary
from src.services.usage_service import UsageMeteringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/metering", tags=["Metering"])


@router.get("/summary", response_model=UsageSummary)
async def get_usage_summary(
    period_type: str = Query(default="daily", pattern="^(hourly|daily|monthly)$"),
    start: datetime = Query(...),
    end: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
) -> UsageSummary:
    """Aggregated usage metrics across tools for a tenant or platform-wide.

    CPI admin sees all tenants; tenant-admin sees only own tenant.
    """
    tenant_id = user.tenant_id or ""
    svc = UsageMeteringService(db)
    return await svc.get_summary(
        tenant_id=tenant_id,
        period_type=period_type,
        start=start,
        end=end,
    )


@router.get("/details", response_model=UsageDetailResponse)
async def get_usage_details(
    period_type: str = Query(default="daily", pattern="^(hourly|daily|monthly)$"),
    start: datetime = Query(...),
    end: datetime = Query(...),
    tool_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
) -> UsageDetailResponse:
    """Detailed per-period usage records with optional tool filter.

    CPI admin sees all tenants; tenant-admin sees only own tenant.
    """
    tenant_id = user.tenant_id or ""
    svc = UsageMeteringService(db)
    return await svc.get_details(
        tenant_id=tenant_id,
        period_type=period_type,
        start=start,
        end=end,
        tool_name=tool_name,
        limit=limit,
        offset=offset,
    )
