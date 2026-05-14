"""Tests for audit trail Kafka -> PostgreSQL consumer."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.audit_event import AuditEvent
from src.workers.audit_trail_consumer import (
    DEFAULT_DLQ_TOPIC,
    GROUP_ID,
    TOPIC,
    AuditTrailConsumer,
    AuditTrailEnvelope,
)

EVENT_ID = "550e8400-e29b-41d4-a716-446655440000"


def _event(**overrides):
    data = {
        "id": EVENT_ID,
        "type": "audit",
        "source": "control-plane-api",
        "tenant_id": "acme",
        "timestamp": datetime(2026, 5, 8, 12, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "version": "1.0",
        "user_id": "user-1",
        "payload": {
            "action": "api.created",
            "resource_type": "api",
            "resource_id": "api-1",
            "details": {"correlation_id": "550e8400-e29b-41d4-a716-446655440001"},
        },
    }
    data.update(overrides)
    return data


def _message(value):
    return SimpleNamespace(value=value, topic=TOPIC, partition=2, offset=42)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


def _session_factory(session):
    return MagicMock(return_value=_SessionContext(session))


def test_current_envelope_maps_to_audit_event_with_kafka_metadata():
    consumer = AuditTrailConsumer()
    envelope = AuditTrailEnvelope.model_validate(_event())

    with patch("src.workers.audit_trail_consumer.get_masker") as get_masker:
        get_masker.return_value.mask_dict.return_value = {"correlation_id": "cid"}
        event = consumer._to_audit_event(envelope, _message(_event()))

    assert event.id == EVENT_ID
    assert event.tenant_id == "acme"
    assert event.actor_id == "user-1"
    assert event.actor_type == "user"
    assert event.method == "KAFKA"
    assert event.path == "/events/kafka/stoa.audit.trail/api/api.created"
    assert event.correlation_id == "550e8400-e29b-41d4-a716-446655440001"
    assert event.created_at == datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    assert event.details["_kafka"] == {
        "topic": TOPIC,
        "partition": 2,
        "offset": 42,
        "producer_event_id": EVENT_ID,
        "producer_source": "control-plane-api",
        "producer_version": "1.0",
    }


@pytest.mark.asyncio
async def test_persist_event_inserts_once_and_commits():
    consumer = AuditTrailConsumer()
    event = AuditEvent(id=EVENT_ID, tenant_id="acme", action="create", method="KAFKA", path="/p", resource_type="api")
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    with (
        patch("src.workers.audit_trail_consumer._get_session_factory", return_value=_session_factory(session)),
        patch(
            "src.services.audit_service.AuditService.record_event", new=AsyncMock(return_value=event)
        ) as record_event,
    ):
        assert await consumer._persist_event(event) == "inserted"

    record_event.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_event_id_is_successful_noop():
    consumer = AuditTrailConsumer()
    event = AuditEvent(id=EVENT_ID, tenant_id="acme", action="create", method="KAFKA", path="/p", resource_type="api")
    session = MagicMock()
    session.get = AsyncMock(return_value=event)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    with patch("src.workers.audit_trail_consumer._get_session_factory", return_value=_session_factory(session)):
        assert await consumer._persist_event(event) == "duplicate"

    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_tenant_goes_to_dlq_and_allows_offset_commit():
    consumer = AuditTrailConsumer()
    message = _message(_event(tenant_id="unknown"))

    with patch.object(consumer, "_publish_dlq", new=AsyncMock(return_value=True)) as dlq:
        assert await consumer._handle_message(message) is True

    dlq.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_outcome_goes_to_dlq_and_dlq_failure_blocks_commit():
    consumer = AuditTrailConsumer()
    event = _event()
    event["payload"]["outcome"] = "maybe"
    message = _message(event)

    with (
        patch.object(consumer, "_publish_dlq", new=AsyncMock(return_value=False)) as dlq,
        patch.object(consumer, "_sleep_before_retry", new=AsyncMock()) as backoff,
    ):
        assert await consumer._handle_message(message) is False

    dlq.assert_awaited_once()
    backoff.assert_awaited_once()


@pytest.mark.asyncio
async def test_db_error_rolls_back_and_does_not_allow_offset_commit():
    consumer = AuditTrailConsumer()
    message = _message(_event())

    with (
        patch.object(consumer, "_persist_event", new=AsyncMock(side_effect=RuntimeError("db down"))),
        patch.object(consumer, "_sleep_before_retry", new=AsyncMock()) as backoff,
    ):
        assert await consumer._handle_message(message) is False

    backoff.assert_awaited_once()


def test_consumer_retries_and_commits_offsets_only_after_successful_processing():
    consumer = AuditTrailConsumer()
    consumer._running = True
    kafka = MagicMock()
    kafka.poll.return_value = {object(): [_message(_event())]}
    outcomes = [False, True]

    def process(_message):
        result = outcomes.pop(0)
        if result:
            consumer._running = False
        return result

    with (
        patch.object(consumer, "_create_consumer", return_value=kafka),
        patch.object(consumer, "_process_message_sync", side_effect=process) as process_message,
    ):
        consumer._consume_thread()

    assert process_message.call_count == 2
    kafka.commit.assert_called_once()


def test_consumer_does_not_commit_after_failed_processing():
    consumer = AuditTrailConsumer()
    consumer._running = True
    kafka = MagicMock()
    kafka.poll.return_value = {object(): [_message(_event())]}

    def process(_message):
        consumer._running = False
        return False

    with (
        patch.object(consumer, "_create_consumer", return_value=kafka),
        patch.object(consumer, "_process_message_sync", side_effect=process),
    ):
        consumer._consume_thread()

    kafka.commit.assert_not_called()


def test_create_consumer_uses_contract_topic_group_and_manual_commit():
    consumer = AuditTrailConsumer()
    mock_kafka = MagicMock()

    with (
        patch("src.workers.audit_trail_consumer.KafkaConsumer", return_value=mock_kafka) as kafka_consumer,
        patch("src.workers.audit_trail_consumer.settings") as mock_settings,
    ):
        mock_settings.KAFKA_BOOTSTRAP_SERVERS = "broker1:9092,broker2:9092"
        mock_settings.KAFKA_SECURITY_PROTOCOL = "PLAINTEXT"
        mock_settings.KAFKA_SASL_MECHANISM = ""
        assert consumer._create_consumer() is mock_kafka

    kafka_consumer.assert_called_once()
    args, kwargs = kafka_consumer.call_args
    assert args == (TOPIC,)
    assert kwargs["group_id"] == GROUP_ID
    assert kwargs["auto_offset_reset"] == "earliest"
    assert kwargs["enable_auto_commit"] is False
    assert kwargs["bootstrap_servers"] == ["broker1:9092", "broker2:9092"]


def test_invalid_json_is_decoded_as_dlq_eligible_string():
    assert AuditTrailConsumer._decode_value(b"not-json") == "not-json"


def test_default_dlq_topic():
    assert AuditTrailConsumer().dlq_topic == DEFAULT_DLQ_TOPIC
