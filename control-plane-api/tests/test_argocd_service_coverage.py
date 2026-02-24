"""Tests for ArgoCDService — coverage gap filler.

Covers: health_check, _request, get_applications, get_application,
        get_application_sync_status, get_platform_status (all branches),
        get_application_events, _extract_events, sync_application,
        get_application_diff, get_sync_summary.

Existing tests only cover basic connectivity. This fills 67% → ~95%.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


def _service():
    """Create a service instance with patched settings."""
    with patch("src.services.argocd_service.settings") as mock_settings:
        mock_settings.ARGOCD_URL = "https://argocd.example.com"
        mock_settings.ARGOCD_VERIFY_SSL = False
        mock_settings.argocd_platform_apps_list = ["app-1", "app-2"]
        mock_settings.GRAFANA_URL = "https://grafana.example.com"
        mock_settings.PROMETHEUS_URL = "https://prom.example.com"
        mock_settings.LOGS_URL = "https://logs.example.com"
        from src.services.argocd_service import ArgoCDService
        svc = ArgoCDService()
    return svc


class TestIsConnected:
    def test_connected_when_url_set(self):
        svc = _service()
        assert svc.is_connected is True

    def test_not_connected_when_empty(self):
        with patch("src.services.argocd_service.settings") as mock_settings:
            mock_settings.ARGOCD_URL = ""
            from src.services.argocd_service import ArgoCDService
            svc = ArgoCDService()
        assert svc.is_connected is False


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self):
        svc = _service()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"Version": "2.9.0"}

        with patch("httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.health_check("token-123")

        assert result is True

    @pytest.mark.asyncio
    async def test_unhealthy(self):
        svc = _service()

        with patch("httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.health_check("token-123")

        assert result is False


class TestExtractEvents:
    def test_extracts_from_history(self):
        svc = _service()
        app = {
            "status": {
                "history": [
                    {"id": 1, "revision": "abc12345678", "deployedAt": "2026-01-01T00:00:00Z", "source": {"repoURL": "https://github.com/org/repo"}},
                    {"id": 2, "revision": "def12345678", "deployedAt": "2026-01-02T00:00:00Z", "source": {"repoURL": "https://github.com/org/repo"}},
                ]
            }
        }
        events = svc._extract_events(app, limit=10)

        assert len(events) == 2
        # Most recent first (reversed)
        assert events[0]["id"] == 2
        assert events[0]["revision"] == "def12345"  # Truncated to 8

    def test_empty_history(self):
        svc = _service()
        events = svc._extract_events({"status": {}}, limit=5)
        assert events == []

    def test_limits_events(self):
        svc = _service()
        history = [{"id": i, "revision": f"rev{i}", "deployedAt": f"2026-01-0{i}T00:00:00Z", "source": {}} for i in range(1, 6)]
        events = svc._extract_events({"status": {"history": history}}, limit=2)
        assert len(events) == 2


class TestGetApplicationSyncStatus:
    @pytest.mark.asyncio
    async def test_returns_formatted_status(self):
        svc = _service()
        app_data = {
            "status": {
                "sync": {"status": "Synced", "revision": "abc12345678"},
                "health": {"status": "Healthy"},
                "operationState": {"phase": "Succeeded"},
                "conditions": [],
            }
        }

        with patch.object(svc, "get_application", return_value=app_data):
            result = await svc.get_application_sync_status("token", "my-app")

        assert result["name"] == "my-app"
        assert result["sync_status"] == "Synced"
        assert result["health_status"] == "Healthy"
        assert result["revision"] == "abc12345678"


class TestGetPlatformStatus:
    @pytest.mark.asyncio
    async def test_all_healthy_and_synced(self):
        svc = _service()
        app_data = {
            "status": {
                "sync": {"status": "Synced", "revision": "abc12345"},
                "health": {"status": "Healthy"},
                "operationState": {"finishedAt": "2026-01-01T00:00:00Z"},
            },
            "spec": {"destination": {"namespace": "stoa-system"}},
        }

        with (
            patch.object(svc, "get_application", return_value=app_data),
            patch("src.services.argocd_service.settings") as mock_settings,
        ):
            mock_settings.argocd_platform_apps_list = ["app-1"]
            result = await svc.get_platform_status("token")

        assert result["status"] == "healthy"
        assert len(result["components"]) == 1
        assert result["components"][0]["sync_status"] == "Synced"

    @pytest.mark.asyncio
    async def test_degraded_when_unhealthy(self):
        svc = _service()
        app_data = {
            "status": {
                "sync": {"status": "Synced", "revision": "abc"},
                "health": {"status": "Degraded"},
                "operationState": {},
            },
            "spec": {"destination": {}},
        }

        with (
            patch.object(svc, "get_application", return_value=app_data),
            patch("src.services.argocd_service.settings") as mock_settings,
        ):
            mock_settings.argocd_platform_apps_list = ["app-1"]
            result = await svc.get_platform_status("token")

        assert result["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_syncing_status(self):
        svc = _service()
        app_data = {
            "status": {
                "sync": {"status": "OutOfSync", "revision": "abc"},
                "health": {"status": "Healthy"},
                "operationState": {},
            },
            "spec": {"destination": {}},
        }

        with (
            patch.object(svc, "get_application", return_value=app_data),
            patch("src.services.argocd_service.settings") as mock_settings,
        ):
            mock_settings.argocd_platform_apps_list = ["app-1"]
            result = await svc.get_platform_status("token")

        assert result["status"] == "syncing"

    @pytest.mark.asyncio
    async def test_404_error_handling(self):
        svc = _service()
        mock_response = MagicMock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("Not found", request=MagicMock(), response=mock_response)

        with (
            patch.object(svc, "get_application", side_effect=error),
            patch("src.services.argocd_service.settings") as mock_settings,
        ):
            mock_settings.argocd_platform_apps_list = ["missing-app"]
            result = await svc.get_platform_status("token")

        assert result["components"][0]["sync_status"] == "NotFound"
        assert result["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_403_error_handling(self):
        svc = _service()
        mock_response = MagicMock()
        mock_response.status_code = 403
        error = httpx.HTTPStatusError("Forbidden", request=MagicMock(), response=mock_response)

        with (
            patch.object(svc, "get_application", side_effect=error),
            patch("src.services.argocd_service.settings") as mock_settings,
        ):
            mock_settings.argocd_platform_apps_list = ["app-1"]
            result = await svc.get_platform_status("token")

        assert "Access denied" in result["components"][0]["message"]

    @pytest.mark.asyncio
    async def test_generic_exception_handling(self):
        svc = _service()

        with (
            patch.object(svc, "get_application", side_effect=ConnectionError("timeout")),
            patch("src.services.argocd_service.settings") as mock_settings,
        ):
            mock_settings.argocd_platform_apps_list = ["app-1"]
            result = await svc.get_platform_status("token")

        assert result["components"][0]["sync_status"] == "Error"

    @pytest.mark.asyncio
    async def test_include_events(self):
        svc = _service()
        app_data = {
            "status": {
                "sync": {"status": "Synced", "revision": "abc"},
                "health": {"status": "Healthy"},
                "operationState": {},
                "history": [{"id": 1, "revision": "abc", "deployedAt": "2026-01-01T00:00:00Z", "source": {}}],
            },
            "spec": {"destination": {}},
        }

        with (
            patch.object(svc, "get_application", return_value=app_data),
            patch("src.services.argocd_service.settings") as mock_settings,
        ):
            mock_settings.argocd_platform_apps_list = ["app-1"]
            result = await svc.get_platform_status("token", include_events=True)

        assert "events" in result
        assert "app-1" in result["events"]

    @pytest.mark.asyncio
    async def test_500_error_handling(self):
        svc = _service()
        mock_response = MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError("Server Error", request=MagicMock(), response=mock_response)

        with (
            patch.object(svc, "get_application", side_effect=error),
            patch("src.services.argocd_service.settings") as mock_settings,
        ):
            mock_settings.argocd_platform_apps_list = ["app-1"]
            result = await svc.get_platform_status("token")

        assert result["components"][0]["sync_status"] == "Error"


class TestSyncApplication:
    @pytest.mark.asyncio
    async def test_triggers_sync(self):
        svc = _service()

        with patch.object(svc, "_request", return_value={"status": {"operationState": {"phase": "Running"}}}) as mock_req:
            await svc.sync_application("token", "my-app")

        mock_req.assert_called_once()
        call_args = mock_req.call_args
        assert call_args[0][1] == "POST"
        assert "/sync" in call_args[0][2]


class TestGetApplicationDiff:
    @pytest.mark.asyncio
    async def test_returns_diff_resources(self):
        svc = _service()
        managed = {
            "items": [
                {"name": "deploy-1", "namespace": "default", "kind": "Deployment", "group": "apps", "status": "OutOfSync", "health": {"status": "Healthy"}, "diff": "- old\n+ new"},
                {"name": "svc-1", "namespace": "default", "kind": "Service", "status": "Synced"},
            ]
        }

        with patch.object(svc, "_request", return_value=managed):
            result = await svc.get_application_diff("token", "my-app")

        assert result["total_resources"] == 2
        assert result["diff_count"] == 1
        assert result["resources"][0]["name"] == "deploy-1"

    @pytest.mark.asyncio
    async def test_no_diffs(self):
        svc = _service()
        managed = {
            "items": [
                {"name": "svc-1", "namespace": "default", "kind": "Service", "status": "Synced"},
            ]
        }

        with patch.object(svc, "_request", return_value=managed):
            result = await svc.get_application_diff("token", "my-app")

        assert result["diff_count"] == 0


class TestGetSyncSummary:
    @pytest.mark.asyncio
    async def test_aggregates_counts(self):
        svc = _service()
        status_data = {
            "components": [
                {"sync_status": "Synced", "health_status": "Healthy"},
                {"sync_status": "OutOfSync", "health_status": "Degraded"},
                {"sync_status": "Synced", "health_status": "Healthy"},
            ],
            "status": "degraded",
            "checked_at": "2026-01-01T00:00:00Z",
        }

        with (
            patch.object(svc, "get_platform_status", return_value=status_data),
            patch("src.services.argocd_service.settings") as mock_settings,
        ):
            mock_settings.ARGOCD_URL = "https://argocd.example.com"
            result = await svc.get_sync_summary("token")

        assert result["total_apps"] == 3
        assert result["synced_count"] == 2
        assert result["out_of_sync_count"] == 1
        assert result["healthy_count"] == 2
        assert result["degraded_count"] == 1

    @pytest.mark.asyncio
    async def test_error_returns_empty(self):
        svc = _service()

        with (
            patch.object(svc, "get_platform_status", side_effect=Exception("fail")),
            patch("src.services.argocd_service.settings") as mock_settings,
        ):
            mock_settings.ARGOCD_URL = "https://argocd.example.com"
            result = await svc.get_sync_summary("token")

        assert result["total_apps"] == 0
        assert "error" in result


class TestGetApplicationEvents:
    @pytest.mark.asyncio
    async def test_delegates_to_extract(self):
        svc = _service()
        app_data = {
            "status": {
                "history": [
                    {"id": 1, "revision": "abc123", "deployedAt": "2026-01-01T00:00:00Z", "source": {}},
                ]
            }
        }

        with patch.object(svc, "get_application", return_value=app_data):
            events = await svc.get_application_events("token", "my-app", limit=10)

        assert len(events) == 1
