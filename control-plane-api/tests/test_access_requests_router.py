"""Tests for Access Requests Router — CAB-1378

Public endpoint (no auth): POST /v1/access-requests
  - Rate-limited (5/min per IP)
  - Honeypot anti-bot (website field)
  - Slack notification on new request
Admin endpoint (cpi-admin): GET /v1/admin/access-requests
  - Paginated list with status filter
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.middleware.rate_limit import limiter


@pytest.fixture(autouse=True)
def _disable_rate_limit():
    """Disable rate limiting for all tests in this module."""
    limiter.enabled = False
    yield
    limiter.enabled = True


class TestAccessRequestsRouter:
    """Test suite for public POST /v1/access-requests."""

    def _create_mock_access_request(self, **overrides):
        """Create a mock AccessRequest ORM object."""
        mock = MagicMock()
        defaults = {
            "id": uuid4(),
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "company": "ACME",
            "role": "developer",
            "source": "portal",
            "status": "pending",
        }
        for k, v in {**defaults, **overrides}.items():
            setattr(mock, k, v)
        return mock

    def test_create_new_request_201(self, client, mock_db_session, app):
        """POST with new email returns 201."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        # simulate: no existing record
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # After db.add + flush, access_request.id must be set
        def side_effect_add(obj):
            obj.id = uuid4()

        mock_db_session.add = MagicMock(side_effect=side_effect_add)

        with TestClient(app) as tc:
            response = tc.post(
                "/v1/access-requests",
                json={
                    "email": "new@example.com",
                    "first_name": "New",
                    "last_name": "User",
                    "company": "Startup Inc",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Thank you! We'll reach out shortly."
        assert "request_id" in data
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_awaited_once()

    def test_create_duplicate_request_200(self, client, mock_db_session, app):
        """POST with existing email returns 200 (idempotent)."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        existing = self._create_mock_access_request(email="existing@example.com")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app) as tc:
            response = tc.post(
                "/v1/access-requests",
                json={"email": "existing@example.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Thank you! We'll reach out shortly."
        assert data["request_id"] == str(existing.id)
        # Should NOT add a new record
        mock_db_session.add.assert_not_called()

    def test_create_request_invalid_email_422(self, client, app):
        """POST with invalid email returns 422 validation error."""
        with TestClient(app) as tc:
            response = tc.post(
                "/v1/access-requests",
                json={"email": "not-an-email"},
            )

        assert response.status_code == 422

    def test_create_request_missing_email_422(self, client, app):
        """POST without email field returns 422."""
        with TestClient(app) as tc:
            response = tc.post(
                "/v1/access-requests",
                json={"first_name": "Test"},
            )

        assert response.status_code == 422


class TestHoneypotProtection:
    """Test honeypot anti-bot field on POST /v1/access-requests."""

    def test_honeypot_filled_returns_fake_201(self, mock_db_session, app):
        """POST with honeypot website field filled returns 201 without DB write."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as tc:
            response = tc.post(
                "/v1/access-requests",
                json={
                    "email": "bot@spam.com",
                    "first_name": "Bot",
                    "website": "http://spam-site.com",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Thank you! We'll reach out shortly."
        assert "request_id" in data
        # Bot trapped: NO database write
        mock_db_session.add.assert_not_called()
        mock_db_session.execute.assert_not_called()

    def test_honeypot_empty_proceeds_normally(self, mock_db_session, app):
        """POST with empty honeypot field proceeds to normal flow."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        def side_effect_add(obj):
            obj.id = uuid4()

        mock_db_session.add = MagicMock(side_effect=side_effect_add)

        with TestClient(app) as tc:
            response = tc.post(
                "/v1/access-requests",
                json={
                    "email": "real-user@example.com",
                    "website": "",  # Empty string = not a bot
                },
            )

        assert response.status_code == 201
        mock_db_session.add.assert_called_once()

    def test_honeypot_absent_proceeds_normally(self, mock_db_session, app):
        """POST without honeypot field at all proceeds to normal flow."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        def side_effect_add(obj):
            obj.id = uuid4()

        mock_db_session.add = MagicMock(side_effect=side_effect_add)

        with TestClient(app) as tc:
            response = tc.post(
                "/v1/access-requests",
                json={"email": "legit@example.com"},
            )

        assert response.status_code == 201
        mock_db_session.add.assert_called_once()


class TestSlackNotification:
    """Test Slack notification on new access request."""

    def test_slack_notification_triggered_on_new_request(self, mock_db_session, app):
        """New request fires Slack notification via asyncio.create_task."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        def side_effect_add(obj):
            obj.id = uuid4()

        mock_db_session.add = MagicMock(side_effect=side_effect_add)

        mock_notify = AsyncMock()
        with patch("src.routers.access_requests._notify_slack_new_request", mock_notify):
            with TestClient(app) as tc:
                response = tc.post(
                    "/v1/access-requests",
                    json={
                        "email": "notify-test@example.com",
                        "company": "Notify Corp",
                    },
                )

            assert response.status_code == 201
            # _notify_slack_new_request is called to create the coroutine for create_task
            mock_notify.assert_called_once_with("notify-test@example.com", "Notify Corp", None)

    def test_slack_notification_not_triggered_on_duplicate(self, mock_db_session, app):
        """Duplicate email does NOT fire Slack notification."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        existing = MagicMock()
        existing.id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        mock_notify = AsyncMock()
        with patch("src.routers.access_requests._notify_slack_new_request", mock_notify):
            with TestClient(app) as tc:
                response = tc.post(
                    "/v1/access-requests",
                    json={"email": "existing@example.com"},
                )

            assert response.status_code == 200
            mock_notify.assert_not_called()

    def test_slack_notification_not_triggered_on_honeypot(self, mock_db_session, app):
        """Honeypot-trapped request does NOT fire Slack notification."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        mock_notify = AsyncMock()
        with patch("src.routers.access_requests._notify_slack_new_request", mock_notify):
            with TestClient(app) as tc:
                response = tc.post(
                    "/v1/access-requests",
                    json={
                        "email": "bot@spam.com",
                        "website": "http://spam.com",
                    },
                )

            assert response.status_code == 201
            mock_notify.assert_not_called()


class TestAdminAccessRequests:
    """Test suite for admin GET /v1/admin/access-requests."""

    def _create_mock_access_request(self, **overrides):
        """Create a mock AccessRequest ORM object with from_attributes support."""
        defaults = {
            "id": uuid4(),
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "company": "ACME",
            "role": "developer",
            "source": "portal",
            "status": "pending",
            "created_at": datetime(2026, 2, 24, 12, 0, 0, tzinfo=UTC),
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def test_admin_list_returns_200(self, client_as_cpi_admin, mock_db_session):
        """cpi-admin can list access requests."""
        item = self._create_mock_access_request()

        # First call: count query
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        # Second call: data query
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = [item]

        mock_db_session.execute = AsyncMock(side_effect=[count_result, data_result])

        response = client_as_cpi_admin.get("/v1/admin/access-requests")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["limit"] == 25
        assert len(data["data"]) == 1
        assert data["data"][0]["email"] == "test@example.com"

    def test_admin_list_forbidden_for_tenant_admin(self, app, mock_db_session):
        """tenant-admin gets 403 on admin endpoint."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db

        mock_user = MagicMock()
        mock_user.roles = ["tenant-admin"]

        async def override_get_current_user():
            return mock_user

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as tc:
            response = tc.get("/v1/admin/access-requests")

        assert response.status_code == 403
        assert "Platform admin access required" in response.json()["detail"]

    def test_admin_list_forbidden_for_viewer(self, app, mock_db_session):
        """viewer gets 403 on admin endpoint."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db

        mock_user = MagicMock()
        mock_user.roles = ["viewer"]

        async def override_get_current_user():
            return mock_user

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as tc:
            response = tc.get("/v1/admin/access-requests")

        assert response.status_code == 403

    def test_admin_list_with_status_filter(self, client_as_cpi_admin, mock_db_session):
        """Status filter passes through to query."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[count_result, data_result])

        response = client_as_cpi_admin.get("/v1/admin/access-requests?status=contacted")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["data"] == []

    def test_admin_list_pagination(self, client_as_cpi_admin, mock_db_session):
        """Custom page and limit parameters work."""
        count_result = MagicMock()
        count_result.scalar.return_value = 50

        items = [self._create_mock_access_request(email=f"user{i}@example.com") for i in range(10)]
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = items

        mock_db_session.execute = AsyncMock(side_effect=[count_result, data_result])

        response = client_as_cpi_admin.get("/v1/admin/access-requests?page=2&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 50
        assert data["page"] == 2
        assert data["limit"] == 10
        assert len(data["data"]) == 10
