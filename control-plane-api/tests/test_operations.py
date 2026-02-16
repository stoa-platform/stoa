"""Tests for operations router — GET /v1/operations/metrics"""

from unittest.mock import AsyncMock, MagicMock, patch

from src.routers.operations import _extract_scalar

PROM_PATH = "src.routers.operations.prometheus_client"


def _prom_vector(value):
    """Build a Prometheus vector result dict."""
    return {"resultType": "vector", "result": [{"value": [0, str(value)]}]}


class TestGetOperationsMetrics:
    def test_prometheus_enabled_returns_metrics(self, client_as_cpi_admin):
        mock_prom = MagicMock()
        mock_prom.is_enabled = True
        mock_prom.query = AsyncMock(
            side_effect=[
                _prom_vector(0.02),  # error_rate (x 100 = 2.0%)
                _prom_vector(0.150),  # p95 (x 1000 = 150.0ms)
                _prom_vector(42.5),  # rps
                _prom_vector(0.9995),  # uptime (x 100 = 99.95%)
                _prom_vector(3),  # active_alerts
            ]
        )

        with patch(PROM_PATH, mock_prom):
            resp = client_as_cpi_admin.get("/v1/operations/metrics")

        assert resp.status_code == 200
        body = resp.json()
        assert body["error_rate"] == 2.0
        assert body["p95_latency_ms"] == 150.0
        assert body["requests_per_minute"] == 42.5
        assert body["uptime"] == 99.95
        assert body["active_alerts"] == 3

    def test_prometheus_disabled_returns_zeros(self, client_as_cpi_admin):
        mock_prom = MagicMock()
        mock_prom.is_enabled = False

        with patch(PROM_PATH, mock_prom):
            resp = client_as_cpi_admin.get("/v1/operations/metrics")

        assert resp.status_code == 200
        body = resp.json()
        assert body["error_rate"] == 0.0
        assert body["p95_latency_ms"] == 0.0
        assert body["requests_per_minute"] == 0.0
        assert body["active_alerts"] == 0
        assert body["uptime"] == 100.0

    def test_prometheus_query_error_returns_defaults(self, client_as_cpi_admin):
        mock_prom = MagicMock()
        mock_prom.is_enabled = True
        mock_prom.query = AsyncMock(side_effect=RuntimeError("Prometheus down"))

        with patch(PROM_PATH, mock_prom):
            resp = client_as_cpi_admin.get("/v1/operations/metrics")

        assert resp.status_code == 200
        body = resp.json()
        assert body["error_rate"] == 0.0
        assert body["uptime"] == 100.0

    def test_viewer_forbidden(self, client_as_no_tenant_user):
        """Viewer role is not in allowed_roles for operations metrics."""
        mock_prom = MagicMock()
        mock_prom.is_enabled = False

        with patch(PROM_PATH, mock_prom):
            resp = client_as_no_tenant_user.get("/v1/operations/metrics")

        assert resp.status_code == 403


class TestExtractScalar:
    def test_normal_value(self):
        result = _prom_vector(42.5)
        assert _extract_scalar(result) == 42.5

    def test_nan_returns_default(self):
        result = {"resultType": "vector", "result": [{"value": [0, "NaN"]}]}
        assert _extract_scalar(result, default=0.0) == 0.0

    def test_none_returns_default(self):
        assert _extract_scalar(None, default=99.0) == 99.0

    def test_empty_result_returns_default(self):
        result = {"resultType": "vector", "result": []}
        assert _extract_scalar(result, default=5.0) == 5.0

    def test_non_vector_type_returns_default(self):
        result = {"resultType": "matrix", "result": []}
        assert _extract_scalar(result) == 0.0

    def test_inf_returns_default(self):
        result = {"resultType": "vector", "result": [{"value": [0, "Inf"]}]}
        assert _extract_scalar(result, default=0.0) == 0.0
