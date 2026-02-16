"""Tests for ArgoCD service — extract_events, platform_status, health_check."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.services.argocd_service import ArgoCDService


@pytest.fixture
def argocd_svc():
    with patch("src.services.argocd_service.settings") as mock_settings:
        mock_settings.ARGOCD_URL = "https://argocd.test.dev"
        mock_settings.ARGOCD_VERIFY_SSL = False
        mock_settings.argocd_platform_apps_list = ["app-1", "app-2"]
        svc = ArgoCDService()
    return svc


class TestExtractEvents:
    def test_extracts_history(self, argocd_svc):
        app = {
            "status": {
                "history": [
                    {
                        "id": 1,
                        "revision": "abc12345678",
                        "deployedAt": "2026-01-01T00:00:00Z",
                        "source": {"repoURL": "https://github.com/test"},
                    },
                    {
                        "id": 2,
                        "revision": "def12345678",
                        "deployedAt": "2026-01-02T00:00:00Z",
                        "source": {"repoURL": "https://github.com/test"},
                    },
                ]
            }
        }
        events = argocd_svc._extract_events(app, limit=10)
        assert len(events) == 2
        # Reversed order (newest first)
        assert events[0]["id"] == 2
        assert events[0]["revision"] == "def12345"  # truncated to 8 chars

    def test_empty_history(self, argocd_svc):
        app = {"status": {"history": []}}
        events = argocd_svc._extract_events(app)
        assert events == []

    def test_limit_applied(self, argocd_svc):
        app = {
            "status": {
                "history": [
                    {"id": i, "revision": f"rev{i:08d}", "deployedAt": "2026-01-01", "source": {}} for i in range(10)
                ]
            }
        }
        events = argocd_svc._extract_events(app, limit=3)
        assert len(events) == 3


class TestHealthCheck:
    async def test_healthy(self, argocd_svc):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = AsyncMock()

        with patch("src.services.argocd_service.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await argocd_svc.health_check("mock-token")

        assert result is True

    async def test_unhealthy(self, argocd_svc):
        with patch("src.services.argocd_service.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await argocd_svc.health_check("mock-token")

        assert result is False


class TestGetSyncSummary:
    async def test_returns_counts(self, argocd_svc):
        mock_status = {
            "status": "healthy",
            "components": [
                {"name": "app-1", "sync_status": "Synced", "health_status": "Healthy"},
                {"name": "app-2", "sync_status": "OutOfSync", "health_status": "Degraded"},
            ],
        }
        argocd_svc.get_platform_status = AsyncMock(return_value=mock_status)

        result = await argocd_svc.get_sync_summary("mock-token")

        assert result["total_apps"] == 2
        assert result["synced_count"] == 1
        assert result["out_of_sync_count"] == 1
        assert result["healthy_count"] == 1
        assert result["degraded_count"] == 1

    async def test_error_returns_empty(self, argocd_svc):
        argocd_svc.get_platform_status = AsyncMock(side_effect=RuntimeError("fail"))

        result = await argocd_svc.get_sync_summary("mock-token")

        assert result["total_apps"] == 0
        assert "error" in result


class TestIsConnected:
    def test_connected_when_url_set(self, argocd_svc):
        assert argocd_svc.is_connected is True

    def test_not_connected_when_empty(self):
        with patch("src.services.argocd_service.settings") as mock_settings:
            mock_settings.ARGOCD_URL = ""
            svc = ArgoCDService()
        assert svc.is_connected is False
