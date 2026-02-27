"""Tests for consumer logs service — DI, time range cap, PII masking."""

import csv
import io
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.consumer_logs_service import (
    MAX_TIME_RANGE_HOURS,
    ConsumerLogsService,
)


@pytest.fixture
def mock_loki():
    loki = MagicMock()
    loki.get_recent_calls = AsyncMock(return_value=[])
    return loki


@pytest.fixture
def mock_pii_masker():
    masker = MagicMock()
    masker.mask_dict = MagicMock(side_effect=lambda d: d)  # passthrough
    return masker


@pytest.fixture
def svc(mock_loki, mock_pii_masker):
    return ConsumerLogsService(loki=mock_loki, pii_masker=mock_pii_masker)


def _make_log_entry(**overrides):
    entry = {
        "timestamp": "2026-01-01T00:00:00Z",
        "id": "req-123",
        "tool_id": "tool-1",
        "tool_name": "Weather API",
        "status": "success",
        "latency_ms": 42.5,
        "error_message": None,
    }
    entry.update(overrides)
    return entry


class TestQueryLogs:
    async def test_returns_empty_logs(self, svc, mock_loki):
        from src.schemas.logs import LogQueryParams

        params = LogQueryParams(limit=10, offset=0)
        result = await svc.query_logs("user-1", "acme", params)
        assert result.logs == []
        assert result.has_more is False

    async def test_has_more_trick(self, svc, mock_loki):
        """Service requests limit+1 to detect has_more."""
        from src.schemas.logs import LogQueryParams

        entries = [_make_log_entry(id=f"req-{i}") for i in range(6)]
        mock_loki.get_recent_calls = AsyncMock(return_value=entries)

        params = LogQueryParams(limit=5, offset=0)
        result = await svc.query_logs("user-1", "acme", params)
        assert result.has_more is True
        assert len(result.logs) == 5

    async def test_time_range_capped(self, svc, mock_loki):
        """Time range > MAX_TIME_RANGE_HOURS gets capped."""
        from src.schemas.logs import LogQueryParams

        now = datetime.now(UTC)
        params = LogQueryParams(
            limit=10,
            offset=0,
            start_time=now - timedelta(hours=48),
            end_time=now,
        )
        await svc.query_logs("user-1", "acme", params)

        call_kwargs = mock_loki.get_recent_calls.call_args[1]
        actual_range = call_kwargs["to_date"] - call_kwargs["from_date"]
        assert actual_range <= timedelta(hours=MAX_TIME_RANGE_HOURS)

    async def test_pii_masker_called(self, svc, mock_loki, mock_pii_masker):
        from src.schemas.logs import LogQueryParams

        mock_loki.get_recent_calls = AsyncMock(return_value=[_make_log_entry()])
        params = LogQueryParams(limit=10, offset=0)
        await svc.query_logs("user-1", "acme", params)
        mock_pii_masker.mask_dict.assert_called_once()


    @pytest.mark.asyncio
    async def test_status_filter_passthrough(self, svc, mock_loki):
        """Non-ALL status is forwarded to Loki."""
        from src.schemas.logs import LogQueryParams, LogStatus

        params = LogQueryParams(limit=10, offset=0, status=LogStatus.ERROR)
        await svc.query_logs("user-1", "acme", params)

        call_kwargs = mock_loki.get_recent_calls.call_args[1]
        assert call_kwargs["status"] == LogStatus.ERROR

    @pytest.mark.asyncio
    async def test_all_status_sends_none(self, svc, mock_loki):
        """ALL status is converted to None (no filter)."""
        from src.schemas.logs import LogQueryParams, LogStatus

        params = LogQueryParams(limit=10, offset=0, status=LogStatus.ALL)
        await svc.query_logs("user-1", "acme", params)

        call_kwargs = mock_loki.get_recent_calls.call_args[1]
        assert call_kwargs["status"] is None

    @pytest.mark.asyncio
    async def test_default_lookback(self, svc, mock_loki):
        """No start/end time uses DEFAULT_LOOKBACK_HOURS."""
        from src.schemas.logs import LogQueryParams
        from src.services.consumer_logs_service import DEFAULT_LOOKBACK_HOURS

        params = LogQueryParams(limit=10, offset=0)
        await svc.query_logs("user-1", "acme", params)

        call_kwargs = mock_loki.get_recent_calls.call_args[1]
        actual_range = call_kwargs["to_date"] - call_kwargs["from_date"]
        assert actual_range <= timedelta(hours=DEFAULT_LOOKBACK_HOURS + 0.01)

    @pytest.mark.asyncio
    async def test_offset_in_response(self, svc, mock_loki):
        """Offset from params is reflected in response."""
        from src.schemas.logs import LogQueryParams

        mock_loki.get_recent_calls = AsyncMock(return_value=[_make_log_entry()])
        params = LogQueryParams(limit=10, offset=5)
        result = await svc.query_logs("user-1", "acme", params)
        assert result.offset == 5

    @pytest.mark.asyncio
    async def test_query_time_ms_positive(self, svc, mock_loki):
        """Response includes a positive query_time_ms."""
        from src.schemas.logs import LogQueryParams

        mock_loki.get_recent_calls = AsyncMock(return_value=[_make_log_entry()])
        params = LogQueryParams(limit=10, offset=0)
        result = await svc.query_logs("user-1", "acme", params)
        assert result.query_time_ms >= 0


class TestMaskEntry:
    def test_field_remapping(self, svc):
        entry = _make_log_entry()
        masked = svc._mask_entry(entry)
        assert "request_id" in masked
        assert "duration_ms" in masked
        assert masked["request_id"] == "req-123"

    def test_missing_id_defaults_empty(self, svc):
        """Entry without 'id' gets empty request_id."""
        entry = _make_log_entry()
        del entry["id"]
        masked = svc._mask_entry(entry)
        assert masked["request_id"] == ""

    def test_missing_status_defaults_unknown(self, svc):
        """Entry without 'status' gets 'unknown'."""
        entry = _make_log_entry()
        del entry["status"]
        masked = svc._mask_entry(entry)
        assert masked["status"] == "unknown"


class TestExportCSV:
    async def test_csv_output(self, svc, mock_loki):
        mock_loki.get_recent_calls = AsyncMock(return_value=[_make_log_entry()])

        now = datetime.now(UTC)
        csv_str = await svc.export_csv(
            user_id="user-1",
            tenant_id="acme",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        assert rows[0] == ["timestamp", "request_id", "tool_id", "tool_name", "status", "latency_ms", "error_message"]
        assert len(rows) == 2  # header + 1 entry

    @pytest.mark.asyncio
    async def test_export_time_range_capped(self, svc, mock_loki):
        """Export with > MAX_TIME_RANGE_HOURS gets capped."""
        now = datetime.now(UTC)
        await svc.export_csv(
            user_id="user-1",
            tenant_id="acme",
            start_time=now - timedelta(hours=72),
            end_time=now,
        )

        call_kwargs = mock_loki.get_recent_calls.call_args[1]
        actual_range = call_kwargs["to_date"] - call_kwargs["from_date"]
        assert actual_range <= timedelta(hours=MAX_TIME_RANGE_HOURS)

    @pytest.mark.asyncio
    async def test_export_multiple_entries(self, svc, mock_loki):
        """CSV export handles multiple entries."""
        entries = [_make_log_entry(id=f"req-{i}") for i in range(3)]
        mock_loki.get_recent_calls = AsyncMock(return_value=entries)

        now = datetime.now(UTC)
        csv_str = await svc.export_csv(
            user_id="user-1",
            tenant_id="acme",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 4  # header + 3 entries

    @pytest.mark.asyncio
    async def test_export_empty_logs(self, svc, mock_loki):
        """CSV export with no logs returns header only."""
        mock_loki.get_recent_calls = AsyncMock(return_value=[])

        now = datetime.now(UTC)
        csv_str = await svc.export_csv(
            user_id="user-1",
            tenant_id="acme",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 1  # header only
