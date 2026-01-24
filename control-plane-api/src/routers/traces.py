"""Pipeline traces API endpoints for end-to-end monitoring (PostgreSQL)"""
import random
import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.trace_service import TraceService
from ..models.traces_db import TraceStatusDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/traces", tags=["Traces"])


async def get_service(db: AsyncSession = Depends(get_db)) -> TraceService:
    """Dependency to get trace service."""
    return TraceService(db)


@router.get("")
async def list_traces(
    limit: int = Query(50, ge=1, le=200),
    tenant_id: Optional[str] = None,
    status: Optional[str] = None,
    service: TraceService = Depends(get_service),
):
    """
    List recent pipeline traces with optional filtering.

    Returns summaries for efficient list display.
    """
    trace_status = None
    if status:
        try:
            trace_status = TraceStatusDB(status)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")

    traces = await service.list_recent(limit, tenant_id, trace_status)

    return {
        "traces": [t.to_summary() for t in traces],
        "total": len(traces),
    }


@router.get("/stats")
async def get_trace_stats(
    service: TraceService = Depends(get_service),
):
    """
    Get pipeline trace statistics.

    Returns aggregated metrics about pipeline executions.
    """
    return await service.get_stats()


@router.get("/live")
async def get_live_traces(
    service: TraceService = Depends(get_service),
):
    """
    Get currently running traces (in_progress status).

    Useful for real-time monitoring dashboards.
    """
    traces = await service.list_recent(20, status=TraceStatusDB.IN_PROGRESS)
    return {
        "traces": [t.to_dict() for t in traces],
        "count": len(traces),
    }


@router.get("/{trace_id}")
async def get_trace(
    trace_id: str,
    service: TraceService = Depends(get_service),
):
    """
    Get detailed information about a specific trace.

    Includes all steps with timing and error details.
    """
    trace = await service.get(trace_id)
    if not trace:
        raise HTTPException(404, f"Trace not found: {trace_id}")

    return trace.to_dict()


@router.get("/{trace_id}/timeline")
async def get_trace_timeline(
    trace_id: str,
    service: TraceService = Depends(get_service),
):
    """
    Get a timeline view of a trace suitable for visualization.

    Returns steps in a format optimized for timeline rendering.
    """
    trace = await service.get(trace_id)
    if not trace:
        raise HTTPException(404, f"Trace not found: {trace_id}")

    timeline = []
    for step in trace.steps:
        timeline.append({
            "name": step.get("name"),
            "status": step.get("status"),
            "started_at": step.get("started_at"),
            "completed_at": step.get("completed_at"),
            "duration_ms": step.get("duration_ms"),
            "error": step.get("error"),
            "details": step.get("details"),
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
        "created_at": trace.created_at.isoformat() if trace.created_at else None,
        "total_duration_ms": trace.total_duration_ms,
        "timeline": timeline,
        "error_summary": trace.error_summary,
    }


# ============ Demo Endpoints ============

@router.post("/demo")
async def create_demo_trace(
    service: TraceService = Depends(get_service),
):
    """Create a demo trace for testing the monitoring UI."""
    # Random statuses for variety (weighted towards success)
    statuses = [TraceStatusDB.SUCCESS] * 7 + [TraceStatusDB.FAILED] * 2 + [TraceStatusDB.IN_PROGRESS]
    final_status = random.choice(statuses)

    # Create trace
    trace = await service.create(
        trigger_type="gitlab-push",
        trigger_source="gitlab",
        git_commit_sha=f"{random.randint(1000000, 9999999):07x}abc",
        git_commit_message=random.choice([
            "feat: add new API endpoint for user management",
            "fix: resolve authentication token expiry issue",
            "chore: update dependencies to latest versions",
            "refactor: improve database query performance",
            "docs: update API documentation",
            "feat: implement rate limiting for API Gateway",
            "fix: handle edge case in payment processing",
        ]),
        git_branch="main",
        git_author=random.choice(["alice", "bob", "charlie", "diana", "eve"]),
        git_author_email="dev@gostoa.dev",
        git_project=random.choice([
            "stoa/api-definitions",
            "stoa/customer-service",
            "stoa/order-service",
            "stoa/payment-gateway",
        ]),
        git_files_changed=[
            f"tenants/acme/apis/{random.choice(['customer-api', 'order-api', 'payment-api'])}/openapi.yaml"
        ],
        tenant_id=random.choice(["tenant-acme", "tenant-globex", "tenant-initech"]),
        api_name=random.choice(["customer-api", "order-api", "inventory-api", "payment-api"]),
        environment="dev",
    )

    # Add realistic steps with timing
    steps_config = [
        ("webhook_received", 15, 50, True),
        ("token_verification", 5, 20, True),
        ("event_processing", 20, 100, True),
        ("analyze_changes", 50, 200, True),
        ("kafka_publish", 30, 150, True),
        ("awx_trigger", 100, 500, final_status != TraceStatusDB.FAILED),
    ]

    for step_name, min_ms, max_ms, should_succeed in steps_config:
        duration = random.randint(min_ms, max_ms)

        if not should_succeed and step_name == "awx_trigger":
            await service.add_step(
                trace,
                name=step_name,
                status="failed",
                duration_ms=duration,
                error="AWX job failed: Ansible playbook error",
                details={"job_id": random.randint(1000, 9999), "error_code": "ANSIBLE_ERROR"},
            )
        else:
            await service.add_step(
                trace,
                name=step_name,
                status="success",
                duration_ms=duration,
                details={"processed": True, "duration_ms": duration},
            )

    # Complete trace
    if final_status == TraceStatusDB.FAILED:
        await service.complete(trace, TraceStatusDB.FAILED, "Pipeline failed at awx_trigger step")
    elif final_status == TraceStatusDB.IN_PROGRESS:
        pass  # Leave as in_progress
    else:
        await service.complete(trace, TraceStatusDB.SUCCESS)

    # Refresh to get final state
    trace = await service.get(trace.id)

    return {
        "created": True,
        "trace_id": trace.id,
        "status": trace.status.value,
        "duration_ms": trace.total_duration_ms,
    }


@router.post("/demo/batch")
async def create_demo_traces_batch(
    count: int = Query(10, ge=1, le=50),
    service: TraceService = Depends(get_service),
):
    """Create multiple demo traces for a realistic monitoring view."""
    traces = []
    for _ in range(count):
        result = await create_demo_trace(service)
        traces.append(result)

    return {
        "created": count,
        "traces": traces,
    }
