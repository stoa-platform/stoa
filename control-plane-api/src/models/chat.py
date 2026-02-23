"""SQLAlchemy models for Chat Agent conversations and messages (CAB-286)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=False, default="New conversation")
    provider = Column(String(50), nullable=False, default="anthropic")
    model = Column(String(100), nullable=False, default="claude-sonnet-4-20250514")
    system_prompt = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_chat_conversations_tenant_user", "tenant_id", "user_id"),
        Index("ix_chat_conversations_updated", "updated_at"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(SAEnum("user", "assistant", "system", name="chat_message_role"), nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(String(50), nullable=True)
    tool_use = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    conversation = relationship("ChatConversation", back_populates="messages")

    __table_args__ = (
        Index("ix_chat_messages_conversation", "conversation_id"),
        Index("ix_chat_messages_created", "created_at"),
    )
