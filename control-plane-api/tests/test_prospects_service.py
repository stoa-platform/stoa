"""Unit tests for prospects_service (CAB-911).

Covers: list_prospects, get_prospect_detail, _calculate_metrics,
get_metrics, export_prospects_csv.

All DB / HTTP calls are mocked — no real infrastructure needed.
asyncio_mode = "auto" (configured in pyproject.toml) so async methods
work without @pytest.mark.asyncio.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.prospects_service import (
    _calculate_metrics,
    export_prospects_csv,
    get_metrics,
    get_prospect_detail,
    list_prospects,
)

# =============================================================================
# Shared Factories
# =============================================================================


def _make_invite(**overrides) -> MagicMock:
    """Build a mock Invite ORM object."""
    obj = MagicMock()
    obj.id = overrides.get("id", uuid.uuid4())
    obj.email = overrides.get("email", "prospect@example.com")
    obj.company = overrides.get("company", "Acme Corp")
    obj.token = overrides.get("token", "tok-abc123")
    obj.source = overrides.get("source", "linkedin")
    obj.status = overrides.get("status", "opened")
    obj.created_at = overrides.get("created_at", datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC))
    obj.opened_at = overrides.get("opened_at", datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC))
    obj.expires_at = overrides.get("expires_at", datetime(2026, 2, 1, 10, 0, 0, tzinfo=UTC))
    return obj


def _make_event(event_type: str = "tool_called", **overrides) -> MagicMock:
    """Build a mock ProspectEvent ORM object."""
    obj = MagicMock()
    obj.id = overrides.get("id", uuid.uuid4())
    obj.invite_id = overrides.get("invite_id", uuid.uuid4())
    obj.event_type = event_type
    obj.event_data = overrides.get("event_data", {})
    obj.timestamp = overrides.get("timestamp", datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
    return obj


def _make_feedback(**overrides) -> MagicMock:
    """Build a mock ProspectFeedback ORM object."""
    obj = MagicMock()
    obj.id = overrides.get("id", uuid.uuid4())
    obj.invite_id = overrides.get("invite_id", uuid.uuid4())
    obj.nps_score = overrides.get("nps_score", 8)
    obj.comment = overrides.get("comment", "Great experience!")
    obj.created_at = overrides.get("created_at", datetime(2026, 1, 2, 9, 0, 0, tzinfo=UTC))
    return obj


def _db_rows(rows: list) -> MagicMock:
    """Mock db.execute() result whose .all() returns a list of tuples."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _db_scalar(value) -> MagicMock:
    """Mock db.execute() result whose .scalar_one() returns a scalar."""
    result = MagicMock()
    result.scalar_one.return_value = value
    result.first.return_value = value
    return result


def _db_scalars(items: list) -> MagicMock:
    """Mock db.execute() result whose .scalars().all() returns a list."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars_mock
    return result


# =============================================================================
# TestListProspects
# =============================================================================


class TestListProspects:
    """Tests for list_prospects()."""

    async def test_returns_response_with_data_and_meta(self) -> None:
        """Happy path: returns ProspectListResponse with matching counts."""
        db = AsyncMock()
        invite = _make_invite()
        # side_effect: first execute = count query, second = data query
        row = (invite, 8, "Good", datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC), datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC), 5)
        db.execute.side_effect = [
            _db_scalar(1),
            _db_rows([row]),
        ]

        result = await list_prospects(db)

        assert result.meta.total == 1
        assert result.meta.page == 1
        assert len(result.data) == 1
        assert result.data[0].email == invite.email
        assert result.data[0].company == invite.company

    async def test_returns_empty_list_when_no_rows(self) -> None:
        """Empty database returns empty data list."""
        db = AsyncMock()
        db.execute.side_effect = [
            _db_scalar(0),
            _db_rows([]),
        ]

        result = await list_prospects(db)

        assert result.meta.total == 0
        assert result.data == []

    async def test_pagination_meta_is_correct(self) -> None:
        """Pagination meta reflects page and limit parameters."""
        db = AsyncMock()
        db.execute.side_effect = [
            _db_scalar(50),
            _db_rows([]),
        ]

        result = await list_prospects(db, page=3, limit=10)

        assert result.meta.page == 3
        assert result.meta.limit == 10
        assert result.meta.total == 50

    async def test_event_count_defaults_to_zero_when_null(self) -> None:
        """Null event_count in row is normalised to 0."""
        db = AsyncMock()
        invite = _make_invite()
        row = (invite, None, None, None, None, None)  # event_count is None
        db.execute.side_effect = [
            _db_scalar(1),
            _db_rows([row]),
        ]

        result = await list_prospects(db)

        assert result.data[0].total_events == 0

    async def test_nps_promoter_categorisation(self) -> None:
        """NPS score >= 9 is categorised as 'promoter'."""
        db = AsyncMock()
        invite = _make_invite()
        row = (invite, 9, None, None, None, 0)
        db.execute.side_effect = [
            _db_scalar(1),
            _db_rows([row]),
        ]

        result = await list_prospects(db)

        assert result.data[0].nps_score == 9
        assert result.data[0].nps_category == "promoter"

    async def test_nps_passive_categorisation(self) -> None:
        """NPS score 7 or 8 is categorised as 'passive'."""
        db = AsyncMock()
        invite = _make_invite()
        row = (invite, 7, None, None, None, 0)
        db.execute.side_effect = [
            _db_scalar(1),
            _db_rows([row]),
        ]

        result = await list_prospects(db)

        assert result.data[0].nps_category == "passive"

    async def test_nps_detractor_categorisation(self) -> None:
        """NPS score < 7 is categorised as 'detractor'."""
        db = AsyncMock()
        invite = _make_invite()
        row = (invite, 4, None, None, None, 0)
        db.execute.side_effect = [
            _db_scalar(1),
            _db_rows([row]),
        ]

        result = await list_prospects(db)

        assert result.data[0].nps_category == "detractor"

    async def test_no_nps_category_when_score_is_none(self) -> None:
        """Null NPS score produces null nps_category."""
        db = AsyncMock()
        invite = _make_invite()
        row = (invite, None, None, None, None, 0)
        db.execute.side_effect = [
            _db_scalar(1),
            _db_rows([row]),
        ]

        result = await list_prospects(db)

        assert result.data[0].nps_score is None
        assert result.data[0].nps_category is None

    async def test_time_to_first_tool_calculated(self) -> None:
        """time_to_first_tool_seconds is computed from opened_at to first_tool_at."""
        db = AsyncMock()
        opened_at = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
        first_tool_at = datetime(2026, 1, 1, 11, 0, 30, tzinfo=UTC)  # 30 seconds later
        invite = _make_invite(opened_at=opened_at)
        row = (invite, None, None, None, first_tool_at, 1)
        db.execute.side_effect = [
            _db_scalar(1),
            _db_rows([row]),
        ]

        result = await list_prospects(db)

        assert result.data[0].time_to_first_tool_seconds == pytest.approx(30.0)

    async def test_time_to_first_tool_none_when_no_opened_at(self) -> None:
        """No time_to_first_tool when invite has not been opened."""
        db = AsyncMock()
        invite = _make_invite(opened_at=None)
        first_tool_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        row = (invite, None, None, None, first_tool_at, 1)
        db.execute.side_effect = [
            _db_scalar(1),
            _db_rows([row]),
        ]

        result = await list_prospects(db)

        assert result.data[0].time_to_first_tool_seconds is None

    async def test_time_to_first_tool_none_when_no_tool_event(self) -> None:
        """No time_to_first_tool when first_tool_at subquery returned null."""
        db = AsyncMock()
        invite = _make_invite()
        row = (invite, None, None, None, None, 0)
        db.execute.side_effect = [
            _db_scalar(1),
            _db_rows([row]),
        ]

        result = await list_prospects(db)

        assert result.data[0].time_to_first_tool_seconds is None

    async def test_multiple_rows_returned(self) -> None:
        """Multiple rows are all included in the data list."""
        db = AsyncMock()
        invites = [_make_invite(email=f"user{i}@example.com") for i in range(3)]
        rows = [(inv, None, None, None, None, 0) for inv in invites]
        db.execute.side_effect = [
            _db_scalar(3),
            _db_rows(rows),
        ]

        result = await list_prospects(db)

        assert len(result.data) == 3

    async def test_company_filter_appends_where_clause(self) -> None:
        """Passing company= causes two db.execute calls (count + data)."""
        db = AsyncMock()
        db.execute.side_effect = [
            _db_scalar(0),
            _db_rows([]),
        ]

        await list_prospects(db, company="Acme")

        # Just verify both queries were issued
        assert db.execute.call_count == 2

    async def test_status_filter_appends_where_clause(self) -> None:
        """Passing status= causes two db.execute calls."""
        db = AsyncMock()
        db.execute.side_effect = [
            _db_scalar(0),
            _db_rows([]),
        ]

        await list_prospects(db, status="converted")

        assert db.execute.call_count == 2

    async def test_date_from_filter_appends_where_clause(self) -> None:
        """Passing date_from= causes two db.execute calls."""
        db = AsyncMock()
        db.execute.side_effect = [
            _db_scalar(0),
            _db_rows([]),
        ]

        await list_prospects(db, date_from=datetime(2026, 1, 1, tzinfo=UTC))

        assert db.execute.call_count == 2

    async def test_date_to_filter_appends_where_clause(self) -> None:
        """Passing date_to= causes two db.execute calls."""
        db = AsyncMock()
        db.execute.side_effect = [
            _db_scalar(0),
            _db_rows([]),
        ]

        await list_prospects(db, date_to=datetime(2026, 3, 1, tzinfo=UTC))

        assert db.execute.call_count == 2

    async def test_all_filters_combined(self) -> None:
        """All filters together still produce valid (count, data) queries."""
        db = AsyncMock()
        db.execute.side_effect = [
            _db_scalar(0),
            _db_rows([]),
        ]

        await list_prospects(
            db,
            company="Acme",
            status="converted",
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to=datetime(2026, 3, 1, tzinfo=UTC),
        )

        assert db.execute.call_count == 2


# =============================================================================
# TestGetProspectDetail
# =============================================================================


class TestGetProspectDetail:
    """Tests for get_prospect_detail()."""

    async def test_returns_none_when_invite_not_found(self) -> None:
        """Unknown invite_id returns None."""
        db = AsyncMock()
        first_result = MagicMock()
        first_result.first.return_value = None
        db.execute.return_value = first_result

        result = await get_prospect_detail(db, uuid.uuid4())

        assert result is None

    async def test_returns_detail_for_known_invite(self) -> None:
        """Known invite returns a ProspectDetail with correct fields."""
        db = AsyncMock()
        invite = _make_invite()
        feedback = _make_feedback(nps_score=9, comment="Excellent")

        invite_result = MagicMock()
        invite_result.first.return_value = (invite, feedback)
        events_result = _db_scalars([])

        db.execute.side_effect = [invite_result, events_result]

        result = await get_prospect_detail(db, invite.id)

        assert result is not None
        assert result.id == invite.id
        assert result.email == invite.email
        assert result.company == invite.company

    async def test_nps_promoter_from_feedback(self) -> None:
        """NPS score 9 produces category 'promoter' in detail."""
        db = AsyncMock()
        invite = _make_invite()
        feedback = _make_feedback(nps_score=9)

        invite_result = MagicMock()
        invite_result.first.return_value = (invite, feedback)
        db.execute.side_effect = [invite_result, _db_scalars([])]

        result = await get_prospect_detail(db, invite.id)

        assert result.nps_score == 9
        assert result.nps_category == "promoter"

    async def test_nps_passive_from_feedback(self) -> None:
        """NPS score 7 produces category 'passive'."""
        db = AsyncMock()
        invite = _make_invite()
        feedback = _make_feedback(nps_score=7)

        invite_result = MagicMock()
        invite_result.first.return_value = (invite, feedback)
        db.execute.side_effect = [invite_result, _db_scalars([])]

        result = await get_prospect_detail(db, invite.id)

        assert result.nps_category == "passive"

    async def test_nps_detractor_from_feedback(self) -> None:
        """NPS score 4 produces category 'detractor'."""
        db = AsyncMock()
        invite = _make_invite()
        feedback = _make_feedback(nps_score=4)

        invite_result = MagicMock()
        invite_result.first.return_value = (invite, feedback)
        db.execute.side_effect = [invite_result, _db_scalars([])]

        result = await get_prospect_detail(db, invite.id)

        assert result.nps_category == "detractor"

    async def test_no_nps_when_feedback_is_none(self) -> None:
        """No feedback row yields None nps_score and None nps_category."""
        db = AsyncMock()
        invite = _make_invite()

        invite_result = MagicMock()
        invite_result.first.return_value = (invite, None)
        db.execute.side_effect = [invite_result, _db_scalars([])]

        result = await get_prospect_detail(db, invite.id)

        assert result.nps_score is None
        assert result.nps_category is None
        assert result.nps_comment is None

    async def test_timeline_contains_all_events(self) -> None:
        """All fetched events appear in the timeline list."""
        db = AsyncMock()
        invite = _make_invite()
        events = [_make_event("page_viewed"), _make_event("tool_called")]

        invite_result = MagicMock()
        invite_result.first.return_value = (invite, None)
        db.execute.side_effect = [invite_result, _db_scalars(events)]

        result = await get_prospect_detail(db, invite.id)

        assert len(result.timeline) == 2

    async def test_errors_list_contains_only_error_events(self) -> None:
        """Error events appear in both timeline and errors list."""
        db = AsyncMock()
        invite = _make_invite()
        error_event = _make_event("error_encountered")
        tool_event = _make_event("tool_called")

        invite_result = MagicMock()
        invite_result.first.return_value = (invite, None)
        db.execute.side_effect = [invite_result, _db_scalars([error_event, tool_event])]

        result = await get_prospect_detail(db, invite.id)

        assert len(result.errors) == 1
        assert result.errors[0].event_type == "error_encountered"
        assert len(result.timeline) == 2

    async def test_first_tool_call_flagged_in_timeline(self) -> None:
        """The oldest tool_called event is flagged as is_first_tool_call."""
        db = AsyncMock()
        invite = _make_invite()

        early_id = uuid.uuid4()
        late_id = uuid.uuid4()
        # Events are returned newest-first (desc order)
        late_event = _make_event("tool_called", id=late_id, timestamp=datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC))
        early_event = _make_event("tool_called", id=early_id, timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))

        invite_result = MagicMock()
        invite_result.first.return_value = (invite, None)
        db.execute.side_effect = [invite_result, _db_scalars([late_event, early_event])]

        result = await get_prospect_detail(db, invite.id)

        # early_event is the first tool call (smallest timestamp)
        first_flagged = [e for e in result.timeline if e.is_first_tool_call]
        assert len(first_flagged) == 1
        assert first_flagged[0].id == early_id

    async def test_no_first_tool_flag_when_no_tool_events(self) -> None:
        """No tool_called events means no event is flagged as first tool call."""
        db = AsyncMock()
        invite = _make_invite()
        events = [_make_event("page_viewed"), _make_event("page_viewed")]

        invite_result = MagicMock()
        invite_result.first.return_value = (invite, None)
        db.execute.side_effect = [invite_result, _db_scalars(events)]

        result = await get_prospect_detail(db, invite.id)

        assert all(not e.is_first_tool_call for e in result.timeline)

    async def test_empty_timeline_when_no_events(self) -> None:
        """No events returns empty timeline and errors."""
        db = AsyncMock()
        invite = _make_invite()

        invite_result = MagicMock()
        invite_result.first.return_value = (invite, None)
        db.execute.side_effect = [invite_result, _db_scalars([])]

        result = await get_prospect_detail(db, invite.id)

        assert result.timeline == []
        assert result.errors == []


# =============================================================================
# TestCalculateMetrics
# =============================================================================


class TestCalculateMetrics:
    """Tests for _calculate_metrics()."""

    async def test_all_zero_for_empty_events(self) -> None:
        """No events yields all-zero counts and None timings."""
        db = AsyncMock()
        invite = _make_invite()

        metrics = await _calculate_metrics(db, invite, [])

        assert metrics.tools_called_count == 0
        assert metrics.pages_viewed_count == 0
        assert metrics.errors_count == 0
        assert metrics.session_duration_seconds is None

    async def test_counts_tool_called_events(self) -> None:
        """tool_called events are counted correctly."""
        db = AsyncMock()
        invite = _make_invite()
        events = [_make_event("tool_called"), _make_event("tool_called"), _make_event("page_viewed")]

        metrics = await _calculate_metrics(db, invite, events)

        assert metrics.tools_called_count == 2

    async def test_counts_page_viewed_events(self) -> None:
        """page_viewed events are counted correctly."""
        db = AsyncMock()
        invite = _make_invite()
        events = [_make_event("page_viewed"), _make_event("page_viewed")]

        metrics = await _calculate_metrics(db, invite, events)

        assert metrics.pages_viewed_count == 2

    async def test_counts_error_encountered_events(self) -> None:
        """error_encountered events are counted correctly."""
        db = AsyncMock()
        invite = _make_invite()
        events = [_make_event("error_encountered")]

        metrics = await _calculate_metrics(db, invite, events)

        assert metrics.errors_count == 1

    async def test_time_to_open_calculated_from_invite(self) -> None:
        """time_to_open_seconds = opened_at - created_at."""
        db = AsyncMock()
        created_at = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        opened_at = datetime(2026, 1, 1, 10, 1, 0, tzinfo=UTC)  # 60s later
        invite = _make_invite(created_at=created_at, opened_at=opened_at)

        metrics = await _calculate_metrics(db, invite, [])

        assert metrics.time_to_open_seconds == pytest.approx(60.0)

    async def test_time_to_open_none_when_not_opened(self) -> None:
        """time_to_open_seconds is None when invite has no opened_at."""
        db = AsyncMock()
        invite = _make_invite(opened_at=None)

        metrics = await _calculate_metrics(db, invite, [])

        assert metrics.time_to_open_seconds is None

    async def test_time_to_first_tool_calculated(self) -> None:
        """time_to_first_tool_seconds = first tool timestamp - opened_at."""
        db = AsyncMock()
        opened_at = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
        tool_ts = datetime(2026, 1, 1, 11, 0, 45, tzinfo=UTC)  # 45s after open
        invite = _make_invite(opened_at=opened_at)
        event = _make_event("tool_called", timestamp=tool_ts)

        metrics = await _calculate_metrics(db, invite, [event])

        assert metrics.time_to_first_tool_seconds == pytest.approx(45.0)

    async def test_time_to_first_tool_none_when_no_tool_events(self) -> None:
        """time_to_first_tool_seconds is None with no tool_called events."""
        db = AsyncMock()
        invite = _make_invite()
        events = [_make_event("page_viewed")]

        metrics = await _calculate_metrics(db, invite, events)

        assert metrics.time_to_first_tool_seconds is None

    async def test_session_duration_computed_from_event_span(self) -> None:
        """session_duration_seconds = last_event - first_event."""
        db = AsyncMock()
        invite = _make_invite()
        first_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        last_ts = datetime(2026, 1, 1, 12, 5, 0, tzinfo=UTC)  # 5 minutes
        events = [
            _make_event("page_viewed", timestamp=last_ts),
            _make_event("tool_called", timestamp=first_ts),
        ]

        metrics = await _calculate_metrics(db, invite, events)

        assert metrics.session_duration_seconds == pytest.approx(300.0)

    async def test_session_duration_zero_for_single_event(self) -> None:
        """Single event yields session_duration_seconds == 0.0."""
        db = AsyncMock()
        invite = _make_invite()
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        events = [_make_event("page_viewed", timestamp=ts)]

        metrics = await _calculate_metrics(db, invite, events)

        assert metrics.session_duration_seconds == pytest.approx(0.0)

    async def test_first_tool_at_picks_earliest_timestamp(self) -> None:
        """When multiple tool_called events exist, the earliest defines first_tool_at."""
        db = AsyncMock()
        opened_at = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        invite = _make_invite(opened_at=opened_at)
        late_ts = datetime(2026, 1, 1, 10, 10, 0, tzinfo=UTC)
        early_ts = datetime(2026, 1, 1, 10, 2, 0, tzinfo=UTC)  # 120s after open
        events = [
            _make_event("tool_called", timestamp=late_ts),
            _make_event("tool_called", timestamp=early_ts),
        ]

        metrics = await _calculate_metrics(db, invite, events)

        assert metrics.time_to_first_tool_seconds == pytest.approx(120.0)

    async def test_mixed_event_types_counted_independently(self) -> None:
        """All event types are counted without cross-contamination."""
        db = AsyncMock()
        invite = _make_invite()
        events = [
            _make_event("tool_called"),
            _make_event("tool_called"),
            _make_event("page_viewed"),
            _make_event("error_encountered"),
            _make_event("session_ended"),  # not counted in specific bins
        ]

        metrics = await _calculate_metrics(db, invite, events)

        assert metrics.tools_called_count == 2
        assert metrics.pages_viewed_count == 1
        assert metrics.errors_count == 1


# =============================================================================
# TestGetMetrics
# =============================================================================


class TestGetMetrics:
    """Tests for get_metrics()."""

    def _funnel_row(
        self,
        total=10,
        pending=2,
        opened=4,
        converted=3,
        expired=1,
    ) -> MagicMock:
        row = MagicMock()
        row.total = total
        row.pending = pending
        row.opened = opened
        row.converted = converted
        row.expired = expired
        return row

    def _nps_row(
        self,
        total_feedback=5,
        promoters=3,
        passives=1,
        detractors=1,
        avg_score=8.0,
    ) -> MagicMock:
        row = MagicMock()
        row.total_feedback = total_feedback
        row.promoters = promoters
        row.passives = passives
        row.detractors = detractors
        row.avg_score = avg_score
        return row

    def _timing_row(self, avg_time_to_tool=60.0, avg_time_to_open=30.0) -> MagicMock:
        row = MagicMock()
        row.avg_time_to_tool = avg_time_to_tool
        row.avg_time_to_open = avg_time_to_open
        return row

    def _companies_result(self, rows: list) -> MagicMock:
        result = MagicMock()
        result.all.return_value = rows
        return result

    def _make_company_row(self, company="Acme", invite_count=5, converted_count=2) -> MagicMock:
        row = MagicMock()
        row.company = company
        row.invite_count = invite_count
        row.converted_count = converted_count
        return row

    async def _setup_db(self, db: AsyncMock, funnel_row=None, nps_row=None, timing_row=None, company_rows=None) -> None:
        funnel_row = funnel_row or self._funnel_row()
        nps_row = nps_row or self._nps_row()
        timing_row = timing_row or self._timing_row()
        company_rows = company_rows or []

        funnel_result = MagicMock()
        funnel_result.first.return_value = funnel_row

        nps_result = MagicMock()
        nps_result.first.return_value = nps_row

        timing_result = MagicMock()
        timing_result.first.return_value = timing_row

        companies_result = self._companies_result(company_rows)

        db.execute.side_effect = [funnel_result, nps_result, timing_result, companies_result]

    async def test_returns_metrics_response(self) -> None:
        """Happy path returns ProspectsMetricsResponse with correct totals."""
        db = AsyncMock()
        await self._setup_db(db)

        result = await get_metrics(db)

        assert result.total_invited == 10
        assert result.total_active == 7  # opened(4) + converted(3)

    async def test_funnel_counts_correct(self) -> None:
        """Funnel breakdown matches the mocked row values."""
        db = AsyncMock()
        await self._setup_db(db, funnel_row=self._funnel_row(total=20, pending=5, opened=8, converted=5, expired=2))

        result = await get_metrics(db)

        assert result.by_status.total_invites == 20
        assert result.by_status.pending == 5
        assert result.by_status.opened == 8
        assert result.by_status.converted == 5
        assert result.by_status.expired == 2

    async def test_nps_score_calculated(self) -> None:
        """NPS score = ((promoters - detractors) / total) * 100."""
        db = AsyncMock()
        # 3 promoters, 1 detractor out of 5 → (2/5)*100 = 40.0
        await self._setup_db(db, nps_row=self._nps_row(total_feedback=5, promoters=3, detractors=1))

        result = await get_metrics(db)

        assert result.nps.nps_score == pytest.approx(40.0)

    async def test_nps_score_zero_when_no_feedback(self) -> None:
        """No feedback records yield nps_score of 0.0."""
        db = AsyncMock()
        await self._setup_db(db, nps_row=self._nps_row(total_feedback=0, promoters=0, passives=0, detractors=0, avg_score=None))

        result = await get_metrics(db)

        assert result.nps.nps_score == 0.0

    async def test_nps_distribution_counts_correct(self) -> None:
        """NPS distribution promoters/passives/detractors are returned."""
        db = AsyncMock()
        await self._setup_db(db, nps_row=self._nps_row(total_feedback=10, promoters=5, passives=3, detractors=2))

        result = await get_metrics(db)

        assert result.nps.promoters == 5
        assert result.nps.passives == 3
        assert result.nps.detractors == 2

    async def test_no_response_count_is_invites_minus_feedback(self) -> None:
        """no_response = total_invites - total_feedback."""
        db = AsyncMock()
        await self._setup_db(
            db,
            funnel_row=self._funnel_row(total=10),
            nps_row=self._nps_row(total_feedback=6),
        )

        result = await get_metrics(db)

        assert result.nps.no_response == 4  # 10 - 6

    async def test_avg_nps_forwarded(self) -> None:
        """avg_nps in response matches the nps_row avg_score."""
        db = AsyncMock()
        await self._setup_db(db, nps_row=self._nps_row(avg_score=7.5))

        result = await get_metrics(db)

        assert result.avg_nps == pytest.approx(7.5)

    async def test_avg_nps_none_when_no_feedback(self) -> None:
        """avg_nps is None when avg_score is None (no feedback)."""
        db = AsyncMock()
        await self._setup_db(db, nps_row=self._nps_row(total_feedback=0, avg_score=None))

        result = await get_metrics(db)

        assert result.avg_nps is None

    async def test_timing_metrics_forwarded(self) -> None:
        """Timing metrics are forwarded from the query row."""
        db = AsyncMock()
        await self._setup_db(db, timing_row=self._timing_row(avg_time_to_tool=120.0, avg_time_to_open=45.0))

        result = await get_metrics(db)

        assert result.avg_time_to_tool == pytest.approx(120.0)
        assert result.timing.avg_time_to_open_seconds == pytest.approx(45.0)
        assert result.timing.avg_time_to_first_tool_seconds == pytest.approx(120.0)

    async def test_timing_none_when_no_opened_invites(self) -> None:
        """Timing metrics are None when avg values are None."""
        db = AsyncMock()
        timing_row = MagicMock()
        timing_row.avg_time_to_tool = None
        timing_row.avg_time_to_open = None
        timing_result = MagicMock()
        timing_result.first.return_value = timing_row

        funnel_result = MagicMock()
        funnel_result.first.return_value = self._funnel_row()
        nps_result = MagicMock()
        nps_result.first.return_value = self._nps_row()
        companies_result = self._companies_result([])
        db.execute.side_effect = [funnel_result, nps_result, timing_result, companies_result]

        result = await get_metrics(db)

        assert result.avg_time_to_tool is None
        assert result.timing.avg_time_to_first_tool_seconds is None

    async def test_top_companies_populated(self) -> None:
        """top_companies list is built from the companies query rows."""
        db = AsyncMock()
        company_rows = [
            self._make_company_row("Acme", 10, 5),
            self._make_company_row("Globex", 7, 3),
        ]
        await self._setup_db(db, company_rows=company_rows)

        result = await get_metrics(db)

        assert len(result.top_companies) == 2
        assert result.top_companies[0].company == "Acme"
        assert result.top_companies[0].invite_count == 10
        assert result.top_companies[0].converted_count == 5

    async def test_top_companies_empty_when_no_rows(self) -> None:
        """Empty companies query yields empty top_companies list."""
        db = AsyncMock()
        await self._setup_db(db, company_rows=[])

        result = await get_metrics(db)

        assert result.top_companies == []

    async def test_company_converted_count_defaults_zero_when_null(self) -> None:
        """converted_count is None-safe (returns 0 when null)."""
        db = AsyncMock()
        company_row = MagicMock()
        company_row.company = "Nullco"
        company_row.invite_count = 3
        company_row.converted_count = None
        await self._setup_db(db, company_rows=[company_row])

        result = await get_metrics(db)

        assert result.top_companies[0].converted_count == 0

    async def test_date_from_filter_passes_through(self) -> None:
        """date_from triggers four db.execute calls (all subqueries)."""
        db = AsyncMock()
        await self._setup_db(db)

        await get_metrics(db, date_from=datetime(2026, 1, 1, tzinfo=UTC))

        assert db.execute.call_count == 4

    async def test_date_to_filter_passes_through(self) -> None:
        """date_to triggers four db.execute calls."""
        db = AsyncMock()
        await self._setup_db(db)

        await get_metrics(db, date_to=datetime(2026, 3, 1, tzinfo=UTC))

        assert db.execute.call_count == 4

    async def test_funnel_null_values_default_to_zero(self) -> None:
        """Null status counts in funnel row are normalised to 0."""
        db = AsyncMock()
        funnel_row = MagicMock()
        funnel_row.total = 5
        funnel_row.pending = None
        funnel_row.opened = None
        funnel_row.converted = None
        funnel_row.expired = None
        funnel_result = MagicMock()
        funnel_result.first.return_value = funnel_row

        nps_result = MagicMock()
        nps_result.first.return_value = self._nps_row()
        timing_result = MagicMock()
        timing_result.first.return_value = self._timing_row()
        db.execute.side_effect = [funnel_result, nps_result, timing_result, self._companies_result([])]

        result = await get_metrics(db)

        assert result.by_status.pending == 0
        assert result.by_status.opened == 0
        assert result.by_status.converted == 0
        assert result.by_status.expired == 0


# =============================================================================
# TestExportProspectsCsv
# =============================================================================


class TestExportProspectsCsv:
    """Tests for export_prospects_csv()."""

    async def test_returns_string(self) -> None:
        """Function returns a string (CSV content)."""
        db = AsyncMock()
        db.execute.return_value = _db_rows([])

        result = await export_prospects_csv(db)

        assert isinstance(result, str)

    async def test_header_row_present(self) -> None:
        """CSV output contains the expected header columns."""
        db = AsyncMock()
        db.execute.return_value = _db_rows([])

        result = await export_prospects_csv(db)

        assert "Email" in result
        assert "Company" in result
        assert "Status" in result
        assert "NPS Score" in result

    async def test_data_row_contains_invite_fields(self) -> None:
        """A single invite row is serialised correctly into CSV."""
        db = AsyncMock()
        invite = _make_invite(
            email="csv@test.com",
            company="CsvCorp",
            status="converted",
            source="web",
        )
        row = (invite, 9, "Excellent", None)  # no first_tool_at
        db.execute.return_value = _db_rows([row])

        result = await export_prospects_csv(db)

        assert "csv@test.com" in result
        assert "CsvCorp" in result
        assert "converted" in result

    async def test_nps_score_in_row(self) -> None:
        """NPS score appears in the CSV row when present."""
        db = AsyncMock()
        invite = _make_invite()
        row = (invite, 8, "Good", None)
        db.execute.return_value = _db_rows([row])

        result = await export_prospects_csv(db)

        assert "8" in result

    async def test_nps_score_empty_when_none(self) -> None:
        """Null NPS score is exported as empty string."""
        db = AsyncMock()
        invite = _make_invite()
        row = (invite, None, None, None)
        db.execute.return_value = _db_rows([row])

        result = await export_prospects_csv(db)

        lines = result.strip().splitlines()
        # Header + 1 data row
        assert len(lines) == 2
        # The NPS score column should be blank (not "None")
        assert "None" not in result

    async def test_time_to_tool_calculated_when_both_dates_present(self) -> None:
        """time_to_tool (seconds) appears in CSV when opened_at and first_tool_at are known."""
        db = AsyncMock()
        opened_at = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
        first_tool_at = datetime(2026, 1, 1, 11, 1, 0, tzinfo=UTC)  # 60 seconds
        invite = _make_invite(opened_at=opened_at)
        row = (invite, None, None, first_tool_at)
        db.execute.return_value = _db_rows([row])

        result = await export_prospects_csv(db)

        assert "60" in result

    async def test_time_to_tool_empty_when_no_opened_at(self) -> None:
        """time_to_tool is empty in CSV when invite was never opened."""
        db = AsyncMock()
        invite = _make_invite(opened_at=None)
        first_tool_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        row = (invite, None, None, first_tool_at)
        db.execute.return_value = _db_rows([row])

        result = await export_prospects_csv(db)

        # The time-to-tool column (8th) should be blank
        lines = result.strip().splitlines()
        data_row = lines[1].split(",")
        # Column index 7 is "Time to First Tool (seconds)"
        assert data_row[7] == ""

    async def test_empty_csv_contains_only_header(self) -> None:
        """No data rows produces a CSV with only the header line."""
        db = AsyncMock()
        db.execute.return_value = _db_rows([])

        result = await export_prospects_csv(db)

        lines = result.strip().splitlines()
        assert len(lines) == 1
        assert "Email" in lines[0]

    async def test_multiple_rows_in_output(self) -> None:
        """Multiple invite rows all appear as separate CSV lines."""
        db = AsyncMock()
        invites = [_make_invite(email=f"user{i}@test.com") for i in range(3)]
        rows = [(inv, None, None, None) for inv in invites]
        db.execute.return_value = _db_rows(rows)

        result = await export_prospects_csv(db)

        lines = result.strip().splitlines()
        assert len(lines) == 4  # 1 header + 3 data rows

    async def test_source_empty_string_when_none(self) -> None:
        """Null source is exported as empty string, not 'None'."""
        db = AsyncMock()
        invite = _make_invite(source=None)
        row = (invite, None, None, None)
        db.execute.return_value = _db_rows([row])

        result = await export_prospects_csv(db)

        assert "None" not in result

    async def test_company_filter_triggers_execute(self) -> None:
        """Passing company= still calls db.execute once (single query for CSV)."""
        db = AsyncMock()
        db.execute.return_value = _db_rows([])

        await export_prospects_csv(db, company="Acme")

        db.execute.assert_called_once()

    async def test_status_filter_triggers_execute(self) -> None:
        """Passing status= still calls db.execute once."""
        db = AsyncMock()
        db.execute.return_value = _db_rows([])

        await export_prospects_csv(db, status="converted")

        db.execute.assert_called_once()

    async def test_date_range_filter_triggers_execute(self) -> None:
        """Passing date_from and date_to still calls db.execute once."""
        db = AsyncMock()
        db.execute.return_value = _db_rows([])

        await export_prospects_csv(
            db,
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to=datetime(2026, 3, 1, tzinfo=UTC),
        )

        db.execute.assert_called_once()

    async def test_opened_at_iso_format_in_row(self) -> None:
        """opened_at is exported as ISO format string."""
        db = AsyncMock()
        opened_at = datetime(2026, 2, 15, 9, 30, 0, tzinfo=UTC)
        invite = _make_invite(opened_at=opened_at)
        row = (invite, None, None, None)
        db.execute.return_value = _db_rows([row])

        result = await export_prospects_csv(db)

        assert "2026-02-15" in result

    async def test_created_at_iso_format_in_row(self) -> None:
        """created_at is exported as ISO format string."""
        db = AsyncMock()
        created_at = datetime(2026, 1, 10, 8, 0, 0, tzinfo=UTC)
        invite = _make_invite(created_at=created_at)
        row = (invite, None, None, None)
        db.execute.return_value = _db_rows([row])

        result = await export_prospects_csv(db)

        assert "2026-01-10" in result

    async def test_nps_comment_in_row(self) -> None:
        """NPS comment appears in the CSV row."""
        db = AsyncMock()
        invite = _make_invite()
        row = (invite, 10, "Absolutely amazing!", None)
        db.execute.return_value = _db_rows([row])

        result = await export_prospects_csv(db)

        assert "Absolutely amazing!" in result

    async def test_nps_comment_empty_when_none(self) -> None:
        """Null NPS comment is exported as empty string."""
        db = AsyncMock()
        invite = _make_invite()
        row = (invite, 8, None, None)
        db.execute.return_value = _db_rows([row])

        result = await export_prospects_csv(db)

        assert "None" not in result
