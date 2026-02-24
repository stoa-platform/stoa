"""Billing metering Kafka consumer (CAB-1458).

Consumes `stoa.metering` events (ToolCallEvent) and records spend
against department budgets via BillingService.record_spend().
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from pydantic import BaseModel

from ..database import _get_session_factory
from ..services.billing_service import BillingService

logger = logging.getLogger(__name__)


class ToolCallMeteringEvent(BaseModel):
    """Pydantic schema for stoa.metering topic ToolCallEvent (billing fields)."""

    tenant_id: str
    department_id: str | None = None
    cost_units_microcents: int = 0
    token_count: int = 0
    tool_tier: str = "standard"


class BillingMeteringConsumer:
    """Thread-based Kafka consumer with asyncio bridge for billing metering."""

    TOPIC = "stoa.metering"
    GROUP = "billing-metering-consumer"

    def __init__(self) -> None:
        self._running = False
        self._consumer: Any = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Start the consumer thread."""
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._thread = threading.Thread(
            target=self._consume_thread,
            daemon=True,
            name="billing-metering-consumer",
        )
        self._thread.start()
        logger.info("Billing metering consumer started")

    async def stop(self) -> None:
        """Stop the consumer."""
        self._running = False
        if self._consumer:
            self._consumer.close()
        logger.info("Billing metering consumer stopped")

    def _consume_thread(self) -> None:
        """Kafka polling loop (runs in daemon thread)."""
        try:
            from kafka import KafkaConsumer

            from ..config import settings

            kafka_config: dict[str, Any] = {
                "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "group_id": self.GROUP,
                "auto_offset_reset": "latest",
                "enable_auto_commit": True,
                "value_deserializer": lambda m: __import__("json").loads(m.decode("utf-8")),
            }
            if settings.KAFKA_SECURITY_PROTOCOL != "PLAINTEXT":
                kafka_config["security_protocol"] = settings.KAFKA_SECURITY_PROTOCOL
            if settings.KAFKA_SASL_MECHANISM:
                kafka_config["sasl_mechanism"] = settings.KAFKA_SASL_MECHANISM
                kafka_config["sasl_plain_username"] = settings.KAFKA_SASL_USERNAME
                kafka_config["sasl_plain_password"] = settings.KAFKA_SASL_PASSWORD

            self._consumer = KafkaConsumer(self.TOPIC, **kafka_config)
            logger.info("Billing metering Kafka consumer connected")

            while self._running:
                records = self._consumer.poll(timeout_ms=1000)
                for _tp, messages in records.items():
                    for message in messages:
                        self._process_message_sync(message)

        except Exception:
            logger.warning("Billing metering consumer thread error", exc_info=True)

    def _process_message_sync(self, message: Any) -> None:
        """Parse and dispatch a single message to the async handler."""
        try:
            event = ToolCallMeteringEvent.model_validate(message.value)
            if not event.department_id:
                return  # Skip events without department attribution
            if event.cost_units_microcents <= 0:
                return  # Skip zero-cost events
            if self._loop:
                asyncio.run_coroutine_threadsafe(self._handle_event(event), self._loop)
        except Exception:
            logger.warning("Failed to process billing metering message", exc_info=True)

    async def _handle_event(self, event: ToolCallMeteringEvent) -> None:
        """Record spend via BillingService."""
        try:
            session_factory = _get_session_factory()
            async with session_factory() as session:
                service = BillingService(session)
                await service.record_spend(
                    tenant_id=event.tenant_id,
                    department_id=event.department_id,
                    amount_microcents=event.cost_units_microcents,
                )
                await session.commit()
        except Exception:
            logger.warning(
                "Failed to record billing spend for dept=%s tenant=%s",
                event.department_id,
                event.tenant_id,
                exc_info=True,
            )


# Singleton instance
billing_metering_consumer = BillingMeteringConsumer()
