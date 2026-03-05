"""Pipeline traces API endpoints for end-to-end monitoring (PostgreSQL)"""

import logging
import os
import random

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.traces_db import TraceStatusDB
from ..services.trace_service import TraceService

HEGEMON_INGEST_KEY = os.environ.get("HEGEMON_INGEST_KEY", "")


# ============ Ingest Schemas ============


class AISessionStep(BaseModel):
    """A step in an AI session trace."""

    name: str
    status: str = "success"
    duration_ms: int | None = None
    details: dict | None = None
    error: str | None = None


class AISessionIngestRequest(BaseModel):
    """Request body for AI session trace ingestion."""

    trigger_type: str = Field("ai-session", pattern="^ai-session$")
    trigger_source: str = Field(..., description="Worker role, e.g. hegemon-backend")
    tenant_id: str = Field("hegemon")
    api_name: str = Field(..., description="Ticket ID, e.g. CAB-1528")
    environment: str = Field("production")
    git_branch: str | None = None
    git_author: str | None = None
    total_duration_ms: int | None = None
    status: str = Field("success", description="success or failed")
    steps: list[AISessionStep] = Field(default_factory=list)
    metadata: dict | None = Field(None, description="AI-specific: tokens, cost, model, turns, etc.")


class TraceListResponse(BaseModel):
    """Paginated trace list."""

    traces: list[dict] = []
    total: int = 0


class TraceLiveResponse(BaseModel):
    """Live traces response."""

    traces: list[dict] = []
    count: int = 0


class TraceIngestResponse(BaseModel):
    """Trace ingest confirmation."""

    ingested: bool
    trace_id: str
    status: str


class TraceTimelineStep(BaseModel):
    """A step in a trace timeline."""

    name: str | None = None
    status: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None
    details: dict | None = None


class TraceTimelineTrigger(BaseModel):
    """Trace trigger info."""

    type: str | None = None
    source: str | None = None
    author: str | None = None
    commit: str | None = None
    message: str | None = None


class TraceTimelineTarget(BaseModel):
    """Trace target info."""

    tenant_id: str | None = None
    api_name: str | None = None
    environment: str | None = None


class TraceTimelineResponse(BaseModel):
    """Timeline view of a trace."""

    trace_id: str
    trigger: TraceTimelineTrigger
    target: TraceTimelineTarget
    status: str
    created_at: str | None = None
    total_duration_ms: int | None = None
    timeline: list[TraceTimelineStep] = []
    error_summary: str | None = None


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/traces", tags=["Traces"])


async def get_service(db: AsyncSession = Depends(get_db)) -> TraceService:
    """Dependency to get trace service."""
    return TraceService(db)


@router.get("", response_model=TraceListResponse)
async def list_traces(
    limit: int = Query(50, ge=1, le=200),
    tenant_id: str | None = None,
    status: str | None = None,
    environment: str | None = Query(None, description="Filter by environment"),
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

    traces = await service.list_recent(limit, tenant_id, trace_status, environment)

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


@router.get("/live", response_model=TraceLiveResponse)
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


@router.get("/{trace_id}/timeline", response_model=TraceTimelineResponse)
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
        timeline.append(
            {
                "name": step.get("name"),
                "status": step.get("status"),
                "started_at": step.get("started_at"),
                "completed_at": step.get("completed_at"),
                "duration_ms": step.get("duration_ms"),
                "error": step.get("error"),
                "details": step.get("details"),
            }
        )

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


# ============ AI Session Ingest ============


async def _verify_ingest_key(
    x_stoa_api_key: str = Header(..., alias="X-STOA-API-KEY"),
) -> str:
    """Verify the ingest API key."""
    if not HEGEMON_INGEST_KEY:
        raise HTTPException(503, "Ingest endpoint not configured")
    if x_stoa_api_key != HEGEMON_INGEST_KEY:
        raise HTTPException(401, "Invalid API key")
    return x_stoa_api_key


@router.post("/ingest", response_model=TraceIngestResponse)
async def ingest_ai_session(
    body: AISessionIngestRequest,
    _key: str = Depends(_verify_ingest_key),
    service: TraceService = Depends(get_service),
):
    """
    Ingest a completed AI session trace from a worker.

    Workers push completed session summaries via this endpoint.
    Auth: X-STOA-API-KEY header.
    """
    trace_status = TraceStatusDB.SUCCESS
    if body.status == "failed":
        trace_status = TraceStatusDB.FAILED

    trace = await service.create(
        trigger_type=body.trigger_type,
        trigger_source=body.trigger_source,
        tenant_id=body.tenant_id,
        api_name=body.api_name,
        environment=body.environment,
        git_branch=body.git_branch,
        git_author=body.git_author,
    )

    # Add metadata as a "session-summary" step
    if body.metadata:
        await service.add_step(
            trace,
            name="session-summary",
            status="success",
            duration_ms=body.total_duration_ms,
            details=body.metadata,
        )

    # Add reported steps
    for step in body.steps:
        await service.add_step(
            trace,
            name=step.name,
            status=step.status,
            duration_ms=step.duration_ms,
            details=step.details,
            error=step.error,
        )

    # Complete the trace
    error_summary = None
    if trace_status == TraceStatusDB.FAILED:
        failed_steps = [s.name for s in body.steps if s.status == "failed"]
        error_summary = f"Session failed at: {', '.join(failed_steps)}" if failed_steps else "Session failed"

    await service.complete(trace, trace_status, error_summary)

    # Override duration with the worker's reported value (complete() calculates ~0ms
    # since create+complete happen in the same request)
    if body.total_duration_ms is not None:
        trace.total_duration_ms = body.total_duration_ms
        await service.session.commit()

    trace = await service.get(trace.id)

    # Check cost alert threshold (CAB-1691) — fire-and-forget
    try:
        alert = await service.check_cost_alert()
        if alert:
            await service.send_cost_alert_slack(alert)
    except Exception as e:
        logger.warning(f"Cost alert check failed (non-blocking): {e}")

    # Push metrics to Pushgateway (CAB-1695) — fire-and-forget
    try:
        await service.push_cost_metrics()
    except Exception as e:
        logger.warning(f"Pushgateway push failed (non-blocking): {e}")

    return {
        "ingested": True,
        "trace_id": trace.id,
        "status": trace.status.value,
    }


@router.get("/stats/ai-sessions")
async def get_ai_session_stats(
    days: int = Query(7, ge=1, le=90),
    worker: str | None = Query(None, description="Filter by worker (trigger_source)"),
    service: TraceService = Depends(get_service),
):
    """
    Get AI session-specific aggregated statistics.

    Returns per-worker stats, daily time series, totals, model breakdown, and WoW cost delta.
    """
    return await service.get_ai_session_stats(days, worker)


@router.get("/export/ai-sessions")
async def export_ai_sessions_csv(
    days: int = Query(7, ge=1, le=90),
    worker: str | None = Query(None, description="Filter by worker (trigger_source)"),
    service: TraceService = Depends(get_service),
):
    """
    Export AI session traces as CSV.

    Returns a downloadable CSV with session details including cost, tokens, and model.
    """
    csv_content = await service.export_ai_sessions_csv(days, worker)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=hegemon-sessions-{days}d.csv"},
    )


# ============ Demo Endpoints ============


@router.post("/demo", include_in_schema=False)
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
        git_commit_message=random.choice(
            [
                "feat: add new API endpoint for user management",
                "fix: resolve authentication token expiry issue",
                "chore: update dependencies to latest versions",
                "refactor: improve database query performance",
                "docs: update API documentation",
                "feat: implement rate limiting for API Gateway",
                "fix: handle edge case in payment processing",
            ]
        ),
        git_branch="main",
        git_author=random.choice(["alice", "bob", "charlie", "diana", "eve"]),
        git_author_email="dev@gostoa.dev",
        git_project=random.choice(
            [
                "stoa/api-definitions",
                "stoa/customer-service",
                "stoa/order-service",
                "stoa/payment-gateway",
            ]
        ),
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
        ("gateway_sync", 100, 500, final_status != TraceStatusDB.FAILED),
    ]

    for step_name, min_ms, max_ms, should_succeed in steps_config:
        duration = random.randint(min_ms, max_ms)

        if not should_succeed and step_name == "gateway_sync":
            await service.add_step(
                trace,
                name=step_name,
                status="failed",
                duration_ms=duration,
                error="Gateway sync failed: adapter error",
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
        await service.complete(trace, TraceStatusDB.FAILED, "Pipeline failed at gateway_sync step")
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


@router.post("/demo/batch", include_in_schema=False)
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


@router.post("/demo/ai-sessions", include_in_schema=False)
async def create_demo_ai_sessions(
    count: int = Query(8, ge=1, le=30),
    service: TraceService = Depends(get_service),
):
    """Create demo AI session traces for the Hegemon dashboard."""
    workers = [
        ("hegemon-backend", "backend"),
        ("hegemon-frontend", "frontend"),
        ("hegemon-mcp", "mcp"),
        ("hegemon-auth", "auth"),
        ("hegemon-qa", "qa"),
    ]
    tickets = [
        "CAB-1528",
        "CAB-1530",
        "CAB-1535",
        "CAB-1540",
        "CAB-1547",
        "CAB-1551",
        "CAB-1555",
        "CAB-1560",
        "CAB-1562",
        "CAB-1565",
        "CAB-1570",
        "CAB-1580",
    ]
    models = ["claude-opus-4-6", "claude-sonnet-4-6"]
    statuses_pool = [TraceStatusDB.SUCCESS] * 7 + [TraceStatusDB.FAILED] * 2 + [TraceStatusDB.IN_PROGRESS]

    results = []
    for _i in range(count):
        worker_name, worker_role = random.choice(workers)
        ticket = random.choice(tickets)
        final_status = random.choice(statuses_pool)
        duration = random.randint(300_000, 2_400_000)
        model = random.choice(models)
        turns = random.randint(8, 45)
        tokens = random.randint(15_000, 120_000)
        cost = round(tokens * 0.00005 * (3 if "opus" in model else 1), 2)
        files = random.randint(2, 15)
        loc = random.randint(30, 400)

        trace = await service.create(
            trigger_type="ai-session",
            trigger_source=worker_name,
            tenant_id="hegemon",
            api_name=ticket,
            environment="production",
            git_branch=f"feat/{ticket.lower()}-auto",
            git_author=f"hegemon-worker-{random.randint(1, 5)}",
        )

        # Session summary metadata
        await service.add_step(
            trace,
            name="session-summary",
            status="success",
            duration_ms=duration,
            details={
                "total_tokens": tokens,
                "cost_usd": cost,
                "model": model,
                "turns": turns,
                "worker_role": worker_role,
                "files_changed": files,
                "loc": loc,
            },
        )

        # Realistic pipeline steps
        steps = [
            ("claimed", "success", random.randint(100, 2000)),
            ("planning", "success", random.randint(30_000, 120_000)),
            ("coding", "success", random.randint(60_000, 600_000)),
            ("testing", "success", random.randint(30_000, 180_000)),
            ("pr-created", "success", random.randint(5_000, 30_000)),
        ]
        if final_status == TraceStatusDB.SUCCESS:
            steps.append(("ci-green", "success", random.randint(120_000, 300_000)))
            steps.append(("merged", "success", random.randint(5_000, 30_000)))
        elif final_status == TraceStatusDB.FAILED:
            steps.append(("ci-green", "failed", random.randint(120_000, 300_000)))

        for step_name, step_status, step_dur in steps:
            await service.add_step(
                trace,
                name=step_name,
                status=step_status,
                duration_ms=step_dur,
                details={"pr": random.randint(1100, 1500)} if step_name == "pr-created" else None,
                error="CI failed: test_consumer.py::test_create FAILED" if step_status == "failed" else None,
            )

        error_summary = None
        if final_status == TraceStatusDB.FAILED:
            error_summary = "CI pipeline failed"
        await service.complete(trace, final_status, error_summary)
        trace = await service.get(trace.id)

        results.append({"trace_id": trace.id, "status": trace.status.value, "worker": worker_name, "ticket": ticket})

    return {"created": count, "traces": results}
