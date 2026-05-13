# CAB-2225 SUB-3 suspend/reactivate webhook regression tests.
# Guards lifecycle Kafka events for temporary subscription transitions.
#
# regression for CAB-2225
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.models.subscription import ProvisioningStatus, SubscriptionStatus


def _make_sub(*, status: SubscriptionStatus) -> MagicMock:
    sub = MagicMock()
    sub.id = uuid4()
    sub.application_id = "00000000-0000-4000-8000-000000000001"
    sub.application_name = "Audit App"
    sub.subscriber_id = "tenant-admin-user-id"
    sub.subscriber_email = "admin@acme.com"
    sub.api_id = "api-audit-1"
    sub.api_name = "Audit API"
    sub.api_version = "1.0"
    sub.tenant_id = "acme"
    sub.consumer_id = None
    sub.plan_id = str(uuid4())
    sub.plan_name = "Basic"
    sub.oauth_client_id = "kc-client-audit"
    sub.api_key_prefix = "stoa_sk_"
    sub.status = status
    sub.status_reason = None
    sub.created_at = datetime.utcnow()
    sub.updated_at = datetime.utcnow()
    sub.approved_at = None
    sub.expires_at = None
    sub.revoked_at = None
    sub.approved_by = None
    sub.revoked_by = None
    sub.rejected_by = None
    sub.rejected_at = None
    sub.provisioning_status = ProvisioningStatus.NONE
    sub.gateway_app_id = None
    sub.provisioning_error = None
    sub.provisioned_at = None
    return sub


def _patch_subscription_repo(sub: MagicMock):
    async def update_status(subscription, new_status, reason=None, actor_id=None):
        subscription.status = new_status
        subscription.status_reason = reason
        return subscription

    return (
        patch("src.routers.subscriptions.SubscriptionRepository.get_by_id", new=AsyncMock(return_value=sub)),
        patch(
            "src.routers.subscriptions.SubscriptionRepository.update_status", new=AsyncMock(side_effect=update_status)
        ),
    )


def _publish_kwargs(kafka_publish: AsyncMock) -> dict:
    kafka_publish.assert_awaited_once()
    return kafka_publish.await_args.kwargs


def test_suspend_emits_webhook(app_with_tenant_admin) -> None:
    sub = _make_sub(status=SubscriptionStatus.ACTIVE)
    status_reason = "SOC containment window"

    get_by_id, update_status = _patch_subscription_repo(sub)
    with (
        get_by_id,
        update_status,
        patch("src.routers.subscriptions.kafka_service.publish", new_callable=AsyncMock) as kafka_publish,
        TestClient(app_with_tenant_admin) as client,
    ):
        response = client.patch(f"/v1/subscriptions/{sub.id}/suspend", json={"status_reason": status_reason})

    assert response.status_code == 200
    kwargs = _publish_kwargs(kafka_publish)
    assert kwargs["event_type"] == "resource-suspended"
    assert kwargs["payload"]["status_reason"] == status_reason


def test_reactivate_emits_webhook(app_with_tenant_admin) -> None:
    sub = _make_sub(status=SubscriptionStatus.SUSPENDED)
    status_reason = "SOC cleared containment"

    get_by_id, update_status = _patch_subscription_repo(sub)
    with (
        get_by_id,
        update_status,
        patch("src.routers.subscriptions.kafka_service.publish", new_callable=AsyncMock) as kafka_publish,
        TestClient(app_with_tenant_admin) as client,
    ):
        response = client.patch(f"/v1/subscriptions/{sub.id}/reactivate", json={"status_reason": status_reason})

    assert response.status_code == 200
    kwargs = _publish_kwargs(kafka_publish)
    assert kwargs["event_type"] == "resource-reactivated"
    assert kwargs["payload"]["reactivation_reason"] == status_reason


def test_suspend_handler_succeeds_when_kafka_fails(app_with_tenant_admin) -> None:
    sub = _make_sub(status=SubscriptionStatus.ACTIVE)

    get_by_id, update_status = _patch_subscription_repo(sub)
    with (
        get_by_id,
        update_status,
        patch(
            "src.routers.subscriptions.kafka_service.publish",
            new_callable=AsyncMock,
            side_effect=RuntimeError("kafka down"),
        ) as kafka_publish,
        TestClient(app_with_tenant_admin) as client,
    ):
        response = client.patch(f"/v1/subscriptions/{sub.id}/suspend", json={"status_reason": "maintenance"})

    assert response.status_code == 200
    kafka_publish.assert_awaited_once()
    assert sub.status == SubscriptionStatus.SUSPENDED


def test_reactivate_handler_succeeds_when_kafka_fails(app_with_tenant_admin) -> None:
    sub = _make_sub(status=SubscriptionStatus.SUSPENDED)

    get_by_id, update_status = _patch_subscription_repo(sub)
    with (
        get_by_id,
        update_status,
        patch(
            "src.routers.subscriptions.kafka_service.publish",
            new_callable=AsyncMock,
            side_effect=RuntimeError("kafka down"),
        ) as kafka_publish,
        TestClient(app_with_tenant_admin) as client,
    ):
        response = client.patch(f"/v1/subscriptions/{sub.id}/reactivate", json={"status_reason": "cleared"})

    assert response.status_code == 200
    kafka_publish.assert_awaited_once()
    assert sub.status == SubscriptionStatus.ACTIVE
