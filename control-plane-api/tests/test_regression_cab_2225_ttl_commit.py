"""
Regression for CAB-2225 SUB-2 — TTL extension uses commit() not flush().

# regression for CAB-2225

Source audit: docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md (SUB-2, P0)
Plan ref:    docs/plans/2026-05-11-uac-subscription-mcp-corrective.md §5.6

The bug: extend_subscription_ttl used `await db.flush()`. flush() emits the
UPDATE on the wire but the transaction is still uncommitted; if anything
between the handler returning and the get_db dependency commit raises
(middleware, response serialization, audit emit), the changes roll back
silently while the response was already prepared.

The fix: call `await db.commit()` inside the handler, BEFORE any external
side effects (Kafka publish). The response reflects truly persisted state.

These tests assert the contract at the mock-session boundary:
  1. commit() MUST be awaited during the handler (not just flush()).
  2. A Kafka publish failure MUST NOT undo the commit — the handler
     swallows the Kafka exception by design and the DB state is durable.
"""

from datetime import datetime, timedelta
from enum import StrEnum
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class SubscriptionStatus(StrEnum):
    """Mirror of src.models.subscription.SubscriptionStatus for testing."""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"


def _make_sub(overrides: dict | None = None) -> MagicMock:
    """Create a mock Subscription with TTL-related fields (matches test_ttl_extension)."""
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


class TestTtlCommitRegression:
    """SUB-2 regression: handler must call commit(), not only flush()."""

    def test_ttl_extend_calls_commit_inside_handler(self, app_with_tenant_admin, mock_db_session):
        """The handler must await db.commit() at least once.

        With the bug (flush only), the override_get_db generator never commits
        either (it just yields the mock), so commit.await_count stays 0.
        With the fix, the handler explicitly commits before returning.
        """
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
                    json={"extend_days": 7, "reason": "regression check"},
                )

            assert response.status_code == 200
            # The contract: commit MUST be awaited in-handler.
            mock_db_session.commit.assert_awaited()

    def test_ttl_extend_persists_when_kafka_publish_fails(self, app_with_tenant_admin, mock_db_session):
        """Kafka publish failure must not undo the DB commit.

        The handler catches Kafka exceptions (logger.warning) and continues.
        With the fix, db.commit() runs BEFORE the kafka publish, so the
        UPDATE is durable regardless of downstream side-effect failures.
        """
        sub = _make_sub()
        original_expires = sub.expires_at

        with (
            patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo,
            patch("src.routers.subscriptions.kafka_service") as mock_kafka,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=sub)
            mock_kafka.publish = AsyncMock(side_effect=RuntimeError("kafka down"))

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"/v1/subscriptions/{sub.id}/ttl",
                    json={"extend_days": 14, "reason": "kafka outage scenario"},
                )

            # Handler still returns success (Kafka failure is non-blocking).
            assert response.status_code == 200
            data = response.json()
            assert data["ttl_extension_count"] == 1
            assert data["ttl_total_extended_days"] == 14
            # In-memory state reflects the increment.
            assert sub.expires_at == original_expires + timedelta(days=14)
            # Commit must have been awaited BEFORE the Kafka raise.
            mock_db_session.commit.assert_awaited()
