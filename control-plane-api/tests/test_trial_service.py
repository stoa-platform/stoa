"""Tests for trial limits enforcement — CAB-1549.

Covers:
- Trial expiry check (30d + 1d grace)
- API creation limit (default 3)
- Trial status/warning
- Integration with create_api endpoint
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.services.trial_service import (
    TRIAL_MAX_APIS,
    TRIAL_MAX_DAILY_REQUESTS,
    check_trial_api_limit,
    check_trial_expiry,
    get_trial_status,
)

# ============== Helpers ==============


def _trial_settings(days_ago: int = 0, max_apis: int = TRIAL_MAX_APIS, **overrides) -> dict:
    """Build trial tenant settings with trial started N days ago."""
    started = datetime.now(UTC) - timedelta(days=days_ago)
    settings = {
        "is_trial": True,
        "trial_started_at": started.isoformat(),
        "max_apis": max_apis,
        "max_daily_requests": TRIAL_MAX_DAILY_REQUESTS,
    }
    settings.update(overrides)
    return settings


# ============== check_trial_expiry ==============


class TestCheckTrialExpiry:
    """Tests for check_trial_expiry()."""

    def test_noop_for_non_trial(self):
        """Non-trial tenants are not subject to expiry check."""
        check_trial_expiry({})  # No exception
        check_trial_expiry({"is_trial": False})  # No exception

    def test_noop_without_started_at(self):
        """Trial without started_at is not enforced."""
        check_trial_expiry({"is_trial": True})  # No exception

    def test_active_trial_passes(self):
        """Trial started 10 days ago passes."""
        settings = _trial_settings(days_ago=10)
        check_trial_expiry(settings)  # No exception

    def test_day_30_passes(self):
        """Trial on day 30 (last day) still passes."""
        settings = _trial_settings(days_ago=30)
        check_trial_expiry(settings)  # No exception (grace period)

    def test_day_31_passes_grace(self):
        """Trial on day 31 (grace day) still passes."""
        settings = _trial_settings(days_ago=31)
        check_trial_expiry(settings)  # No exception (within grace)

    def test_day_32_raises_402(self):
        """Trial on day 32 (past grace) raises 402."""
        settings = _trial_settings(days_ago=32)
        with pytest.raises(HTTPException) as exc_info:
            check_trial_expiry(settings)
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail["error"] == "trial_expired"

    def test_expired_trial_detail_includes_dates(self):
        """Expired trial error includes start and expiry dates."""
        settings = _trial_settings(days_ago=60)
        with pytest.raises(HTTPException) as exc_info:
            check_trial_expiry(settings)
        detail = exc_info.value.detail
        assert "trial_started_at" in detail
        assert "expired_at" in detail

    def test_naive_datetime_handled(self):
        """Naive datetime (no timezone) is treated as UTC."""
        started = datetime.utcnow() - timedelta(days=32)
        settings = {
            "is_trial": True,
            "trial_started_at": started.isoformat(),  # No +00:00 suffix
        }
        with pytest.raises(HTTPException) as exc_info:
            check_trial_expiry(settings)
        assert exc_info.value.status_code == 402


# ============== check_trial_api_limit ==============


class TestCheckTrialApiLimit:
    """Tests for check_trial_api_limit()."""

    def test_noop_for_non_trial(self):
        """Non-trial tenants have no API limit."""
        check_trial_api_limit({}, current_api_count=100)  # No exception

    def test_under_limit_passes(self):
        """Trial with 2 APIs (limit 3) can create more."""
        settings = _trial_settings()
        check_trial_api_limit(settings, current_api_count=2)  # No exception

    def test_zero_apis_passes(self):
        """Trial with 0 APIs can create."""
        settings = _trial_settings()
        check_trial_api_limit(settings, current_api_count=0)  # No exception

    def test_at_limit_raises_403(self):
        """Trial with 3 APIs (limit 3) cannot create more."""
        settings = _trial_settings()
        with pytest.raises(HTTPException) as exc_info:
            check_trial_api_limit(settings, current_api_count=3)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "trial_api_limit"
        assert exc_info.value.detail["limit"] == TRIAL_MAX_APIS
        assert exc_info.value.detail["current"] == 3

    def test_over_limit_raises_403(self):
        """Trial with 5 APIs (limit 3) cannot create more."""
        settings = _trial_settings()
        with pytest.raises(HTTPException) as exc_info:
            check_trial_api_limit(settings, current_api_count=5)
        assert exc_info.value.status_code == 403

    def test_custom_limit_respected(self):
        """Custom max_apis in settings is respected."""
        settings = _trial_settings(max_apis=5)
        check_trial_api_limit(settings, current_api_count=4)  # No exception

        with pytest.raises(HTTPException):
            check_trial_api_limit(settings, current_api_count=5)

    def test_default_limit_when_not_set(self):
        """Default TRIAL_MAX_APIS is used when max_apis not in settings."""
        settings = {"is_trial": True}  # No max_apis key
        check_trial_api_limit(settings, current_api_count=TRIAL_MAX_APIS - 1)  # OK
        with pytest.raises(HTTPException):
            check_trial_api_limit(settings, current_api_count=TRIAL_MAX_APIS)


# ============== get_trial_status ==============


class TestGetTrialStatus:
    """Tests for get_trial_status()."""

    def test_returns_none_for_non_trial(self):
        """Non-trial tenants return None."""
        assert get_trial_status({}) is None
        assert get_trial_status({"is_trial": False}) is None

    def test_returns_status_for_active_trial(self):
        """Active trial returns status dict."""
        settings = _trial_settings(days_ago=10)
        status = get_trial_status(settings)
        assert status is not None
        assert status["is_trial"] is True
        assert status["days_elapsed"] == 10
        assert status["days_remaining"] == 20
        assert "expires_at" in status

    def test_warning_at_day_25(self):
        """Warning flag set when trial is at day 25+."""
        settings = _trial_settings(days_ago=25)
        status = get_trial_status(settings)
        assert status["warning"] == "trial_expiring_soon"

    def test_no_warning_at_day_24(self):
        """No warning flag before day 25."""
        settings = _trial_settings(days_ago=24)
        status = get_trial_status(settings)
        assert "warning" not in status

    def test_expired_flag_set(self):
        """Expired flag set after grace period."""
        settings = _trial_settings(days_ago=32)
        status = get_trial_status(settings)
        assert status.get("expired") is True

    def test_includes_limits(self):
        """Status includes configured limits."""
        settings = _trial_settings(max_apis=5)
        status = get_trial_status(settings)
        assert status["max_apis"] == 5
        assert status["max_daily_requests"] == TRIAL_MAX_DAILY_REQUESTS

    def test_missing_started_at(self):
        """Trial with missing started_at returns warning."""
        settings = {"is_trial": True}
        status = get_trial_status(settings)
        assert status is not None
        assert "warning" in status


# ============== Integration: create_api with trial limits ==============


TENANT_PATH = "src.routers.apis.TenantRepository"
GIT_PATH = "src.routers.apis.git_service"
KAFKA_PATH = "src.routers.apis.kafka_service"

API_PAYLOAD = {
    "name": "test-api",
    "display_name": "Test API",
    "backend_url": "https://backend.example.com",
}


def _mock_tenant(settings: dict | None = None):
    """Create a mock Tenant."""
    mock = MagicMock()
    mock.id = "acme"
    mock.settings = settings or {}
    return mock


class TestCreateApiTrialLimits:
    """Integration tests: create_api endpoint with trial limits."""

    def test_non_trial_tenant_no_limit(self, client_as_tenant_admin):
        """Non-trial tenant can create APIs without limit."""
        tenant = _mock_tenant(settings={"is_trial": False})
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(TENANT_PATH) as MockRepo,
            patch(GIT_PATH) as mock_git,
            patch(KAFKA_PATH) as mock_kafka,
        ):
            MockRepo.return_value = mock_repo
            mock_git.list_apis = AsyncMock(return_value=[{}, {}, {}, {}, {}])  # 5 APIs
            mock_git.create_api = AsyncMock()
            mock_kafka.emit_api_created = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()
            resp = client_as_tenant_admin.post("/v1/tenants/acme/apis", json=API_PAYLOAD)

        assert resp.status_code == 200

    def test_trial_tenant_under_limit_ok(self, client_as_tenant_admin):
        """Trial tenant under API limit can create."""
        tenant = _mock_tenant(settings=_trial_settings(days_ago=5))
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(TENANT_PATH) as MockRepo,
            patch(GIT_PATH) as mock_git,
            patch(KAFKA_PATH) as mock_kafka,
        ):
            MockRepo.return_value = mock_repo
            mock_git.list_apis = AsyncMock(return_value=[{}, {}])  # 2 APIs < 3
            mock_git.create_api = AsyncMock()
            mock_kafka.emit_api_created = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()
            resp = client_as_tenant_admin.post("/v1/tenants/acme/apis", json=API_PAYLOAD)

        assert resp.status_code == 200

    def test_trial_tenant_at_limit_blocked(self, client_as_tenant_admin):
        """Trial tenant at API limit gets 429."""
        tenant = _mock_tenant(settings=_trial_settings(days_ago=5))
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(TENANT_PATH) as MockRepo,
            patch(GIT_PATH) as mock_git,
        ):
            MockRepo.return_value = mock_repo
            mock_git.list_apis = AsyncMock(return_value=[{}, {}, {}])  # 3 APIs = limit
            resp = client_as_tenant_admin.post("/v1/tenants/acme/apis", json=API_PAYLOAD)

        assert resp.status_code == 429

    def test_expired_trial_blocked_402(self, client_as_tenant_admin):
        """Expired trial tenant gets 402."""
        tenant = _mock_tenant(settings=_trial_settings(days_ago=60))
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        with patch(TENANT_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.post("/v1/tenants/acme/apis", json=API_PAYLOAD)

        assert resp.status_code == 402
        assert resp.json()["detail"]["error"] == "trial_expired"

    def test_tenant_not_found_proceeds(self, client_as_tenant_admin):
        """If tenant not in DB, API creation proceeds (no trial check)."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(TENANT_PATH) as MockRepo,
            patch(GIT_PATH) as mock_git,
            patch(KAFKA_PATH) as mock_kafka,
        ):
            MockRepo.return_value = mock_repo
            mock_git.create_api = AsyncMock()
            mock_kafka.emit_api_created = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()
            resp = client_as_tenant_admin.post("/v1/tenants/acme/apis", json=API_PAYLOAD)

        assert resp.status_code == 200
