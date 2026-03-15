"""Service for managing pipeline traces in PostgreSQL."""

import csv
import io
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.traces_db import PipelineTraceDB, TraceStatusDB

PUSHGATEWAY_URL = os.environ.get("PUSHGATEWAY_URL", "")
COST_ALERT_THRESHOLD_USD = float(os.environ.get("HEGEMON_COST_ALERT_THRESHOLD", "50.0"))
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

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

        # By-model aggregation (CAB-1692)
        model_map: dict[str, dict] = {}
        for trace in all_traces:
            meta = self._extract_session_metadata(trace)
            model = (meta.get("model") if meta else None) or "unknown"
            if model not in model_map:
                model_map[model] = {"sessions": 0, "cost": 0.0, "tokens": 0}
            model_map[model]["sessions"] += 1
            model_map[model]["cost"] += (meta.get("cost_usd", 0) if meta else 0) or 0
            model_map[model]["tokens"] += (meta.get("total_tokens", 0) if meta else 0) or 0

        by_model = [
            {
                "model": m,
                "sessions": d["sessions"],
                "cost_usd": round(d["cost"], 2),
                "tokens": d["tokens"],
            }
            for m, d in sorted(model_map.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        # Week-over-week cost delta (CAB-1693)
        prev_since = since - timedelta(days=days)
        prev_filter = [
            PipelineTraceDB.trigger_type == "ai-session",
            PipelineTraceDB.created_at >= prev_since,
            PipelineTraceDB.created_at < since,
        ]
        if worker:
            prev_filter.append(PipelineTraceDB.trigger_source == worker)

        prev_traces_result = await self.session.execute(select(PipelineTraceDB).where(*prev_filter))
        prev_traces = list(prev_traces_result.scalars().all())

        prev_cost = 0.0
        prev_tokens = 0
        for trace in prev_traces:
            meta = self._extract_session_metadata(trace)
            prev_cost += (meta.get("cost_usd", 0) if meta else 0) or 0
            prev_tokens += (meta.get("total_tokens", 0) if meta else 0) or 0

        cost_delta_usd = round(total_cost - prev_cost, 2)
        cost_delta_pct = round((total_cost - prev_cost) / prev_cost * 100, 1) if prev_cost > 0 else 0.0
        tokens_delta = total_tokens - prev_tokens

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
                "cost_delta_usd": cost_delta_usd,
                "cost_delta_pct": cost_delta_pct,
                "tokens_delta": tokens_delta,
                "prev_cost_usd": round(prev_cost, 2),
            },
            "by_model": by_model,
            "workers": workers,
            "daily": daily,
        }

    async def export_ai_sessions_csv(self, days: int = 7, worker: str | None = None) -> str:
        """Export AI session traces as CSV string."""
        since = datetime.now(UTC) - timedelta(days=days)
        base_filter = [
            PipelineTraceDB.trigger_type == "ai-session",
            PipelineTraceDB.created_at >= since,
        ]
        if worker:
            base_filter.append(PipelineTraceDB.trigger_source == worker)

        result = await self.session.execute(
            select(PipelineTraceDB).where(*base_filter).order_by(desc(PipelineTraceDB.created_at))
        )
        traces = list(result.scalars().all())

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["id", "worker", "ticket", "status", "created_at", "duration_ms", "cost_usd", "tokens", "model", "branch"]
        )
        for trace in traces:
            meta = self._extract_session_metadata(trace)
            writer.writerow(
                [
                    trace.id,
                    trace.trigger_source,
                    trace.api_name or "",
                    trace.status.value,
                    trace.created_at.isoformat() if trace.created_at else "",
                    trace.total_duration_ms or "",
                    meta.get("cost_usd", "") if meta else "",
                    meta.get("total_tokens", "") if meta else "",
                    meta.get("model", "") if meta else "",
                    trace.git_branch or "",
                ]
            )
        return output.getvalue()

    async def check_cost_alert(self) -> dict | None:
        """Check if today's cost exceeds threshold.

        Returns alert info or None. Deduplicates: max 1 alert per day (CAB-1691).
        """
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        base_filter = [
            PipelineTraceDB.trigger_type == "ai-session",
            PipelineTraceDB.created_at >= today_start,
        ]
        result = await self.session.execute(select(PipelineTraceDB).where(*base_filter))
        traces = list(result.scalars().all())

        today_cost = 0.0
        for trace in traces:
            meta = self._extract_session_metadata(trace)
            today_cost += (meta.get("cost_usd", 0) if meta else 0) or 0

        if today_cost >= COST_ALERT_THRESHOLD_USD:
            # Dedup: check if a cost-alert trace was already created today
            alert_check = await self.session.execute(
                select(func.count(PipelineTraceDB.id)).where(
                    PipelineTraceDB.trigger_type == "cost-alert",
                    PipelineTraceDB.created_at >= today_start,
                )
            )
            if (alert_check.scalar() or 0) > 0:
                logger.debug("Cost alert already sent today, skipping (dedup)")
                return None

            return {
                "alert": True,
                "today_cost_usd": round(today_cost, 2),
                "threshold_usd": COST_ALERT_THRESHOLD_USD,
                "sessions_today": len(traces),
            }
        return None

    async def record_cost_alert(self, alert: dict) -> None:
        """Record a cost-alert trace to prevent duplicate alerts today."""
        trace = PipelineTraceDB(
            id=str(uuid.uuid4()),
            trigger_type="cost-alert",
            trigger_source="cost-monitor",
            tenant_id="hegemon",
            api_name="cost-alert",
            environment="production",
            status=TraceStatusDB.SUCCESS,
            steps=[{"name": "alert-sent", "status": "success", "details": alert}],
        )
        self.session.add(trace)
        await self.session.commit()

    async def push_cost_metrics(self) -> bool:
        """Push aggregated cost metrics to Pushgateway.

        Pushes total, per-worker, and per-model gauges for Grafana dashboards.
        """
        if not PUSHGATEWAY_URL:
            logger.debug("PUSHGATEWAY_URL not configured, skipping metrics push")
            return False

        stats = await self.get_ai_session_stats(days=1)
        totals = stats["totals"]

        metrics = (
            "# HELP hegemon_cost_usd_total Total Hegemon AI session cost in USD\n"
            "# TYPE hegemon_cost_usd_total gauge\n"
            f'hegemon_cost_usd_total {totals["total_cost_usd"]}\n'
            "# HELP hegemon_tokens_total Total tokens consumed by Hegemon sessions\n"
            "# TYPE hegemon_tokens_total gauge\n"
            f'hegemon_tokens_total {totals["total_tokens"]}\n'
            "# HELP hegemon_sessions_total Total Hegemon sessions today\n"
            "# TYPE hegemon_sessions_total gauge\n"
            f'hegemon_sessions_total {totals["sessions"]}\n'
            "# HELP hegemon_cost_per_session_usd Average cost per session\n"
            "# TYPE hegemon_cost_per_session_usd gauge\n"
            f'hegemon_cost_per_session_usd {totals["avg_cost_per_session"]}\n'
            "# HELP hegemon_success_rate Success rate percentage\n"
            "# TYPE hegemon_success_rate gauge\n"
            f'hegemon_success_rate {totals["success_rate"]}\n'
        )

        # Per-worker metrics (CAB-1695)
        for worker_stat in stats.get("workers", []):
            worker_label = worker_stat["worker"].replace('"', '\\"')
            metrics += (
                f'hegemon_cost_by_worker_usd{{worker="{worker_label}"}} {worker_stat["total_cost_usd"]}\n'
                f'hegemon_tokens_by_worker{{worker="{worker_label}"}} {worker_stat["total_tokens"]}\n'
                f'hegemon_sessions_by_worker{{worker="{worker_label}"}} {worker_stat["sessions"]}\n'
                f'hegemon_success_rate_by_worker{{worker="{worker_label}"}} {worker_stat["success_rate"]}\n'
            )

        # Per-model metrics
        for model_stat in stats.get("by_model", []):
            model_label = model_stat["model"].replace('"', '\\"')
            metrics += (
                f'hegemon_cost_by_model_usd{{model="{model_label}"}} {model_stat["cost_usd"]}\n'
                f'hegemon_tokens_by_model{{model="{model_label}"}} {model_stat["tokens"]}\n'
                f'hegemon_sessions_by_model{{model="{model_label}"}} {model_stat["sessions"]}\n'
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.put(
                    f"{PUSHGATEWAY_URL}/metrics/job/hegemon_ai_factory",
                    content=metrics,
                    headers={"Content-Type": "text/plain"},
                )
                resp.raise_for_status()
                logger.info("Pushed Hegemon cost metrics to Pushgateway")
                return True
        except Exception as e:
            logger.warning(f"Failed to push metrics to Pushgateway: {e}")
            return False

    @staticmethod
    async def send_cost_alert_slack(alert: dict) -> bool:
        """Send cost alert to Slack webhook."""
        if not SLACK_WEBHOOK_URL:
            logger.debug("SLACK_WEBHOOK_URL not configured, skipping cost alert")
            return False

        payload = {
            "text": (
                f":warning: *Hegemon Cost Alert*\n"
                f"Today's spend: *${alert['today_cost_usd']:.2f}* "
                f"(threshold: ${alert['threshold_usd']:.2f})\n"
                f"Sessions today: {alert['sessions_today']}"
            ),
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(SLACK_WEBHOOK_URL, json=payload)
                resp.raise_for_status()
                logger.info("Sent Hegemon cost alert to Slack")
                return True
        except Exception as e:
            logger.warning(f"Failed to send cost alert to Slack: {e}")
            return False


# Dependency injection helper
async def get_trace_service(session: AsyncSession) -> TraceService:
    """Get trace service instance."""
    return TraceService(session)
