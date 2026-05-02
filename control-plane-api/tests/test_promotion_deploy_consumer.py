"""Tests for the promotion deploy Kafka consumer."""

from unittest.mock import MagicMock

from src.consumers.promotion_deploy_consumer import PromotionDeployConsumer


def test_gateway_aware_promotion_event_does_not_trigger_legacy_auto_deploy():
    consumer = PromotionDeployConsumer()
    consumer._auto_deploy = MagicMock()
    consumer._loop = MagicMock()
    message = MagicMock()
    message.value = {
        "event_type": "promotion-approved",
        "tenant_id": "acme",
        "payload": {
            "promotion_id": "16d9e16d-d97d-4661-9eb2-b0c2dbda0821",
            "api_id": "payments",
            "target_environment": "staging",
            "approved_by": "admin",
            "gateway_deployments_created": True,
        },
    }

    consumer._handle_message(message)

    consumer._auto_deploy.assert_not_called()
