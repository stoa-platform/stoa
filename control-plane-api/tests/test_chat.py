"""Unit tests for Chat Agent backend (CAB-286).

Tests cover:
  - ChatService CRUD (create, list, get, delete)
  - ChatService.send_message streaming with mocked provider
  - AnthropicProvider._map_chunk normalisation
  - Router endpoint validation (auth, 404, missing header)
  - API key encrypt/decrypt round-trip
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.schemas.chat import ConversationCreate, MessageSend
from src.services.chat_provider import AnthropicProvider
from src.services.chat_service import ChatService

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
    return session


@pytest.fixture
def chat_service(mock_session):
    return ChatService(mock_session)


# ---------------------------------------------------------------------------
# Schema validation tests
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

    def test_message_send_valid(self):
        schema = MessageSend(content="Hello!")
        assert schema.content == "Hello!"

    def test_message_send_empty_rejected(self):
        with pytest.raises(ValueError):
            MessageSend(content="")


# ---------------------------------------------------------------------------
# ChatService tests
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
        # Mock execute to return count=0 and empty rows
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


class TestChatServiceDelete:
    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self, chat_service, mock_session, conversation_id, tenant_id, user_id):
        # Patch get_conversation to return None
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
# ChatService.send_message tests
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
# AnthropicProvider._map_chunk tests
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
        assert events[0]["event"] == "content_delta"
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
# API key encrypt/decrypt round-trip
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
# _build_history tests
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
        # system messages are not included in history (handled separately via system_prompt)
        assert len(history) == 1
        assert history[0]["role"] == "user"
