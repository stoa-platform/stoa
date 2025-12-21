"""Pipeline traces API endpoints for end-to-end monitoring"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime

from ..models.traces import trace_store, PipelineTrace, TraceStatus

router = APIRouter(prefix="/v1/traces", tags=["Traces"])


@router.get("")
async def list_traces(
    limit: int = Query(50, ge=1, le=200),
    tenant_id: Optional[str] = None,
    status: Optional[str] = None,
):
    """
    List recent pipeline traces with optional filtering.

    Returns summaries for efficient list display.
    """
    if status:
        try:
            trace_status = TraceStatus(status)
            traces = trace_store.list_by_status(trace_status, limit)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")
    else:
        traces = trace_store.list_recent(limit, tenant_id)

    return {
        "traces": [t.to_summary() for t in traces],
        "total": len(traces),
    }


@router.get("/stats")
async def get_trace_stats():
    """
    Get pipeline trace statistics.

    Returns aggregated metrics about pipeline executions.
    """
    return trace_store.get_stats()


@router.get("/live")
async def get_live_traces():
    """
    Get currently running traces (in_progress status).

    Useful for real-time monitoring dashboards.
    """
    traces = trace_store.list_by_status(TraceStatus.IN_PROGRESS, limit=20)
    return {
        "traces": [t.model_dump() for t in traces],
        "count": len(traces),
    }


@router.get("/{trace_id}")
async def get_trace(trace_id: str):
    """
    Get detailed information about a specific trace.

    Includes all steps with timing and error details.
    """
    trace = trace_store.get(trace_id)
    if not trace:
        raise HTTPException(404, f"Trace not found: {trace_id}")

    return trace.model_dump()


@router.get("/{trace_id}/timeline")
async def get_trace_timeline(trace_id: str):
    """
    Get a timeline view of a trace suitable for visualization.

    Returns steps in a format optimized for timeline rendering.
    """
    trace = trace_store.get(trace_id)
    if not trace:
        raise HTTPException(404, f"Trace not found: {trace_id}")

    timeline = []
    for step in trace.steps:
        timeline.append({
            "name": step.name,
            "status": step.status.value,
            "started_at": step.started_at.isoformat() if step.started_at else None,
            "completed_at": step.completed_at.isoformat() if step.completed_at else None,
            "duration_ms": step.duration_ms,
            "error": step.error,
            "details": step.details,
        })

    return {
        "trace_id": trace.id,
        "trigger": {
            "type": trace.trigger_type,
            "source": trace.trigger_source,
            "author": trace.git_author,
            "commit": trace.git_commit_sha[:8] if trace.git_commit_sha else None,
            "message": trace.git_commit_message,
        },
        "target": {
            "tenant_id": trace.tenant_id,
            "api_name": trace.api_name,
            "environment": trace.environment,
        },
        "status": trace.status.value,
        "created_at": trace.created_at.isoformat(),
        "total_duration_ms": trace.total_duration_ms,
        "timeline": timeline,
        "error_summary": trace.error_summary,
    }
