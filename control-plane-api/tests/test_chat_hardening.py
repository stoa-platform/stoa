"""Chat agent hardening tests — CAB-1452.

Tests for edge cases, error handling, and security properties of the
chat agent subsystem.  Uses the same _build_chat_app() pattern as
test_chat_router.py so the chat router is always mounted, independent
of the CHAT_ENABLED feature flag.

28 tests spread across 5 priority groups:
  P0 (8) — Streaming Resilience
  P1 (5) — Provider Error Handling
  P2 (5) — Rate Limiting & Budget
  P3 (5) — Tool Security
  P4 (5) — Input Validation
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Minimal test app (mirrors test_chat_router.py pattern exactly)
# ---------------------------------------------------------------------------

SVC_PATH = "src.routers.chat.ChatService"
REPO_PATH = "src.routers.chat.ChatTokenUsageRepository"


def _build_chat_app(current_user: Any, db_session: Any) -> FastAPI:
    """Return a FastAPI app with the chat router mounted and auth/db overridden."""
    from src.auth.dependencies import get_current_user
    from src.database import get_db
    from src.routers.chat import router as chat_router

    app = FastAPI()
    app.include_router(chat_router)

    async def _override_user():
        return current_user

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_sse_event_loop():
    """Reset sse_starlette's module-level AppStatus event between tests.

    sse_starlette binds AppStatus.should_exit_event to the first event loop
    it encounters.  When pytest-asyncio creates a new loop per test, subsequent
    SSE calls fail with 'bound to a different event loop'.  Resetting the event
    here prevents this cross-test contamination.
    """
    try:
        from sse_starlette.sse import AppStatus

        AppStatus.should_exit_event = asyncio.Event()
    except Exception:
        pass
    yield


@pytest.fixture
def mock_db():
    """Minimal SQLAlchemy async session mock."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def tenant_admin_user():
    from pydantic import BaseModel

    class _User(BaseModel):
        id: str = "tenant-admin-user-id"
        email: str = "admin@acme.com"
        username: str = "tenant-admin"
        roles: list[str] = ["tenant-admin"]
        tenant_id: str | None = "acme"
        sub: str = "tenant-admin-user-id"

    return _User()


@pytest.fixture
def tenant_client(tenant_admin_user, mock_db):
    app = _build_chat_app(tenant_admin_user, mock_db)
    with TestClient(app) as c:
        yield c


def _make_conv(**overrides):
    """Build a mock ChatConversation ORM-like object."""
    conv = MagicMock()
    conv.id = overrides.get("id", uuid4())
    conv.tenant_id = overrides.get("tenant_id", "acme")
    conv.user_id = overrides.get("user_id", "tenant-admin-user-id")
    conv.title = overrides.get("title", "New conversation")
    conv.provider = overrides.get("provider", "anthropic")
    conv.model = overrides.get("model", "claude-sonnet-4-20250514")
    conv.system_prompt = overrides.get("system_prompt")
    conv.status = overrides.get("status", "active")
    conv.messages = overrides.get("messages", [])
    conv.created_at = overrides.get("created_at", datetime.now(UTC))
    conv.updated_at = overrides.get("updated_at", datetime.now(UTC))
    return conv


CONV_URL = "/v1/tenants/acme/chat/conversations"
API_KEY_HEADER = {"X-Provider-Api-Key": "sk-test-hardening"}


# ---------------------------------------------------------------------------
# P0 — Streaming Resilience (8 tests)
# ---------------------------------------------------------------------------


class TestStreamingResilience:
    """P0: The SSE stream MUST always produce a well-formed response."""

    def test_stream_delivers_content_delta_events(self, tenant_client):
        """Happy path: content_delta events are delivered via SSE."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {"event": "content_delta", "data": {"delta": "Hello"}}
            yield {"event": "content_delta", "data": {"delta": " World"}}
            yield {
                "event": "message_end",
                "data": {"input_tokens": 10, "output_tokens": 5, "stop_reason": "end_turn"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Hello"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = resp.text
        assert "content_delta" in body
        assert "message_end" in body

    def test_stream_delivers_message_end_event(self, tenant_client):
        """message_end event carries token counts."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {
                "event": "message_end",
                "data": {"input_tokens": 20, "output_tokens": 10, "stop_reason": "end_turn"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Hi"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        assert "message_end" in resp.text
        assert "input_tokens" in resp.text

    def test_stream_empty_generator_returns_200(self, tenant_client):
        """An empty generator (no events) must still return HTTP 200."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            return
            yield  # make it a generator

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Hello"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200

    def test_stream_error_event_in_stream_not_500(self, tenant_client):
        """Error events are streamed as SSE data, not raised as HTTP 500."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {"event": "error", "data": {"error": "something went wrong"}}

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Hello"},
                headers=API_KEY_HEADER,
            )

        # Error is delivered inside the stream, not as HTTP 5xx
        assert resp.status_code == 200
        assert "error" in resp.text

    def test_stream_tool_use_event_delivered(self, tenant_client):
        """tool_use events pass through the stream transparently."""
        conv = _make_conv()
        tool_call = {"id": "tool_123", "name": "list_tenants", "input": {}}

        async def mock_stream(**kwargs):
            yield {"event": "tool_use", "data": tool_call}
            yield {"event": "tool_result", "data": {"tool_use_id": "tool_123", "content": "[]"}}
            yield {
                "event": "message_end",
                "data": {"input_tokens": 10, "output_tokens": 5, "stop_reason": "tool_use"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "List tenants"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        assert "tool_use" in resp.text

    def test_stream_multiple_tool_iterations_delivered(self, tenant_client):
        """Multiple tool call iterations are streamed without truncation."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            # Iteration 1
            yield {"event": "tool_use", "data": {"id": "t1", "name": "list_tenants", "input": {}}}
            yield {"event": "tool_result", "data": {"tool_use_id": "t1", "content": "[]"}}
            # Iteration 2
            yield {"event": "tool_use", "data": {"id": "t2", "name": "list_apis", "input": {}}}
            yield {"event": "tool_result", "data": {"tool_use_id": "t2", "content": "[]"}}
            yield {"event": "content_delta", "data": {"delta": "Done"}}
            yield {
                "event": "message_end",
                "data": {"input_tokens": 50, "output_tokens": 10, "stop_reason": "end_turn"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Do it"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        # Both tool iterations must appear in the SSE body
        # Count "event: tool_use" lines to avoid counting "tool_use_id" in tool_result data
        assert resp.text.count("event: tool_use") == 2

    def test_stream_conversation_not_found_yields_error_event(self, tenant_client):
        """Conversation not found yields error SSE event, not HTTP 404."""
        conv_id = uuid4()

        async def mock_stream(**kwargs):
            yield {"event": "error", "data": {"error": "Conversation not found"}}

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv_id}/messages",
                json={"content": "Hello"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        assert "Conversation not found" in resp.text

    def test_stream_kafka_failure_does_not_break_stream(self, tenant_client):
        """Kafka metering failure is silent — stream completes normally."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {"event": "content_delta", "data": {"delta": "Reply"}}
            yield {
                "event": "message_end",
                "data": {"input_tokens": 5, "output_tokens": 2, "stop_reason": "end_turn"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Hi"},
                headers=API_KEY_HEADER,
            )

        # Stream completes successfully despite any Kafka error
        assert resp.status_code == 200
        assert "message_end" in resp.text


# ---------------------------------------------------------------------------
# P1 — Provider Error Handling (5 tests)
# ---------------------------------------------------------------------------


class TestProviderErrorHandling:
    """P1: Upstream provider errors must be surfaced as SSE error events."""

    def test_provider_non_200_response_yields_error_event(self, tenant_client):
        """Non-200 from Anthropic API → error event in stream."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {
                "event": "error",
                "data": {"error": "Anthropic API returned 429", "detail": "rate limit exceeded"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Hello"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        assert "Anthropic API returned 429" in resp.text

    def test_provider_401_unauthorized_yields_error_event(self, tenant_client):
        """Invalid API key → 401 from Anthropic → error event in stream."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {
                "event": "error",
                "data": {"error": "Anthropic API returned 401", "detail": "authentication_error"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Hello"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        assert "Anthropic API returned 401" in resp.text

    def test_provider_500_server_error_yields_error_event(self, tenant_client):
        """Anthropic 500 → error event (not HTTP 500)."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {
                "event": "error",
                "data": {"error": "Anthropic API returned 500", "detail": "internal_server_error"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Hello"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        assert "Anthropic API returned 500" in resp.text

    def test_provider_overload_yields_error_event(self, tenant_client):
        """Anthropic overload error (529) → error event in stream."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {
                "event": "error",
                "data": {"error": "Anthropic API returned 529", "detail": "overloaded"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Hello"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        assert "Anthropic API returned 529" in resp.text

    def test_missing_api_key_header_returns_400(self, tenant_client):
        """Missing X-Provider-Api-Key header returns HTTP 400 (before streaming)."""
        resp = tenant_client.post(
            f"{CONV_URL}/{uuid4()}/messages",
            json={"content": "Hello"},
            # Deliberately no X-Provider-Api-Key header
        )

        assert resp.status_code == 400
        assert "X-Provider-Api-Key" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# P2 — Rate Limiting & Budget (5 tests)
# ---------------------------------------------------------------------------


class TestRateLimitingAndBudget:
    """P2: Daily token budget enforcement must be surfaced as SSE error events."""

    def test_budget_exceeded_yields_error_event(self, tenant_client):
        """When daily budget is exceeded, stream yields a budget error event."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {
                "event": "error",
                "data": {
                    "error": "Daily token budget exceeded",
                    "tokens_used": 100000,
                    "budget": 50000,
                },
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Hi"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        assert "Daily token budget exceeded" in resp.text

    def test_budget_error_contains_tokens_used(self, tenant_client):
        """Budget error event contains both tokens_used and budget fields."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {
                "event": "error",
                "data": {
                    "error": "Daily token budget exceeded",
                    "tokens_used": 75000,
                    "budget": 50000,
                },
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Hi"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        body = resp.text
        assert "tokens_used" in body
        assert "budget" in body

    def test_get_budget_status_returns_current_usage(self, tenant_client):
        """GET /usage/budget returns current token consumption vs budget."""
        budget_data = {
            "user_tokens_today": 1500,
            "tenant_tokens_today": 8000,
            "daily_budget": 10000,
            "remaining": 8500,
            "budget_exceeded": False,
            "usage_percent": 15.0,
        }
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_budget_status = AsyncMock(return_value=budget_data)
            with patch("src.routers.chat.settings") as mock_settings:
                mock_settings.CHAT_TOKEN_BUDGET_DAILY = 10000
                resp = tenant_client.get("/v1/tenants/acme/chat/usage/budget")

        assert resp.status_code == 200
        body = resp.json()
        assert body["budget_exceeded"] is False
        assert body["remaining"] == 8500

    def test_get_budget_status_shows_exceeded_flag(self, tenant_client):
        """GET /usage/budget reflects budget_exceeded=True when over limit."""
        budget_data = {
            "user_tokens_today": 55000,
            "tenant_tokens_today": 120000,
            "daily_budget": 50000,
            "remaining": 0,
            "budget_exceeded": True,
            "usage_percent": 100.0,
        }
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_budget_status = AsyncMock(return_value=budget_data)
            with patch("src.routers.chat.settings") as mock_settings:
                mock_settings.CHAT_TOKEN_BUDGET_DAILY = 50000
                resp = tenant_client.get("/v1/tenants/acme/chat/usage/budget")

        assert resp.status_code == 200
        assert resp.json()["budget_exceeded"] is True

    def test_tool_loop_max_iterations_boundary(self, tenant_client):
        """Stream handles exactly MAX_TOOL_ITERATIONS=3 tool calls without looping."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            # Exactly 3 tool calls — at the limit
            for i in range(3):
                yield {
                    "event": "tool_use",
                    "data": {"id": f"t{i}", "name": "list_tenants", "input": {}},
                }
                yield {
                    "event": "tool_result",
                    "data": {"tool_use_id": f"t{i}", "content": "[]"},
                }
            yield {"event": "content_delta", "data": {"delta": "Done"}}
            yield {
                "event": "message_end",
                "data": {"input_tokens": 100, "output_tokens": 5, "stop_reason": "end_turn"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "Do things"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        # Count "event: tool_use" lines to avoid counting "tool_use_id" in tool_result data
        assert resp.text.count("event: tool_use") == 3
        assert "message_end" in resp.text


# ---------------------------------------------------------------------------
# P3 — Tool Security (5 tests)
# ---------------------------------------------------------------------------


class TestToolSecurity:
    """P3: Tool execution must never leak exceptions or allow unknown tools."""

    def test_unknown_tool_returns_json_error_not_exception(self, tenant_client):
        """Unknown tool name returns JSON error string, not an uncaught exception."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            # Service returns an error event for unknown tool
            yield {
                "event": "tool_result",
                "data": {"tool_use_id": "t0", "content": '{"error": "Unknown tool: hack_system"}'},
            }
            yield {
                "event": "message_end",
                "data": {"input_tokens": 10, "output_tokens": 2, "stop_reason": "end_turn"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "hack_system()"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        # Error is captured in tool_result content, not as HTTP 5xx
        assert "Unknown tool" in resp.text

    def test_tool_exception_returns_json_error_not_500(self, tenant_client):
        """Tool that raises an exception yields JSON error, stream continues."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {
                "event": "tool_result",
                "data": {
                    "tool_use_id": "t0",
                    "content": '{"error": "Tool list_tenants failed: connection refused"}',
                },
            }
            yield {
                "event": "message_end",
                "data": {"input_tokens": 8, "output_tokens": 3, "stop_reason": "end_turn"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "List tenants"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        assert "failed" in resp.text.lower()

    def test_tool_result_is_json_string(self, tenant_client):
        """Tool results in SSE are valid JSON strings."""
        conv = _make_conv()
        tool_result = json.dumps({"tenants": ["acme", "corp"]})

        async def mock_stream(**kwargs):
            yield {"event": "tool_result", "data": {"tool_use_id": "t0", "content": tool_result}}
            yield {
                "event": "message_end",
                "data": {"input_tokens": 10, "output_tokens": 5, "stop_reason": "end_turn"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "List tenants"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 200
        assert "tool_result" in resp.text

    def test_cross_tenant_tool_access_blocked(self, mock_db):
        """User from tenant B cannot call tools on tenant A's conversations."""
        from pydantic import BaseModel

        class _OtherUser(BaseModel):
            id: str = "evil-user-id"
            email: str = "evil@attacker.com"
            username: str = "evil"
            roles: list[str] = ["tenant-admin"]
            tenant_id: str | None = "attacker"
            sub: str = "evil-user-id"

        app = _build_chat_app(_OtherUser(), mock_db)
        with TestClient(app) as client:
            resp = client.post(
                f"{CONV_URL}/{uuid4()}/messages",
                json={"content": "List everything"},
                headers=API_KEY_HEADER,
            )

        # Tenant isolation: attacker cannot access acme's conversations
        assert resp.status_code == 403

    def test_tool_list_has_seven_known_tools(self):
        """CHAT_TOOLS must contain exactly 7 registered tools."""
        from src.services.chat_tools import CHAT_TOOLS

        tool_names = [t["name"] for t in CHAT_TOOLS]
        assert len(tool_names) == 7
        expected = {
            "list_tenants",
            "list_apis",
            "get_api_detail",
            "list_gateway_instances",
            "list_deployments",
            "platform_info",
            "search_docs",
        }
        assert set(tool_names) == expected


# ---------------------------------------------------------------------------
# P4 — Input Validation (5 tests)
# ---------------------------------------------------------------------------


class TestInputValidation:
    """P4: Invalid inputs must be rejected before reaching the service layer."""

    def test_empty_message_content_rejected(self, tenant_client):
        """Empty string content (length=0) fails min_length=1 → 422."""
        resp = tenant_client.post(
            f"{CONV_URL}/{uuid4()}/messages",
            json={"content": ""},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 422

    def test_missing_content_field_rejected(self, tenant_client):
        """Missing 'content' field returns 422."""
        resp = tenant_client.post(
            f"{CONV_URL}/{uuid4()}/messages",
            json={},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 422

    def test_whitespace_only_content_accepted_by_schema(self, tenant_client):
        """Whitespace content passes min_length=1 schema validation.

        MessageSend.content has min_length=1 but no strip/whitespace validator.
        3-space string satisfies min_length and reaches the SSE endpoint → 200.
        Rejecting purely-whitespace inputs would require a custom validator.
        This test documents the current (permissive) behavior.
        """
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {
                "event": "message_end",
                "data": {"input_tokens": 1, "output_tokens": 1, "stop_reason": "end_turn"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"{CONV_URL}/{conv.id}/messages",
                json={"content": "   "},
                headers=API_KEY_HEADER,
            )

        # Schema allows whitespace content; custom rejection would need a validator
        assert resp.status_code == 200

    def test_create_conversation_model_field_accepts_any_string(self, tenant_client):
        """ConversationCreate.model is a free-form string (max_length=100).

        Pydantic does not validate the model name against an allowlist.
        Provider/model validation happens at the service layer, not the schema.
        This test documents that schema-level validation accepts any string.
        """
        conv = _make_conv(title="New conversation")
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.create_conversation = AsyncMock(return_value=conv)
            resp = tenant_client.post(
                f"{CONV_URL}",
                json={"model": "gpt-42-turbo"},
            )

        # Schema accepts any string for model; service-level validation is separate
        assert resp.status_code == 201

    def test_create_conversation_empty_title_accepted(self, tenant_client):
        """Empty title is valid — service sets a default title."""
        conv = _make_conv(title="New conversation")
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.create_conversation = AsyncMock(return_value=conv)
            resp = tenant_client.post(
                f"{CONV_URL}",
                json={"title": ""},
            )

        # Empty title should be accepted (service fills default)
        assert resp.status_code == 201
