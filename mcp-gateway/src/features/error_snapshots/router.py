"""
MCP Error Snapshot API Router

REST endpoints for error snapshot management.

Reference: CAB-397 - Error Snapshot / Flight Recorder (Time-Travel Debugging)
"""

from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...services.database import get_session
from ...models.error_snapshot import ResolutionStatus
from .repository import ErrorSnapshotRepository
from .models import MCPErrorType

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/mcp/v1/errors/snapshots", tags=["Error Snapshots"])


# Response models
class SnapshotSummary(BaseModel):
    """Summary view of an error snapshot for list responses."""
    id: str
    timestamp: str
    error_type: str
    error_message: str
    response_status: int
    mcp_server_name: Optional[str] = None
    tool_name: Optional[str] = None
    total_cost_usd: float
    tokens_wasted: int
    resolution_status: str


class SnapshotListResponse(BaseModel):
    """Response for list endpoint."""
    snapshots: list[SnapshotSummary]
    total: int
    page: int
    page_size: int
    has_next: bool


class SnapshotStats(BaseModel):
    """Aggregated statistics for snapshots."""
    total: int
    by_error_type: dict[str, int]
    by_status: dict[int, int]
    by_server: dict[str, int]
    total_cost_usd: float
    total_tokens_wasted: int
    avg_cost_usd: float
    resolution_stats: dict[str, int]


class ResolutionUpdate(BaseModel):
    """Request model for updating resolution status."""
    resolution_status: str = Field(..., description="New resolution status")
    resolution_notes: Optional[str] = Field(None, description="Notes about the resolution")


class ReplayResponse(BaseModel):
    """Response for replay command generation."""
    curl_command: str
    warning: Optional[str] = None


class FiltersResponse(BaseModel):
    """Available filter values."""
    error_types: list[str]
    servers: list[str]
    tools: list[str]
    resolution_statuses: list[str]


@router.get("", response_model=SnapshotListResponse)
async def list_snapshots(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    error_type: list[str] = Query(default=[], description="Filter by error types"),
    status_code: list[int] = Query(default=[], description="Filter by HTTP status codes"),
    server_name: list[str] = Query(default=[], description="Filter by MCP server names"),
    tool_name: list[str] = Query(default=[], description="Filter by tool names"),
    resolution_status: list[str] = Query(default=[], description="Filter by resolution status"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    min_cost_usd: Optional[float] = Query(None, ge=0, description="Minimum cost filter"),
    search: Optional[str] = Query(None, description="Search in error message, tool, server"),
    session: AsyncSession = Depends(get_session),
):
    """List error snapshots with filters and pagination."""
    repo = ErrorSnapshotRepository(session)

    snapshots, total = await repo.list(
        page=page,
        page_size=page_size,
        error_types=error_type if error_type else None,
        status_codes=status_code if status_code else None,
        server_names=server_name if server_name else None,
        tool_names=tool_name if tool_name else None,
        resolution_statuses=resolution_status if resolution_status else None,
        start_date=start_date,
        end_date=end_date,
        min_cost_usd=min_cost_usd,
        search=search,
    )

    return SnapshotListResponse(
        snapshots=[SnapshotSummary(**s.to_summary_dict()) for s in snapshots],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
    )


@router.get("/stats", response_model=SnapshotStats)
async def get_stats(
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    session: AsyncSession = Depends(get_session),
):
    """Get aggregated error statistics."""
    repo = ErrorSnapshotRepository(session)

    stats = await repo.get_stats(
        start_date=start_date,
        end_date=end_date,
    )

    return SnapshotStats(**stats)


@router.get("/filters", response_model=FiltersResponse)
async def get_filters(
    session: AsyncSession = Depends(get_session),
):
    """Get available filter values for the UI."""
    repo = ErrorSnapshotRepository(session)

    servers = await repo.get_distinct_servers()
    tools = await repo.get_distinct_tools()

    return FiltersResponse(
        error_types=[e.value for e in MCPErrorType],
        servers=servers,
        tools=tools,
        resolution_statuses=[s.value for s in ResolutionStatus],
    )


@router.get("/{snapshot_id}")
async def get_snapshot(
    snapshot_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get full error snapshot details."""
    repo = ErrorSnapshotRepository(session)

    snapshot = await repo.get_by_id(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return snapshot.to_full_dict()


@router.patch("/{snapshot_id}")
async def update_resolution(
    snapshot_id: str,
    update: ResolutionUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update snapshot resolution status."""
    repo = ErrorSnapshotRepository(session)

    # Validate resolution status
    try:
        status = ResolutionStatus(update.resolution_status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resolution status. Must be one of: {[s.value for s in ResolutionStatus]}",
        )

    snapshot = await repo.update_resolution(
        snapshot_id=snapshot_id,
        status=status,
        notes=update.resolution_notes,
    )

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return snapshot.to_full_dict()


@router.delete("/{snapshot_id}", status_code=204)
async def delete_snapshot(
    snapshot_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete an error snapshot."""
    repo = ErrorSnapshotRepository(session)

    deleted = await repo.delete(snapshot_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Snapshot not found")


@router.post("/{snapshot_id}/replay", response_model=ReplayResponse)
async def generate_replay(
    snapshot_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Generate cURL command to replay the request."""
    repo = ErrorSnapshotRepository(session)

    snapshot = await repo.get_by_id(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Extract request details from snapshot_data
    data = snapshot.snapshot_data
    request = data.get("request", {})

    method = request.get("method", "GET")
    path = request.get("path", "/")
    headers = request.get("headers", {})
    query_params = request.get("query_params", {})

    # Build URL with query params (properly encoded)
    url = f"https://mcp.gostoa.dev{path}"
    if query_params:
        url = f"{url}?{urlencode(query_params)}"

    # Build cURL command
    curl_parts = [f"curl -X {method}"]

    # Add headers (filter out sensitive ones that are masked)
    warning = None
    masked_headers = []
    for name, value in headers.items():
        if "[REDACTED]" in str(value):
            masked_headers.append(name)
            curl_parts.append(f"  -H '{name}: <YOUR_TOKEN>'")
        else:
            curl_parts.append(f"  -H '{name}: {value}'")

    if masked_headers:
        warning = f"Headers {', '.join(masked_headers)} were masked. Replace <YOUR_TOKEN> with actual values."

    # Add body if tool invocation exists
    tool_invocation = data.get("tool_invocation", {})
    if tool_invocation and method in ["POST", "PUT", "PATCH"]:
        input_params = tool_invocation.get("input_params", {})
        if input_params:
            import json
            body = json.dumps(input_params)
            curl_parts.append(f"  -d '{body}'")

    curl_parts.append(f"  '{url}'")

    curl_command = " \\\n".join(curl_parts)

    return ReplayResponse(
        curl_command=curl_command,
        warning=warning,
    )


@router.post("/test/trigger-error")
async def trigger_test_error():
    """
    Test endpoint to trigger a 500 error for snapshot capture testing.

    This endpoint intentionally raises an exception to test the
    error snapshot middleware capture functionality.
    """
    logger.info("test_error_triggered", endpoint="/test/trigger-error")
    raise RuntimeError("Test error for snapshot capture demonstration")
