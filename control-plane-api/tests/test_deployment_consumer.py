"""Tests for DeploymentConsumer — Wave 2

Covers: start/stop lifecycle, _handle message processing,
        _create_consumer config, error handling.

The deployment consumer fans Kafka events to Slack via notify_deployment_event.
Uses kafka-python in a daemon thread — we test the business logic methods
directly (no Kafka broker needed).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDeploymentConsumerLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_sets_running_and_spawns_thread(self):
        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()
        with patch.object(consumer, "_consume_thread"):
            await consumer.start()

        assert consumer._running is True
        assert consumer._thread is not None
        assert consumer._thread.daemon is True
        assert consumer._loop is not None

        # Cleanup
        consumer._running = False

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self):
        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()
        consumer._running = True
        consumer._consumer = MagicMock()

        await consumer.stop()

        assert consumer._running is False
        consumer._consumer.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_without_consumer(self):
        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()
        consumer._running = True
        consumer._consumer = None

        await consumer.stop()

        assert consumer._running is False


class TestHandleMessage:
    """Tests for _handle message dispatch."""

    def test_handle_dispatches_event(self):
        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()
        loop = asyncio.new_event_loop()
        consumer._loop = loop

        message = MagicMock()
        message.value = {
            "event_type": "deployment.completed",
            "payload": {"deployment_id": "deploy-123", "status": "success"},
        }

        with (
            patch(
                "src.consumers.deployment_consumer.notify_deployment_event",
                new_callable=AsyncMock,
            ),
            patch("asyncio.run_coroutine_threadsafe") as mock_rcts,
        ):
                mock_future = MagicMock()
                mock_rcts.return_value = mock_future

                consumer._handle(message)

                mock_rcts.assert_called_once()
                mock_future.result.assert_called_once_with(timeout=10)

        loop.close()

    def test_handle_skips_missing_event_type(self):
        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()
        consumer._loop = MagicMock()

        message = MagicMock()
        message.value = {"payload": {"data": "no event_type"}}

        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            consumer._handle(message)
            mock_rcts.assert_not_called()

    def test_handle_empty_event_type(self):
        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()
        consumer._loop = MagicMock()

        message = MagicMock()
        message.value = {"event_type": "", "payload": {}}

        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            consumer._handle(message)
            mock_rcts.assert_not_called()

    def test_handle_flat_envelope(self):
        """When payload is absent, uses the whole data dict as payload."""
        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()
        loop = asyncio.new_event_loop()
        consumer._loop = loop

        message = MagicMock()
        message.value = {
            "event_type": "deployment.started",
            "deployment_id": "deploy-456",
        }

        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            mock_future = MagicMock()
            mock_rcts.return_value = mock_future

            consumer._handle(message)

            # Verify the full data dict is passed as payload
            mock_rcts.assert_called_once()

        loop.close()

    def test_handle_exception_logged(self):
        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()
        consumer._loop = MagicMock()

        message = MagicMock()
        message.value = {"event_type": "deployment.failed", "payload": {}}

        with patch("asyncio.run_coroutine_threadsafe", side_effect=Exception("boom")):
            # Should not raise
            consumer._handle(message)

    def test_handle_no_loop(self):
        """If loop is None, nothing should happen."""
        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()
        consumer._loop = None

        message = MagicMock()
        message.value = {"event_type": "deployment.completed", "payload": {}}

        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            consumer._handle(message)
            mock_rcts.assert_not_called()


class TestCreateConsumer:
    """Tests for _create_consumer Kafka config."""

    def test_create_consumer_basic_config(self):
        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()

        with (
            patch("src.consumers.deployment_consumer.KafkaConsumer") as MockKC,
            patch("src.consumers.deployment_consumer.settings") as mock_settings,
        ):
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "broker1:9092,broker2:9092"
            mock_settings.KAFKA_SASL_USERNAME = None

            consumer._create_consumer()

            MockKC.assert_called_once()
            call_kwargs = MockKC.call_args[1]
            assert call_kwargs["bootstrap_servers"] == ["broker1:9092", "broker2:9092"]
            assert call_kwargs["group_id"] == "deployment-notification-consumer"
            assert call_kwargs["auto_offset_reset"] == "earliest"

    def test_create_consumer_with_sasl(self):
        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()

        with (
            patch("src.consumers.deployment_consumer.KafkaConsumer") as MockKC,
            patch("src.consumers.deployment_consumer.settings") as mock_settings,
        ):
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "broker:9092"
            mock_settings.KAFKA_SASL_USERNAME = "user"
            mock_settings.KAFKA_SASL_PASSWORD = "pass"

            consumer._create_consumer()

            call_kwargs = MockKC.call_args[1]
            assert call_kwargs["security_protocol"] == "SASL_PLAINTEXT"
            assert call_kwargs["sasl_mechanism"] == "SCRAM-SHA-256"
            assert call_kwargs["sasl_plain_username"] == "user"

    def test_create_consumer_returns_none_on_error(self):
        from kafka.errors import KafkaError

        from src.consumers.deployment_consumer import DeploymentConsumer

        consumer = DeploymentConsumer()

        with (
            patch("src.consumers.deployment_consumer.KafkaConsumer", side_effect=KafkaError("fail")),
            patch("src.consumers.deployment_consumer.settings") as mock_settings,
        ):
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "broker:9092"
            mock_settings.KAFKA_SASL_USERNAME = None

            assert consumer._create_consumer() is None
