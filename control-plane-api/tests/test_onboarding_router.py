"""Tests for Onboarding Router — CAB-1436

Covers: /v1/me/onboarding (get progress, mark step, complete)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

REPO_PATH = "src.routers.onboarding.OnboardingRepository"
BASE = "/v1/me/onboarding"


def _mock_progress(**overrides):
    """Create a mock OnboardingProgress."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "tenant_id": "acme",
        "user_id": "tenant-admin-user-id",
        "steps_completed": {"choose_use_case": "2026-01-01T10:00:00"},
        "started_at": "2026-01-01T00:00:00",
        "completed_at": None,
        "ttftc_seconds": None,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestGetOnboardingProgress:
    """Tests for GET /v1/me/onboarding."""

    def test_get_progress_success(self, app_with_tenant_admin, mock_db_session):
        progress = _mock_progress()
        mock_repo = MagicMock()
        mock_repo.get_or_create = AsyncMock(return_value=progress)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get(BASE)

        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "acme"
        assert data["is_complete"] is False
        assert "choose_use_case" in data["steps_completed"]

    def test_get_progress_no_tenant(self, app_with_no_tenant_user, mock_db_session):
        """User without tenant gets 400."""
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get(BASE)

        assert resp.status_code == 400
        assert "no tenant" in resp.json()["detail"].lower()


class TestMarkStepCompleted:
    """Tests for PUT /v1/me/onboarding/steps/{step_name}."""

    def test_mark_step_success(self, app_with_tenant_admin, mock_db_session):
        progress = _mock_progress()
        mock_repo = MagicMock()
        mock_repo.get_or_create = AsyncMock(return_value=progress)
        mock_repo.upsert_step = AsyncMock(return_value=progress)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.put(f"{BASE}/steps/subscribe_api")

        assert resp.status_code == 200

    def test_mark_invalid_step(self, app_with_tenant_admin, mock_db_session):
        """Invalid step name returns 400."""
        with TestClient(app_with_tenant_admin) as client:
            resp = client.put(f"{BASE}/steps/invalid_step_name")

        assert resp.status_code == 400
        assert "Invalid step" in resp.json()["detail"]

    def test_mark_step_no_tenant(self, app_with_no_tenant_user, mock_db_session):
        """User without tenant gets 400."""
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.put(f"{BASE}/steps/choose_use_case")

        assert resp.status_code == 400


class TestCompleteOnboarding:
    """Tests for POST /v1/me/onboarding/complete."""

    def test_complete_success(self, app_with_tenant_admin, mock_db_session):
        progress = _mock_progress(completed_at="2026-01-01T01:00:00", ttftc_seconds=3600)
        mock_repo = MagicMock()
        mock_repo.get_or_create = AsyncMock(return_value=_mock_progress())
        mock_repo.mark_complete = AsyncMock(return_value=progress)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"{BASE}/complete")

        assert resp.status_code == 200
        data = resp.json()
        assert data["completed_at"] is not None
        assert data["ttftc_seconds"] == 3600

    def test_complete_no_tenant(self, app_with_no_tenant_user, mock_db_session):
        """User without tenant gets 400."""
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.post(f"{BASE}/complete")

        assert resp.status_code == 400
