"""Regression tests for the legacy promotion deploy consumer."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

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


@pytest.mark.asyncio
async def test_repeated_promotion_approved_event_is_ignored_without_auto_deploy(monkeypatch) -> None:
    import src.consumers.promotion_deploy_consumer as consumer_module

    def fail_if_legacy_orchestrator_is_loaded(*_args, **_kwargs):
        raise AssertionError("legacy deployment orchestrator must not be used")

    monkeypatch.setattr(
        consumer_module,
        "DeploymentOrchestrationService",
        fail_if_legacy_orchestrator_is_loaded,
        raising=False,
    )

    consumer = PromotionDeployConsumer()
    promotion_id = str(uuid.uuid4())

    await consumer._auto_deploy("payments-api", "acme", "staging", "admin", promotion_id)
    await consumer._auto_deploy("payments-api", "acme", "staging", "admin", promotion_id)
