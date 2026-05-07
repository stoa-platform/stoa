"""Audit trail Kafka consumer that persists audit envelopes to PostgreSQL."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from prometheus_client import Counter, Gauge, Histogram
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..core.pii.masker import MaskingContext, get_masker
from ..database import _get_session_factory
from ..models.audit_event import AuditEvent
from ..services.kafka_service import EVENT_VERSION, Topics

logger = logging.getLogger(__name__)

COMPONENT = "audit-trail-consumer"
TOPIC = Topics.AUDIT_LOG
GROUP_ID = "audit-trail-pg-consumer"
DEFAULT_DLQ_TOPIC = "stoa.audit.trail.dlq"
VALID_OUTCOMES = {"success", "failure", "denied", "error"}
PROCESSING_TIMEOUT_SECONDS = 30

MESSAGES_TOTAL = Counter(
    "stoa_audit_consumer_messages_total",
    "Audit trail Kafka messages processed by result.",
    ["result"],
)
PROCESSING_SECONDS = Histogram(
    "stoa_audit_consumer_processing_seconds",
    "Audit trail Kafka message processing latency.",
)
DB_ERRORS_TOTAL = Counter(
    "stoa_audit_consumer_db_errors_total",
    "Audit trail PostgreSQL persistence failures.",
)
DLQ_TOTAL = Counter(
    "stoa_audit_consumer_dlq_total",
    "Audit trail Kafka messages published to the DLQ.",
    ["error_type"],
)
DUPLICATE_TOTAL = Counter(
    "stoa_audit_consumer_duplicate_total",
    "Audit trail duplicate event ids skipped.",
)
LAST_SUCCESS_TIMESTAMP = Gauge(
    "stoa_audit_consumer_last_success_timestamp_seconds",
    "Unix timestamp of the latest successful audit trail sink operation.",
)


class AuditPayload(BaseModel):
    """Compatible payload fields published by KafkaService.emit_audit_event."""

    action: str
    resource_type: str
    resource_id: str | None = None
    details: dict[str, Any] | None = Field(default_factory=dict)
    method: str | None = None
    path: str | None = None
    resource_name: str | None = None
    outcome: str = "success"
    status_code: int | None = None
    actor_email: str | None = None
    actor_type: str | None = None
    correlation_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    diff: dict[str, Any] | None = None
    duration_ms: int | None = None

    @field_validator("action", "resource_type")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("field must be non-empty")
        return value

    @field_validator("outcome")
    @classmethod
    def _valid_outcome(cls, value: str) -> str:
        if value not in VALID_OUTCOMES:
            raise ValueError("outcome must be one of success, failure, denied, error")
        return value

    @field_validator("details")
    @classmethod
    def _details_must_be_object(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None and not isinstance(value, dict):
            raise ValueError("details must be an object")
        return value


class AuditTrailEnvelope(BaseModel):
    """Canonical audit event envelope from `stoa.audit.trail`."""

    id: str
    type: str
    source: str
    tenant_id: str
    timestamp: datetime
    version: str
    user_id: str | None = None
    payload: AuditPayload

    @field_validator("id")
    @classmethod
    def _id_must_be_uuid(cls, value: str) -> str:
        uuid.UUID(value)
        return value

    @field_validator("type")
    @classmethod
    def _type_must_be_audit(cls, value: str) -> str:
        if value != "audit":
            raise ValueError('type must equal "audit"')
        return value

    @field_validator("source")
    @classmethod
    def _source_must_be_non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("source must be non-empty")
        return value

    @field_validator("tenant_id")
    @classmethod
    def _tenant_must_be_known(cls, value: str) -> str:
        if not value or not value.strip() or value.strip().lower() == "unknown":
            raise ValueError("tenant_id must be non-empty and known")
        return value

    @field_validator("timestamp")
    @classmethod
    def _timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("version")
    @classmethod
    def _version_must_match(cls, value: str) -> str:
        if value != EVENT_VERSION:
            raise ValueError(f"version must equal {EVENT_VERSION}")
        return value


class AuditTrailConsumer:
    """Threaded Kafka consumer with manual commit after PG or DLQ success."""

    def __init__(self) -> None:
        self._consumer: KafkaConsumer | None = None
        self._producer: KafkaProducer | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._db_backoff_seconds = 1.0
        self.dlq_topic = os.getenv("AUDIT_TRAIL_DLQ_TOPIC", DEFAULT_DLQ_TOPIC)

    async def start(self) -> None:
        """Start consuming audit trail events in a daemon thread."""
        self._loop = asyncio.get_running_loop()
        self._running = True
        self._thread = threading.Thread(target=self._consume_thread, daemon=True, name=COMPONENT)
        self._thread.start()
        logger.info("Audit trail consumer started", extra={"component": COMPONENT, "topic": TOPIC})

    async def stop(self) -> None:
        """Stop the consumer and close Kafka clients."""
        self._running = False
        if self._consumer:
            self._consumer.close()
        if self._producer:
            self._producer.close()
        logger.info("Audit trail consumer stopped", extra={"component": COMPONENT})

    def _consume_thread(self) -> None:
        try:
            self._consumer = self._create_consumer()
            if self._consumer is None:
                return
            while self._running:
                for _tp, records in self._consumer.poll(timeout_ms=1000).items():
                    for message in records:
                        if not self._running:
                            break
                        processed = self._process_message_sync(message)
                        while self._running and not processed:
                            processed = self._process_message_sync(message)
                        if processed:
                            self._consumer.commit()
        except Exception:
            if self._running:
                logger.error("Audit trail consumer thread failed", exc_info=True, extra={"component": COMPONENT})
        finally:
            if self._consumer:
                self._consumer.close()

    def _create_consumer(self) -> KafkaConsumer | None:
        try:
            return KafkaConsumer(TOPIC, **self._kafka_config(group_id=GROUP_ID, enable_auto_commit=False))
        except KafkaError:
            logger.error("Failed to create audit trail consumer", exc_info=True, extra={"component": COMPONENT})
            return None

    def _create_producer(self) -> KafkaProducer:
        return KafkaProducer(
            **self._kafka_base_config(),
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        )

    def _kafka_config(self, *, group_id: str | None, enable_auto_commit: bool | None) -> dict[str, Any]:
        config = {
            **self._kafka_base_config(),
            "auto_offset_reset": "earliest",
            "value_deserializer": self._decode_value,
        }
        if group_id is not None:
            config["group_id"] = group_id
        if enable_auto_commit is not None:
            config["enable_auto_commit"] = enable_auto_commit
        return config

    def _kafka_base_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {
            "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
        }
        if settings.KAFKA_SECURITY_PROTOCOL != "PLAINTEXT":
            config["security_protocol"] = settings.KAFKA_SECURITY_PROTOCOL
        if settings.KAFKA_SASL_MECHANISM:
            config["sasl_mechanism"] = settings.KAFKA_SASL_MECHANISM
            config["sasl_plain_username"] = settings.KAFKA_SASL_USERNAME
            config["sasl_plain_password"] = settings.KAFKA_SASL_PASSWORD
        return config

    @staticmethod
    def _decode_value(message: bytes) -> Any:
        try:
            return json.loads(message.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return message.decode("utf-8", errors="replace")

    def _process_message_sync(self, message: Any) -> bool:
        if self._loop is None:
            logger.error("No event loop available for audit consumer", extra={"component": COMPONENT})
            return False
        future = asyncio.run_coroutine_threadsafe(self._handle_message(message), self._loop)
        return bool(future.result(timeout=PROCESSING_TIMEOUT_SECONDS))

    async def _handle_message(self, message: Any) -> bool:
        started = time.monotonic()
        try:
            envelope = AuditTrailEnvelope.model_validate(message.value)
            event = self._to_audit_event(envelope, message)
            result = await self._persist_event(event)
            self._record_success(result)
            self._log_message(message, envelope, result=result)
            return True
        except (ValidationError, ValueError) as exc:
            ok = await self._publish_dlq(message, "validation_error", str(exc))
            result = "invalid" if ok else "dlq_error"
            MESSAGES_TOTAL.labels(result=result).inc()
            if not ok:
                await self._sleep_before_retry()
            self._log_message(message, None, result=result, error_type="validation_error")
            return ok
        except Exception as exc:
            DB_ERRORS_TOTAL.inc()
            MESSAGES_TOTAL.labels(result="db_error").inc()
            await self._sleep_before_retry()
            self._log_message(message, None, result="db_error", error_type=type(exc).__name__)
            return False
        finally:
            PROCESSING_SECONDS.observe(time.monotonic() - started)

    def _to_audit_event(self, envelope: AuditTrailEnvelope, message: Any) -> AuditEvent:
        payload = envelope.payload
        method = payload.method or "KAFKA"
        path = payload.path or f"/events/kafka/{TOPIC}/{payload.resource_type}/{payload.action}"
        if len(method) > 10:
            raise ValueError("method must fit audit_events.method")
        if len(path) > 1024:
            raise ValueError("path must fit audit_events.path")

        raw_details = payload.details or {}
        correlation_id = payload.correlation_id or raw_details.get("correlation_id")
        details = get_masker().mask_dict(
            raw_details,
            context=MaskingContext(tenant_id=envelope.tenant_id, user_id=envelope.user_id, source=COMPONENT),
        )
        details["_kafka"] = {
            "topic": getattr(message, "topic", TOPIC),
            "partition": getattr(message, "partition", None),
            "offset": getattr(message, "offset", None),
            "producer_event_id": envelope.id,
            "producer_source": envelope.source,
            "producer_version": envelope.version,
        }

        return AuditEvent(
            id=envelope.id,
            tenant_id=envelope.tenant_id,
            actor_id=envelope.user_id,
            actor_email=payload.actor_email,
            actor_type=payload.actor_type or ("user" if envelope.user_id else "system"),
            action=payload.action,
            method=method,
            path=path,
            resource_type=payload.resource_type,
            resource_id=payload.resource_id,
            resource_name=payload.resource_name,
            outcome=payload.outcome,
            status_code=payload.status_code,
            client_ip=payload.client_ip,
            user_agent=payload.user_agent,
            correlation_id=correlation_id,
            details=details,
            diff=payload.diff,
            duration_ms=payload.duration_ms,
            created_at=envelope.timestamp,
        )

    async def _persist_event(self, event: AuditEvent) -> str:
        factory = _get_session_factory()
        async with factory() as session:
            existing = await session.get(AuditEvent, event.id)
            if existing is not None:
                await session.rollback()
                return "duplicate"
            try:
                session.add(event)
                await session.commit()
                return "inserted"
            except IntegrityError:
                await session.rollback()
                return "duplicate"
            except Exception:
                await session.rollback()
                raise

    async def _publish_dlq(self, message: Any, error_type: str, error_message: str) -> bool:
        dlq_message = {
            "source_topic": getattr(message, "topic", TOPIC),
            "source_partition": getattr(message, "partition", None),
            "source_offset": getattr(message, "offset", None),
            "error_type": error_type,
            "error_message": error_message,
            "received_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "raw_event": message.value,
        }
        try:
            if self._producer is None:
                self._producer = self._create_producer()
            self._producer.send(self.dlq_topic, value=dlq_message).get(timeout=10)
            DLQ_TOTAL.labels(error_type=error_type).inc()
            return True
        except Exception:
            logger.error("Failed to publish audit event to DLQ", exc_info=True, extra={"component": COMPONENT})
            return False

    async def _sleep_before_retry(self) -> None:
        delay = self._db_backoff_seconds
        self._db_backoff_seconds = min(self._db_backoff_seconds * 2, 60)
        await asyncio.sleep(delay)

    def _record_success(self, result: str) -> None:
        self._db_backoff_seconds = 1.0
        MESSAGES_TOTAL.labels(result=result).inc()
        if result == "duplicate":
            DUPLICATE_TOTAL.inc()
        LAST_SUCCESS_TIMESTAMP.set(time.time())

    def _log_message(
        self,
        message: Any,
        envelope: AuditTrailEnvelope | None,
        *,
        result: str,
        error_type: str | None = None,
    ) -> None:
        logger.info(
            "Audit trail message processed",
            extra={
                "component": COMPONENT,
                "topic": getattr(message, "topic", TOPIC),
                "partition": getattr(message, "partition", None),
                "offset": getattr(message, "offset", None),
                "event_id": envelope.id if envelope else None,
                "tenant_id": envelope.tenant_id if envelope else None,
                "action": envelope.payload.action if envelope else None,
                "resource_type": envelope.payload.resource_type if envelope else None,
                "result": result,
                "error_type": error_type,
            },
        )


audit_trail_consumer = AuditTrailConsumer()
