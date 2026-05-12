"""CAB-2218 guardrails metrics reader state precedence tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.services.gateway_metrics_service import GatewayMetricsService


def _vector(value: int, *, sample_at: datetime | None = None, metric: dict[str, str] | None = None) -> dict:
    ts = (sample_at or datetime.now(UTC)).timestamp()
    return {"result": [{"metric": metric or {}, "value": [ts, str(value)]}]}


@pytest.mark.parametrize(
    ("source_healthy", "producer_present", "evaluations", "trips", "age", "expected"),
    [
        (False, True, 7, 2, 30, "metrics_unavailable"),
        (True, False, 0, 0, None, "metrics_unavailable"),
        (True, True, 0, 0, 301, "stale_data"),
        (True, True, 0, 0, 30, "no_evaluations"),
        (True, True, 3, 0, 30, "evaluations_zero_trips"),
        (True, True, 3, 1, 30, "trips_observed"),
    ],
)
def test_state_precedence_order_is_locked(
    source_healthy: bool,
    producer_present: bool,
    evaluations: int,
    trips: int,
    age: int | None,
    expected: str,
) -> None:
    assert (
        GatewayMetricsService._derive_guardrails_state(
            source_healthy=source_healthy,
            producer_present=producer_present,
            evaluations_count=evaluations,
            trips_count=trips,
            scrape_age_seconds=age,
            freshness_threshold_seconds=300,
        )
        == expected
    )


def test_capped_freshness_threshold_never_exceeds_one_hour() -> None:
    assert GatewayMetricsService._freshness_threshold_seconds("1h", scrape_interval_seconds=30) == 300
    assert GatewayMetricsService._freshness_threshold_seconds("24h", scrape_interval_seconds=30) == 600
    assert GatewayMetricsService._freshness_threshold_seconds("7d", scrape_interval_seconds=30) == 1800
    assert GatewayMetricsService._freshness_threshold_seconds("7d", scrape_interval_seconds=7200) == 3600


def test_trips_and_errors_are_derived_from_bounded_decision_enum() -> None:
    counts = GatewayMetricsService._derive_guardrails_counts({"allow": 7, "redact": 2, "block": 3, "error": 5})

    assert counts == {"decisions_count": 17, "trips_count": 5, "error_count": 5}


@pytest.mark.asyncio
async def test_prometheus_failure_uses_bounded_stale_reason_without_raw_error_leak() -> None:
    svc = GatewayMetricsService(AsyncMock())

    with patch("src.services.gateway_metrics_service.prometheus_client") as mock_prometheus:
        mock_prometheus.is_enabled = True
        mock_prometheus.query = AsyncMock(
            side_effect=RuntimeError("query failed against http://prometheus.monitoring.svc:9090/api/v1/query")
        )

        result = await svc._fetch_guardrails_metrics(time_range="1h")

    assert result["state"] == "metrics_unavailable"
    assert result["evaluations_count"] is None
    assert result["decisions_count"] is None
    assert result["trips_count"] is None
    assert result["error_count"] is None
    assert result["stale_reason"] == "prom_unreachable"
    assert result["stale_reason"] in {"prom_unreachable", "scrape_gap", "producer_absent", "stale_unknown"}
    for forbidden in ("http://", "prometheus", "9090", "query="):
        assert forbidden not in str(result["stale_reason"]).lower()


@pytest.mark.asyncio
async def test_fetch_reads_new_and_legacy_counters_with_per_guardrail_independence() -> None:
    svc = GatewayMetricsService(AsyncMock())
    now = datetime.now(UTC)
    fresh = now - timedelta(seconds=30)
    stale = now - timedelta(hours=2)
    observed: list[str] = []

    async def query(promql: str) -> dict:
        observed.append(promql)
        if "max by (guardrail) (timestamp(stoa_guardrails_evaluations_total))" in promql:
            return {
                "result": [
                    {"metric": {"guardrail": "pii"}, "value": [now.timestamp(), str(stale.timestamp())]},
                    {"metric": {"guardrail": "injection"}, "value": [now.timestamp(), str(fresh.timestamp())]},
                ]
            }
        if "max(timestamp(stoa_guardrails_evaluations_total))" in promql:
            return _vector(int(fresh.timestamp()), sample_at=now)
        if "sum by (guardrail, decision)" in promql:
            return {
                "result": [
                    {"metric": {"guardrail": "pii", "decision": "redact"}, "value": [now.timestamp(), "0"]},
                    {"metric": {"guardrail": "pii", "decision": "error"}, "value": [now.timestamp(), "4"]},
                    {"metric": {"guardrail": "injection", "decision": "allow"}, "value": [now.timestamp(), "1"]},
                ]
            }
        if "sum by (guardrail)" in promql and "stoa_guardrails_evaluations_total" in promql:
            return {
                "result": [
                    {"metric": {"guardrail": "pii"}, "value": [now.timestamp(), "1"]},
                    {"metric": {"guardrail": "injection"}, "value": [now.timestamp(), "1"]},
                ]
            }
        if "stoa_guardrails_evaluations_total" in promql:
            return _vector(2, sample_at=fresh)
        if 'decision=~"redact|block"' in promql:
            return _vector(0, sample_at=fresh)
        if 'decision="error"' in promql:
            return _vector(4, sample_at=fresh)
        if "stoa_guardrails_decisions_total" in promql:
            return _vector(5, sample_at=fresh)
        if "stoa_guardrails_pii_detected_total" in promql:
            return _vector(0, sample_at=fresh)
        if "stoa_guardrails_injection_blocked_total" in promql:
            return _vector(0, sample_at=fresh)
        if "stoa_guardrails_content_filtered_total" in promql:
            return _vector(0, sample_at=fresh)
        if "stoa_prompt_guard_detected_total" in promql or "rate_limit" in promql:
            return _vector(0, sample_at=fresh)
        return {"result": []}

    with patch("src.services.gateway_metrics_service.prometheus_client") as mock_prometheus:
        mock_prometheus.is_enabled = True
        mock_prometheus.query = AsyncMock(side_effect=query)

        result = await svc._fetch_guardrails_metrics(time_range="7d")

    joined_queries = "\n".join(observed)
    assert "stoa_guardrails_evaluations_total" in joined_queries
    assert "stoa_guardrails_decisions_total" in joined_queries
    assert "stoa_guardrails_pii_detected_total" in joined_queries
    assert result["state"] == "evaluations_zero_trips"
    assert result["evaluations_count"] == 2
    assert result["decisions_count"] == 5
    assert result["trips_count"] == 0
    assert result["error_count"] == 4
    assert result["source_healthy"] is True
    assert result["scrape_sample_at"] is not None
    assert result["by_guardrail"]["pii"]["state"] == "stale_data"
    assert result["by_guardrail"]["pii"]["stale_reason"] == "scrape_gap"
    assert result["by_guardrail"]["injection"]["state"] == "evaluations_zero_trips"
    assert result["state"] != "stale_data"
