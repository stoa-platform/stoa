"""Regression guard for PR-3B1 guardrails runtime truth.

The backend must preserve unknown ``null`` separately from a healthy numeric
``0`` so the frontend can distinguish no sample from enabled+zero events.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.services.gateway_metrics_service import GatewayMetricsService


def _result(value: int) -> dict:
    return {"result": [{"value": [1_777_777_777.0, str(value)]}]}


def _empty_result() -> dict:
    return {"result": []}


@pytest.mark.asyncio
async def test_guardrails_runtime_truth_distinguishes_healthy_zero_from_unknown_null():
    svc = GatewayMetricsService(AsyncMock())
    pii_query = "sum(increase(stoa_guardrails_pii_detected_total[1h]))"

    async def healthy_zero_query(promql: str) -> dict:
        if promql == pii_query:
            return _result(0)
        return _empty_result()

    async def unknown_query(promql: str) -> dict:
        return _empty_result()

    with patch("src.services.gateway_metrics_service.prometheus_client") as mock_prometheus:
        mock_prometheus.is_enabled = True
        mock_prometheus.query = AsyncMock(side_effect=healthy_zero_query)
        zero = await svc._fetch_guardrails_metrics(time_range="1h")

    with patch("src.services.gateway_metrics_service.prometheus_client") as mock_prometheus:
        mock_prometheus.is_enabled = True
        mock_prometheus.query = AsyncMock(side_effect=unknown_query)
        unknown = await svc._fetch_guardrails_metrics(time_range="1h")

    assert zero["source_healthy"] is True
    assert unknown["source_healthy"] is True
    assert zero["pii_detections"] == 0
    assert unknown["pii_detections"] is None
    assert zero["last_sample_at"] is not None
    assert unknown["last_sample_at"] is None
    assert all("opa" not in key for key in zero)
