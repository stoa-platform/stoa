"""Tests for health endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health_endpoint(client):
    """Test /health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "stoa-mcp-gateway"
    assert "version" in data
    assert "timestamp" in data


def test_ready_endpoint(client):
    """Test /ready endpoint returns status."""
    response = client.get("/ready")
    # Status can be 200 (ready) or 503 (not ready) depending on app state
    assert response.status_code in [200, 503]
    data = response.json()
    assert data["status"] in ["ready", "not_ready"]
    assert data["service"] == "stoa-mcp-gateway"
    assert "checks" in data


def test_live_endpoint(client):
    """Test /live endpoint returns alive status."""
    response = client.get("/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


def test_root_endpoint(client):
    """Test root endpoint returns service info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "stoa-mcp-gateway"
    assert "version" in data
    assert "links" in data


def test_mcp_tools_endpoint(client):
    """Test MCP tools endpoint (placeholder)."""
    response = client.get("/mcp/v1/tools")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data


def test_mcp_resources_endpoint(client):
    """Test MCP resources endpoint (placeholder)."""
    response = client.get("/mcp/v1/resources")
    assert response.status_code == 200
    data = response.json()
    assert "resources" in data


# =============================================================================
# CAB-658: Health Check Module Tests
# =============================================================================


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self):
        """Test that HealthStatus has correct values."""
        from src.services.health import HealthStatus

        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.DOWN.value == "down"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestHealthThresholds:
    """Tests for latency thresholds."""

    def test_determine_status_healthy(self):
        """Test status determination for healthy latency."""
        from src.services.health import determine_status, HealthThresholds, HealthStatus

        thresholds = HealthThresholds(healthy_max=100, degraded_max=500)
        assert determine_status(50, thresholds) == HealthStatus.HEALTHY
        assert determine_status(100, thresholds) == HealthStatus.HEALTHY

    def test_determine_status_degraded(self):
        """Test status determination for degraded latency."""
        from src.services.health import determine_status, HealthThresholds, HealthStatus

        thresholds = HealthThresholds(healthy_max=100, degraded_max=500)
        assert determine_status(101, thresholds) == HealthStatus.DEGRADED
        assert determine_status(500, thresholds) == HealthStatus.DEGRADED

    def test_determine_status_very_slow(self):
        """Test status determination for very slow responses."""
        from src.services.health import determine_status, HealthThresholds, HealthStatus

        thresholds = HealthThresholds(healthy_max=100, degraded_max=500)
        # Very slow but responding is still degraded, not down
        assert determine_status(1000, thresholds) == HealthStatus.DEGRADED


class TestComponentHealth:
    """Tests for ComponentHealth model."""

    def test_component_health_creation(self):
        """Test creating ComponentHealth instance."""
        from src.services.health import ComponentHealth, HealthStatus

        health = ComponentHealth(
            status=HealthStatus.HEALTHY,
            latency_ms=12.5,
        )
        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms == 12.5
        assert health.error is None
        assert health.details is None

    def test_component_health_with_error(self):
        """Test ComponentHealth with error."""
        from src.services.health import ComponentHealth, HealthStatus

        health = ComponentHealth(
            status=HealthStatus.DOWN,
            latency_ms=None,
            error="Connection refused",
        )
        assert health.status == HealthStatus.DOWN
        assert health.latency_ms is None
        assert health.error == "Connection refused"

    def test_component_health_with_details(self):
        """Test ComponentHealth with details."""
        from src.services.health import ComponentHealth, HealthStatus

        health = ComponentHealth(
            status=HealthStatus.HEALTHY,
            latency_ms=45.0,
            details={"cluster_status": "green", "number_of_nodes": 3},
        )
        assert health.details["cluster_status"] == "green"
        assert health.details["number_of_nodes"] == 3


class TestPlatformHealth:
    """Tests for PlatformHealth model."""

    def test_platform_health_summary_all_healthy(self):
        """Test summary when all components are healthy."""
        from src.services.health import PlatformHealth, ComponentHealth, HealthStatus

        health = PlatformHealth(
            overall=HealthStatus.HEALTHY,
            components={
                "gateway": ComponentHealth(status=HealthStatus.HEALTHY, latency_ms=12),
                "keycloak": ComponentHealth(status=HealthStatus.HEALTHY, latency_ms=45),
            },
            checked_at="2026-01-18T14:30:00Z",
        )
        assert health.summary == "All systems operational"

    def test_platform_health_summary_degraded(self):
        """Test summary when some components are degraded."""
        from src.services.health import PlatformHealth, ComponentHealth, HealthStatus

        health = PlatformHealth(
            overall=HealthStatus.DEGRADED,
            components={
                "gateway": ComponentHealth(status=HealthStatus.HEALTHY, latency_ms=12),
                "kafka": ComponentHealth(status=HealthStatus.DEGRADED, latency_ms=230),
            },
            checked_at="2026-01-18T14:30:00Z",
        )
        assert "kafka" in health.summary
        assert "degraded" in health.summary

    def test_platform_health_summary_down(self):
        """Test summary when some components are down."""
        from src.services.health import PlatformHealth, ComponentHealth, HealthStatus

        health = PlatformHealth(
            overall=HealthStatus.DOWN,
            components={
                "gateway": ComponentHealth(status=HealthStatus.HEALTHY, latency_ms=12),
                "database": ComponentHealth(
                    status=HealthStatus.DOWN,
                    error="Connection refused",
                ),
            },
            checked_at="2026-01-18T14:30:00Z",
        )
        assert "database" in health.summary
        assert "down" in health.summary


class TestHealthChecker:
    """Tests for HealthChecker class."""

    def test_health_checker_creation(self):
        """Test creating HealthChecker with defaults."""
        from src.services.health import HealthChecker

        checker = HealthChecker()
        assert checker.timeout == 5.0
        assert "gateway" in checker.thresholds
        assert "keycloak" in checker.thresholds

    def test_health_checker_custom_config(self):
        """Test HealthChecker with custom configuration."""
        from src.services.health import HealthChecker

        checker = HealthChecker(
            gateway_url="http://custom:8080",
            timeout_seconds=10.0,
        )
        assert checker.gateway_url == "http://custom:8080"
        assert checker.timeout == 10.0

    @pytest.mark.asyncio
    async def test_check_components_invalid(self):
        """Test checking invalid component name."""
        from src.services.health import HealthChecker

        checker = HealthChecker()
        health = await checker.check_components(["invalid_component"])
        # Invalid components are silently ignored
        assert len(health.components) == 0
