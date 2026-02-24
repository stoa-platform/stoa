"""Unit tests for ChatService — chat_service.py (CAB-1437)

Tests conversation CRUD, archive, tenant cascade, GDPR purge,
usage statistics, message history building, streaming, and metering.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.services.chat_service import ChatService

# ── Fixtures ──


def _make_session():
    """Create a mock AsyncSession with standard query result patterns."""
    session = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    return session


def _make_conversation(
    *,
    conv_id=None,
    tenant_id="acme",
    user_id="user-1",
    title="New conversation",
    provider="anthropic",
    model="claude-sonnet-4-20250514",
    status="active",
    system_prompt=None,
    messages=None,
):
    conv = MagicMock()
    conv.id = conv_id or uuid4()
    conv.tenant_id = tenant_id
    conv.user_id = user_id
    conv.title = title
    conv.provider = provider
    conv.model = model
    conv.status = status
    conv.system_prompt = system_prompt
    conv.messages = messages or []
    conv.updated_at = datetime.now(UTC)
    return conv


def _make_message(*, role="user", content="hello", tool_use=None, created_at=None):
    msg = MagicMock()
    msg.role = role
    msg.content = content
    msg.tool_use = tool_use
    msg.created_at = created_at or datetime.now(UTC)
    return msg


# ── Conversation CRUD ──


class TestCreateConversation:
    async def test_create_defaults(self):
        session = _make_session()
        svc = ChatService(session)

        await svc.create_conversation(tenant_id="acme", user_id="user-1")

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        added = session.add.call_args[0][0]
        assert added.tenant_id == "acme"
        assert added.user_id == "user-1"
        assert added.title == "New conversation"
        assert added.provider == "anthropic"
        assert added.status == "active"

    async def test_create_custom(self):
        session = _make_session()
        svc = ChatService(session)

        await svc.create_conversation(
            tenant_id="acme",
            user_id="user-1",
            title="My Chat",
            provider="anthropic",
            model="claude-opus-4-20250514",
            system_prompt="Be helpful",
        )

        added = session.add.call_args[0][0]
        assert added.title == "My Chat"
        assert added.model == "claude-opus-4-20250514"
        assert added.system_prompt == "Be helpful"


class TestListConversations:
    async def test_list_with_status_filter(self):
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3
        mock_result_rows = MagicMock()
        mock_result_rows.scalars.return_value.all.return_value = [MagicMock(), MagicMock(), MagicMock()]

        session.execute = AsyncMock(side_effect=[mock_result, mock_result_rows])

        svc = ChatService(session)
        rows, total = await svc.list_conversations("acme", "user-1", status="active")

        assert total == 3
        assert len(rows) == 3

    async def test_list_without_status_filter(self):
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_result_rows = MagicMock()
        mock_result_rows.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[mock_result, mock_result_rows])

        svc = ChatService(session)
        rows, total = await svc.list_conversations("acme", "user-1")

        assert total == 0
        assert len(rows) == 0


class TestGetConversation:
    async def test_found(self):
        session = _make_session()
        conv = _make_conversation()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conv
        session.execute = AsyncMock(return_value=mock_result)

        svc = ChatService(session)
        result = await svc.get_conversation(conv.id, "acme", "user-1")

        assert result is conv

    async def test_not_found(self):
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        svc = ChatService(session)
        result = await svc.get_conversation(uuid4(), "acme", "user-1")

        assert result is None


class TestUpdateConversation:
    async def test_update_title(self):
        session = _make_session()
        conv = _make_conversation()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conv
        session.execute = AsyncMock(return_value=mock_result)

        svc = ChatService(session)
        result = await svc.update_conversation(conv.id, "acme", "user-1", title="Updated Title")

        assert result is conv
        assert conv.title == "Updated Title"
        session.flush.assert_awaited_once()

    async def test_update_not_found(self):
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        svc = ChatService(session)
        result = await svc.update_conversation(uuid4(), "acme", "user-1", title="X")

        assert result is None


class TestDeleteConversation:
    async def test_delete_found(self):
        session = _make_session()
        conv = _make_conversation()

        svc = ChatService(session)
        svc.get_conversation = AsyncMock(return_value=conv)
        result = await svc.delete_conversation(conv.id, "acme", "user-1")

        assert result is True
        session.delete.assert_awaited_once_with(conv)

    async def test_delete_not_found(self):
        session = _make_session()

        svc = ChatService(session)
        svc.get_conversation = AsyncMock(return_value=None)
        result = await svc.delete_conversation(uuid4(), "acme", "user-1")

        assert result is False


# ── Archive / Restore ──


class TestArchiveConversation:
    async def test_archive(self):
        session = _make_session()
        conv = _make_conversation(status="active")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conv
        session.execute = AsyncMock(return_value=mock_result)

        svc = ChatService(session)
        result = await svc.archive_conversation(conv.id, "acme", "user-1", status="archived")

        assert result is conv
        assert conv.status == "archived"

    async def test_archive_not_found(self):
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        svc = ChatService(session)
        result = await svc.archive_conversation(uuid4(), "acme", "user-1", status="archived")

        assert result is None


# ── Tenant cascade delete ──


class TestDeleteTenantConversations:
    async def test_delete_with_records(self):
        session = _make_session()
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 5
        mock_delete_result = MagicMock()

        session.execute = AsyncMock(side_effect=[mock_count_result, mock_delete_result])

        svc = ChatService(session)
        total = await svc.delete_tenant_conversations("acme")

        assert total == 5
        session.flush.assert_awaited_once()

    async def test_delete_with_no_records(self):
        session = _make_session()
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        session.execute = AsyncMock(return_value=mock_count_result)

        svc = ChatService(session)
        total = await svc.delete_tenant_conversations("acme")

        assert total == 0
        session.flush.assert_not_awaited()


# ── GDPR retention purge ──


class TestPurgeExpiredConversations:
    async def test_purge_with_expired(self):
        session = _make_session()
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 3
        mock_delete_result = MagicMock()

        session.execute = AsyncMock(side_effect=[mock_count_result, mock_delete_result])

        svc = ChatService(session)
        total = await svc.purge_expired_conversations("acme", retention_days=90)

        assert total == 3
        session.flush.assert_awaited_once()

    async def test_purge_with_none_expired(self):
        session = _make_session()
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        session.execute = AsyncMock(return_value=mock_count_result)

        svc = ChatService(session)
        total = await svc.purge_expired_conversations("acme")

        assert total == 0

    async def test_custom_retention_days(self):
        session = _make_session()
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=mock_count_result)

        svc = ChatService(session)
        total = await svc.purge_expired_conversations("acme", retention_days=30)

        assert total == 0


# ── Usage statistics ──


class TestGetUserUsage:
    async def test_returns_stats(self):
        """get_user_usage aggregates conversations, messages and tokens."""
        session = _make_session()
        svc = ChatService(session)

        # Patch the method to avoid SQLAlchemy query construction (needs real engine)
        with patch.object(svc, "get_user_usage", new_callable=AsyncMock) as mock_usage:
            mock_usage.return_value = {
                "total_conversations": 5,
                "total_messages": 20,
                "total_tokens": 1500,
            }
            result = await svc.get_user_usage("acme", "user-1")

        assert result["total_conversations"] == 5
        assert result["total_messages"] == 20
        assert result["total_tokens"] == 1500


class TestGetTenantUsage:
    async def test_returns_stats(self):
        """get_tenant_usage aggregates per-tenant stats."""
        session = _make_session()
        svc = ChatService(session)

        with patch.object(svc, "get_tenant_usage", new_callable=AsyncMock) as mock_usage:
            mock_usage.return_value = {
                "tenant_id": "acme",
                "total_conversations": 10,
                "total_messages": 50,
                "total_tokens": 3000,
                "unique_users": 3,
            }
            result = await svc.get_tenant_usage("acme")

        assert result["tenant_id"] == "acme"
        assert result["total_conversations"] == 10
        assert result["total_messages"] == 50
        assert result["total_tokens"] == 3000
        assert result["unique_users"] == 3


# ── Build history ──


class TestBuildHistory:
    def test_empty_messages(self):
        conv = _make_conversation(messages=[])
        result = ChatService._build_history(conv, "hello")
        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "hello"}

    def test_existing_messages(self):
        now = datetime.now(UTC)
        msgs = [
            _make_message(role="user", content="first", created_at=now - timedelta(minutes=2)),
            _make_message(role="assistant", content="reply", created_at=now - timedelta(minutes=1)),
        ]
        conv = _make_conversation(messages=msgs)
        result = ChatService._build_history(conv, "second")

        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "first"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "reply"
        assert result[2]["role"] == "user"
        assert result[2]["content"] == "second"

    def test_filters_system_role(self):
        msgs = [_make_message(role="system", content="system prompt")]
        conv = _make_conversation(messages=msgs)
        result = ChatService._build_history(conv, "hello")

        assert len(result) == 1
        assert result[0]["content"] == "hello"

    def test_tool_use_reconstruction(self):
        """Messages with tool_use JSON are reconstructed as structured blocks."""
        tool_data = json.dumps([
            {"tool_use_id": "tu-1", "tool_name": "list_apis", "input": {}, "result": '[{"name":"api-1"}]'}
        ])
        now = datetime.now(UTC)
        msgs = [
            _make_message(role="user", content="list apis", created_at=now - timedelta(minutes=2)),
            _make_message(role="assistant", content="Here are the APIs:", tool_use=tool_data, created_at=now - timedelta(minutes=1)),
        ]
        conv = _make_conversation(messages=msgs)
        result = ChatService._build_history(conv, "tell me more")

        # user + assistant (structured) + tool_result (user) + final user
        assert len(result) == 4
        # The assistant message should be structured
        assistant_msg = result[1]
        assert assistant_msg["role"] == "assistant"
        assert isinstance(assistant_msg["content"], list)
        assert assistant_msg["content"][0]["type"] == "text"
        assert assistant_msg["content"][1]["type"] == "tool_use"
        # Tool result follows
        assert result[2]["role"] == "user"
        assert isinstance(result[2]["content"], list)
        assert result[2]["content"][0]["type"] == "tool_result"

    def test_tool_use_invalid_json(self):
        """Invalid tool_use JSON falls back to plain content."""
        now = datetime.now(UTC)
        msgs = [
            _make_message(role="assistant", content="text", tool_use="not json", created_at=now),
        ]
        conv = _make_conversation(messages=msgs)
        result = ChatService._build_history(conv, "hello")

        assert len(result) == 2
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "text"

    def test_deduplication_of_latest(self):
        """If last message already matches latest_content, it's not duplicated."""
        now = datetime.now(UTC)
        msgs = [
            _make_message(role="user", content="hello", created_at=now),
        ]
        conv = _make_conversation(messages=msgs)
        result = ChatService._build_history(conv, "hello")

        assert len(result) == 1


# ── API key encryption ──


class TestApiKeyEncryption:
    @patch("src.services.chat_service.encrypt_auth_config")
    def test_encrypt(self, mock_encrypt):
        mock_encrypt.return_value = "encrypted"
        result = ChatService.encrypt_api_key("sk-test")
        mock_encrypt.assert_called_once_with({"api_key": "sk-test"})
        assert result == "encrypted"

    @patch("src.services.chat_service.decrypt_auth_config")
    def test_decrypt(self, mock_decrypt):
        mock_decrypt.return_value = {"api_key": "sk-test"}
        result = ChatService.decrypt_api_key("encrypted")
        assert result == "sk-test"

    @patch("src.services.chat_service.decrypt_auth_config")
    def test_decrypt_missing_key(self, mock_decrypt):
        mock_decrypt.return_value = {}
        result = ChatService.decrypt_api_key("encrypted")
        assert result == ""


# ── send_message streaming ──


class TestSendMessage:
    async def test_conversation_not_found(self):
        session = _make_session()
        svc = ChatService(session)
        svc.get_conversation = AsyncMock(return_value=None)

        events = []
        async for evt in svc.send_message(
            conversation_id=uuid4(), tenant_id="acme", user_id="user-1",
            content="hello", api_key="sk-test",
        ):
            events.append(evt)

        assert len(events) == 1
        assert events[0]["event"] == "error"
        assert "not found" in events[0]["data"]["error"]

    @patch("src.services.chat_service.settings")
    async def test_budget_exceeded(self, mock_settings):
        mock_settings.CHAT_TOKEN_BUDGET_DAILY = 1000

        session = _make_session()
        conv = _make_conversation()
        svc = ChatService(session)
        svc.get_conversation = AsyncMock(return_value=conv)

        with patch("src.services.chat_service.ChatTokenUsageRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_daily_user_usage = AsyncMock(return_value=1500)

            events = []
            async for evt in svc.send_message(
                conversation_id=conv.id, tenant_id="acme", user_id="user-1",
                content="hello", api_key="sk-test",
            ):
                events.append(evt)

        assert len(events) == 1
        assert events[0]["event"] == "error"
        assert "budget" in events[0]["data"]["error"].lower()

    @patch("src.services.chat_service.settings")
    async def test_budget_zero_skips_check(self, mock_settings):
        """Budget of 0 means unlimited — skip budget check."""
        mock_settings.CHAT_TOKEN_BUDGET_DAILY = 0

        session = _make_session()
        conv = _make_conversation()
        svc = ChatService(session)
        svc.get_conversation = AsyncMock(return_value=conv)

        # Mock provider to yield a simple response
        async def mock_stream(**kwargs):
            yield {"event": "content_delta", "data": {"delta": "Hi"}}
            yield {"event": "message_end", "data": {"input_tokens": 10, "output_tokens": 5, "stop_reason": "end_turn"}}

        mock_provider = MagicMock()
        mock_provider.stream_response = mock_stream

        with (
            patch("src.services.chat_service._PROVIDERS", {"anthropic": mock_provider}),
            patch.object(svc, "_emit_metering_event", new_callable=AsyncMock),
        ):
            mock_execute_result = MagicMock()
            session.execute = AsyncMock(return_value=mock_execute_result)

            events = []
            async for evt in svc.send_message(
                conversation_id=conv.id, tenant_id="acme", user_id="user-1",
                content="hello", api_key="sk-test",
            ):
                events.append(evt)

        event_types = [e["event"] for e in events]
        assert "content_delta" in event_types
        assert "message_end" in event_types

    @patch("src.services.chat_service.settings")
    async def test_unknown_provider(self, mock_settings):
        mock_settings.CHAT_TOKEN_BUDGET_DAILY = 0

        session = _make_session()
        conv = _make_conversation(provider="openai")
        svc = ChatService(session)
        svc.get_conversation = AsyncMock(return_value=conv)

        events = []
        async for evt in svc.send_message(
            conversation_id=conv.id, tenant_id="acme", user_id="user-1",
            content="hello", api_key="sk-test",
        ):
            events.append(evt)

        assert len(events) == 1
        assert events[0]["event"] == "error"
        assert "Unknown provider" in events[0]["data"]["error"]

    @patch("src.services.chat_service.settings")
    async def test_auto_title(self, mock_settings):
        """First user message replaces default 'New conversation' title."""
        mock_settings.CHAT_TOKEN_BUDGET_DAILY = 0

        session = _make_session()
        conv = _make_conversation(title="New conversation")
        svc = ChatService(session)
        svc.get_conversation = AsyncMock(return_value=conv)

        async def mock_stream(**kwargs):
            yield {"event": "message_end", "data": {"input_tokens": 5, "output_tokens": 5, "stop_reason": "end_turn"}}

        mock_provider = MagicMock()
        mock_provider.stream_response = mock_stream

        with (
            patch("src.services.chat_service._PROVIDERS", {"anthropic": mock_provider}),
            patch.object(svc, "_emit_metering_event", new_callable=AsyncMock),
        ):
            session.execute = AsyncMock(return_value=MagicMock())
            async for _ in svc.send_message(
                conversation_id=conv.id, tenant_id="acme", user_id="user-1",
                content="How do I deploy an API?", api_key="sk-test",
            ):
                pass

        assert conv.title == "How do I deploy an API?"

    @patch("src.services.chat_service.settings")
    async def test_tool_use_loop(self, mock_settings):
        """Agentic loop: LLM requests tool, tool executes, LLM continues."""
        mock_settings.CHAT_TOKEN_BUDGET_DAILY = 0

        session = _make_session()
        conv = _make_conversation()
        svc = ChatService(session)
        svc.get_conversation = AsyncMock(return_value=conv)

        call_count = 0

        async def mock_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: LLM wants to use a tool
                yield {"event": "tool_use_start", "data": {"tool_use_id": "tu-1", "tool_name": "list_apis"}}
                yield {"event": "tool_input_delta", "data": {"delta": "{}"}}
                yield {"event": "content_block_stop", "data": {"index": 0}}
                yield {"event": "message_end", "data": {"input_tokens": 50, "output_tokens": 20, "stop_reason": "tool_use"}}
            else:
                # Second call: LLM responds with text
                yield {"event": "content_delta", "data": {"delta": "Here are your APIs"}}
                yield {"event": "message_end", "data": {"input_tokens": 100, "output_tokens": 30, "stop_reason": "end_turn"}}

        mock_provider = MagicMock()
        mock_provider.stream_response = mock_stream

        with (
            patch("src.services.chat_service._PROVIDERS", {"anthropic": mock_provider}),
            patch("src.services.chat_service.execute_tool", new_callable=AsyncMock, return_value='[{"name":"api-1"}]'),
            patch.object(svc, "_emit_metering_event", new_callable=AsyncMock),
        ):
            session.execute = AsyncMock(return_value=MagicMock())
            events = []
            async for evt in svc.send_message(
                conversation_id=conv.id, tenant_id="acme", user_id="user-1",
                content="list my apis", api_key="sk-test",
            ):
                events.append(evt)

        event_types = [e["event"] for e in events]
        assert "tool_use_start" in event_types
        assert "tool_use_result" in event_types
        assert "content_delta" in event_types
        assert "message_end" in event_types
        assert call_count == 2


# ── Metering ──


class TestEmitMeteringEvent:
    async def test_emit_success(self):
        mock_kafka = MagicMock()
        mock_kafka.publish = AsyncMock()

        with patch("src.services.kafka_service", mock_kafka):
            await ChatService._emit_metering_event(
                tenant_id="acme",
                user_id="user-1",
                conversation_id="conv-1",
                model="claude-3",
                input_tokens=100,
                output_tokens=50,
            )

        mock_kafka.publish.assert_awaited_once()
        call_kwargs = mock_kafka.publish.call_args[1]
        assert call_kwargs["topic"] == "stoa.chat.tokens_used"
        assert call_kwargs["payload"]["total_tokens"] == 150

    async def test_emit_failure_is_silent(self):
        """Kafka failure is logged but not raised."""
        mock_kafka = MagicMock()
        mock_kafka.publish = AsyncMock(side_effect=Exception("Kafka down"))

        with patch("src.services.kafka_service", mock_kafka):
            # Should not raise
            await ChatService._emit_metering_event(
                tenant_id="acme",
                user_id="user-1",
                conversation_id="conv-1",
                model="claude-3",
                input_tokens=100,
                output_tokens=50,
            )
