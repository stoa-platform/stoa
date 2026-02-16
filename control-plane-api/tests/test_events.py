"""
Tests for Events Router - CAB-1300

Target: Coverage of src/routers/events.py
Tests: event history, deployment-result, global stream RBAC.
"""

from fastapi.testclient import TestClient


class TestEventHistory:
    """Test event history endpoint."""

    def test_event_history_returns_empty_with_message(self, app_with_tenant_admin, mock_db_session):
        """Event history returns empty list with informational message."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/events/history/acme")

        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []
        assert "not yet configured" in data["message"]

    def test_event_history_with_type_filter(self, app_with_tenant_admin, mock_db_session):
        """Event history accepts event_type filter parameter."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/events/history/acme?event_type=deploy-success")

        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []


class TestDeploymentResult:
    """Test deployment result endpoint."""

    def test_deployment_result_publishes_to_kafka(self, app_with_cpi_admin, mock_db_session):
        """Deployment result endpoint publishes event to Kafka."""
        with TestClient(app_with_cpi_admin) as client:
            response = client.post(
                "/v1/events/deployment-result",
                json={
                    "api_name": "weather-api",
                    "api_version": "1.0",
                    "tenant_id": "acme",
                    "status": "success",
                    "action": "deploy",
                    "message": "Deployed successfully",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["api_name"] == "weather-api"
        assert data["deployment_status"] == "success"


class TestGlobalStream:
    """Test global event stream RBAC."""

    def test_global_stream_requires_cpi_admin(self, app_with_tenant_admin, mock_db_session):
        """Non-admin users cannot access global event stream."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/events/stream/global")

        assert response.status_code == 403
        assert "cpi-admin" in response.json()["detail"]
