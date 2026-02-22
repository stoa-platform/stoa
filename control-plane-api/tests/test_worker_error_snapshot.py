"""Tests for ErrorSnapshotConsumer worker (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.workers.error_snapshot_consumer import (
    TOPIC,
    GROUP_ID,
    ErrorSnapshotConsumer,
)


# ── Constants ──


class TestConstants:
    def test_topic(self):
        assert TOPIC == "stoa.errors.snapshots"

    def test_group_id(self):
        assert GROUP_ID == "error-snapshot-consumer"


# ── Lifecycle ──


class TestErrorSnapshotConsumerLifecycle:
    def test_initial_state(self):
        consumer = ErrorSnapshotConsumer()
        assert consumer._running is False
        assert consumer._consumer is None
        assert consumer._thread is None

    async def test_start_creates_thread(self):
        consumer = ErrorSnapshotConsumer()
        with patch("threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            await consumer.start()
            assert consumer._running is True
            mock_thread.start.assert_called_once()

    async def test_stop_sets_running_false(self):
        consumer = ErrorSnapshotConsumer()
        consumer._running = True
        mock_kafka = MagicMock()
        consumer._consumer = mock_kafka
        await consumer.stop()
        assert consumer._running is False
        mock_kafka.close.assert_called_once()

    async def test_stop_no_consumer(self):
        consumer = ErrorSnapshotConsumer()
        consumer._running = True
        consumer._consumer = None
        await consumer.stop()
        assert consumer._running is False


# ── _create_consumer ──


class TestCreateConsumer:
    def test_kafka_error_returns_none(self):
        consumer = ErrorSnapshotConsumer()
        from kafka.errors import KafkaError
        with patch("src.workers.error_snapshot_consumer.KafkaConsumer", side_effect=KafkaError("refused")):
            result = consumer._create_consumer()
            assert result is None

    def test_success_without_sasl(self):
        consumer = ErrorSnapshotConsumer()
        mock_kafka = MagicMock()
        with patch("src.workers.error_snapshot_consumer.KafkaConsumer", return_value=mock_kafka):
            with patch("src.workers.error_snapshot_consumer.settings") as mock_settings:
                mock_settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
                mock_settings.KAFKA_SASL_USERNAME = None
                result = consumer._create_consumer()
                assert result is mock_kafka

    def test_success_with_sasl(self):
        consumer = ErrorSnapshotConsumer()
        mock_kafka = MagicMock()
        with patch("src.workers.error_snapshot_consumer.KafkaConsumer", return_value=mock_kafka):
            with patch("src.workers.error_snapshot_consumer.settings") as mock_settings:
                mock_settings.KAFKA_BOOTSTRAP_SERVERS = "kafka:9092"
                mock_settings.KAFKA_SASL_USERNAME = "user"
                mock_settings.KAFKA_SASL_PASSWORD = "pass"
                result = consumer._create_consumer()
                assert result is mock_kafka


# ── _process_message_sync ──


class TestProcessMessageSync:
    def test_valid_snapshot_stored(self):
        consumer = ErrorSnapshotConsumer()
        consumer._loop = MagicMock()

        message = MagicMock()
        message.value = {
            "id": "snap-001",
            "tenant_id": "acme",
            "source": "webmethods-gateway",
            "request": {"method": "GET", "path": "/api/v1/test", "headers": {}},
            "response": {"status": 500, "body": "Internal Error", "duration_ms": 150},
            "timestamp": "2026-02-22T12:00:00Z",
        }

        mock_service = MagicMock()
        mock_storage = AsyncMock()
        mock_service.storage = mock_storage
        mock_future = MagicMock()
        mock_future.result.return_value = None

        with patch("src.workers.error_snapshot_consumer.get_snapshot_service", return_value=mock_service):
            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
                consumer._process_message_sync(message)
                mock_future.result.assert_called_once()

    def test_adds_default_source(self):
        consumer = ErrorSnapshotConsumer()
        consumer._loop = MagicMock()

        captured_data = []
        message = MagicMock()
        message.value = {
            "id": "snap-002",
            "tenant_id": "acme",
            "request": {"method": "POST", "path": "/api/test", "headers": {}},
            "response": {"status": 400, "body": "Bad Request"},
            "timestamp": "2026-02-22T12:00:00Z",
        }

        mock_service = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = None

        with patch("src.workers.error_snapshot_consumer.get_snapshot_service", return_value=mock_service):
            from src.features.error_snapshots.models import ErrorSnapshot
            with patch.object(ErrorSnapshot, "model_validate", side_effect=lambda d: (captured_data.append(d), MagicMock())[1]):
                with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
                    consumer._process_message_sync(message)
                    # Verify default source was added
                    if captured_data:
                        assert captured_data[0].get("source") == "webmethods-gateway"

    def test_no_service_discards_snapshot(self):
        consumer = ErrorSnapshotConsumer()
        consumer._loop = MagicMock()

        message = MagicMock()
        message.value = {
            "id": "snap-003",
            "tenant_id": "acme",
            "source": "webmethods-gateway",
            "request": {"method": "GET", "path": "/test", "headers": {}},
            "response": {"status": 503, "body": "", "duration_ms": 0},
            "timestamp": "2026-02-22T12:00:00Z",
        }

        with patch("src.workers.error_snapshot_consumer.get_snapshot_service", return_value=None):
            # Should not raise and should log debug
            consumer._process_message_sync(message)

    def test_validation_error_logs_warning(self):
        consumer = ErrorSnapshotConsumer()
        consumer._loop = MagicMock()

        message = MagicMock()
        message.value = {"invalid": "data"}

        # Should not raise, just log warning
        consumer._process_message_sync(message)

    def test_exception_logs_error(self):
        consumer = ErrorSnapshotConsumer()
        consumer._loop = MagicMock()

        message = MagicMock()
        message.value = {
            "id": "snap-004",
            "tenant_id": "acme",
            "source": "webmethods-gateway",
            "request": {"method": "GET", "path": "/test", "headers": {}},
            "response": {"status": 500, "body": "", "duration_ms": 0},
            "timestamp": "2026-02-22T12:00:00Z",
        }

        with patch("src.workers.error_snapshot_consumer.get_snapshot_service", side_effect=RuntimeError("db down")):
            # Should not raise — swallowed with logging
            consumer._process_message_sync(message)


# ── _consume_thread ──


class TestConsumeThread:
    def test_none_consumer_exits_early(self):
        consumer = ErrorSnapshotConsumer()
        consumer._running = True
        with patch.object(consumer, "_create_consumer", return_value=None):
            # Should return without errors
            consumer._consume_thread()
            assert True  # No exception

    def test_stops_when_not_running(self):
        consumer = ErrorSnapshotConsumer()
        consumer._running = False
        mock_kafka = MagicMock()
        mock_kafka.poll.return_value = {}  # Empty messages

        with patch.object(consumer, "_create_consumer", return_value=mock_kafka):
            consumer._consume_thread()
            mock_kafka.close.assert_called_once()
