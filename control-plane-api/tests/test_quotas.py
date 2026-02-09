"""
Tests for Quota Enforcement — CAB-1121 Phase 4

Target: Admin quota endpoints, consumer quota endpoint, quota check dependency,
        period resets, tenant isolation.
Tests: 16 test cases
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class TestAdminQuotasRouter:
    """Test suite for Admin Quotas Router endpoints."""

    # ============== Helper Methods ==============

    def _create_mock_usage(self, data: dict) -> MagicMock:
        """Create a mock QuotaUsage object from data dict."""
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    # ============== List Quota Usage Tests ==============

    def test_list_quota_usage_success(
        self, app_with_tenant_admin, mock_db_session, sample_quota_usage_data
    ):
        """Test listing quota usage for a tenant."""
        mock_usage = self._create_mock_usage(sample_quota_usage_data)

        with patch("src.routers.quotas.QuotaUsageRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(
                return_value=([mock_usage], 1)
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/admin/quotas/acme")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            assert data["items"][0]["request_count_daily"] == 500

    def test_list_quota_usage_empty(self, app_with_tenant_admin, mock_db_session):
        """Test listing quota usage when no data exists."""
        with patch("src.routers.quotas.QuotaUsageRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(return_value=([], 0))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/admin/quotas/acme")

            assert response.status_code == 200
            assert response.json()["total"] == 0
            assert response.json()["items"] == []

    def test_list_quota_usage_403_wrong_tenant(
        self, app_with_other_tenant, mock_db_session
    ):
        """Test tenant isolation — cannot view another tenant's quotas."""
        with TestClient(app_with_other_tenant) as client:
            response = client.get("/v1/admin/quotas/acme")

        assert response.status_code == 403

    # ============== Get Consumer Quota Tests ==============

    def test_get_consumer_quota_success(
        self, app_with_tenant_admin, mock_db_session, sample_quota_usage_data
    ):
        """Test getting specific consumer quota usage."""
        mock_usage = self._create_mock_usage(sample_quota_usage_data)
        consumer_id = sample_quota_usage_data["consumer_id"]

        with patch("src.routers.quotas.QuotaUsageRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_current = AsyncMock(return_value=mock_usage)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/admin/quotas/acme/{consumer_id}"
                )

            assert response.status_code == 200
            data = response.json()
            assert data["request_count_daily"] == 500
            assert data["request_count_monthly"] == 15000

    def test_get_consumer_quota_404(self, app_with_tenant_admin, mock_db_session):
        """Test 404 when no quota usage found."""
        with patch("src.routers.quotas.QuotaUsageRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_current = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/admin/quotas/acme/{uuid4()}")

            assert response.status_code == 404

    # ============== Quota Stats Tests ==============

    def test_get_quota_stats_success(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Test aggregate quota stats."""
        stats = {
            "total_requests_today": 5000,
            "total_requests_month": 150000,
            "top_consumers": [
                {"consumer_id": uuid4(), "request_count_monthly": 50000},
            ],
            "near_limit": [],
        }

        with patch("src.routers.quotas.QuotaUsageRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_stats = AsyncMock(return_value=stats)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/admin/quotas/acme/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["total_requests_today"] == 5000
            assert data["total_requests_month"] == 150000
            assert len(data["top_consumers"]) == 1

    # ============== Reset Quota Tests ==============

    def test_reset_quota_success(
        self, app_with_tenant_admin, mock_db_session, sample_quota_usage_data
    ):
        """Test manual quota reset by admin."""
        reset_data = {
            **sample_quota_usage_data,
            "request_count_daily": 0,
            "request_count_monthly": 0,
            "bandwidth_bytes_daily": 0,
            "bandwidth_bytes_monthly": 0,
            "last_reset_at": datetime.utcnow(),
        }
        mock_usage = self._create_mock_usage(reset_data)
        consumer_id = sample_quota_usage_data["consumer_id"]

        with patch("src.routers.quotas.QuotaUsageRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.reset = AsyncMock(return_value=mock_usage)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/admin/quotas/acme/{consumer_id}/reset"
                )

            assert response.status_code == 200
            data = response.json()
            assert data["request_count_daily"] == 0
            assert data["request_count_monthly"] == 0

    def test_reset_quota_404(self, app_with_tenant_admin, mock_db_session):
        """Test reset 404 when no usage found."""
        with patch("src.routers.quotas.QuotaUsageRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.reset = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/admin/quotas/acme/{uuid4()}/reset"
                )

            assert response.status_code == 404

    # ============== CPI Admin Cross-Tenant Access ==============

    def test_cpi_admin_cross_tenant_access(
        self, app_with_cpi_admin, mock_db_session, sample_quota_usage_data
    ):
        """Test CPI admin can access any tenant's quotas."""
        mock_usage = self._create_mock_usage(sample_quota_usage_data)

        with patch("src.routers.quotas.QuotaUsageRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(
                return_value=([mock_usage], 1)
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/quotas/acme")

            assert response.status_code == 200
            assert response.json()["total"] == 1


class TestConsumerQuotaEndpoint:
    """Test suite for consumer-facing quota status endpoint."""

    def _create_mock_consumer(self, data: dict) -> MagicMock:
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    def _create_mock_usage(self, data: dict) -> MagicMock:
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    def test_get_consumer_quota_status_success(
        self,
        app_with_tenant_admin,
        mock_db_session,
        sample_consumer_data,
        sample_quota_usage_data,
    ):
        """Test consumer quota status with plan limits and usage."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        mock_usage = self._create_mock_usage(sample_quota_usage_data)
        consumer_id = sample_consumer_data["id"]

        # Mock the DB execute for subscription + plan lookup
        mock_sub_row = MagicMock()
        mock_sub_row.plan_id = str(uuid4())

        mock_plan = MagicMock()
        mock_plan.daily_request_limit = 1000
        mock_plan.monthly_request_limit = 30000

        # Build mock execute results
        mock_sub_result = MagicMock()
        mock_sub_result.first.return_value = mock_sub_row

        mock_plan_result = MagicMock()
        mock_plan_result.scalar_one_or_none.return_value = mock_plan

        mock_db_session.execute = AsyncMock(
            side_effect=[mock_sub_result, mock_plan_result]
        )

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.QuotaUsageRepository") as MockQuotaRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)

            mock_quota_repo_instance = MockQuotaRepo.return_value
            mock_quota_repo_instance.get_current = AsyncMock(return_value=mock_usage)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/consumers/acme/{consumer_id}/quota"
                )

            assert response.status_code == 200
            data = response.json()
            assert data["plan"]["daily_request_limit"] == 1000
            assert data["plan"]["monthly_request_limit"] == 30000
            assert data["usage"]["daily"] == 500
            assert data["usage"]["monthly"] == 15000
            assert data["remaining"]["daily"] == 500
            assert data["remaining"]["monthly"] == 15000
            assert "resets_at" in data

    def test_get_consumer_quota_status_no_plan(
        self,
        app_with_tenant_admin,
        mock_db_session,
        sample_consumer_data,
    ):
        """Test quota status when consumer has no plan (limits are null)."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        consumer_id = sample_consumer_data["id"]

        # No subscription found
        mock_sub_result = MagicMock()
        mock_sub_result.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_sub_result)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.QuotaUsageRepository") as MockQuotaRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)

            mock_quota_repo_instance = MockQuotaRepo.return_value
            mock_quota_repo_instance.get_current = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/consumers/acme/{consumer_id}/quota"
                )

            assert response.status_code == 200
            data = response.json()
            assert data["plan"]["daily_request_limit"] is None
            assert data["plan"]["monthly_request_limit"] is None
            assert data["usage"]["daily"] == 0
            assert data["usage"]["monthly"] == 0
            assert data["remaining"]["daily"] is None
            assert data["remaining"]["monthly"] is None

    def test_get_consumer_quota_status_404(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Test 404 when consumer not found."""
        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/consumers/acme/{uuid4()}/quota"
                )

            assert response.status_code == 404

    def test_get_consumer_quota_status_403(
        self, app_with_other_tenant, mock_db_session
    ):
        """Test tenant isolation for quota endpoint."""
        with TestClient(app_with_other_tenant) as client:
            response = client.get(
                f"/v1/consumers/acme/{uuid4()}/quota"
            )

        assert response.status_code == 403


class TestQuotaCheckDependency:
    """Test suite for quota check dependency logic."""

    def test_check_quota_under_limit(self):
        """Test quota check passes when under limit."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_db = AsyncMock()
        consumer_id = uuid4()

        mock_usage = MagicMock()
        mock_usage.request_count_daily = 100
        mock_usage.request_count_monthly = 5000

        with patch("src.dependencies.quota._get_plan_limits", new_callable=AsyncMock) as mock_limits, \
             patch("src.dependencies.quota.QuotaUsageRepository") as MockRepo:
            mock_limits.return_value = {
                "daily_request_limit": 1000,
                "monthly_request_limit": 30000,
            }
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_or_create = AsyncMock(return_value=mock_usage)
            mock_repo_instance.increment = AsyncMock()

            from src.dependencies.quota import check_quota
            # Should not raise
            asyncio.get_event_loop().run_until_complete(
                check_quota(consumer_id, "acme", mock_db)
            )

            mock_repo_instance.increment.assert_called_once()

    def test_check_quota_daily_exceeded(self):
        """Test quota check raises 429 when daily limit exceeded."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        import pytest
        from fastapi import HTTPException

        mock_db = AsyncMock()
        consumer_id = uuid4()

        mock_usage = MagicMock()
        mock_usage.request_count_daily = 1000
        mock_usage.request_count_monthly = 5000

        with patch("src.dependencies.quota._get_plan_limits", new_callable=AsyncMock) as mock_limits, \
             patch("src.dependencies.quota.QuotaUsageRepository") as MockRepo:
            mock_limits.return_value = {
                "daily_request_limit": 1000,
                "monthly_request_limit": 30000,
            }
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_or_create = AsyncMock(return_value=mock_usage)

            from src.dependencies.quota import check_quota

            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    check_quota(consumer_id, "acme", mock_db)
                )
            assert exc_info.value.status_code == 429
            assert "Retry-After" in exc_info.value.headers

    def test_check_quota_monthly_exceeded(self):
        """Test quota check raises 429 when monthly limit exceeded."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        import pytest
        from fastapi import HTTPException

        mock_db = AsyncMock()
        consumer_id = uuid4()

        mock_usage = MagicMock()
        mock_usage.request_count_daily = 100
        mock_usage.request_count_monthly = 30000

        with patch("src.dependencies.quota._get_plan_limits", new_callable=AsyncMock) as mock_limits, \
             patch("src.dependencies.quota.QuotaUsageRepository") as MockRepo:
            mock_limits.return_value = {
                "daily_request_limit": 1000,
                "monthly_request_limit": 30000,
            }
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_or_create = AsyncMock(return_value=mock_usage)

            from src.dependencies.quota import check_quota

            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    check_quota(consumer_id, "acme", mock_db)
                )
            assert exc_info.value.status_code == 429

    def test_check_quota_no_plan(self):
        """Test quota check passes when no plan is attached."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        mock_db = AsyncMock()
        consumer_id = uuid4()

        with patch("src.dependencies.quota._get_plan_limits", new_callable=AsyncMock) as mock_limits:
            mock_limits.return_value = None

            from src.dependencies.quota import check_quota
            # Should not raise — no enforcement when no plan
            asyncio.get_event_loop().run_until_complete(
                check_quota(consumer_id, "acme", mock_db)
            )
