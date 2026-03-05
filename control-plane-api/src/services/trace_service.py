"""Service for managing pipeline traces in PostgreSQL."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.traces_db import PipelineTraceDB, TraceStatusDB

logger = logging.getLogger(__name__)


class TraceService:
    """Async service for pipeline trace operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, trigger_type: str, trigger_source: str, **kwargs) -> PipelineTraceDB:
        """Create a new pipeline trace."""
        trace = PipelineTraceDB(
            id=str(uuid.uuid4()),
            trigger_type=trigger_type,
            trigger_source=trigger_source,
            status=TraceStatusDB.IN_PROGRESS,
            steps=[],
            **kwargs,
        )
        self.session.add(trace)
        await self.session.commit()
        await self.session.refresh(trace)
        logger.info(f"Created trace {trace.id}")
        return trace

    async def get(self, trace_id: str) -> PipelineTraceDB | None:
        """Get a trace by ID."""
        result = await self.session.execute(select(PipelineTraceDB).where(PipelineTraceDB.id == trace_id))
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
        details: dict | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> PipelineTraceDB:
        """Add a step to the trace."""
        step = {
            "name": name,
            "status": status,
            "started_at": datetime.now(UTC).isoformat(),
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
        details: dict | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> PipelineTraceDB:
        """Update a step in the trace."""
        steps = list(trace.steps)
        for step in steps:
            if step["name"] == step_name:
                step["status"] = status
                step["completed_at"] = datetime.now(UTC).isoformat()
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
        self, trace: PipelineTraceDB, status: TraceStatusDB = TraceStatusDB.SUCCESS, error_summary: str | None = None
    ) -> PipelineTraceDB:
        """Mark trace as completed."""
        trace.status = status
        trace.completed_at = datetime.now(UTC)
        if trace.created_at:
            trace.total_duration_ms = int((trace.completed_at - trace.created_at).total_seconds() * 1000)
        if error_summary:
            trace.error_summary = error_summary
        await self.session.commit()
        await self.session.refresh(trace)
        logger.info(f"Completed trace {trace.id}: {status.value}")
        return trace

    async def list_recent(
        self,
        limit: int = 50,
        tenant_id: str | None = None,
        status: TraceStatusDB | None = None,
        environment: str | None = None,
    ) -> list[PipelineTraceDB]:
        """List recent traces with optional filtering."""
        query = select(PipelineTraceDB)

        if tenant_id:
            query = query.where(PipelineTraceDB.tenant_id == tenant_id)
        if status:
            query = query.where(PipelineTraceDB.status == status)
        if environment:
            query = query.where(PipelineTraceDB.environment == environment)

        query = query.order_by(desc(PipelineTraceDB.created_at)).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_stats(self) -> dict:
        """Get aggregated statistics about traces."""
        # Total count
        total_result = await self.session.execute(select(func.count(PipelineTraceDB.id)))
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
                select(func.count(PipelineTraceDB.id)).where(PipelineTraceDB.status == status)
            )
            by_status[status.value] = count_result.scalar() or 0

        # Average duration
        avg_result = await self.session.execute(
            select(func.avg(PipelineTraceDB.total_duration_ms)).where(PipelineTraceDB.total_duration_ms.isnot(None))
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

    @staticmethod
    def _extract_session_metadata(trace: PipelineTraceDB) -> dict | None:
        """Extract cost/tokens/model from the 'session-summary' step details."""
        for step in trace.steps:
            if step.get("name") == "session-summary" and step.get("details"):
                return step["details"]
        return None

    async def get_ai_session_stats(self, days: int = 7, worker: str | None = None) -> dict:
        """Get aggregated statistics for AI session traces."""
        since = datetime.now(UTC) - timedelta(days=days)

        base_filter = [
            PipelineTraceDB.trigger_type == "ai-session",
            PipelineTraceDB.created_at >= since,
        ]
        if worker:
            base_filter.append(PipelineTraceDB.trigger_source == worker)

        # Total sessions
        total_result = await self.session.execute(select(func.count(PipelineTraceDB.id)).where(*base_filter))
        total_sessions = total_result.scalar() or 0

        if total_sessions == 0:
            return {
                "days": days,
                "totals": {
                    "sessions": 0,
                    "total_duration_ms": 0,
                    "avg_duration_ms": 0,
                    "success_count": 0,
                    "success_rate": 0,
                    "total_cost_usd": 0,
                    "total_tokens": 0,
                    "avg_cost_per_session": 0,
                },
                "workers": [],
                "daily": [],
            }

        # Fetch all matching traces for cost/token extraction
        all_traces_result = await self.session.execute(select(PipelineTraceDB).where(*base_filter))
        all_traces = list(all_traces_result.scalars().all())

        # Totals
        agg_result = await self.session.execute(
            select(
                func.count(PipelineTraceDB.id),
                func.sum(PipelineTraceDB.total_duration_ms),
                func.avg(PipelineTraceDB.total_duration_ms),
            ).where(*base_filter)
        )
        row = agg_result.one()
        total_count = row[0] or 0
        total_duration = row[1] or 0
        avg_duration = row[2] or 0

        success_result = await self.session.execute(
            select(func.count(PipelineTraceDB.id)).where(*base_filter, PipelineTraceDB.status == TraceStatusDB.SUCCESS)
        )
        success_count = success_result.scalar() or 0
        success_rate = round(success_count / total_count * 100, 1) if total_count > 0 else 0

        # Aggregate cost/token data from session-summary steps
        total_cost = 0.0
        total_tokens = 0
        # Per-worker accumulators: {worker_name: {cost, tokens, models}}
        worker_cost_map: dict[str, dict] = {}
        # Daily cost accumulators: {date_str: {cost, tokens}}
        daily_cost_map: dict[str, dict] = {}

        for trace in all_traces:
            meta = self._extract_session_metadata(trace)
            cost = meta.get("cost_usd", 0) if meta else 0
            tokens = meta.get("total_tokens", 0) if meta else 0
            model = meta.get("model") if meta else None

            total_cost += cost or 0
            total_tokens += tokens or 0

            # Per-worker accumulation
            w_name = trace.trigger_source
            if w_name not in worker_cost_map:
                worker_cost_map[w_name] = {"cost": 0.0, "tokens": 0, "models": {}}
            worker_cost_map[w_name]["cost"] += cost or 0
            worker_cost_map[w_name]["tokens"] += tokens or 0
            if model:
                worker_cost_map[w_name]["models"][model] = worker_cost_map[w_name]["models"].get(model, 0) + 1

            # Daily accumulation
            if trace.created_at:
                day_str = str(trace.created_at.date())
                if day_str not in daily_cost_map:
                    daily_cost_map[day_str] = {"cost": 0.0, "tokens": 0}
                daily_cost_map[day_str]["cost"] += cost or 0
                daily_cost_map[day_str]["tokens"] += tokens or 0

        avg_cost = round(total_cost / total_count, 2) if total_count > 0 else 0

        # Per-worker stats
        worker_result = await self.session.execute(
            select(
                PipelineTraceDB.trigger_source,
                func.count(PipelineTraceDB.id),
                func.sum(PipelineTraceDB.total_duration_ms),
                func.avg(PipelineTraceDB.total_duration_ms),
                func.max(PipelineTraceDB.created_at),
            )
            .where(*base_filter)
            .group_by(PipelineTraceDB.trigger_source)
        )
        workers = []
        for w_row in worker_result.all():
            w_name, w_count, w_total_dur, w_avg_dur, w_last = w_row
            # Count successes per worker
            w_success_result = await self.session.execute(
                select(func.count(PipelineTraceDB.id)).where(
                    *base_filter,
                    PipelineTraceDB.trigger_source == w_name,
                    PipelineTraceDB.status == TraceStatusDB.SUCCESS,
                )
            )
            w_success = w_success_result.scalar() or 0

            # Cost/token data from accumulator
            w_cost_data = worker_cost_map.get(w_name, {"cost": 0, "tokens": 0, "models": {}})
            w_models = w_cost_data["models"]
            primary_model = max(w_models, key=w_models.get) if w_models else None

            workers.append(
                {
                    "worker": w_name,
                    "sessions": w_count,
                    "total_duration_ms": int(w_total_dur or 0),
                    "avg_duration_ms": int(w_avg_dur or 0),
                    "success_count": w_success,
                    "success_rate": round(w_success / w_count * 100, 1) if w_count > 0 else 0,
                    "last_activity": w_last.isoformat() if w_last else None,
                    "total_cost_usd": round(w_cost_data["cost"], 2),
                    "total_tokens": w_cost_data["tokens"],
                    "avg_cost_usd": round(w_cost_data["cost"] / w_count, 2) if w_count > 0 else 0,
                    "primary_model": primary_model,
                }
            )

        # Daily time series
        date_col = func.date(PipelineTraceDB.created_at).label("day")
        daily_result = await self.session.execute(
            select(date_col, func.count(PipelineTraceDB.id)).where(*base_filter).group_by(date_col).order_by(date_col)
        )
        daily = []
        for d_row in daily_result.all():
            day_str = str(d_row[0])
            day_cost = daily_cost_map.get(day_str, {"cost": 0, "tokens": 0})
            daily.append(
                {
                    "date": day_str,
                    "sessions": d_row[1],
                    "cost_usd": round(day_cost["cost"], 2),
                    "tokens": day_cost["tokens"],
                }
            )

        return {
            "days": days,
            "totals": {
                "sessions": total_count,
                "total_duration_ms": int(total_duration),
                "avg_duration_ms": int(avg_duration),
                "success_count": success_count,
                "success_rate": success_rate,
                "total_cost_usd": round(total_cost, 2),
                "total_tokens": total_tokens,
                "avg_cost_per_session": avg_cost,
            },
            "workers": workers,
            "daily": daily,
        }


# Dependency injection helper
async def get_trace_service(session: AsyncSession) -> TraceService:
    """Get trace service instance."""
    return TraceService(session)
