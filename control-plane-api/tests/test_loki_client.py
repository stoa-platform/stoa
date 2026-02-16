"""Tests for LokiClient (CAB-1291)"""
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.loki_client import LokiClient


def _make_client(**overrides):
    """Create LokiClient with mocked settings."""
    defaults = {
        "LOKI_INTERNAL_URL": "http://loki:3100",
        "LOKI_TIMEOUT_SECONDS": 10,
        "LOKI_ENABLED": True,
    }
    defaults.update(overrides)
    with patch("src.services.loki_client.settings") as mock_settings:
        for k, v in defaults.items():
            setattr(mock_settings, k, v)
        return LokiClient()


# ── Init + Properties ──


class TestInit:
    def test_defaults(self):
        client = _make_client()
        assert client._base_url == "http://loki:3100"
        assert client._timeout == 10.0
        assert client._enabled is True

    def test_disabled(self):
        client = _make_client(LOKI_ENABLED=False)
        assert client.is_enabled is False


# ── Connect ──


class TestConnect:
    async def test_disabled_noop(self):
        client = _make_client(LOKI_ENABLED=False)
        await client.connect()  # should not raise

    async def test_success(self):
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.loki_client.httpx.AsyncClient", return_value=mock_http):
            await client.connect()

    async def test_unhealthy(self):
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.loki_client.httpx.AsyncClient", return_value=mock_http):
            await client.connect()  # should not raise, just warn

    async def test_connection_error(self):
        client = _make_client()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("refused"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.loki_client.httpx.AsyncClient", return_value=mock_http):
            await client.connect()  # should not raise


# ── Disconnect ──


class TestDisconnect:
    async def test_noop(self):
        client = _make_client()
        await client.disconnect()  # no-op, should not raise


# ── query_range ──


class TestQueryRange:
    async def test_disabled_returns_none(self):
        client = _make_client(LOKI_ENABLED=False)
        result = await client.query_range("{job=\"test\"}", datetime.utcnow(), datetime.utcnow())
        assert result is None

    async def test_success(self):
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "stream": {"job": "test"},
                        "values": [
                            ["1708099200000000000", '{"msg": "hello"}'],
                        ],
                    }
                ]
            },
        }

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.loki_client.httpx.AsyncClient", return_value=mock_http):
            entries = await client.query_range(
                "{job=\"test\"}", datetime(2026, 2, 16), datetime(2026, 2, 17)
            )
        assert entries is not None
        assert len(entries) == 1
        assert entries[0]["raw"] == '{"msg": "hello"}'

    async def test_non_success_status(self):
        client = _make_client()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "error"}

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.loki_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.query_range("{job=\"test\"}", datetime(2026, 2, 16), datetime(2026, 2, 17))
        assert result is None

    async def test_timeout(self):
        client = _make_client()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.loki_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.query_range("{job=\"test\"}", datetime(2026, 2, 16), datetime(2026, 2, 17))
        assert result is None

    async def test_exception(self):
        client = _make_client()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("network"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.loki_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.query_range("{job=\"test\"}", datetime(2026, 2, 16), datetime(2026, 2, 17))
        assert result is None


# ── Helper methods ──


class TestExtractLogEntries:
    def test_success(self):
        client = _make_client()
        data = {
            "result": [
                {
                    "stream": {"job": "gw"},
                    "values": [
                        ["1708099200000000000", '{"msg": "ok"}'],
                        ["1708099201000000000", '{"msg": "done"}'],
                    ],
                },
            ]
        }
        entries = client._extract_log_entries(data)
        assert len(entries) == 2
        assert entries[0]["raw"] == '{"msg": "ok"}'
        assert entries[0]["labels"] == {"job": "gw"}

    def test_empty(self):
        client = _make_client()
        entries = client._extract_log_entries({})
        assert entries == []

    def test_malformed(self):
        client = _make_client()
        # Missing 'values' key
        data = {"result": [{"stream": {}}]}
        entries = client._extract_log_entries(data)
        assert entries == []


class TestParseLogLine:
    def test_valid_json(self):
        client = _make_client()
        result = client._parse_log_line('{"tool": "search"}')
        assert result == {"tool": "search"}

    def test_invalid_json(self):
        client = _make_client()
        result = client._parse_log_line("not json")
        assert result is None


class TestGetActivityTitle:
    def test_known_types(self):
        client = _make_client()
        assert "Subscribed" in client._get_activity_title("subscription.created", {"tool_name": "search"})
        assert "approved" in client._get_activity_title("subscription.approved", {"tool_name": "search"})
        assert "revoked" in client._get_activity_title("subscription.revoked", {"tool_name": "x"})
        assert "API call" in client._get_activity_title("api.call", {"tool_name": "search"})
        assert "rotated" in client._get_activity_title("key.rotated", {"tool_name": "search"})

    def test_unknown_type(self):
        client = _make_client()
        title = client._get_activity_title("custom.event", {})
        assert "custom.event" in title


class TestFormatCallEntries:
    def test_formats_entries(self):
        client = _make_client()
        entries = [
            {
                "timestamp": datetime(2026, 2, 16),
                "raw": json.dumps({"request_id": "r1", "tool_id": "t1", "tool_name": "Search", "status": "success", "duration_ms": 150}),
                "labels": {},
            },
        ]
        calls = client._format_call_entries(entries)
        assert len(calls) == 1
        assert calls[0]["id"] == "r1"
        assert calls[0]["tool_id"] == "t1"
        assert calls[0]["latency_ms"] == 150

    def test_invalid_json_skipped(self):
        client = _make_client()
        entries = [
            {"timestamp": datetime(2026, 2, 16), "raw": "not json", "labels": {}},
        ]
        calls = client._format_call_entries(entries)
        assert calls == []


class TestFormatActivityEntries:
    def test_formats_entries(self):
        client = _make_client()
        entries = [
            {
                "timestamp": datetime(2026, 2, 16),
                "raw": json.dumps({"event_type": "api.call", "tool_name": "Search"}),
                "labels": {},
            },
        ]
        activities = client._format_activity_entries(entries)
        assert len(activities) == 1
        assert activities[0]["type"] == "api.call"
        assert "API call" in activities[0]["title"]


# ── get_recent_calls ──


class TestGetRecentCalls:
    async def test_builds_query_and_calls(self):
        client = _make_client()
        client.query_range = AsyncMock(return_value=[
            {
                "timestamp": datetime(2026, 2, 16),
                "raw": json.dumps({"request_id": "r1", "tool_id": "t1", "tool_name": "T", "status": "success", "duration_ms": 100}),
                "labels": {},
            }
        ])
        calls = await client.get_recent_calls("u1", "acme")
        assert len(calls) == 1
        client.query_range.assert_awaited_once()

    async def test_with_all_filters(self):
        client = _make_client()
        client.query_range = AsyncMock(return_value=[])
        calls = await client.get_recent_calls(
            "u1", "acme",
            limit=5,
            tool_id="t1",
            status="error",
            from_date=datetime(2026, 2, 1),
            to_date=datetime(2026, 2, 16),
            search="timeout",
            level="error",
        )
        assert calls == []
        # Verify query was built with filters
        args = client.query_range.call_args
        query = args[0][0]
        assert 'tool_id="t1"' in query
        assert 'status="error"' in query
        assert 'level="error"' in query
        assert "timeout" in query

    async def test_none_result(self):
        client = _make_client()
        client.query_range = AsyncMock(return_value=None)
        calls = await client.get_recent_calls("u1", "acme")
        assert calls == []


# ── get_recent_activity ──


class TestGetRecentActivity:
    async def test_returns_formatted(self):
        client = _make_client()
        client.query_range = AsyncMock(return_value=[
            {
                "timestamp": datetime(2026, 2, 16),
                "raw": json.dumps({"event_type": "subscription.created", "tool_name": "Search"}),
                "labels": {},
            }
        ])
        activities = await client.get_recent_activity("u1", "acme")
        assert len(activities) == 1

    async def test_none_result(self):
        client = _make_client()
        client.query_range = AsyncMock(return_value=None)
        activities = await client.get_recent_activity("u1", "acme")
        assert activities == []
