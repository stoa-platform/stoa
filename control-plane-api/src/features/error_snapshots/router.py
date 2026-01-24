"""API endpoints for error snapshots.

CAB-397: CRUD operations for viewing and managing error snapshots.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...auth.dependencies import User, get_current_user
from .config import SnapshotSettings, get_snapshot_settings
from .models import (
    ErrorSnapshot,
    ReplayResponse,
    SnapshotFilters,
    SnapshotListResponse,
    SnapshotTrigger,
)
from .service import SnapshotService
from .storage import SnapshotStorage

router = APIRouter(prefix="/v1/snapshots", tags=["Error Snapshots"])

# Dependency for getting snapshot service
_snapshot_service: SnapshotService | None = None


def set_snapshot_service(service: SnapshotService) -> None:
    """Set the snapshot service instance (called during app startup)."""
    global _snapshot_service
    _snapshot_service = service


def get_snapshot_service() -> SnapshotService:
    """Get snapshot service dependency."""
    if _snapshot_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Error snapshot service not initialized",
        )
    return _snapshot_service


@router.get("", response_model=SnapshotListResponse)
async def list_snapshots(
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page")
    ] = 20,
    start_date: Annotated[
        datetime | None, Query(description="Filter: start date")
    ] = None,
    end_date: Annotated[
        datetime | None, Query(description="Filter: end date")
    ] = None,
    status_code: Annotated[
        int | None, Query(description="Filter: HTTP status code")
    ] = None,
    trigger: Annotated[
        SnapshotTrigger | None, Query(description="Filter: trigger type")
    ] = None,
    path_contains: Annotated[
        str | None, Query(description="Filter: path contains string")
    ] = None,
    user: User = Depends(get_current_user),
    service: SnapshotService = Depends(get_snapshot_service),
) -> SnapshotListResponse:
    """List error snapshots for the user's tenant.

    Supports filtering by:
    - Date range (start_date, end_date)
    - HTTP status code
    - Trigger type (4xx, 5xx, timeout, manual)
    - Path substring

    Results are paginated and sorted by timestamp (newest first).
    """
    # Use user's tenant_id for isolation
    tenant_id = user.tenant_id or "unknown"

    filters = SnapshotFilters(
        start_date=start_date,
        end_date=end_date,
        status_code=status_code,
        trigger=trigger,
        path_contains=path_contains,
    )

    return await service.list(
        tenant_id=tenant_id,
        filters=filters,
        page=page,
        page_size=page_size,
    )


@router.get("/{snapshot_id}", response_model=ErrorSnapshot)
async def get_snapshot(
    snapshot_id: str,
    user: User = Depends(get_current_user),
    service: SnapshotService = Depends(get_snapshot_service),
) -> ErrorSnapshot:
    """Get detailed error snapshot by ID.

    Returns the complete snapshot including:
    - Request/response data (with PII masked)
    - Routing and policy information
    - Backend state
    - Captured logs
    - Environment information

    Access is restricted to the user's tenant.
    """
    tenant_id = user.tenant_id or "unknown"

    snapshot = await service.get(snapshot_id, tenant_id)

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot {snapshot_id} not found",
        )

    return snapshot


@router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_snapshot(
    snapshot_id: str,
    user: User = Depends(get_current_user),
    service: SnapshotService = Depends(get_snapshot_service),
) -> None:
    """Delete an error snapshot.

    Permanently removes the snapshot from storage.
    Access is restricted to the user's tenant.
    """
    tenant_id = user.tenant_id or "unknown"

    deleted = await service.delete(snapshot_id, tenant_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot {snapshot_id} not found",
        )


@router.post("/{snapshot_id}/replay", response_model=ReplayResponse)
async def generate_replay(
    snapshot_id: str,
    user: User = Depends(get_current_user),
    service: SnapshotService = Depends(get_snapshot_service),
) -> ReplayResponse:
    """Generate cURL command to replay the captured request.

    Returns a cURL command that can be used to replay the original
    request. Note that sensitive data (Authorization headers, etc.)
    will show as [REDACTED] in the generated command.

    Access is restricted to the user's tenant.
    """
    tenant_id = user.tenant_id or "unknown"

    snapshot = await service.get(snapshot_id, tenant_id)

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot {snapshot_id} not found",
        )

    curl_command = service.generate_replay_curl(snapshot)

    return ReplayResponse(
        curl_command=curl_command,
        warning=(
            "Sensitive data has been masked with [REDACTED]. "
            "You may need to provide actual credentials to replay the request."
            if snapshot.masked_fields
            else None
        ),
    )


@router.get("/stats/summary")
async def get_snapshot_stats(
    start_date: Annotated[
        datetime | None, Query(description="Start date for stats")
    ] = None,
    end_date: Annotated[
        datetime | None, Query(description="End date for stats")
    ] = None,
    user: User = Depends(get_current_user),
    service: SnapshotService = Depends(get_snapshot_service),
) -> dict:
    """Get snapshot statistics summary.

    Returns counts by trigger type and status code.
    """
    tenant_id = user.tenant_id or "unknown"

    # Get all snapshots for the period
    filters = SnapshotFilters(start_date=start_date, end_date=end_date)
    result = await service.list(tenant_id, filters, page=1, page_size=1000)

    # Calculate stats
    by_trigger: dict[str, int] = {}
    by_status: dict[int, int] = {}

    for item in result.items:
        trigger = item.trigger.value
        by_trigger[trigger] = by_trigger.get(trigger, 0) + 1

        status = item.status
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "total": result.total,
        "by_trigger": by_trigger,
        "by_status_code": by_status,
        "period": {
            "start": start_date.isoformat() if start_date else None,
            "end": end_date.isoformat() if end_date else None,
        },
    }
