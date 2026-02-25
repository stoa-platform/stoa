"""Tests for AuditService — CAB-1475 Phase 1.

Covers: record_event, list_events, get_event, export_events, get_summary, purge_before.
Uses mock AsyncSession — no real database.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.audit_event import AuditEvent
from src.services.audit_service import AuditService


@pytest.fixture
def mock_session():
    """Create a mock async DB session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def audit_service(mock_session):
    """Create AuditService with mock session."""
    return AuditService(mock_session)


class TestRecordEvent:
    """Tests for AuditService.record_event()."""

    @pytest.mark.asyncio
    async def test_record_event_success(self, audit_service, mock_session):
        result = await audit_service.record_event(
            tenant_id="acme",
            action="subscription.created",
            method="POST",
            path="/v1/subscriptions",
            resource_type="subscription",
            resource_id="sub-123",
            actor_id="user-001",
            actor_email="admin@acme.com",
            outcome="success",
            status_code=201,
            client_ip="192.168.1.1",
            correlation_id="corr-abc",
            duration_ms=42,
        )

        assert result is not None
        assert result.tenant_id == "acme"
        assert result.action == "subscription.created"
        assert result.method == "POST"
        assert result.resource_type == "subscription"
        assert result.resource_id == "sub-123"
        assert result.actor_id == "user-001"
        assert result.outcome == "success"
        assert result.duration_ms == 42
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_event_minimal_fields(self, audit_service, mock_session):
        result = await audit_service.record_event(
            tenant_id="acme",
            action="data.accessed",
            method="GET",
            path="/v1/apis",
            resource_type="api",
        )

        assert result.tenant_id == "acme"
        assert result.actor_id is None
        assert result.resource_id is None
        assert result.outcome == "success"

    @pytest.mark.asyncio
    async def test_record_event_db_error_raises(self, audit_service, mock_session):
        mock_session.flush.side_effect = Exception("DB connection lost")

        with pytest.raises(Exception, match="DB connection lost"):
            await audit_service.record_event(
                tenant_id="acme",
                action="test",
                method="POST",
                path="/test",
                resource_type="test",
            )


class TestListEvents:
    """Tests for AuditService.list_events()."""

    @pytest.mark.asyncio
    async def test_list_events_returns_tuple(self, audit_service, mock_session):
        # Mock count query
        count_result = MagicMock()
        count_result.scalar.return_value = 2

        # Mock events query
        event1 = MagicMock(spec=AuditEvent)
        event2 = MagicMock(spec=AuditEvent)
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = [event1, event2]

        mock_session.execute = AsyncMock(side_effect=[count_result, events_result])

        events, total = await audit_service.list_events("acme")

        assert total == 2
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_list_events_with_filters(self, audit_service, mock_session):
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[count_result, events_result])

        events, total = await audit_service.list_events(
            "acme",
            action="subscription.created",
            outcome="success",
            resource_type="subscription",
            actor_id="user-001",
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 12, 31, tzinfo=UTC),
            search="subscriptions",
        )

        assert total == 0
        assert events == []

    @pytest.mark.asyncio
    async def test_list_events_pagination(self, audit_service, mock_session):
        count_result = MagicMock()
        count_result.scalar.return_value = 100
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = [MagicMock()] * 10
        mock_session.execute = AsyncMock(side_effect=[count_result, events_result])

        events, total = await audit_service.list_events("acme", page=3, page_size=10)

        assert total == 100
        assert len(events) == 10


class TestGetEvent:
    """Tests for AuditService.get_event()."""

    @pytest.mark.asyncio
    async def test_get_event_found(self, audit_service, mock_session):
        event = MagicMock(spec=AuditEvent)
        event.id = "evt-123"
        result = MagicMock()
        result.scalar_one_or_none.return_value = event
        mock_session.execute = AsyncMock(return_value=result)

        found = await audit_service.get_event("evt-123")
        assert found is not None
        assert found.id == "evt-123"

    @pytest.mark.asyncio
    async def test_get_event_not_found(self, audit_service, mock_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result)

        found = await audit_service.get_event("nonexistent")
        assert found is None


class TestExportEvents:
    """Tests for AuditService.export_events()."""

    @pytest.mark.asyncio
    async def test_export_events_returns_list(self, audit_service, mock_session):
        events = [MagicMock(spec=AuditEvent) for _ in range(3)]
        result = MagicMock()
        result.scalars.return_value.all.return_value = events
        mock_session.execute = AsyncMock(return_value=result)

        exported = await audit_service.export_events("acme")
        assert len(exported) == 3

    @pytest.mark.asyncio
    async def test_export_events_with_date_range(self, audit_service, mock_session):
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result)

        exported = await audit_service.export_events(
            "acme",
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 3, 1, tzinfo=UTC),
            limit=500,
        )
        assert exported == []


class TestGetSummary:
    """Tests for AuditService.get_summary()."""

    @pytest.mark.asyncio
    async def test_get_summary_global(self, audit_service, mock_session):
        # Total count
        total_result = MagicMock()
        total_result.scalar.return_value = 50

        # 4 outcome counts
        outcome_results = []
        for count in [40, 5, 3, 2]:
            r = MagicMock()
            r.scalar.return_value = count
            outcome_results.append(r)

        # Top actions
        action_rows = [MagicMock(action="create", cnt=20), MagicMock(action="update", cnt=15)]
        action_result = MagicMock()
        action_result.__iter__ = lambda self: iter(action_rows)

        mock_session.execute = AsyncMock(
            side_effect=[total_result, *outcome_results, action_result]
        )

        summary = await audit_service.get_summary()

        assert summary["total"] == 50
        assert summary["by_outcome"]["success"] == 40
        assert summary["by_outcome"]["failure"] == 5
        assert summary["by_action"]["create"] == 20

    @pytest.mark.asyncio
    async def test_get_summary_per_tenant(self, audit_service, mock_session):
        total_result = MagicMock()
        total_result.scalar.return_value = 10

        outcome_results = [MagicMock(scalar=MagicMock(return_value=v)) for v in [8, 1, 0, 1]]
        for r, v in zip(outcome_results, [8, 1, 0, 1]):
            r.scalar.return_value = v

        action_result = MagicMock()
        action_result.__iter__ = lambda self: iter([])

        mock_session.execute = AsyncMock(
            side_effect=[total_result, *outcome_results, action_result]
        )

        summary = await audit_service.get_summary(tenant_id="acme")
        assert summary["total"] == 10


class TestPurgeBefore:
    """Tests for AuditService.purge_before()."""

    @pytest.mark.asyncio
    async def test_purge_deletes_old_events(self, audit_service, mock_session):
        result = MagicMock()
        result.rowcount = 42
        mock_session.execute = AsyncMock(return_value=result)

        count = await audit_service.purge_before(
            "acme",
            datetime.now(UTC) - timedelta(days=365),
        )

        assert count == 42
        mock_session.execute.assert_awaited_once()
