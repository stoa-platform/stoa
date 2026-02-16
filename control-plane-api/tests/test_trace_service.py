"""Tests for TraceService (CAB-1291)"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.models.traces_db import TraceStatusDB
from src.services.trace_service import TraceService, get_trace_service


def _mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _mock_trace(**kwargs):
    """Create a mock PipelineTraceDB."""
    trace = MagicMock()
    trace.id = kwargs.get("id", "trace-1")
    trace.trigger_type = kwargs.get("trigger_type", "manual")
    trace.trigger_source = kwargs.get("trigger_source", "user")
    trace.status = kwargs.get("status", TraceStatusDB.IN_PROGRESS)
    trace.steps = kwargs.get("steps", [])
    trace.created_at = kwargs.get("created_at", datetime(2026, 2, 16, 10, 0, tzinfo=UTC))
    trace.completed_at = kwargs.get("completed_at", None)
    trace.total_duration_ms = kwargs.get("total_duration_ms", None)
    trace.error_summary = kwargs.get("error_summary", None)
    trace.tenant_id = kwargs.get("tenant_id", None)
    return trace


# ── Create ──


class TestCreate:
    async def test_creates_trace(self):
        session = _mock_session()
        svc = TraceService(session)

        with patch("src.services.trace_service.PipelineTraceDB") as MockTrace:
            mock_instance = MagicMock()
            mock_instance.id = "new-id"
            MockTrace.return_value = mock_instance

            result = await svc.create("manual", "user")

        session.add.assert_called_once_with(mock_instance)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(mock_instance)
        assert result is mock_instance


# ── Get ──


class TestGet:
    async def test_found(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_trace()
        session.execute = AsyncMock(return_value=mock_result)

        svc = TraceService(session)
        trace = await svc.get("trace-1")
        assert trace is not None
        assert trace.id == "trace-1"

    async def test_not_found(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        svc = TraceService(session)
        trace = await svc.get("nonexistent")
        assert trace is None


# ── Update ──


class TestUpdate:
    async def test_commits_and_refreshes(self):
        session = _mock_session()
        svc = TraceService(session)
        trace = _mock_trace()

        result = await svc.update(trace)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(trace)
        assert result is trace


# ── Add Step ──


class TestAddStep:
    async def test_adds_step(self):
        session = _mock_session()
        svc = TraceService(session)
        trace = _mock_trace(steps=[])

        result = await svc.add_step(trace, "fetch", status="running", details={"url": "http://x"})
        session.commit.assert_awaited_once()
        # Steps should now have 1 entry
        assert len(trace.steps) == 1
        step = trace.steps[0]
        assert step["name"] == "fetch"
        assert step["status"] == "running"
        assert step["details"] == {"url": "http://x"}
        assert step["completed_at"] is None

    async def test_appends_to_existing(self):
        session = _mock_session()
        svc = TraceService(session)
        existing = [{"name": "init", "status": "done"}]
        trace = _mock_trace(steps=existing)

        await svc.add_step(trace, "process")
        assert len(trace.steps) == 2
        assert trace.steps[1]["name"] == "process"

    async def test_with_error_and_duration(self):
        session = _mock_session()
        svc = TraceService(session)
        trace = _mock_trace(steps=[])

        await svc.add_step(trace, "validate", status="failed", error="bad input", duration_ms=150)
        step = trace.steps[0]
        assert step["error"] == "bad input"
        assert step["duration_ms"] == 150


# ── Update Step ──


class TestUpdateStep:
    async def test_updates_matching_step(self):
        session = _mock_session()
        svc = TraceService(session)
        trace = _mock_trace(steps=[
            {"name": "fetch", "status": "running", "completed_at": None, "duration_ms": None, "details": None, "error": None},
        ])

        await svc.update_step(trace, "fetch", "done", duration_ms=200)
        step = trace.steps[0]
        assert step["status"] == "done"
        assert step["duration_ms"] == 200
        assert step["completed_at"] is not None

    async def test_updates_with_error(self):
        session = _mock_session()
        svc = TraceService(session)
        trace = _mock_trace(steps=[
            {"name": "process", "status": "running", "completed_at": None, "duration_ms": None, "details": None, "error": None},
        ])

        await svc.update_step(trace, "process", "failed", error="timeout", details={"retry": 3})
        step = trace.steps[0]
        assert step["status"] == "failed"
        assert step["error"] == "timeout"
        assert step["details"] == {"retry": 3}

    async def test_no_match_no_change(self):
        session = _mock_session()
        svc = TraceService(session)
        trace = _mock_trace(steps=[
            {"name": "fetch", "status": "done", "completed_at": None, "duration_ms": None, "details": None, "error": None},
        ])

        await svc.update_step(trace, "nonexistent", "done")
        assert trace.steps[0]["status"] == "done"  # unchanged


# ── Complete ──


class TestComplete:
    async def test_success(self):
        session = _mock_session()
        svc = TraceService(session)
        trace = _mock_trace(created_at=datetime(2026, 2, 16, 10, 0, tzinfo=UTC))

        result = await svc.complete(trace, TraceStatusDB.SUCCESS)
        assert trace.status == TraceStatusDB.SUCCESS
        assert trace.completed_at is not None
        assert trace.total_duration_ms is not None
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(trace)

    async def test_failure_with_error(self):
        session = _mock_session()
        svc = TraceService(session)
        trace = _mock_trace()

        await svc.complete(trace, TraceStatusDB.FAILED, error_summary="step 3 failed")
        assert trace.status == TraceStatusDB.FAILED
        assert trace.error_summary == "step 3 failed"

    async def test_no_created_at(self):
        session = _mock_session()
        svc = TraceService(session)
        trace = _mock_trace(created_at=None)

        await svc.complete(trace)
        # Should not set total_duration_ms when created_at is None
        assert trace.status == TraceStatusDB.SUCCESS


# ── List Recent ──


class TestListRecent:
    async def test_basic(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_trace(), _mock_trace(id="t2")]
        session.execute = AsyncMock(return_value=mock_result)

        svc = TraceService(session)
        traces = await svc.list_recent()
        assert len(traces) == 2

    async def test_with_filters(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        svc = TraceService(session)
        traces = await svc.list_recent(limit=10, tenant_id="acme", status=TraceStatusDB.SUCCESS)
        assert traces == []


# ── Get Stats ──


class TestGetStats:
    async def test_empty(self):
        session = _mock_session()
        # total = 0
        mock_total = MagicMock()
        mock_total.scalar.return_value = 0
        session.execute = AsyncMock(return_value=mock_total)

        svc = TraceService(session)
        stats = await svc.get_stats()
        assert stats["total"] == 0
        assert stats["by_status"] == {}
        assert stats["avg_duration_ms"] == 0
        assert stats["success_rate"] == 0

    async def test_with_data(self):
        session = _mock_session()

        # Build sequence of mock results for each execute call
        # 1. total count
        total_result = MagicMock()
        total_result.scalar.return_value = 10

        # 2-6. count by status (5 statuses: pending, in_progress, success, failed, skipped)
        status_results = []
        for count in [0, 1, 6, 2, 1]:
            r = MagicMock()
            r.scalar.return_value = count
            status_results.append(r)

        # 7. avg duration
        avg_result = MagicMock()
        avg_result.scalar.return_value = 1500.0

        session.execute = AsyncMock(
            side_effect=[total_result] + status_results + [avg_result]
        )

        svc = TraceService(session)
        stats = await svc.get_stats()
        assert stats["total"] == 10
        assert stats["avg_duration_ms"] == 1500
        assert stats["success_rate"] > 0


# ── Dependency helper ──


class TestGetTraceService:
    async def test_returns_service(self):
        session = AsyncMock()
        svc = await get_trace_service(session)
        assert isinstance(svc, TraceService)
        assert svc.session is session
