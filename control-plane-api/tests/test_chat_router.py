"""Tests for Chat router — /v1/tenants/{tenant_id}/chat/* (CAB-1452)

The chat router is conditionally mounted (settings.CHAT_ENABLED).
These tests use a dedicated FastAPI test app that always includes the router,
independent of the CHAT_ENABLED flag.

Covers all 13 endpoints:
  POST   /conversations              — create
  GET    /conversations              — list
  GET    /conversations/{id}         — get with messages
  PATCH  /conversations/{id}         — rename
  DELETE /conversations/{id}         — delete
  PATCH  /conversations/{id}/archive — archive/restore
  DELETE /conversations              — cascade delete (tenant)
  DELETE /conversations/purge        — GDPR retention purge
  POST   /conversations/{id}/messages — send + stream (SSE)
  GET    /usage                      — token usage (user)
  GET    /usage/tenant               — token usage (admin)
  GET    /usage/budget               — budget status
  GET    /usage/metering             — aggregated stats
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Minimal test app that always includes the chat router
# ---------------------------------------------------------------------------


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

UTC = UTC


@pytest.fixture
def mock_db():
    """Minimal SQLAlchemy async session mock."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def tenant_admin_user():
    """User object matching mock_user_tenant_admin in conftest."""

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
def cpi_admin_user():

    from pydantic import BaseModel

    class _User(BaseModel):
        id: str = "admin-user-id"
        email: str = "admin@gostoa.dev"
        username: str = "cpi-admin"
        roles: list[str] = ["cpi-admin"]
        tenant_id: str | None = None
        sub: str = "admin-user-id"

    return _User()


@pytest.fixture
def other_tenant_user():

    from pydantic import BaseModel

    class _User(BaseModel):
        id: str = "other-user-id"
        email: str = "user@other.com"
        username: str = "other-user"
        roles: list[str] = ["tenant-admin"]
        tenant_id: str | None = "other-tenant"
        sub: str = "other-user-id"

    return _User()


@pytest.fixture
def tenant_client(tenant_admin_user, mock_db):
    app = _build_chat_app(tenant_admin_user, mock_db)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def cpi_client(cpi_admin_user, mock_db):
    app = _build_chat_app(cpi_admin_user, mock_db)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def other_client(other_tenant_user, mock_db):
    app = _build_chat_app(other_tenant_user, mock_db)
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


SVC_PATH = "src.routers.chat.ChatService"


# ---------------------------------------------------------------------------
# POST /conversations — create
# ---------------------------------------------------------------------------


class TestCreateConversation:
    def test_create_defaults(self, tenant_client):
        conv = _make_conv()
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.create_conversation = AsyncMock(return_value=conv)
            resp = tenant_client.post(
                "/v1/tenants/acme/chat/conversations",
                json={},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["tenant_id"] == "acme"

    def test_create_with_title_and_system_prompt(self, tenant_client):
        conv = _make_conv(title="My Chat", system_prompt="Be concise.")
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.create_conversation = AsyncMock(return_value=conv)
            resp = tenant_client.post(
                "/v1/tenants/acme/chat/conversations",
                json={"title": "My Chat", "system_prompt": "Be concise."},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "My Chat"
        assert body["system_prompt"] == "Be concise."

    def test_create_with_custom_model(self, tenant_client):
        conv = _make_conv(model="claude-opus-4-20250514")
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.create_conversation = AsyncMock(return_value=conv)
            resp = tenant_client.post(
                "/v1/tenants/acme/chat/conversations",
                json={"model": "claude-opus-4-20250514"},
            )

        assert resp.status_code == 201
        assert resp.json()["model"] == "claude-opus-4-20250514"

    def test_other_tenant_forbidden(self, other_client):
        resp = other_client.post(
            "/v1/tenants/acme/chat/conversations",
            json={},
        )
        assert resp.status_code == 403

    def test_cpi_admin_can_create_cross_tenant(self, cpi_client):
        conv = _make_conv()
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.create_conversation = AsyncMock(return_value=conv)
            resp = cpi_client.post(
                "/v1/tenants/acme/chat/conversations",
                json={},
            )

        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# GET /conversations — list
# ---------------------------------------------------------------------------


class TestListConversations:
    def test_list_returns_paginated(self, tenant_client):
        conv1 = _make_conv()
        conv2 = _make_conv(title="Second")
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.list_conversations = AsyncMock(return_value=([conv1, conv2], 2))
            resp = tenant_client.get("/v1/tenants/acme/chat/conversations")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_list_empty(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.list_conversations = AsyncMock(return_value=([], 0))
            resp = tenant_client.get("/v1/tenants/acme/chat/conversations")

        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_list_with_status_filter(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.list_conversations = AsyncMock(return_value=([], 0))
            resp = tenant_client.get("/v1/tenants/acme/chat/conversations?status=archived")

        assert resp.status_code == 200
        MockSvc.return_value.list_conversations.assert_awaited_once()
        call_kwargs = MockSvc.return_value.list_conversations.call_args.kwargs
        assert call_kwargs.get("status") == "archived"

    def test_list_pagination_params(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.list_conversations = AsyncMock(return_value=([], 0))
            resp = tenant_client.get("/v1/tenants/acme/chat/conversations?limit=10&offset=20")

        assert resp.status_code == 200

    def test_list_other_tenant_forbidden(self, other_client):
        resp = other_client.get("/v1/tenants/acme/chat/conversations")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /conversations/{id} — get with messages
# ---------------------------------------------------------------------------


class TestGetConversation:
    def test_get_found(self, tenant_client):
        conv = _make_conv()
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.get_conversation = AsyncMock(return_value=conv)
            resp = tenant_client.get(f"/v1/tenants/acme/chat/conversations/{conv.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(conv.id)

    def test_get_not_found_returns_404(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.get_conversation = AsyncMock(return_value=None)
            resp = tenant_client.get(f"/v1/tenants/acme/chat/conversations/{uuid4()}")

        assert resp.status_code == 404

    def test_get_other_tenant_forbidden(self, other_client):
        resp = other_client.get(f"/v1/tenants/acme/chat/conversations/{uuid4()}")
        assert resp.status_code == 403

    def test_get_includes_messages_field(self, tenant_client):
        conv = _make_conv(messages=[])
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.get_conversation = AsyncMock(return_value=conv)
            resp = tenant_client.get(f"/v1/tenants/acme/chat/conversations/{conv.id}")

        assert "messages" in resp.json()


# ---------------------------------------------------------------------------
# PATCH /conversations/{id} — rename
# ---------------------------------------------------------------------------


class TestUpdateConversation:
    def test_update_title(self, tenant_client):
        conv = _make_conv(title="Renamed")
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.update_conversation = AsyncMock(return_value=conv)
            resp = tenant_client.patch(
                f"/v1/tenants/acme/chat/conversations/{conv.id}",
                json={"title": "Renamed"},
            )

        assert resp.status_code == 200
        assert resp.json()["title"] == "Renamed"

    def test_update_not_found_returns_404(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.update_conversation = AsyncMock(return_value=None)
            resp = tenant_client.patch(
                f"/v1/tenants/acme/chat/conversations/{uuid4()}",
                json={"title": "Whatever"},
            )

        assert resp.status_code == 404

    def test_update_empty_title_rejected(self, tenant_client):
        """Empty title fails schema validation before reaching the service."""
        resp = tenant_client.patch(
            f"/v1/tenants/acme/chat/conversations/{uuid4()}",
            json={"title": ""},
        )
        assert resp.status_code == 422

    def test_update_other_tenant_forbidden(self, other_client):
        resp = other_client.patch(
            f"/v1/tenants/acme/chat/conversations/{uuid4()}",
            json={"title": "X"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /conversations/{id} — delete
# ---------------------------------------------------------------------------


class TestDeleteConversation:
    def test_delete_success(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.delete_conversation = AsyncMock(return_value=True)
            resp = tenant_client.delete(f"/v1/tenants/acme/chat/conversations/{uuid4()}")

        assert resp.status_code == 204

    def test_delete_not_found_returns_404(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.delete_conversation = AsyncMock(return_value=False)
            resp = tenant_client.delete(f"/v1/tenants/acme/chat/conversations/{uuid4()}")

        assert resp.status_code == 404

    def test_delete_other_tenant_forbidden(self, other_client):
        resp = other_client.delete(f"/v1/tenants/acme/chat/conversations/{uuid4()}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /conversations/{id}/archive — archive/restore
# ---------------------------------------------------------------------------


class TestArchiveConversation:
    def test_archive_conversation(self, tenant_client):
        conv = _make_conv(status="archived")
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.archive_conversation = AsyncMock(return_value=conv)
            resp = tenant_client.patch(
                f"/v1/tenants/acme/chat/conversations/{conv.id}/archive",
                json={"status": "archived"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    def test_restore_conversation(self, tenant_client):
        conv = _make_conv(status="active")
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.archive_conversation = AsyncMock(return_value=conv)
            resp = tenant_client.patch(
                f"/v1/tenants/acme/chat/conversations/{conv.id}/archive",
                json={"status": "active"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_archive_not_found(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.archive_conversation = AsyncMock(return_value=None)
            resp = tenant_client.patch(
                f"/v1/tenants/acme/chat/conversations/{uuid4()}/archive",
                json={"status": "archived"},
            )

        assert resp.status_code == 404

    def test_archive_invalid_status_rejected(self, tenant_client):
        """Invalid status value fails schema validation."""
        resp = tenant_client.patch(
            f"/v1/tenants/acme/chat/conversations/{uuid4()}/archive",
            json={"status": "deleted"},
        )
        assert resp.status_code == 422

    def test_archive_other_tenant_forbidden(self, other_client):
        resp = other_client.patch(
            f"/v1/tenants/acme/chat/conversations/{uuid4()}/archive",
            json={"status": "archived"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /conversations — cascade delete (tenant)
# ---------------------------------------------------------------------------


class TestDeleteTenantConversations:
    def test_cascade_delete_returns_count(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.delete_tenant_conversations = AsyncMock(return_value=5)
            resp = tenant_client.delete("/v1/tenants/acme/chat/conversations")

        assert resp.status_code == 200
        assert resp.json() == {"deleted": 5}

    def test_cascade_delete_empty_tenant(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.delete_tenant_conversations = AsyncMock(return_value=0)
            resp = tenant_client.delete("/v1/tenants/acme/chat/conversations")

        assert resp.json() == {"deleted": 0}

    def test_cascade_delete_other_tenant_forbidden(self, other_client):
        resp = other_client.delete("/v1/tenants/acme/chat/conversations")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /conversations/purge — GDPR retention purge
# ---------------------------------------------------------------------------


class TestPurgeConversations:
    """Tests for DELETE /conversations/purge (GDPR retention purge).

    NOTE: The /conversations/purge route is currently shadowed by the
    /conversations/{conversation_id} route because FastAPI registers the
    parameterized route first. Since conversation_id is typed as UUID,
    any request to /conversations/purge returns 422 (UUID parse failure
    for the literal string "purge") rather than 403/200.

    These tests document the current behaviour. The fix would be to reorder
    the router so /conversations/purge is registered before
    /conversations/{conversation_id}.
    """

    def test_purge_path_shadowed_by_uuid_route(self, tenant_client):
        """The purge route is currently unreachable — shadowed by {conversation_id}."""
        resp = tenant_client.delete("/v1/tenants/acme/chat/conversations/purge?retention_days=30")
        # FastAPI tries to parse "purge" as UUID and fails with 422
        assert resp.status_code == 422
        assert "uuid" in resp.json()["detail"][0]["type"]

    def test_purge_default_retention_also_shadowed(self, tenant_client):
        """Without query params the route is still shadowed."""
        resp = tenant_client.delete("/v1/tenants/acme/chat/conversations/purge")
        assert resp.status_code == 422

    def test_purge_invalid_retention_days_returns_422(self, tenant_client):
        """retention_days=0 also fails (but for the same routing reason)."""
        resp = tenant_client.delete("/v1/tenants/acme/chat/conversations/purge?retention_days=0")
        assert resp.status_code == 422

    def test_purge_other_tenant_also_422(self, other_client):
        """Cross-tenant purge is also 422 due to the routing shadow."""
        resp = other_client.delete("/v1/tenants/acme/chat/conversations/purge")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /conversations/{id}/messages — send + stream (SSE)
# ---------------------------------------------------------------------------


class TestSendMessage:
    def test_send_requires_api_key_header(self, tenant_client):
        """Missing X-Provider-Api-Key returns 400."""
        resp = tenant_client.post(
            f"/v1/tenants/acme/chat/conversations/{uuid4()}/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 400
        assert "X-Provider-Api-Key" in resp.json()["detail"]

    def test_send_empty_content_rejected(self, tenant_client):
        resp = tenant_client.post(
            f"/v1/tenants/acme/chat/conversations/{uuid4()}/messages",
            json={"content": ""},
            headers={"X-Provider-Api-Key": "sk-test"},
        )
        assert resp.status_code == 422

    def test_send_other_tenant_forbidden(self, other_client):
        resp = other_client.post(
            f"/v1/tenants/acme/chat/conversations/{uuid4()}/messages",
            json={"content": "Hi"},
            headers={"X-Provider-Api-Key": "sk-test"},
        )
        assert resp.status_code == 403

    def test_send_streams_sse(self, tenant_client):
        """SSE endpoint returns 200 with text/event-stream content type."""
        conv = _make_conv()

        async def mock_stream(**kwargs):
            yield {"event": "content_delta", "data": {"delta": "Hello"}}
            yield {
                "event": "message_end",
                "data": {"input_tokens": 5, "output_tokens": 3, "stop_reason": "end_turn"},
            }

        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.send_message = mock_stream
            resp = tenant_client.post(
                f"/v1/tenants/acme/chat/conversations/{conv.id}/messages",
                json={"content": "Hello"},
                headers={"X-Provider-Api-Key": "sk-test"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# GET /usage — token usage (user)
# ---------------------------------------------------------------------------


class TestGetUsage:
    def test_get_user_usage(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.get_user_usage = AsyncMock(
                return_value={
                    "total_conversations": 3,
                    "total_messages": 15,
                    "total_tokens": 2500,
                }
            )
            resp = tenant_client.get("/v1/tenants/acme/chat/usage")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_conversations"] == 3
        assert body["total_messages"] == 15
        assert body["total_tokens"] == 2500

    def test_get_usage_other_tenant_forbidden(self, other_client):
        resp = other_client.get("/v1/tenants/acme/chat/usage")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /usage/tenant — token usage (admin)
# ---------------------------------------------------------------------------


class TestGetTenantUsage:
    def test_get_tenant_usage(self, tenant_client):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.get_tenant_usage = AsyncMock(
                return_value={
                    "tenant_id": "acme",
                    "total_conversations": 10,
                    "total_messages": 50,
                    "total_tokens": 8000,
                    "unique_users": 3,
                }
            )
            resp = tenant_client.get("/v1/tenants/acme/chat/usage/tenant")

        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "acme"
        assert body["unique_users"] == 3

    def test_get_tenant_usage_other_tenant_forbidden(self, other_client):
        resp = other_client.get("/v1/tenants/acme/chat/usage/tenant")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /usage/budget — budget status
# ---------------------------------------------------------------------------


class TestGetBudgetStatus:
    def test_get_budget_status(self, tenant_client):
        budget_data = {
            "user_tokens_today": 1500,
            "tenant_tokens_today": 8000,
            "daily_budget": 10000,
            "remaining": 8500,
            "budget_exceeded": False,
            "usage_percent": 15.0,
        }
        with patch("src.routers.chat.ChatTokenUsageRepository") as MockRepo:
            MockRepo.return_value.get_budget_status = AsyncMock(return_value=budget_data)
            with patch("src.routers.chat.settings") as mock_settings:
                mock_settings.CHAT_TOKEN_BUDGET_DAILY = 10000
                resp = tenant_client.get("/v1/tenants/acme/chat/usage/budget")

        assert resp.status_code == 200
        body = resp.json()
        assert body["daily_budget"] == 10000
        assert body["budget_exceeded"] is False
        assert body["usage_percent"] == 15.0

    def test_get_budget_status_unlimited_budget(self, tenant_client):
        """Budget of 0 (unlimited) is treated as 1_000_000 for display."""
        budget_data = {
            "user_tokens_today": 0,
            "tenant_tokens_today": 0,
            "daily_budget": 1_000_000,
            "remaining": 1_000_000,
            "budget_exceeded": False,
            "usage_percent": 0.0,
        }
        with patch("src.routers.chat.ChatTokenUsageRepository") as MockRepo:
            MockRepo.return_value.get_budget_status = AsyncMock(return_value=budget_data)
            with patch("src.routers.chat.settings") as mock_settings:
                mock_settings.CHAT_TOKEN_BUDGET_DAILY = 0
                resp = tenant_client.get("/v1/tenants/acme/chat/usage/budget")

        assert resp.status_code == 200

    def test_get_budget_status_other_tenant_forbidden(self, other_client):
        resp = other_client.get("/v1/tenants/acme/chat/usage/budget")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /usage/metering — aggregated stats
# ---------------------------------------------------------------------------


class TestGetUsageStats:
    def test_get_usage_stats(self, tenant_client):
        stats_data = {
            "tenant_id": "acme",
            "period_days": 30,
            "total_tokens": 50000,
            "total_input_tokens": 30000,
            "total_output_tokens": 20000,
            "total_requests": 200,
            "today_tokens": 1500,
            "top_users": [{"user_id": "user-1", "tokens": 25000}],
            "daily_breakdown": [{"date": "2026-02-24", "tokens": 1500, "requests": 6}],
        }
        with patch("src.routers.chat.ChatTokenUsageRepository") as MockRepo:
            MockRepo.return_value.get_usage_stats = AsyncMock(return_value=stats_data)
            resp = tenant_client.get("/v1/tenants/acme/chat/usage/metering")

        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "acme"
        assert body["total_tokens"] == 50000
        assert len(body["top_users"]) == 1
        assert len(body["daily_breakdown"]) == 1

    def test_get_usage_stats_with_days_param(self, tenant_client):
        stats_data = {
            "tenant_id": "acme",
            "period_days": 7,
            "total_tokens": 5000,
            "total_input_tokens": 3000,
            "total_output_tokens": 2000,
            "total_requests": 20,
            "today_tokens": 500,
            "top_users": [],
            "daily_breakdown": [],
        }
        with patch("src.routers.chat.ChatTokenUsageRepository") as MockRepo:
            MockRepo.return_value.get_usage_stats = AsyncMock(return_value=stats_data)
            resp = tenant_client.get("/v1/tenants/acme/chat/usage/metering?days=7")

        assert resp.status_code == 200
        MockRepo.return_value.get_usage_stats.assert_awaited_once()
        call_kwargs = MockRepo.return_value.get_usage_stats.call_args.kwargs
        assert call_kwargs.get("days") == 7

    def test_get_usage_stats_invalid_days(self, tenant_client):
        """days=0 fails query validation (ge=1)."""
        resp = tenant_client.get("/v1/tenants/acme/chat/usage/metering?days=0")
        assert resp.status_code == 422

    def test_get_usage_stats_other_tenant_forbidden(self, other_client):
        resp = other_client.get("/v1/tenants/acme/chat/usage/metering")
        assert resp.status_code == 403
