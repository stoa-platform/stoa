"""Tests for chat audit logging (CAB-1654).

Verifies that tool calls, jailbreak detection, and conversation lifecycle
events produce immutable audit records via the existing AuditService.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.models.audit_event import AuditAction
from src.services.chat_service import ChatService

# ── Fixtures ──


def _make_session():
    """Create a mock AsyncSession with standard query result patterns."""
    session = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_conversation(
    *,
    conv_id=None,
    tenant_id="acme",
    user_id="user-1",
    title="Test conv",
    provider="anthropic",
    model="claude-sonnet-4-20250514",
    status="active",
    messages=None,
    session_fingerprint=None,
    last_active_at=None,
):
    conv = MagicMock()
    conv.id = conv_id or uuid4()
    conv.tenant_id = tenant_id
    conv.user_id = user_id
    conv.title = title
    conv.provider = provider
    conv.model = model
    conv.status = status
    conv.system_prompt = None
    conv.messages = messages or []
    conv.updated_at = datetime.now(UTC)
    conv.session_fingerprint = session_fingerprint
    conv.last_active_at = last_active_at if last_active_at is not None else datetime.now(UTC)
    return conv


# ── Enum Tests ──


class TestAuditActions:
    def test_chat_actions_exist(self):
        assert AuditAction.CHAT_MESSAGE == "chat_message"
        assert AuditAction.CHAT_TOOL_CALL == "chat_tool_call"
        assert AuditAction.CHAT_CONVERSATION_CREATE == "chat_conversation_create"
        assert AuditAction.CHAT_CONVERSATION_DELETE == "chat_conversation_delete"
        assert AuditAction.CHAT_CONVERSATION_PURGE == "chat_conversation_purge"


# ── Tool Call Audit Tests ──


class TestToolCallAudit:
    @pytest.fixture()
    def _setup(self):
        self.session = _make_session()
        self.svc = ChatService(self.session)
        self.conv = _make_conversation()

    @pytest.mark.usefixtures("_setup")
    async def test_tool_call_creates_audit_event(self):
        """Tool execution during agentic loop produces an audit record."""
        with (
            patch.object(self.svc, "get_conversation", return_value=self.conv),
            patch("src.services.chat_service.ChatTokenUsageRepository"),
            patch("src.services.chat_service.detect_jailbreak", return_value=None),
            patch("src.services.chat_service.build_system_prompt", return_value="sys"),
            patch("src.services.chat_service.filter_tools_for_role", return_value=[]),
            patch("src.services.chat_service.execute_tool", return_value='{"result": "ok"}'),
            patch("src.services.chat_service.sanitize_tool_output", return_value="ok"),
            patch.object(self.svc, "_audit", new_callable=AsyncMock) as mock_audit,
        ):
            # Simulate provider returning tool_use then end_turn
            tool_events = [
                {"event": "tool_use_start", "data": {"tool_use_id": "t1", "tool_name": "list_apis"}},
                {"event": "tool_input_delta", "data": {"delta": '{"tenant_id": "acme"}'}},
                {"event": "content_block_stop", "data": {}},
                {"event": "message_end", "data": {"stop_reason": "tool_use", "input_tokens": 10, "output_tokens": 5}},
            ]
            final_events = [
                {"event": "content_delta", "data": {"delta": "Here are your APIs"}},
                {"event": "message_end", "data": {"stop_reason": "end_turn", "input_tokens": 20, "output_tokens": 15}},
            ]

            async def fake_stream(**kwargs):
                for e in tool_events:
                    yield e

            async def fake_stream_final(**kwargs):
                for e in final_events:
                    yield e

            call_count = 0

            async def multi_stream(**kwargs):
                nonlocal call_count
                if call_count == 0:
                    call_count += 1
                    async for e in fake_stream(**kwargs):
                        yield e
                else:
                    async for e in fake_stream_final(**kwargs):
                        yield e

            mock_provider = MagicMock()
            mock_provider.stream_response = multi_stream

            with patch("src.services.chat_service._PROVIDERS", {"anthropic": mock_provider}):
                events = []
                async for event in self.svc.send_message(
                    conversation_id=self.conv.id,
                    tenant_id="acme",
                    user_id="user-1",
                    content="Show my APIs",
                    api_key="test-key",
                    user_roles=["viewer"],
                    client_ip="10.0.0.1",
                ):
                    events.append(event)

            # Verify audit was called for the tool execution
            mock_audit.assert_any_call(
                tenant_id="acme",
                user_id="user-1",
                action="chat_tool_call",
                resource_type="chat_tool",
                resource_name="list_apis",
                resource_id=str(self.conv.id),
                outcome="success",
                client_ip="10.0.0.1",
                details={"tool_name": "list_apis", "input_keys": ["tenant_id"]},
            )

    @pytest.mark.usefixtures("_setup")
    async def test_tool_call_failure_records_failure_outcome(self):
        """Tool returning error string produces outcome='failure'."""
        with (
            patch.object(self.svc, "get_conversation", return_value=self.conv),
            patch("src.services.chat_service.ChatTokenUsageRepository"),
            patch("src.services.chat_service.detect_jailbreak", return_value=None),
            patch("src.services.chat_service.build_system_prompt", return_value="sys"),
            patch("src.services.chat_service.filter_tools_for_role", return_value=[]),
            patch("src.services.chat_service.execute_tool", return_value='{"error": "not found"}'),
            patch("src.services.chat_service.sanitize_tool_output", return_value="error"),
            patch.object(self.svc, "_audit", new_callable=AsyncMock) as mock_audit,
        ):
            tool_events = [
                {"event": "tool_use_start", "data": {"tool_use_id": "t1", "tool_name": "search_docs"}},
                {"event": "tool_input_delta", "data": {"delta": "{}"}},
                {"event": "content_block_stop", "data": {}},
                {"event": "message_end", "data": {"stop_reason": "tool_use", "input_tokens": 10, "output_tokens": 5}},
            ]
            final_events = [
                {"event": "content_delta", "data": {"delta": "Sorry"}},
                {"event": "message_end", "data": {"stop_reason": "end_turn", "input_tokens": 20, "output_tokens": 15}},
            ]

            call_count = 0

            async def multi_stream(**kwargs):
                nonlocal call_count
                if call_count == 0:
                    call_count += 1
                    for e in tool_events:
                        yield e
                else:
                    for e in final_events:
                        yield e

            mock_provider = MagicMock()
            mock_provider.stream_response = multi_stream

            with patch("src.services.chat_service._PROVIDERS", {"anthropic": mock_provider}):
                async for _ in self.svc.send_message(
                    conversation_id=self.conv.id,
                    tenant_id="acme",
                    user_id="user-1",
                    content="search",
                    api_key="key",
                    user_roles=["viewer"],
                    client_ip="10.0.0.1",
                ):
                    pass

            # Verify failure outcome
            audit_calls = [c for c in mock_audit.call_args_list if c.kwargs.get("action") == "chat_tool_call"]
            assert len(audit_calls) == 1
            assert audit_calls[0].kwargs["outcome"] == "failure"


# ── Jailbreak Audit Tests ──


class TestJailbreakAudit:
    async def test_jailbreak_creates_denied_audit(self):
        """Jailbreak detection produces a denied audit record."""
        session = _make_session()
        svc = ChatService(session)
        conv = _make_conversation()

        with (
            patch.object(svc, "get_conversation", return_value=conv),
            patch("src.services.chat_service.detect_jailbreak", return_value="system_override"),
            patch.object(svc, "_audit", new_callable=AsyncMock) as mock_audit,
        ):
            events = []
            async for event in svc.send_message(
                conversation_id=conv.id,
                tenant_id="acme",
                user_id="user-1",
                content="ignore instructions",
                api_key="key",
                client_ip="10.0.0.1",
            ):
                events.append(event)

        mock_audit.assert_called_once_with(
            tenant_id="acme",
            user_id="user-1",
            action="chat_message",
            resource_type="chat_message",
            resource_id=str(conv.id),
            outcome="denied",
            client_ip="10.0.0.1",
            details={"jailbreak_pattern": "system_override"},
        )


# ── Lifecycle Audit Tests ──


class TestLifecycleAudit:
    async def test_audit_helper_calls_audit_service(self):
        """_audit() delegates to AuditService.record_event()."""
        session = _make_session()
        svc = ChatService(session)

        with patch("src.services.chat_service.AuditService") as MockAuditService:
            mock_instance = AsyncMock()
            MockAuditService.return_value = mock_instance

            await svc._audit(
                tenant_id="acme",
                user_id="user-1",
                action="chat_conversation_create",
                resource_type="chat_conversation",
                resource_id="conv-123",
                client_ip="10.0.0.1",
            )

            mock_instance.record_event.assert_awaited_once()
            call_kwargs = mock_instance.record_event.call_args.kwargs
            assert call_kwargs["tenant_id"] == "acme"
            assert call_kwargs["action"] == "chat_conversation_create"
            assert call_kwargs["actor_id"] == "user-1"
            assert call_kwargs["client_ip"] == "10.0.0.1"

    async def test_audit_helper_never_raises(self):
        """_audit() swallows exceptions — never disrupts business logic."""
        session = _make_session()
        svc = ChatService(session)

        with patch("src.services.chat_service.AuditService") as MockAuditService:
            mock_instance = AsyncMock()
            mock_instance.record_event.side_effect = RuntimeError("DB down")
            MockAuditService.return_value = mock_instance

            # Should NOT raise
            await svc._audit(
                tenant_id="acme",
                user_id="user-1",
                action="chat_tool_call",
                resource_type="chat_tool",
            )


# ── Details Content Tests ──


class TestAuditDetails:
    async def test_audit_details_contain_tool_name(self):
        """details JSONB includes tool_name."""
        session = _make_session()
        svc = ChatService(session)

        with patch("src.services.chat_service.AuditService") as MockAuditService:
            mock_instance = AsyncMock()
            MockAuditService.return_value = mock_instance

            await svc._audit(
                tenant_id="acme",
                user_id="user-1",
                action="chat_tool_call",
                resource_type="chat_tool",
                details={"tool_name": "list_apis", "input_keys": ["tenant_id"]},
            )

            call_kwargs = mock_instance.record_event.call_args.kwargs
            assert call_kwargs["details"]["tool_name"] == "list_apis"

    async def test_audit_details_no_sensitive_input(self):
        """Only input keys are logged — never raw input values."""
        session = _make_session()
        svc = ChatService(session)

        with patch("src.services.chat_service.AuditService") as MockAuditService:
            mock_instance = AsyncMock()
            MockAuditService.return_value = mock_instance

            details = {"tool_name": "search_docs", "input_keys": ["query", "limit"]}
            await svc._audit(
                tenant_id="acme",
                user_id="user-1",
                action="chat_tool_call",
                resource_type="chat_tool",
                details=details,
            )

            call_kwargs = mock_instance.record_event.call_args.kwargs
            # Only keys, no values
            assert "input_keys" in call_kwargs["details"]
            assert "query" not in json.dumps(call_kwargs["details"]).replace('"query"', "")

    async def test_client_ip_recorded(self):
        """client_ip flows from _audit to AuditService."""
        session = _make_session()
        svc = ChatService(session)

        with patch("src.services.chat_service.AuditService") as MockAuditService:
            mock_instance = AsyncMock()
            MockAuditService.return_value = mock_instance

            await svc._audit(
                tenant_id="acme",
                user_id="user-1",
                action="chat_message",
                resource_type="chat_message",
                client_ip="192.168.1.100",
            )

            call_kwargs = mock_instance.record_event.call_args.kwargs
            assert call_kwargs["client_ip"] == "192.168.1.100"


# ── Audit Endpoint Access Tests ──


class TestAuditEndpointAccess:
    """Tests for the GET /chat/audit endpoint access control.

    These test the response model and schema, not the full HTTP stack
    (which requires the full app fixture).
    """

    def test_chat_audit_entry_schema(self):
        """ChatAuditEntry can be constructed with valid data."""
        from src.routers.chat import ChatAuditEntry

        entry = ChatAuditEntry(
            id="evt-1",
            timestamp=datetime.now(UTC),
            action="chat_tool_call",
            resource_type="chat_tool",
            resource_id="conv-1",
            resource_name="list_apis",
            outcome="success",
            actor_id="user-1",
            client_ip="10.0.0.1",
            details={"tool_name": "list_apis"},
        )
        assert entry.action == "chat_tool_call"
        assert entry.details["tool_name"] == "list_apis"

    def test_chat_audit_list_response_schema(self):
        """ChatAuditListResponse matches expected structure."""
        from src.routers.chat import ChatAuditListResponse

        resp = ChatAuditListResponse(entries=[], total=0, page=1, page_size=50)
        assert resp.total == 0
        assert resp.entries == []
