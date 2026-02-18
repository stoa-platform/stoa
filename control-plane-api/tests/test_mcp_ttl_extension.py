"""
Tests for MCP Subscription TTL Extension - CAB-86

Target: PATCH /v1/mcp/subscriptions/{subscription_id}/ttl endpoint
Coverage: ownership validation, extension limits, increment validation, Kafka event emission
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


def _make_subscription(
    sub_id=None,
    subscriber_id="user-001",
    status_value="active",
    expires_at=None,
    ttl_extensions=0,
    tenant_id="acme",
):
    """Create a mock MCPServerSubscription."""
    from src.models.mcp_subscription import MCPSubscriptionStatus

    sub = MagicMock()
    sub.id = sub_id or uuid4()
    sub.server_id = uuid4()
    sub.subscriber_id = subscriber_id
    sub.subscriber_email = f"{subscriber_id}@acme.com"
    sub.tenant_id = tenant_id
    sub.plan = "basic"
    sub.api_key_prefix = "stoa_mcp_"
    sub.status = MCPSubscriptionStatus(status_value)
    sub.status_reason = None
    sub.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    sub.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    sub.approved_at = datetime(2026, 1, 1, tzinfo=UTC)
    sub.expires_at = expires_at
    sub.ttl_extensions = ttl_extensions
    sub.last_used_at = None
    sub.usage_count = 0
    return sub


class TestTTLExtensionOwnership:
    """Test ownership validation."""

    def test_owner_can_extend(self, app_with_tenant_admin, mock_db_session):
        """Subscription owner can extend TTL."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",  # matches tenant-admin fixture user.id
            expires_at=datetime(2026, 3, 1, tzinfo=UTC),
            ttl_extensions=0,
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with patch("src.routers.mcp.kafka_service") as mock_kafka:
                mock_kafka.publish = AsyncMock()

                with TestClient(app_with_tenant_admin) as client:
                    response = client.patch(
                        f"/v1/mcp/subscriptions/{sub_id}/ttl",
                        json={"extend_days": 7, "reason": "Need more time for testing"},
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["extend_days"] == 7
        assert data["ttl_extensions"] == 1
        assert data["remaining_extensions"] == 1

    def test_non_owner_denied(self, app_with_tenant_admin, mock_db_session):
        """Non-owner cannot extend TTL."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="other-user",  # different from tenant-admin user.id
            expires_at=datetime(2026, 3, 1, tzinfo=UTC),
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/mcp/subscriptions/{sub_id}/ttl",
                    json={"extend_days": 7, "reason": "Testing"},
                )

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    def test_subscription_not_found(self, app_with_tenant_admin, mock_db_session):
        """Returns 404 if subscription doesn't exist."""
        sub_id = uuid4()

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/mcp/subscriptions/{sub_id}/ttl",
                    json={"extend_days": 7, "reason": "Testing"},
                )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestTTLExtensionLimits:
    """Test extension limit enforcement (max 2 extensions)."""

    def test_first_extension_allowed(self, app_with_tenant_admin, mock_db_session):
        """First extension is allowed."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",
            expires_at=datetime(2026, 3, 1, tzinfo=UTC),
            ttl_extensions=0,
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with patch("src.routers.mcp.kafka_service") as mock_kafka:
                mock_kafka.publish = AsyncMock()

                with TestClient(app_with_tenant_admin) as client:
                    response = client.patch(
                        f"/v1/mcp/subscriptions/{sub_id}/ttl",
                        json={"extend_days": 14, "reason": "Extended testing"},
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["ttl_extensions"] == 1

    def test_second_extension_allowed(self, app_with_tenant_admin, mock_db_session):
        """Second extension is allowed."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",
            expires_at=datetime(2026, 3, 8, tzinfo=UTC),
            ttl_extensions=1,
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with patch("src.routers.mcp.kafka_service") as mock_kafka:
                mock_kafka.publish = AsyncMock()

                with TestClient(app_with_tenant_admin) as client:
                    response = client.patch(
                        f"/v1/mcp/subscriptions/{sub_id}/ttl",
                        json={"extend_days": 7, "reason": "Final extension"},
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["ttl_extensions"] == 2
        assert data["remaining_extensions"] == 0

    def test_third_extension_denied(self, app_with_tenant_admin, mock_db_session):
        """Third extension is denied (limit reached)."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",
            expires_at=datetime(2026, 3, 15, tzinfo=UTC),
            ttl_extensions=2,
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/mcp/subscriptions/{sub_id}/ttl",
                    json={"extend_days": 7, "reason": "One more please"},
                )

        assert response.status_code == 400
        assert "Extension limit reached" in response.json()["detail"]


class TestTTLExtensionIncrements:
    """Test valid increment validation (7 or 14 days only)."""

    def test_7_days_valid(self, app_with_tenant_admin, mock_db_session):
        """7-day extension is valid."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",
            expires_at=datetime(2026, 3, 1, tzinfo=UTC),
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with patch("src.routers.mcp.kafka_service") as mock_kafka:
                mock_kafka.publish = AsyncMock()

                with TestClient(app_with_tenant_admin) as client:
                    response = client.patch(
                        f"/v1/mcp/subscriptions/{sub_id}/ttl",
                        json={"extend_days": 7, "reason": "Testing"},
                    )

        assert response.status_code == 200

    def test_14_days_valid(self, app_with_tenant_admin, mock_db_session):
        """14-day extension is valid."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",
            expires_at=datetime(2026, 3, 1, tzinfo=UTC),
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with patch("src.routers.mcp.kafka_service") as mock_kafka:
                mock_kafka.publish = AsyncMock()

                with TestClient(app_with_tenant_admin) as client:
                    response = client.patch(
                        f"/v1/mcp/subscriptions/{sub_id}/ttl",
                        json={"extend_days": 14, "reason": "Testing"},
                    )

        assert response.status_code == 200

    def test_1_day_invalid(self, app_with_tenant_admin, mock_db_session):
        """1-day extension is invalid."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",
            expires_at=datetime(2026, 3, 1, tzinfo=UTC),
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/mcp/subscriptions/{sub_id}/ttl",
                    json={"extend_days": 1, "reason": "Testing"},
                )

        # Pydantic validation fails before endpoint logic
        assert response.status_code == 422

    def test_30_days_invalid(self, app_with_tenant_admin, mock_db_session):
        """30-day extension is invalid."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",
            expires_at=datetime(2026, 3, 1, tzinfo=UTC),
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/mcp/subscriptions/{sub_id}/ttl",
                    json={"extend_days": 30, "reason": "Testing"},
                )

        # Pydantic validation fails (ge=7, le=14)
        assert response.status_code == 422


class TestTTLExtensionCalculation:
    """Test expires_at calculation logic."""

    def test_extends_from_current_expiry(self, app_with_tenant_admin, mock_db_session):
        """Extension adds to current expires_at."""
        sub_id = uuid4()
        original_expiry = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",
            expires_at=original_expiry,
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with patch("src.routers.mcp.kafka_service") as mock_kafka:
                mock_kafka.publish = AsyncMock()

                with TestClient(app_with_tenant_admin) as client:
                    response = client.patch(
                        f"/v1/mcp/subscriptions/{sub_id}/ttl",
                        json={"extend_days": 7, "reason": "Testing"},
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["previous_expires_at"] == original_expiry.isoformat().replace("+00:00", "Z")
        # New expiry should be original + 7 days
        expected_new = original_expiry + timedelta(days=7)
        assert data["new_expires_at"] == expected_new.isoformat().replace("+00:00", "Z")

    def test_extends_from_now_if_no_expiry(self, app_with_tenant_admin, mock_db_session):
        """If no expiry set, extends from now."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",
            expires_at=None,
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with patch("src.routers.mcp.kafka_service") as mock_kafka:
                mock_kafka.publish = AsyncMock()

                with TestClient(app_with_tenant_admin) as client:
                    response = client.patch(
                        f"/v1/mcp/subscriptions/{sub_id}/ttl",
                        json={"extend_days": 14, "reason": "Testing"},
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["previous_expires_at"] is None
        assert data["new_expires_at"] is not None


class TestKafkaEventEmission:
    """Test Kafka event emission for audit trail."""

    def test_kafka_event_published(self, app_with_tenant_admin, mock_db_session):
        """Kafka event is published on successful extension."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",
            tenant_id="acme",
            expires_at=datetime(2026, 3, 1, tzinfo=UTC),
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with patch("src.routers.mcp.kafka_service") as mock_kafka:
                mock_kafka.publish = AsyncMock()

                with TestClient(app_with_tenant_admin) as client:
                    response = client.patch(
                        f"/v1/mcp/subscriptions/{sub_id}/ttl",
                        json={"extend_days": 7, "reason": "Integration testing"},
                    )

        assert response.status_code == 200
        # Verify Kafka publish was called
        mock_kafka.publish.assert_called_once()
        call_args = mock_kafka.publish.call_args
        assert call_args.kwargs["event_type"] == "resource-ttl-extended"
        assert call_args.kwargs["tenant_id"] == "acme"
        assert call_args.kwargs["payload"]["resource_type"] == "mcp_subscription"
        assert call_args.kwargs["payload"]["extend_days"] == 7
        assert call_args.kwargs["payload"]["reason"] == "Integration testing"

    def test_kafka_failure_non_blocking(self, app_with_tenant_admin, mock_db_session):
        """Kafka emission failure doesn't fail the extension."""
        sub_id = uuid4()
        sub = _make_subscription(
            sub_id=sub_id,
            subscriber_id="tenant-admin-user-id",
            expires_at=datetime(2026, 3, 1, tzinfo=UTC),
        )

        with patch("src.routers.mcp.MCPSubscriptionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id = AsyncMock(return_value=sub)

            with patch("src.routers.mcp.kafka_service") as mock_kafka:
                # Kafka publish raises an exception
                mock_kafka.publish = AsyncMock(side_effect=Exception("Kafka down"))

                with TestClient(app_with_tenant_admin) as client:
                    response = client.patch(
                        f"/v1/mcp/subscriptions/{sub_id}/ttl",
                        json={"extend_days": 7, "reason": "Testing"},
                    )

        # Extension still succeeds despite Kafka failure
        assert response.status_code == 200
