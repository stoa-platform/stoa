"""API endpoints for error snapshots.

CAB-397: CRUD operations for viewing and managing error snapshots.
Routes with fixed paths (/stats, /filters) MUST be defined BEFORE
/{snapshot_id} to avoid path parameter capture.

Graceful degradation: when MinIO/S3 storage is unavailable (e.g., not
deployed), read endpoints return empty results instead of 500/503.
Write endpoints return 503 to clearly signal the storage is down.
"""

import logging
from datetime import datetime
from typing import Annotated, TypeGuard

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...auth.dependencies import User, get_current_user
from .models import (
    ErrorSnapshot,
    ReplayResponse,
    ResolutionStatus,
    ResolutionUpdate,
    SnapshotFilters,
    SnapshotFiltersResponse,
    SnapshotListResponse,
    SnapshotTrigger,
)
from .service import SnapshotService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/snapshots", tags=["Error Snapshots"])

# Dependency for getting snapshot service
_snapshot_service: SnapshotService | None = None


def set_snapshot_service(service: SnapshotService) -> None:
    """Set the snapshot service instance (called during app startup)."""
    global _snapshot_service
    _snapshot_service = service


def get_snapshot_service() -> SnapshotService | None:
    """Get snapshot service dependency.

    Returns None when storage is unavailable — endpoints handle graceful
    degradation by returning empty results for reads and 503 for writes.
    """
    return _snapshot_service


# ── Fixed-path routes (MUST come before /{snapshot_id}) ──────────────


@router.get("", response_model=SnapshotListResponse)
async def list_snapshots(
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    start_date: Annotated[datetime | None, Query(description="Filter: start date")] = None,
    end_date: Annotated[datetime | None, Query(description="Filter: end date")] = None,
    status_code: Annotated[int | None, Query(description="Filter: HTTP status code")] = None,
    trigger: Annotated[SnapshotTrigger | None, Query(description="Filter: trigger type")] = None,
    path_contains: Annotated[str | None, Query(description="Filter: path contains string")] = None,
    source: Annotated[str | None, Query(description="Filter: gateway source")] = None,
    resolution_status: Annotated[ResolutionStatus | None, Query(description="Filter: resolution status")] = None,
    user: User = Depends(get_current_user),
    service: SnapshotService | None = Depends(get_snapshot_service),
) -> SnapshotListResponse:
    """List error snapshots for the user's tenant.

    Returns empty list when storage is unavailable.
    """
    if service is None:
        return _empty_list_response(page, page_size)

    tenant_id = user.tenant_id or "unknown"

    filters = SnapshotFilters(
        start_date=start_date,
        end_date=end_date,
        status_code=status_code,
        trigger=trigger,
        path_contains=path_contains,
        source=source,
        resolution_status=resolution_status,
    )

    try:
        return await service.list(
            tenant_id=tenant_id,
            filters=filters,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.warning(f"snapshot_list_failed storage_error={e}")
        return _empty_list_response(page, page_size)


@router.get("/stats/summary")
async def get_snapshot_stats_summary(
    start_date: Annotated[datetime | None, Query(description="Start date for stats")] = None,
    end_date: Annotated[datetime | None, Query(description="End date for stats")] = None,
    user: User = Depends(get_current_user),
    service: SnapshotService | None = Depends(get_snapshot_service),
) -> dict:
    """Get snapshot statistics summary."""
    return await _compute_stats(start_date, end_date, user, service)


@router.get("/stats")
async def get_snapshot_stats(
    start_date: Annotated[datetime | None, Query(description="Start date for stats")] = None,
    end_date: Annotated[datetime | None, Query(description="End date for stats")] = None,
    user: User = Depends(get_current_user),
    service: SnapshotService | None = Depends(get_snapshot_service),
) -> dict:
    """Get snapshot statistics (alias for /stats/summary)."""
    return await _compute_stats(start_date, end_date, user, service)


@router.get("/filters", response_model=SnapshotFiltersResponse)
async def get_available_filters(
    user: User = Depends(get_current_user),
    service: SnapshotService | None = Depends(get_snapshot_service),
) -> SnapshotFiltersResponse:
    """Get available filter values for the UI.

    Returns empty filters when storage is unavailable.
    """
    if service is None:
        return _empty_filters_response()

    tenant_id = user.tenant_id or "unknown"

    try:
        filters = SnapshotFilters()
        result = await service.list(tenant_id, filters, page=1, page_size=1000)

        triggers: set[str] = set()
        sources: set[str] = set()
        status_codes: set[int] = set()
        resolution_statuses: set[str] = set()

        for item in result.items:
            triggers.add(item.trigger.value)
            sources.add(item.source)
            status_codes.add(item.status)
            resolution_statuses.add(item.resolution_status.value)

        # Always include all known resolution statuses
        for rs in ResolutionStatus:
            resolution_statuses.add(rs.value)

        return SnapshotFiltersResponse(
            triggers=sorted(triggers),
            sources=sorted(sources),
            status_codes=sorted(status_codes),
            resolution_statuses=sorted(resolution_statuses),
        )
    except Exception as e:
        logger.warning(f"snapshot_filters_failed storage_error={e}")
        return _empty_filters_response()


# ── Parameterized routes ──────────────────────────────────────────────


@router.get("/{snapshot_id}", response_model=ErrorSnapshot)
async def get_snapshot(
    snapshot_id: str,
    user: User = Depends(get_current_user),
    service: SnapshotService | None = Depends(get_snapshot_service),
) -> ErrorSnapshot:
    """Get detailed error snapshot by ID."""
    _require_service(service)

    tenant_id = user.tenant_id or "unknown"
    snapshot = await service.get(snapshot_id, tenant_id)

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot {snapshot_id} not found",
        )
    return snapshot


@router.patch("/{snapshot_id}", response_model=ErrorSnapshot)
async def update_snapshot_resolution(
    snapshot_id: str,
    body: ResolutionUpdate,
    user: User = Depends(get_current_user),
    service: SnapshotService | None = Depends(get_snapshot_service),
) -> ErrorSnapshot:
    """Update the resolution status of an error snapshot."""
    _require_service(service)

    tenant_id = user.tenant_id or "unknown"
    snapshot = await service.get(snapshot_id, tenant_id)

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot {snapshot_id} not found",
        )

    snapshot.resolution_status = body.resolution_status
    if body.resolution_notes is not None:
        snapshot.resolution_notes = body.resolution_notes

    await service.save(snapshot)
    return snapshot


@router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_snapshot(
    snapshot_id: str,
    user: User = Depends(get_current_user),
    service: SnapshotService | None = Depends(get_snapshot_service),
) -> None:
    """Delete an error snapshot."""
    _require_service(service)

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
    service: SnapshotService | None = Depends(get_snapshot_service),
) -> ReplayResponse:
    """Generate cURL command to replay the captured request."""
    _require_service(service)

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


# ── Helpers ───────────────────────────────────────────────────────────


def _require_service(service: SnapshotService | None) -> TypeGuard[SnapshotService]:
    """Raise 503 if service is unavailable (for write endpoints).

    Returns TypeGuard to help mypy understand service cannot be None after this call.
    """
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Error snapshot storage not available",
        )
    return True


def _empty_list_response(page: int = 1, page_size: int = 20) -> SnapshotListResponse:
    """Return an empty list response for graceful degradation."""
    return SnapshotListResponse(items=[], total=0, page=page, page_size=page_size)


def _empty_stats() -> dict:
    """Return empty stats for graceful degradation."""
    return {
        "total": 0,
        "by_trigger": {},
        "by_status_code": {},
        "resolution_stats": {
            "unresolved": 0,
            "investigating": 0,
            "resolved": 0,
            "ignored": 0,
        },
        "period": {"start": None, "end": None},
    }


def _empty_filters_response() -> SnapshotFiltersResponse:
    """Return default filters for graceful degradation."""
    return SnapshotFiltersResponse(
        triggers=["4xx", "5xx", "timeout"],
        sources=[],
        status_codes=[],
        resolution_statuses=sorted(rs.value for rs in ResolutionStatus),
    )


async def _compute_stats(
    start_date: datetime | None,
    end_date: datetime | None,
    user: User,
    service: SnapshotService | None,
) -> dict:
    """Shared stats computation for /stats and /stats/summary."""
    if service is None:
        return _empty_stats()

    tenant_id = user.tenant_id or "unknown"

    try:
        filters = SnapshotFilters(start_date=start_date, end_date=end_date)
        result = await service.list(tenant_id, filters, page=1, page_size=1000)
    except Exception as e:
        logger.warning(f"snapshot_stats_failed storage_error={e}")
        return _empty_stats()

    by_trigger: dict[str, int] = {}
    by_status: dict[int, int] = {}
    by_resolution: dict[str, int] = {
        "unresolved": 0,
        "investigating": 0,
        "resolved": 0,
        "ignored": 0,
    }

    for item in result.items:
        trigger_val = item.trigger.value
        by_trigger[trigger_val] = by_trigger.get(trigger_val, 0) + 1

        status_val = item.status
        by_status[status_val] = by_status.get(status_val, 0) + 1

        res_val = item.resolution_status.value
        by_resolution[res_val] = by_resolution.get(res_val, 0) + 1

    return {
        "total": result.total,
        "by_trigger": by_trigger,
        "by_status_code": by_status,
        "resolution_stats": by_resolution,
        "period": {
            "start": start_date.isoformat() if start_date else None,
            "end": end_date.isoformat() if end_date else None,
        },
    }
