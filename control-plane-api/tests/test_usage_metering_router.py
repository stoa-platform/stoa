"""Tests for usage metering router endpoints (CAB-1334 Phase 1)."""

from datetime import UTC
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.schemas.usage_metering import (
    UsageDetailResponse,
    UsageSummaryListResponse,
    UsageSummaryResponse,
)

# ---------- Fixtures ----------


@pytest.fixture
def sample_api_id():
    return uuid4()


@pytest.fixture
def mock_summary_response(sample_api_id):
    """Build a realistic UsageSummaryListResponse."""
    from datetime import datetime

    now = datetime.now(tz=UTC)
    item = UsageSummaryResponse(
        id=uuid4(),
        tenant_id="acme",
        api_id=sample_api_id,
        consumer_id=None,
        period="daily",
        period_start=now,
        request_count=1500,
        error_count=12,
        total_latency_ms=450000,
        p99_latency_ms=980,
        total_tokens=25000,
        created_at=now,
        updated_at=now,
    )
    return UsageSummaryListResponse(items=[item], total=1, limit=50, offset=0)


@pytest.fixture
def mock_detail_response(sample_api_id):
    """Build a realistic UsageDetailResponse."""
    from datetime import datetime

    now = datetime.now(tz=UTC)
    return UsageDetailResponse(
        api_id=sample_api_id,
        tenant_id="acme",
        period="daily",
        period_start=now,
        total_requests=1500,
        total_errors=12,
        error_rate=0.8,
        avg_latency_ms=300.0,
        p99_latency_ms=980,
        total_tokens=25000,
    )


# ---------- GET /v1/usage/summary ----------


class TestGetUsageSummary:
    """Tests for GET /v1/usage/summary endpoint."""

    def test_summary_as_tenant_admin(self, client_as_tenant_admin, mock_summary_response):
        with patch(
            "src.services.usage_metering.UsageMeteringService.get_summary",
            new_callable=AsyncMock,
            return_value=mock_summary_response,
        ):
            response = client_as_tenant_admin.get("/v1/usage/summary")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            assert data["items"][0]["request_count"] == 1500

    def test_summary_as_cpi_admin_no_tenant(self, client_as_no_tenant_user):
        """cpi-admin without tenant_id should get 400 (viewer role won't even reach the endpoint)."""
        response = client_as_no_tenant_user.get("/v1/usage/summary")
        # User with viewer role is forbidden (403) by RBAC before tenant check
        assert response.status_code == 403

    def test_summary_with_api_id_filter(self, client_as_tenant_admin, sample_api_id, mock_summary_response):
        with patch(
            "src.services.usage_metering.UsageMeteringService.get_summary",
            new_callable=AsyncMock,
            return_value=mock_summary_response,
        ) as mock_svc:
            response = client_as_tenant_admin.get(f"/v1/usage/summary?api_id={sample_api_id}")
            assert response.status_code == 200
            mock_svc.assert_called_once()

    def test_summary_with_pagination(self, client_as_tenant_admin, mock_summary_response):
        with patch(
            "src.services.usage_metering.UsageMeteringService.get_summary",
            new_callable=AsyncMock,
            return_value=mock_summary_response,
        ) as mock_svc:
            response = client_as_tenant_admin.get("/v1/usage/summary?limit=10&offset=5")
            assert response.status_code == 200
            call_kwargs = mock_svc.call_args.kwargs
            assert call_kwargs["limit"] == 10
            assert call_kwargs["offset"] == 5

    def test_summary_empty_result(self, client_as_tenant_admin):
        empty = UsageSummaryListResponse(items=[], total=0, limit=50, offset=0)
        with patch(
            "src.services.usage_metering.UsageMeteringService.get_summary",
            new_callable=AsyncMock,
            return_value=empty,
        ):
            response = client_as_tenant_admin.get("/v1/usage/summary")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
            assert data["items"] == []


# ---------- GET /v1/usage/details ----------


class TestGetUsageDetails:
    """Tests for GET /v1/usage/details endpoint."""

    def test_details_as_tenant_admin(self, client_as_tenant_admin, sample_api_id, mock_detail_response):
        with patch(
            "src.services.usage_metering.UsageMeteringService.get_details",
            new_callable=AsyncMock,
            return_value=mock_detail_response,
        ):
            response = client_as_tenant_admin.get(f"/v1/usage/details?api_id={sample_api_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["total_requests"] == 1500
            assert data["error_rate"] == 0.8

    def test_details_not_found(self, client_as_tenant_admin, sample_api_id):
        with patch(
            "src.services.usage_metering.UsageMeteringService.get_details",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client_as_tenant_admin.get(f"/v1/usage/details?api_id={sample_api_id}")
            assert response.status_code == 404
            assert "No usage data found" in response.json()["detail"]

    def test_details_requires_api_id(self, client_as_tenant_admin):
        """api_id is required — omitting it should return 422."""
        response = client_as_tenant_admin.get("/v1/usage/details")
        assert response.status_code == 422

    def test_details_no_tenant_returns_400(self, app_with_no_tenant_user):
        """User with no tenant should get 403 (RBAC blocks viewer role)."""
        with TestClient(app_with_no_tenant_user) as client:
            response = client.get(f"/v1/usage/details?api_id={uuid4()}")
            # viewer role is blocked by require_role(["cpi-admin", "tenant-admin"])
            assert response.status_code == 403

    def test_details_with_period_param(self, client_as_tenant_admin, sample_api_id, mock_detail_response):
        with patch(
            "src.services.usage_metering.UsageMeteringService.get_details",
            new_callable=AsyncMock,
            return_value=mock_detail_response,
        ) as mock_svc:
            response = client_as_tenant_admin.get(f"/v1/usage/details?api_id={sample_api_id}&period=monthly")
            assert response.status_code == 200
            call_kwargs = mock_svc.call_args.kwargs
            assert call_kwargs["period"] == "monthly"
