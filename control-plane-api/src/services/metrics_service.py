# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Metrics orchestration service (CAB-840)

Combines data from Prometheus, Loki, and PostgreSQL for usage endpoints.
Implements graceful degradation when external services are unavailable.

Security Features (CAB-840):
- Circuit breaker error handling with degraded state reporting
- All responses include degraded flag for client awareness
"""
import logging
from typing import Optional, List
from datetime import datetime, timedelta
from circuitbreaker import CircuitBreakerError

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
    MCPMetricsResponse,
    SubscriptionMetricsResponse,
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
        """Get comprehensive usage summary for a user with degraded state tracking.

        Args:
            user_id: User ID
            tenant_id: Tenant ID

        Returns:
            UsageSummary with period stats, top tools, daily calls, and degraded state
        """
        degraded_services: List[str] = []

        # Fetch period stats (today, week, month) - track Prometheus degradation
        try:
            today_stats = await self._get_period_stats(user_id, tenant_id, "1d", "today")
            week_stats = await self._get_period_stats(user_id, tenant_id, "7d", "week")
            month_stats = await self._get_period_stats(user_id, tenant_id, "30d", "month")
        except (CircuitBreakerError, ValueError) as e:
            logger.warning(f"Prometheus degraded for usage summary: {e}")
            if "prometheus" not in degraded_services:
                degraded_services.append("prometheus")
            today_stats = self._empty_period_stats("today")
            week_stats = self._empty_period_stats("week")
            month_stats = self._empty_period_stats("month")

        # Get top tools
        try:
            top_tools_raw = await self._prometheus.get_top_tools(user_id, tenant_id, limit=5)
            top_tools = await self._enrich_tool_stats(top_tools_raw, user_id, tenant_id)
        except (CircuitBreakerError, ValueError) as e:
            logger.warning(f"Prometheus degraded for top tools: {e}")
            if "prometheus" not in degraded_services:
                degraded_services.append("prometheus")
            top_tools = []

        # Get daily calls for chart
        try:
            daily_raw = await self._prometheus.get_daily_calls(user_id, tenant_id, days=7)
            daily_calls = [DailyCallStat(date=d["date"], calls=d["calls"]) for d in daily_raw]
        except (CircuitBreakerError, ValueError) as e:
            logger.warning(f"Prometheus degraded for daily calls: {e}")
            if "prometheus" not in degraded_services:
                degraded_services.append("prometheus")
            daily_calls = []

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
            degraded=bool(degraded_services),
            degraded_services=degraded_services,
        )

    def _empty_period_stats(self, period: str) -> UsagePeriodStats:
        """Return empty period stats for degraded mode."""
        return UsagePeriodStats(
            period=period,
            total_calls=0,
            success_count=0,
            error_count=0,
            success_rate=100.0,
            avg_latency_ms=0,
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
            # Use 90d as max time range per CAB-840 security review
            call_count = await self._prometheus.get_request_count(
                subscription_id=str(sub.id),
                time_range="90d"
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

    # ===== CAB-840: New Metrics Methods =====

    async def get_mcp_metrics(
        self,
        tenant_id: str,
        time_range: str = "24h"
    ) -> MCPMetricsResponse:
        """Get MCP Gateway metrics for a tenant with degraded state tracking.

        Args:
            tenant_id: Tenant ID
            time_range: Time range for metrics (default: 24h)

        Returns:
            MCPMetricsResponse with tool call stats and degraded state
        """
        degraded_services: List[str] = []

        try:
            metrics = await self._prometheus.get_mcp_metrics(tenant_id, time_range)

            return MCPMetricsResponse(
                total_tool_calls=metrics.get("total_tool_calls", 0),
                tool_calls_by_name=metrics.get("tool_calls_by_name", {}),
                avg_execution_time_ms=metrics.get("avg_execution_time_ms", 0),
                error_rate=metrics.get("error_rate", 0.0),
                active_sessions=metrics.get("active_sessions", 0),
                time_range=time_range,
                degraded=False,
                degraded_services=[],
            )
        except (CircuitBreakerError, ValueError) as e:
            logger.warning(f"Prometheus degraded for MCP metrics: {e}")
            degraded_services.append("prometheus")

            return MCPMetricsResponse(
                total_tool_calls=0,
                tool_calls_by_name={},
                avg_execution_time_ms=0,
                error_rate=0.0,
                active_sessions=0,
                time_range=time_range,
                degraded=True,
                degraded_services=degraded_services,
            )

    async def get_subscription_metrics(
        self,
        subscription_id: str,
        user_id: str,
        tenant_id: str,
        time_range: str = "30d"
    ) -> SubscriptionMetricsResponse:
        """Get per-subscription usage metrics with degraded state tracking.

        Args:
            subscription_id: Subscription ID
            user_id: User ID (for validation)
            tenant_id: Tenant ID (for validation)
            time_range: Time range for metrics (default: 30d)

        Returns:
            SubscriptionMetricsResponse with usage stats and degraded state
        """
        degraded_services: List[str] = []

        try:
            # Get total calls for subscription
            total_calls = await self._prometheus.get_request_count(
                subscription_id=subscription_id,
                time_range=time_range
            )

            # Get success count for rate calculation
            success_count = await self._prometheus.get_success_count(
                subscription_id=subscription_id,
                time_range=time_range
            )

            # Calculate success rate
            success_rate = (success_count / total_calls * 100) if total_calls > 0 else 100.0

            # Get average latency
            avg_latency_ms = await self._prometheus.get_avg_latency_ms(
                subscription_id=subscription_id,
                time_range=time_range
            )

            # Get daily breakdown (use 7 days for chart)
            end = datetime.utcnow()
            start = end - timedelta(days=7)
            daily_query = f'sum(increase(mcp_requests_total{{subscription_id="{subscription_id}"}}[1d]))'
            daily_result = await self._prometheus.query_range(daily_query, start, end, step="1d")

            daily_breakdown = []
            if daily_result:
                for item in daily_result.get("result", []):
                    for timestamp, value in item.get("values", []):
                        date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
                        raw_value = float(value)
                        if raw_value != raw_value:  # NaN check
                            raw_value = 0
                        daily_breakdown.append(DailyCallStat(date=date, calls=int(raw_value)))

            if not daily_breakdown:
                daily_breakdown = self._generate_empty_daily_calls(7)

            return SubscriptionMetricsResponse(
                subscription_id=subscription_id,
                total_calls=total_calls,
                success_rate=round(success_rate, 1),
                avg_latency_ms=avg_latency_ms,
                daily_breakdown=daily_breakdown,
                time_range=time_range,
                degraded=False,
                degraded_services=[],
            )
        except (CircuitBreakerError, ValueError) as e:
            logger.warning(f"Prometheus degraded for subscription metrics: {e}")
            degraded_services.append("prometheus")

            return SubscriptionMetricsResponse(
                subscription_id=subscription_id,
                total_calls=0,
                success_rate=100.0,
                avg_latency_ms=0,
                daily_breakdown=self._generate_empty_daily_calls(7),
                time_range=time_range,
                degraded=True,
                degraded_services=degraded_services,
            )

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
