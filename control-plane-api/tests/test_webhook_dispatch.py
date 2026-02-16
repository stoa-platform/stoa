"""Tests for WebhookService dispatch + delivery logic (CAB-1291)"""
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.services.webhook_service import (
    WebhookService,
    emit_deployment_failed,
    emit_deployment_rolled_back,
    emit_deployment_started,
    emit_deployment_succeeded,
    emit_subscription_approved,
    emit_subscription_created,
    emit_subscription_key_rotated,
    emit_subscription_revoked,
)


def _mock_db():
    """Create mock async session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
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
    wh.matches_event = kwargs.get("matches_event", MagicMock(return_value=True))
    return wh


def _mock_subscription(**kwargs):
    """Create mock Subscription."""
    sub = MagicMock()
    sub.id = kwargs.get("id", uuid4())
    sub.tenant_id = kwargs.get("tenant_id", "acme")
    sub.application_id = kwargs.get("application_id", "app-1")
    sub.application_name = kwargs.get("application_name", "My App")
    sub.api_id = kwargs.get("api_id", "api-1")
    sub.api_name = kwargs.get("api_name", "Weather API")
    sub.subscriber_id = kwargs.get("subscriber_id", "user-1")
    sub.subscriber_email = kwargs.get("subscriber_email", "user@example.com")
    sub.status = kwargs.get("status", MagicMock(value="active"))
    sub.approved_by = kwargs.get("approved_by", None)
    sub.approved_at = kwargs.get("approved_at", None)
    sub.revoked_by = kwargs.get("revoked_by", None)
    sub.revoked_at = kwargs.get("revoked_at", None)
    sub.status_reason = kwargs.get("status_reason", None)
    sub.rotation_count = kwargs.get("rotation_count", 0)
    sub.last_rotated_at = kwargs.get("last_rotated_at", None)
    sub.previous_key_expires_at = kwargs.get("previous_key_expires_at", None)
    return sub


def _mock_deployment(**kwargs):
    """Create mock Deployment."""
    dep = MagicMock()
    dep.id = kwargs.get("id", uuid4())
    dep.api_id = kwargs.get("api_id", "api-1")
    dep.api_name = kwargs.get("api_name", "Weather")
    dep.tenant_id = kwargs.get("tenant_id", "acme")
    dep.environment = kwargs.get("environment", "production")
    dep.version = kwargs.get("version", "1.0.0")
    dep.status = kwargs.get("status", "in_progress")
    dep.deployed_by = kwargs.get("deployed_by", "alice")
    dep.error_message = kwargs.get("error_message", None)
    dep.rollback_of = kwargs.get("rollback_of", None)
    dep.rollback_version = kwargs.get("rollback_version", None)
    return dep


# ── delete_webhook ──


class TestDeleteWebhook:
    async def test_found(self):
        db = _mock_db()
        svc = WebhookService(db)
        wh = _mock_webhook()
        svc.get_webhook = AsyncMock(return_value=wh)

        result = await svc.delete_webhook(wh.id)
        assert result is True
        db.delete.assert_awaited_once_with(wh)

    async def test_not_found(self):
        db = _mock_db()
        svc = WebhookService(db)
        svc.get_webhook = AsyncMock(return_value=None)

        result = await svc.delete_webhook(uuid4())
        assert result is False


# ── _build_payload ──


class TestBuildPayload:
    def test_basic(self):
        db = _mock_db()
        svc = WebhookService(db)
        sub = _mock_subscription()
        payload = svc._build_payload("subscription.created", sub)
        assert payload["event"] == "subscription.created"
        assert payload["data"]["subscription_id"] == str(sub.id)
        assert payload["data"]["api_name"] == "Weather API"

    def test_approved_event(self):
        db = _mock_db()
        svc = WebhookService(db)
        sub = _mock_subscription(approved_by="admin", approved_at=datetime(2026, 2, 16))
        payload = svc._build_payload("subscription.approved", sub)
        assert payload["data"]["approved_by"] == "admin"

    def test_revoked_event(self):
        db = _mock_db()
        svc = WebhookService(db)
        sub = _mock_subscription(
            revoked_by="admin",
            revoked_at=datetime(2026, 2, 16),
            status_reason="violation",
        )
        payload = svc._build_payload("subscription.revoked", sub)
        assert payload["data"]["revoked_by"] == "admin"
        assert payload["data"]["reason"] == "violation"

    def test_key_rotated_event(self):
        db = _mock_db()
        svc = WebhookService(db)
        sub = _mock_subscription(
            rotation_count=3,
            last_rotated_at=datetime(2026, 2, 16),
            previous_key_expires_at=datetime(2026, 2, 17),
        )
        payload = svc._build_payload("subscription.key_rotated", sub)
        assert payload["data"]["rotation_count"] == 3

    def test_additional_data(self):
        db = _mock_db()
        svc = WebhookService(db)
        sub = _mock_subscription()
        payload = svc._build_payload("subscription.created", sub, {"extra": "data"})
        assert payload["data"]["extra"] == "data"


# ── _generate_signature ──


class TestGenerateSignature:
    def test_signature(self):
        db = _mock_db()
        svc = WebhookService(db)
        signature = svc._generate_signature("secret", {"key": "value"})
        assert signature.startswith("sha256=")
        assert len(signature) > 10

    def test_different_secrets_different_signatures(self):
        db = _mock_db()
        svc = WebhookService(db)
        sig1 = svc._generate_signature("secret1", {"key": "value"})
        sig2 = svc._generate_signature("secret2", {"key": "value"})
        assert sig1 != sig2


# ── _build_deployment_payload ──


class TestBuildDeploymentPayload:
    def test_basic(self):
        db = _mock_db()
        svc = WebhookService(db)
        dep = _mock_deployment()
        payload = svc._build_deployment_payload("deployment.started", dep)
        assert payload["event"] == "deployment.started"
        assert payload["data"]["version"] == "1.0.0"
        assert payload["data"]["environment"] == "production"

    def test_failed_event(self):
        db = _mock_db()
        svc = WebhookService(db)
        dep = _mock_deployment(error_message="timeout")
        payload = svc._build_deployment_payload("deployment.failed", dep)
        assert payload["data"]["error_message"] == "timeout"

    def test_rolled_back_event(self):
        db = _mock_db()
        svc = WebhookService(db)
        rollback_id = uuid4()
        dep = _mock_deployment(rollback_of=rollback_id, rollback_version="0.9.0")
        payload = svc._build_deployment_payload("deployment.rolled_back", dep)
        assert payload["data"]["rollback_of"] == str(rollback_id)
        assert payload["data"]["rollback_version"] == "0.9.0"

    def test_additional_data(self):
        db = _mock_db()
        svc = WebhookService(db)
        dep = _mock_deployment()
        payload = svc._build_deployment_payload("deployment.started", dep, {"ci_url": "http://ci"})
        assert payload["data"]["ci_url"] == "http://ci"


# ── dispatch_event ──


class TestDispatchEvent:
    async def test_no_matching_webhooks(self):
        db = _mock_db()
        svc = WebhookService(db)
        svc.list_webhooks = AsyncMock(return_value=[])
        sub = _mock_subscription()

        result = await svc.dispatch_event("subscription.created", sub)
        assert result == []

    async def test_webhooks_not_matching_event(self):
        db = _mock_db()
        svc = WebhookService(db)
        wh = _mock_webhook(matches_event=MagicMock(return_value=False))
        svc.list_webhooks = AsyncMock(return_value=[wh])
        sub = _mock_subscription()

        result = await svc.dispatch_event("subscription.created", sub)
        assert result == []

    async def test_dispatches_to_matching(self):
        db = _mock_db()
        svc = WebhookService(db)
        wh = _mock_webhook()
        svc.list_webhooks = AsyncMock(return_value=[wh])
        sub = _mock_subscription()

        with patch("src.services.webhook_service.WebhookDelivery") as MockDelivery, \
             patch("src.services.webhook_service.asyncio.create_task"):
            mock_delivery = MagicMock()
            MockDelivery.return_value = mock_delivery
            result = await svc.dispatch_event("subscription.created", sub)

        assert len(result) == 1
        db.add.assert_called_once()


# ── dispatch_deployment_event ──


class TestDispatchDeploymentEvent:
    async def test_no_webhooks(self):
        db = _mock_db()
        svc = WebhookService(db)
        svc.list_webhooks = AsyncMock(return_value=[])
        dep = _mock_deployment()

        result = await svc.dispatch_deployment_event("deployment.started", dep)
        assert result == []

    async def test_dispatches(self):
        db = _mock_db()
        svc = WebhookService(db)
        wh = _mock_webhook()
        svc.list_webhooks = AsyncMock(return_value=[wh])
        dep = _mock_deployment()

        with patch("src.services.webhook_service.WebhookDelivery") as MockDelivery, \
             patch("src.services.webhook_service.asyncio.create_task"):
            MockDelivery.return_value = MagicMock()
            result = await svc.dispatch_deployment_event("deployment.started", dep)

        assert len(result) == 1


# ── get_delivery_history ──


class TestGetDeliveryHistory:
    async def test_returns_list(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=mock_result)

        svc = WebhookService(db)
        result = await svc.get_delivery_history(uuid4())
        assert len(result) == 2


# ── retry_delivery ──


class TestRetryDelivery:
    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        svc = WebhookService(db)
        result = await svc.retry_delivery(uuid4())
        assert result is None

    async def test_not_failed_raises(self):
        db = _mock_db()
        delivery = MagicMock()
        delivery.status = "success"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        db.execute = AsyncMock(return_value=mock_result)

        svc = WebhookService(db)
        with pytest.raises(ValueError, match="only retry failed"):
            await svc.retry_delivery(uuid4())

    async def test_webhook_gone_raises(self):
        db = _mock_db()
        delivery = MagicMock()
        delivery.status = "failed"
        delivery.webhook_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        db.execute = AsyncMock(return_value=mock_result)

        svc = WebhookService(db)
        svc.get_webhook = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="no longer exists"):
            await svc.retry_delivery(uuid4())

    async def test_retry_success(self):
        db = _mock_db()
        delivery = MagicMock()
        delivery.status = "failed"
        delivery.webhook_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        db.execute = AsyncMock(return_value=mock_result)

        svc = WebhookService(db)
        wh = _mock_webhook()
        svc.get_webhook = AsyncMock(return_value=wh)

        with patch("src.services.webhook_service.asyncio.create_task"):
            result = await svc.retry_delivery(uuid4())
        assert result is delivery
        assert delivery.attempt_count == 0


# ── Emit helpers ──


class TestEmitHelpers:
    async def test_emit_subscription_created(self):
        db = _mock_db()
        sub = _mock_subscription()
        with patch("src.services.webhook_service.WebhookService") as MockSvc:
            MockSvc.return_value.dispatch_event = AsyncMock(return_value=[])
            await emit_subscription_created(db, sub)
            MockSvc.return_value.dispatch_event.assert_awaited_once()

    async def test_emit_subscription_approved(self):
        db = _mock_db()
        sub = _mock_subscription()
        with patch("src.services.webhook_service.WebhookService") as MockSvc:
            MockSvc.return_value.dispatch_event = AsyncMock(return_value=[])
            await emit_subscription_approved(db, sub)

    async def test_emit_subscription_revoked(self):
        db = _mock_db()
        sub = _mock_subscription()
        with patch("src.services.webhook_service.WebhookService") as MockSvc:
            MockSvc.return_value.dispatch_event = AsyncMock(return_value=[])
            await emit_subscription_revoked(db, sub)

    async def test_emit_subscription_key_rotated(self):
        db = _mock_db()
        sub = _mock_subscription()
        with patch("src.services.webhook_service.WebhookService") as MockSvc:
            MockSvc.return_value.dispatch_event = AsyncMock(return_value=[])
            await emit_subscription_key_rotated(db, sub, grace_period_hours=24)

    async def test_emit_deployment_started(self):
        db = _mock_db()
        dep = _mock_deployment()
        with patch("src.services.webhook_service.WebhookService") as MockSvc:
            MockSvc.return_value.dispatch_deployment_event = AsyncMock(return_value=[])
            await emit_deployment_started(db, dep)

    async def test_emit_deployment_succeeded(self):
        db = _mock_db()
        dep = _mock_deployment()
        with patch("src.services.webhook_service.WebhookService") as MockSvc:
            MockSvc.return_value.dispatch_deployment_event = AsyncMock(return_value=[])
            await emit_deployment_succeeded(db, dep)

    async def test_emit_deployment_failed(self):
        db = _mock_db()
        dep = _mock_deployment()
        with patch("src.services.webhook_service.WebhookService") as MockSvc:
            MockSvc.return_value.dispatch_deployment_event = AsyncMock(return_value=[])
            await emit_deployment_failed(db, dep)

    async def test_emit_deployment_rolled_back(self):
        db = _mock_db()
        dep = _mock_deployment()
        with patch("src.services.webhook_service.WebhookService") as MockSvc:
            MockSvc.return_value.dispatch_deployment_event = AsyncMock(return_value=[])
            await emit_deployment_rolled_back(db, dep)
