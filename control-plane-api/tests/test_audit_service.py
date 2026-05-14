"""Tests for AuditService — CAB-1475 Phase 1.

Covers: record_event, list_events, get_event, export_events, get_summary, purge_before.
Uses mock AsyncSession — no real database.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.audit_event import AuditEvent
from src.services.audit_service import _ACTOR_CACHE, AuditService, resolve_actor


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


def _mock_empty_chain(session):
    session.execute = AsyncMock(side_effect=[MagicMock(), MagicMock()])
    session.scalar = AsyncMock(return_value=None)


@pytest.fixture(autouse=True)
def clear_actor_cache():
    _ACTOR_CACHE.clear()
    yield
    _ACTOR_CACHE.clear()


class TestRecordEvent:
    """Tests for AuditService.record_event()."""

    @pytest.mark.asyncio
    async def test_record_event_success(self, audit_service, mock_session):
        _mock_empty_chain(mock_session)

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
        assert result.row_hash is not None
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        mock_session.scalar.assert_awaited_once()
        assert mock_session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_record_event_minimal_fields(self, audit_service, mock_session):
        _mock_empty_chain(mock_session)

        result = await audit_service.record_event(
            tenant_id="acme",
            action="data.accessed",
            method="GET",
            path="/v1/apis",
            resource_type="api",
        )

        assert result is not None
        assert result.tenant_id == "acme"
        assert result.actor_id is None
        assert result.resource_id is None
        assert result.outcome == "success"
        assert result.row_hash is not None

    @pytest.mark.asyncio
    async def test_record_event_db_error_returns_none(self, audit_service, mock_session):
        _mock_empty_chain(mock_session)
        mock_session.flush.side_effect = Exception("DB connection lost")

        result = await audit_service.record_event(
            tenant_id="acme",
            action="test",
            method="POST",
            path="/test",
            resource_type="test",
        )

        assert result is None


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


class TestResolveActor:
    """Tests for audit actor resolution."""

    @pytest.mark.asyncio
    async def test_resolve_actor_caches_keycloak_lookup(self):
        keycloak = MagicMock()
        keycloak._admin = object()
        keycloak.get_user = AsyncMock(
            return_value={
                "id": "user-123",
                "email": "alice@example.com",
                "firstName": "Alice",
                "lastName": "Nguyen",
                "username": "alice",
            }
        )

        with patch("src.services.keycloak_service.keycloak_service", keycloak):
            first = await resolve_actor("user-123", None)
            second = await resolve_actor("user-123", None)

        assert first == second
        assert first.resolved is True
        assert first.user_email == "alice@example.com"
        assert first.user_display_name == "Alice Nguyen"
        keycloak.get_user.assert_awaited_once_with("user-123")

    @pytest.mark.asyncio
    async def test_resolve_actor_returns_unresolved_when_keycloak_down(self):
        keycloak = MagicMock()
        keycloak._admin = object()
        keycloak.get_user = AsyncMock(side_effect=RuntimeError("keycloak down"))

        with patch("src.services.keycloak_service.keycloak_service", keycloak):
            actor = await resolve_actor("user-123", "alice@example.com")

        assert actor.user_id == "user-123"
        assert actor.user_email is None
        assert actor.user_display_name is None
        assert actor.resolved is False

    @pytest.mark.asyncio
    async def test_resolve_actor_does_not_raise_on_missing_user(self):
        keycloak = MagicMock()
        keycloak._admin = object()
        keycloak.get_user = AsyncMock(return_value=None)

        with patch("src.services.keycloak_service.keycloak_service", keycloak):
            actor = await resolve_actor("missing-user", "missing@example.com")

        assert actor.user_id == "missing-user"
        assert actor.user_email is None
        assert actor.user_display_name is None
        assert actor.resolved is False


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
        action_result.__iter__ = lambda _self: iter(action_rows)

        mock_session.execute = AsyncMock(side_effect=[total_result, *outcome_results, action_result])

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
        for r, v in zip(outcome_results, [8, 1, 0, 1], strict=True):
            r.scalar.return_value = v

        action_result = MagicMock()
        action_result.__iter__ = lambda _self: iter([])

        mock_session.execute = AsyncMock(side_effect=[total_result, *outcome_results, action_result])

        summary = await audit_service.get_summary(tenant_id="acme")
        assert summary["total"] == 10


class TestPurgeBefore:
    """Tests for AuditService.purge_before()."""

    @pytest.mark.asyncio
    async def test_purge_raises_after_audit_immutability(self, audit_service, mock_session):
        with pytest.raises(NotImplementedError, match="CAB-2226 makes audit_events append-only"):
            await audit_service.purge_before(
                "acme",
                datetime.now(UTC) - timedelta(days=365),
            )

        mock_session.execute.assert_not_awaited()


class TestEraseUserPii:
    """Tests for AuditService.erase_user_pii() — GDPR Art. 17 (CAB-1794)."""

    @pytest.mark.asyncio
    async def test_erase_user_pii_records_auxiliary_erasure(self, audit_service, mock_session):
        """Erasure records metadata in the auxiliary table."""

        with patch(
            "src.services.audit_service._wrap_pseudonymization_key",
            new=AsyncMock(return_value=b"vault:v1:test-ciphertext"),
        ):
            response = await audit_service.erase_user_pii(
                "user-123",
                dpo_approver_id="dpo-1",
                legal_basis="GDPR Art.17",
                redaction_map={"actor_email": None},
                scope_event_ids=["evt-1"],
            )

        assert response["records_affected"] == 0
        assert response["erasure_id"]
        assert response["scope_actor_ids"] == ["user-123"]
        assert response["scope_event_ids"] == ["evt-1"]
        statement = mock_session.execute.await_args.args[0]
        assert statement.table.name == "pseudonymized_audit_erasures"
        params = statement.compile().params
        assert params["pseudonymization_key"].startswith(b"vault:v1:")
        mock_session.execute.assert_awaited_once()
