"""Tests for Onboarding Admin Router — CAB-1436

Covers: /v1/admin/onboarding/funnel, /v1/admin/onboarding/stalled
RBAC: cpi-admin only
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


REPO_PATH = "src.routers.onboarding_admin.OnboardingRepository"


class TestOnboardingFunnel:
    """Tests for GET /v1/admin/onboarding/funnel."""

    def test_funnel_success(self, app_with_cpi_admin, mock_db_session):
        """CPI admin gets funnel analytics."""
        mock_repo = MagicMock()
        mock_repo.get_funnel_stats = AsyncMock(
            return_value={
                "total_started": 100,
                "total_completed": 42,
                "step_counts": {
                    "choose_use_case": 80,
                    "create_app": 60,
                    "subscribe_api": 50,
                    "first_call": 42,
                },
                "avg_ttftc_seconds": 3600.0,
                "p50_ttftc_seconds": 2400.0,
                "p90_ttftc_seconds": 7200.0,
            }
        )

        with patch(REPO_PATH, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/admin/onboarding/funnel")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_started"] == 100
        assert data["total_completed"] == 42
        assert len(data["stages"]) == 5
        # First stage should be "registered" with count == total_started
        assert data["stages"][0]["stage"] == "registered"
        assert data["stages"][0]["count"] == 100
        assert data["stages"][0]["conversion_rate"] == 1.0
        # Last stage
        assert data["stages"][4]["stage"] == "first_call"
        assert data["stages"][4]["count"] == 42

    def test_funnel_403_non_admin(self, app_with_tenant_admin, mock_db_session):
        """Non cpi-admin is denied access."""
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/admin/onboarding/funnel")

        assert resp.status_code == 403

    def test_funnel_zero_started(self, app_with_cpi_admin, mock_db_session):
        """Funnel with zero users returns None conversion rates."""
        mock_repo = MagicMock()
        mock_repo.get_funnel_stats = AsyncMock(
            return_value={
                "total_started": 0,
                "total_completed": 0,
                "step_counts": {},
                "avg_ttftc_seconds": None,
                "p50_ttftc_seconds": None,
                "p90_ttftc_seconds": None,
            }
        )

        with patch(REPO_PATH, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/admin/onboarding/funnel")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_started"] == 0
        assert data["stages"][0]["conversion_rate"] is None


class TestStalledUsers:
    """Tests for GET /v1/admin/onboarding/stalled."""

    def test_stalled_users_success(self, app_with_cpi_admin, mock_db_session):
        """CPI admin gets stalled users."""
        mock_repo = MagicMock()
        mock_repo.get_stalled_users = AsyncMock(
            return_value=[
                {
                    "user_id": "user-1",
                    "tenant_id": "acme",
                    "last_step": "create_app",
                    "started_at": "2026-02-22T10:00:00",
                    "hours_stalled": 48.0,
                },
            ]
        )

        with patch(REPO_PATH, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/admin/onboarding/stalled?hours=24")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["user_id"] == "user-1"

    def test_stalled_users_custom_hours(self, app_with_cpi_admin, mock_db_session):
        """Custom hours parameter is forwarded."""
        mock_repo = MagicMock()
        mock_repo.get_stalled_users = AsyncMock(return_value=[])

        with patch(REPO_PATH, return_value=mock_repo):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/admin/onboarding/stalled?hours=72")

        assert resp.status_code == 200
        mock_repo.get_stalled_users.assert_called_once_with(stall_hours=72.0)

    def test_stalled_users_403_non_admin(self, app_with_tenant_admin, mock_db_session):
        """Non cpi-admin is denied access."""
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/admin/onboarding/stalled")

        assert resp.status_code == 403
