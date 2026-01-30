"""
Self-Service Logs Router (CAB-793)

Allows API consumers to view their own call logs in production
without opening support tickets.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import StreamingResponse

from ..auth import get_current_user, User
from ..core.pii import PIIMasker
from ..services.loki_client import loki_client
from ..services.consumer_logs_service import ConsumerLogsService
from ..schemas.logs import (
    LogQueryParams,
    LogQueryResponse,
    LogStatus,
    LogLevel,
)

router = APIRouter(
    prefix="/v1/logs",
    tags=["Logs"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
    },
)


def _get_logs_service(current_user: User = Depends(get_current_user)) -> ConsumerLogsService:
    pii_masker = PIIMasker.for_tenant(current_user.tenant_id)
    return ConsumerLogsService(loki_client, pii_masker)


@router.get(
    "/calls",
    response_model=LogQueryResponse,
    summary="Get my API call logs",
    description=(
        "Retrieve your own API call logs. "
        "You can only see logs for YOUR authenticated identity. "
        "All PII is automatically masked for RGPD compliance. "
        "Max time range: 24 hours. Max results per page: 100."
    ),
)
async def get_my_logs(
    logs_service: Annotated[ConsumerLogsService, Depends(_get_logs_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    start_time: Annotated[datetime | None, Query(description="Start time (ISO format)")] = None,
    end_time: Annotated[datetime | None, Query(description="End time (ISO format)")] = None,
    tool_id: Annotated[str | None, Query(description="Filter by tool/API ID")] = None,
    status_filter: Annotated[LogStatus, Query(alias="status", description="Filter by status")] = LogStatus.ALL,
    level: Annotated[LogLevel | None, Query(description="Filter by log level")] = None,
    search: Annotated[str | None, Query(max_length=200, description="Search in messages")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Results per page")] = 50,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
) -> LogQueryResponse:
    params = LogQueryParams(
        start_time=start_time,
        end_time=end_time,
        tool_id=tool_id,
        status=status_filter,
        level=level,
        search=search,
        limit=limit,
        offset=offset,
    )
    # SECURITY: user_id from token, NEVER from request
    return await logs_service.query_logs(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        params=params,
    )


@router.get(
    "/calls/export",
    summary="Export my logs as CSV",
    description="Export your API call logs as a CSV file. Max 24 hours, max 10,000 rows.",
    responses={200: {"content": {"text/csv": {}}, "description": "CSV file download"}},
)
async def export_my_logs(
    logs_service: Annotated[ConsumerLogsService, Depends(_get_logs_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    start_time: Annotated[datetime, Query(description="Start time (ISO format)")],
    end_time: Annotated[datetime, Query(description="End time (ISO format)")],
    tool_id: Annotated[str | None, Query(description="Filter by tool/API ID")] = None,
    status_filter: Annotated[LogStatus, Query(alias="status", description="Filter by status")] = LogStatus.ALL,
) -> StreamingResponse:
    csv_status = None if status_filter == LogStatus.ALL else status_filter.value
    csv_content = await logs_service.export_csv(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        start_time=start_time,
        end_time=end_time,
        tool_id=tool_id,
        status=csv_status,
    )
    filename = f"logs_{current_user.id}_{start_time.strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get(
    "/calls/{request_id}",
    response_model=dict,
    summary="Get single log entry by request ID",
)
async def get_log_by_request_id(
    request_id: str,
    logs_service: Annotated[ConsumerLogsService, Depends(_get_logs_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    params = LogQueryParams(search=request_id, limit=1)
    result = await logs_service.query_logs(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        params=params,
    )
    if not result.logs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log entry not found: {request_id}",
        )
    return result.logs[0].model_dump()
