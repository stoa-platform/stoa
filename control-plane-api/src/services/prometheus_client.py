"""Prometheus client for PromQL queries (CAB-840)

Provides access to Prometheus metrics for usage statistics.
Uses httpx.AsyncClient with context managers following existing patterns.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, cast

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

MCP_TOOL_CALLS_METRIC = "stoa_mcp_tools_calls_total"
MCP_TOOL_DURATION_METRIC = "stoa_mcp_tool_duration_seconds"
LEGACY_MCP_REQUEST_DURATION_METRIC = "mcp_request_duration_seconds"

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_TIME_RANGE_RE = re.compile(r"^[1-9][0-9]*(s|m|h|d|w)$")


class PrometheusClient:
    """Service for Prometheus PromQL queries."""

    def __init__(self):
        self._base_url: str = settings.PROMETHEUS_INTERNAL_URL.rstrip("/")
        self._timeout: float = float(settings.PROMETHEUS_TIMEOUT_SECONDS)
        self._enabled: bool = settings.PROMETHEUS_ENABLED

    @property
    def is_enabled(self) -> bool:
        return self._enabled

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

    async def query(self, promql: str) -> dict[str, Any] | None:
        """Execute instant PromQL query.

        Args:
            promql: PromQL query string

        Returns:
            Query result data or None on error
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
                    return cast(dict[str, Any], data.get("data", {}))
                logger.warning(f"Prometheus query failed: {data}")
                return None
        except httpx.TimeoutException:
            logger.warning(f"Prometheus query timeout: {promql[:50]}...")
            return None
        except Exception as e:
            logger.warning(f"Prometheus query error: {e}")
            return None

    async def query_range(self, promql: str, start: datetime, end: datetime, step: str = "1h") -> dict[str, Any] | None:
        """Execute range PromQL query.

        Args:
            promql: PromQL query string
            start: Start timestamp
            end: End timestamp
            step: Query resolution step (e.g., "1h", "1d")

        Returns:
            Query result data or None on error
        """
        if not self._enabled:
            return None

        try:
            async with httpx.AsyncClient(
                base_url=f"{self._base_url}/api/v1",
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            ) as client:
                response = await client.get(
                    "/query_range",
                    params={
                        "query": promql,
                        "start": start.isoformat() + "Z",
                        "end": end.isoformat() + "Z",
                        "step": step,
                    },
                )
                response.raise_for_status()
                data = response.json()
                if data.get("status") == "success":
                    return cast(dict[str, Any], data.get("data", {}))
                return None
        except Exception as e:
            logger.warning(f"Prometheus range query error: {e}")
            return None

    async def _query(self, promql: str) -> list[dict[str, Any]]:
        """Execute an instant query and return the raw Prometheus result vector.

        Older router code uses this thin wrapper directly. Keep it as a
        compatibility shim over query() so all Prometheus HTTP behavior remains
        centralized in one method.
        """
        data = await self.query(promql)
        if data is None:
            raise ConnectionError("Prometheus query failed")
        return cast(list[dict[str, Any]], data.get("result", []))

    # ===== Specific Query Methods =====

    async def get_request_count(
        self,
        subscription_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
        time_range: str = "24h",
    ) -> int:
        """Get total request count for given filters."""
        label_sets = self._mcp_call_label_sets(
            subscription_id=subscription_id,
            tenant_id=tenant_id,
        )
        query = self._sum_increase_query(MCP_TOOL_CALLS_METRIC, label_sets, time_range)
        result = await self.query(query)
        return self._extract_scalar(result, default=0)

    async def get_success_count(
        self,
        subscription_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
        time_range: str = "24h",
    ) -> int:
        """Get successful request count."""
        label_sets = self._mcp_call_label_sets(
            subscription_id=subscription_id,
            tenant_id=tenant_id,
            status_selector='status="success"',
        )
        query = self._sum_increase_query(MCP_TOOL_CALLS_METRIC, label_sets, time_range)
        result = await self.query(query)
        return self._extract_scalar(result, default=0)

    async def get_error_count(
        self,
        subscription_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
        time_range: str = "24h",
    ) -> int:
        """Get error request count."""
        label_sets = self._mcp_call_label_sets(
            subscription_id=subscription_id,
            tenant_id=tenant_id,
            status_selector='status=~"error|timeout"',
        )
        query = self._sum_increase_query(MCP_TOOL_CALLS_METRIC, label_sets, time_range)
        result = await self.query(query)
        return self._extract_scalar(result, default=0)

    async def get_avg_latency_ms(
        self,
        subscription_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
        time_range: str = "24h",
    ) -> int:
        """Get average latency in milliseconds."""
        label_sets = self._mcp_call_label_sets(
            subscription_id=subscription_id,
            tenant_id=tenant_id,
        )
        sum_query = self._sum_rate_query(
            [MCP_TOOL_DURATION_METRIC, LEGACY_MCP_REQUEST_DURATION_METRIC],
            "sum",
            label_sets,
            time_range,
        )
        count_query = self._sum_rate_query(
            [MCP_TOOL_DURATION_METRIC, LEGACY_MCP_REQUEST_DURATION_METRIC],
            "count",
            label_sets,
            time_range,
        )
        query = f"""
            (
                ({sum_query})
                /
                ({count_query})
            ) * 1000
        """.strip().replace("\n", " ").replace("  ", " ")
        result = await self.query(query)
        value = self._extract_scalar(result, default=0)
        # Handle NaN from division by zero
        if value != value:  # NaN check
            return 0
        return value

    async def get_top_tools(
        self, user_id: str, tenant_id: str, limit: int = 5, time_range: str = "30d"
    ) -> list[dict[str, Any]]:
        """Get top tools by usage count."""
        legacy_labels = self._join_labels([self._label("tenant", tenant_id)])
        canonical_labels = self._join_labels([self._label("tenant_id", tenant_id)])
        query = f"""
            topk({limit},
                {self._compat_or([
                    f'sum by (tool_name) (label_replace(increase({MCP_TOOL_CALLS_METRIC}{{{legacy_labels}}}[{time_range}]), "tool_name", "$1", "tool", "(.+)"))',
                    f'sum by (tool_name) (increase({MCP_TOOL_CALLS_METRIC}{{{canonical_labels}}}[{time_range}]))',
                ], default_zero=False)}
            )
        """.strip().replace("\n", " ").replace("  ", " ")
        result = await self.query(query)
        return self._extract_tool_stats(result)

    async def get_daily_calls(self, user_id: str, tenant_id: str, days: int = 7) -> list[dict[str, Any]]:
        """Get daily call counts for the last N days."""
        end = datetime.utcnow()
        start = end - timedelta(days=days)
        label_sets = self._mcp_call_label_sets(tenant_id=tenant_id)
        query = self._sum_increase_query(MCP_TOOL_CALLS_METRIC, label_sets, "1d")

        result = await self.query_range(query, start, end, step="1d")
        return self._extract_daily_stats(result)

    async def get_tool_success_rate(self, tool_id: str, user_id: str, tenant_id: str, time_range: str = "30d") -> float:
        """Get success rate for a specific tool."""
        success_label_sets = self._mcp_call_label_sets(
            tenant_id=tenant_id,
            tool_name=tool_id,
            status_selector='status="success"',
        )
        total_label_sets = self._mcp_call_label_sets(
            tenant_id=tenant_id,
            tool_name=tool_id,
        )
        success_query = self._sum_increase_query(MCP_TOOL_CALLS_METRIC, success_label_sets, time_range)
        total_query = self._sum_increase_query(MCP_TOOL_CALLS_METRIC, total_label_sets, time_range)
        query = f"""
            (
                ({success_query})
                /
                ({total_query})
            ) * 100
        """.strip().replace("\n", " ").replace("  ", " ")
        result = await self.query(query)
        value = self._extract_scalar_float(result, default=100.0)
        # Handle NaN
        if value != value:
            return 100.0
        return round(value, 1)

    async def get_tool_avg_latency(self, tool_id: str, user_id: str, tenant_id: str, time_range: str = "30d") -> int:
        """Get average latency for a specific tool."""
        label_sets = self._mcp_call_label_sets(
            tenant_id=tenant_id,
            tool_name=tool_id,
        )
        sum_query = self._sum_rate_query(
            [MCP_TOOL_DURATION_METRIC, LEGACY_MCP_REQUEST_DURATION_METRIC],
            "sum",
            label_sets,
            time_range,
        )
        count_query = self._sum_rate_query(
            [MCP_TOOL_DURATION_METRIC, LEGACY_MCP_REQUEST_DURATION_METRIC],
            "count",
            label_sets,
            time_range,
        )
        query = f"""
            (
                ({sum_query})
                /
                ({count_query})
            ) * 1000
        """.strip().replace("\n", " ").replace("  ", " ")
        result = await self.query(query)
        value = self._extract_scalar(result, default=0)
        if value != value:  # NaN check
            return 0
        return value

    # ===== LLM Cost Query Methods (CAB-1487) =====

    async def get_llm_cost_total(
        self,
        tenant_id: str | None = None,
        time_range: str = "30d",
    ) -> float:
        """Get total LLM spend (USD) from gateway_llm_cost_total counter."""
        labels = f'tenant_id="{tenant_id}"' if tenant_id else ""
        query = f"sum(increase(gateway_llm_cost_total{{{labels}}}[{time_range}])) or vector(0)"
        result = await self.query(query)
        return self._extract_scalar_float(result, default=0.0)

    async def get_llm_cost_timeseries(
        self,
        tenant_id: str | None = None,
        days: int = 7,
        step: str = "1h",
    ) -> list[dict[str, Any]]:
        """Get LLM cost time-series (hourly buckets by default)."""
        end = datetime.utcnow()
        start = end - timedelta(days=days)
        labels = f'tenant_id="{tenant_id}"' if tenant_id else ""
        query = f"sum(increase(gateway_llm_cost_total{{{labels}}}[1h]))"
        result = await self.query_range(query, start, end, step=step)
        return self._extract_timeseries(result)

    async def get_llm_provider_breakdown(
        self,
        tenant_id: str | None = None,
        time_range: str = "30d",
    ) -> list[dict[str, Any]]:
        """Get LLM cost grouped by provider (and model)."""
        labels = f'tenant_id="{tenant_id}"' if tenant_id else ""
        query = f"sum by (provider, model) " f"(increase(gateway_llm_cost_total{{{labels}}}[{time_range}]))"
        result = await self.query(query)
        return self._extract_provider_breakdown(result)

    async def get_llm_token_totals(
        self,
        tenant_id: str | None = None,
        time_range: str = "30d",
    ) -> dict[str, int]:
        """Get total input/output tokens from gateway counters."""
        labels = f'tenant_id="{tenant_id}"' if tenant_id else ""
        input_q = f"sum(increase(gateway_llm_input_tokens_total{{{labels}}}[{time_range}])) or vector(0)"
        output_q = f"sum(increase(gateway_llm_output_tokens_total{{{labels}}}[{time_range}])) or vector(0)"
        input_result, output_result = await self.query(input_q), await self.query(output_q)
        return {
            "input_tokens": self._extract_scalar(input_result, default=0),
            "output_tokens": self._extract_scalar(output_result, default=0),
        }

    async def get_llm_cache_savings(
        self,
        tenant_id: str | None = None,
        time_range: str = "30d",
    ) -> dict[str, float]:
        """Get cache read cost savings from Anthropic prompt caching."""
        labels = f'tenant_id="{tenant_id}"' if tenant_id else ""
        read_q = f"sum(increase(gateway_llm_cache_read_cost_total{{{labels}}}[{time_range}])) or vector(0)"
        write_q = f"sum(increase(gateway_llm_cache_write_cost_total{{{labels}}}[{time_range}])) or vector(0)"
        read_result, write_result = await self.query(read_q), await self.query(write_q)
        return {
            "cache_read_cost_usd": round(self._extract_scalar_float(read_result, default=0.0), 6),
            "cache_write_cost_usd": round(self._extract_scalar_float(write_result, default=0.0), 6),
        }

    async def get_llm_avg_cost_per_request(
        self,
        tenant_id: str | None = None,
        time_range: str = "30d",
    ) -> float:
        """Get average cost per LLM request."""
        labels = f'tenant_id="{tenant_id}"' if tenant_id else ""
        query = (
            f"(sum(increase(gateway_llm_cost_total{{{labels}}}[{time_range}])) / "
            f"sum(increase(gateway_llm_requests_total{{{labels}}}[{time_range}]))) or vector(0)"
        )
        result = await self.query(query)
        value = self._extract_scalar_float(result, default=0.0)
        if value != value:  # NaN from 0/0
            return 0.0
        return round(value, 6)

    async def get_llm_latency_by_provider(
        self,
        tenant_id: str | None = None,
        time_range: str = "30d",
    ) -> list[dict[str, Any]]:
        """Get average LLM latency grouped by provider."""
        labels = f'tenant_id="{tenant_id}"' if tenant_id else ""
        query = (
            f"sum by (provider) "
            f"(rate(gateway_llm_latency_seconds_sum{{{labels}}}[{time_range}])) / "
            f"sum by (provider) "
            f"(rate(gateway_llm_latency_seconds_count{{{labels}}}[{time_range}]))"
        )
        result = await self.query(query)
        entries = []
        if result and result.get("resultType") == "vector":
            for item in result.get("result", []):
                metric = item.get("metric", {})
                val = float(item.get("value", [0, 0])[1])
                if val != val:
                    val = 0.0
                entries.append(
                    {
                        "provider": metric.get("provider", "unknown"),
                        "avg_latency_seconds": round(val, 4),
                    }
                )
        return entries

    # ===== Helper Methods =====

    def _build_labels(
        self, subscription_id: str | None = None, user_id: str | None = None, tenant_id: str | None = None
    ) -> str:
        """Build PromQL label selector.

        Maps API field names to gateway metric labels:
        - tenant_id -> tenant (gateway uses 'tenant' label, with fallback to 'default')
        - user_id not emitted by gateway, omitted from PromQL
        """
        labels = []
        if subscription_id:
            labels.append(self._label("subscription_id", subscription_id))
        if tenant_id:
            labels.append(self._label("tenant", tenant_id))
        return ",".join(labels)

    def _validate_identifier(self, value: str, field_name: str) -> str:
        """Validate a Prometheus label value used by router-level metrics endpoints."""
        if not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError(f"Invalid {field_name}: {value}")
        return value

    def _validate_time_range(self, value: str) -> str:
        """Validate compact Prometheus time ranges used by public usage endpoints."""
        if not _TIME_RANGE_RE.fullmatch(value):
            raise ValueError(f"Invalid time range: {value}")
        return value

    def _label(self, name: str, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{name}="{escaped}"'

    def _join_labels(self, labels: list[str]) -> str:
        return ",".join(label for label in labels if label)

    def _dedupe(self, values: list[str]) -> list[str]:
        deduped: list[str] = []
        for value in values:
            if value not in deduped:
                deduped.append(value)
        return deduped

    def _compat_or(self, queries: list[str], default_zero: bool = True) -> str:
        parts = self._dedupe([query for query in queries if query])
        if default_zero:
            parts.append("vector(0)")
        return " or ".join(parts)

    def _mcp_call_label_sets(
        self,
        subscription_id: str | None = None,
        tenant_id: str | None = None,
        tool_name: str | None = None,
        status_selector: str | None = None,
    ) -> list[str]:
        legacy_labels: list[str] = []
        canonical_labels: list[str] = []

        if subscription_id:
            legacy_labels.append(self._label("subscription_id", subscription_id))
            canonical_labels.append(self._label("subscription_id", subscription_id))
        if tenant_id:
            legacy_labels.append(self._label("tenant", tenant_id))
            canonical_labels.append(self._label("tenant_id", tenant_id))
        if tool_name:
            legacy_labels.append(self._label("tool", tool_name))
            canonical_labels.append(self._label("tool_name", tool_name))
        if status_selector:
            legacy_labels.append(status_selector)
            canonical_labels.append(status_selector)

        return self._dedupe(
            [
                self._join_labels(legacy_labels),
                self._join_labels(canonical_labels),
            ]
        )

    def _sum_increase_query(self, metric: str, label_sets: list[str], time_range: str) -> str:
        return self._compat_or([f"sum(increase({metric}{{{labels}}}[{time_range}]))" for labels in label_sets])

    def _sum_rate_query(
        self,
        metric_bases: list[str],
        suffix: str,
        label_sets: list[str],
        time_range: str,
    ) -> str:
        return self._compat_or(
            [
                f"sum(rate({metric}_{suffix}{{{labels}}}[{time_range}]))"
                for metric in metric_bases
                for labels in label_sets
            ]
        )

    def _extract_scalar(self, result: dict | None, default: int = 0) -> int:
        """Extract scalar value from Prometheus result."""
        if not result:
            return default
        try:
            if result.get("resultType") == "vector":
                values = result.get("result", [])
                if values:
                    raw_value = float(values[0].get("value", [0, 0])[1])
                    # Handle NaN and Inf
                    if raw_value != raw_value or raw_value == float("inf"):
                        return default
                    return int(raw_value)
            return default
        except (IndexError, ValueError, TypeError):
            return default

    def _extract_scalar_float(self, result: dict | None, default: float = 0.0) -> float:
        """Extract scalar float value from Prometheus result."""
        if not result:
            return default
        try:
            if result.get("resultType") == "vector":
                values = result.get("result", [])
                if values:
                    raw_value = float(values[0].get("value", [0, 0])[1])
                    if raw_value != raw_value or raw_value == float("inf"):
                        return default
                    return raw_value
            return default
        except (IndexError, ValueError, TypeError):
            return default

    def _extract_tool_stats(self, result: dict | None) -> list[dict[str, Any]]:
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
                tool_name = metric.get("tool_name") or metric.get("tool") or "Unknown Tool"
                tools.append(
                    {
                        "tool_id": metric.get("tool_id") or tool_name,
                        "tool_name": tool_name,
                        "call_count": int(value),
                    }
                )
        except Exception as e:
            logger.warning(f"Error extracting tool stats: {e}")
        return tools

    def _extract_timeseries(self, result: dict | None) -> list[dict[str, Any]]:
        """Extract time-series points from Prometheus range result."""
        if not result:
            return []
        points: list[dict[str, Any]] = []
        try:
            for item in result.get("result", []):
                for timestamp, value in item.get("values", []):
                    raw = float(value)
                    if raw != raw:  # NaN
                        raw = 0.0
                    points.append(
                        {
                            "timestamp": datetime.utcfromtimestamp(timestamp).isoformat() + "Z",
                            "value": round(raw, 6),
                        }
                    )
        except Exception as e:
            logger.warning(f"Error extracting timeseries: {e}")
        return points

    def _extract_provider_breakdown(self, result: dict | None) -> list[dict[str, Any]]:
        """Extract provider/model breakdown from Prometheus vector result."""
        if not result:
            return []
        entries: list[dict[str, Any]] = []
        try:
            for item in result.get("result", []):
                metric = item.get("metric", {})
                raw = float(item.get("value", [0, 0])[1])
                if raw != raw:
                    raw = 0.0
                entries.append(
                    {
                        "provider": metric.get("provider", "unknown"),
                        "model": metric.get("model", "unknown"),
                        "cost_usd": round(raw, 6),
                    }
                )
        except Exception as e:
            logger.warning(f"Error extracting provider breakdown: {e}")
        # Sort descending by cost
        entries.sort(key=lambda x: x["cost_usd"], reverse=True)
        return entries

    def _extract_daily_stats(self, result: dict | None) -> list[dict[str, Any]]:
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
                    daily.append(
                        {
                            "date": date,
                            "calls": int(raw_value),
                        }
                    )
        except Exception as e:
            logger.warning(f"Error extracting daily stats: {e}")
        return daily


# Global instance
prometheus_client = PrometheusClient()
