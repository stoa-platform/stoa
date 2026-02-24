"""Tests for usage metering service layer (CAB-1334 Phase 1)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.schemas.usage_metering import (
    UsageDetailResponse,
    UsageSummaryListResponse,
    UsageSummaryResponse,
)
from src.services.usage_metering import UsageMeteringService

# ---------- Fixtures ----------


@pytest.fixture
def mock_session():
    """Minimal async session mock for service construction."""
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    """UsageMeteringService with mocked repository."""
    svc = UsageMeteringService(mock_session)
    svc.repo = MagicMock()
    return svc


@pytest.fixture
def sample_api_id():
    return uuid4()


@pytest.fixture
def sample_record(sample_api_id):
    """An ORM-like object (MagicMock with attributes) simulating UsageSummary."""
    now = datetime.now(tz=UTC)
    record = MagicMock()
    record.id = uuid4()
    record.tenant_id = "acme"
    record.api_id = sample_api_id
    record.consumer_id = None
    record.period = "daily"
    record.period_start = now
    record.request_count = 500
    record.error_count = 5
    record.total_latency_ms = 100000
    record.p99_latency_ms = 450
    record.total_tokens = 8000
    record.created_at = now
    record.updated_at = now
    return record


# ---------- get_summary ----------


class TestGetSummary:
    """Tests for UsageMeteringService.get_summary."""

    @pytest.mark.asyncio
    async def test_returns_paginated_list(self, service, sample_record):
        service.repo.get_usage_summary = AsyncMock(return_value=([sample_record], 1))
        result = await service.get_summary(tenant_id="acme")
        assert isinstance(result, UsageSummaryListResponse)
        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].request_count == 500

    @pytest.mark.asyncio
    async def test_empty_results(self, service):
        service.repo.get_usage_summary = AsyncMock(return_value=([], 0))
        result = await service.get_summary(tenant_id="acme")
        assert result.total == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_passes_filter_params(self, service, sample_api_id, sample_record):
        service.repo.get_usage_summary = AsyncMock(return_value=([sample_record], 1))
        await service.get_summary(
            tenant_id="acme",
            api_id=sample_api_id,
            period="monthly",
            limit=10,
            offset=5,
        )
        service.repo.get_usage_summary.assert_called_once_with(
            tenant_id="acme",
            api_id=sample_api_id,
            period="monthly",
            limit=10,
            offset=5,
        )


# ---------- get_details ----------


class TestGetDetails:
    """Tests for UsageMeteringService.get_details."""

    @pytest.mark.asyncio
    async def test_returns_detail_response(self, service, sample_api_id):
        now = datetime.now(tz=UTC)
        service.repo.get_usage_details = AsyncMock(
            return_value={
                "api_id": sample_api_id,
                "tenant_id": "acme",
                "period": "daily",
                "period_start": now,
                "total_requests": 1000,
                "total_errors": 10,
                "error_rate": 1.0,
                "avg_latency_ms": 250.0,
                "p99_latency_ms": 800,
                "total_tokens": 15000,
            }
        )
        result = await service.get_details(tenant_id="acme", api_id=sample_api_id)
        assert isinstance(result, UsageDetailResponse)
        assert result.total_requests == 1000
        assert result.error_rate == 1.0

    @pytest.mark.asyncio
    async def test_returns_none_when_no_data(self, service, sample_api_id):
        service.repo.get_usage_details = AsyncMock(return_value=None)
        result = await service.get_details(tenant_id="acme", api_id=sample_api_id)
        assert result is None


# ---------- record_usage ----------


class TestRecordUsage:
    """Tests for UsageMeteringService.record_usage."""

    @pytest.mark.asyncio
    async def test_upserts_and_returns_summary(self, service, sample_record, sample_api_id):
        service.repo.upsert_usage = AsyncMock(return_value=sample_record)
        now = datetime.now(tz=UTC)
        result = await service.record_usage(
            tenant_id="acme",
            api_id=sample_api_id,
            period="daily",
            period_start=now,
            request_count=100,
            error_count=2,
            total_latency_ms=5000,
        )
        assert isinstance(result, UsageSummaryResponse)
        assert result.request_count == 500  # from sample_record mock
        service.repo.upsert_usage.assert_called_once()
