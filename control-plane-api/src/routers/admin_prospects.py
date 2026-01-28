# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Admin Prospects API Router - Dashboard for conversion tracking (CAB-911).

Provides endpoints for the admin prospects dashboard:
- List prospects with filters and pagination
- Get detailed prospect info with timeline
- Get aggregated KPIs and metrics
- Export prospects to CSV

All endpoints require the `cpi-admin` role.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import User, get_current_user
from ..database import get_db
from ..schemas.prospects import (
    ProspectDetail,
    ProspectListResponse,
    ProspectsMetricsResponse,
)
from ..services import prospects_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin/prospects", tags=["Admin Prospects"])


def _require_admin(user: User) -> None:
    """Require cpi-admin role for access.

    Only platform admins can view prospect data (not tenant-admins).
    This protects sensitive lead/conversion data.
    """
    if "cpi-admin" not in user.roles:
        raise HTTPException(
            status_code=403,
            detail="Platform admin access required",
        )


@router.get("", response_model=ProspectListResponse)
async def list_prospects(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company: Optional[str] = Query(
        None,
        description="Filter by company name (partial match, case-insensitive)",
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by status (pending, opened, converted, expired)",
    ),
    date_from: Optional[datetime] = Query(
        None,
        description="Filter invites created after this date (ISO8601)",
    ),
    date_to: Optional[datetime] = Query(
        None,
        description="Filter invites created before this date (ISO8601)",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(25, ge=1, le=100, description="Items per page"),
):
    """List prospects with filters and pagination.

    Returns a paginated list of prospects with their current status,
    NPS score (if submitted), and event counts.

    **Requires**: `cpi-admin` role
    """
    _require_admin(user)
    logger.info(
        f"Admin {user.email} listing prospects: company={company}, status={status}, page={page}"
    )

    return await prospects_service.list_prospects(
        db,
        company=company,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )


@router.get("/metrics", response_model=ProspectsMetricsResponse)
async def get_metrics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    date_from: Optional[datetime] = Query(
        None,
        description="Filter invites created after this date",
    ),
    date_to: Optional[datetime] = Query(
        None,
        description="Filter invites created before this date",
    ),
):
    """Get aggregated KPIs for the prospects dashboard.

    Returns:
    - Conversion funnel (invited → opened → converted)
    - NPS distribution and score
    - Timing metrics (avg time to first tool)
    - Top companies by invite count

    **Requires**: `cpi-admin` role
    """
    _require_admin(user)
    logger.info(f"Admin {user.email} fetching prospects metrics")

    return await prospects_service.get_metrics(
        db,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/export")
async def export_prospects(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    """Export prospects to CSV file.

    Downloads a CSV file with all prospects matching the filters.
    The file includes: email, company, status, source, dates,
    time-to-tool metrics, and NPS feedback.

    **Requires**: `cpi-admin` role
    """
    _require_admin(user)
    logger.info(f"Admin {user.email} exporting prospects to CSV")

    csv_content = await prospects_service.export_prospects_csv(
        db,
        company=company,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )

    filename = f"prospects_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/{invite_id}", response_model=ProspectDetail)
async def get_prospect(
    invite_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed prospect info with timeline.

    Returns full prospect details including:
    - Basic info (email, company, status)
    - NPS feedback (if submitted)
    - Calculated metrics (time-to-tool, session duration)
    - Event timeline (last 50 events)
    - Error events (separated for easy viewing)

    **Requires**: `cpi-admin` role
    """
    _require_admin(user)
    logger.info(f"Admin {user.email} viewing prospect {invite_id}")

    prospect = await prospects_service.get_prospect_detail(db, invite_id)
    if not prospect:
        raise HTTPException(
            status_code=404,
            detail="Prospect not found",
        )

    return prospect
