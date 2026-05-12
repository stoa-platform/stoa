"""Gateway metrics aggregation service for observability dashboard.

Phase 2 (CAB-1635): per-tenant filtering, adapter operation metrics, health history.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.metrics import (
    ADAPTER_OPERATION_DURATION,
    ADAPTER_OPERATIONS_TOTAL,
)
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.gateway_instance import GatewayInstance, GatewayInstanceStatus
from src.services.prometheus_client import prometheus_client

logger = logging.getLogger(__name__)

TimeRange = Literal["1h", "6h", "24h", "7d"]
GuardrailsState = Literal[
    "metrics_unavailable",
    "stale_data",
    "no_evaluations",
    "evaluations_zero_trips",
    "trips_observed",
]
StaleReason = Literal["prom_unreachable", "scrape_gap", "producer_absent", "stale_unknown"]

_GUARDRAILS_FULL_GUARDRAILS: tuple[str, ...] = (
    "pii",
    "injection",
    "prompt_guard",
    "content_filter",
    "rate_limit",
)
_GUARDRAILS_FULL_DECISIONS: tuple[str, ...] = ("allow", "redact", "block", "error")
_PROMETHEUS_SCRAPE_INTERVAL_SECONDS = 60
_MAX_FRESHNESS_THRESHOLD_SECONDS = 60 * 60

_GUARDRAILS_TOTAL_QUERIES: dict[str, str] = {
    "evaluations_count": "sum(increase(stoa_guardrails_evaluations_total[{range}]))",
    "decisions_count": "sum(increase(stoa_guardrails_decisions_total[{range}]))",
    "pii_detections": "sum(increase(stoa_guardrails_pii_detected_total[{range}]))",
    "injection_blocks": "sum(increase(stoa_guardrails_injection_blocked_total[{range}]))",
    "content_filter_blocks": "sum(increase(stoa_guardrails_content_filtered_total[{range}]))",
    "prompt_guard_blocks": "sum(increase(stoa_prompt_guard_detected_total[{range}]))",
}

_GUARDRAILS_TRIPS_QUERY = 'sum(increase(stoa_guardrails_decisions_total{{decision=~"redact|block"}}[{range}]))'
_GUARDRAILS_ERRORS_QUERY = 'sum(increase(stoa_guardrails_decisions_total{{decision="error"}}[{range}]))'
_GUARDRAILS_SCRAPE_SAMPLE_QUERY = "max(timestamp(stoa_guardrails_evaluations_total))"
_GUARDRAILS_BY_GUARDRAIL_EVAL_QUERY = "sum by (guardrail) (increase(stoa_guardrails_evaluations_total[{range}]))"
_GUARDRAILS_BY_GUARDRAIL_DECISION_QUERY = (
    "sum by (guardrail, decision) (increase(stoa_guardrails_decisions_total[{range}]))"
)
_GUARDRAILS_BY_GUARDRAIL_SCRAPE_QUERY = "max by (guardrail) (timestamp(stoa_guardrails_evaluations_total))"

_RATE_LIMIT_BLOCK_QUERIES: tuple[str, ...] = (
    "sum(increase(stoa_rate_limit_hits_total[{range}]))",
    "sum(increase(stoa_api_proxy_rate_limited_total[{range}]))",
    "sum(increase(stoa_ws_proxy_rate_limited_total[{range}]))",
)


class GatewayMetricsService:
    """Aggregates health and sync metrics across gateways."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_health_summary(self, tenant_id: str | None = None) -> dict:
        """Count gateways by status (online/offline/degraded/maintenance).

        Args:
            tenant_id: When provided, only count gateways belonging to this tenant.
                       cpi-admin passes None to see all.
        """
        counts = {}
        total = 0
        for status in GatewayInstanceStatus:
            query = select(func.count()).where(GatewayInstance.status == status)
            if tenant_id:
                query = query.where(GatewayInstance.tenant_id == tenant_id)
            result = await self.db.execute(query)
            count = result.scalar_one()
            counts[status.value] = count
            total += count

        counts["total_gateways"] = total
        if total > 0:
            online = counts.get("online", 0)
            counts["health_percentage"] = round((online / total) * 100, 1)
        else:
            counts["health_percentage"] = 0.0

        return counts

    async def get_sync_status_summary(self, gateway_id: UUID | None = None, tenant_id: str | None = None) -> dict:
        """Count deployments by sync_status, optionally filtered by gateway or tenant.

        Args:
            gateway_id: Filter by specific gateway instance.
            tenant_id: Filter by tenant (joins through gateway_instances).
                       Skipped when gateway_id is already provided.
        """
        counts = {}
        total = 0
        for status in DeploymentSyncStatus:
            query = select(func.count()).where(GatewayDeployment.sync_status == status)
            if gateway_id:
                query = query.where(GatewayDeployment.gateway_instance_id == gateway_id)
            elif tenant_id:
                query = query.join(
                    GatewayInstance,
                    GatewayDeployment.gateway_instance_id == GatewayInstance.id,
                ).where(GatewayInstance.tenant_id == tenant_id)
            result = await self.db.execute(query)
            count = result.scalar_one()
            counts[status.value] = count
            total += count

        counts["total_deployments"] = total
        synced = counts.get("synced", 0)
        if total > 0:
            counts["sync_percentage"] = round((synced / total) * 100, 1)
        else:
            counts["sync_percentage"] = 0.0

        return counts

    async def get_gateway_metrics(self, gateway_id: UUID, tenant_id: str | None = None) -> dict | None:
        """Per-gateway metrics: status, health, sync summary, recent errors.

        Args:
            gateway_id: Gateway instance ID.
            tenant_id: When provided, verifies gateway belongs to this tenant.
        """
        query = select(GatewayInstance).where(
            GatewayInstance.id == gateway_id,
            GatewayInstance.deleted_at.is_(None),
        )
        if tenant_id:
            query = query.where(GatewayInstance.tenant_id == tenant_id)
        result = await self.db.execute(query)
        gateway = result.scalar_one_or_none()
        if not gateway:
            return None

        sync_summary = await self.get_sync_status_summary(gateway_id=gateway_id)

        # Get recent errors (last 5)
        error_result = await self.db.execute(
            select(GatewayDeployment)
            .where(
                GatewayDeployment.gateway_instance_id == gateway_id,
                GatewayDeployment.sync_status == DeploymentSyncStatus.ERROR,
            )
            .order_by(GatewayDeployment.last_sync_attempt.desc())
            .limit(5)
        )
        recent_errors = [
            {
                "deployment_id": str(d.id),
                "api_catalog_id": str(d.api_catalog_id),
                "error": d.sync_error,
                "attempts": d.sync_attempts,
                "last_attempt": d.last_sync_attempt.isoformat() if d.last_sync_attempt else None,
            }
            for d in error_result.scalars().all()
        ]

        return {
            "gateway_id": str(gateway.id),
            "name": gateway.name,
            "display_name": gateway.display_name,
            "gateway_type": gateway.gateway_type.value if gateway.gateway_type else "",
            "status": gateway.status.value if gateway.status else "offline",
            "last_health_check": gateway.last_health_check.isoformat() if gateway.last_health_check else None,
            "sync": sync_summary,
            "recent_errors": recent_errors,
        }

    @staticmethod
    def _empty_guardrails_metrics(source_healthy: bool) -> dict[str, Any]:
        state: GuardrailsState = "no_evaluations" if source_healthy else "metrics_unavailable"
        stale_reason: StaleReason | None = None if source_healthy else "prom_unreachable"
        empty_count = 0 if source_healthy else None
        return {
            "state": state,
            "evaluations_count": empty_count,
            "decisions_count": empty_count,
            "trips_count": empty_count,
            "error_count": empty_count,
            "pii_detections": None,
            "injection_blocks": None,
            "prompt_guard_blocks": None,
            "content_filter_blocks": None,
            "rate_limit_blocks": None,
            "last_evaluation_delta_at": None,
            "last_decision_delta_at": None,
            "scrape_sample_at": None,
            "stale_reason": stale_reason,
            "by_guardrail": {
                guardrail: GatewayMetricsService._empty_guardrail_metrics(state, source_healthy, stale_reason)
                for guardrail in _GUARDRAILS_FULL_GUARDRAILS
            },
            "last_sample_at": None,
            "metrics_age_seconds": None,
            "source_healthy": source_healthy,
            # Compatibility fields for the current UI until PR-3B2 consumes the contract names.
            "content_filters": None,
            "prompt_guard_flags": None,
            "rate_limit_enforcements": None,
            "by_tool": {},
            "by_category": {},
        }

    @staticmethod
    def _empty_guardrail_metrics(
        state: GuardrailsState,
        source_healthy: bool,
        stale_reason: StaleReason | None,
    ) -> dict[str, Any]:
        empty_count = 0 if source_healthy else None
        return {
            "state": state,
            "evaluations_count": empty_count,
            "decisions_count": empty_count,
            "trips_count": empty_count,
            "error_count": empty_count,
            "last_evaluation_delta_at": None,
            "last_decision_delta_at": None,
            "scrape_sample_at": None,
            "source_healthy": source_healthy,
            "stale_reason": stale_reason,
        }

    @staticmethod
    def _extract_prometheus_scalar(result: dict[str, Any] | None) -> tuple[int | None, datetime | None, bool]:
        """Return scalar value, sample timestamp, and whether the result was interpretable."""
        if result is None:
            return None, None, False

        values = result.get("result")
        if not isinstance(values, list):
            return None, None, False
        if not values:
            return None, None, True

        raw_value = values[0].get("value")
        if not isinstance(raw_value, list) or len(raw_value) < 2:
            return None, None, False

        try:
            sample_at = datetime.fromtimestamp(float(raw_value[0]), UTC)
            numeric = float(raw_value[1])
        except (TypeError, ValueError, OSError):
            return None, None, False

        if numeric != numeric or numeric in {float("inf"), float("-inf")}:
            return None, None, False

        return int(numeric), sample_at, True

    @staticmethod
    def _extract_prometheus_vector(
        result: dict[str, Any] | None,
    ) -> tuple[list[tuple[dict[str, str], int, datetime]], bool]:
        """Return vector samples and whether the result was interpretable."""
        if result is None:
            return [], False

        values = result.get("result")
        if not isinstance(values, list):
            return [], False

        parsed: list[tuple[dict[str, str], int, datetime]] = []
        for item in values:
            if not isinstance(item, dict):
                return [], False
            raw_value = item.get("value")
            metric = item.get("metric", {})
            if not isinstance(raw_value, list) or len(raw_value) < 2 or not isinstance(metric, dict):
                return [], False
            try:
                sample_at = datetime.fromtimestamp(float(raw_value[0]), UTC)
                numeric = float(raw_value[1])
            except (TypeError, ValueError, OSError):
                return [], False
            if numeric != numeric or numeric in {float("inf"), float("-inf")}:
                return [], False

            parsed.append(({str(key): str(value) for key, value in metric.items()}, int(numeric), sample_at))

        return parsed, True

    @staticmethod
    def _extract_prometheus_timestamp(result: dict[str, Any] | None) -> tuple[datetime | None, bool]:
        """Return a timestamp encoded as the Prometheus sample value."""
        value, _, interpretable = GatewayMetricsService._extract_prometheus_scalar(result)
        if not interpretable or value is None:
            return None, interpretable
        try:
            return datetime.fromtimestamp(float(value), UTC), True
        except (TypeError, ValueError, OSError):
            return None, False

    async def _query_guardrails_scalar(self, promql: str, metric_name: str) -> tuple[int | None, datetime | None, bool]:
        try:
            result = await prometheus_client.query(promql)
        except Exception:
            logger.debug("Failed to fetch guardrails metric %s", metric_name)
            return None, None, False
        value, sample_at, interpretable = self._extract_prometheus_scalar(result)
        return value, sample_at, interpretable

    async def _query_guardrails_vector(
        self, promql: str, metric_name: str
    ) -> tuple[list[tuple[dict[str, str], int, datetime]], bool]:
        try:
            result = await prometheus_client.query(promql)
        except Exception:
            logger.debug("Failed to fetch guardrails metric %s", metric_name)
            return [], False
        return self._extract_prometheus_vector(result)

    async def _query_guardrails_timestamp(self, promql: str, metric_name: str) -> tuple[datetime | None, bool]:
        try:
            result = await prometheus_client.query(promql)
        except Exception:
            logger.debug("Failed to fetch guardrails metric %s", metric_name)
            return None, False
        return self._extract_prometheus_timestamp(result)

    @staticmethod
    def _metrics_age_seconds(last_sample_at: datetime | None) -> int | None:
        if last_sample_at is None:
            return None
        return max(0, int(datetime.now(UTC).timestamp() - last_sample_at.timestamp()))

    @staticmethod
    def _freshness_threshold_seconds(
        time_range: TimeRange,
        scrape_interval_seconds: int = _PROMETHEUS_SCRAPE_INTERVAL_SECONDS,
    ) -> int:
        if time_range == "1h":
            floor = 5 * 60
        elif time_range in {"6h", "24h"}:
            floor = 10 * 60
        else:
            floor = 30 * 60
        return min(max(2 * scrape_interval_seconds, floor), _MAX_FRESHNESS_THRESHOLD_SECONDS)

    @staticmethod
    def _derive_guardrails_counts(decisions: dict[str, int]) -> dict[str, int]:
        bounded = {decision: max(0, int(decisions.get(decision, 0))) for decision in _GUARDRAILS_FULL_DECISIONS}
        return {
            "decisions_count": sum(bounded.values()),
            "trips_count": bounded["redact"] + bounded["block"],
            "error_count": bounded["error"],
        }

    @staticmethod
    def _derive_guardrails_state(
        *,
        source_healthy: bool,
        producer_present: bool,
        evaluations_count: int | None,
        trips_count: int | None,
        scrape_age_seconds: int | None,
        freshness_threshold_seconds: int,
    ) -> GuardrailsState:
        if not source_healthy or not producer_present:
            return "metrics_unavailable"
        if scrape_age_seconds is None:
            return "metrics_unavailable"
        if scrape_age_seconds > freshness_threshold_seconds:
            return "stale_data"
        if evaluations_count is None or trips_count is None:
            return "metrics_unavailable"
        if evaluations_count == 0:
            return "no_evaluations"
        if trips_count == 0:
            return "evaluations_zero_trips"
        return "trips_observed"

    @staticmethod
    def _guardrails_stale_reason(
        state: GuardrailsState,
        *,
        prometheus_ok: bool,
        producer_present: bool,
    ) -> StaleReason | None:
        if not prometheus_ok:
            return "prom_unreachable"
        if not producer_present:
            return "producer_absent"
        if state == "stale_data":
            return "scrape_gap"
        if state == "metrics_unavailable":
            return "stale_unknown"
        return None

    @staticmethod
    def _source_is_healthy(
        prometheus_ok: bool, producer_present: bool, scrape_age_seconds: int | None, threshold: int
    ) -> bool:
        return bool(
            prometheus_ok and producer_present and scrape_age_seconds is not None and scrape_age_seconds <= threshold
        )

    async def _fetch_guardrails_metrics(self, time_range: TimeRange = "1h") -> dict[str, Any]:
        """Fetch guardrails counters + freshness from Prometheus."""
        guardrails = self._empty_guardrails_metrics(source_healthy=False)
        if not prometheus_client.is_enabled:
            return guardrails

        guardrails = self._empty_guardrails_metrics(source_healthy=True)
        prometheus_ok = True
        newest_sample_at: datetime | None = None
        sample_ats: dict[str, datetime] = {}

        for key, promql_template in _GUARDRAILS_TOTAL_QUERIES.items():
            value, sample_at, ok = await self._query_guardrails_scalar(promql_template.format(range=time_range), key)
            prometheus_ok = prometheus_ok and ok
            if not ok:
                continue
            guardrails[key] = value
            if sample_at:
                sample_ats[key] = sample_at
                if newest_sample_at is None or sample_at > newest_sample_at:
                    newest_sample_at = sample_at

        for key, promql_template in {
            "trips_count": _GUARDRAILS_TRIPS_QUERY,
            "error_count": _GUARDRAILS_ERRORS_QUERY,
        }.items():
            value, sample_at, ok = await self._query_guardrails_scalar(promql_template.format(range=time_range), key)
            prometheus_ok = prometheus_ok and ok
            if ok:
                guardrails[key] = value
                if sample_at and (newest_sample_at is None or sample_at > newest_sample_at):
                    newest_sample_at = sample_at

        rate_limit_values: list[int] = []
        for promql_template in _RATE_LIMIT_BLOCK_QUERIES:
            value, sample_at, ok = await self._query_guardrails_scalar(
                promql_template.format(range=time_range), "rate_limit_blocks"
            )
            prometheus_ok = prometheus_ok and ok
            if not ok:
                continue
            if value is not None:
                rate_limit_values.append(value)
            if sample_at and (newest_sample_at is None or sample_at > newest_sample_at):
                newest_sample_at = sample_at

        if rate_limit_values:
            guardrails["rate_limit_blocks"] = sum(rate_limit_values)

        by_guardrail_evaluations: dict[str, tuple[int, datetime]] = {}
        vector, ok = await self._query_guardrails_vector(
            _GUARDRAILS_BY_GUARDRAIL_EVAL_QUERY.format(range=time_range), "evaluations_by_guardrail"
        )
        prometheus_ok = prometheus_ok and ok
        if ok:
            for metric, value, sample_at in vector:
                guardrail = metric.get("guardrail")
                if guardrail in _GUARDRAILS_FULL_GUARDRAILS:
                    by_guardrail_evaluations[guardrail] = (value, sample_at)

        by_guardrail_decisions: dict[str, dict[str, int]] = {}
        by_guardrail_decision_sample_at: dict[str, datetime] = {}
        vector, ok = await self._query_guardrails_vector(
            _GUARDRAILS_BY_GUARDRAIL_DECISION_QUERY.format(range=time_range), "decisions_by_guardrail"
        )
        prometheus_ok = prometheus_ok and ok
        if ok:
            for metric, value, sample_at in vector:
                guardrail = metric.get("guardrail")
                decision = metric.get("decision")
                if guardrail in _GUARDRAILS_FULL_GUARDRAILS and decision in _GUARDRAILS_FULL_DECISIONS:
                    by_guardrail_decisions.setdefault(guardrail, {})[decision] = value
                    current = by_guardrail_decision_sample_at.get(guardrail)
                    if current is None or sample_at > current:
                        by_guardrail_decision_sample_at[guardrail] = sample_at

        scrape_sample_at, ok = await self._query_guardrails_timestamp(_GUARDRAILS_SCRAPE_SAMPLE_QUERY, "scrape_sample")
        prometheus_ok = prometheus_ok and ok

        by_guardrail_scrape_sample_at: dict[str, datetime] = {}
        vector, ok = await self._query_guardrails_vector(
            _GUARDRAILS_BY_GUARDRAIL_SCRAPE_QUERY, "scrape_sample_by_guardrail"
        )
        prometheus_ok = prometheus_ok and ok
        if ok:
            for metric, value, _ in vector:
                guardrail = metric.get("guardrail")
                if guardrail in _GUARDRAILS_FULL_GUARDRAILS:
                    by_guardrail_scrape_sample_at[guardrail] = datetime.fromtimestamp(float(value), UTC)

        threshold_seconds = self._freshness_threshold_seconds(time_range)
        scrape_age_seconds = self._metrics_age_seconds(scrape_sample_at)
        producer_present = scrape_sample_at is not None
        state = self._derive_guardrails_state(
            source_healthy=prometheus_ok,
            producer_present=producer_present,
            evaluations_count=guardrails["evaluations_count"],
            trips_count=guardrails["trips_count"],
            scrape_age_seconds=scrape_age_seconds,
            freshness_threshold_seconds=threshold_seconds,
        )
        source_healthy = self._source_is_healthy(prometheus_ok, producer_present, scrape_age_seconds, threshold_seconds)
        stale_reason = self._guardrails_stale_reason(
            state, prometheus_ok=prometheus_ok, producer_present=producer_present
        )

        if state == "metrics_unavailable":
            for key in ("evaluations_count", "decisions_count", "trips_count", "error_count"):
                guardrails[key] = None

        guardrails["state"] = state
        guardrails["last_evaluation_delta_at"] = (
            sample_ats["evaluations_count"].isoformat() if guardrails["evaluations_count"] else None
        )
        guardrails["last_decision_delta_at"] = (
            sample_ats["decisions_count"].isoformat() if guardrails["decisions_count"] else None
        )
        guardrails["scrape_sample_at"] = scrape_sample_at.isoformat() if scrape_sample_at else None
        guardrails["stale_reason"] = stale_reason
        guardrails["source_healthy"] = source_healthy
        sample_alias_at = scrape_sample_at or newest_sample_at
        guardrails["last_sample_at"] = sample_alias_at.isoformat() if sample_alias_at else None
        guardrails["metrics_age_seconds"] = self._metrics_age_seconds(sample_alias_at)

        by_guardrail: dict[str, dict[str, Any]] = {}
        for guardrail in _GUARDRAILS_FULL_GUARDRAILS:
            guardrail_scrape_sample_at = by_guardrail_scrape_sample_at.get(guardrail)
            guardrail_producer_present = guardrail_scrape_sample_at is not None
            guardrail_scrape_age = self._metrics_age_seconds(guardrail_scrape_sample_at)
            guardrail_evaluations = by_guardrail_evaluations.get(guardrail)
            derived_counts = self._derive_guardrails_counts(by_guardrail_decisions.get(guardrail, {}))
            guardrail_counts: dict[str, int | None] = {
                "decisions_count": derived_counts["decisions_count"],
                "trips_count": derived_counts["trips_count"],
                "error_count": derived_counts["error_count"],
            }
            guardrail_eval_count = guardrail_evaluations[0] if guardrail_evaluations else None
            guardrail_state = self._derive_guardrails_state(
                source_healthy=prometheus_ok,
                producer_present=guardrail_producer_present,
                evaluations_count=guardrail_eval_count,
                trips_count=guardrail_counts["trips_count"],
                scrape_age_seconds=guardrail_scrape_age,
                freshness_threshold_seconds=threshold_seconds,
            )
            guardrail_source_healthy = self._source_is_healthy(
                prometheus_ok,
                guardrail_producer_present,
                guardrail_scrape_age,
                threshold_seconds,
            )
            guardrail_stale_reason = self._guardrails_stale_reason(
                guardrail_state,
                prometheus_ok=prometheus_ok,
                producer_present=guardrail_producer_present,
            )
            if guardrail_state == "metrics_unavailable":
                guardrail_eval_count = None
                guardrail_counts = {"decisions_count": None, "trips_count": None, "error_count": None}
            by_guardrail[guardrail] = {
                "state": guardrail_state,
                "evaluations_count": guardrail_eval_count,
                "decisions_count": guardrail_counts["decisions_count"],
                "trips_count": guardrail_counts["trips_count"],
                "error_count": guardrail_counts["error_count"],
                "last_evaluation_delta_at": (
                    guardrail_evaluations[1].isoformat() if guardrail_evaluations and guardrail_eval_count else None
                ),
                "last_decision_delta_at": (
                    by_guardrail_decision_sample_at[guardrail].isoformat()
                    if guardrail_counts["decisions_count"] and guardrail in by_guardrail_decision_sample_at
                    else None
                ),
                "scrape_sample_at": guardrail_scrape_sample_at.isoformat() if guardrail_scrape_sample_at else None,
                "source_healthy": guardrail_source_healthy,
                "stale_reason": guardrail_stale_reason,
            }

        guardrails["by_guardrail"] = by_guardrail

        # Compatibility aliases for the current UI. PR-3B2 consumes the canonical names.
        guardrails["content_filters"] = guardrails["content_filter_blocks"]
        guardrails["prompt_guard_flags"] = guardrails["prompt_guard_blocks"]
        guardrails["rate_limit_enforcements"] = guardrails["rate_limit_blocks"]

        # Breakdown by tool (injection)
        try:
            result = await prometheus_client.query(
                f"sum by (tool) (increase(stoa_guardrails_injection_blocked_total[{time_range}]))"
            )
            if result and result.get("result"):
                for item in result["result"]:
                    tool = item.get("metric", {}).get("tool", "unknown")
                    val = int(float(item["value"][1]))
                    guardrails["by_tool"][tool] = guardrails["by_tool"].get(tool, 0) + val
        except Exception:
            logger.debug("Failed to fetch injection by_tool breakdown")

        # Breakdown by category (content filter)
        try:
            result = await prometheus_client.query(
                f"sum by (category) (increase(stoa_guardrails_content_filtered_total[{time_range}]))"
            )
            if result and result.get("result"):
                for item in result["result"]:
                    cat = item.get("metric", {}).get("category", "unknown")
                    val = int(float(item["value"][1]))
                    guardrails["by_category"][cat] = val
        except Exception:
            logger.debug("Failed to fetch content_filter by_category breakdown")

        # Breakdown by tool (PII — via recent rate to identify which tools leak PII)
        try:
            result = await prometheus_client.query(
                f"sum by (tool) (increase(stoa_guardrails_pii_detected_total[{time_range}]))"
            )
            if result and result.get("result"):
                for item in result["result"]:
                    tool = item.get("metric", {}).get("tool", "unknown")
                    val = int(float(item["value"][1]))
                    if tool != "unknown":
                        guardrails["by_tool"][tool] = guardrails["by_tool"].get(tool, 0) + val
        except Exception:
            pass

        return guardrails

    async def get_aggregated_metrics(self, tenant_id: str | None = None, time_range: TimeRange = "1h") -> dict:
        """Combined health + sync summaries + guardrails + overall_status."""
        health = await self.get_health_summary(tenant_id=tenant_id)
        sync = await self.get_sync_status_summary(tenant_id=tenant_id)
        guardrails = await self._fetch_guardrails_metrics(time_range=time_range)

        # Determine overall status
        total_gateways = health.get("total_gateways", 0)
        online = health.get("online", 0)
        error_count = sync.get("error", 0)
        drifted_count = sync.get("drifted", 0)

        if total_gateways == 0:
            overall = "unknown"
        elif online == total_gateways and error_count == 0 and drifted_count == 0:
            overall = "healthy"
        elif online == 0:
            overall = "critical"
        else:
            overall = "degraded"

        return {
            "health": health,
            "sync": sync,
            "guardrails": guardrails,
            "overall_status": overall,
        }

    def get_adapter_operation_metrics(self) -> dict:
        """Read adapter operation metrics from in-process Prometheus registry.

        Returns per-gateway-type: total_ops, success_rate, avg_latency_ms, operations breakdown.
        """
        metrics_by_gateway: dict[str, dict] = {}

        # Collect operation counts from Counter
        for metric_family in ADAPTER_OPERATIONS_TOTAL.collect():
            for sample in metric_family.samples:
                if sample.name.endswith("_created"):
                    continue
                gw = sample.labels.get("gateway_type", "unknown")
                op = sample.labels.get("operation", "unknown")
                status = sample.labels.get("status", "unknown")

                if gw not in metrics_by_gateway:
                    metrics_by_gateway[gw] = {
                        "total_ops": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "operations": {},
                    }

                entry = metrics_by_gateway[gw]
                if op not in entry["operations"]:
                    entry["operations"][op] = {"total": 0, "success": 0, "error": 0, "timeout": 0}

                entry["operations"][op][status] = int(sample.value)
                entry["operations"][op]["total"] += int(sample.value)
                entry["total_ops"] += int(sample.value)
                if status == "success":
                    entry["success_count"] += int(sample.value)
                elif status in ("error", "timeout"):
                    entry["error_count"] += int(sample.value)

        # Collect latency (sum/count from Histogram for avg calculation)
        for metric_family in ADAPTER_OPERATION_DURATION.collect():
            for sample in metric_family.samples:
                gw = sample.labels.get("gateway_type", "unknown")
                if gw not in metrics_by_gateway:
                    continue
                if sample.name.endswith("_sum"):
                    metrics_by_gateway[gw].setdefault("_duration_sum", 0.0)
                    metrics_by_gateway[gw]["_duration_sum"] += sample.value
                elif sample.name.endswith("_count"):
                    metrics_by_gateway[gw].setdefault("_duration_count", 0)
                    metrics_by_gateway[gw]["_duration_count"] += int(sample.value)

        # Compute derived fields
        for data in metrics_by_gateway.values():
            total = data["total_ops"]
            data["success_rate"] = round((data["success_count"] / total) * 100, 1) if total > 0 else 0.0
            count = data.pop("_duration_count", 0)
            total_sum = data.pop("_duration_sum", 0.0)
            data["avg_latency_ms"] = round((total_sum / count) * 1000, 2) if count > 0 else 0.0

        return {"gateway_types": metrics_by_gateway}

    async def get_health_history(self, gateway_id: UUID, tenant_id: str | None = None) -> dict | None:
        """Get health check details for a specific gateway.

        Returns current health status, last check time, and health_details JSONB
        which contains check_method, consecutive_failures, last_error, etc.

        Args:
            gateway_id: Gateway instance ID.
            tenant_id: When provided, verifies gateway belongs to this tenant.
        """
        query = select(GatewayInstance).where(
            GatewayInstance.id == gateway_id,
            GatewayInstance.deleted_at.is_(None),
        )
        if tenant_id:
            query = query.where(GatewayInstance.tenant_id == tenant_id)
        result = await self.db.execute(query)
        gateway = result.scalar_one_or_none()
        if not gateway:
            return None

        return {
            "gateway_id": str(gateway.id),
            "name": gateway.name,
            "gateway_type": gateway.gateway_type.value if gateway.gateway_type else "",
            "status": gateway.status.value if gateway.status else "offline",
            "last_health_check": gateway.last_health_check.isoformat() if gateway.last_health_check else None,
            "health_details": gateway.health_details or {},
            "tenant_id": gateway.tenant_id,
        }
