"""Kafka consumer for auto-deploy on promotion (CAB-1888).

Listens to deploy-requests topic for promotion-approved events.
When a promotion is approved and the target environment has auto-deploy
assignments, triggers deployment to those gateways.

Topic:   stoa.deploy.requests
Group:   promotion-deploy-consumer
Events:  promotion-approved
"""

import asyncio
import json
import logging
import threading

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from ..config import settings
from ..database import _get_session_factory
from ..services.deployment_orchestration_service import DeploymentOrchestrationService
from ..services.kafka_service import Topics

logger = logging.getLogger(__name__)

GROUP_ID = "promotion-deploy-consumer"


class PromotionDeployConsumer:
    """Consumes promotion-approved events and triggers auto-deploy.

    Uses kafka-python in a background thread (same pattern as DeploymentConsumer).
    """

    def __init__(self) -> None:
        self._consumer: KafkaConsumer | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._running = True
        self._thread = threading.Thread(target=self._consume_thread, daemon=True)
        self._thread.start()
        logger.info("PromotionDeployConsumer started, consuming from %s", Topics.DEPLOY_REQUESTS)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            self._consumer.close()
        logger.info("PromotionDeployConsumer stopped")

    def _consume_thread(self) -> None:
        """Background thread running the Kafka consumer."""
        try:
            kafka_config = {
                "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
                "group_id": GROUP_ID,
                "auto_offset_reset": "latest",
                "enable_auto_commit": True,
                "value_deserializer": lambda m: json.loads(m.decode("utf-8")),
            }
            if hasattr(settings, "KAFKA_SASL_USERNAME") and settings.KAFKA_SASL_USERNAME:
                kafka_config.update({
                    "security_protocol": "SASL_PLAINTEXT",
                    "sasl_mechanism": "SCRAM-SHA-256",
                    "sasl_plain_username": settings.KAFKA_SASL_USERNAME,
                    "sasl_plain_password": settings.KAFKA_SASL_PASSWORD,
                })

            self._consumer = KafkaConsumer(Topics.DEPLOY_REQUESTS, **kafka_config)
            logger.info("PromotionDeployConsumer Kafka consumer connected")

            while self._running:
                try:
                    messages = self._consumer.poll(timeout_ms=1000)
                    for _tp, records in messages.items():
                        for message in records:
                            if not self._running:
                                break
                            self._handle_message(message)
                except Exception as e:
                    if self._running:
                        logger.error("Error polling promotion events: %s", e, exc_info=True)

        except KafkaError as e:
            logger.error("Failed to create Kafka consumer for promotion-deploy: %s", e)
        finally:
            if self._consumer:
                self._consumer.close()

    def _handle_message(self, message) -> None:
        """Handle a deploy-request message — dispatch auto-deploy if promotion-approved."""
        try:
            data = message.value
            event_type = data.get("event_type", "")
            if event_type != "promotion-approved":
                return  # Not our event

            payload = data.get("payload", {})
            api_id = payload.get("api_id")
            target_env = payload.get("target_environment")
            approved_by = payload.get("approved_by", "system")
            promotion_id = payload.get("promotion_id")
            tenant_id = data.get("tenant_id", "")

            if not api_id or not target_env:
                logger.warning("promotion-approved event missing api_id or target_environment: %s", data)
                return

            logger.info(
                "Received promotion-approved: api=%s env=%s approved_by=%s",
                api_id, target_env, approved_by,
            )

            if self._loop:
                future = asyncio.run_coroutine_threadsafe(
                    self._auto_deploy(api_id, tenant_id, target_env, approved_by, promotion_id),
                    self._loop,
                )
                future.add_done_callback(self._deploy_callback)

        except Exception as e:
            logger.error("Failed to handle promotion-approved event: %s", e, exc_info=True)

    async def _auto_deploy(
        self, api_id: str, tenant_id: str, target_env: str, approved_by: str,
        promotion_id: str | None = None,
    ) -> None:
        """Execute auto-deploy in an async context with its own DB session."""
        from uuid import UUID as _UUID

        promo_uuid = _UUID(promotion_id) if promotion_id else None
        async with _get_session_factory()() as session:
            svc = DeploymentOrchestrationService(session)
            deployments = await svc.auto_deploy_on_promotion(
                api_id=api_id,
                tenant_id=tenant_id,
                target_environment=target_env,
                approved_by=approved_by,
                promotion_id=promo_uuid,
            )
            if deployments:
                await session.commit()
                logger.info(
                    "Auto-deployed api=%s to %d gateways in %s",
                    api_id, len(deployments), target_env,
                )

    @staticmethod
    def _deploy_callback(future) -> None:
        """Log errors from async auto-deploy."""
        try:
            future.result()
        except Exception as e:
            logger.error("Auto-deploy failed: %s", e, exc_info=True)


promotion_deploy_consumer = PromotionDeployConsumer()
