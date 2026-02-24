"""Tests for Usage Metering Router + Service + Repository — CAB-1334 Phase 1.

Covers:
- GET /v1/metering/summary (200, RBAC, tenant isolation, period validation)
- GET /v1/metering/details (200, pagination, tool filter, RBAC)
- UsageMeteringService aggregation logic
- UsageRepository upsert + query
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

SVC_PATH = "src.routers.metering.UsageMeteringService"


# ---- Helpers ----


def _mock_summary():
    """Return a mock UsageSummary-like object."""
    return MagicMock(
        tenant_id="acme",
        period_type="daily",
        period_start=datetime(2026, 2, 1, tzinfo=UTC),
        period_end=datetime(2026, 2, 28, tzinfo=UTC),
        total_requests=1000,
        total_tokens=50000,
        total_errors=10,
        avg_latency_ms=120.5,
        tools=[],
    )


def _mock_details():
    """Return a mock UsageDetailResponse-like object."""
    return MagicMock(
        tenant_id="acme",
        tool_name=None,
        period_type="daily",
        items=[],
        total=0,
    )


# ---- Router Tests: /v1/metering/summary ----


class TestMeteringSummary:
    """Tests for GET /v1/metering/summary."""

    def test_summary_success_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        """CPI admin gets usage summary across all tenants."""
        mock_svc = MagicMock()
        mock_svc.get_summary = AsyncMock(return_value=_mock_summary())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get(
                "/v1/metering/summary?start=2026-02-01T00:00:00Z&end=2026-02-28T00:00:00Z"
            )

        assert resp.status_code == 200
        mock_svc.get_summary.assert_called_once()
        # CPI admin has no tenant_id → passes ""
        call_kwargs = mock_svc.get_summary.call_args.kwargs
        assert call_kwargs["tenant_id"] == ""

    def test_summary_success_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin gets usage summary scoped to own tenant."""
        mock_svc = MagicMock()
        mock_svc.get_summary = AsyncMock(return_value=_mock_summary())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(
                "/v1/metering/summary?start=2026-02-01T00:00:00Z&end=2026-02-28T00:00:00Z"
            )

        assert resp.status_code == 200
        call_kwargs = mock_svc.get_summary.call_args.kwargs
        assert call_kwargs["tenant_id"] == "acme"

    def test_summary_with_hourly_period(self, app_with_cpi_admin, mock_db_session):
        """Summary with hourly period_type is accepted."""
        mock_svc = MagicMock()
        mock_svc.get_summary = AsyncMock(return_value=_mock_summary())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get(
                "/v1/metering/summary"
                "?period_type=hourly&start=2026-02-01T00:00:00Z&end=2026-02-01T23:59:59Z"
            )

        assert resp.status_code == 200
        call_kwargs = mock_svc.get_summary.call_args.kwargs
        assert call_kwargs["period_type"] == "hourly"

    def test_summary_with_monthly_period(self, app_with_cpi_admin, mock_db_session):
        """Summary with monthly period_type is accepted."""
        mock_svc = MagicMock()
        mock_svc.get_summary = AsyncMock(return_value=_mock_summary())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get(
                "/v1/metering/summary"
                "?period_type=monthly&start=2026-01-01T00:00:00Z&end=2026-12-31T23:59:59Z"
            )

        assert resp.status_code == 200
        call_kwargs = mock_svc.get_summary.call_args.kwargs
        assert call_kwargs["period_type"] == "monthly"

    def test_summary_invalid_period_type(self, app_with_cpi_admin, mock_db_session):
        """Invalid period_type returns 422."""
        with TestClient(app_with_cpi_admin) as client:
            resp = client.get(
                "/v1/metering/summary"
                "?period_type=weekly&start=2026-02-01T00:00:00Z&end=2026-02-28T00:00:00Z"
            )

        assert resp.status_code == 422

    def test_summary_missing_start(self, app_with_cpi_admin, mock_db_session):
        """Missing start parameter returns 422."""
        with TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/metering/summary?end=2026-02-28T00:00:00Z")

        assert resp.status_code == 422

    def test_summary_403_viewer(self, app_with_no_tenant_user):
        """Viewer role is denied access to summary."""
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get(
                "/v1/metering/summary?start=2026-02-01T00:00:00Z&end=2026-02-28T00:00:00Z"
            )

        assert resp.status_code == 403


# ---- Router Tests: /v1/metering/details ----


class TestMeteringDetails:
    """Tests for GET /v1/metering/details."""

    def test_details_success(self, app_with_cpi_admin, mock_db_session):
        """CPI admin gets detailed usage breakdown."""
        mock_svc = MagicMock()
        mock_svc.get_details = AsyncMock(return_value=_mock_details())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get(
                "/v1/metering/details?start=2026-02-01T00:00:00Z&end=2026-02-28T00:00:00Z"
            )

        assert resp.status_code == 200
        mock_svc.get_details.assert_called_once()

    def test_details_with_tool_filter(self, app_with_cpi_admin, mock_db_session):
        """Details with tool_name filter forwards the parameter."""
        mock_svc = MagicMock()
        mock_svc.get_details = AsyncMock(return_value=_mock_details())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get(
                "/v1/metering/details"
                "?start=2026-02-01T00:00:00Z&end=2026-02-28T00:00:00Z"
                "&tool_name=crm-search"
            )

        assert resp.status_code == 200
        call_kwargs = mock_svc.get_details.call_args.kwargs
        assert call_kwargs["tool_name"] == "crm-search"

    def test_details_pagination(self, app_with_cpi_admin, mock_db_session):
        """Details with custom limit and offset."""
        mock_svc = MagicMock()
        mock_svc.get_details = AsyncMock(return_value=_mock_details())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get(
                "/v1/metering/details"
                "?start=2026-02-01T00:00:00Z&end=2026-02-28T00:00:00Z"
                "&limit=50&offset=100"
            )

        assert resp.status_code == 200
        call_kwargs = mock_svc.get_details.call_args.kwargs
        assert call_kwargs["limit"] == 50
        assert call_kwargs["offset"] == 100

    def test_details_tenant_admin_scoped(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin details are scoped to own tenant."""
        mock_svc = MagicMock()
        mock_svc.get_details = AsyncMock(return_value=_mock_details())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(
                "/v1/metering/details?start=2026-02-01T00:00:00Z&end=2026-02-28T00:00:00Z"
            )

        assert resp.status_code == 200
        call_kwargs = mock_svc.get_details.call_args.kwargs
        assert call_kwargs["tenant_id"] == "acme"

    def test_details_403_viewer(self, app_with_no_tenant_user):
        """Viewer role is denied access to details."""
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get(
                "/v1/metering/details?start=2026-02-01T00:00:00Z&end=2026-02-28T00:00:00Z"
            )

        assert resp.status_code == 403

    def test_details_invalid_period_type(self, app_with_cpi_admin, mock_db_session):
        """Invalid period_type returns 422."""
        with TestClient(app_with_cpi_admin) as client:
            resp = client.get(
                "/v1/metering/details"
                "?period_type=yearly&start=2026-02-01T00:00:00Z&end=2026-02-28T00:00:00Z"
            )

        assert resp.status_code == 422


# ---- Service Tests ----


class TestUsageMeteringService:
    """Tests for UsageMeteringService aggregation logic."""

    @pytest.mark.asyncio
    async def test_summary_aggregates_tools(self):
        """Summary groups records by tool and computes weighted avg latency."""
        from src.services.usage_service import UsageMeteringService

        mock_db = AsyncMock()
        svc = UsageMeteringService(mock_db)

        rec1 = MagicMock(
            tool_name="crm-search",
            request_count=100,
            token_count=5000,
            error_count=2,
            avg_latency_ms=120.0,
        )
        rec2 = MagicMock(
            tool_name="crm-search",
            request_count=200,
            token_count=10000,
            error_count=3,
            avg_latency_ms=150.0,
        )
        rec3 = MagicMock(
            tool_name="weather-api",
            request_count=50,
            token_count=1000,
            error_count=0,
            avg_latency_ms=80.0,
        )

        with patch.object(svc.repo, "get_usage_summary", new_callable=AsyncMock) as mock_repo:
            mock_repo.return_value = [rec1, rec2, rec3]

            result = await svc.get_summary(
                tenant_id="acme",
                period_type="daily",
                start=datetime(2026, 2, 1, tzinfo=UTC),
                end=datetime(2026, 2, 28, tzinfo=UTC),
            )

        assert result.total_requests == 350
        assert result.total_tokens == 16000
        assert result.total_errors == 5
        assert len(result.tools) == 2
        # crm-search: weighted avg = (120*100 + 150*200) / 300 = 42000/300 = 140.0
        crm = next(t for t in result.tools if t.tool_name == "crm-search")
        assert crm.request_count == 300
        assert crm.avg_latency_ms == 140.0

    @pytest.mark.asyncio
    async def test_summary_no_records(self):
        """Summary with no records returns zeros."""
        from src.services.usage_service import UsageMeteringService

        mock_db = AsyncMock()
        svc = UsageMeteringService(mock_db)

        with patch.object(svc.repo, "get_usage_summary", new_callable=AsyncMock) as mock_repo:
            mock_repo.return_value = []

            result = await svc.get_summary(
                tenant_id="acme",
                period_type="daily",
                start=datetime(2026, 2, 1, tzinfo=UTC),
                end=datetime(2026, 2, 28, tzinfo=UTC),
            )

        assert result.total_requests == 0
        assert result.total_tokens == 0
        assert result.total_errors == 0
        assert result.avg_latency_ms is None
        assert result.tools == []

    @pytest.mark.asyncio
    async def test_summary_null_latency(self):
        """Records with None latency are handled gracefully."""
        from src.services.usage_service import UsageMeteringService

        mock_db = AsyncMock()
        svc = UsageMeteringService(mock_db)

        rec = MagicMock(
            tool_name="api-tool",
            request_count=50,
            token_count=1000,
            error_count=1,
            avg_latency_ms=None,
        )

        with patch.object(svc.repo, "get_usage_summary", new_callable=AsyncMock) as mock_repo:
            mock_repo.return_value = [rec]

            result = await svc.get_summary(
                tenant_id="acme",
                period_type="daily",
                start=datetime(2026, 2, 1, tzinfo=UTC),
                end=datetime(2026, 2, 28, tzinfo=UTC),
            )

        assert result.total_requests == 50
        assert result.avg_latency_ms is None
        assert result.tools[0].avg_latency_ms is None

    @pytest.mark.asyncio
    async def test_details_delegates_to_repo(self):
        """Details endpoint delegates to repository with correct params."""
        from src.services.usage_service import UsageMeteringService

        mock_db = AsyncMock()
        svc = UsageMeteringService(mock_db)

        rec = MagicMock(
            period_start=datetime(2026, 2, 1, tzinfo=UTC),
            period_end=datetime(2026, 2, 2, tzinfo=UTC),
            request_count=100,
            token_count=5000,
            error_count=2,
            avg_latency_ms=120.0,
        )

        with patch.object(svc.repo, "get_usage_details", new_callable=AsyncMock) as mock_repo:
            mock_repo.return_value = ([rec], 1)

            result = await svc.get_details(
                tenant_id="acme",
                period_type="daily",
                start=datetime(2026, 2, 1, tzinfo=UTC),
                end=datetime(2026, 2, 28, tzinfo=UTC),
                tool_name="crm-search",
                limit=50,
                offset=0,
            )

        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].request_count == 100
        mock_repo.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_usage_delegates_to_repo(self):
        """record_usage delegates upsert to repository."""
        from src.services.usage_service import UsageMeteringService

        mock_db = AsyncMock()
        svc = UsageMeteringService(mock_db)

        with patch.object(svc.repo, "upsert_usage_record", new_callable=AsyncMock) as mock_upsert:
            await svc.record_usage(
                tenant_id="acme",
                tool_name="crm-search",
                period_start=datetime(2026, 2, 1, tzinfo=UTC),
                period_end=datetime(2026, 2, 2, tzinfo=UTC),
                period_type="daily",
                request_count=50,
                token_count=2000,
                error_count=1,
                avg_latency_ms=130.0,
            )

        mock_upsert.assert_called_once_with(
            tenant_id="acme",
            tool_name="crm-search",
            period_start=datetime(2026, 2, 1, tzinfo=UTC),
            period_end=datetime(2026, 2, 2, tzinfo=UTC),
            period_type="daily",
            request_count=50,
            token_count=2000,
            error_count=1,
            avg_latency_ms=130.0,
        )


# ---- Schema Tests ----


class TestMeteringSchemas:
    """Tests for Pydantic schema validation."""

    def test_usage_summary_valid(self):
        """UsageSummary schema accepts valid data."""
        from src.schemas.metering import UsageSummary

        summary = UsageSummary(
            tenant_id="acme",
            period_type="daily",
            period_start=datetime(2026, 2, 1, tzinfo=UTC),
            period_end=datetime(2026, 2, 28, tzinfo=UTC),
            total_requests=100,
            total_tokens=5000,
            total_errors=2,
            avg_latency_ms=120.5,
            tools=[],
        )
        assert summary.total_requests == 100

    def test_usage_detail_response_valid(self):
        """UsageDetailResponse schema accepts valid data."""
        from src.schemas.metering import UsageDetailResponse

        detail = UsageDetailResponse(
            tenant_id="acme",
            tool_name="crm-search",
            period_type="hourly",
            items=[],
            total=0,
        )
        assert detail.total == 0

    def test_tool_usage_valid(self):
        """ToolUsage schema accepts valid data."""
        from src.schemas.metering import ToolUsage

        tool = ToolUsage(
            tool_name="crm-search",
            request_count=100,
            token_count=5000,
            error_count=2,
            avg_latency_ms=120.5,
        )
        assert tool.tool_name == "crm-search"


# ---- Model Tests ----


class TestUsageRecordModel:
    """Tests for UsageRecord SQLAlchemy model."""

    def test_model_repr(self):
        """UsageRecord __repr__ returns readable string."""
        from src.models.usage import UsageRecord

        record = UsageRecord(
            tenant_id="acme",
            tool_name="crm-search",
            period_type="daily",
        )
        assert "acme" in repr(record)
        assert "crm-search" in repr(record)
        assert "daily" in repr(record)

    def test_model_columns(self):
        """UsageRecord has expected columns with correct defaults."""
        from src.models.usage import UsageRecord

        # Column defaults are applied at INSERT time, not at Python instantiation.
        # Verify columns exist and have the expected default callables.
        table = UsageRecord.__table__
        assert table.c.request_count.default.arg == 0
        assert table.c.token_count.default.arg == 0
        assert table.c.error_count.default.arg == 0
        assert table.c.avg_latency_ms.default is None
