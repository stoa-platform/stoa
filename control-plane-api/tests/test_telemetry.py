"""Tests for the telemetry subsystem (CAB-1682).

Covers:
- TelemetryAdapterInterface contract
- LogWriter batching, circuit breaker, backpressure
- TelemetryCollector normalization
- Telemetry ingest endpoint
- OTel span enrichment on InstrumentedAdapter
"""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.adapters.gateway_adapter_interface import AdapterResult
from src.adapters.telemetry_interface import TelemetryAdapterInterface
from src.opensearch.log_writer import (
    BACKPRESSURE_LIMIT,
    BATCH_SIZE,
    MAX_FAILURES,
    LogWriter,
)
from src.services.telemetry_collector import TelemetryCollector

# --- TelemetryAdapterInterface ---


class FakeTelemetryAdapter(TelemetryAdapterInterface):
    """Concrete implementation for testing."""

    def __init__(self, config=None):
        self._config = config or {}
        self.logs = [
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "gateway_type": "fake",
                "method": "GET",
                "path": "/api/test",
                "status": 200,
                "latency_ms": 42.0,
                "tenant_id": "test-tenant",
            }
        ]

    async def get_access_logs(self, since: datetime, limit: int = 1000) -> list[dict]:
        return self.logs[:limit]

    async def get_metrics_snapshot(self) -> dict:
        return {"requests_total": 100, "errors_total": 2}

    async def setup_push_subscription(self, webhook_url: str) -> AdapterResult:
        return AdapterResult(success=True, data={"webhook_url": webhook_url})


class TestTelemetryAdapterInterface:
    @pytest.mark.asyncio
    async def test_get_access_logs(self):
        adapter = FakeTelemetryAdapter()
        logs = await adapter.get_access_logs(since=datetime.now(UTC) - timedelta(minutes=5))
        assert len(logs) == 1
        assert logs[0]["method"] == "GET"
        assert logs[0]["status"] == 200

    @pytest.mark.asyncio
    async def test_get_metrics_snapshot(self):
        adapter = FakeTelemetryAdapter()
        metrics = await adapter.get_metrics_snapshot()
        assert metrics["requests_total"] == 100

    @pytest.mark.asyncio
    async def test_setup_push_subscription(self):
        adapter = FakeTelemetryAdapter()
        result = await adapter.setup_push_subscription("https://api.example.com/telemetry/ingest")
        assert result.success is True
        assert result.data["webhook_url"] == "https://api.example.com/telemetry/ingest"


# --- LogWriter ---


class TestLogWriter:
    @pytest.mark.asyncio
    async def test_add_entries_to_buffer(self):
        writer = LogWriter()
        entries = [{"timestamp": "2026-03-05T10:00:00", "gateway_type": "kong", "tenant_id": "t1"}]
        result = await writer.add(entries)
        assert result is True
        assert writer.buffer_count() == 1

    @pytest.mark.asyncio
    async def test_backpressure_limit(self):
        writer = LogWriter()
        big_batch = [{"gateway_type": "kong", "tenant_id": "t1"}] * (BACKPRESSURE_LIMIT + 1)
        result = await writer.add(big_batch)
        assert result is False

    @pytest.mark.asyncio
    async def test_flush_calls_bulk(self):
        mock_client = AsyncMock()
        mock_client.bulk.return_value = {"errors": False, "items": []}
        writer = LogWriter(os_client=mock_client)

        entries = [
            {
                "timestamp": "2026-03-05T10:00:00",
                "gateway_type": "kong",
                "tenant_id": "t1",
                "method": "GET",
                "path": "/test",
                "status": 200,
            }
        ]
        await writer.add(entries)
        await writer.flush()

        mock_client.bulk.assert_called_once()
        assert writer.buffer_count() == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        mock_client = AsyncMock()
        mock_client.bulk.side_effect = ConnectionError("OS down")
        writer = LogWriter(os_client=mock_client)

        for _i in range(MAX_FAILURES):
            entries = [{"gateway_type": "kong", "tenant_id": "t1"}]
            await writer.add(entries)
            await writer.flush()

        assert writer._circuit_open is True
        assert writer._consecutive_failures >= MAX_FAILURES

    @pytest.mark.asyncio
    async def test_circuit_breaker_drops_entries_when_open(self):
        writer = LogWriter()
        writer._circuit_open = True
        writer._circuit_opened_at = time.monotonic()

        entries = [{"gateway_type": "kong", "tenant_id": "t1"}]
        await writer.add(entries)
        await writer.flush()

        assert writer.buffer_count() == 0

    @pytest.mark.asyncio
    async def test_no_client_drops_entries(self):
        writer = LogWriter(os_client=None)
        entries = [{"gateway_type": "kong", "tenant_id": "t1"}]
        await writer.add(entries)
        await writer.flush()
        assert writer.buffer_count() == 0

    @pytest.mark.asyncio
    async def test_batch_triggers_flush(self):
        mock_client = AsyncMock()
        mock_client.bulk.return_value = {"errors": False, "items": []}
        writer = LogWriter(os_client=mock_client)

        big_batch = [{"gateway_type": "kong", "tenant_id": "t1"}] * BATCH_SIZE
        await writer.add(big_batch)

        mock_client.bulk.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_bulk_body_format(self):
        entries = [
            {
                "timestamp": "2026-03-05T10:00:00",
                "gateway_type": "kong",
                "tenant_id": "acme",
            }
        ]
        body = LogWriter._build_bulk_body(entries)
        lines = body.strip().split("\n")
        assert len(lines) == 2
        import json

        action = json.loads(lines[0])
        assert "index" in action
        assert action["index"]["_index"] == "stoa-gw-kong-acme-2026.03.05"

    @pytest.mark.asyncio
    async def test_partial_bulk_error_handling(self):
        mock_client = AsyncMock()
        mock_client.bulk.return_value = {
            "errors": True,
            "items": [
                {"index": {"error": "mapping_exception"}},
                {"index": {"_id": "ok"}},
            ],
        }
        writer = LogWriter(os_client=mock_client)
        entries = [{"gateway_type": "kong", "tenant_id": "t1"}, {"gateway_type": "kong", "tenant_id": "t2"}]
        await writer.add(entries)
        await writer.flush()
        # Buffer should be cleared despite partial errors
        assert writer.buffer_count() == 0


# --- TelemetryCollector ---


class TestTelemetryCollector:
    @pytest.mark.asyncio
    async def test_normalize_entry(self):
        collector = TelemetryCollector()
        entry = {
            "timestamp": "2026-03-05T10:00:00",
            "gateway_type": "kong",
            "method": "POST",
            "path": "/api/v1/users",
            "status": 201,
            "latency_ms": 55.3,
            "tenant_id": "acme",
        }
        normalized = collector._normalize(entry)
        assert normalized["gateway_type"] == "kong"
        assert normalized["method"] == "POST"
        assert normalized["status"] == 201
        assert normalized["latency_ms"] == 55.3
        assert normalized["tenant_id"] == "acme"

    @pytest.mark.asyncio
    async def test_normalize_defaults(self):
        collector = TelemetryCollector()
        normalized = collector._normalize({})
        assert normalized["gateway_type"] == "unknown"
        assert normalized["method"] == "UNKNOWN"
        assert normalized["tenant_id"] == "platform"
        assert normalized["status"] == 0

    @pytest.mark.asyncio
    async def test_ingest_calls_log_writer(self):
        collector = TelemetryCollector()
        with patch("src.services.telemetry_collector.log_writer") as mock_writer:
            mock_writer.add = AsyncMock(return_value=True)
            result = await collector.ingest(
                [{"gateway_type": "kong", "method": "GET", "path": "/", "status": 200}],
                source="test",
            )
            assert result is True
            mock_writer.add.assert_called_once()


# --- Telemetry Router ---


class TestTelemetryRouter:
    def test_ingest_endpoint_accepts_valid_payload(self):
        from src.main import app

        client = TestClient(app, raise_server_exceptions=False)
        payload = {
            "entries": [
                {
                    "gateway_type": "kong",
                    "method": "GET",
                    "path": "/api/test",
                    "status": 200,
                    "latency_ms": 42.0,
                    "tenant_id": "acme",
                }
            ]
        }
        with patch("src.services.telemetry_collector.log_writer") as mock_writer:
            mock_writer.add = AsyncMock(return_value=True)
            response = client.post("/internal/telemetry/ingest", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] == 1
        assert data["status"] == "ok"

    def test_ingest_endpoint_rejects_empty_entries(self):
        from src.main import app

        client = TestClient(app, raise_server_exceptions=False)
        payload = {"entries": []}
        response = client.post("/internal/telemetry/ingest", json=payload)
        assert response.status_code == 422

    def test_ingest_endpoint_returns_429_on_backpressure(self):
        from src.main import app

        client = TestClient(app, raise_server_exceptions=False)
        payload = {"entries": [{"gateway_type": "kong", "method": "GET", "path": "/", "status": 200}]}
        with patch("src.services.telemetry_collector.log_writer") as mock_writer:
            mock_writer.add = AsyncMock(return_value=False)
            response = client.post("/internal/telemetry/ingest", json=payload)
        assert response.status_code == 429

    def test_status_endpoint(self):
        from src.main import app

        client = TestClient(app, raise_server_exceptions=False)
        with patch("src.opensearch.log_writer.log_writer") as mock_writer:
            mock_writer.buffer_count.return_value = 42
            mock_writer._circuit_open = False
            mock_writer._consecutive_failures = 0
            response = client.get("/internal/telemetry/status")
        assert response.status_code == 200


# --- OTel Span Enrichment ---


class TestOTelSpanEnrichment:
    @pytest.mark.asyncio
    async def test_record_creates_otel_span(self):
        from src.adapters.metrics import InstrumentedAdapter

        inner = MagicMock()
        inner._config = {}
        inner.health_check = AsyncMock(return_value=AdapterResult(success=True))

        adapter = InstrumentedAdapter(inner=inner, gateway_type="kong")

        with patch("src.adapters.metrics.trace") as mock_trace:
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)
            mock_trace.get_tracer.return_value = mock_tracer

            result = await adapter.health_check()

            assert result.success is True
            mock_trace.get_tracer.assert_called_with("stoa.adapter")
            mock_tracer.start_as_current_span.assert_called_once()
            call_kwargs = mock_tracer.start_as_current_span.call_args
            assert call_kwargs[0][0] == "adapter.health_check"
            assert call_kwargs[1]["attributes"]["adapter.gateway_type"] == "kong"
