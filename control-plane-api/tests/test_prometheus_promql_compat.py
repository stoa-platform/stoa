from unittest.mock import AsyncMock, patch

import pytest

from src.services.prometheus_client import PrometheusClient


@pytest.mark.asyncio
async def test_avg_latency_reads_emitted_gateway_metric_with_legacy_alias():
    client = PrometheusClient()
    client._enabled = True

    with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {
            "resultType": "vector",
            "result": [{"value": [0, "123"]}],
        }

        result = await client.get_avg_latency_ms(tenant_id="acme", time_range="24h")

    query = mock_query.await_args.args[0]
    assert result == 123
    assert "stoa_mcp_tool_duration_seconds_sum" in query
    assert "stoa_mcp_tool_duration_seconds_count" in query
    assert "mcp_request_duration_seconds_sum" in query
    assert "mcp_request_duration_seconds_count" in query
    assert 'tenant="acme"' in query
    assert 'tenant_id="acme"' in query


@pytest.mark.asyncio
async def test_top_tools_normalizes_legacy_tool_label_without_default_regex():
    client = PrometheusClient()
    client._enabled = True

    with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {
            "resultType": "vector",
            "result": [{"metric": {"tool_name": "crm-search"}, "value": [0, "7"]}],
        }

        result = await client.get_top_tools(user_id="user-1", tenant_id="acme")

    query = mock_query.await_args.args[0]
    assert result == [{"tool_id": "crm-search", "tool_name": "crm-search", "call_count": 7}]
    assert "label_replace" in query
    assert 'tenant="acme"' in query
    assert 'tenant_id="acme"' in query
    assert "tool_id" not in query
    assert "tenant=~" not in query
    assert "|default" not in query


@pytest.mark.asyncio
async def test_tool_success_rate_reads_legacy_and_canonical_labels():
    client = PrometheusClient()
    client._enabled = True

    with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {
            "resultType": "vector",
            "result": [{"value": [0, "98.5"]}],
        }

        result = await client.get_tool_success_rate(
            tool_id="crm-search",
            user_id="user-1",
            tenant_id="acme",
            time_range="7d",
        )

    query = mock_query.await_args.args[0]
    assert result == 98.5
    assert 'tool="crm-search"' in query
    assert 'tool_name="crm-search"' in query
    assert 'tenant="acme"' in query
    assert 'tenant_id="acme"' in query
    assert 'status="success"' in query
    assert "tool_id" not in query
    assert "user_id" not in query


def test_extract_tool_stats_maps_legacy_tool_label_to_canonical_name():
    client = PrometheusClient()
    result = {
        "resultType": "vector",
        "result": [{"metric": {"tool": "crm-search"}, "value": [0, "3"]}],
    }

    assert client._extract_tool_stats(result) == [{"tool_id": "crm-search", "tool_name": "crm-search", "call_count": 3}]


@pytest.mark.asyncio
async def test_private_query_shim_returns_prometheus_result_vector():
    client = PrometheusClient()
    client._enabled = True

    with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {
            "resultType": "vector",
            "result": [{"metric": {}, "value": [0, "1"]}],
        }

        assert await client._query("up") == [{"metric": {}, "value": [0, "1"]}]


@pytest.mark.asyncio
async def test_private_query_shim_raises_when_query_fails():
    client = PrometheusClient()
    client._enabled = True

    with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = None

        with pytest.raises(ConnectionError):
            await client._query("up")


def test_router_prometheus_identifier_and_time_range_validation():
    client = PrometheusClient()

    assert client._validate_identifier("oasis-gunters", "tenant_id") == "oasis-gunters"
    assert client._validate_identifier("123e4567-e89b-12d3-a456-426614174000", "tenant_id")
    assert client._validate_time_range("24h") == "24h"
    assert client._validate_time_range("36500d") == "36500d"

    with pytest.raises(ValueError):
        client._validate_identifier('acme" or tenant!="acme', "tenant_id")
    with pytest.raises(ValueError):
        client._validate_time_range("99x")
