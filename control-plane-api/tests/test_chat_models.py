"""Tests for Chat ORM models — ChatConversation, ChatMessage, ChatTokenUsage (CAB-1452).

Validates column definitions, defaults, indexes, constraints, and relationships
without requiring a running database.
"""

from src.models.chat import ChatConversation, ChatMessage
from src.models.chat_token_usage import ChatTokenUsage

# =============================================================================
# ChatConversation
# =============================================================================


class TestChatConversation:
    def test_tablename(self):
        assert ChatConversation.__tablename__ == "chat_conversations"

    def test_columns_exist(self):
        cols = {c.name for c in ChatConversation.__table__.columns}
        expected = {
            "id",
            "tenant_id",
            "user_id",
            "title",
            "provider",
            "model",
            "system_prompt",
            "status",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)

    def test_primary_key_is_uuid(self):
        pk = ChatConversation.__table__.c.id
        assert pk.primary_key

    def test_tenant_id_not_nullable(self):
        assert not ChatConversation.__table__.c.tenant_id.nullable

    def test_user_id_not_nullable(self):
        assert not ChatConversation.__table__.c.user_id.nullable

    def test_title_max_length(self):
        col = ChatConversation.__table__.c.title
        assert col.type.length == 500

    def test_provider_default(self):
        col = ChatConversation.__table__.c.provider
        assert col.default.arg == "anthropic"

    def test_model_default(self):
        col = ChatConversation.__table__.c.model
        assert col.default.arg == "claude-sonnet-4-20250514"

    def test_system_prompt_nullable(self):
        assert ChatConversation.__table__.c.system_prompt.nullable

    def test_status_default(self):
        col = ChatConversation.__table__.c.status
        assert col.default.arg == "active"

    def test_status_server_default(self):
        col = ChatConversation.__table__.c.status
        assert col.server_default is not None
        assert col.server_default.arg == "active"

    def test_indexes_defined(self):
        idx_names = {idx.name for idx in ChatConversation.__table__.indexes}
        assert "ix_chat_conversations_tenant_user" in idx_names
        assert "ix_chat_conversations_updated" in idx_names

    def test_messages_relationship(self):
        rels = ChatConversation.__mapper__.relationships
        assert "messages" in rels
        assert rels["messages"].cascade.delete_orphan


# =============================================================================
# ChatMessage
# =============================================================================


class TestChatMessage:
    def test_tablename(self):
        assert ChatMessage.__tablename__ == "chat_messages"

    def test_columns_exist(self):
        cols = {c.name for c in ChatMessage.__table__.columns}
        expected = {
            "id",
            "conversation_id",
            "role",
            "content",
            "token_count",
            "tool_use",
            "created_at",
        }
        assert expected.issubset(cols)

    def test_conversation_fk(self):
        col = ChatMessage.__table__.c.conversation_id
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert "chat_conversations.id" in str(fks[0])

    def test_conversation_fk_cascade_delete(self):
        col = ChatMessage.__table__.c.conversation_id
        fk = next(iter(col.foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_role_enum_values(self):
        col = ChatMessage.__table__.c.role
        assert col.type.enums == ["user", "assistant", "system"]

    def test_content_not_nullable(self):
        assert not ChatMessage.__table__.c.content.nullable

    def test_token_count_nullable(self):
        assert ChatMessage.__table__.c.token_count.nullable

    def test_tool_use_nullable(self):
        assert ChatMessage.__table__.c.tool_use.nullable

    def test_indexes_defined(self):
        idx_names = {idx.name for idx in ChatMessage.__table__.indexes}
        assert "ix_chat_messages_conversation" in idx_names
        assert "ix_chat_messages_created" in idx_names

    def test_conversation_relationship(self):
        rels = ChatMessage.__mapper__.relationships
        assert "conversation" in rels


# =============================================================================
# ChatTokenUsage
# =============================================================================


class TestChatTokenUsage:
    def test_tablename(self):
        assert ChatTokenUsage.__tablename__ == "chat_token_usage"

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

    def test_unique_constraint(self):
        constraints = ChatTokenUsage.__table__.constraints
        uq = [c for c in constraints if hasattr(c, "columns") and len(c.columns) == 4]
        assert len(uq) >= 1
        uq_cols = {c.name for c in uq[0].columns}
        assert uq_cols == {"tenant_id", "user_id", "model", "period_date"}

    def test_tenant_id_indexed(self):
        col = ChatTokenUsage.__table__.c.tenant_id
        assert col.index

    def test_token_defaults_zero(self):
        for col_name in ("input_tokens", "output_tokens", "total_tokens", "request_count"):
            col = ChatTokenUsage.__table__.c[col_name]
            assert col.default.arg == 0
