"""Tests for Operations router — GET /v1/operations/metrics (CAB-Observability)."""

from unittest.mock import AsyncMock, patch

from src.routers.operations import _extract_scalar

# ── Helper: prometheus result fixtures ──


def _make_vector_result(value: str) -> dict:
    """Build a fake Prometheus vector result with a single value."""
    return {
        "resultType": "vector",
        "result": [{"metric": {}, "value": [1700000000, value]}],
    }


# ── Unit tests for _extract_scalar ──


class TestExtractScalar:
    def test_extracts_float_from_vector(self):
        result = _make_vector_result("0.05")
        assert _extract_scalar(result) == 0.05

    def test_empty_result_returns_default(self):
        assert _extract_scalar(None) == 0.0
        assert _extract_scalar(None, default=1.0) == 1.0

    def test_empty_result_dict_returns_default(self):
        assert _extract_scalar({}) == 0.0

    def test_empty_vector_list_returns_default(self):
        result = {"resultType": "vector", "result": []}
        assert _extract_scalar(result, default=99.0) == 99.0

    def test_non_vector_result_type_returns_default(self):
        result = {"resultType": "scalar", "result": [1700000000, "0.5"]}
        assert _extract_scalar(result, default=7.0) == 7.0

    def test_nan_value_returns_default(self):
        result = _make_vector_result("NaN")
        # float("NaN") != float("NaN") — should return default
        assert _extract_scalar(result, default=3.14) == 3.14

    def test_inf_value_returns_default(self):
        result = _make_vector_result("Inf")
        assert _extract_scalar(result, default=5.0) == 5.0

    def test_zero_value_extracted(self):
        result = _make_vector_result("0")
        assert _extract_scalar(result) == 0.0

    def test_large_value_extracted(self):
        result = _make_vector_result("9999.99")
        assert _extract_scalar(result) == 9999.99

    def test_negative_value_extracted(self):
        result = _make_vector_result("-0.5")
        assert _extract_scalar(result) == -0.5


# ── Integration tests via TestClient ──


class TestGetOperationsMetrics:
    def test_metrics_prometheus_disabled_returns_defaults(self, client_as_cpi_admin):
        """When Prometheus is disabled, all metrics should return safe defaults."""
        with patch("src.routers.operations.prometheus_client") as mock_client:
            mock_client.is_enabled = False

            response = client_as_cpi_admin.get("/v1/operations/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["error_rate"] == 0.0
        assert data["p95_latency_ms"] == 0.0
        assert data["requests_per_minute"] == 0.0
        assert data["active_alerts"] == 0
        assert data["uptime"] == 100.0

    def test_metrics_prometheus_enabled_returns_computed_values(self, client_as_cpi_admin):
        """When Prometheus is enabled, endpoint should query and return real metrics."""
        error_rate_result = _make_vector_result("0.02")  # 0.02 → 2.0%
        p95_result = _make_vector_result("0.250")  # 0.25s → 250.0ms
        rps_result = _make_vector_result("120.0")  # 120.0 rpm
        uptime_result = _make_vector_result("0.9995")  # 99.95%
        alerts_result = _make_vector_result("3")  # 3 alerts

        with patch("src.routers.operations.prometheus_client") as mock_client:
            mock_client.is_enabled = True
            mock_client.query = AsyncMock(
                side_effect=[
                    error_rate_result,
                    p95_result,
                    rps_result,
                    uptime_result,
                    alerts_result,
                ]
            )

            response = client_as_cpi_admin.get("/v1/operations/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["error_rate"] == 2.0  # 0.02 * 100
        assert data["p95_latency_ms"] == 250.0  # 0.25 * 1000
        assert data["requests_per_minute"] == 120.0
        assert data["active_alerts"] == 3
        assert data["uptime"] == 99.95  # 0.9995 * 100 = 99.95

    def test_metrics_prometheus_exception_returns_defaults(self, client_as_cpi_admin):
        """When Prometheus raises an exception, endpoint returns safe defaults."""
        with patch("src.routers.operations.prometheus_client") as mock_client:
            mock_client.is_enabled = True
            mock_client.query = AsyncMock(side_effect=Exception("Prometheus unreachable"))

            response = client_as_cpi_admin.get("/v1/operations/metrics")

        assert response.status_code == 200
        data = response.json()
        # Graceful degradation: all zero / 100% uptime
        assert data["error_rate"] == 0.0
        assert data["active_alerts"] == 0
        assert data["uptime"] == 100.0

    def test_metrics_requires_auth(self, client_as_no_tenant_user):
        """Viewer role should be forbidden (403) from operations metrics."""
        response = client_as_no_tenant_user.get("/v1/operations/metrics")
        # viewer role is not in ["cpi-admin", "devops", "admin"]
        assert response.status_code == 403

    def test_metrics_response_schema(self, client_as_cpi_admin):
        """Response always contains the full OperationsMetrics schema."""
        with patch("src.routers.operations.prometheus_client") as mock_client:
            mock_client.is_enabled = False

            response = client_as_cpi_admin.get("/v1/operations/metrics")

        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {
            "error_rate",
            "p95_latency_ms",
            "requests_per_minute",
            "active_alerts",
            "uptime",
        }

    def test_metrics_zero_alerts_when_no_firing(self, client_as_cpi_admin):
        """active_alerts is 0 when alertmanager returns vector(0)."""
        zero_result = _make_vector_result("0")

        with patch("src.routers.operations.prometheus_client") as mock_client:
            mock_client.is_enabled = True
            mock_client.query = AsyncMock(return_value=zero_result)

            response = client_as_cpi_admin.get("/v1/operations/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["active_alerts"] == 0
