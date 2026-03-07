"""Tests for chat rate limiter + kill switch (CAB-1655)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Rate limiter unit tests
# ---------------------------------------------------------------------------

SVC_PATH = "src.routers.chat.ChatService"
CONV_URL = "/v1/tenants/acme/chat/conversations"
API_KEY_HEADER = {"X-Provider-Api-Key": "sk-test-rate-limit"}


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset rate limiter state between tests."""
    from src.services.chat_rate_limiter import reset_all

    reset_all()
    yield
    reset_all()


@pytest.fixture(autouse=True)
def reset_sse_event_loop():
    try:
        from sse_starlette.sse import AppStatus

        AppStatus.should_exit_event = asyncio.Event()
    except Exception:
        pass
    yield


def _build_app(current_user, db_session):
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


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
    return session


@pytest.fixture
def user():
    from pydantic import BaseModel

    class _User(BaseModel):
        id: str = "rate-test-user"
        email: str = "user@acme.com"
        username: str = "rateuser"
        roles: list[str] = ["tenant-admin"]
        tenant_id: str | None = "acme"
        sub: str = "rate-test-user"

    return _User()


@pytest.fixture
def client(user, mock_db):
    app = _build_app(user, mock_db)
    with TestClient(app) as c:
        yield c


class TestChatRateLimiterUnit:
    """Unit tests for the rate limiter module."""

    def test_first_request_allowed(self):
        from src.services.chat_rate_limiter import check_rate_limit

        allowed, reason, retry = check_rate_limit("u1", "t1", "message")
        assert allowed is True
        assert reason is None
        assert retry is None

    def test_user_message_limit_enforced(self):
        from src.services.chat_rate_limiter import check_rate_limit, record_event

        with patch("src.services.chat_rate_limiter.settings") as mock_settings:
            mock_settings.CHAT_RATE_LIMIT_USER_MESSAGES = 3
            mock_settings.CHAT_RATE_LIMIT_TENANT_MESSAGES = 100

            for _ in range(3):
                record_event("u1", "t1", "message")

            allowed, reason, retry = check_rate_limit("u1", "t1", "message")
            assert allowed is False
            assert "User rate limit exceeded" in reason
            assert retry == 60

    def test_tenant_message_limit_enforced(self):
        from src.services.chat_rate_limiter import check_rate_limit, record_event

        with patch("src.services.chat_rate_limiter.settings") as mock_settings:
            mock_settings.CHAT_RATE_LIMIT_USER_MESSAGES = 100
            mock_settings.CHAT_RATE_LIMIT_TENANT_MESSAGES = 5

            # 5 different users, same tenant
            for i in range(5):
                record_event(f"user-{i}", "t1", "message")

            allowed, reason, _retry = check_rate_limit("user-new", "t1", "message")
            assert allowed is False
            assert "Tenant rate limit exceeded" in reason

    def test_tool_call_limit_enforced(self):
        from src.services.chat_rate_limiter import check_rate_limit, record_event

        with patch("src.services.chat_rate_limiter.settings") as mock_settings:
            mock_settings.CHAT_RATE_LIMIT_USER_TOOL_CALLS = 2

            record_event("u1", "t1", "tool_call")
            record_event("u1", "t1", "tool_call")

            allowed, reason, _ = check_rate_limit("u1", "t1", "tool_call")
            assert allowed is False
            assert "tool_call" in reason

    def test_different_users_independent(self):
        from src.services.chat_rate_limiter import check_rate_limit, record_event

        with patch("src.services.chat_rate_limiter.settings") as mock_settings:
            mock_settings.CHAT_RATE_LIMIT_USER_MESSAGES = 2
            mock_settings.CHAT_RATE_LIMIT_TENANT_MESSAGES = 100

            record_event("u1", "t1", "message")
            record_event("u1", "t1", "message")

            # u1 is limited
            allowed_u1, _, _ = check_rate_limit("u1", "t1", "message")
            assert allowed_u1 is False

            # u2 is fine
            allowed_u2, _, _ = check_rate_limit("u2", "t1", "message")
            assert allowed_u2 is True

    def test_reset_clears_all(self):
        from src.services.chat_rate_limiter import check_rate_limit, record_event, reset_all

        with patch("src.services.chat_rate_limiter.settings") as mock_settings:
            mock_settings.CHAT_RATE_LIMIT_USER_MESSAGES = 1
            mock_settings.CHAT_RATE_LIMIT_TENANT_MESSAGES = 100

            record_event("u1", "t1", "message")
            allowed, _, _ = check_rate_limit("u1", "t1", "message")
            assert allowed is False

            reset_all()
            allowed, _, _ = check_rate_limit("u1", "t1", "message")
            assert allowed is True


class TestKillSwitch:
    """Kill switch disables all chat endpoints with 503."""

    def test_kill_switch_blocks_create_conversation(self, client):
        with patch("src.routers.chat.settings") as mock_settings:
            mock_settings.CHAT_KILL_SWITCH = True
            resp = client.post(CONV_URL, json={"title": "test"})

        assert resp.status_code == 503
        assert "temporarily disabled" in resp.json()["detail"]

    def test_kill_switch_blocks_send_message(self, client):
        conv_id = uuid4()
        with patch("src.routers.chat.settings") as mock_settings:
            mock_settings.CHAT_KILL_SWITCH = True
            resp = client.post(
                f"{CONV_URL}/{conv_id}/messages",
                json={"content": "Hello"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 503

    def test_kill_switch_off_allows_requests(self, client):
        conv = MagicMock()
        conv.id = uuid4()
        conv.tenant_id = "acme"
        conv.user_id = "rate-test-user"
        conv.title = "Test"
        conv.provider = "anthropic"
        conv.model = "claude-sonnet-4-20250514"
        conv.system_prompt = None
        conv.status = "active"
        conv.messages = []
        from datetime import UTC, datetime

        conv.created_at = datetime.now(UTC)
        conv.updated_at = datetime.now(UTC)

        with patch("src.routers.chat.settings") as mock_settings:
            mock_settings.CHAT_KILL_SWITCH = False
            with patch(SVC_PATH) as MockSvc:
                MockSvc.return_value.create_conversation = AsyncMock(return_value=conv)
                resp = client.post(CONV_URL, json={"title": "test"})

        assert resp.status_code == 201


class TestRateLimitEndpoint:
    """Rate limiting on the send_message endpoint."""

    def test_rate_limit_returns_429_with_retry_after(self, client):
        conv_id = uuid4()
        with patch("src.routers.chat.check_rate_limit") as mock_check:
            mock_check.return_value = (False, "User rate limit exceeded: 20/20 messages per minute", 60)
            resp = client.post(
                f"{CONV_URL}/{conv_id}/messages",
                json={"content": "Hello"},
                headers=API_KEY_HEADER,
            )

        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert resp.headers["Retry-After"] == "60"
        assert "rate limit" in resp.json()["detail"].lower()

    def test_allowed_request_proceeds_to_stream(self, client):
        conv_id = uuid4()

        async def mock_stream(**kwargs):
            yield {"event": "message_end", "data": {"input_tokens": 1, "output_tokens": 1, "stop_reason": "end_turn"}}

        with patch("src.routers.chat.check_rate_limit") as mock_check:
            mock_check.return_value = (True, None, None)
            with patch("src.routers.chat.record_event"), patch(SVC_PATH) as MockSvc:
                MockSvc.return_value.send_message = mock_stream
                resp = client.post(
                    f"{CONV_URL}/{conv_id}/messages",
                    json={"content": "Hello"},
                    headers=API_KEY_HEADER,
                )

        assert resp.status_code == 200
        assert "message_end" in resp.text
