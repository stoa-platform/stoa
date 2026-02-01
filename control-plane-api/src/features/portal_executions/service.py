"""Portal Executions service — aggregation layer.

CAB-432: Aggregates data from Prometheus, Loki, and Error Snapshots
to build a consumer-friendly execution view. Implements degraded mode
when external services are unavailable.
"""

import logging
from datetime import UTC, datetime, timedelta

from ...auth.dependencies import User
from ...services.loki_client import loki_client
from ...services.metrics_service import metrics_service
from ..error_snapshots import get_snapshot_service
from .classifier import classify_error
from .config import PortalExecutionsSettings
from .models import (
    ExecutionError,
    ExecutionStats,
    ExecutionSummary,
)

logger = logging.getLogger(__name__)


def _mask_api_key(key: str | None) -> str:
    """Mask an API key, showing only last 3 characters."""
    if not key:
        return "***"
    if len(key) <= 6:
        return "***"
    return f"sk-***{key[-3:]}"


def _verify_app_ownership(app_id: str, user: User) -> dict | None:
    """Check if the user owns the application.

    Returns the app dict if owned, None otherwise.
    """
    # Import in-memory applications store from portal_applications
    from ...routers.portal_applications import _applications

    app = _applications.get(app_id)
    if not app:
        return None

    owner_id = app.get("owner_id")
    if owner_id not in [user.id, user.username]:
        return None

    return app


class PortalExecutionsService:
    """Aggregates execution data for the consumer portal.

    Data sources:
    - Prometheus (via metrics_service): Call counts, latencies, success rates
    - Loki (via loki_client): Recent error logs
    - Error Snapshots (CAB-397): Enriched error detail
    """

    def __init__(self, settings: PortalExecutionsSettings):
        self._settings = settings

    async def get_execution_summary(
        self,
        app_id: str,
        user: User,
    ) -> ExecutionSummary:
        """Build execution summary for a consumer app.

        Args:
            app_id: Application ID.
            user: Authenticated user.

        Returns:
            ExecutionSummary with stats and recent errors.

        Raises:
            ValueError: If app not found.
            PermissionError: If user doesn't own the app.
        """
        app = _verify_app_ownership(app_id, user)
        if app is None:
            from ...routers.portal_applications import _applications

            if app_id in _applications:
                raise PermissionError(f"Access denied to app {app_id}")
            raise ValueError(f"Application {app_id} not found")

        tenant_id = user.tenant_id or "default"
        degraded_services: list[str] = []

        # Fetch stats from Prometheus
        stats = ExecutionStats()
        try:
            summary = await metrics_service.get_usage_summary(user.id, tenant_id)
            stats = ExecutionStats(
                total_calls_24h=summary.today.total_calls,
                success_rate=summary.today.success_rate,
                avg_latency_ms=summary.today.avg_latency_ms,
                error_count_24h=summary.today.error_count,
            )
        except Exception as e:
            logger.warning(f"prometheus_degraded app={app_id}: {e}")
            degraded_services.append("metrics")

        # Fetch recent errors from Loki
        recent_errors: list[ExecutionError] = []
        try:
            end = datetime.now(UTC)
            start = end - timedelta(hours=self._settings.error_window_hours)
            error_entries = await loki_client.get_recent_calls(
                user_id=user.id,
                tenant_id=tenant_id,
                limit=self._settings.max_errors,
                status="error",
                from_date=start,
                to_date=end,
            )
            for entry in error_entries:
                status_code = int(entry.get("status_code", entry.get("latency_ms", 500)))
                # Determine status_code from error_message or status field
                raw_status = entry.get("status", "error")
                if raw_status == "timeout":
                    status_code = 504
                elif "status_code" in entry:
                    status_code = int(entry["status_code"])
                else:
                    status_code = 500

                is_mcp = entry.get("tool_id") not in (None, "unknown")
                classification = classify_error(
                    status_code=status_code,
                    duration_ms=int(entry.get("latency_ms", 0)),
                    is_mcp_tool=is_mcp,
                )

                recent_errors.append(
                    ExecutionError(
                        id=entry.get("id", "unknown"),
                        timestamp=entry.get("timestamp", datetime.now(UTC)),
                        method=entry.get("method", "POST"),
                        path=entry.get("tool_name", "/unknown"),
                        status_code=status_code,
                        duration_ms=int(entry.get("latency_ms", 0)),
                        error_source=classification["error_source"],
                        error_category=classification["error_category"],
                        summary=classification["summary"],
                        help_text=classification["help_text"],
                        suggested_action=classification["suggested_action"],
                        trace_id=entry.get("id", "unknown"),
                    )
                )
        except Exception as e:
            logger.warning(f"loki_degraded app={app_id}: {e}")
            degraded_services.append("logs")

        return ExecutionSummary(
            app_id=app_id,
            app_name=app.get("display_name", app.get("name", app_id)),
            api_key_hint=_mask_api_key(app.get("client_id")),
            stats=stats,
            recent_errors=recent_errors,
            degraded=len(degraded_services) > 0,
            degraded_services=degraded_services,
        )

    async def get_error_detail(
        self,
        app_id: str,
        error_id: str,
        user: User,
    ) -> ExecutionError | None:
        """Get detailed error information for escalation.

        Args:
            app_id: Application ID.
            error_id: Error/snapshot ID.
            user: Authenticated user.

        Returns:
            ExecutionError if found, None otherwise.

        Raises:
            PermissionError: If user doesn't own the app.
        """
        app = _verify_app_ownership(app_id, user)
        if app is None:
            from ...routers.portal_applications import _applications

            if app_id in _applications:
                raise PermissionError(f"Access denied to app {app_id}")
            return None

        tenant_id = user.tenant_id or "default"

        # Try error snapshots first (SNP-* format)
        if error_id.startswith("SNP-"):
            snapshot_service = get_snapshot_service()
            if snapshot_service:
                try:
                    snapshot = await snapshot_service.get(error_id, tenant_id)
                    if snapshot:
                        status_code = snapshot.response.status_code
                        duration_ms = snapshot.duration_ms or 0
                        classification = classify_error(
                            status_code=status_code,
                            duration_ms=duration_ms,
                        )
                        return ExecutionError(
                            id=snapshot.id,
                            timestamp=snapshot.timestamp,
                            method=snapshot.request.method,
                            path=snapshot.request.path,
                            status_code=status_code,
                            duration_ms=duration_ms,
                            error_source=classification["error_source"],
                            error_category=classification["error_category"],
                            summary=classification["summary"],
                            help_text=classification["help_text"],
                            suggested_action=classification["suggested_action"],
                            trace_id=snapshot.trace_id or snapshot.id,
                        )
                except Exception as e:
                    logger.warning(f"snapshot_fetch_failed error_id={error_id}: {e}")

        # Fallback: search in Loki logs by request_id
        try:
            end = datetime.now(UTC)
            start = end - timedelta(hours=self._settings.error_window_hours)
            entries = await loki_client.get_recent_calls(
                user_id=user.id,
                tenant_id=tenant_id,
                limit=100,
                status="error",
                from_date=start,
                to_date=end,
            )
            for entry in entries:
                if entry.get("id") == error_id:
                    status_code = int(entry.get("status_code", 500))
                    is_mcp = entry.get("tool_id") not in (None, "unknown")
                    classification = classify_error(
                        status_code=status_code,
                        duration_ms=int(entry.get("latency_ms", 0)),
                        is_mcp_tool=is_mcp,
                    )
                    return ExecutionError(
                        id=entry["id"],
                        timestamp=entry.get("timestamp", datetime.now(UTC)),
                        method=entry.get("method", "POST"),
                        path=entry.get("tool_name", "/unknown"),
                        status_code=status_code,
                        duration_ms=int(entry.get("latency_ms", 0)),
                        error_source=classification["error_source"],
                        error_category=classification["error_category"],
                        summary=classification["summary"],
                        help_text=classification["help_text"],
                        suggested_action=classification["suggested_action"],
                        trace_id=entry.get("id", error_id),
                    )
        except Exception as e:
            logger.warning(f"loki_error_detail_failed error_id={error_id}: {e}")

        return None
