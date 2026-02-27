"""Tests for usage metering service (CAB-1558)."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.usage_metering import UsageMeteringService


def _mock_summary_row(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": "acme",
        "api_id": uuid.uuid4(),
        "consumer_id": None,
        "period": "daily",
        "period_start": datetime.utcnow(),
        "request_count": 100,
        "error_count": 2,
        "total_latency_ms": 5000,
        "p99_latency_ms": 200,
        "total_tokens": 1500,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


@pytest.fixture
def svc():
    session = AsyncMock()
    with patch("src.services.usage_metering.UsageMeteringRepository") as MockRepo:
        mock_repo = AsyncMock()
        MockRepo.return_value = mock_repo
        service = UsageMeteringService(session)
        service._mock_repo = mock_repo
        yield service


class TestGetSummary:
    @pytest.mark.asyncio
    async def test_returns_paginated_list(self, svc):
        rows = [_mock_summary_row(), _mock_summary_row()]
        svc._mock_repo.get_usage_summary.return_value = (rows, 2)

        result = await svc.get_summary("acme")

        assert result.total == 2
        assert len(result.items) == 2
        assert result.limit == 50
        assert result.offset == 0

    @pytest.mark.asyncio
    async def test_with_api_filter(self, svc):
        api_id = uuid.uuid4()
        svc._mock_repo.get_usage_summary.return_value = ([], 0)

        result = await svc.get_summary("acme", api_id=api_id)

        assert result.total == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_custom_pagination(self, svc):
        svc._mock_repo.get_usage_summary.return_value = ([], 0)

        result = await svc.get_summary("acme", limit=10, offset=5)

        assert result.limit == 10
        assert result.offset == 5


class TestGetDetails:
    @pytest.mark.asyncio
    async def test_returns_detail(self, svc):
        detail = {
            "api_id": uuid.uuid4(),
            "tenant_id": "acme",
            "period": "daily",
            "period_start": datetime.utcnow(),
            "total_requests": 200,
            "total_errors": 5,
            "error_rate": 2.5,
            "avg_latency_ms": 45.0,
            "p99_latency_ms": 180,
            "total_tokens": 3000,
        }
        svc._mock_repo.get_usage_details.return_value = detail

        result = await svc.get_details("acme", detail["api_id"])

        assert result is not None
        assert result.total_requests == 200

    @pytest.mark.asyncio
    async def test_returns_none_when_no_data(self, svc):
        svc._mock_repo.get_usage_details.return_value = None

        result = await svc.get_details("acme", uuid.uuid4())

        assert result is None


class TestRecordUsage:
    @pytest.mark.asyncio
    async def test_record_success(self, svc):
        row = _mock_summary_row()
        svc._mock_repo.upsert_usage.return_value = row

        result = await svc.record_usage(
            tenant_id="acme",
            api_id=uuid.uuid4(),
            period="daily",
            period_start=datetime.utcnow(),
            request_count=10,
            error_count=1,
            total_latency_ms=500,
        )

        assert result.request_count == 100  # from mock
        svc._mock_repo.upsert_usage.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_with_tokens(self, svc):
        row = _mock_summary_row(total_tokens=500)
        svc._mock_repo.upsert_usage.return_value = row

        result = await svc.record_usage(
            tenant_id="acme",
            api_id=uuid.uuid4(),
            period="daily",
            period_start=datetime.utcnow(),
            total_tokens=500,
        )

        assert result.total_tokens == 500

    @pytest.mark.asyncio
    async def test_record_with_consumer(self, svc):
        consumer_id = uuid.uuid4()
        row = _mock_summary_row(consumer_id=consumer_id)
        svc._mock_repo.upsert_usage.return_value = row

        result = await svc.record_usage(
            tenant_id="acme",
            api_id=uuid.uuid4(),
            period="daily",
            period_start=datetime.utcnow(),
            consumer_id=consumer_id,
        )

        assert result.consumer_id == consumer_id
