"""
Tests for TTL Extension Endpoint — CAB-86

Target: PATCH /v1/subscriptions/{id}/ttl
Tests: 11 cases covering happy path, limits, auth, edge cases
"""

from datetime import datetime, timedelta
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class SubscriptionStatus(str, Enum):
    """Mirror of src.models.subscription.SubscriptionStatus for testing."""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"


def _make_sub(overrides: dict | None = None) -> MagicMock:
    """Create a mock Subscription with TTL-related fields."""
    defaults = {
        "id": uuid4(),
        "application_id": "app-test-123",
        "application_name": "Test App",
        "subscriber_id": "tenant-admin-user-id",
        "subscriber_email": "admin@acme.com",
        "api_id": "api-weather-456",
        "api_name": "Weather API",
        "api_version": "1.0",
        "tenant_id": "acme",
        "plan_id": "basic",
        "plan_name": "Basic Plan",
        "api_key_hash": "hashed",
        "api_key_prefix": "stoa_sk_tes",
        "status": SubscriptionStatus.ACTIVE,
        "status_reason": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "approved_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=30),
        "revoked_at": None,
        "approved_by": "admin",
        "revoked_by": None,
        "previous_api_key_hash": None,
        "previous_key_expires_at": None,
        "last_rotated_at": None,
        "rotation_count": 0,
        "provisioning_status": "none",
        "gateway_app_id": None,
        "provisioning_error": None,
        "provisioned_at": None,
        "consumer_id": None,
        "ttl_extension_count": 0,
        "ttl_total_extended_days": 0,
    }
    if overrides:
        defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestTTLExtension:
    """Test suite for PATCH /v1/subscriptions/{id}/ttl"""

    def test_extend_ttl_7_days(self, app_with_tenant_admin, mock_db_session):
        """Happy path: extend by 7 days."""
        sub = _make_sub()
        original_expires = sub.expires_at

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service") as mock_kafka,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=sub)
            mock_kafka.publish = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 7, "reason": "Need more testing time"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["ttl_extension_count"] == 1
            assert data["ttl_total_extended_days"] == 7
            assert data["remaining_extensions"] == 1
            # expires_at should be 7 days later
            assert sub.expires_at == original_expires + timedelta(days=7)

    def test_extend_ttl_14_days(self, app_with_tenant_admin, mock_db_session):
        """Happy path: extend by 14 days."""
        sub = _make_sub()

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service") as mock_kafka,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=sub)
            mock_kafka.publish = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 14, "reason": "Integration testing"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["ttl_extension_count"] == 1
            assert data["ttl_total_extended_days"] == 14
            assert data["remaining_extensions"] == 1

    def test_extend_ttl_twice(self, app_with_tenant_admin, mock_db_session):
        """Two extensions succeed, count reaches 2."""
        sub = _make_sub()

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service") as mock_kafka,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=sub)
            mock_kafka.publish = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                # First extension
                resp1 = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 7, "reason": "First extension"},
                )
                assert resp1.status_code == 200
                assert resp1.json()["ttl_extension_count"] == 1

                # Second extension
                resp2 = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 14, "reason": "Second extension"},
                )
                assert resp2.status_code == 200
                data = resp2.json()
                assert data["ttl_extension_count"] == 2
                assert data["ttl_total_extended_days"] == 21
                assert data["remaining_extensions"] == 0

    def test_extend_ttl_max_reached(self, app_with_tenant_admin, mock_db_session):
        """Third extension is rejected (max 2)."""
        sub = _make_sub({"ttl_extension_count": 2, "ttl_total_extended_days": 21})

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service"),
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 7, "reason": "One more please"},
                )

            assert response.status_code == 409
            assert "Maximum extensions reached" in response.json()["detail"]

    def test_extend_ttl_total_days_exceeded(self, app_with_tenant_admin, mock_db_session):
        """Reject when total would exceed 60-day cap."""
        sub = _make_sub({"ttl_extension_count": 1, "ttl_total_extended_days": 50})

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service"),
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 14, "reason": "Too many days"},
                )

            assert response.status_code == 409
            assert "60-day maximum" in response.json()["detail"]

    def test_extend_ttl_not_owner(self, app_with_other_tenant, mock_db_session):
        """Different tenant user gets 403."""
        sub = _make_sub()  # tenant_id=acme, subscriber_id=tenant-admin-user-id

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service"),
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_other_tenant) as client:
                response = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 7, "reason": "Sneaky"},
                )

            assert response.status_code == 403

    def test_extend_ttl_admin_override(self, app_with_cpi_admin, mock_db_session):
        """cpi-admin can extend any subscription."""
        sub = _make_sub({"subscriber_id": "some-other-user-id"})

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service") as mock_kafka,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=sub)
            mock_kafka.publish = AsyncMock()

            with TestClient(app_with_cpi_admin) as client:
                response = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 7, "reason": "Admin extension"},
                )

            assert response.status_code == 200
            assert response.json()["ttl_extension_count"] == 1

    def test_extend_ttl_not_found(self, app_with_tenant_admin, mock_db_session):
        """Non-existent subscription returns 404."""
        fake_id = uuid4()

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service"),
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/subscriptions/{fake_id}/ttl",
                    json={"extend_days": 7, "reason": "Not here"},
                )

            assert response.status_code == 404

    def test_extend_ttl_inactive(self, app_with_tenant_admin, mock_db_session):
        """PENDING subscription returns 409."""
        sub = _make_sub({"status": SubscriptionStatus.PENDING})

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service"),
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 7, "reason": "Not active yet"},
                )

            assert response.status_code == 409
            assert "Only active subscriptions" in response.json()["detail"]

    def test_extend_ttl_no_expiry(self, app_with_tenant_admin, mock_db_session):
        """Subscription without expires_at returns 409."""
        sub = _make_sub({"expires_at": None})

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service"),
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 7, "reason": "No expiry"},
                )

            assert response.status_code == 409
            assert "no expiry date" in response.json()["detail"]

    def test_extend_ttl_invalid_days(self, app_with_tenant_admin, mock_db_session):
        """extend_days=30 is rejected by Pydantic Literal validation (422)."""
        sub = _make_sub()

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service"),
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 30, "reason": "Invalid days"},
                )

            assert response.status_code == 422
