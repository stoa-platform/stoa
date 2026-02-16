"""Tests for health router — /health/live, /health/ready, /health/startup"""

from unittest.mock import patch


class TestLiveness:
    def test_live_returns_healthy(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/health/live")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert "version" in body
        assert "timestamp" in body

    def test_live_no_auth_required(self, client):
        """Health endpoints should work without authentication."""
        resp = client.get("/health/live")
        assert resp.status_code == 200


class TestStartup:
    def test_startup_returns_healthy(self, client):
        resp = client.get("/health/startup")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"


class TestReadiness:
    def test_ready_all_healthy(self, client):
        with (
            patch("src.routers.health._check_kafka_connected", return_value=True),
            patch("src.routers.health._check_keycloak_connected", return_value=True),
            patch("src.routers.health._check_gitlab_connected", return_value=True),
            patch("src.routers.health._check_gateway_connected", return_value=True),
        ):
            resp = client.get("/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["checks"]["kafka"] == "ok"
        assert body["checks"]["keycloak"] == "ok"

    def test_ready_kafka_disconnected_returns_503(self, client):
        with (
            patch("src.routers.health.settings") as mock_settings,
            patch("src.routers.health._check_kafka_connected", return_value=False),
            patch("src.routers.health._check_keycloak_connected", return_value=True),
            patch("src.routers.health._check_gitlab_connected", return_value=True),
            patch("src.routers.health._check_gateway_connected", return_value=True),
        ):
            mock_settings.KAFKA_ENABLED = True
            mock_settings.VERSION = "test"
            resp = client.get("/health/ready")
        assert resp.status_code == 503
        body = resp.json()["detail"]
        assert body["status"] == "degraded"
        assert body["checks"]["kafka"] == "disconnected"

    def test_ready_keycloak_disconnected_returns_503(self, client):
        with (
            patch("src.routers.health._check_kafka_connected", return_value=True),
            patch("src.routers.health._check_keycloak_connected", return_value=False),
            patch("src.routers.health._check_gitlab_connected", return_value=True),
            patch("src.routers.health._check_gateway_connected", return_value=True),
        ):
            resp = client.get("/health/ready")
        assert resp.status_code == 503

    def test_ready_gitlab_disconnected_still_healthy(self, client):
        """GitLab is non-critical — should not affect readiness."""
        with (
            patch("src.routers.health._check_kafka_connected", return_value=True),
            patch("src.routers.health._check_keycloak_connected", return_value=True),
            patch("src.routers.health._check_gitlab_connected", return_value=False),
            patch("src.routers.health._check_gateway_connected", return_value=True),
        ):
            resp = client.get("/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["checks"]["gitlab"] == "disconnected"

    def test_ready_kafka_disabled(self, client):
        with (
            patch("src.routers.health.settings") as mock_settings,
            patch("src.routers.health._check_keycloak_connected", return_value=True),
            patch("src.routers.health._check_gitlab_connected", return_value=True),
            patch("src.routers.health._check_gateway_connected", return_value=True),
        ):
            mock_settings.KAFKA_ENABLED = False
            mock_settings.VERSION = "test"
            resp = client.get("/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["checks"]["kafka"] == "disabled"
