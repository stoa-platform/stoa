"""Tests for Tenant Webhooks Router — CRUD operations for webhook configurations.

Covers: /tenants/{tenant_id}/webhooks (create, list, get, update, delete,
        list deliveries, retry, test, event types)

CRITICAL: This router uses current_user.get("tenant_id") — the user must be a dict,
          NOT a Pydantic User model. Custom app fixture required.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

WEBHOOK_SVC_PATH = "src.routers.tenant_webhooks.WebhookService"


def _mock_webhook(**overrides):
    """Build a MagicMock mimicking a Webhook ORM object."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "tenant_id": "acme",
        "name": "Test Webhook",
        "url": "https://example.com/hook",
        "events": ["subscription.created"],
        "secret": "test-secret-min16chars",
        "headers": {},
        "enabled": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "created_by": "tenant-admin-user-id",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _mock_delivery(**overrides):
    """Build a MagicMock mimicking a WebhookDelivery ORM object."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "webhook_id": uuid4(),
        "subscription_id": uuid4(),
        "event_type": "subscription.created",
        "payload": {"event": "subscription.created"},
        "status": "success",
        "attempt_count": 1,
        "max_attempts": 3,
        "response_status_code": 200,
        "response_body": "OK",
        "error_message": None,
        "created_at": datetime.utcnow(),
        "last_attempt_at": datetime.utcnow(),
        "next_retry_at": None,
        "delivered_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _build_webhook_app(app, mock_db_session, user_dict=None):
    """Build app with dict-based current_user override (tenant_webhooks router expects a dict)."""
    from src.auth import get_current_user
    from src.database import get_db

    if user_dict is None:
        user_dict = {
            "sub": "tenant-admin-user-id",
            "email": "admin@acme.com",
            "tenant_id": "acme",
            "roles": ["tenant-admin"],
        }

    async def override_user():
        return user_dict

    async def override_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return app


def _build_cpi_admin_app(app, mock_db_session):
    return _build_webhook_app(
        app,
        mock_db_session,
        user_dict={
            "sub": "cpi-admin-user-id",
            "email": "admin@gostoa.dev",
            "tenant_id": None,
            "roles": ["cpi-admin"],
        },
    )


def _build_other_tenant_app(app, mock_db_session):
    return _build_webhook_app(
        app,
        mock_db_session,
        user_dict={
            "sub": "other-tenant-user-id",
            "email": "user@other.com",
            "tenant_id": "other-tenant",
            "roles": ["tenant-admin"],
        },
    )


# ============================================================
# GET /events — list event types
# ============================================================


class TestListEventTypes:
    """Tests for GET /tenants/{tenant_id}/webhooks/events."""

    def test_list_event_types_success(self, app, mock_db_session):
        _build_webhook_app(app, mock_db_session)
        with TestClient(app) as client:
            resp = client.get("/tenants/acme/webhooks/events")

        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert len(data["events"]) > 0
        event_names = [e["event"] for e in data["events"]]
        assert "subscription.created" in event_names


# ============================================================
# POST /tenants/{tenant_id}/webhooks — create webhook
# ============================================================


class TestCreateWebhook:
    """Tests for POST /tenants/{tenant_id}/webhooks."""

    def _payload(self):
        return {
            "name": "My Webhook",
            "url": "https://example.com/hook",
            "events": ["subscription.created"],
            "secret": "a-valid-secret-key-1234",
        }

    def test_create_webhook_success(self, app, mock_db_session):
        wh = _mock_webhook()
        mock_svc = MagicMock()
        mock_svc.create_webhook = AsyncMock(return_value=wh)

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.post("/tenants/acme/webhooks", json=self._payload())

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Webhook"
        assert data["tenant_id"] == "acme"
        assert "secret" not in data  # secret is never returned directly
        assert "has_secret" in data

    def test_create_webhook_403_wrong_tenant(self, app, mock_db_session):
        """A tenant-admin cannot create a webhook for another tenant."""
        _build_other_tenant_app(app, mock_db_session)

        with TestClient(app) as client:
            resp = client.post("/tenants/acme/webhooks", json=self._payload())

        assert resp.status_code == 403

    def test_create_webhook_cpi_admin_any_tenant(self, app, mock_db_session):
        """CPI admin can create webhooks for any tenant."""
        wh = _mock_webhook()
        mock_svc = MagicMock()
        mock_svc.create_webhook = AsyncMock(return_value=wh)

        _build_cpi_admin_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.post("/tenants/acme/webhooks", json=self._payload())

        assert resp.status_code == 201

    def test_create_webhook_400_value_error(self, app, mock_db_session):
        """ValueError from service results in 400."""
        mock_svc = MagicMock()
        mock_svc.create_webhook = AsyncMock(side_effect=ValueError("Invalid URL"))

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.post("/tenants/acme/webhooks", json=self._payload())

        assert resp.status_code == 400


# ============================================================
# GET /tenants/{tenant_id}/webhooks — list webhooks
# ============================================================


class TestListWebhooks:
    """Tests for GET /tenants/{tenant_id}/webhooks."""

    def test_list_webhooks_success(self, app, mock_db_session):
        wh = _mock_webhook()
        mock_svc = MagicMock()
        mock_svc.list_webhooks = AsyncMock(return_value=[wh])

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.get("/tenants/acme/webhooks")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_webhooks_403_wrong_tenant(self, app, mock_db_session):
        _build_other_tenant_app(app, mock_db_session)

        with TestClient(app) as client:
            resp = client.get("/tenants/acme/webhooks")

        assert resp.status_code == 403

    def test_list_webhooks_empty(self, app, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.list_webhooks = AsyncMock(return_value=[])

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.get("/tenants/acme/webhooks")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ============================================================
# GET /tenants/{tenant_id}/webhooks/{id} — get webhook
# ============================================================


class TestGetWebhook:
    """Tests for GET /tenants/{tenant_id}/webhooks/{webhook_id}."""

    def test_get_webhook_success(self, app, mock_db_session):
        wh = _mock_webhook()
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.get(f"/tenants/acme/webhooks/{uuid4()}")

        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "acme"

    def test_get_webhook_404_not_found(self, app, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=None)

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.get(f"/tenants/acme/webhooks/{uuid4()}")

        assert resp.status_code == 404

    def test_get_webhook_403_wrong_tenant(self, app, mock_db_session):
        """Webhook belonging to another tenant returns 403."""
        wh = _mock_webhook(tenant_id="other-tenant")
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)

        _build_webhook_app(app, mock_db_session)  # acme user

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.get(f"/tenants/acme/webhooks/{uuid4()}")

        assert resp.status_code == 403

    def test_get_webhook_404_tenant_mismatch(self, app, mock_db_session):
        """Webhook from different tenant in URL path returns 404."""
        wh = _mock_webhook(tenant_id="acme")
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)

        _build_cpi_admin_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            # CPI admin but URL says different-tenant while webhook belongs to acme
            resp = client.get(f"/tenants/different-tenant/webhooks/{uuid4()}")

        assert resp.status_code == 404


# ============================================================
# PATCH /tenants/{tenant_id}/webhooks/{id} — update webhook
# ============================================================


class TestUpdateWebhook:
    """Tests for PATCH /tenants/{tenant_id}/webhooks/{webhook_id}."""

    def test_update_webhook_success(self, app, mock_db_session):
        wh = _mock_webhook(name="Old Name")
        updated_wh = _mock_webhook(name="New Name")
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)
        mock_svc.update_webhook = AsyncMock(return_value=updated_wh)

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.patch(
                f"/tenants/acme/webhooks/{uuid4()}",
                json={"name": "New Name"},
            )

        assert resp.status_code == 200

    def test_update_webhook_404_not_found(self, app, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=None)

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.patch(
                f"/tenants/acme/webhooks/{uuid4()}",
                json={"name": "Updated"},
            )

        assert resp.status_code == 404


# ============================================================
# DELETE /tenants/{tenant_id}/webhooks/{id} — delete webhook
# ============================================================


class TestDeleteWebhook:
    """Tests for DELETE /tenants/{tenant_id}/webhooks/{webhook_id}."""

    def test_delete_webhook_success(self, app, mock_db_session):
        wh = _mock_webhook()
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)
        mock_svc.delete_webhook = AsyncMock()

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.delete(f"/tenants/acme/webhooks/{uuid4()}")

        assert resp.status_code == 204

    def test_delete_webhook_404_not_found(self, app, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=None)

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.delete(f"/tenants/acme/webhooks/{uuid4()}")

        assert resp.status_code == 404

    def test_delete_webhook_403_wrong_tenant(self, app, mock_db_session):
        wh = _mock_webhook(tenant_id="other-tenant")
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)

        _build_webhook_app(app, mock_db_session)  # acme user

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.delete(f"/tenants/acme/webhooks/{uuid4()}")

        assert resp.status_code == 403


# ============================================================
# GET /tenants/{tenant_id}/webhooks/{id}/deliveries
# ============================================================


class TestListDeliveries:
    """Tests for GET /tenants/{tenant_id}/webhooks/{webhook_id}/deliveries."""

    def test_list_deliveries_success(self, app, mock_db_session):
        wh = _mock_webhook()
        delivery = _mock_delivery(webhook_id=wh.id)

        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)
        mock_svc.get_delivery_history = AsyncMock(return_value=[delivery])

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.get(f"/tenants/acme/webhooks/{uuid4()}/deliveries")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_deliveries_404_webhook_not_found(self, app, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=None)

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.get(f"/tenants/acme/webhooks/{uuid4()}/deliveries")

        assert resp.status_code == 404

    def test_list_deliveries_empty(self, app, mock_db_session):
        wh = _mock_webhook()
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)
        mock_svc.get_delivery_history = AsyncMock(return_value=[])

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.get(f"/tenants/acme/webhooks/{uuid4()}/deliveries")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ============================================================
# POST /tenants/{tenant_id}/webhooks/{id}/deliveries/{did}/retry
# ============================================================


class TestRetryDelivery:
    """Tests for POST /tenants/{tenant_id}/webhooks/{wid}/deliveries/{did}/retry."""

    def test_retry_delivery_success(self, app, mock_db_session):
        wh = _mock_webhook()
        delivery = _mock_delivery(webhook_id=wh.id)

        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)
        mock_svc.retry_delivery = AsyncMock(return_value=delivery)

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.post(f"/tenants/acme/webhooks/{uuid4()}/deliveries/{uuid4()}/retry")

        assert resp.status_code == 200
        assert resp.json()["event_type"] == "subscription.created"

    def test_retry_delivery_404_webhook_not_found(self, app, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=None)

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.post(f"/tenants/acme/webhooks/{uuid4()}/deliveries/{uuid4()}/retry")

        assert resp.status_code == 404

    def test_retry_delivery_404_delivery_not_found(self, app, mock_db_session):
        wh = _mock_webhook()
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)
        mock_svc.retry_delivery = AsyncMock(return_value=None)

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.post(f"/tenants/acme/webhooks/{uuid4()}/deliveries/{uuid4()}/retry")

        assert resp.status_code == 404


# ============================================================
# POST /tenants/{tenant_id}/webhooks/{id}/test
# ============================================================


class TestTestWebhook:
    """Tests for POST /tenants/{tenant_id}/webhooks/{webhook_id}/test."""

    def test_test_webhook_success(self, app, mock_db_session):
        """Test webhook endpoint calls the real HTTP machinery (mocked via httpx)."""

        wh = _mock_webhook()
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)

        _build_webhook_app(app, mock_db_session)

        # Mock httpx.AsyncClient so no real HTTP call is made
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.post = AsyncMock(return_value=mock_response)

        with (
            patch(WEBHOOK_SVC_PATH, return_value=mock_svc),
            patch("httpx.AsyncClient", return_value=mock_async_client),
            TestClient(app) as client,
        ):
            resp = client.post(
                f"/tenants/acme/webhooks/{uuid4()}/test",
                json={"event_type": "subscription.created"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["status_code"] == 200

    def test_test_webhook_404_not_found(self, app, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=None)

        _build_webhook_app(app, mock_db_session)

        with patch(WEBHOOK_SVC_PATH, return_value=mock_svc), TestClient(app) as client:
            resp = client.post(
                f"/tenants/acme/webhooks/{uuid4()}/test",
                json={"event_type": "subscription.created"},
            )

        assert resp.status_code == 404

    def test_test_webhook_timeout_handled(self, app, mock_db_session):
        """Timeout from httpx returns success=False with error message."""
        import httpx

        wh = _mock_webhook()
        mock_svc = MagicMock()
        mock_svc.get_webhook = AsyncMock(return_value=wh)

        _build_webhook_app(app, mock_db_session)

        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with (
            patch(WEBHOOK_SVC_PATH, return_value=mock_svc),
            patch("httpx.AsyncClient", return_value=mock_async_client),
            TestClient(app) as client,
        ):
            resp = client.post(
                f"/tenants/acme/webhooks/{uuid4()}/test",
                json={"event_type": "subscription.created"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "timed out" in data["error"].lower() or "timeout" in data["error"].lower()
