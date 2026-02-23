"""Chat service — business logic for conversations and message streaming (CAB-286).

Orchestrates conversation CRUD, message persistence, provider streaming,
Kafka metering events, and usage statistics.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy import distinct, func, select, update
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

    async def update_conversation(
        self,
        conversation_id: UUID,
        tenant_id: str,
        user_id: str,
        *,
        title: str,
    ) -> ChatConversation | None:
        q = select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.tenant_id == tenant_id,
            ChatConversation.user_id == user_id,
        )
        conv = (await self.session.execute(q)).scalar_one_or_none()
        if conv is None:
            return None
        conv.title = title
        await self.session.flush()
        return conv

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
    # Usage statistics
    # ------------------------------------------------------------------

    async def get_user_usage(self, tenant_id: str, user_id: str) -> dict[str, int]:
        """Return token usage stats for a single user."""
        conv_count_q = select(func.count()).select_from(
            select(ChatConversation.id)
            .where(
                ChatConversation.tenant_id == tenant_id,
                ChatConversation.user_id == user_id,
            )
            .subquery()
        )
        total_conversations = (await self.session.execute(conv_count_q)).scalar_one()

        msg_q = (
            select(
                func.count(ChatMessage.id), func.coalesce(func.sum(func.cast(ChatMessage.token_count, func.text())), 0)
            )
            .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
            .where(
                ChatConversation.tenant_id == tenant_id,
                ChatConversation.user_id == user_id,
            )
        )
        row = (await self.session.execute(msg_q)).one()
        return {
            "total_conversations": total_conversations,
            "total_messages": row[0],
            "total_tokens": int(row[1]) if row[1] else 0,
        }

    async def get_tenant_usage(self, tenant_id: str) -> dict[str, Any]:
        """Return token usage stats for an entire tenant (admin)."""
        conv_count_q = select(func.count()).select_from(
            select(ChatConversation.id).where(ChatConversation.tenant_id == tenant_id).subquery()
        )
        total_conversations = (await self.session.execute(conv_count_q)).scalar_one()

        msg_q = (
            select(
                func.count(ChatMessage.id), func.coalesce(func.sum(func.cast(ChatMessage.token_count, func.text())), 0)
            )
            .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
            .where(ChatConversation.tenant_id == tenant_id)
        )
        row = (await self.session.execute(msg_q)).one()

        users_q = select(func.count(distinct(ChatConversation.user_id))).where(ChatConversation.tenant_id == tenant_id)
        unique_users = (await self.session.execute(users_q)).scalar_one()

        return {
            "tenant_id": tenant_id,
            "total_conversations": total_conversations,
            "total_messages": row[0],
            "total_tokens": int(row[1]) if row[1] else 0,
            "unique_users": unique_users,
        }

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
        total_tokens = input_tokens + output_tokens
        assistant_msg = ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            content="".join(full_text),
            token_count=str(total_tokens) if total_tokens else None,
        )
        self.session.add(assistant_msg)

        # Touch conversation updated_at
        await self.session.execute(
            update(ChatConversation).where(ChatConversation.id == conv.id).values(updated_at=func.now())
        )
        await self.session.flush()

        # Emit Kafka metering event (best-effort, non-blocking)
        if total_tokens:
            await self._emit_metering_event(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=str(conv.id),
                model=conv.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

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
        """Build the message list for the provider from persisted messages."""
        msgs: list[dict[str, str]] = []
        if conv.messages:
            for m in sorted(conv.messages, key=lambda x: x.created_at):
                if m.role in ("user", "assistant"):
                    msgs.append({"role": m.role, "content": m.content})
        if not msgs or msgs[-1].get("content") != latest_content:
            msgs.append({"role": "user", "content": latest_content})
        return msgs

    @staticmethod
    async def _emit_metering_event(
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Emit a chat.tokens_used Kafka event (best-effort)."""
        try:
            from ..services import kafka_service

            await kafka_service.publish(
                topic="stoa.chat.tokens_used",
                event_type="chat.tokens_used",
                tenant_id=tenant_id,
                user_id=user_id,
                payload={
                    "conversation_id": conversation_id,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            )
        except Exception:
            logger.warning("Failed to emit chat metering event", exc_info=True)
