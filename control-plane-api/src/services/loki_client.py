"""Loki client for LogQL queries (CAB-840)

Provides access to Loki logs for call history and activity feeds.
Uses httpx.AsyncClient with context managers following existing patterns.
"""
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class LokiClient:
    """Service for Loki LogQL queries."""

    def __init__(self):
        self._base_url: str = settings.LOKI_INTERNAL_URL.rstrip("/")
        self._timeout: float = float(settings.LOKI_TIMEOUT_SECONDS)
        self._enabled: bool = settings.LOKI_ENABLED

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def connect(self):
        """Initialize Loki client (validates connectivity)."""
        if not self._enabled:
            logger.info("Loki client disabled via configuration")
            return

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/ready")
                if response.status_code == 200:
                    logger.info(f"Loki connected at {self._base_url}")
                else:
                    logger.warning(f"Loki health check failed: {response.status_code}")
        except Exception as e:
            logger.warning(f"Loki connectivity check failed: {e}")

    async def disconnect(self):
        """Cleanup (no-op for stateless client)."""
        pass

    async def query_range(
        self,
        logql: str,
        start: datetime,
        end: datetime,
        limit: int = 100,
        direction: str = "backward"
    ) -> Optional[List[Dict[str, Any]]]:
        """Execute LogQL range query.

        Args:
            logql: LogQL query string
            start: Start timestamp
            end: End timestamp
            limit: Maximum number of entries to return
            direction: Query direction ("forward" or "backward")

        Returns:
            List of log entries or None on error
        """
        if not self._enabled:
            return None

        try:
            async with httpx.AsyncClient(
                base_url=f"{self._base_url}/loki/api/v1",
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            ) as client:
                response = await client.get("/query_range", params={
                    "query": logql,
                    "start": str(int(start.timestamp() * 1e9)),  # nanoseconds
                    "end": str(int(end.timestamp() * 1e9)),
                    "limit": limit,
                    "direction": direction,
                })
                response.raise_for_status()
                data = response.json()
                if data.get("status") == "success":
                    return self._extract_log_entries(data.get("data", {}))
                return None
        except httpx.TimeoutException:
            logger.warning(f"Loki query timeout: {logql[:50]}...")
            return None
        except Exception as e:
            logger.warning(f"Loki query error: {e}")
            return None

    # ===== Specific Query Methods =====

    async def get_recent_calls(
        self,
        user_id: str,
        tenant_id: str,
        limit: int = 20,
        tool_id: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent API calls from logs.

        Args:
            user_id: User ID to filter by
            tenant_id: Tenant ID to filter by
            limit: Maximum number of calls to return
            tool_id: Optional tool ID filter
            status: Optional status filter (success, error, timeout)
            from_date: Optional start date
            to_date: Optional end date

        Returns:
            List of call entries
        """
        end = to_date or datetime.utcnow()
        start = from_date or (end - timedelta(days=7))

        # Build LogQL query with stream selector and filters
        stream_selector = f'{{job="mcp-gateway",user_id="{user_id}",tenant_id="{tenant_id}"}}'
        line_filters = '| json'

        if tool_id:
            line_filters += f' | tool_id="{tool_id}"'
        if status:
            line_filters += f' | status="{status}"'

        query = f'{stream_selector} {line_filters}'

        entries = await self.query_range(query, start, end, limit=limit)
        return self._format_call_entries(entries or [])

    async def get_recent_activity(
        self,
        user_id: str,
        tenant_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent activity for dashboard.

        Args:
            user_id: User ID to filter by
            tenant_id: Tenant ID to filter by
            limit: Maximum number of activities to return

        Returns:
            List of activity entries
        """
        end = datetime.utcnow()
        start = end - timedelta(days=30)

        # Query for all activity types from multiple sources
        query = (
            f'{{job=~"mcp-gateway|control-plane-api",tenant_id="{tenant_id}",user_id="{user_id}"}} '
            f'| json '
            f'| event_type=~"subscription.*|api.call|key.rotated"'
        )

        entries = await self.query_range(query, start, end, limit=limit)
        return self._format_activity_entries(entries or [])

    # ===== Helper Methods =====

    def _extract_log_entries(self, data: Dict) -> List[Dict[str, Any]]:
        """Extract log entries from Loki response."""
        entries = []
        try:
            for stream in data.get("result", []):
                stream_labels = stream.get("stream", {})
                for value in stream.get("values", []):
                    timestamp_ns, log_line = value
                    entries.append({
                        "timestamp": datetime.utcfromtimestamp(int(timestamp_ns) / 1e9),
                        "raw": log_line,
                        "labels": stream_labels,
                    })
        except Exception as e:
            logger.warning(f"Error extracting log entries: {e}")
        return entries

    def _format_call_entries(self, entries: List[Dict]) -> List[Dict[str, Any]]:
        """Format log entries as UsageCall-compatible objects."""
        calls = []
        for i, entry in enumerate(entries):
            try:
                log_data = self._parse_log_line(entry.get("raw", "{}"))
                if not log_data:
                    continue

                calls.append({
                    "id": log_data.get("request_id", f"call-{i:04d}"),
                    "timestamp": entry.get("timestamp"),
                    "tool_id": log_data.get("tool_id", "unknown"),
                    "tool_name": log_data.get("tool_name", "Unknown"),
                    "status": log_data.get("status", "success"),
                    "latency_ms": int(log_data.get("duration_ms", 0)),
                    "error_message": log_data.get("error"),
                })
            except Exception as e:
                logger.debug(f"Skipping malformed call entry: {e}")
                continue
        return calls

    def _format_activity_entries(self, entries: List[Dict]) -> List[Dict[str, Any]]:
        """Format log entries as RecentActivityItem-compatible objects."""
        activities = []
        for i, entry in enumerate(entries):
            try:
                log_data = self._parse_log_line(entry.get("raw", "{}"))
                if not log_data:
                    continue

                event_type = log_data.get("event_type", "api.call")
                activities.append({
                    "id": log_data.get("event_id", f"act-{i:04d}"),
                    "type": event_type,
                    "title": self._get_activity_title(event_type, log_data),
                    "description": log_data.get("description"),
                    "tool_id": log_data.get("tool_id"),
                    "tool_name": log_data.get("tool_name"),
                    "timestamp": entry.get("timestamp"),
                })
            except Exception as e:
                logger.debug(f"Skipping malformed activity entry: {e}")
                continue
        return activities

    def _parse_log_line(self, log_line: str) -> Optional[Dict[str, Any]]:
        """Parse a log line as JSON."""
        try:
            return json.loads(log_line)
        except json.JSONDecodeError:
            return None

    def _get_activity_title(self, event_type: str, data: Dict) -> str:
        """Generate human-readable activity title."""
        tool_name = data.get("tool_name", "tool")
        titles = {
            "subscription.created": f"Subscribed to {tool_name}",
            "subscription.approved": f"Subscription approved for {tool_name}",
            "subscription.revoked": f"Subscription revoked for {tool_name}",
            "api.call": f"API call to {tool_name}",
            "key.rotated": f"API key rotated for {tool_name}",
        }
        return titles.get(event_type, f"Activity: {event_type}")


# Global instance
loki_client = LokiClient()
