"""Metrics orchestration service (CAB-840)

Combines data from Prometheus, Loki, and PostgreSQL for usage endpoints.
Implements graceful degradation when external services are unavailable.
"""
import logging
from typing import Optional, List
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from .prometheus_client import prometheus_client, PrometheusClient
from .loki_client import loki_client, LokiClient
from ..models.mcp_subscription import (
    MCPServerSubscription,
    MCPServer,
    MCPSubscriptionStatus,
    MCPServerStatus,
)
from ..schemas.usage import (
    UsageSummary,
    UsagePeriodStats,
    ToolUsageStat,
    DailyCallStat,
    UsageCall,
    UsageCallsResponse,
    ActiveSubscription,
    DashboardStats,
    RecentActivityItem,
    CallStatus,
    ActivityType,
)

logger = logging.getLogger(__name__)


class MetricsService:
    """Orchestration service for usage metrics.

    Combines data from:
    - Prometheus: Request counts, latencies, success rates
    - Loki: Call logs, activity feed
    - PostgreSQL: Subscription data, tool counts
    """

    def __init__(
        self,
        prometheus: PrometheusClient = prometheus_client,
        loki: LokiClient = loki_client,
    ):
        self._prometheus = prometheus
        self._loki = loki

    async def connect(self):
        """Initialize underlying clients."""
        await self._prometheus.connect()
        await self._loki.connect()
        logger.info("MetricsService initialized")

    async def disconnect(self):
        """Cleanup underlying clients."""
        await self._prometheus.disconnect()
        await self._loki.disconnect()

    # ===== GET /v1/usage/me =====

    async def get_usage_summary(
        self,
        user_id: str,
        tenant_id: str,
    ) -> UsageSummary:
        """Get comprehensive usage summary for a user.

        Args:
            user_id: User ID
            tenant_id: Tenant ID

        Returns:
            UsageSummary with period stats, top tools, and daily calls
        """
        # Fetch period stats (today, week, month)
        today_stats = await self._get_period_stats(user_id, tenant_id, "1d", "today")
        week_stats = await self._get_period_stats(user_id, tenant_id, "7d", "week")
        month_stats = await self._get_period_stats(user_id, tenant_id, "30d", "month")

        # Get top tools
        top_tools_raw = await self._prometheus.get_top_tools(user_id, tenant_id, limit=5)
        top_tools = await self._enrich_tool_stats(top_tools_raw, user_id, tenant_id)

        # Get daily calls for chart
        daily_raw = await self._prometheus.get_daily_calls(user_id, tenant_id, days=7)
        daily_calls = [DailyCallStat(date=d["date"], calls=d["calls"]) for d in daily_raw]

        # Fallback to empty if no data
        if not daily_calls:
            daily_calls = self._generate_empty_daily_calls(7)

        return UsageSummary(
            tenant_id=tenant_id,
            user_id=user_id,
            today=today_stats,
            this_week=week_stats,
            this_month=month_stats,
            top_tools=top_tools,
            daily_calls=daily_calls,
        )

    async def _get_period_stats(
        self,
        user_id: str,
        tenant_id: str,
        time_range: str,
        period: str,
    ) -> UsagePeriodStats:
        """Get stats for a specific time period."""
        total = await self._prometheus.get_request_count(
            user_id=user_id, tenant_id=tenant_id, time_range=time_range
        )
        success = await self._prometheus.get_success_count(
            user_id=user_id, tenant_id=tenant_id, time_range=time_range
        )
        errors = await self._prometheus.get_error_count(
            user_id=user_id, tenant_id=tenant_id, time_range=time_range
        )
        avg_latency = await self._prometheus.get_avg_latency_ms(
            user_id=user_id, tenant_id=tenant_id, time_range=time_range
        )

        success_rate = (success / total * 100) if total > 0 else 100.0

        return UsagePeriodStats(
            period=period,
            total_calls=total,
            success_count=success,
            error_count=errors,
            success_rate=round(success_rate, 1),
            avg_latency_ms=avg_latency,
        )

    async def _enrich_tool_stats(
        self,
        tools: List[dict],
        user_id: str,
        tenant_id: str,
    ) -> List[ToolUsageStat]:
        """Enrich tool stats with success rate and latency."""
        enriched = []
        for tool in tools:
            tool_id = tool.get("tool_id")
            call_count = tool.get("call_count", 0)

            # Get per-tool metrics
            success_rate = await self._prometheus.get_tool_success_rate(
                tool_id, user_id, tenant_id, time_range="30d"
            )
            latency = await self._prometheus.get_tool_avg_latency(
                tool_id, user_id, tenant_id, time_range="30d"
            )

            enriched.append(ToolUsageStat(
                tool_id=tool_id,
                tool_name=tool.get("tool_name", "Unknown"),
                call_count=call_count,
                success_rate=success_rate,
                avg_latency_ms=latency,
            ))

        return enriched

    # ===== GET /v1/usage/me/calls =====

    async def get_user_calls(
        self,
        user_id: str,
        tenant_id: str,
        limit: int = 20,
        offset: int = 0,
        status: Optional[CallStatus] = None,
        tool_id: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> UsageCallsResponse:
        """Get paginated call history from Loki.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            limit: Page size
            offset: Offset for pagination
            status: Optional status filter
            tool_id: Optional tool ID filter
            from_date: Optional start date
            to_date: Optional end date

        Returns:
            UsageCallsResponse with paginated calls
        """
        # Fetch more than needed for pagination (Loki doesn't support offset natively)
        fetch_limit = offset + limit + 100

        calls_raw = await self._loki.get_recent_calls(
            user_id=user_id,
            tenant_id=tenant_id,
            limit=fetch_limit,
            tool_id=tool_id,
            status=status.value if status else None,
            from_date=from_date,
            to_date=to_date,
        )

        # Convert to UsageCall objects
        all_calls = []
        for call in (calls_raw or []):
            try:
                call_status = call.get("status", "success")
                # Map status string to enum
                if call_status == "success":
                    enum_status = CallStatus.SUCCESS
                elif call_status == "timeout":
                    enum_status = CallStatus.TIMEOUT
                else:
                    enum_status = CallStatus.ERROR

                all_calls.append(UsageCall(
                    id=call["id"],
                    timestamp=call["timestamp"],
                    tool_id=call["tool_id"],
                    tool_name=call["tool_name"],
                    status=enum_status,
                    latency_ms=call["latency_ms"],
                    error_message=call.get("error_message"),
                ))
            except (KeyError, ValueError) as e:
                logger.debug(f"Error parsing call entry: {e}")
                continue

        # Apply pagination
        total = len(all_calls)
        paginated = all_calls[offset:offset + limit]

        return UsageCallsResponse(
            calls=paginated,
            total=total,
            limit=limit,
            offset=offset,
        )

    # ===== GET /v1/usage/me/subscriptions =====

    async def get_active_subscriptions(
        self,
        user_id: str,
        db: AsyncSession,
    ) -> List[ActiveSubscription]:
        """Get active subscriptions from PostgreSQL with usage data from Prometheus.

        Args:
            user_id: User ID
            db: Database session

        Returns:
            List of active subscriptions with usage counts
        """
        # Query database for active subscriptions
        result = await db.execute(
            select(MCPServerSubscription, MCPServer)
            .join(MCPServer, MCPServerSubscription.server_id == MCPServer.id)
            .where(
                MCPServerSubscription.subscriber_id == user_id,
                MCPServerSubscription.status == MCPSubscriptionStatus.ACTIVE,
            )
            .order_by(MCPServerSubscription.created_at.desc())
        )

        subscriptions = []
        for sub, server in result.all():
            # Get call count from Prometheus (or use DB value as fallback)
            call_count = await self._prometheus.get_request_count(
                subscription_id=str(sub.id),
                time_range="36500d"  # All time (100 years)
            )
            # Use DB usage_count as fallback if Prometheus returns 0
            if call_count == 0:
                call_count = sub.usage_count or 0

            subscriptions.append(ActiveSubscription(
                id=str(sub.id),
                tool_id=server.name,
                tool_name=server.display_name,
                tool_description=server.description,
                status=sub.status.value,
                created_at=sub.created_at,
                last_used_at=sub.last_used_at,
                call_count_total=call_count,
            ))

        return subscriptions

    # ===== GET /v1/dashboard/stats =====

    async def get_dashboard_stats(
        self,
        user_id: str,
        tenant_id: str,
        db: AsyncSession,
    ) -> DashboardStats:
        """Get aggregated dashboard statistics.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            db: Database session

        Returns:
            DashboardStats with counts and trends
        """
        # Count available tools (active servers)
        tools_result = await db.execute(
            select(func.count(MCPServer.id))
            .where(MCPServer.status == MCPServerStatus.ACTIVE)
        )
        tools_available = tools_result.scalar_one()

        # Count active subscriptions for user
        subs_result = await db.execute(
            select(func.count(MCPServerSubscription.id))
            .where(
                MCPServerSubscription.subscriber_id == user_id,
                MCPServerSubscription.status == MCPSubscriptionStatus.ACTIVE,
            )
        )
        active_subscriptions = subs_result.scalar_one()

        # Get API calls this week from Prometheus
        calls_this_week = await self._prometheus.get_request_count(
            user_id=user_id, tenant_id=tenant_id, time_range="7d"
        )

        # Calculate trend (compare to previous week)
        calls_last_two_weeks = await self._prometheus.get_request_count(
            user_id=user_id, tenant_id=tenant_id, time_range="14d"
        )
        calls_last_week = calls_last_two_weeks - calls_this_week

        calls_trend = None
        if calls_last_week > 0:
            calls_trend = round((calls_this_week - calls_last_week) / calls_last_week * 100, 1)

        return DashboardStats(
            tools_available=tools_available,
            active_subscriptions=active_subscriptions,
            api_calls_this_week=calls_this_week,
            tools_trend=None,  # Would require historical snapshots
            subscriptions_trend=None,  # Would require historical snapshots
            calls_trend=calls_trend,
        )

    # ===== GET /v1/dashboard/activity =====

    async def get_dashboard_activity(
        self,
        user_id: str,
        tenant_id: str,
        limit: int = 5,
    ) -> List[RecentActivityItem]:
        """Get recent activity for dashboard.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            limit: Maximum activities to return

        Returns:
            List of recent activity items
        """
        activities_raw = await self._loki.get_recent_activity(
            user_id=user_id,
            tenant_id=tenant_id,
            limit=limit,
        )

        activities = []
        for act in (activities_raw or []):
            try:
                # Map activity type string to enum
                act_type = act.get("type", "api.call")
                try:
                    enum_type = ActivityType(act_type)
                except ValueError:
                    enum_type = ActivityType.API_CALL

                activities.append(RecentActivityItem(
                    id=act["id"],
                    type=enum_type,
                    title=act["title"],
                    description=act.get("description"),
                    tool_id=act.get("tool_id"),
                    tool_name=act.get("tool_name"),
                    timestamp=act["timestamp"],
                ))
            except (KeyError, ValueError) as e:
                logger.debug(f"Error parsing activity entry: {e}")
                continue

        return activities

    # ===== Helper Methods =====

    def _generate_empty_daily_calls(self, days: int) -> List[DailyCallStat]:
        """Generate empty daily stats as fallback."""
        result = []
        for i in range(days - 1, -1, -1):
            date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
            result.append(DailyCallStat(date=date, calls=0))
        return result


# Global instance
metrics_service = MetricsService()
