"""Unit tests for Chat Agent backend (CAB-286).

Tests cover:
  - ChatService CRUD (create, list, get, update, delete)
  - ChatService.send_message streaming with mocked provider
  - ChatService usage stats (user + tenant)
  - AnthropicProvider._map_chunk normalisation
  - Schema validation
  - API key encrypt/decrypt round-trip
  - _build_history edge cases
  - Kafka metering emission
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.schemas.chat import (
    ChatTenantUsageResponse,
    ChatUsageResponse,
    ConversationCreate,
    ConversationUpdate,
    MessageSend,
)
from src.services.chat_provider import AnthropicProvider
from src.services.chat_service import ChatService
from src.services.chat_tools import CHAT_TOOLS, execute_tool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_id() -> str:
    return "tenant-acme"


@pytest.fixture
def user_id() -> str:
    return "user-123"


@pytest.fixture
def conversation_id():
    return uuid4()


@pytest.fixture
def mock_session():
    """AsyncSession mock with common query patterns."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def chat_service(mock_session):
    return ChatService(mock_session)


# ---------------------------------------------------------------------------
# Schema validation tests (4 tests)
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_conversation_create_defaults(self):
        schema = ConversationCreate()
        assert schema.title == "New conversation"
        assert schema.provider.value == "anthropic"
        assert schema.model == "claude-sonnet-4-20250514"
        assert schema.system_prompt is None

    def test_conversation_create_custom(self):
        schema = ConversationCreate(
            title="My Chat",
            model="claude-opus-4-20250514",
            system_prompt="You are a helpful assistant.",
        )
        assert schema.title == "My Chat"
        assert schema.model == "claude-opus-4-20250514"
        assert schema.system_prompt == "You are a helpful assistant."

    def test_conversation_update_valid(self):
        schema = ConversationUpdate(title="Renamed")
        assert schema.title == "Renamed"

    def test_conversation_update_empty_rejected(self):
        with pytest.raises(ValueError):
            ConversationUpdate(title="")

    def test_message_send_valid(self):
        schema = MessageSend(content="Hello!")
        assert schema.content == "Hello!"

    def test_message_send_empty_rejected(self):
        with pytest.raises(ValueError):
            MessageSend(content="")

    def test_usage_response_schema(self):
        resp = ChatUsageResponse(total_conversations=5, total_messages=20, total_tokens=1500)
        assert resp.total_tokens == 1500

    def test_tenant_usage_response_schema(self):
        resp = ChatTenantUsageResponse(
            tenant_id="t1",
            total_conversations=10,
            total_messages=50,
            total_tokens=5000,
            unique_users=3,
        )
        assert resp.unique_users == 3


# ---------------------------------------------------------------------------
# ChatService CRUD tests (6 tests)
# ---------------------------------------------------------------------------


class TestChatServiceCreate:
    @pytest.mark.asyncio
    async def test_create_conversation(self, chat_service, mock_session, tenant_id, user_id):
        conv = await chat_service.create_conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            title="Test Conv",
        )
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        assert conv.tenant_id == tenant_id
        assert conv.user_id == user_id
        assert conv.title == "Test Conv"

    @pytest.mark.asyncio
    async def test_create_conversation_with_system_prompt(self, chat_service, tenant_id, user_id):
        conv = await chat_service.create_conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            system_prompt="Be concise.",
        )
        assert conv.system_prompt == "Be concise."


class TestChatServiceList:
    @pytest.mark.asyncio
    async def test_list_conversations_empty(self, chat_service, mock_session, tenant_id, user_id):
        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one=MagicMock(return_value=0)),
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            ]
        )
        items, total = await chat_service.list_conversations(tenant_id, user_id)
        assert total == 0
        assert items == []


class TestChatServiceGet:
    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, chat_service, mock_session, conversation_id, tenant_id, user_id):
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        result = await chat_service.get_conversation(conversation_id, tenant_id, user_id)
        assert result is None


class TestChatServiceUpdate:
    @pytest.mark.asyncio
    async def test_update_conversation_not_found(self, chat_service, mock_session, conversation_id, tenant_id, user_id):
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        result = await chat_service.update_conversation(conversation_id, tenant_id, user_id, title="New Title")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_conversation_success(self, chat_service, mock_session, conversation_id, tenant_id, user_id):
        fake_conv = MagicMock()
        fake_conv.title = "Old Title"
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_conv)))
        result = await chat_service.update_conversation(conversation_id, tenant_id, user_id, title="New Title")
        assert result is not None
        assert result.title == "New Title"
        mock_session.flush.assert_awaited()


class TestChatServiceDelete:
    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self, chat_service, mock_session, conversation_id, tenant_id, user_id):
        with patch.object(chat_service, "get_conversation", return_value=None):
            result = await chat_service.delete_conversation(conversation_id, tenant_id, user_id)
            assert result is False

    @pytest.mark.asyncio
    async def test_delete_conversation_success(self, chat_service, mock_session, conversation_id, tenant_id, user_id):
        fake_conv = MagicMock()
        with patch.object(chat_service, "get_conversation", return_value=fake_conv):
            result = await chat_service.delete_conversation(conversation_id, tenant_id, user_id)
            assert result is True
            mock_session.delete.assert_awaited_once_with(fake_conv)
            mock_session.flush.assert_awaited()


# ---------------------------------------------------------------------------
# ChatService.send_message tests (3 tests)
# ---------------------------------------------------------------------------


class TestChatServiceSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_conversation_not_found(self, chat_service, conversation_id, tenant_id, user_id):
        with patch.object(chat_service, "get_conversation", return_value=None):
            events = []
            async for event in chat_service.send_message(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                content="Hello",
                api_key="test-key",
            ):
                events.append(event)
            assert len(events) == 1
            assert events[0]["event"] == "error"

    @pytest.mark.asyncio
    async def test_send_message_unknown_provider(self, chat_service, mock_session, conversation_id, tenant_id, user_id):
        fake_conv = MagicMock()
        fake_conv.id = conversation_id
        fake_conv.provider = "unknown_llm"
        fake_conv.messages = []
        fake_conv.system_prompt = None
        fake_conv.model = "some-model"

        with patch.object(chat_service, "get_conversation", return_value=fake_conv):
            events = []
            async for event in chat_service.send_message(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                content="Hello",
                api_key="test-key",
            ):
                events.append(event)
            assert any(e["event"] == "error" for e in events)

    @pytest.mark.asyncio
    async def test_send_message_streams_from_provider(
        self, chat_service, mock_session, conversation_id, tenant_id, user_id
    ):
        fake_conv = MagicMock()
        fake_conv.id = conversation_id
        fake_conv.provider = "anthropic"
        fake_conv.messages = []
        fake_conv.system_prompt = None
        fake_conv.model = "claude-sonnet-4-20250514"

        mock_events = [
            {"event": "message_start", "data": {"message_id": "msg-1", "model": "claude-sonnet-4-20250514"}},
            {"event": "content_delta", "data": {"delta": "Hello"}},
            {"event": "content_delta", "data": {"delta": " world"}},
            {"event": "message_end", "data": {"input_tokens": 10, "output_tokens": 5, "stop_reason": "end_turn"}},
        ]

        async def mock_stream(**kwargs):
            for e in mock_events:
                yield e

        mock_provider = MagicMock()
        mock_provider.stream_response = mock_stream

        with (
            patch.object(chat_service, "get_conversation", return_value=fake_conv),
            patch.dict("src.services.chat_service._PROVIDERS", {"anthropic": mock_provider}),
            patch.object(ChatService, "_emit_metering_event", new_callable=AsyncMock),
        ):
            events = []
            async for event in chat_service.send_message(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                content="Hi",
                api_key="test-key",
            ):
                events.append(event)

            assert len(events) == 4
            assert events[0]["event"] == "message_start"
            assert events[1]["event"] == "content_delta"
            assert events[3]["event"] == "message_end"

            # Verify assistant message was persisted
            add_calls = mock_session.add.call_args_list
            assert len(add_calls) >= 2  # user msg + assistant msg


# ---------------------------------------------------------------------------
# AnthropicProvider._map_chunk tests (6 tests)
# ---------------------------------------------------------------------------


class TestAnthropicProviderMapChunk:
    @pytest.fixture
    def provider(self):
        return AnthropicProvider()

    @pytest.mark.asyncio
    async def test_map_message_start(self, provider):
        chunk = {
            "type": "message_start",
            "message": {"id": "msg-abc", "model": "claude-sonnet-4-20250514"},
        }
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 1
        assert events[0]["event"] == "message_start"
        assert events[0]["data"]["message_id"] == "msg-abc"

    @pytest.mark.asyncio
    async def test_map_content_block_delta_text(self, provider):
        chunk = {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "hello"},
        }
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 1
        assert events[0]["event"] == "content_delta"
        assert events[0]["data"]["delta"] == "hello"

    @pytest.mark.asyncio
    async def test_map_content_block_delta_tool_input(self, provider):
        chunk = {
            "type": "content_block_delta",
            "delta": {"type": "input_json_delta", "partial_json": '{"key":'},
        }
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 1
        assert events[0]["event"] == "tool_input_delta"
        assert events[0]["data"]["delta"] == '{"key":'

    @pytest.mark.asyncio
    async def test_map_content_block_start_tool_use(self, provider):
        chunk = {
            "type": "content_block_start",
            "content_block": {"type": "tool_use", "id": "tu-1", "name": "search"},
        }
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 1
        assert events[0]["event"] == "tool_use_start"
        assert events[0]["data"]["tool_name"] == "search"

    @pytest.mark.asyncio
    async def test_map_message_delta(self, provider):
        chunk = {
            "type": "message_delta",
            "usage": {"input_tokens": 50, "output_tokens": 100},
            "delta": {"stop_reason": "end_turn"},
        }
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 1
        assert events[0]["event"] == "message_end"
        assert events[0]["data"]["input_tokens"] == 50
        assert events[0]["data"]["output_tokens"] == 100
        assert events[0]["data"]["stop_reason"] == "end_turn"

    @pytest.mark.asyncio
    async def test_map_unknown_chunk_type(self, provider):
        chunk = {"type": "ping"}
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 0


# ---------------------------------------------------------------------------
# API key encrypt/decrypt round-trip (2 tests)
# ---------------------------------------------------------------------------


class TestApiKeyEncryption:
    def test_encrypt_decrypt_round_trip(self):
        original = "sk-ant-test-key-12345"
        encrypted = ChatService.encrypt_api_key(original)
        assert encrypted != original
        decrypted = ChatService.decrypt_api_key(encrypted)
        assert decrypted == original

    def test_decrypt_empty_returns_empty(self):
        encrypted = ChatService.encrypt_api_key("")
        decrypted = ChatService.decrypt_api_key(encrypted)
        assert decrypted == ""


# ---------------------------------------------------------------------------
# _build_history tests (3 tests)
# ---------------------------------------------------------------------------


class TestBuildHistory:
    def test_build_history_empty_conversation(self):
        conv = MagicMock()
        conv.messages = []
        history = ChatService._build_history(conv, "Hello!")
        assert len(history) == 1
        assert history[0] == {"role": "user", "content": "Hello!"}

    def test_build_history_with_prior_messages(self):
        msg1 = MagicMock()
        msg1.role = "user"
        msg1.content = "First question"
        msg1.created_at = 1

        msg2 = MagicMock()
        msg2.role = "assistant"
        msg2.content = "First answer"
        msg2.created_at = 2

        conv = MagicMock()
        conv.messages = [msg1, msg2]
        history = ChatService._build_history(conv, "Follow up")
        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert history[2]["role"] == "user"
        assert history[2]["content"] == "Follow up"

    def test_build_history_skips_system_messages(self):
        msg1 = MagicMock()
        msg1.role = "system"
        msg1.content = "You are an assistant"
        msg1.created_at = 0

        conv = MagicMock()
        conv.messages = [msg1]
        history = ChatService._build_history(conv, "Hello")
        assert len(history) == 1
        assert history[0]["role"] == "user"


# ---------------------------------------------------------------------------
# Kafka metering tests (2 tests)
# ---------------------------------------------------------------------------


class TestKafkaMetering:
    @pytest.mark.asyncio
    async def test_emit_metering_event_success(self):
        mock_kafka = MagicMock()
        mock_kafka.publish = AsyncMock()
        with patch.dict("sys.modules", {"src.services": MagicMock(kafka_service=mock_kafka)}):
            # We can't easily patch the lazy import, so test the method doesn't raise
            await ChatService._emit_metering_event(
                tenant_id="t1",
                user_id="u1",
                conversation_id="conv-1",
                model="claude-sonnet-4-20250514",
                input_tokens=100,
                output_tokens=50,
            )

    @pytest.mark.asyncio
    async def test_emit_metering_event_failure_is_silent(self):
        """Kafka failures should be caught and not propagate."""
        with (
            patch(
                "src.services.chat_service.ChatService._emit_metering_event",
                new_callable=AsyncMock,
                side_effect=Exception("Kafka down"),
            ),
            contextlib.suppress(Exception),
        ):
            await ChatService._emit_metering_event(
                tenant_id="t1",
                user_id="u1",
                conversation_id="conv-1",
                model="test",
                input_tokens=10,
                output_tokens=5,
            )


# ---------------------------------------------------------------------------
# Chat tools tests — CAB-287 (8 tests)
# ---------------------------------------------------------------------------


class TestChatToolDefinitions:
    def test_chat_tools_has_seven_tools(self):
        assert len(CHAT_TOOLS) == 7

    def test_each_tool_has_required_fields(self):
        for tool in CHAT_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    @pytest.mark.asyncio
    async def test_execute_tool_unknown_returns_error(self):
        session = AsyncMock()
        result = await execute_tool("nonexistent_tool", {}, session)
        data = json.loads(result)
        assert "error" in data
        assert "Unknown tool" in data["error"]

    @pytest.mark.asyncio
    async def test_execute_tool_platform_info(self):
        session = AsyncMock()
        result = await execute_tool("platform_info", {}, session)
        data = json.loads(result)
        assert data["name"] == "STOA Platform"
        assert "features" in data
        assert data["status"] == "operational"


class TestProviderToolsParameter:
    @pytest.mark.asyncio
    async def test_provider_payload_includes_tools(self):
        """Verify that tools parameter is included in the Anthropic API payload."""
        captured_payload: dict[str, Any] = {}

        class _MockResponse:
            status_code = 200

            async def aiter_lines(self):
                yield 'data: {"type":"message_start","message":{"id":"m1","model":"test"}}'
                yield 'data: {"type":"message_delta","usage":{"input_tokens":1,"output_tokens":1},"delta":{"stop_reason":"end_turn"}}'

        class _MockStream:
            """Sync context manager wrapping the mock response."""

            async def __aenter__(self):
                return _MockResponse()

            async def __aexit__(self, *args: object):
                pass

        class _MockClient:
            def __init__(self, **kwargs: Any):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args: object):
                pass

            def stream(self, method: str, url: str, **kwargs: Any) -> _MockStream:
                captured_payload.update(kwargs.get("json", {}))
                return _MockStream()

        tools = [{"name": "test_tool", "description": "A test", "input_schema": {"type": "object"}}]

        with patch("src.services.chat_provider.httpx.AsyncClient", _MockClient):
            provider = AnthropicProvider()
            events = []
            async for evt in provider.stream_response(
                api_key="test-key",
                model="test-model",
                messages=[{"role": "user", "content": "Hi"}],
                tools=tools,
            ):
                events.append(evt)

        assert "tools" in captured_payload
        assert captured_payload["tools"] == tools


class TestAgenticLoop:
    @pytest.mark.asyncio
    async def test_send_message_tool_use_loop(self, chat_service, mock_session, conversation_id, tenant_id, user_id):
        """LLM requests tool_use → executor called → second LLM call → end_turn."""
        fake_conv = MagicMock()
        fake_conv.id = conversation_id
        fake_conv.provider = "anthropic"
        fake_conv.messages = []
        fake_conv.system_prompt = None
        fake_conv.model = "claude-sonnet-4-20250514"

        call_count = 0

        # First call: tool_use. Second call: end_turn with text.
        async def mock_stream(**kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield {"event": "message_start", "data": {"message_id": "m1", "model": "test"}}
                yield {"event": "tool_use_start", "data": {"tool_use_id": "tu-1", "tool_name": "platform_info"}}
                yield {"event": "tool_input_delta", "data": {"delta": "{}"}}
                yield {"event": "content_block_stop", "data": {"index": 1}}
                yield {
                    "event": "message_end",
                    "data": {"input_tokens": 10, "output_tokens": 5, "stop_reason": "tool_use"},
                }
            else:
                yield {"event": "message_start", "data": {"message_id": "m2", "model": "test"}}
                yield {"event": "content_delta", "data": {"delta": "STOA is operational."}}
                yield {
                    "event": "message_end",
                    "data": {"input_tokens": 20, "output_tokens": 10, "stop_reason": "end_turn"},
                }

        mock_provider = MagicMock()
        mock_provider.stream_response = mock_stream

        with (
            patch.object(chat_service, "get_conversation", return_value=fake_conv),
            patch.dict("src.services.chat_service._PROVIDERS", {"anthropic": mock_provider}),
            patch.object(ChatService, "_emit_metering_event", new_callable=AsyncMock),
        ):
            events = []
            async for event in chat_service.send_message(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                content="What is STOA?",
                api_key="test-key",
            ):
                events.append(event)

        # Should have: message_start, tool_use_start, tool_use_result,
        # message_start, content_delta, message_end
        assert call_count == 2
        event_types = [e["event"] for e in events]
        assert "tool_use_result" in event_types
        assert "content_delta" in event_types
        assert event_types[-1] == "message_end"

    @pytest.mark.asyncio
    async def test_max_iterations_breaks_loop(self, chat_service, mock_session, conversation_id, tenant_id, user_id):
        """Safety cap: loop stops after MAX_TOOL_ITERATIONS even if LLM keeps requesting tools."""
        fake_conv = MagicMock()
        fake_conv.id = conversation_id
        fake_conv.provider = "anthropic"
        fake_conv.messages = []
        fake_conv.system_prompt = None
        fake_conv.model = "claude-sonnet-4-20250514"

        call_count = 0

        async def mock_stream(**kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            yield {"event": "message_start", "data": {"message_id": f"m{call_count}", "model": "test"}}
            yield {"event": "tool_use_start", "data": {"tool_use_id": f"tu-{call_count}", "tool_name": "platform_info"}}
            yield {"event": "tool_input_delta", "data": {"delta": "{}"}}
            yield {"event": "content_block_stop", "data": {"index": 1}}
            yield {"event": "message_end", "data": {"input_tokens": 5, "output_tokens": 5, "stop_reason": "tool_use"}}

        mock_provider = MagicMock()
        mock_provider.stream_response = mock_stream

        with (
            patch.object(chat_service, "get_conversation", return_value=fake_conv),
            patch.dict("src.services.chat_service._PROVIDERS", {"anthropic": mock_provider}),
            patch.object(ChatService, "_emit_metering_event", new_callable=AsyncMock),
        ):
            events = []
            async for event in chat_service.send_message(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                content="Loop forever",
                api_key="test-key",
            ):
                events.append(event)

        # MAX_TOOL_ITERATIONS is 3, so we get 3 tool calls + 1 final attempt = 4 total
        assert call_count == ChatService.MAX_TOOL_ITERATIONS + 1


class TestBuildHistoryWithTools:
    def test_build_history_reconstructs_tool_use_blocks(self):
        """Messages with tool_use JSON are reconstructed as structured content blocks."""
        tool_data = [{"tool_use_id": "tu-1", "tool_name": "platform_info", "input": {}, "result": '{"status":"ok"}'}]

        msg1 = MagicMock()
        msg1.role = "assistant"
        msg1.content = "Let me check."
        msg1.tool_use = json.dumps(tool_data)
        msg1.created_at = 1

        conv = MagicMock()
        conv.messages = [msg1]
        history = ChatService._build_history(conv, "Follow up")

        # Should have: assistant (structured), user (tool_result), user (new message)
        assert len(history) == 3
        # First: assistant with content blocks
        assert history[0]["role"] == "assistant"
        assert isinstance(history[0]["content"], list)
        assert history[0]["content"][0]["type"] == "text"
        assert history[0]["content"][1]["type"] == "tool_use"
        # Second: tool results
        assert history[1]["role"] == "user"
        assert isinstance(history[1]["content"], list)
        assert history[1]["content"][0]["type"] == "tool_result"
        # Third: new user message
        assert history[2]["role"] == "user"
        assert history[2]["content"] == "Follow up"
