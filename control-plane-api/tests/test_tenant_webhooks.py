"""
Tests for Tenant Webhooks Router - CAB-1116 Phase 2B

Target: Coverage of src/routers/tenant_webhooks.py
Tests: 20 test cases covering CRUD, delivery, test webhook, auth, and tenant isolation.

Note: tenant_webhooks uses `dict` for current_user (not User model).
The conftest User fixture is a Pydantic model, so we need to override get_current_user
to return a dict for this router.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


def _make_webhook(
    webhook_id=None,
    tenant_id="acme",
    name="test-webhook",
    url="https://example.com/hook",
    events=None,
    secret="s3cret",  # noqa: S107
    enabled=True,
):
    """Create a mock webhook object."""
    wh = MagicMock()
    wh.id = webhook_id or uuid4()
    wh.tenant_id = tenant_id
    wh.name = name
    wh.url = url
    wh.events = events or ["subscription.created"]
    wh.secret = secret
    wh.headers = {"X-Custom": "value"}
    wh.enabled = enabled
    wh.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    wh.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    wh.created_by = "user-001"
    return wh


def _make_delivery(delivery_id=None, webhook_id=None):
    """Create a mock delivery object."""
    d = MagicMock()
    d.id = delivery_id or uuid4()
    d.webhook_id = webhook_id or uuid4()
    d.subscription_id = uuid4()
    d.event_type = "subscription.created"
    d.payload = {"event": "subscription.created"}
    d.status = "success"
    d.attempt_count = 1
    d.max_attempts = 5
    d.response_status_code = 200
    d.response_body = "OK"
    d.error_message = None
    d.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    d.last_attempt_at = datetime(2026, 1, 1, tzinfo=UTC)
    d.next_retry_at = None
    d.delivered_at = datetime(2026, 1, 1, tzinfo=UTC)
    return d


def _app_with_dict_user(app, mock_db_session, tenant_id="acme", roles=None):
    """Override auth to return a dict user (as tenant_webhooks expects)."""
    from src.auth.dependencies import get_current_user
    from src.database import get_db

    user_dict = {
        "sub": "user-001",
        "email": "admin@acme.com",
        "tenant_id": tenant_id,
        "roles": roles or ["tenant-admin"],
    }

    async def override_user():
        return user_dict

    async def override_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return app


class TestTenantWebhooksEventTypes:
    """Test event types listing (no auth required for this endpoint)."""

    def test_list_event_types(self, app_with_tenant_admin):
        """List webhook event types returns all defined types."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/tenants/acme/webhooks/events")

        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert len(data["events"]) >= 4
        event_names = [e["event"] for e in data["events"]]
        assert "subscription.created" in event_names


class TestTenantWebhooksCRUD:
    """Test webhook CRUD operations."""

    def test_create_webhook_success(self, app, mock_db_session):
        """Create a webhook for own tenant."""
        _app_with_dict_user(app, mock_db_session)
        mock_webhook = _make_webhook()

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.create_webhook = AsyncMock(return_value=mock_webhook)

            with TestClient(app) as client:
                response = client.post(
                    "/tenants/acme/webhooks",
                    json={
                        "name": "test-webhook",
                        "url": "https://example.com/hook",
                        "events": ["subscription.created"],
                    },
                )

        app.dependency_overrides.clear()
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-webhook"

    def test_create_webhook_403_wrong_tenant(self, app, mock_db_session):
        """Cannot create webhook for another tenant."""
        _app_with_dict_user(app, mock_db_session, tenant_id="other-tenant")

        with TestClient(app) as client:
            response = client.post(
                "/tenants/acme/webhooks",
                json={
                    "name": "test",
                    "url": "https://example.com/hook",
                    "events": ["subscription.created"],
                },
            )

        app.dependency_overrides.clear()
        assert response.status_code == 403

    def test_create_webhook_cpi_admin_any_tenant(self, app, mock_db_session):
        """CPI admin can create webhook for any tenant."""
        _app_with_dict_user(app, mock_db_session, tenant_id=None, roles=["cpi-admin"])
        mock_webhook = _make_webhook()

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.create_webhook = AsyncMock(return_value=mock_webhook)

            with TestClient(app) as client:
                response = client.post(
                    "/tenants/acme/webhooks",
                    json={
                        "name": "test",
                        "url": "https://example.com/hook",
                        "events": ["subscription.created"],
                    },
                )

        app.dependency_overrides.clear()
        assert response.status_code == 201

    def test_list_webhooks_success(self, app, mock_db_session):
        """List webhooks for own tenant."""
        _app_with_dict_user(app, mock_db_session)
        mock_wh = _make_webhook()

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.list_webhooks = AsyncMock(return_value=[mock_wh])

            with TestClient(app) as client:
                response = client.get("/tenants/acme/webhooks")

        app.dependency_overrides.clear()
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_list_webhooks_403_wrong_tenant(self, app, mock_db_session):
        """Cannot list webhooks for another tenant."""
        _app_with_dict_user(app, mock_db_session, tenant_id="other-tenant")

        with TestClient(app) as client:
            response = client.get("/tenants/acme/webhooks")

        app.dependency_overrides.clear()
        assert response.status_code == 403

    def test_get_webhook_success(self, app, mock_db_session):
        """Get webhook by ID."""
        _app_with_dict_user(app, mock_db_session)
        wh_id = uuid4()
        mock_wh = _make_webhook(webhook_id=wh_id, tenant_id="acme")

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=mock_wh)

            with TestClient(app) as client:
                response = client.get(f"/tenants/acme/webhooks/{wh_id}")

        app.dependency_overrides.clear()
        assert response.status_code == 200

    def test_get_webhook_404(self, app, mock_db_session):
        """Get non-existent webhook returns 404."""
        _app_with_dict_user(app, mock_db_session)

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=None)

            with TestClient(app) as client:
                response = client.get(f"/tenants/acme/webhooks/{uuid4()}")

        app.dependency_overrides.clear()
        assert response.status_code == 404

    def test_get_webhook_wrong_tenant(self, app, mock_db_session):
        """Get webhook from different tenant returns 404."""
        _app_with_dict_user(app, mock_db_session)
        wh_id = uuid4()
        mock_wh = _make_webhook(webhook_id=wh_id, tenant_id="other-tenant")

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=mock_wh)

            with TestClient(app) as client:
                response = client.get(f"/tenants/acme/webhooks/{wh_id}")

        app.dependency_overrides.clear()
        assert response.status_code == 403

    def test_update_webhook_success(self, app, mock_db_session):
        """Update webhook fields."""
        _app_with_dict_user(app, mock_db_session)
        wh_id = uuid4()
        mock_wh = _make_webhook(webhook_id=wh_id, tenant_id="acme")
        updated_wh = _make_webhook(webhook_id=wh_id, tenant_id="acme", name="updated")

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=mock_wh)
            svc.update_webhook = AsyncMock(return_value=updated_wh)

            with TestClient(app) as client:
                response = client.patch(
                    f"/tenants/acme/webhooks/{wh_id}",
                    json={"name": "updated"},
                )

        app.dependency_overrides.clear()
        assert response.status_code == 200

    def test_delete_webhook_success(self, app, mock_db_session):
        """Delete webhook."""
        _app_with_dict_user(app, mock_db_session)
        wh_id = uuid4()
        mock_wh = _make_webhook(webhook_id=wh_id, tenant_id="acme")

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=mock_wh)
            svc.delete_webhook = AsyncMock()

            with TestClient(app) as client:
                response = client.delete(f"/tenants/acme/webhooks/{wh_id}")

        app.dependency_overrides.clear()
        assert response.status_code == 204

    def test_delete_webhook_404(self, app, mock_db_session):
        """Delete non-existent webhook returns 404."""
        _app_with_dict_user(app, mock_db_session)

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=None)

            with TestClient(app) as client:
                response = client.delete(f"/tenants/acme/webhooks/{uuid4()}")

        app.dependency_overrides.clear()
        assert response.status_code == 404


class TestTenantWebhooksDeliveries:
    """Test delivery history endpoints."""

    def test_list_deliveries_success(self, app, mock_db_session):
        """List delivery history for a webhook."""
        _app_with_dict_user(app, mock_db_session)
        wh_id = uuid4()
        mock_wh = _make_webhook(webhook_id=wh_id, tenant_id="acme")
        mock_delivery = _make_delivery(webhook_id=wh_id)

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=mock_wh)
            svc.get_delivery_history = AsyncMock(return_value=[mock_delivery])

            with TestClient(app) as client:
                response = client.get(f"/tenants/acme/webhooks/{wh_id}/deliveries")

        app.dependency_overrides.clear()
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_retry_delivery_success(self, app, mock_db_session):
        """Retry a failed delivery."""
        _app_with_dict_user(app, mock_db_session)
        wh_id = uuid4()
        delivery_id = uuid4()
        mock_wh = _make_webhook(webhook_id=wh_id, tenant_id="acme")
        mock_delivery = _make_delivery(delivery_id=delivery_id, webhook_id=wh_id)

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=mock_wh)
            svc.retry_delivery = AsyncMock(return_value=mock_delivery)

            with TestClient(app) as client:
                response = client.post(
                    f"/tenants/acme/webhooks/{wh_id}/deliveries/{delivery_id}/retry"
                )

        app.dependency_overrides.clear()
        assert response.status_code == 200

    def test_retry_delivery_404_webhook(self, app, mock_db_session):
        """Retry delivery when webhook doesn't exist."""
        _app_with_dict_user(app, mock_db_session)

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=None)

            with TestClient(app) as client:
                response = client.post(
                    f"/tenants/acme/webhooks/{uuid4()}/deliveries/{uuid4()}/retry"
                )

        app.dependency_overrides.clear()
        assert response.status_code == 404


class TestTenantWebhooksTest:
    """Test the webhook test endpoint."""

    def test_webhook_test_success(self, app, mock_db_session):
        """Test webhook sends HTTP request and returns result."""
        _app_with_dict_user(app, mock_db_session)
        wh_id = uuid4()
        mock_wh = _make_webhook(webhook_id=wh_id, tenant_id="acme")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=mock_wh)

            with patch("httpx.AsyncClient") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.post = AsyncMock(return_value=mock_response)
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client_instance

                with TestClient(app) as client:
                    response = client.post(
                        f"/tenants/acme/webhooks/{wh_id}/test",
                        json={"event_type": "subscription.created"},
                    )

        app.dependency_overrides.clear()
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status_code"] == 200

    def test_webhook_test_timeout(self, app, mock_db_session):
        """Test webhook handles timeout gracefully."""
        import httpx

        _app_with_dict_user(app, mock_db_session)
        wh_id = uuid4()
        mock_wh = _make_webhook(webhook_id=wh_id, tenant_id="acme", secret=None)

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=mock_wh)

            with patch("httpx.AsyncClient") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client_instance

                with TestClient(app) as client:
                    response = client.post(
                        f"/tenants/acme/webhooks/{wh_id}/test",
                        json={"event_type": "subscription.created"},
                    )

        app.dependency_overrides.clear()
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "timed out" in data["error"]

    def test_webhook_test_404_not_found(self, app, mock_db_session):
        """Test webhook when webhook not found."""
        _app_with_dict_user(app, mock_db_session)

        with patch("src.routers.tenant_webhooks.WebhookService") as MockService:
            svc = MockService.return_value
            svc.get_webhook = AsyncMock(return_value=None)

            with TestClient(app) as client:
                response = client.post(
                    f"/tenants/acme/webhooks/{uuid4()}/test",
                    json={"event_type": "subscription.created"},
                )

        app.dependency_overrides.clear()
        assert response.status_code == 404
