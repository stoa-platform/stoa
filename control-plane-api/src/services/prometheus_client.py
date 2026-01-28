"""Prometheus client for PromQL queries (CAB-840)

Provides access to Prometheus metrics for usage statistics.
Uses httpx.AsyncClient with context managers following existing patterns.

Security Features:
- Circuit breaker for resilient service calls
- Input validation for tenant_id and time_range
- Predefined safe label names to prevent injection
"""
import logging
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import httpx
from circuitbreaker import circuit, CircuitBreakerError

from ..config import settings

# ===== Security Constants (CAB-840) =====

# Regex pattern for validating tenant_id, user_id, etc.
IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

# Allowlist of safe label names to prevent PromQL injection
SAFE_LABEL_NAMES = frozenset({
    'tenant_id', 'user_id', 'subscription_id', 'tool_id', 'tool_name', 'status'
})

# Allowlist of safe time ranges (max 90d per review)
SAFE_TIME_RANGES = frozenset({
    '1h', '6h', '12h', '24h', '1d', '7d', '14d', '30d', '90d'
})

logger = logging.getLogger(__name__)


class PrometheusClient:
    """Service for Prometheus PromQL queries with circuit breaker protection."""

    def __init__(self):
        self._base_url: str = settings.PROMETHEUS_INTERNAL_URL.rstrip("/")
        self._timeout: float = float(settings.PROMETHEUS_TIMEOUT_SECONDS)
        self._enabled: bool = settings.PROMETHEUS_ENABLED
        self._circuit_failure_threshold: int = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self._circuit_recovery_timeout: int = settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    # ===== Input Validation (CAB-840 Security) =====

    def _validate_identifier(self, value: Optional[str], field: str) -> Optional[str]:
        """Validate identifier format to prevent injection.

        Args:
            value: The value to validate
            field: Field name for error messages

        Returns:
            The validated value or None

        Raises:
            ValueError: If value doesn't match safe pattern
        """
        if value is None:
            return None
        if not IDENTIFIER_PATTERN.match(value):
            raise ValueError(f"Invalid {field} format: must match ^[a-zA-Z0-9_-]{{1,64}}$")
        return value

    def _validate_time_range(self, time_range: str) -> str:
        """Validate time range against allowlist.

        Args:
            time_range: Time range string (e.g., "24h", "7d")

        Returns:
            The validated time range

        Raises:
            ValueError: If time_range not in allowlist
        """
        if time_range not in SAFE_TIME_RANGES:
            raise ValueError(f"Invalid time_range: {time_range}. Allowed: {', '.join(sorted(SAFE_TIME_RANGES))}")
        return time_range

    def _validate_and_build_labels(self, **kwargs: Optional[str]) -> str:
        """Build PromQL label selector with validation.

        Args:
            **kwargs: Label name/value pairs (e.g., tenant_id="acme")

        Returns:
            Validated PromQL label selector string

        Raises:
            ValueError: If label name not in allowlist or value invalid
        """
        labels = []
        for name, value in kwargs.items():
            if name not in SAFE_LABEL_NAMES:
                raise ValueError(f"Invalid label name: {name}. Allowed: {', '.join(sorted(SAFE_LABEL_NAMES))}")
            if value is not None:
                # Validate the value
                self._validate_identifier(value, name)
                labels.append(f'{name}="{value}"')
        return ",".join(labels)

    async def connect(self):
        """Initialize Prometheus client (validates connectivity)."""
        if not self._enabled:
            logger.info("Prometheus client disabled via configuration")
            return

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/-/healthy")
                if response.status_code == 200:
                    logger.info(f"Prometheus connected at {self._base_url}")
                else:
                    logger.warning(f"Prometheus health check failed: {response.status_code}")
        except Exception as e:
            logger.warning(f"Prometheus connectivity check failed: {e}")

    async def disconnect(self):
        """Cleanup (no-op for stateless client)."""
        pass

    @circuit(
        failure_threshold=5,
        recovery_timeout=30,
        expected_exception=Exception,
        name="prometheus_query"
    )
    async def query(self, promql: str) -> Optional[Dict[str, Any]]:
        """Execute instant PromQL query with circuit breaker protection.

        Args:
            promql: PromQL query string (should be built using validated inputs)

        Returns:
            Query result data or None on error

        Raises:
            CircuitBreakerError: When circuit is open after repeated failures
        """
        if not self._enabled:
            return None

        try:
            async with httpx.AsyncClient(
                base_url=f"{self._base_url}/api/v1",
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            ) as client:
                response = await client.get("/query", params={"query": promql})
                response.raise_for_status()
                data = response.json()
                if data.get("status") == "success":
                    return data.get("data", {})
                logger.warning(f"Prometheus query failed: {data}")
                return None
        except httpx.TimeoutException:
            logger.warning(f"Prometheus query timeout: {promql[:50]}...")
            raise  # Let circuit breaker count this as failure
        except Exception as e:
            logger.warning(f"Prometheus query error: {e}")
            raise  # Let circuit breaker count this as failure

    @circuit(
        failure_threshold=5,
        recovery_timeout=30,
        expected_exception=Exception,
        name="prometheus_query_range"
    )
    async def query_range(
        self,
        promql: str,
        start: datetime,
        end: datetime,
        step: str = "1h"
    ) -> Optional[Dict[str, Any]]:
        """Execute range PromQL query with circuit breaker protection.

        Args:
            promql: PromQL query string (should be built using validated inputs)
            start: Start timestamp
            end: End timestamp
            step: Query resolution step (e.g., "1h", "1d")

        Returns:
            Query result data or None on error

        Raises:
            CircuitBreakerError: When circuit is open after repeated failures
        """
        if not self._enabled:
            return None

        try:
            async with httpx.AsyncClient(
                base_url=f"{self._base_url}/api/v1",
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            ) as client:
                response = await client.get("/query_range", params={
                    "query": promql,
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z",
                    "step": step,
                })
                response.raise_for_status()
                data = response.json()
                if data.get("status") == "success":
                    return data.get("data", {})
                return None
        except Exception as e:
            logger.warning(f"Prometheus range query error: {e}")
            raise  # Let circuit breaker count this as failure

    # ===== Specific Query Methods (with validation) =====

    async def get_request_count(
        self,
        subscription_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        time_range: str = "24h"
    ) -> int:
        """Get total request count for given filters with input validation."""
        self._validate_time_range(time_range)
        labels = self._validate_and_build_labels(
            subscription_id=subscription_id,
            user_id=user_id,
            tenant_id=tenant_id
        )
        query = f'sum(increase(mcp_requests_total{{{labels}}}[{time_range}])) or vector(0)'
        try:
            result = await self.query(query)
            return self._extract_scalar(result, default=0)
        except CircuitBreakerError:
            logger.warning("Prometheus circuit breaker open, returning default")
            return 0

    async def get_success_count(
        self,
        subscription_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        time_range: str = "24h"
    ) -> int:
        """Get successful request count with input validation."""
        self._validate_time_range(time_range)
        labels = self._validate_and_build_labels(
            subscription_id=subscription_id,
            user_id=user_id,
            tenant_id=tenant_id
        )
        if labels:
            labels += ','
        query = f'sum(increase(mcp_requests_total{{{labels}status="success"}}[{time_range}])) or vector(0)'
        try:
            result = await self.query(query)
            return self._extract_scalar(result, default=0)
        except CircuitBreakerError:
            logger.warning("Prometheus circuit breaker open, returning default")
            return 0

    async def get_error_count(
        self,
        subscription_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        time_range: str = "24h"
    ) -> int:
        """Get error request count with input validation."""
        self._validate_time_range(time_range)
        labels = self._validate_and_build_labels(
            subscription_id=subscription_id,
            user_id=user_id,
            tenant_id=tenant_id
        )
        if labels:
            labels += ','
        query = f'sum(increase(mcp_requests_total{{{labels}status=~"error|timeout"}}[{time_range}])) or vector(0)'
        try:
            result = await self.query(query)
            return self._extract_scalar(result, default=0)
        except CircuitBreakerError:
            logger.warning("Prometheus circuit breaker open, returning default")
            return 0

    async def get_avg_latency_ms(
        self,
        subscription_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        time_range: str = "24h"
    ) -> int:
        """Get average latency in milliseconds with input validation."""
        self._validate_time_range(time_range)
        labels = self._validate_and_build_labels(
            subscription_id=subscription_id,
            user_id=user_id,
            tenant_id=tenant_id
        )
        query = f'''
            (
                sum(rate(mcp_request_duration_seconds_sum{{{labels}}}[{time_range}]))
                /
                sum(rate(mcp_request_duration_seconds_count{{{labels}}}[{time_range}]))
            ) * 1000
        '''.strip().replace('\n', ' ').replace('  ', ' ')
        try:
            result = await self.query(query)
            value = self._extract_scalar(result, default=0)
            # Handle NaN from division by zero
            if value != value:  # NaN check
                return 0
            return value
        except CircuitBreakerError:
            logger.warning("Prometheus circuit breaker open, returning default")
            return 0

    async def get_top_tools(
        self,
        user_id: str,
        tenant_id: str,
        limit: int = 5,
        time_range: str = "30d"
    ) -> List[Dict[str, Any]]:
        """Get top tools by usage count with input validation."""
        self._validate_identifier(user_id, "user_id")
        self._validate_identifier(tenant_id, "tenant_id")
        self._validate_time_range(time_range)

        query = f'''
            topk({limit},
                sum by (tool_id, tool_name) (
                    increase(mcp_requests_total{{user_id="{user_id}",tenant_id="{tenant_id}"}}[{time_range}])
                )
            )
        '''.strip().replace('\n', ' ').replace('  ', ' ')
        try:
            result = await self.query(query)
            return self._extract_tool_stats(result)
        except CircuitBreakerError:
            logger.warning("Prometheus circuit breaker open, returning empty list")
            return []

    async def get_daily_calls(
        self,
        user_id: str,
        tenant_id: str,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """Get daily call counts for the last N days with input validation."""
        self._validate_identifier(user_id, "user_id")
        self._validate_identifier(tenant_id, "tenant_id")

        end = datetime.utcnow()
        start = end - timedelta(days=days)
        query = f'sum(increase(mcp_requests_total{{user_id="{user_id}",tenant_id="{tenant_id}"}}[1d]))'

        try:
            result = await self.query_range(query, start, end, step="1d")
            return self._extract_daily_stats(result)
        except CircuitBreakerError:
            logger.warning("Prometheus circuit breaker open, returning empty list")
            return []

    async def get_tool_success_rate(
        self,
        tool_id: str,
        user_id: str,
        tenant_id: str,
        time_range: str = "30d"
    ) -> float:
        """Get success rate for a specific tool with input validation."""
        self._validate_identifier(tool_id, "tool_id")
        self._validate_identifier(user_id, "user_id")
        self._validate_identifier(tenant_id, "tenant_id")
        self._validate_time_range(time_range)

        labels = f'tool_id="{tool_id}",user_id="{user_id}",tenant_id="{tenant_id}"'
        query = f'''
            (
                sum(increase(mcp_requests_total{{{labels},status="success"}}[{time_range}]))
                /
                sum(increase(mcp_requests_total{{{labels}}}[{time_range}]))
            ) * 100
        '''.strip().replace('\n', ' ').replace('  ', ' ')
        try:
            result = await self.query(query)
            value = self._extract_scalar_float(result, default=100.0)
            # Handle NaN
            if value != value:
                return 100.0
            return round(value, 1)
        except CircuitBreakerError:
            logger.warning("Prometheus circuit breaker open, returning default")
            return 100.0

    async def get_tool_avg_latency(
        self,
        tool_id: str,
        user_id: str,
        tenant_id: str,
        time_range: str = "30d"
    ) -> int:
        """Get average latency for a specific tool with input validation."""
        self._validate_identifier(tool_id, "tool_id")
        self._validate_identifier(user_id, "user_id")
        self._validate_identifier(tenant_id, "tenant_id")
        self._validate_time_range(time_range)

        labels = f'tool_id="{tool_id}",user_id="{user_id}",tenant_id="{tenant_id}"'
        query = f'''
            (
                sum(rate(mcp_request_duration_seconds_sum{{{labels}}}[{time_range}]))
                /
                sum(rate(mcp_request_duration_seconds_count{{{labels}}}[{time_range}]))
            ) * 1000
        '''.strip().replace('\n', ' ').replace('  ', ' ')
        try:
            result = await self.query(query)
            value = self._extract_scalar(result, default=0)
            if value != value:  # NaN check
                return 0
            return value
        except CircuitBreakerError:
            logger.warning("Prometheus circuit breaker open, returning default")
            return 0

    # ===== Aggregate Statistics Methods (CAB-840) =====

    async def get_api_statistics(
        self,
        tenant_id: str,
        time_range: str = "24h"
    ) -> Dict[str, Any]:
        """Get aggregate API statistics for a tenant.

        Args:
            tenant_id: Tenant ID to filter by
            time_range: Time range for statistics (default: 24h)

        Returns:
            Dictionary with aggregate statistics:
            - total_requests: Total request count
            - success_rate: Success rate (0.0-1.0)
            - avg_latency_ms: Average latency in milliseconds
            - requests_by_status_code: Dict of status code -> count
        """
        self._validate_identifier(tenant_id, "tenant_id")
        self._validate_time_range(time_range)

        try:
            # Get total requests
            total_requests = await self.get_request_count(
                tenant_id=tenant_id, time_range=time_range
            )

            # Get success count for rate calculation
            success_count = await self.get_success_count(
                tenant_id=tenant_id, time_range=time_range
            )

            # Calculate success rate
            success_rate = (success_count / total_requests) if total_requests > 0 else 1.0

            # Get average latency
            avg_latency_ms = await self.get_avg_latency_ms(
                tenant_id=tenant_id, time_range=time_range
            )

            # Get requests by status code
            status_query = f'''
                sum by (status_code) (
                    increase(mcp_requests_total{{tenant_id="{tenant_id}"}}[{time_range}])
                )
            '''.strip().replace('\n', ' ').replace('  ', ' ')
            status_result = await self.query(status_query)
            requests_by_status_code = self._extract_status_code_stats(status_result)

            return {
                "total_requests": total_requests,
                "success_rate": round(success_rate, 4),
                "avg_latency_ms": avg_latency_ms,
                "requests_by_status_code": requests_by_status_code,
                "time_range": time_range,
            }
        except CircuitBreakerError:
            logger.warning("Prometheus circuit breaker open, returning empty statistics")
            return {
                "total_requests": 0,
                "success_rate": 1.0,
                "avg_latency_ms": 0,
                "requests_by_status_code": {},
                "time_range": time_range,
            }

    async def get_mcp_metrics(
        self,
        tenant_id: str,
        time_range: str = "24h"
    ) -> Dict[str, Any]:
        """Get MCP Gateway metrics for a tenant.

        Args:
            tenant_id: Tenant ID to filter by
            time_range: Time range for metrics (default: 24h)

        Returns:
            Dictionary with MCP-specific metrics:
            - total_tool_calls: Total tool invocations
            - tool_calls_by_name: Dict of tool_name -> count
            - avg_execution_time_ms: Average tool execution time
            - error_rate: Error rate (0.0-1.0)
            - active_sessions: Count of active sessions (approximate)
        """
        self._validate_identifier(tenant_id, "tenant_id")
        self._validate_time_range(time_range)

        try:
            # Get total tool calls
            total_query = f'sum(increase(stoa_mcp_tool_invocations_total{{tenant_id="{tenant_id}"}}[{time_range}])) or vector(0)'
            total_result = await self.query(total_query)
            total_tool_calls = self._extract_scalar(total_result, default=0)

            # Get tool calls by name
            by_name_query = f'''
                sum by (tool_name) (
                    increase(stoa_mcp_tool_invocations_total{{tenant_id="{tenant_id}"}}[{time_range}])
                )
            '''.strip().replace('\n', ' ').replace('  ', ' ')
            by_name_result = await self.query(by_name_query)
            tool_calls_by_name = self._extract_by_label_stats(by_name_result, "tool_name")

            # Get average execution time
            latency_query = f'''
                (
                    sum(rate(stoa_mcp_tool_invocation_duration_seconds_sum{{tenant_id="{tenant_id}"}}[{time_range}]))
                    /
                    sum(rate(stoa_mcp_tool_invocation_duration_seconds_count{{tenant_id="{tenant_id}"}}[{time_range}]))
                ) * 1000
            '''.strip().replace('\n', ' ').replace('  ', ' ')
            latency_result = await self.query(latency_query)
            avg_execution_time_ms = self._extract_scalar(latency_result, default=0)
            if avg_execution_time_ms != avg_execution_time_ms:  # NaN check
                avg_execution_time_ms = 0

            # Get error count for error rate
            error_query = f'sum(increase(stoa_mcp_tool_invocations_total{{tenant_id="{tenant_id}",status="error"}}[{time_range}])) or vector(0)'
            error_result = await self.query(error_query)
            error_count = self._extract_scalar(error_result, default=0)
            error_rate = (error_count / total_tool_calls) if total_tool_calls > 0 else 0.0

            # Get active sessions (approximate - unique sessions in time range)
            sessions_query = f'count(count by (session_id) (stoa_mcp_tool_invocations_total{{tenant_id="{tenant_id}"}})) or vector(0)'
            sessions_result = await self.query(sessions_query)
            active_sessions = self._extract_scalar(sessions_result, default=0)

            return {
                "total_tool_calls": total_tool_calls,
                "tool_calls_by_name": tool_calls_by_name,
                "avg_execution_time_ms": avg_execution_time_ms,
                "error_rate": round(error_rate, 4),
                "active_sessions": active_sessions,
                "time_range": time_range,
            }
        except CircuitBreakerError:
            logger.warning("Prometheus circuit breaker open, returning empty MCP metrics")
            return {
                "total_tool_calls": 0,
                "tool_calls_by_name": {},
                "avg_execution_time_ms": 0,
                "error_rate": 0.0,
                "active_sessions": 0,
                "time_range": time_range,
            }

    def _extract_status_code_stats(self, result: Optional[Dict]) -> Dict[int, int]:
        """Extract status code statistics from Prometheus result."""
        if not result:
            return {}
        stats = {}
        try:
            for item in result.get("result", []):
                metric = item.get("metric", {})
                status_code = metric.get("status_code", "unknown")
                value = float(item.get("value", [0, 0])[1])
                if value != value:  # NaN check
                    value = 0
                try:
                    stats[int(status_code)] = int(value)
                except (ValueError, TypeError):
                    stats[status_code] = int(value)
        except Exception as e:
            logger.warning(f"Error extracting status code stats: {e}")
        return stats

    def _extract_by_label_stats(self, result: Optional[Dict], label_name: str) -> Dict[str, int]:
        """Extract statistics grouped by a label from Prometheus result."""
        if not result:
            return {}
        stats = {}
        try:
            for item in result.get("result", []):
                metric = item.get("metric", {})
                label_value = metric.get(label_name, "unknown")
                value = float(item.get("value", [0, 0])[1])
                if value != value:  # NaN check
                    value = 0
                stats[label_value] = int(value)
        except Exception as e:
            logger.warning(f"Error extracting {label_name} stats: {e}")
        return stats

    # ===== Helper Methods =====

    def _extract_scalar(self, result: Optional[Dict], default: int = 0) -> int:
        """Extract scalar value from Prometheus result."""
        if not result:
            return default
        try:
            if result.get("resultType") == "vector":
                values = result.get("result", [])
                if values:
                    raw_value = float(values[0].get("value", [0, 0])[1])
                    # Handle NaN and Inf
                    if raw_value != raw_value or raw_value == float('inf'):
                        return default
                    return int(raw_value)
            return default
        except (IndexError, ValueError, TypeError):
            return default

    def _extract_scalar_float(self, result: Optional[Dict], default: float = 0.0) -> float:
        """Extract scalar float value from Prometheus result."""
        if not result:
            return default
        try:
            if result.get("resultType") == "vector":
                values = result.get("result", [])
                if values:
                    raw_value = float(values[0].get("value", [0, 0])[1])
                    if raw_value != raw_value or raw_value == float('inf'):
                        return default
                    return raw_value
            return default
        except (IndexError, ValueError, TypeError):
            return default

    def _extract_tool_stats(self, result: Optional[Dict]) -> List[Dict[str, Any]]:
        """Extract tool statistics from Prometheus result."""
        if not result:
            return []
        tools = []
        try:
            for item in result.get("result", []):
                metric = item.get("metric", {})
                value = float(item.get("value", [0, 0])[1])
                if value != value:  # NaN check
                    value = 0
                tools.append({
                    "tool_id": metric.get("tool_id", "unknown"),
                    "tool_name": metric.get("tool_name", "Unknown Tool"),
                    "call_count": int(value),
                })
        except Exception as e:
            logger.warning(f"Error extracting tool stats: {e}")
        return tools

    def _extract_daily_stats(self, result: Optional[Dict]) -> List[Dict[str, Any]]:
        """Extract daily statistics from Prometheus range result."""
        if not result:
            return []
        daily = []
        try:
            for item in result.get("result", []):
                for timestamp, value in item.get("values", []):
                    date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
                    raw_value = float(value)
                    if raw_value != raw_value:  # NaN check
                        raw_value = 0
                    daily.append({
                        "date": date,
                        "calls": int(raw_value),
                    })
        except Exception as e:
            logger.warning(f"Error extracting daily stats: {e}")
        return daily


# Global instance
prometheus_client = PrometheusClient()
