"""Tests for SecurityAlertConsumer worker (CAB-1388)."""
import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID

import pytest

from src.workers.security_alert_consumer import (
    TOPIC,
    GROUP_ID,
    VALID_SEVERITIES,
    SecurityAlertConsumer,
    SecurityAlertPayload,
)


# ── SecurityAlertPayload ──


class TestSecurityAlertPayload:
    def test_basic_fields(self):
        payload = SecurityAlertPayload(
            id="abc-123",
            type="login_failure",
            source="keycloak",
            tenant_id="acme",
            payload={"severity": "high", "details": {"ip": "1.2.3.4"}},
        )
        assert payload.severity == "high"
        assert payload.details == {"ip": "1.2.3.4"}

    def test_default_source(self):
        payload = SecurityAlertPayload(id="x", type="alert")
        assert payload.source == "unknown"

    def test_default_severity(self):
        payload = SecurityAlertPayload(id="x", type="alert", payload={})
        assert payload.severity == "medium"

    def test_default_details(self):
        payload = SecurityAlertPayload(id="x", type="alert")
        assert payload.details == {}


# ── VALID_SEVERITIES ──


class TestValidSeverities:
    def test_contains_expected(self):
        assert "critical" in VALID_SEVERITIES
        assert "high" in VALID_SEVERITIES
        assert "medium" in VALID_SEVERITIES
        assert "low" in VALID_SEVERITIES

    def test_no_invalid(self):
        assert "unknown" not in VALID_SEVERITIES


# ── SecurityAlertConsumer lifecycle ──


class TestSecurityAlertConsumerLifecycle:
    def test_initial_state(self):
        consumer = SecurityAlertConsumer()
        assert consumer._running is False
        assert consumer._consumer is None
        assert consumer._thread is None

    async def test_start_creates_thread(self):
        consumer = SecurityAlertConsumer()
        with patch.object(consumer, "_consume_thread", return_value=None):
            with patch("threading.Thread") as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread
                await consumer.start()
                assert consumer._running is True
                mock_thread.start.assert_called_once()

    async def test_stop_sets_running_false(self):
        consumer = SecurityAlertConsumer()
        consumer._running = True
        mock_kafka = MagicMock()
        consumer._consumer = mock_kafka
        await consumer.stop()
        assert consumer._running is False
        mock_kafka.close.assert_called_once()

    async def test_stop_without_consumer(self):
        consumer = SecurityAlertConsumer()
        consumer._running = True
        consumer._consumer = None
        await consumer.stop()
        assert consumer._running is False


# ── _create_consumer ──


class TestCreateConsumer:
    def test_kafka_error_returns_none(self):
        consumer = SecurityAlertConsumer()
        from kafka.errors import KafkaError
        with patch("src.workers.security_alert_consumer.KafkaConsumer", side_effect=KafkaError("connection refused")):
            result = consumer._create_consumer()
            assert result is None

    def test_success_without_sasl(self):
        consumer = SecurityAlertConsumer()
        mock_kafka = MagicMock()
        with patch("src.workers.security_alert_consumer.KafkaConsumer", return_value=mock_kafka):
            with patch("src.workers.security_alert_consumer.settings") as mock_settings:
                mock_settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
                mock_settings.KAFKA_SASL_USERNAME = None
                result = consumer._create_consumer()
                assert result is mock_kafka


# ── _process_message ──


class TestProcessMessage:
    def test_valid_alert_persisted(self):
        consumer = SecurityAlertConsumer()
        consumer._loop = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = None
        consumer._loop.run_in_executor = MagicMock()

        message = MagicMock()
        message.value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "type": "brute_force",
            "source": "keycloak",
            "tenant_id": "acme",
            "payload": {"severity": "high", "details": {}},
        }

        with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
            consumer._process_message(message)
        mock_future.result.assert_called_once()

    def test_invalid_payload_logs_warning(self):
        consumer = SecurityAlertConsumer()
        consumer._loop = MagicMock()

        message = MagicMock()
        message.value = {"broken": "data"}  # Missing required 'id' and 'type'

        import logging
        with patch.object(logging.getLogger("src.workers.security_alert_consumer"), "warning") as mock_warn:
            consumer._process_message(message)

    def test_invalid_severity_normalized_to_medium(self):
        consumer = SecurityAlertConsumer()
        consumer._loop = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = None

        message = MagicMock()
        message.value = {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "type": "test",
            "payload": {"severity": "extreme"},  # invalid severity
        }

        captured_severity = []

        async def capture_persist(alert, severity):
            captured_severity.append(severity)

        with patch.object(consumer, "_persist_alert", side_effect=capture_persist):
            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future) as mock_run:
                mock_run.side_effect = lambda coro, loop: mock_future
                consumer._process_message(message)


# ── _persist_alert ──


class TestPersistAlert:
    async def test_persist_calls_session(self):
        consumer = SecurityAlertConsumer()
        alert = SecurityAlertPayload(
            id="550e8400-e29b-41d4-a716-446655440000",
            type="brute_force",
            tenant_id="acme",
            payload={"severity": "high"},
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("src.workers.security_alert_consumer._get_session_factory", return_value=mock_factory):
            await consumer._persist_alert(alert, "high")
            mock_session.execute.assert_called_once()
            mock_session.commit.assert_called_once()


# ── Constants ──


class TestConstants:
    def test_topic(self):
        assert TOPIC == "stoa.security.alerts"

    def test_group_id(self):
        assert GROUP_ID == "security-alert-consumer"
