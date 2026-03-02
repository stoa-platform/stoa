"""Tests for MonitoringService — OpenSearch-backed transaction analytics."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.monitoring_service import MonitoringService, _extract_api_name, _status_from_code

# =============================================================================
# Unit tests for helpers
# =============================================================================


class TestStatusFromCode:
    def test_success_200(self):
        assert _status_from_code(200) == "success"

    def test_success_201(self):
        assert _status_from_code(201) == "success"

    def test_success_204(self):
        assert _status_from_code(204) == "success"

    def test_success_301(self):
        assert _status_from_code(301) == "success"

    def test_error_400(self):
        assert _status_from_code(400) == "error"

    def test_error_401(self):
        assert _status_from_code(401) == "error"

    def test_error_404(self):
        assert _status_from_code(404) == "error"

    def test_error_500(self):
        assert _status_from_code(500) == "error"

    def test_timeout_504(self):
        assert _status_from_code(504) == "timeout"


class TestExtractApiName:
    def test_v1_path(self):
        assert _extract_api_name("/v1/tenants/123") == "tenants"

    def test_v1_apis(self):
        assert _extract_api_name("/v1/apis/my-api") == "apis"

    def test_no_v1_prefix(self):
        assert _extract_api_name("/health") == "health"

    def test_empty_path(self):
        assert _extract_api_name("/") == ""

    def test_deep_path(self):
        assert _extract_api_name("/v1/monitoring/transactions/tx-123") == "monitoring"


# =============================================================================
# MonitoringService tests
# =============================================================================


def _make_os_hit(
    event_id: str = "evt-1",
    method: str = "GET",
    path: str = "/v1/apis",
    status_code: int = 200,
    latency_ms: float = 42.5,
    tenant_id: str = "tenant-1",
    correlation_id: str = "corr-1",
    timestamp: str = "2026-03-02T10:00:00Z",
) -> dict:
    """Build a realistic OpenSearch audit hit."""
    return {
        "_id": f"os-{event_id}",
        "_source": {
            "@timestamp": timestamp,
            "event_id": event_id,
            "correlation_id": correlation_id,
            "tenant_id": tenant_id,
            "request": {"method": method, "path": path},
            "response": {"status_code": status_code, "latency_ms": latency_ms},
            "actor": {"id": "user-1", "ip_address": "10.0.0.1"},
            "details": {},
        },
    }


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.search = AsyncMock()
    return client


@pytest.fixture
def service(mock_client):
    return MonitoringService(mock_client)


class TestListTransactions:
    @pytest.mark.asyncio
    async def test_maps_audit_events(self, service, mock_client):
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    _make_os_hit(event_id="e1", path="/v1/apis", status_code=200, latency_ms=35),
                    _make_os_hit(event_id="e2", path="/v1/tenants/t1", status_code=404, latency_ms=12),
                ],
            },
        }

        result = await service.list_transactions(tenant_id="tenant-1", limit=10)

        assert result is not None
        assert len(result) == 2
        assert result[0].id == "e1"
        assert result[0].api_name == "apis"
        assert result[0].status == "success"
        assert result[0].total_duration_ms == 35
        assert result[1].id == "e2"
        assert result[1].status == "error"

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, service, mock_client):
        mock_client.search.side_effect = Exception("connection refused")

        result = await service.list_transactions(tenant_id="t1")
        assert result is None

    @pytest.mark.asyncio
    async def test_filters_by_status_success(self, service, mock_client):
        mock_client.search.return_value = {"hits": {"hits": []}}

        await service.list_transactions(tenant_id="t1", status="success")

        call_body = mock_client.search.call_args[1]["body"]
        filters = call_body["query"]["bool"]["filter"]
        # Should have tenant_id, time_range, and status_code range filter
        assert len(filters) == 3
        assert {"range": {"response.status_code": {"lt": 400}}} in filters

    @pytest.mark.asyncio
    async def test_filters_by_status_timeout(self, service, mock_client):
        mock_client.search.return_value = {"hits": {"hits": []}}

        await service.list_transactions(tenant_id="t1", status="timeout")

        call_body = mock_client.search.call_args[1]["body"]
        filters = call_body["query"]["bool"]["filter"]
        assert {"term": {"response.status_code": 504}} in filters

    @pytest.mark.asyncio
    async def test_empty_results(self, service, mock_client):
        mock_client.search.return_value = {"hits": {"hits": []}}

        result = await service.list_transactions(tenant_id="t1")
        assert result is not None
        assert result == []


class TestGetTransactionStats:
    @pytest.mark.asyncio
    async def test_aggregations_mapped(self, service, mock_client):
        mock_client.search.return_value = {
            "hits": {"total": {"value": 1000}},
            "aggregations": {
                "success_count": {"doc_count": 900},
                "error_count": {"doc_count": 90},
                "timeout_count": {"doc_count": 10},
                "latency_stats": {"avg": 85.5, "count": 1000, "min": 5, "max": 3000, "sum": 85500},
                "latency_percentiles": {"values": {"95.0": 250.0, "99.0": 800.0}},
                "by_api": {
                    "buckets": [
                        {
                            "key": "/v1/apis",
                            "doc_count": 500,
                            "avg_latency": {"value": 60.0},
                            "errors": {"doc_count": 20},
                        },
                        {
                            "key": "/v1/tenants/t1",
                            "doc_count": 300,
                            "avg_latency": {"value": 120.0},
                            "errors": {"doc_count": 50},
                        },
                    ]
                },
                "by_status_code": {
                    "buckets": [
                        {"key": 200, "doc_count": 800},
                        {"key": 404, "doc_count": 90},
                        {"key": 504, "doc_count": 10},
                    ]
                },
            },
        }

        result = await service.get_transaction_stats(tenant_id="t1", time_range_minutes=60)

        assert result is not None
        assert result.total_requests == 1000
        assert result.success_count == 900
        assert result.error_count == 90
        assert result.timeout_count == 10
        assert result.avg_latency_ms == 85.5
        assert result.p95_latency_ms == 250.0
        assert result.p99_latency_ms == 800.0
        assert result.requests_per_minute == pytest.approx(1000 / 60, rel=0.01)
        assert "apis" in result.by_api
        assert result.by_api["apis"]["total"] == 500
        assert result.by_api["apis"]["errors"] == 20
        assert result.by_status_code[200] == 800

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, service, mock_client):
        mock_client.search.side_effect = Exception("timeout")

        result = await service.get_transaction_stats(tenant_id="t1")
        assert result is None


class TestGetTransaction:
    @pytest.mark.asyncio
    async def test_maps_single_event(self, service, mock_client):
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    _make_os_hit(
                        event_id="evt-42",
                        method="POST",
                        path="/v1/apis",
                        status_code=201,
                        latency_ms=150,
                    )
                ],
            },
        }

        result = await service.get_transaction(event_id="evt-42", tenant_id="tenant-1")

        assert result is not None
        assert result.id == "evt-42"
        assert result.method == "POST"
        assert result.status == "success"
        assert result.total_duration_ms == 150
        assert len(result.spans) == 1
        assert result.spans[0].name == "api_request"
        assert result.spans[0].duration_ms == 150

    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_client):
        mock_client.search.return_value = {"hits": {"hits": []}}

        result = await service.get_transaction(event_id="nope", tenant_id="t1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, service, mock_client):
        mock_client.search.side_effect = Exception("connection error")

        result = await service.get_transaction(event_id="e1", tenant_id="t1")
        assert result is None

    @pytest.mark.asyncio
    async def test_error_message_populated_on_failure(self, service, mock_client):
        hit = _make_os_hit(event_id="err-1", status_code=500)
        hit["_source"]["details"] = {"error": "Internal failure"}
        mock_client.search.return_value = {"hits": {"hits": [hit]}}

        result = await service.get_transaction(event_id="err-1", tenant_id="tenant-1")

        assert result is not None
        assert result.status == "error"
        assert result.error_message == "Internal failure"
