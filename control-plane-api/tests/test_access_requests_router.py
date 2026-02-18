"""Tests for Access Requests Router — CAB-1378

Public endpoint (no auth): POST /v1/access-requests
Idempotent email capture for Developer Portal.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class TestAccessRequestsRouter:
    """Test suite for Access Requests Router endpoints."""

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
