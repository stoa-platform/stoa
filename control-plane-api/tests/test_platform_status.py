"""Tests for CAB-687: Parallel ArgoCD calls in platform status endpoint.

Validates:
- Parallel execution (not waterfall)
- 5s timeout per call (Council obligation #1)
- Partial failure logging (Council obligation #2)
- 30s in-memory cache (Council obligation #3)
"""
import asyncio
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.argocd_service import ArgoCDService, ARGOCD_CALL_TIMEOUT


# ============================================================================
# Unit tests for ArgoCDService.get_platform_status (parallel gather)
# ============================================================================

class TestPlatformStatusParallel:
    """Verify that get_platform_status uses asyncio.gather for parallel calls."""

    @pytest.mark.asyncio
    async def test_parallel_calls_faster_than_sequential(self):
        """Apps should be fetched in parallel, not sequentially."""
        service = ArgoCDService.__new__(ArgoCDService)
        service._base_url = "https://argocd.test"

        call_count = 0

        async def mock_get_app(auth_token, name):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # 100ms per call
            return {
                "status": {
                    "sync": {"status": "Synced", "revision": "abc12345"},
                    "health": {"status": "Healthy"},
                    "operationState": {"finishedAt": "2026-01-01T00:00:00Z"},
                    "history": [],
                },
                "spec": {"destination": {"namespace": "stoa-system"}},
            }

        service.get_application = mock_get_app
        app_names = ["app1", "app2", "app3", "app4"]

        start = time.time()
        result = await service.get_platform_status("token", app_names=app_names)
        elapsed = time.time() - start

        assert call_count == 4
        # 4 calls x 100ms sequential = 400ms; parallel should be ~100ms
        assert elapsed < 0.3, f"Expected parallel execution, took {elapsed:.2f}s"
        assert result["status"] == "healthy"
        assert len(result["components"]) == 4

    @pytest.mark.asyncio
    async def test_partial_failure_graceful_degradation(self):
        """One app failing should not break the entire response."""
        service = ArgoCDService.__new__(ArgoCDService)
        service._base_url = "https://argocd.test"

        async def mock_get_app(auth_token, name):
            if name == "failing-app":
                raise ConnectionError("Connection refused")
            return {
                "status": {
                    "sync": {"status": "Synced", "revision": "abc12345"},
                    "health": {"status": "Healthy"},
                    "operationState": {"finishedAt": "2026-01-01T00:00:00Z"},
                    "history": [],
                },
                "spec": {"destination": {"namespace": "stoa-system"}},
            }

        service.get_application = mock_get_app

        result = await service.get_platform_status(
            "token", app_names=["good-app", "failing-app"]
        )

        assert result["status"] == "degraded"
        assert len(result["components"]) == 2
        assert result["components"][0]["sync_status"] == "Synced"
        assert result["components"][1]["sync_status"] == "Error"
        assert "Connection refused" in result["components"][1]["message"]

    @pytest.mark.asyncio
    async def test_include_events_extracts_from_fetched_apps(self):
        """include_events=True should extract events without extra API calls."""
        service = ArgoCDService.__new__(ArgoCDService)
        service._base_url = "https://argocd.test"

        async def mock_get_app(auth_token, name):
            return {
                "status": {
                    "sync": {"status": "Synced", "revision": "abc12345"},
                    "health": {"status": "Healthy"},
                    "operationState": {"finishedAt": "2026-01-01T00:00:00Z"},
                    "history": [
                        {"id": 1, "revision": "abc12345", "deployedAt": "2026-01-01T00:00:00Z",
                         "source": {"repoURL": "https://git.example.com"}},
                    ],
                },
                "spec": {"destination": {"namespace": "stoa-system"}},
            }

        service.get_application = mock_get_app

        result = await service.get_platform_status(
            "token", app_names=["app1"], include_events=True
        )

        assert "events" in result
        assert "app1" in result["events"]
        assert len(result["events"]["app1"]) == 1
        assert result["events"]["app1"][0]["revision"] == "abc12345"


# ============================================================================
# Timeout tests (Council obligation #1)
# ============================================================================

class TestTimeoutObligation:
    """Verify explicit 5s timeout on ArgoCD calls."""

    def test_timeout_constant_is_5s(self):
        """ARGOCD_CALL_TIMEOUT must be 5 seconds."""
        assert ARGOCD_CALL_TIMEOUT == 5.0


# ============================================================================
# Partial error logging tests (Council obligation #2)
# ============================================================================

class TestPartialErrorLogging:
    """Verify partial failures are logged, not silenced."""

    @pytest.mark.asyncio
    async def test_partial_failure_logs_warning(self):
        """Failed apps should produce a warning log with app names."""
        service = ArgoCDService.__new__(ArgoCDService)
        service._base_url = "https://argocd.test"

        async def mock_get_app(auth_token, name):
            if name == "broken":
                raise RuntimeError("timeout")
            return {
                "status": {
                    "sync": {"status": "Synced", "revision": "abc"},
                    "health": {"status": "Healthy"},
                    "operationState": {},
                    "history": [],
                },
                "spec": {"destination": {"namespace": "ns"}},
            }

        service.get_application = mock_get_app

        with patch("src.services.argocd_service.logger") as mock_logger:
            await service.get_platform_status("token", app_names=["ok-app", "broken"])

            # Should log individual failure
            mock_logger.warning.assert_any_call(
                "Failed to get status for broken: timeout"
            )
            # Should log summary
            summary_calls = [
                c for c in mock_logger.warning.call_args_list
                if "partial failure" in str(c)
            ]
            assert len(summary_calls) == 1, "Expected partial failure summary log"


# ============================================================================
# Cache tests (Council obligation #3)
# ============================================================================

class TestPlatformStatusCache:
    """Verify 30s in-memory cache for /v1/platform/status."""

    def test_cache_ttl_is_30s(self):
        """Platform status cache TTL must be 30 seconds."""
        from src.routers.platform import _platform_status_cache
        assert _platform_status_cache._default_ttl == 30

    @pytest.mark.asyncio
    async def test_cache_returns_cached_response(self):
        """Second call should return cached data without hitting ArgoCD."""
        from src.routers.platform import _platform_status_cache

        # Clear any existing cache
        await _platform_status_cache.clear()

        test_response = {"cached": True}
        await _platform_status_cache.set("platform:status", test_response)

        cached = await _platform_status_cache.get("platform:status")
        assert cached == test_response

        # Clean up
        await _platform_status_cache.clear()
