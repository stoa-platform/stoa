"""Pydantic schemas for Chat Agent API (CAB-286)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatProvider(StrEnum):
    ANTHROPIC = "anthropic"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ConversationCreate(BaseModel):
    """Create a new conversation."""

    title: str = Field(default="New conversation", max_length=500)
    provider: ChatProvider = ChatProvider.ANTHROPIC
    model: str = Field(default="claude-sonnet-4-20250514", max_length=100)
    system_prompt: str | None = Field(default=None, max_length=10000)


class ConversationUpdate(BaseModel):
    """Rename / update a conversation."""

    title: str = Field(..., min_length=1, max_length=500)


class MessageSend(BaseModel):
    """Send a message in a conversation."""

    content: str = Field(..., min_length=1, max_length=100000)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class MessageResponse(BaseModel):
    """Single chat message."""

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    token_count: str | None = None
    tool_use: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationResponse(BaseModel):
    """Conversation metadata (without messages)."""

    id: UUID
    tenant_id: str
    user_id: str
    title: str
    provider: str
    model: str
    system_prompt: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(ConversationResponse):
    """Conversation with messages included."""

    messages: list[MessageResponse] = []


class ConversationListResponse(BaseModel):
    """Paginated list of conversations."""

    items: list[ConversationResponse]
    total: int


# ---------------------------------------------------------------------------
# Usage schemas
# ---------------------------------------------------------------------------


class ChatUsageResponse(BaseModel):
    """Token usage stats for a user."""

    total_conversations: int
    total_messages: int
    total_tokens: int


class ChatTenantUsageResponse(BaseModel):
    """Token usage stats for an entire tenant (admin)."""

    tenant_id: str
    total_conversations: int
    total_messages: int
    total_tokens: int
    unique_users: int


# ---------------------------------------------------------------------------
# SSE event schemas
# ---------------------------------------------------------------------------


class SSEMessageStart(BaseModel):
    """SSE: message_start — emitted once at the start of assistant reply."""

    message_id: str
    model: str


class SSEContentDelta(BaseModel):
    """SSE: content_delta — incremental text token."""

    delta: str


class SSEToolUseStart(BaseModel):
    """SSE: tool_use_start — beginning of a tool call block."""

    tool_use_id: str
    tool_name: str


class SSEToolUseResult(BaseModel):
    """SSE: tool_use_result — result from a tool call."""

    tool_use_id: str
    result: str


class SSEMessageEnd(BaseModel):
    """SSE: message_end — final event with token usage."""

    input_tokens: int
    output_tokens: int
    stop_reason: str
