"""Chat token metering Kafka consumer (CAB-288).

Consumes `stoa.chat.tokens_used` events and persists aggregated
token usage via ChatTokenUsageRepository.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from pydantic import BaseModel

from ..database import _get_session_factory
from ..repositories.chat_token_usage_repository import ChatTokenUsageRepository

logger = logging.getLogger(__name__)


class ChatTokensEvent(BaseModel):
    """Schema for stoa.chat.tokens_used Kafka event."""

    tenant_id: str
    user_id: str
    conversation_id: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ChatMeteringConsumer:
    """Thread-based Kafka consumer with asyncio bridge for chat metering."""

    TOPIC = "stoa.chat.tokens_used"
    GROUP = "chat-metering-consumer"

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
            name="chat-metering-consumer",
        )
        self._thread.start()
        logger.info("Chat metering consumer started")

    async def stop(self) -> None:
        """Stop the consumer."""
        self._running = False
        if self._consumer:
            self._consumer.close()
        logger.info("Chat metering consumer stopped")

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
            logger.info("Chat metering Kafka consumer connected")

            while self._running:
                records = self._consumer.poll(timeout_ms=1000)
                for _tp, messages in records.items():
                    for message in messages:
                        self._process_message_sync(message)

        except Exception:
            logger.warning("Chat metering consumer thread error", exc_info=True)

    def _process_message_sync(self, message: Any) -> None:
        """Parse and dispatch a single message to the async handler."""
        try:
            event = ChatTokensEvent.model_validate(message.value)
            if self._loop:
                asyncio.run_coroutine_threadsafe(self._handle_event(event), self._loop)
        except Exception:
            logger.warning("Failed to process chat metering message", exc_info=True)

    async def _handle_event(self, event: ChatTokensEvent) -> None:
        """Persist token usage via repository."""
        try:
            session_factory = _get_session_factory()
            async with session_factory() as session:
                repo = ChatTokenUsageRepository(session)
                await repo.increment(
                    tenant_id=event.tenant_id,
                    user_id=event.user_id,
                    model=event.model,
                    input_tokens=event.input_tokens,
                    output_tokens=event.output_tokens,
                )
                await session.commit()
        except Exception:
            logger.warning("Failed to persist chat token usage", exc_info=True)


# Singleton instance
chat_metering_consumer = ChatMeteringConsumer()
