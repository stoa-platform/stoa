"""Tests for Quotas Router — CAB-1448

Covers: /v1/admin/quotas (list, stats, get consumer, reset).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

REPO_PATH = "src.routers.quotas.QuotaUsageRepository"
TENANT_ID = "acme"
CONSUMER_ID = uuid4()


def _make_quota_usage(**overrides):
    """Create a mock QuotaUsage model."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "consumer_id": CONSUMER_ID,
        "subscription_id": None,
        "tenant_id": TENANT_ID,
        "request_count_daily": 500,
        "request_count_monthly": 15000,
        "bandwidth_bytes_daily": 1048576,
        "bandwidth_bytes_monthly": 31457280,
        "period_start_daily": "2026-01-01",
        "period_start_monthly": "2026-01-01",
        "last_reset_at": None,
        "updated_at": "2026-01-01T00:00:00",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestListQuotaUsage:
    """Tests for GET /v1/admin/quotas/{tenant_id}."""

    def test_list_quotas_tenant_admin(self, client_as_tenant_admin):
        usage = _make_quota_usage()
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([usage], 1))

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/admin/quotas/{TENANT_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_list_quotas_cpi_admin(self, client_as_cpi_admin):
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_cpi_admin.get(f"/v1/admin/quotas/{TENANT_ID}")

        assert resp.status_code == 200

    def test_list_quotas_403_other_tenant(self, client_as_other_tenant):
        resp = client_as_other_tenant.get(f"/v1/admin/quotas/{TENANT_ID}")
        assert resp.status_code == 403

    def test_list_quotas_403_viewer(self, client_as_no_tenant_user):
        resp = client_as_no_tenant_user.get(f"/v1/admin/quotas/{TENANT_ID}")
        assert resp.status_code == 403


class TestGetQuotaStats:
    """Tests for GET /v1/admin/quotas/{tenant_id}/stats."""

    def test_stats_success(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_stats = AsyncMock(
            return_value={
                "total_requests_today": 2500,
                "total_requests_month": 75000,
                "top_consumers": [],
                "near_limit": [],
            }
        )

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/admin/quotas/{TENANT_ID}/stats")

        assert resp.status_code == 200

    def test_stats_403_other_tenant(self, client_as_other_tenant):
        resp = client_as_other_tenant.get(f"/v1/admin/quotas/{TENANT_ID}/stats")
        assert resp.status_code == 403


class TestGetConsumerQuota:
    """Tests for GET /v1/admin/quotas/{tenant_id}/{consumer_id}."""

    def test_get_consumer_quota_success(self, client_as_tenant_admin):
        usage = _make_quota_usage()
        mock_repo = MagicMock()
        mock_repo.get_current = AsyncMock(return_value=usage)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/admin/quotas/{TENANT_ID}/{CONSUMER_ID}")

        assert resp.status_code == 200

    def test_get_consumer_quota_404(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_current = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/admin/quotas/{TENANT_ID}/{CONSUMER_ID}")

        assert resp.status_code == 404


class TestResetConsumerQuota:
    """Tests for POST /v1/admin/quotas/{tenant_id}/{consumer_id}/reset."""

    def test_reset_success(self, client_as_tenant_admin):
        usage = _make_quota_usage(request_count_daily=0, request_count_monthly=0)
        mock_repo = MagicMock()
        mock_repo.reset = AsyncMock(return_value=usage)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.post(f"/v1/admin/quotas/{TENANT_ID}/{CONSUMER_ID}/reset")

        assert resp.status_code == 200

    def test_reset_404(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.reset = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.post(f"/v1/admin/quotas/{TENANT_ID}/{CONSUMER_ID}/reset")

        assert resp.status_code == 404

    def test_reset_403_other_tenant(self, client_as_other_tenant):
        resp = client_as_other_tenant.post(f"/v1/admin/quotas/{TENANT_ID}/{CONSUMER_ID}/reset")
        assert resp.status_code == 403
