"""Service for managing pipeline traces in PostgreSQL."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.traces_db import PipelineTraceDB, TraceStatusDB

logger = logging.getLogger(__name__)


class TraceService:
    """Async service for pipeline trace operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        trigger_type: str,
        trigger_source: str,
        **kwargs
    ) -> PipelineTraceDB:
        """Create a new pipeline trace."""
        trace = PipelineTraceDB(
            id=str(uuid.uuid4()),
            trigger_type=trigger_type,
            trigger_source=trigger_source,
            status=TraceStatusDB.IN_PROGRESS,
            steps=[],
            **kwargs
        )
        self.session.add(trace)
        await self.session.commit()
        await self.session.refresh(trace)
        logger.info(f"Created trace {trace.id}")
        return trace

    async def get(self, trace_id: str) -> Optional[PipelineTraceDB]:
        """Get a trace by ID."""
        result = await self.session.execute(
            select(PipelineTraceDB).where(PipelineTraceDB.id == trace_id)
        )
        return result.scalar_one_or_none()

    async def update(self, trace: PipelineTraceDB) -> PipelineTraceDB:
        """Update a trace."""
        await self.session.commit()
        await self.session.refresh(trace)
        return trace

    async def add_step(
        self,
        trace: PipelineTraceDB,
        name: str,
        status: str = "pending",
        details: Optional[dict] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> PipelineTraceDB:
        """Add a step to the trace."""
        step = {
            "name": name,
            "status": status,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "duration_ms": duration_ms,
            "details": details,
            "error": error,
        }
        # JSONB needs copy to trigger change detection
        steps = list(trace.steps)
        steps.append(step)
        trace.steps = steps
        await self.session.commit()
        return trace

    async def update_step(
        self,
        trace: PipelineTraceDB,
        step_name: str,
        status: str,
        details: Optional[dict] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> PipelineTraceDB:
        """Update a step in the trace."""
        steps = list(trace.steps)
        for step in steps:
            if step["name"] == step_name:
                step["status"] = status
                step["completed_at"] = datetime.now(timezone.utc).isoformat()
                if duration_ms:
                    step["duration_ms"] = duration_ms
                if details:
                    step["details"] = details
                if error:
                    step["error"] = error
                break
        trace.steps = steps
        await self.session.commit()
        return trace

    async def complete(
        self,
        trace: PipelineTraceDB,
        status: TraceStatusDB = TraceStatusDB.SUCCESS,
        error_summary: Optional[str] = None
    ) -> PipelineTraceDB:
        """Mark trace as completed."""
        trace.status = status
        trace.completed_at = datetime.now(timezone.utc)
        if trace.created_at:
            trace.total_duration_ms = int(
                (trace.completed_at - trace.created_at).total_seconds() * 1000
            )
        if error_summary:
            trace.error_summary = error_summary
        await self.session.commit()
        await self.session.refresh(trace)
        logger.info(f"Completed trace {trace.id}: {status.value}")
        return trace

    async def list_recent(
        self,
        limit: int = 50,
        tenant_id: Optional[str] = None,
        status: Optional[TraceStatusDB] = None
    ) -> List[PipelineTraceDB]:
        """List recent traces with optional filtering."""
        query = select(PipelineTraceDB)

        if tenant_id:
            query = query.where(PipelineTraceDB.tenant_id == tenant_id)
        if status:
            query = query.where(PipelineTraceDB.status == status)

        query = query.order_by(desc(PipelineTraceDB.created_at)).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_stats(self) -> dict:
        """Get aggregated statistics about traces."""
        # Total count
        total_result = await self.session.execute(
            select(func.count(PipelineTraceDB.id))
        )
        total = total_result.scalar() or 0

        if total == 0:
            return {
                "total": 0,
                "by_status": {},
                "avg_duration_ms": 0,
                "success_rate": 0,
            }

        # Count by status
        by_status = {}
        for status in TraceStatusDB:
            count_result = await self.session.execute(
                select(func.count(PipelineTraceDB.id)).where(
                    PipelineTraceDB.status == status
                )
            )
            by_status[status.value] = count_result.scalar() or 0

        # Average duration
        avg_result = await self.session.execute(
            select(func.avg(PipelineTraceDB.total_duration_ms)).where(
                PipelineTraceDB.total_duration_ms.isnot(None)
            )
        )
        avg_duration = avg_result.scalar() or 0

        # Success rate
        finished = by_status.get("success", 0) + by_status.get("failed", 0)
        success_rate = (by_status.get("success", 0) / finished * 100) if finished > 0 else 0

        return {
            "total": total,
            "by_status": by_status,
            "avg_duration_ms": int(avg_duration),
            "success_rate": round(success_rate, 1),
        }


# Dependency injection helper
async def get_trace_service(session: AsyncSession) -> TraceService:
    """Get trace service instance."""
    return TraceService(session)
