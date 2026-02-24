"""Tests for Platform Router — CAB-1436

Covers: /v1/platform (status, components, sync, events, diff)
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


ARGOCD_SVC = "src.routers.platform.argocd_service"
SETTINGS = "src.routers.platform.settings"


def _mock_settings():
    """Return mock settings with expected attributes."""
    s = MagicMock()
    s.ARGOCD_URL = "https://argocd.gostoa.dev"
    s.GRAFANA_URL = "https://grafana.gostoa.dev"
    s.PROMETHEUS_URL = "https://prometheus.gostoa.dev"
    s.LOGS_URL = "https://logs.gostoa.dev"
    s.argocd_platform_apps_list = ["stoa-control-plane", "stoa-console"]
    return s


def _mock_status_data():
    """Return mock platform status from ArgoCD."""
    return {
        "status": "healthy",
        "checked_at": "2026-02-24T10:00:00Z",
        "components": [
            {
                "name": "stoa-control-plane",
                "display_name": "Control Plane API",
                "sync_status": "Synced",
                "health_status": "Healthy",
                "revision": "abc1234",
                "last_sync": "2026-02-24T10:00:00Z",
                "message": None,
            },
        ],
        "events": {
            "stoa-control-plane": [
                {"id": 1, "revision": "abc1234", "deployed_at": "2026-02-24T10:00:00Z"},
            ],
        },
    }


class TestPlatformStatus:
    """Tests for GET /v1/platform/status."""

    def test_status_mock_when_argocd_not_connected(self, client_as_cpi_admin: TestClient):
        """Returns mock status when ArgoCD is not configured."""
        mock_argocd = MagicMock()
        mock_argocd.is_connected = False

        with (
            patch(ARGOCD_SVC, mock_argocd),
            patch(SETTINGS, _mock_settings()),
        ):
            resp = client_as_cpi_admin.get(
                "/v1/platform/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "gitops" in data
        assert "events" in data

    def test_status_success_with_argocd(self, client_as_cpi_admin: TestClient):
        """Returns real status when ArgoCD is connected."""
        mock_argocd = MagicMock()
        mock_argocd.is_connected = True
        mock_argocd.health_check = AsyncMock(return_value=True)
        mock_argocd.get_platform_status = AsyncMock(return_value=_mock_status_data())

        cache_mock = MagicMock()
        cache_mock.get = AsyncMock(return_value=None)
        cache_mock.set = AsyncMock()

        with (
            patch(ARGOCD_SVC, mock_argocd),
            patch(SETTINGS, _mock_settings()),
            patch("src.routers.platform._platform_status_cache", cache_mock),
        ):
            resp = client_as_cpi_admin.get(
                "/v1/platform/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["gitops"]["status"] == "healthy"
        assert len(data["gitops"]["components"]) == 1


class TestListComponents:
    """Tests for GET /v1/platform/components."""

    def test_list_components_success(self, client_as_cpi_admin: TestClient):
        """List platform components."""
        mock_argocd = MagicMock()
        mock_argocd.get_platform_status = AsyncMock(
            return_value=_mock_status_data()
        )

        with patch(ARGOCD_SVC, mock_argocd):
            resp = client_as_cpi_admin.get(
                "/v1/platform/components",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "stoa-control-plane"

    def test_list_components_error(self, client_as_cpi_admin: TestClient):
        """ArgoCD failure returns 500."""
        mock_argocd = MagicMock()
        mock_argocd.get_platform_status = AsyncMock(
            side_effect=Exception("ArgoCD unreachable")
        )

        with patch(ARGOCD_SVC, mock_argocd):
            resp = client_as_cpi_admin.get(
                "/v1/platform/components",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 500


class TestGetComponent:
    """Tests for GET /v1/platform/components/{name}."""

    def test_get_component_success(self, client_as_cpi_admin: TestClient):
        """Get a single component status."""
        mock_argocd = MagicMock()
        mock_argocd.get_application_sync_status = AsyncMock(
            return_value={
                "name": "stoa-control-plane",
                "sync_status": "Synced",
                "health_status": "Healthy",
                "revision": "abc1234def5678",
                "operation_state": {"finishedAt": "2026-02-24T10:00:00Z"},
            }
        )

        with patch(ARGOCD_SVC, mock_argocd):
            resp = client_as_cpi_admin.get(
                "/v1/platform/components/stoa-control-plane",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "stoa-control-plane"
        assert data["sync_status"] == "Synced"

    def test_get_component_not_found(self, client_as_cpi_admin: TestClient):
        """Non-existent component returns 404."""
        mock_argocd = MagicMock()
        mock_argocd.get_application_sync_status = AsyncMock(
            side_effect=Exception("not found")
        )

        with patch(ARGOCD_SVC, mock_argocd):
            resp = client_as_cpi_admin.get(
                "/v1/platform/components/nonexistent",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 404


class TestSyncComponent:
    """Tests for POST /v1/platform/components/{name}/sync."""

    def test_sync_component_success(self, client_as_cpi_admin: TestClient):
        """Trigger sync for a component (cpi-admin)."""
        mock_argocd = MagicMock()
        mock_argocd.sync_application = AsyncMock(
            return_value={"status": {"operationState": {"phase": "Running"}}}
        )

        with patch(ARGOCD_SVC, mock_argocd):
            resp = client_as_cpi_admin.post(
                "/v1/platform/components/stoa-control-plane/sync",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 200
        assert "sync triggered" in resp.json()["message"].lower()

    def test_sync_component_403_viewer(self, client_as_tenant_admin: TestClient):
        """Non-admin/devops cannot sync — require_role blocks."""
        # tenant-admin does not have cpi-admin or devops role
        # The require_role(["cpi-admin", "devops"]) dependency should block
        # Note: this depends on how require_role is implemented.
        # If tenant-admin is not in ["cpi-admin", "devops"], expect 403.
        resp = client_as_tenant_admin.post(
            "/v1/platform/components/stoa-control-plane/sync",
            headers={"Authorization": "Bearer test-token"},
        )

        assert resp.status_code == 403


class TestPlatformEvents:
    """Tests for GET /v1/platform/events."""

    def test_list_events_success(self, client_as_cpi_admin: TestClient):
        """List platform events."""
        mock_argocd = MagicMock()
        mock_argocd.get_application_events = AsyncMock(
            return_value=[
                {"id": 1, "revision": "abc1234", "deployed_at": "2026-02-24T10:00:00Z"},
            ]
        )

        with (
            patch(ARGOCD_SVC, mock_argocd),
            patch(SETTINGS, _mock_settings()),
        ):
            resp = client_as_cpi_admin.get(
                "/v1/platform/events",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_list_events_filter_by_component(self, client_as_cpi_admin: TestClient):
        """List events filtered by component name."""
        mock_argocd = MagicMock()
        mock_argocd.get_application_events = AsyncMock(return_value=[])

        with patch(ARGOCD_SVC, mock_argocd):
            resp = client_as_cpi_admin.get(
                "/v1/platform/events?component=stoa-control-plane",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 200


class TestComponentDiff:
    """Tests for GET /v1/platform/components/{name}/diff."""

    def test_diff_success(self, client_as_cpi_admin: TestClient):
        """Get diff for an OutOfSync component."""
        mock_argocd = MagicMock()
        mock_argocd.get_application_diff = AsyncMock(
            return_value={
                "total_resources": 5,
                "diff_count": 1,
                "resources": [
                    {
                        "name": "deployment-api",
                        "namespace": "stoa-system",
                        "kind": "Deployment",
                        "group": "apps",
                        "status": "OutOfSync",
                        "health": "Healthy",
                        "diff": "--- live\n+++ desired\n@@ image changed",
                    },
                ],
            }
        )

        with patch(ARGOCD_SVC, mock_argocd):
            resp = client_as_cpi_admin.get(
                "/v1/platform/components/stoa-control-plane/diff",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["application"] == "stoa-control-plane"
        assert data["diff_count"] == 1
        assert len(data["resources"]) == 1

    def test_diff_error(self, client_as_cpi_admin: TestClient):
        """Diff failure returns 500."""
        mock_argocd = MagicMock()
        mock_argocd.get_application_diff = AsyncMock(
            side_effect=Exception("ArgoCD error")
        )

        with patch(ARGOCD_SVC, mock_argocd):
            resp = client_as_cpi_admin.get(
                "/v1/platform/components/nonexistent/diff",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 500
