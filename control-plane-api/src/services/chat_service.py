"""Chat service — business logic for conversations and message streaming (CAB-286).

Orchestrates conversation CRUD, message persistence, provider API key
resolution (encrypted per-tenant), and SSE fan-out.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.chat import ChatConversation, ChatMessage
from ..services.chat_provider import AnthropicProvider, ChatProviderProtocol
from ..services.encryption_service import decrypt_auth_config, encrypt_auth_config

logger = logging.getLogger(__name__)

# Provider registry — extend when adding new LLM backends
_PROVIDERS: dict[str, ChatProviderProtocol] = {
    "anthropic": AnthropicProvider(),
}


class ChatService:
    """Stateless service; receives a DB session per call."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Conversation CRUD
    # ------------------------------------------------------------------

    async def create_conversation(
        self,
        *,
        tenant_id: str,
        user_id: str,
        title: str = "New conversation",
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-20250514",
        system_prompt: str | None = None,
    ) -> ChatConversation:
        conv = ChatConversation(
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
            provider=provider,
            model=model,
            system_prompt=system_prompt,
        )
        self.session.add(conv)
        await self.session.flush()
        return conv

    async def list_conversations(
        self,
        tenant_id: str,
        user_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ChatConversation], int]:
        base = select(ChatConversation).where(
            ChatConversation.tenant_id == tenant_id,
            ChatConversation.user_id == user_id,
        )

        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        rows_q = base.order_by(ChatConversation.updated_at.desc()).offset(offset).limit(limit)
        rows = (await self.session.execute(rows_q)).scalars().all()
        return list(rows), total

    async def get_conversation(
        self,
        conversation_id: UUID,
        tenant_id: str,
        user_id: str,
    ) -> ChatConversation | None:
        q = (
            select(ChatConversation)
            .options(selectinload(ChatConversation.messages))
            .where(
                ChatConversation.id == conversation_id,
                ChatConversation.tenant_id == tenant_id,
                ChatConversation.user_id == user_id,
            )
        )
        return (await self.session.execute(q)).scalar_one_or_none()

    async def delete_conversation(
        self,
        conversation_id: UUID,
        tenant_id: str,
        user_id: str,
    ) -> bool:
        conv = await self.get_conversation(conversation_id, tenant_id, user_id)
        if conv is None:
            return False
        await self.session.delete(conv)
        await self.session.flush()
        return True

    # ------------------------------------------------------------------
    # Message streaming
    # ------------------------------------------------------------------

    async def send_message(
        self,
        *,
        conversation_id: UUID,
        tenant_id: str,
        user_id: str,
        content: str,
        api_key: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Persist user message, call provider, persist + stream assistant reply."""

        conv = await self.get_conversation(conversation_id, tenant_id, user_id)
        if conv is None:
            yield {"event": "error", "data": {"error": "Conversation not found"}}
            return

        # Persist the user message
        user_msg = ChatMessage(
            conversation_id=conv.id,
            role="user",
            content=content,
        )
        self.session.add(user_msg)
        await self.session.flush()

        # Build message history for the provider
        history = self._build_history(conv, content)

        provider = _PROVIDERS.get(conv.provider)
        if provider is None:
            yield {"event": "error", "data": {"error": f"Unknown provider: {conv.provider}"}}
            return

        # Stream from LLM and accumulate the assistant response
        full_text: list[str] = []
        input_tokens = 0
        output_tokens = 0

        async for event in provider.stream_response(
            api_key=api_key,
            model=conv.model,
            messages=history,
            system_prompt=conv.system_prompt,
        ):
            yield event

            if event.get("event") == "content_delta":
                full_text.append(event["data"].get("delta", ""))

            if event.get("event") == "message_end":
                input_tokens = event["data"].get("input_tokens", 0)
                output_tokens = event["data"].get("output_tokens", 0)

        # Persist assistant message
        assistant_msg = ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            content="".join(full_text),
            token_count=str(input_tokens + output_tokens) if (input_tokens or output_tokens) else None,
        )
        self.session.add(assistant_msg)

        # Touch conversation updated_at
        await self.session.execute(
            update(ChatConversation).where(ChatConversation.id == conv.id).values(updated_at=func.now())
        )
        await self.session.flush()

    # ------------------------------------------------------------------
    # Tenant API key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def encrypt_api_key(api_key: str) -> str:
        """Encrypt a provider API key for DB storage."""
        return encrypt_auth_config({"api_key": api_key})

    @staticmethod
    def decrypt_api_key(encrypted: str) -> str:
        """Decrypt a provider API key from DB storage."""
        data = decrypt_auth_config(encrypted)
        return data.get("api_key", "")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_history(conv: ChatConversation, latest_content: str) -> list[dict[str, str]]:
        """Build the message list for the provider from persisted messages + the new user message."""
        msgs: list[dict[str, str]] = []
        if conv.messages:
            for m in sorted(conv.messages, key=lambda x: x.created_at):
                if m.role in ("user", "assistant"):
                    msgs.append({"role": m.role, "content": m.content})
        # Append the latest user message (already persisted but in sorted order
        # the flush may not have committed ordering yet)
        if not msgs or msgs[-1].get("content") != latest_content:
            msgs.append({"role": "user", "content": latest_content})
        return msgs
