"""Tests for Chat Pydantic schemas (CAB-1452).

Validates enums, request/response schemas, SSE event schemas,
and token metering schemas.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.schemas.chat import (
    ChatProvider,
    ChatRole,
    ChatTenantUsageResponse,
    ChatUsageResponse,
    ConversationArchive,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationStatus,
    ConversationUpdate,
    DailyBreakdown,
    MessageResponse,
    MessageSend,
    SSEContentDelta,
    SSEMessageEnd,
    SSEMessageStart,
    SSEToolUseResult,
    SSEToolUseStart,
    TokenBudgetStatusResponse,
    TokenUsageStatsResponse,
    TopUserUsage,
)

# =============================================================================
# Enum Tests
# =============================================================================


class TestChatEnums:
    def test_chat_role_values(self):
        assert ChatRole.USER == "user"
        assert ChatRole.ASSISTANT == "assistant"
        assert ChatRole.SYSTEM == "system"

    def test_chat_provider_values(self):
        assert ChatProvider.ANTHROPIC == "anthropic"

    def test_conversation_status_values(self):
        assert ConversationStatus.ACTIVE == "active"
        assert ConversationStatus.ARCHIVED == "archived"


# =============================================================================
# Request Schemas
# =============================================================================


class TestConversationCreate:
    def test_defaults(self):
        c = ConversationCreate()
        assert c.title == "New conversation"
        assert c.provider == ChatProvider.ANTHROPIC
        assert c.model == "claude-sonnet-4-20250514"
        assert c.system_prompt is None

    def test_custom_values(self):
        c = ConversationCreate(
            title="My Chat",
            model="claude-opus-4-20250514",
            system_prompt="You are helpful.",
        )
        assert c.title == "My Chat"
        assert c.model == "claude-opus-4-20250514"

    def test_title_max_length(self):
        with pytest.raises(ValidationError):
            ConversationCreate(title="x" * 501)

    def test_model_max_length(self):
        with pytest.raises(ValidationError):
            ConversationCreate(model="x" * 101)

    def test_system_prompt_max_length(self):
        with pytest.raises(ValidationError):
            ConversationCreate(system_prompt="x" * 10001)


class TestConversationUpdate:
    def test_valid(self):
        u = ConversationUpdate(title="Renamed")
        assert u.title == "Renamed"

    def test_title_required(self):
        with pytest.raises(ValidationError):
            ConversationUpdate()

    def test_title_min_length(self):
        with pytest.raises(ValidationError):
            ConversationUpdate(title="")


class TestConversationArchive:
    def test_active(self):
        a = ConversationArchive(status=ConversationStatus.ACTIVE)
        assert a.status == ConversationStatus.ACTIVE

    def test_archived(self):
        a = ConversationArchive(status=ConversationStatus.ARCHIVED)
        assert a.status == ConversationStatus.ARCHIVED

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            ConversationArchive(status="deleted")


class TestMessageSend:
    def test_valid(self):
        m = MessageSend(content="Hello")
        assert m.content == "Hello"

    def test_content_required(self):
        with pytest.raises(ValidationError):
            MessageSend()

    def test_content_min_length(self):
        with pytest.raises(ValidationError):
            MessageSend(content="")

    def test_content_max_length(self):
        with pytest.raises(ValidationError):
            MessageSend(content="x" * 100001)


# =============================================================================
# Response Schemas
# =============================================================================


class TestMessageResponse:
    def _sample(self, **overrides):
        defaults = {
            "id": uuid4(),
            "conversation_id": uuid4(),
            "role": "user",
            "content": "Hello",
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        }
        defaults.update(overrides)
        return defaults

    def test_valid(self):
        r = MessageResponse(**self._sample())
        assert r.role == "user"

    def test_optional_fields(self):
        r = MessageResponse(**self._sample())
        assert r.token_count is None
        assert r.tool_use is None

    def test_from_attributes_config(self):
        assert MessageResponse.model_config.get("from_attributes") is True


class TestConversationResponse:
    def _sample(self, **overrides):
        defaults = {
            "id": uuid4(),
            "tenant_id": "acme",
            "user_id": "user-1",
            "title": "Test",
            "provider": "anthropic",
            "model": "claude-sonnet-4-20250514",
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 1, 2, tzinfo=UTC),
        }
        defaults.update(overrides)
        return defaults

    def test_valid(self):
        r = ConversationResponse(**self._sample())
        assert r.status == "active"

    def test_system_prompt_optional(self):
        r = ConversationResponse(**self._sample())
        assert r.system_prompt is None


class TestConversationDetailResponse:
    def test_inherits_conversation_response(self):
        assert issubclass(ConversationDetailResponse, ConversationResponse)

    def test_messages_default_empty(self):
        r = ConversationDetailResponse(
            id=uuid4(),
            tenant_id="acme",
            user_id="user-1",
            title="Test",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        assert r.messages == []


class TestConversationListResponse:
    def test_valid(self):
        r = ConversationListResponse(items=[], total=0)
        assert r.items == []
        assert r.total == 0


# =============================================================================
# Usage Schemas
# =============================================================================


class TestChatUsageResponse:
    def test_valid(self):
        r = ChatUsageResponse(total_conversations=5, total_messages=50, total_tokens=12000)
        assert r.total_conversations == 5


class TestChatTenantUsageResponse:
    def test_valid(self):
        r = ChatTenantUsageResponse(
            tenant_id="acme",
            total_conversations=10,
            total_messages=100,
            total_tokens=50000,
            unique_users=3,
        )
        assert r.unique_users == 3


# =============================================================================
# Token Metering Schemas
# =============================================================================


class TestTokenBudgetStatusResponse:
    def test_valid(self):
        r = TokenBudgetStatusResponse(
            user_tokens_today=1500,
            tenant_tokens_today=8000,
            daily_budget=10000,
            remaining=8500,
            budget_exceeded=False,
            usage_percent=15.0,
        )
        assert r.budget_exceeded is False
        assert r.remaining == 8500


class TestTopUserUsage:
    def test_valid(self):
        r = TopUserUsage(user_id="user-1", tokens=5000)
        assert r.tokens == 5000


class TestDailyBreakdown:
    def test_valid(self):
        r = DailyBreakdown(date="2026-01-15", tokens=3000, requests=42)
        assert r.requests == 42


class TestTokenUsageStatsResponse:
    def test_valid(self):
        r = TokenUsageStatsResponse(
            tenant_id="acme",
            period_days=30,
            total_tokens=100000,
            total_input_tokens=60000,
            total_output_tokens=40000,
            total_requests=500,
            today_tokens=2000,
            top_users=[],
            daily_breakdown=[],
        )
        assert r.total_input_tokens + r.total_output_tokens == r.total_tokens


# =============================================================================
# SSE Event Schemas
# =============================================================================


class TestSSESchemas:
    def test_message_start(self):
        s = SSEMessageStart(message_id="msg-123", model="claude-sonnet-4-20250514")
        assert s.message_id == "msg-123"

    def test_content_delta(self):
        s = SSEContentDelta(delta="Hello")
        assert s.delta == "Hello"

    def test_tool_use_start(self):
        s = SSEToolUseStart(tool_use_id="tu-1", tool_name="list_apis")
        assert s.tool_name == "list_apis"

    def test_tool_use_result(self):
        s = SSEToolUseResult(tool_use_id="tu-1", result='{"apis": []}')
        assert "apis" in s.result

    def test_message_end(self):
        s = SSEMessageEnd(input_tokens=100, output_tokens=50, stop_reason="end_turn")
        assert s.stop_reason == "end_turn"
        assert s.input_tokens + s.output_tokens == 150
