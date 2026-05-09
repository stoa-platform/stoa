"""Tests for Gateway Observability Router — CAB-1378

Endpoints:
- GET /v1/admin/gateways/metrics
- GET /v1/admin/gateways/health-summary
- GET /v1/admin/gateways/{gateway_id}/metrics

RBAC: require_role(["cpi-admin", "tenant-admin"])
"""

from typing import get_args
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import Depends
from fastapi.testclient import TestClient
import pytest


_GUARDRAILS_ENV = {
    "STOA_GUARDRAILS_PII_ENABLED": "true",
    "STOA_GUARDRAILS_INJECTION_ENABLED": "false",
    "STOA_PROMPT_GUARD_ENABLED": "true",
    "STOA_GUARDRAILS_CONTENT_FILTER_ENABLED": "false",
    "STOA_RATE_LIMIT_DEFAULT": "1000",
    "STOA_POLICY_ENABLED": "true",
}


class TestGatewayObservabilityRouter:
    """Test suite for Gateway Observability endpoints."""

    # ============== GET /guardrails/config ==============

    def test_guardrails_config_endpoint_returns_documented_shape(self, app_with_cpi_admin, mock_db_session):
        """GET /guardrails/config returns the PR-3A documented shape."""
        with patch.dict("os.environ", _GUARDRAILS_ENV, clear=False):
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/guardrails/config")

        assert response.status_code == 200
        data = response.json()
        assert set(data) == {
            "pii_enabled",
            "injection_detection_enabled",
            "prompt_guard_enabled",
            "content_filter_enabled",
            "rate_limit_enabled",
            "opa_policy_enabled",
            "source",
            "updated_at",
        }
        assert data["source"] == "env"
        assert isinstance(data["updated_at"], str)

    def test_guardrails_config_booleans_never_null(self, app_with_cpi_admin, mock_db_session):
        """All six guardrails config fields are non-null booleans."""
        with patch.dict("os.environ", _GUARDRAILS_ENV, clear=False):
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/guardrails/config")

        assert response.status_code == 200
        data = response.json()
        for field in (
            "pii_enabled",
            "injection_detection_enabled",
            "prompt_guard_enabled",
            "content_filter_enabled",
            "rate_limit_enabled",
            "opa_policy_enabled",
        ):
            assert isinstance(data[field], bool)

    def test_guardrails_config_source_enum(self, app_with_cpi_admin, mock_db_session):
        """The response model source enum is exactly the PR-3A contract set."""
        from src.routers.gateway_observability import GuardrailsConfigResponse

        source_values = set(get_args(GuardrailsConfigResponse.model_fields["source"].annotation))
        assert source_values == {"env", "runtime", "config-service"}

        with patch.dict("os.environ", _GUARDRAILS_ENV, clear=False):
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/guardrails/config")

        assert response.status_code == 200
        assert response.json()["source"] in source_values

    def test_guardrails_config_missing_env_fails_closed(self, app_with_cpi_admin, mock_db_session):
        """Missing effective env state fails instead of returning guessed booleans."""
        env = dict(_GUARDRAILS_ENV)
        env.pop("STOA_GUARDRAILS_PII_ENABLED")

        with patch.dict("os.environ", env, clear=True):
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/guardrails/config")

        assert response.status_code == 503
        assert "STOA_GUARDRAILS_PII_ENABLED" in response.json()["detail"]

    def test_guardrails_config_invalid_env_fails_closed(self, app_with_cpi_admin, mock_db_session):
        """Invalid effective env state fails instead of returning guessed booleans."""
        env = dict(_GUARDRAILS_ENV, STOA_GUARDRAILS_PII_ENABLED="maybe")

        with patch.dict("os.environ", env, clear=True):
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/guardrails/config")

        assert response.status_code == 503
        assert "invalid" in response.json()["detail"]

    def test_guardrails_config_explicit_rate_limit_bool(self, app_with_cpi_admin, mock_db_session):
        """Explicit STOA_RATE_LIMIT_ENABLED is honored over numeric default."""
        env = dict(_GUARDRAILS_ENV, STOA_RATE_LIMIT_ENABLED="false")

        with patch.dict("os.environ", env, clear=True):
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/guardrails/config")

        assert response.status_code == 200
        assert response.json()["rate_limit_enabled"] is False

    # ============== GET /metrics ==============

    def test_get_aggregated_metrics_success(self, app_with_cpi_admin, mock_db_session):
        """GET /metrics returns aggregated metrics for cpi-admin."""
        mock_metrics = {
            "health": {"online": 2, "offline": 0, "total_gateways": 2, "health_percentage": 100.0},
            "sync": {"synced": 5, "total_deployments": 5, "sync_percentage": 100.0},
            "overall_status": "healthy",
        }

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_aggregated_metrics = AsyncMock(return_value=mock_metrics)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "healthy"
        assert data["health"]["total_gateways"] == 2

    def test_get_aggregated_metrics_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """GET /metrics is also accessible to tenant-admin."""
        mock_metrics = {
            "health": {"online": 1, "total_gateways": 1, "health_percentage": 100.0},
            "sync": {"synced": 3, "total_deployments": 3, "sync_percentage": 100.0},
            "overall_status": "healthy",
        }

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_aggregated_metrics = AsyncMock(return_value=mock_metrics)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/admin/gateways/metrics")

        assert response.status_code == 200

    def test_get_aggregated_metrics_403_viewer(self, app, mock_db_session):
        """GET /metrics returns 403 for viewer role."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db

        viewer = MagicMock()
        viewer.id = "viewer-id"
        viewer.email = "viewer@acme.com"
        viewer.username = "viewer"
        viewer.roles = ["viewer"]
        viewer.tenant_id = "acme"

        app.dependency_overrides[get_current_user] = lambda: viewer
        app.dependency_overrides[get_db] = lambda: mock_db_session

        with TestClient(app) as client:
            response = client.get("/v1/admin/gateways/metrics")

        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_guardrails_metrics_preserves_null_vs_zero(self, app_with_cpi_admin, mock_db_session):
        """Guardrails metrics preserve unknown null separately from healthy zero."""
        mock_metrics = {
            "health": {"total_gateways": 0},
            "sync": {"error": 0, "drifted": 0},
            "guardrails": {
                "pii_detections": None,
                "injection_blocks": 0,
                "prompt_guard_blocks": None,
                "content_filter_blocks": 0,
                "rate_limit_blocks": None,
                "last_sample_at": "2026-05-10T00:00:00+00:00",
                "metrics_age_seconds": 12,
                "source_healthy": True,
            },
            "overall_status": "unknown",
        }

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_aggregated_metrics = AsyncMock(return_value=mock_metrics)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/metrics")

        assert response.status_code == 200
        guardrails = response.json()["guardrails"]
        assert guardrails["pii_detections"] is None
        assert guardrails["injection_blocks"] == 0
        assert guardrails["content_filter_blocks"] == 0
        assert guardrails["rate_limit_blocks"] is None

    def test_guardrails_metrics_includes_freshness_fields(self, app_with_cpi_admin, mock_db_session):
        """Guardrails metrics include freshness fields required by PR-3A."""
        mock_metrics = {
            "health": {"total_gateways": 0},
            "sync": {"error": 0, "drifted": 0},
            "guardrails": {
                "pii_detections": 1,
                "injection_blocks": 0,
                "prompt_guard_blocks": 0,
                "content_filter_blocks": 0,
                "rate_limit_blocks": 0,
                "last_sample_at": "2026-05-10T00:00:00+00:00",
                "metrics_age_seconds": 12,
                "source_healthy": True,
            },
            "overall_status": "unknown",
        }

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_aggregated_metrics = AsyncMock(return_value=mock_metrics)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/metrics")

        assert response.status_code == 200
        guardrails = response.json()["guardrails"]
        assert "last_sample_at" in guardrails
        assert "metrics_age_seconds" in guardrails
        assert "source_healthy" in guardrails

    @pytest.mark.asyncio
    async def test_guardrails_metrics_source_healthy_false_on_query_failure(self, mock_db_session):
        """Prometheus query failure sets source_healthy=false instead of fake zeroes."""
        from src.services.gateway_metrics_service import GatewayMetricsService

        svc = GatewayMetricsService(mock_db_session)

        with patch("src.services.gateway_metrics_service.prometheus_client") as mock_prometheus:
            mock_prometheus.is_enabled = True
            mock_prometheus.query = AsyncMock(return_value=None)

            result = await svc._fetch_guardrails_metrics(time_range="1h")

        assert result["source_healthy"] is False
        assert result["pii_detections"] is None
        assert result["last_sample_at"] is None
        assert result["metrics_age_seconds"] is None

    def test_guardrails_metrics_range_filter(self, app_with_cpi_admin, mock_db_session):
        """GET /metrics accepts Live Calls-aligned range and passes it to the service."""
        mock_metrics = {
            "health": {"total_gateways": 0},
            "sync": {"error": 0, "drifted": 0},
            "guardrails": {},
            "overall_status": "unknown",
        }

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            get_aggregated_metrics = AsyncMock(return_value=mock_metrics)
            MockSvc.return_value.get_aggregated_metrics = get_aggregated_metrics

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/metrics?range=6h")

        assert response.status_code == 200
        get_aggregated_metrics.assert_awaited_once_with(tenant_id=None, time_range="6h")

    # ============== GET /metrics/guardrails/events ==============

    def test_guardrails_events_accepts_range_filter(self, app_with_tenant_admin, mock_db_session):
        """Guardrails events accepts Live Calls-aligned range and maps it to OpenSearch."""
        mock_client = MagicMock()
        mock_client.search = AsyncMock(
            return_value={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "startTime": "2026-05-10T00:00:00Z",
                                "traceId": "trace-1",
                                "spanId": "span-1",
                                "span.attributes.guardrails@tool": "tool-a",
                                "span.attributes.guardrails@action": "blocked",
                                "span.attributes.guardrails@reason": "injection",
                            }
                        }
                    ]
                }
            }
        )

        with patch("src.opensearch.opensearch_integration.get_opensearch_client", AsyncMock(return_value=mock_client)):
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/admin/gateways/metrics/guardrails/events?range=6h&limit=5")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["events"][0]["trace_id"] == "trace-1"

        body = mock_client.search.await_args.kwargs["body"]
        assert body["size"] == 5
        assert {"range": {"startTime": {"gte": "now-360m"}}} in body["query"]["bool"]["filter"]
        assert {"term": {"resource.attributes.tenant@id": "acme"}} in body["query"]["bool"]["filter"]

    def test_guardrails_events_no_client_returns_empty(self, app_with_cpi_admin, mock_db_session):
        """Missing OpenSearch client returns explicit empty events payload."""
        with patch("src.opensearch.opensearch_integration.get_opensearch_client", AsyncMock(return_value=None)):
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/metrics/guardrails/events")

        assert response.status_code == 200
        assert response.json() == {"events": [], "total": 0}

    def test_guardrails_events_query_failure_returns_empty(self, app_with_cpi_admin, mock_db_session):
        """OpenSearch query failure degrades to empty events payload."""
        mock_client = MagicMock()
        mock_client.search = AsyncMock(side_effect=RuntimeError("opensearch down"))

        with patch("src.opensearch.opensearch_integration.get_opensearch_client", AsyncMock(return_value=mock_client)):
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/metrics/guardrails/events")

        assert response.status_code == 200
        assert response.json() == {"events": [], "total": 0}

    # ============== GET /health-summary ==============

    def test_get_health_summary_success(self, app_with_cpi_admin, mock_db_session):
        """GET /health-summary returns gateway status counts."""
        mock_summary = {
            "online": 3,
            "offline": 1,
            "degraded": 0,
            "maintenance": 0,
            "total_gateways": 4,
            "health_percentage": 75.0,
        }

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_health_summary = AsyncMock(return_value=mock_summary)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/health-summary")

        assert response.status_code == 200
        data = response.json()
        assert data["total_gateways"] == 4
        assert data["health_percentage"] == 75.0

    # ============== GET /{gateway_id}/metrics ==============

    def test_get_gateway_metrics_success(self, app_with_cpi_admin, mock_db_session):
        """GET /{gateway_id}/metrics returns per-gateway metrics."""
        gw_id = uuid4()
        mock_gw_metrics = {
            "gateway_id": str(gw_id),
            "name": "kong-standalone",
            "display_name": "Kong DB-less",
            "gateway_type": "kong",
            "status": "online",
            "last_health_check": "2026-02-18T10:00:00",
            "sync": {"synced": 5, "total_deployments": 5, "sync_percentage": 100.0},
            "recent_errors": [],
        }

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_gateway_metrics = AsyncMock(return_value=mock_gw_metrics)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"/v1/admin/gateways/{gw_id}/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "kong-standalone"
        assert data["status"] == "online"

    def test_get_gateway_metrics_404(self, app_with_cpi_admin, mock_db_session):
        """GET /{gateway_id}/metrics returns 404 when gateway not found."""
        gw_id = uuid4()

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_gateway_metrics = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"/v1/admin/gateways/{gw_id}/metrics")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_gateway_metrics_invalid_uuid(self, app_with_cpi_admin, mock_db_session):
        """GET /{gateway_id}/metrics returns 422 for invalid UUID."""
        with TestClient(app_with_cpi_admin) as client:
            response = client.get("/v1/admin/gateways/not-a-uuid/metrics")

        assert response.status_code == 422
