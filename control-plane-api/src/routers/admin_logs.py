"""
Admin Logs Router (CAB-2004)

Provides admin access to structured gateway/API/auth logs via Loki.
cpi-admin: all logs. tenant-admin: own tenant only.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import User, require_role
from ..core.pii import PIIMasker
from ..schemas.logs import AdminLogQueryResponse, LogLevel
from ..services.admin_logs_service import AdminLogsService
from ..services.loki_client import loki_client

router = APIRouter(
    prefix="/v1/admin/logs",
    tags=["Admin Logs"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
    },
)


def _get_admin_logs_service(
    user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
) -> tuple[AdminLogsService, User]:
    pii_masker = PIIMasker.for_tenant(user.tenant_id)
    return AdminLogsService(loki_client, pii_masker), user


@router.get(
    "",
    response_model=AdminLogQueryResponse,
    summary="Query structured logs (admin)",
    description=(
        "Query structured logs from Loki. "
        "cpi-admin sees all logs; tenant-admin sees own tenant only. "
        "Max time range: 24 hours."
    ),
)
async def get_admin_logs(
    svc_and_user: Annotated[
        tuple[AdminLogsService, User], Depends(_get_admin_logs_service)
    ],
    service: Annotated[
        str, Query(description="Service filter: gateway, api, auth, or all")
    ] = "all",
    level: Annotated[
        LogLevel | None, Query(description="Log level filter")
    ] = None,
    search: Annotated[
        str | None, Query(max_length=200, description="Free-text search")
    ] = None,
    start_time: Annotated[
        datetime | None, Query(description="Start time (ISO 8601)")
    ] = None,
    end_time: Annotated[
        datetime | None, Query(description="End time (ISO 8601)")
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=200, description="Max results (1-200)")
    ] = 50,
) -> AdminLogQueryResponse:
    svc, user = svc_and_user

    # Tenant-scoping: tenant-admin sees only own tenant
    tenant_id = None
    if "cpi-admin" not in user.roles:
        tenant_id = user.tenant_id

    try:
        result = await svc.query_logs(
            service=service,
            level=level,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            tenant_id=tenant_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Loki unavailable",
        )

    return result
