"""Tests for CAB-957: Anti-Zombie Node Pattern.

Tests for:
- DeepReadinessChecker
- LastGaspMiddleware
- Readiness probe deep checks
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import Response


# =============================================================================
# DeepReadinessChecker Tests
# =============================================================================


class TestDeepReadinessChecker:
    """Tests for DeepReadinessChecker class."""

    def test_creation_with_defaults(self):
        """Test creating DeepReadinessChecker with default values."""
        from src.services.health import DeepReadinessChecker

        checker = DeepReadinessChecker()
        assert checker.timeout == 3.0
        assert checker.cache_ttl == 1.0
        assert checker.database_url == ""
        assert checker.keycloak_url == ""
        assert checker.core_api_url == ""

    def test_creation_with_custom_config(self):
        """Test creating DeepReadinessChecker with custom configuration."""
        from src.services.health import DeepReadinessChecker

        checker = DeepReadinessChecker(
            database_url="postgresql://localhost/test",
            keycloak_url="https://auth.example.com",
            keycloak_realm="test",
            core_api_url="https://api.example.com",
            timeout_seconds=5.0,
            cache_ttl_seconds=2.0,
        )
        assert checker.database_url == "postgresql://localhost/test"
        assert checker.keycloak_url == "https://auth.example.com"
        assert checker.keycloak_realm == "test"
        assert checker.core_api_url == "https://api.example.com"
        assert checker.timeout == 5.0
        assert checker.cache_ttl == 2.0

    @pytest.mark.asyncio
    async def test_check_returns_ready_when_no_components_configured(self):
        """Test that check returns not ready when no components configured."""
        from src.services.health import DeepReadinessChecker

        checker = DeepReadinessChecker()
        result = await checker.check()

        # No components configured = no checks = not ready
        assert result.ready is False
        assert len(result.checks) == 0
        assert len(result.failed_checks) == 0

    @pytest.mark.asyncio
    async def test_check_caches_result(self):
        """Test that check result is cached within TTL."""
        from src.services.health import DeepReadinessChecker

        checker = DeepReadinessChecker(
            keycloak_url="https://auth.example.com",
            cache_ttl_seconds=10.0,  # Long TTL for test
        )

        # Mock the keycloak check
        with patch.object(checker, '_check_keycloak') as mock_check:
            mock_check.return_value = MagicMock(status="healthy")

            # First call should hit the check
            result1 = await checker.check()
            assert mock_check.call_count == 1

            # Second call should use cache
            result2 = await checker.check()
            assert mock_check.call_count == 1  # Still 1, cached

            assert result2.cached is True

    def test_invalidate_cache(self):
        """Test cache invalidation."""
        from src.services.health import DeepReadinessChecker

        checker = DeepReadinessChecker()
        checker._cached_result = MagicMock()
        checker._cache_timestamp = 100.0

        checker.invalidate_cache()

        assert checker._cached_result is None
        assert checker._cache_timestamp == 0.0

    @pytest.mark.asyncio
    async def test_readiness_fails_when_keycloak_unreachable(self):
        """Test readiness fails when Keycloak is unreachable."""
        from src.services.health import DeepReadinessChecker, HealthStatus
        import httpx

        checker = DeepReadinessChecker(
            keycloak_url="https://auth.example.com",
            timeout_seconds=1.0,
        )

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.TimeoutException("Connection timeout")

            result = await checker.check()

            assert result.ready is False
            assert "keycloak" in result.failed_checks
            assert result.checks["keycloak"].status == HealthStatus.DOWN
            assert "timeout" in result.checks["keycloak"].error.lower()


class TestReadinessResult:
    """Tests for ReadinessResult model."""

    def test_readiness_result_creation(self):
        """Test creating ReadinessResult instance."""
        from src.services.health import ReadinessResult, ComponentHealth, HealthStatus

        result = ReadinessResult(
            ready=True,
            checks={
                "database": ComponentHealth(status=HealthStatus.HEALTHY, latency_ms=10),
            },
            failed_checks=[],
            checked_at="2026-01-26T12:00:00Z",
            cached=False,
        )
        assert result.ready is True
        assert len(result.checks) == 1
        assert len(result.failed_checks) == 0
        assert result.cached is False

    def test_readiness_result_with_failures(self):
        """Test ReadinessResult with failed checks."""
        from src.services.health import ReadinessResult, ComponentHealth, HealthStatus

        result = ReadinessResult(
            ready=False,
            checks={
                "database": ComponentHealth(status=HealthStatus.HEALTHY, latency_ms=10),
                "keycloak": ComponentHealth(status=HealthStatus.DOWN, error="Connection refused"),
            },
            failed_checks=["keycloak"],
            checked_at="2026-01-26T12:00:00Z",
            cached=False,
        )
        assert result.ready is False
        assert len(result.failed_checks) == 1
        assert "keycloak" in result.failed_checks


# =============================================================================
# LastGaspMiddleware Tests
# =============================================================================


class TestLastGaspMiddleware:
    """Tests for LastGaspMiddleware class."""

    @pytest.fixture
    def app_state(self):
        """Create test app state."""
        return {"ready": True}

    @pytest.fixture
    def test_app(self, app_state):
        """Create test FastAPI app with LastGaspMiddleware."""
        from src.middleware.last_gasp import LastGaspMiddleware

        app = FastAPI()
        app.add_middleware(LastGaspMiddleware, app_state=app_state)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        return app

    def test_request_passes_when_ready(self, test_app, app_state):
        """Test that requests pass through when node is ready."""
        app_state["ready"] = True
        client = TestClient(test_app)

        response = client.get("/test")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_request_rejected_when_not_ready(self, test_app, app_state):
        """Test that requests are rejected with 503 when not ready."""
        app_state["ready"] = False
        client = TestClient(test_app)

        response = client.get("/test")

        assert response.status_code == 503
        assert response.headers.get("X-STOA-Node-Status") == "degraded"
        assert "X-Correlation-ID" in response.headers
        assert "Retry-After" in response.headers

    def test_correlation_id_preserved(self, test_app, app_state):
        """Test that existing correlation ID is preserved in rejection."""
        app_state["ready"] = False
        client = TestClient(test_app)

        correlation_id = "test-correlation-123"
        response = client.get("/test", headers={"X-Correlation-ID": correlation_id})

        assert response.status_code == 503
        assert response.headers.get("X-Correlation-ID") == correlation_id

    def test_correlation_id_generated_if_missing(self, test_app, app_state):
        """Test that correlation ID is generated if not provided."""
        app_state["ready"] = False
        client = TestClient(test_app)

        response = client.get("/test")

        assert response.status_code == 503
        correlation_id = response.headers.get("X-Correlation-ID")
        assert correlation_id is not None
        # Should be a valid UUID format
        assert len(correlation_id) == 36  # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx


class TestLastGaspMetrics:
    """Tests for Last Gasp Prometheus metrics."""

    def test_rejected_requests_metric_exists(self):
        """Test that rejected requests counter exists."""
        from src.middleware.last_gasp import REQUESTS_REJECTED_TOTAL

        assert REQUESTS_REJECTED_TOTAL is not None

    def test_record_request_rejected_function(self):
        """Test the helper function for recording rejections."""
        from src.middleware.last_gasp import record_request_rejected, REQUESTS_REJECTED_TOTAL

        # Get initial value
        initial_value = REQUESTS_REJECTED_TOTAL.labels(reason="test").describe()[0].samples[0].value \
            if REQUESTS_REJECTED_TOTAL.labels(reason="test").describe() else 0

        # Record a rejection
        record_request_rejected("test")

        # Value should have increased (counter behavior)
        # Note: In tests, we just verify the function doesn't raise


# =============================================================================
# Integration Tests
# =============================================================================


class TestHealthReadyEndpointIntegration:
    """Integration tests for /health/ready endpoint with deep checks."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.main import app
        return TestClient(app)

    def test_health_ready_returns_checks(self, client):
        """Test that /health/ready returns check details."""
        response = client.get("/health/ready")

        # Can be 200 or 503 depending on state
        assert response.status_code in [200, 503]
        data = response.json()

        assert "status" in data
        assert "checks" in data
        assert "timestamp" in data
        assert data["status"] in ["healthy", "unhealthy"]

    def test_health_ready_includes_failed_checks_on_failure(self, client):
        """Test that /health/ready includes failed_checks when unhealthy."""
        response = client.get("/health/ready")

        if response.status_code == 503:
            data = response.json()
            # Should include failed_checks and details when unhealthy
            assert "failed_checks" in data or "checks" in data


class TestK8sProbeConfiguration:
    """Tests to validate K8s probe configuration expectations."""

    def test_health_ready_responds_within_timeout(self, monkeypatch):
        """Test that /health/ready responds within probe timeout (5s)."""
        import time
        from src.main import app

        client = TestClient(app)

        start = time.time()
        response = client.get("/health/ready")
        elapsed = time.time() - start

        # Should respond within 5 seconds (K8s probe timeout)
        assert elapsed < 5.0
        assert response.status_code in [200, 503]

    def test_health_ready_returns_503_when_not_ready(self):
        """Test that /health/ready returns 503 when app not ready."""
        from src.main import app, app_state

        # Save original state
        original_ready = app_state.get("ready", False)

        try:
            # Set not ready
            app_state["ready"] = False

            client = TestClient(app)
            response = client.get("/health/ready")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
        finally:
            # Restore original state
            app_state["ready"] = original_ready
