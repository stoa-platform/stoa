"""Tests for Kafka service — event creation, publish, convenience methods."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.kafka_service import KafkaService, Topics


@pytest.fixture
def kafka_svc():
    return KafkaService()


class TestCreateEvent:
    def test_event_structure(self, kafka_svc):
        event = kafka_svc._create_event(
            event_type="api-created",
            tenant_id="acme",
            payload={"name": "test-api"},
            user_id="user-1",
        )
        assert event["type"] == "api-created"
        assert event["tenant_id"] == "acme"
        assert event["user_id"] == "user-1"
        assert event["payload"] == {"name": "test-api"}
        assert "id" in event
        assert "timestamp" in event

    def test_event_has_uuid(self, kafka_svc):
        e1 = kafka_svc._create_event("t", "acme", {})
        e2 = kafka_svc._create_event("t", "acme", {})
        assert e1["id"] != e2["id"]

    def test_event_timestamp_format(self, kafka_svc):
        event = kafka_svc._create_event("t", "acme", {})
        assert event["timestamp"].endswith("Z")


class TestPublish:
    @patch("src.services.kafka_service.settings")
    async def test_publish_disabled_returns_uuid(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        event_id = await kafka_svc.publish("topic", "type", "acme", {})
        assert isinstance(event_id, str)
        assert len(event_id) == 36  # UUID format

    @patch("src.services.kafka_service.settings")
    async def test_publish_no_producer_raises(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = True
        kafka_svc._producer = None
        with pytest.raises(RuntimeError, match="not initialized"):
            await kafka_svc.publish("topic", "type", "acme", {})

    @patch("src.services.kafka_service.settings")
    async def test_publish_happy_path(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = True
        mock_producer = MagicMock()
        mock_future = MagicMock()
        mock_future.get.return_value = None
        mock_producer.send.return_value = mock_future
        kafka_svc._producer = mock_producer

        event_id = await kafka_svc.publish(
            topic="api-events",
            event_type="api-created",
            tenant_id="acme",
            payload={"name": "test"},
            user_id="user-1",
        )

        assert isinstance(event_id, str)
        mock_producer.send.assert_called_once()
        call_kwargs = mock_producer.send.call_args
        assert call_kwargs[1]["key"] == "acme"  # default partition key


class TestConvenienceMethods:
    @patch("src.services.kafka_service.settings")
    async def test_emit_api_created(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        event_id = await kafka_svc.emit_api_created("acme", {"name": "test"}, "user-1")
        assert isinstance(event_id, str)

    @patch("src.services.kafka_service.settings")
    async def test_emit_api_deleted(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        event_id = await kafka_svc.emit_api_deleted("acme", "api-123", "user-1")
        assert isinstance(event_id, str)

    @patch("src.services.kafka_service.settings")
    async def test_emit_audit_event(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        event_id = await kafka_svc.emit_audit_event(
            tenant_id="acme",
            action="create",
            resource_type="api",
            resource_id="api-1",
            user_id="user-1",
        )
        assert isinstance(event_id, str)


class TestTopics:
    def test_api_events_topic(self):
        assert Topics.API_EVENTS == "api-events"

    def test_audit_log_topic(self):
        assert Topics.AUDIT_LOG == "audit-log"
