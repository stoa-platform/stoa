"""Regression tests for CAB-2029 — Authenticated Prometheus metrics proxy.

Validates:
- Unauthenticated requests → 401/403
- tenant-admin has tenant_id injected into PromQL
- cpi-admin queries run unmodified
- PromQL tenant_id injection logic
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.routers.metrics_proxy import _inject_tenant_filter

PROMETHEUS_PATH = "src.routers.metrics_proxy._prometheus"


# ============ PromQL tenant injection unit tests ============


class TestInjectTenantFilter:
    """Unit tests for _inject_tenant_filter."""

    def test_simple_metric_with_labels(self):
        result = _inject_tenant_filter('stoa_calls_total{status="200"}', "acme")
        assert 'tenant_id="acme"' in result
        assert 'status="200"' in result

    def test_metric_with_empty_braces(self):
        result = _inject_tenant_filter("stoa_calls_total{}", "acme")
        assert result == 'stoa_calls_total{tenant_id="acme"}'

    def test_metric_with_multiple_labels(self):
        result = _inject_tenant_filter('sum(stoa_calls_total{method="GET", status="200"})', "acme")
        assert 'tenant_id="acme"' in result
        assert 'method="GET"' in result

    def test_bare_metric_name(self):
        """Bare metric without braces gets tenant filter added."""
        result = _inject_tenant_filter("up", "acme")
        assert 'tenant_id="acme"' in result

    def test_preserves_existing_tenant_label(self):
        """If tenant_id already present, it gets added again (double filter is safe)."""
        result = _inject_tenant_filter('metric{tenant_id="other"}', "acme")
        assert 'tenant_id="acme"' in result


# ============ Endpoint auth tests ============


class TestMetricsProxyNoAuth:
    """Requests without JWT must be rejected."""

    def test_query_no_auth(self, client):
        resp = client.get("/v1/metrics/query?query=up")
        assert resp.status_code in (401, 403)

    def test_query_range_no_auth(self, client):
        resp = client.get("/v1/metrics/query_range?query=up&start=1&end=2&step=60s")
        assert resp.status_code in (401, 403)


class TestMetricsProxyTenantIsolation:
    """tenant-admin has tenant_id injected."""

    @patch(PROMETHEUS_PATH)
    def test_query_injects_tenant(self, mock_prom, app_with_tenant_admin):
        mock_prom.query = AsyncMock(return_value={
            "resultType": "vector", "result": [],
        })

        client = TestClient(app_with_tenant_admin)
        resp = client.get("/v1/metrics/query?query=stoa_calls_total")
        assert resp.status_code == 200

        # Verify tenant_id was injected into the PromQL
        call_args = mock_prom.query.call_args[0][0]
        assert 'tenant_id="acme"' in call_args

    @patch(PROMETHEUS_PATH)
    def test_query_range_injects_tenant(self, mock_prom, app_with_tenant_admin):
        mock_prom.query_range = AsyncMock(return_value={
            "resultType": "matrix", "result": [],
        })

        client = TestClient(app_with_tenant_admin)
        resp = client.get(
            "/v1/metrics/query_range?query=stoa_calls_total&start=1000&end=2000&step=60s"
        )
        assert resp.status_code == 200

        call_args = mock_prom.query_range.call_args[0][0]
        assert 'tenant_id="acme"' in call_args


class TestMetricsProxyCpiAdmin:
    """cpi-admin queries run unmodified."""

    @patch(PROMETHEUS_PATH)
    def test_query_no_tenant_injection(self, mock_prom, app_with_cpi_admin):
        mock_prom.query = AsyncMock(return_value={
            "resultType": "vector", "result": [],
        })

        client = TestClient(app_with_cpi_admin)
        resp = client.get("/v1/metrics/query?query=stoa_calls_total")
        assert resp.status_code == 200

        # cpi-admin: query should pass through unmodified
        call_args = mock_prom.query.call_args[0][0]
        assert call_args == "stoa_calls_total"
        assert "tenant_id" not in call_args

    @patch(PROMETHEUS_PATH)
    def test_prometheus_unavailable_returns_empty(self, mock_prom, app_with_cpi_admin):
        mock_prom.query = AsyncMock(return_value=None)

        client = TestClient(app_with_cpi_admin)
        resp = client.get("/v1/metrics/query?query=up")
        assert resp.status_code == 200
        assert resp.json()["data"]["result"] == []
