"""Tests for WebhookService CRUD + dispatch (CAB-1291)"""
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.services.webhook_service import (
    MAX_RETRY_ATTEMPTS,
    RETRY_DELAYS,
    WebhookService,
)


def _mock_db():
    """Create mock async session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _mock_webhook(**kwargs):
    """Create mock TenantWebhook."""
    wh = MagicMock()
    wh.id = kwargs.get("id", uuid4())
    wh.tenant_id = kwargs.get("tenant_id", "acme")
    wh.name = kwargs.get("name", "test-hook")
    wh.url = kwargs.get("url", "https://example.com/webhook")
    wh.events = kwargs.get("events", ["*"])
    wh.secret = kwargs.get("secret", None)
    wh.headers = kwargs.get("headers", {})
    wh.enabled = kwargs.get("enabled", True)
    wh.created_by = kwargs.get("created_by", None)
    wh.created_at = kwargs.get("created_at", datetime(2026, 2, 16))
    return wh


# ── Constants ──


class TestConstants:
    def test_retry_config(self):
        assert MAX_RETRY_ATTEMPTS == 5
        assert len(RETRY_DELAYS) == 5
        assert RETRY_DELAYS[0] == 60
        assert RETRY_DELAYS[-1] == 7200


# ── create_webhook ──


class TestCreateWebhook:
    async def test_creates(self):
        db = _mock_db()
        svc = WebhookService(db)

        with patch("src.services.webhook_service.TenantWebhook") as MockWH:
            mock_instance = _mock_webhook()
            MockWH.return_value = mock_instance

            result = await svc.create_webhook(
                "acme", "My Hook", "https://example.com/hook",
                events=["*"], secret="s3cret", created_by="alice"
            )
        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        assert result is mock_instance

    async def test_invalid_event_raises(self):
        db = _mock_db()
        svc = WebhookService(db)

        with pytest.raises(ValueError, match="Invalid event type"):
            await svc.create_webhook(
                "acme", "Bad Hook", "https://example.com",
                events=["nonexistent.event.type.invalid"]
            )


# ── get_webhook ──


class TestGetWebhook:
    async def test_found(self):
        db = _mock_db()
        wh = _mock_webhook()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = wh
        db.execute = AsyncMock(return_value=mock_result)

        svc = WebhookService(db)
        result = await svc.get_webhook(wh.id)
        assert result is wh

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        svc = WebhookService(db)
        result = await svc.get_webhook(uuid4())
        assert result is None


# ── list_webhooks ──


class TestListWebhooks:
    async def test_all(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_webhook(), _mock_webhook()]
        db.execute = AsyncMock(return_value=mock_result)

        svc = WebhookService(db)
        hooks = await svc.list_webhooks("acme")
        assert len(hooks) == 2

    async def test_enabled_only(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_webhook(enabled=True)]
        db.execute = AsyncMock(return_value=mock_result)

        svc = WebhookService(db)
        hooks = await svc.list_webhooks("acme", enabled_only=True)
        assert len(hooks) == 1


# ── update_webhook ──


class TestUpdateWebhook:
    async def test_not_found(self):
        db = _mock_db()
        svc = WebhookService(db)
        svc.get_webhook = AsyncMock(return_value=None)

        result = await svc.update_webhook(uuid4(), name="Updated")
        assert result is None

    async def test_update_name(self):
        db = _mock_db()
        wh = _mock_webhook()
        svc = WebhookService(db)
        svc.get_webhook = AsyncMock(return_value=wh)

        result = await svc.update_webhook(wh.id, name="New Name")
        assert result is wh
        assert wh.name == "New Name"

    async def test_update_events_invalid(self):
        db = _mock_db()
        wh = _mock_webhook()
        svc = WebhookService(db)
        svc.get_webhook = AsyncMock(return_value=wh)

        with pytest.raises(ValueError, match="Invalid event type"):
            await svc.update_webhook(wh.id, events=["bad.event.type.xyz"])

    async def test_update_url_and_enabled(self):
        db = _mock_db()
        wh = _mock_webhook()
        svc = WebhookService(db)
        svc.get_webhook = AsyncMock(return_value=wh)

        await svc.update_webhook(wh.id, url="https://new.com", enabled=False)
        assert wh.url == "https://new.com"
        assert wh.enabled is False
