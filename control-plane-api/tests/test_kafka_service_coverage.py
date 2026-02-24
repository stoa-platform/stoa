"""Tests for KafkaService — coverage gap filler.

Covers: connect (retry logic), disconnect, _create_event, publish,
        convenience emitters, create_consumer.

Existing tests only cover the Topics class and basic publish.
This fills the 67% → ~90% gap.
"""

from unittest.mock import MagicMock, patch

import pytest
from kafka.errors import KafkaError


class TestKafkaServiceConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with (
            patch("src.services.kafka_service.settings") as mock_settings,
            patch("src.services.kafka_service.KafkaProducer") as MockProducer,
        ):
            mock_settings.KAFKA_ENABLED = True
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "broker:9092"
            MockProducer.return_value = MagicMock()

            await svc.connect()

        assert svc._producer is not None

    @pytest.mark.asyncio
    async def test_connect_disabled(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch("src.services.kafka_service.settings") as mock_settings:
            mock_settings.KAFKA_ENABLED = False

            await svc.connect()

        assert svc._producer is None

    @pytest.mark.asyncio
    async def test_connect_retry_then_success(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()
        producer_mock = MagicMock()

        with (
            patch("src.services.kafka_service.settings") as mock_settings,
            patch("src.services.kafka_service.KafkaProducer", side_effect=[KafkaError("fail"), producer_mock]) as MockProducer,
            patch("time.sleep"),
        ):
            mock_settings.KAFKA_ENABLED = True
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "broker:9092"

            await svc.connect()

        assert svc._producer is producer_mock
        assert MockProducer.call_count == 2

    @pytest.mark.asyncio
    async def test_connect_all_retries_fail(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with (
            patch("src.services.kafka_service.settings") as mock_settings,
            patch("src.services.kafka_service.KafkaProducer", side_effect=KafkaError("fail")),
            patch("time.sleep"),
        ):
            mock_settings.KAFKA_ENABLED = True
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "broker:9092"

            with pytest.raises(KafkaError):
                await svc.connect()


class TestKafkaServiceDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_closes_producer(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()
        svc._producer = MagicMock()
        svc._consumers = {"c1": MagicMock(), "c2": MagicMock()}

        await svc.disconnect()

        svc._producer is None  # noqa: B015
        assert len(svc._consumers) == 0

    @pytest.mark.asyncio
    async def test_disconnect_without_producer(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()
        svc._producer = None
        await svc.disconnect()  # Should not raise


class TestCreateEvent:
    def test_envelope_structure(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()
        event = svc._create_event("api-created", "acme", {"api_id": "a1"}, user_id="u1")

        assert event["type"] == "api-created"
        assert event["tenant_id"] == "acme"
        assert event["source"] == "control-plane-api"
        assert event["version"] == "1.0"
        assert event["user_id"] == "u1"
        assert event["payload"]["api_id"] == "a1"
        assert "id" in event
        assert "timestamp" in event


class TestPublish:
    @pytest.mark.asyncio
    async def test_publish_success(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()
        future = MagicMock()
        future.get.return_value = None
        producer = MagicMock()
        producer.send.return_value = future
        svc._producer = producer

        with patch("src.services.kafka_service.settings") as mock_settings:
            mock_settings.KAFKA_ENABLED = True

            event_id = await svc.publish("topic", "event-type", "acme", {"data": 1}, user_id="u1")

        assert event_id is not None
        producer.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_disabled(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch("src.services.kafka_service.settings") as mock_settings:
            mock_settings.KAFKA_ENABLED = False

            event_id = await svc.publish("topic", "event-type", "acme", {})

        assert event_id is not None  # Returns a UUID even when disabled

    @pytest.mark.asyncio
    async def test_publish_no_producer_raises(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()
        svc._producer = None

        with patch("src.services.kafka_service.settings") as mock_settings:
            mock_settings.KAFKA_ENABLED = True

            with pytest.raises(RuntimeError, match="not initialized"):
                await svc.publish("topic", "event-type", "acme", {})

    @pytest.mark.asyncio
    async def test_publish_kafka_error(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()
        future = MagicMock()
        future.get.side_effect = KafkaError("send failed")
        producer = MagicMock()
        producer.send.return_value = future
        svc._producer = producer

        with patch("src.services.kafka_service.settings") as mock_settings:
            mock_settings.KAFKA_ENABLED = True

            with pytest.raises(KafkaError):
                await svc.publish("topic", "event-type", "acme", {})

    @pytest.mark.asyncio
    async def test_publish_uses_custom_key(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()
        future = MagicMock()
        future.get.return_value = None
        producer = MagicMock()
        producer.send.return_value = future
        svc._producer = producer

        with patch("src.services.kafka_service.settings") as mock_settings:
            mock_settings.KAFKA_ENABLED = True

            await svc.publish("topic", "event-type", "acme", {}, key="custom-key")

        call_kwargs = producer.send.call_args
        assert call_kwargs[1]["key"] == "custom-key"


class TestConvenienceEmitters:
    """Verify convenience methods delegate to publish correctly."""

    @pytest.mark.asyncio
    async def test_emit_api_created(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-1") as mock_pub:
            result = await svc.emit_api_created("acme", {"name": "api"}, "u1")

        assert result == "evt-1"
        mock_pub.assert_called_once()
        assert mock_pub.call_args[0][1] == "api-created"

    @pytest.mark.asyncio
    async def test_emit_api_updated(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-2") as mock_pub:
            await svc.emit_api_updated("acme", {}, "u1")
        assert mock_pub.call_args[0][1] == "api-updated"

    @pytest.mark.asyncio
    async def test_emit_api_deleted(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-3") as mock_pub:
            await svc.emit_api_deleted("acme", "api-1", "u1")
        assert mock_pub.call_args[0][1] == "api-deleted"

    @pytest.mark.asyncio
    async def test_emit_deploy_request(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-4") as mock_pub:
            await svc.emit_deploy_request("acme", "api-1", "prod", "1.0", "u1")
        assert mock_pub.call_args[0][1] == "deploy-request"

    @pytest.mark.asyncio
    async def test_emit_audit_event(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-5") as mock_pub:
            await svc.emit_audit_event("acme", "create", "api", "api-1", "u1", {"extra": True})
        assert mock_pub.call_args[0][1] == "audit"

    @pytest.mark.asyncio
    async def test_emit_security_alert(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-6") as mock_pub:
            await svc.emit_security_alert("acme", "brute-force", "high", {"ip": "1.2.3.4"})
        assert mock_pub.call_args[0][1] == "brute-force"

    @pytest.mark.asyncio
    async def test_emit_subscription_event(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-7") as mock_pub:
            await svc.emit_subscription_event("acme", {"sub_id": "s1"}, "u1")
        assert mock_pub.call_args[0][1] == "subscription-changed"

    @pytest.mark.asyncio
    async def test_emit_policy_created(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-8") as mock_pub:
            await svc.emit_policy_created("acme", {"id": "p1"}, "u1")
        assert mock_pub.call_args[0][1] == "policy-created"

    @pytest.mark.asyncio
    async def test_emit_policy_updated(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-9") as mock_pub:
            await svc.emit_policy_updated("acme", {"id": "p1"}, "u1")
        assert mock_pub.call_args[0][1] == "policy-updated"

    @pytest.mark.asyncio
    async def test_emit_policy_deleted(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-10") as mock_pub:
            await svc.emit_policy_deleted("acme", "p1", "u1")
        assert mock_pub.call_args[0][1] == "policy-deleted"

    @pytest.mark.asyncio
    async def test_emit_policy_binding_created(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-11") as mock_pub:
            await svc.emit_policy_binding_created("acme", {"binding": "b1"}, "u1")
        assert mock_pub.call_args[0][1] == "policy-binding-created"

    @pytest.mark.asyncio
    async def test_emit_policy_binding_deleted(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with patch.object(svc, "publish", return_value="evt-12") as mock_pub:
            await svc.emit_policy_binding_deleted("acme", {"binding": "b1"}, "u1")
        assert mock_pub.call_args[0][1] == "policy-binding-deleted"


class TestCreateConsumer:
    def test_creates_consumer(self):
        from src.services.kafka_service import KafkaService

        svc = KafkaService()

        with (
            patch("src.services.kafka_service.settings") as mock_settings,
            patch("src.services.kafka_service.KafkaConsumer") as MockConsumer,
        ):
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "broker:9092"
            consumer_instance = MagicMock()
            MockConsumer.return_value = consumer_instance

            result = svc.create_consumer(["topic1", "topic2"], "my-group")

        assert result is consumer_instance
        assert len(svc._consumers) == 1
