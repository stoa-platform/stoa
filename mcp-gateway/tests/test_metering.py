# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for Metering Pipeline."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from src.metering.models import (
    MeteringEvent,
    MeteringEventBatch,
    MeteringStatus,
)
from src.metering.producer import (
    MeteringProducer,
    get_metering_producer,
    shutdown_metering_producer,
)


# =============================================================================
# MeteringEvent Model Tests
# =============================================================================


class TestMeteringEvent:
    """Tests for MeteringEvent model."""

    def test_create_event_with_required_fields(self):
        """Test creating event with minimal required fields."""
        event = MeteringEvent(
            tenant="acme-corp",
            user_id="user-123",
            tool="stoa_list_apis",
            latency_ms=45,
            status=MeteringStatus.SUCCESS,
        )

        assert event.tenant == "acme-corp"
        assert event.user_id == "user-123"
        assert event.tool == "stoa_list_apis"
        assert event.latency_ms == 45
        assert event.status == MeteringStatus.SUCCESS
        assert isinstance(event.event_id, UUID)
        assert isinstance(event.timestamp, datetime)
        assert event.consumer == "unknown"
        assert event.cost_units == 0.001

    def test_create_event_with_all_fields(self):
        """Test creating event with all fields."""
        event = MeteringEvent(
            tenant="acme-corp",
            project="api-prod",
            consumer="claude-desktop",
            user_id="user-123",
            tool="stoa_deploy_api",
            latency_ms=500,
            status=MeteringStatus.SUCCESS,
            cost_units=0.005,
            request_id="req-abc",
            metadata={"api_id": "api-1"},
        )

        assert event.project == "api-prod"
        assert event.consumer == "claude-desktop"
        assert event.cost_units == 0.005
        assert event.request_id == "req-abc"
        assert event.metadata == {"api_id": "api-1"}

    def test_from_tool_invocation(self):
        """Test creating event from tool invocation context."""
        event = MeteringEvent.from_tool_invocation(
            tenant="acme-corp",
            user_id="user-123",
            tool="stoa_create_api",
            latency_ms=100,
            status=MeteringStatus.SUCCESS,
            project="my-project",
            consumer="cursor",
            request_id="req-xyz",
        )

        assert event.tenant == "acme-corp"
        assert event.user_id == "user-123"
        assert event.tool == "stoa_create_api"
        assert event.latency_ms == 100
        assert event.status == MeteringStatus.SUCCESS
        assert event.project == "my-project"
        assert event.consumer == "cursor"
        assert event.request_id == "req-xyz"

    def test_to_kafka_message(self):
        """Test converting event to Kafka message format."""
        event = MeteringEvent(
            tenant="acme-corp",
            user_id="user-123",
            tool="stoa_list_apis",
            latency_ms=45,
            status=MeteringStatus.SUCCESS,
        )

        msg = event.to_kafka_message()

        assert msg["tenant"] == "acme-corp"
        assert msg["user_id"] == "user-123"
        assert msg["tool"] == "stoa_list_apis"
        assert msg["latency_ms"] == 45
        assert msg["status"] == "success"
        assert "timestamp" in msg
        assert msg["timestamp"].endswith("Z")

    def test_cost_computation_base(self):
        """Test base cost computation."""
        cost = MeteringEvent._compute_cost("stoa_list_apis", 100)
        # Base cost 0.001 + latency cost 0.0001
        assert cost == pytest.approx(0.0011, rel=1e-4)

    def test_cost_computation_premium_tool(self):
        """Test premium tool has higher cost."""
        cost_regular = MeteringEvent._compute_cost("stoa_list_apis", 100)
        cost_premium = MeteringEvent._compute_cost("stoa_delete_api", 100)

        # Premium tools have 2x base cost
        assert cost_premium > cost_regular

    def test_cost_computation_long_latency(self):
        """Test latency affects cost."""
        cost_fast = MeteringEvent._compute_cost("stoa_list_apis", 100)
        cost_slow = MeteringEvent._compute_cost("stoa_list_apis", 1000)

        assert cost_slow > cost_fast


class TestMeteringStatus:
    """Tests for MeteringStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert MeteringStatus.SUCCESS.value == "success"
        assert MeteringStatus.ERROR.value == "error"
        assert MeteringStatus.TIMEOUT.value == "timeout"
        assert MeteringStatus.RATE_LIMITED.value == "rate_limited"
        assert MeteringStatus.UNAUTHORIZED.value == "unauthorized"


class TestMeteringEventBatch:
    """Tests for MeteringEventBatch model."""

    def test_create_batch(self):
        """Test creating a batch of events."""
        events = [
            MeteringEvent(
                tenant="acme-corp",
                user_id="user-123",
                tool="stoa_list_apis",
                latency_ms=45,
                status=MeteringStatus.SUCCESS,
                cost_units=0.001,
            ),
            MeteringEvent(
                tenant="acme-corp",
                user_id="user-123",
                tool="stoa_create_api",
                latency_ms=100,
                status=MeteringStatus.SUCCESS,
                cost_units=0.002,
            ),
        ]

        batch = MeteringEventBatch(events=events)

        assert batch.count == 2
        assert batch.total_cost_units == pytest.approx(0.003, rel=1e-4)
        assert isinstance(batch.batch_id, UUID)
        assert isinstance(batch.created_at, datetime)


# =============================================================================
# MeteringProducer Tests
# =============================================================================


class TestMeteringProducer:
    """Tests for MeteringProducer."""

    def test_producer_init(self):
        """Test producer initialization."""
        producer = MeteringProducer(
            bootstrap_servers="localhost:9092",
            topic="test.metering",
            enabled=True,
            client_id="test-client",
        )

        assert producer.bootstrap_servers == "localhost:9092"
        assert producer.topic == "test.metering"
        assert producer.enabled is True
        assert producer.client_id == "test-client"

    def test_producer_disabled(self):
        """Test producer when disabled."""
        producer = MeteringProducer(enabled=False)
        assert producer.enabled is False

    @pytest.mark.asyncio
    async def test_emit_when_disabled(self):
        """Test emit returns False when disabled."""
        producer = MeteringProducer(enabled=False)

        event = MeteringEvent(
            tenant="acme-corp",
            user_id="user-123",
            tool="stoa_list_apis",
            latency_ms=45,
            status=MeteringStatus.SUCCESS,
        )

        result = await producer.emit(event)
        assert result is False

    @pytest.mark.asyncio
    async def test_emit_batch_when_disabled(self):
        """Test emit_batch returns 0 when disabled."""
        producer = MeteringProducer(enabled=False)

        batch = MeteringEventBatch(
            events=[
                MeteringEvent(
                    tenant="acme-corp",
                    user_id="user-123",
                    tool="stoa_list_apis",
                    latency_ms=45,
                    status=MeteringStatus.SUCCESS,
                )
            ]
        )

        result = await producer.emit_batch(batch)
        assert result == 0

    @pytest.mark.asyncio
    async def test_emit_immediate_when_not_started(self):
        """Test emit_immediate returns False when not started."""
        producer = MeteringProducer(enabled=True)
        # Not calling startup()

        event = MeteringEvent(
            tenant="acme-corp",
            user_id="user-123",
            tool="stoa_list_apis",
            latency_ms=45,
            status=MeteringStatus.SUCCESS,
        )

        result = await producer.emit_immediate(event)
        assert result is False

    @pytest.mark.asyncio
    async def test_startup_disabled(self):
        """Test startup does nothing when disabled."""
        producer = MeteringProducer(enabled=False)
        await producer.startup()
        assert producer._producer is None

    @pytest.mark.asyncio
    async def test_startup_failure_disables_metering(self):
        """Test startup failure gracefully disables metering."""
        producer = MeteringProducer(
            bootstrap_servers="invalid:9092",
            enabled=True,
        )

        # Mock AIOKafkaProducer to raise exception
        with patch("src.metering.producer.AIOKafkaProducer") as mock_kafka:
            mock_instance = AsyncMock()
            mock_instance.start.side_effect = Exception("Connection refused")
            mock_kafka.return_value = mock_instance

            await producer.startup()

            # Should have disabled metering
            assert producer.enabled is False
            assert producer._started is False

    @pytest.mark.asyncio
    async def test_shutdown_flushes_buffer(self):
        """Test shutdown flushes buffered events."""
        producer = MeteringProducer(enabled=True)
        producer._started = True
        producer._buffer = [
            MeteringEvent(
                tenant="acme-corp",
                user_id="user-123",
                tool="stoa_list_apis",
                latency_ms=45,
                status=MeteringStatus.SUCCESS,
            )
        ]

        # Mock the flush
        producer._flush_buffer = AsyncMock()

        await producer.shutdown()

        producer._flush_buffer.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_buffers_events(self):
        """Test emit adds events to buffer."""
        producer = MeteringProducer(enabled=True)

        event = MeteringEvent(
            tenant="acme-corp",
            user_id="user-123",
            tool="stoa_list_apis",
            latency_ms=45,
            status=MeteringStatus.SUCCESS,
        )

        result = await producer.emit(event)

        assert result is True
        assert len(producer._buffer) == 1
        assert producer._buffer[0] == event

    @pytest.mark.asyncio
    async def test_emit_flushes_on_buffer_full(self):
        """Test emit flushes when buffer is full."""
        producer = MeteringProducer(enabled=True)
        producer._buffer_size = 2
        producer._flush_buffer = AsyncMock()

        # Add two events to fill buffer
        event = MeteringEvent(
            tenant="acme-corp",
            user_id="user-123",
            tool="stoa_list_apis",
            latency_ms=45,
            status=MeteringStatus.SUCCESS,
        )

        await producer.emit(event)
        await producer.emit(event)

        # Should have flushed
        producer._flush_buffer.assert_called_once()


# =============================================================================
# Singleton Tests
# =============================================================================


class TestMeteringSingleton:
    """Tests for metering producer singleton."""

    @pytest.mark.asyncio
    async def test_get_metering_producer_creates_singleton(self):
        """Test get_metering_producer returns singleton."""
        await shutdown_metering_producer()  # Clean up

        with patch("src.metering.producer.AIOKafkaProducer") as mock_kafka:
            mock_instance = AsyncMock()
            mock_kafka.return_value = mock_instance

            producer1 = await get_metering_producer()
            producer2 = await get_metering_producer()

            assert producer1 is producer2

            await shutdown_metering_producer()

    @pytest.mark.asyncio
    async def test_shutdown_clears_singleton(self):
        """Test shutdown clears the singleton."""
        with patch("src.metering.producer.AIOKafkaProducer") as mock_kafka:
            mock_instance = AsyncMock()
            mock_kafka.return_value = mock_instance

            producer1 = await get_metering_producer()
            await shutdown_metering_producer()

            producer2 = await get_metering_producer()
            assert producer1 is not producer2

            await shutdown_metering_producer()


# =============================================================================
# Integration Tests (with mocked Kafka)
# =============================================================================


class TestMeteringIntegration:
    """Integration tests for metering with mocked Kafka."""

    @pytest.mark.asyncio
    async def test_full_event_flow(self):
        """Test full flow from event creation to Kafka send."""
        with patch("src.metering.producer.AIOKafkaProducer") as mock_kafka:
            # Setup mock
            mock_producer = AsyncMock()
            mock_kafka.return_value = mock_producer

            # Create producer and start
            producer = MeteringProducer(
                bootstrap_servers="localhost:9092",
                topic="test.metering",
                enabled=True,
            )
            await producer.startup()

            # Create and emit event
            event = MeteringEvent.from_tool_invocation(
                tenant="acme-corp",
                user_id="user-123",
                tool="stoa_create_api",
                latency_ms=100,
                status=MeteringStatus.SUCCESS,
                consumer="claude-desktop",
            )

            # Use emit_immediate for simpler testing
            result = await producer.emit_immediate(event)
            assert result is True

            # Verify send was called
            mock_producer.send_and_wait.assert_called_once()

            await producer.shutdown()

    @pytest.mark.asyncio
    async def test_emit_immediate_sends_directly(self):
        """Test emit_immediate sends without buffering."""
        with patch("src.metering.producer.AIOKafkaProducer") as mock_kafka:
            mock_producer = AsyncMock()
            mock_kafka.return_value = mock_producer

            producer = MeteringProducer(
                bootstrap_servers="localhost:9092",
                topic="test.metering",
                enabled=True,
            )
            await producer.startup()

            event = MeteringEvent(
                tenant="acme-corp",
                user_id="user-123",
                tool="stoa_list_apis",
                latency_ms=45,
                status=MeteringStatus.SUCCESS,
            )

            result = await producer.emit_immediate(event)
            assert result is True

            # Should have sent directly
            mock_producer.send_and_wait.assert_called_once()

            await producer.shutdown()
