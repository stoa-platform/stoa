"""Tests for Chat Token Metering — CAB-288 + CAB-1452.

Covers: model, schemas, repository, budget enforcement, consumer.
Extended with edge-case coverage for consumer error paths,
repository budget boundaries, and usage stats with data.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.models.chat_token_usage import ChatTokenUsage
from src.repositories.chat_token_usage_repository import ChatTokenUsageRepository
from src.workers.chat_metering_consumer import ChatMeteringConsumer, ChatTokensEvent

_today = datetime.now(UTC).date()


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class TestChatTokenUsageModel:
    """Test the ChatTokenUsage SQLAlchemy model structure."""

    def test_table_name(self):
        assert ChatTokenUsage.__tablename__ == "chat_token_usage"

    def test_unique_constraint_exists(self):
        constraints = ChatTokenUsage.__table_args__
        assert any(
            getattr(c, "name", None) == "uq_chat_token_usage_tenant_user_model_date"
            for c in constraints
            if hasattr(c, "name")
        )

    def test_columns_exist(self):
        cols = {c.name for c in ChatTokenUsage.__table__.columns}
        expected = {
            "id",
            "tenant_id",
            "user_id",
            "model",
            "period_date",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "request_count",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestMeteringSchemas:
    """Test Pydantic schemas for metering events."""

    def test_valid_event(self):
        event = ChatTokensEvent(
            tenant_id="t1",
            user_id="u1",
            conversation_id="c1",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )
        assert event.total_tokens == 150

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            ChatTokensEvent(tenant_id="t1")  # type: ignore[call-arg]

    def test_event_roundtrip(self):
        data = {
            "tenant_id": "t1",
            "user_id": "u1",
            "conversation_id": "c1",
            "model": "claude-sonnet-4-20250514",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }
        event = ChatTokensEvent.model_validate(data)
        assert event.model_dump() == data


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class TestChatTokenUsageRepository:
    """Test the ChatTokenUsageRepository methods (mocked DB)."""

    def _make_repo(self, session: AsyncMock) -> ChatTokenUsageRepository:
        return ChatTokenUsageRepository(session)

    @pytest.mark.asyncio
    async def test_increment_executes_upsert(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = ChatTokenUsage(
            id=uuid4(),
            tenant_id="t1",
            user_id="u1",
            model="claude-sonnet-4-20250514",
            period_date=_today,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            request_count=1,
        )
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()

        repo = self._make_repo(session)
        result = await repo.increment(
            tenant_id="t1",
            user_id="u1",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
        )
        assert result.total_tokens == 150
        session.execute.assert_awaited_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_daily_user_usage(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5000
        session.execute = AsyncMock(return_value=mock_result)

        repo = self._make_repo(session)
        usage = await repo.get_daily_user_usage("t1", "u1")
        assert usage == 5000

    @pytest.mark.asyncio
    async def test_get_daily_tenant_usage(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 25000
        session.execute = AsyncMock(return_value=mock_result)

        repo = self._make_repo(session)
        usage = await repo.get_daily_tenant_usage("t1")
        assert usage == 25000

    @pytest.mark.asyncio
    async def test_get_budget_status_under_budget(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5000
        session.execute = AsyncMock(return_value=mock_result)

        repo = self._make_repo(session)
        status = await repo.get_budget_status("t1", "u1", daily_budget=10000)
        assert status["budget_exceeded"] is False
        assert status["remaining"] == 5000

    @pytest.mark.asyncio
    async def test_get_budget_status_exceeded(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 15000
        session.execute = AsyncMock(return_value=mock_result)

        repo = self._make_repo(session)
        status = await repo.get_budget_status("t1", "u1", daily_budget=10000)
        assert status["budget_exceeded"] is True
        assert status["remaining"] == 0
        assert status["usage_percent"] == 100.0

    @pytest.mark.asyncio
    async def test_get_usage_stats_empty(self):
        session = AsyncMock()

        # Totals query returns zeros
        totals_result = MagicMock()
        totals_result.one.return_value = (0, 0, 0, 0)

        # Today query returns zero
        today_result = MagicMock()
        today_result.scalar_one.return_value = 0

        # Top users query returns empty
        top_result = MagicMock()
        top_result.all.return_value = []

        # Daily breakdown returns empty
        daily_result = MagicMock()
        daily_result.all.return_value = []

        session.execute = AsyncMock(side_effect=[totals_result, today_result, top_result, daily_result])

        repo = self._make_repo(session)
        stats = await repo.get_usage_stats("t1", days=30)
        assert stats["total_tokens"] == 0
        assert stats["top_users"] == []
        assert stats["daily_breakdown"] == []

    @pytest.mark.asyncio
    async def test_increment_returns_chat_token_usage(self):
        session = AsyncMock()
        usage = ChatTokenUsage(
            id=uuid4(),
            tenant_id="t1",
            user_id="u1",
            model="claude-sonnet-4-20250514",
            period_date=_today,
            input_tokens=200,
            output_tokens=100,
            total_tokens=300,
            request_count=2,
        )
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = usage
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()

        repo = self._make_repo(session)
        result = await repo.increment(
            tenant_id="t1",
            user_id="u1",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
        )
        assert isinstance(result, ChatTokenUsage)
        assert result.request_count == 2


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------


class TestBudgetEnforcement:
    """Test the budget check integration in ChatService.send_message."""

    @pytest.mark.asyncio
    async def test_budget_exceeded_yields_error(self):
        """When daily budget is exceeded, send_message yields an error event."""
        from src.services.chat_service import ChatService

        session = AsyncMock()

        # Conversation lookup
        mock_conv = MagicMock()
        mock_conv.id = uuid4()
        mock_conv.provider = "anthropic"
        mock_conv.model = "claude-sonnet-4-20250514"
        mock_conv.system_prompt = None
        mock_conv.messages = []

        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = mock_conv
        session.execute = AsyncMock(return_value=conv_result)
        session.flush = AsyncMock()
        session.add = MagicMock()

        svc = ChatService(session)

        with (
            patch(
                "src.services.chat_service.settings",
                MagicMock(CHAT_TOKEN_BUDGET_DAILY=1000),
            ),
            patch(
                "src.repositories.chat_token_usage_repository.ChatTokenUsageRepository.get_daily_user_usage",
                new_callable=AsyncMock,
                return_value=2000,
            ),
        ):
            events: list[dict[str, Any]] = []
            async for event in svc.send_message(
                conversation_id=mock_conv.id,
                tenant_id="t1",
                user_id="u1",
                content="Hello",
                api_key="sk-test",
            ):
                events.append(event)

        assert len(events) == 1
        assert events[0]["event"] == "error"
        assert "budget" in events[0]["data"]["error"].lower()

    @pytest.mark.asyncio
    async def test_no_budget_limit_allows_through(self):
        """When budget is 0 (unlimited), no budget check runs."""
        from src.services.chat_service import ChatService

        session = AsyncMock()

        mock_conv = MagicMock()
        mock_conv.id = uuid4()
        mock_conv.provider = "anthropic"
        mock_conv.model = "claude-sonnet-4-20250514"
        mock_conv.system_prompt = None
        mock_conv.messages = []

        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = mock_conv
        session.execute = AsyncMock(return_value=conv_result)
        session.flush = AsyncMock()
        session.add = MagicMock()

        svc = ChatService(session)

        with (
            patch(
                "src.services.chat_service.settings",
                MagicMock(CHAT_TOKEN_BUDGET_DAILY=0),
            ),
            patch("src.services.chat_service.AnthropicProvider") as _mock_provider_cls,
        ):
            # Make provider.stream_response an async generator
            async def fake_stream(*_a, **_k):
                yield {
                    "event": "message_start",
                    "data": {"message_id": "msg1", "model": "test"},
                }
                yield {
                    "event": "message_end",
                    "data": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "stop_reason": "end_turn",
                    },
                }

            mock_provider_instance = MagicMock()
            mock_provider_instance.stream_response = fake_stream

            with patch.dict(
                "src.services.chat_service._PROVIDERS",
                {"anthropic": mock_provider_instance},
            ):
                events: list[dict[str, Any]] = []
                async for event in svc.send_message(
                    conversation_id=mock_conv.id,
                    tenant_id="t1",
                    user_id="u1",
                    content="Hello",
                    api_key="sk-test",
                ):
                    events.append(event)

        # Should NOT get budget error
        assert not any(e.get("event") == "error" and "budget" in str(e.get("data", "")).lower() for e in events)


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------


class TestChatMeteringConsumer:
    """Test the ChatMeteringConsumer class."""

    def test_singleton_exists(self):
        from src.workers.chat_metering_consumer import chat_metering_consumer

        assert isinstance(chat_metering_consumer, ChatMeteringConsumer)

    def test_topic_and_group(self):
        consumer = ChatMeteringConsumer()
        assert consumer.TOPIC == "stoa.chat.tokens_used"
        assert consumer.GROUP == "chat-metering-consumer"

    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        consumer = ChatMeteringConsumer()
        with patch.object(consumer, "_consume_thread"):
            await consumer.start()
            assert consumer._running is True
            assert consumer._thread is not None
            await consumer.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running(self):
        consumer = ChatMeteringConsumer()
        consumer._running = True
        consumer._consumer = MagicMock()
        await consumer.stop()
        assert consumer._running is False

    def test_process_message_sync_valid(self):
        consumer = ChatMeteringConsumer()
        consumer._loop = asyncio.new_event_loop()

        msg = MagicMock()
        msg.value = {
            "tenant_id": "t1",
            "user_id": "u1",
            "conversation_id": "c1",
            "model": "claude-sonnet-4-20250514",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

        with patch.object(consumer, "_handle_event", new_callable=AsyncMock):
            consumer._process_message_sync(msg)

        consumer._loop.close()

    def test_process_message_sync_invalid_data(self):
        consumer = ChatMeteringConsumer()
        consumer._loop = asyncio.new_event_loop()

        msg = MagicMock()
        msg.value = {"bad": "data"}

        # Should not raise
        consumer._process_message_sync(msg)
        consumer._loop.close()

    @pytest.mark.asyncio
    async def test_handle_event_persists(self):
        consumer = ChatMeteringConsumer()
        event = ChatTokensEvent(
            tenant_id="t1",
            user_id="u1",
            conversation_id="c1",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_repo = AsyncMock()

        mock_factory = MagicMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        with (
            patch(
                "src.workers.chat_metering_consumer._get_session_factory",
                return_value=mock_factory,
            ),
            patch(
                "src.workers.chat_metering_consumer.ChatTokenUsageRepository",
                return_value=mock_repo,
            ),
        ):
            await consumer._handle_event(event)

        mock_repo.increment.assert_awaited_once_with(
            tenant_id="t1",
            user_id="u1",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
        )
        mock_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# Consumer — extended edge cases (CAB-1452)
# ---------------------------------------------------------------------------


class TestChatMeteringConsumerEdgeCases:
    """Extended consumer tests: error paths, null guards, DB failures."""

    def test_process_message_sync_no_loop(self):
        """When _loop is None, message is parsed but not dispatched."""
        consumer = ChatMeteringConsumer()
        consumer._loop = None  # No event loop captured

        msg = MagicMock()
        msg.value = {
            "tenant_id": "t1",
            "user_id": "u1",
            "conversation_id": "c1",
            "model": "claude-sonnet-4-20250514",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

        # Should not raise — silently skip dispatch
        consumer._process_message_sync(msg)

    def test_process_message_sync_null_message(self):
        """Null message value triggers the except branch."""
        consumer = ChatMeteringConsumer()
        consumer._loop = asyncio.new_event_loop()

        msg = MagicMock()
        msg.value = None

        # Should not raise — caught by except
        consumer._process_message_sync(msg)
        consumer._loop.close()

    def test_process_message_sync_extra_fields_ignored(self):
        """Extra fields in the payload should be silently ignored by Pydantic."""
        consumer = ChatMeteringConsumer()
        consumer._loop = asyncio.new_event_loop()

        msg = MagicMock()
        msg.value = {
            "tenant_id": "t1",
            "user_id": "u1",
            "conversation_id": "c1",
            "model": "claude-sonnet-4-20250514",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "extra_unknown_field": "should be ignored",
        }

        with patch.object(consumer, "_handle_event", new_callable=AsyncMock):
            consumer._process_message_sync(msg)

        consumer._loop.close()

    @pytest.mark.asyncio
    async def test_handle_event_db_exception_is_swallowed(self):
        """DB failure in _handle_event is logged but not raised."""
        consumer = ChatMeteringConsumer()
        event = ChatTokensEvent(
            tenant_id="t1",
            user_id="u1",
            conversation_id="c1",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )

        mock_factory = MagicMock()
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        mock_repo = AsyncMock()
        mock_repo.increment = AsyncMock(side_effect=RuntimeError("DB connection lost"))

        with (
            patch(
                "src.workers.chat_metering_consumer._get_session_factory",
                return_value=mock_factory,
            ),
            patch(
                "src.workers.chat_metering_consumer.ChatTokenUsageRepository",
                return_value=mock_repo,
            ),
        ):
            # Should not raise — exception is swallowed
            await consumer._handle_event(event)

    @pytest.mark.asyncio
    async def test_handle_event_session_factory_exception(self):
        """When _get_session_factory raises, the error is swallowed."""
        consumer = ChatMeteringConsumer()
        event = ChatTokensEvent(
            tenant_id="t1",
            user_id="u1",
            conversation_id="c1",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )

        with patch(
            "src.workers.chat_metering_consumer._get_session_factory",
            side_effect=RuntimeError("No engine configured"),
        ):
            # Should not raise
            await consumer._handle_event(event)

    @pytest.mark.asyncio
    async def test_stop_without_consumer(self):
        """stop() when _consumer is None should not raise."""
        consumer = ChatMeteringConsumer()
        consumer._running = True
        consumer._consumer = None
        await consumer.stop()
        assert consumer._running is False

    def test_initial_state(self):
        """Fresh consumer has correct initial state."""
        consumer = ChatMeteringConsumer()
        assert consumer._running is False
        assert consumer._consumer is None
        assert consumer._thread is None
        assert consumer._loop is None


# ---------------------------------------------------------------------------
# Repository — extended edge cases (CAB-1452)
# ---------------------------------------------------------------------------


class TestChatTokenUsageRepositoryEdgeCases:
    """Extended repository tests: budget boundaries, populated stats."""

    def _make_repo(self, session: AsyncMock) -> ChatTokenUsageRepository:
        return ChatTokenUsageRepository(session)

    @pytest.mark.asyncio
    async def test_budget_status_zero_budget(self):
        """Zero budget: usage_percent=0, budget_exceeded=True (0>=0)."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=mock_result)

        repo = self._make_repo(session)
        status = await repo.get_budget_status("t1", "u1", daily_budget=0)
        assert status["budget_exceeded"] is True
        assert status["usage_percent"] == 0.0
        assert status["remaining"] == 0

    @pytest.mark.asyncio
    async def test_budget_status_zero_budget_with_usage(self):
        """Zero budget with existing usage: exceeded, 0% (not division by zero)."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5000
        session.execute = AsyncMock(return_value=mock_result)

        repo = self._make_repo(session)
        status = await repo.get_budget_status("t1", "u1", daily_budget=0)
        assert status["budget_exceeded"] is True
        assert status["usage_percent"] == 0.0  # Not division by zero
        assert status["remaining"] == 0

    @pytest.mark.asyncio
    async def test_budget_status_exact_limit(self):
        """At exact limit: budget_exceeded=True, remaining=0, usage_percent=100."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 10000
        session.execute = AsyncMock(return_value=mock_result)

        repo = self._make_repo(session)
        status = await repo.get_budget_status("t1", "u1", daily_budget=10000)
        assert status["budget_exceeded"] is True
        assert status["remaining"] == 0
        assert status["usage_percent"] == 100.0

    @pytest.mark.asyncio
    async def test_budget_status_one_under_limit(self):
        """One token under limit: not exceeded, 1 remaining."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 9999
        session.execute = AsyncMock(return_value=mock_result)

        repo = self._make_repo(session)
        status = await repo.get_budget_status("t1", "u1", daily_budget=10000)
        assert status["budget_exceeded"] is False
        assert status["remaining"] == 1

    @pytest.mark.asyncio
    async def test_budget_status_includes_tenant_usage(self):
        """get_budget_status returns both user and tenant usage."""
        session = AsyncMock()

        # Two sequential calls: user_usage=5000, tenant_usage=25000
        user_result = MagicMock()
        user_result.scalar_one.return_value = 5000
        tenant_result = MagicMock()
        tenant_result.scalar_one.return_value = 25000

        session.execute = AsyncMock(side_effect=[user_result, tenant_result])

        repo = self._make_repo(session)
        status = await repo.get_budget_status("t1", "u1", daily_budget=10000)
        assert status["user_tokens_today"] == 5000
        assert status["tenant_tokens_today"] == 25000
        assert status["daily_budget"] == 10000

    @pytest.mark.asyncio
    async def test_get_usage_stats_with_data(self):
        """get_usage_stats returns populated stats with top users and breakdown."""
        session = AsyncMock()

        # Totals query
        totals_result = MagicMock()
        totals_result.one.return_value = (150000, 100000, 50000, 500)

        # Today query
        today_result = MagicMock()
        today_result.scalar_one.return_value = 8000

        # Top users
        user1 = MagicMock()
        user1.user_id = "alice"
        user1.tokens = 80000
        user2 = MagicMock()
        user2.user_id = "bob"
        user2.tokens = 70000
        top_result = MagicMock()
        top_result.all.return_value = [user1, user2]

        # Daily breakdown
        day1 = MagicMock()
        day1.day = _today
        day1.tokens = 8000
        day1.requests = 30
        daily_result = MagicMock()
        daily_result.all.return_value = [day1]

        session.execute = AsyncMock(side_effect=[totals_result, today_result, top_result, daily_result])

        repo = self._make_repo(session)
        stats = await repo.get_usage_stats("t1", days=7)

        assert stats["tenant_id"] == "t1"
        assert stats["period_days"] == 7
        assert stats["total_tokens"] == 150000
        assert stats["total_input_tokens"] == 100000
        assert stats["total_output_tokens"] == 50000
        assert stats["total_requests"] == 500
        assert stats["today_tokens"] == 8000
        assert len(stats["top_users"]) == 2
        assert stats["top_users"][0]["user_id"] == "alice"
        assert stats["top_users"][0]["tokens"] == 80000
        assert len(stats["daily_breakdown"]) == 1
        assert stats["daily_breakdown"][0]["tokens"] == 8000

    @pytest.mark.asyncio
    async def test_budget_status_over_budget_usage_capped(self):
        """When over budget, usage_percent is capped at 100.0."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 20000  # 2x the budget
        session.execute = AsyncMock(return_value=mock_result)

        repo = self._make_repo(session)
        status = await repo.get_budget_status("t1", "u1", daily_budget=10000)
        assert status["budget_exceeded"] is True
        assert status["usage_percent"] == 100.0  # Capped by min(100.0, ...)
        assert status["remaining"] == 0
