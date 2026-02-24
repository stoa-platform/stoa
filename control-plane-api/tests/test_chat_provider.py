"""Unit tests for AnthropicProvider — chat_provider.py (CAB-1437)

Tests SSE streaming, chunk mapping, error handling, and payload construction.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.chat_provider import (
    ANTHROPIC_API_URL,
    ANTHROPIC_API_VERSION,
    DEFAULT_MAX_TOKENS,
    AnthropicProvider,
)

# ── Constants ──


class TestConstants:
    def test_api_url(self):
        assert ANTHROPIC_API_URL == "https://api.anthropic.com/v1/messages"

    def test_api_version(self):
        assert ANTHROPIC_API_VERSION == "2023-06-01"

    def test_default_max_tokens(self):
        assert DEFAULT_MAX_TOKENS == 4096


# ── _map_chunk ──


class TestMapChunk:
    """Test normalisation of Anthropic SSE chunks."""

    @pytest.fixture()
    def provider(self):
        return AnthropicProvider()

    async def test_message_start(self, provider):
        chunk = {"type": "message_start", "message": {"id": "msg-1", "model": "claude-3"}}
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 1
        assert events[0]["event"] == "message_start"
        assert events[0]["data"]["message_id"] == "msg-1"
        assert events[0]["data"]["model"] == "claude-3"

    async def test_message_start_empty_message(self, provider):
        chunk = {"type": "message_start", "message": {}}
        events = [e async for e in provider._map_chunk(chunk)]
        assert events[0]["data"]["message_id"] == ""
        assert events[0]["data"]["model"] == ""

    async def test_content_block_start_tool_use(self, provider):
        chunk = {
            "type": "content_block_start",
            "content_block": {"type": "tool_use", "id": "tu-1", "name": "list_apis"},
        }
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 1
        assert events[0]["event"] == "tool_use_start"
        assert events[0]["data"]["tool_use_id"] == "tu-1"
        assert events[0]["data"]["tool_name"] == "list_apis"

    async def test_content_block_start_text(self, provider):
        """Text blocks are not emitted at content_block_start."""
        chunk = {"type": "content_block_start", "content_block": {"type": "text", "text": ""}}
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 0

    async def test_content_block_delta_text(self, provider):
        chunk = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}}
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 1
        assert events[0]["event"] == "content_delta"
        assert events[0]["data"]["delta"] == "Hello"

    async def test_content_block_delta_input_json(self, provider):
        chunk = {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": '{"q":'}}
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 1
        assert events[0]["event"] == "tool_input_delta"
        assert events[0]["data"]["delta"] == '{"q":'

    async def test_content_block_delta_unknown_type(self, provider):
        chunk = {"type": "content_block_delta", "delta": {"type": "unknown_delta"}}
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 0

    async def test_content_block_stop(self, provider):
        chunk = {"type": "content_block_stop", "index": 2}
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 1
        assert events[0]["event"] == "content_block_stop"
        assert events[0]["data"]["index"] == 2

    async def test_message_delta(self, provider):
        chunk = {
            "type": "message_delta",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "delta": {"stop_reason": "end_turn"},
        }
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 1
        assert events[0]["event"] == "message_end"
        assert events[0]["data"]["input_tokens"] == 100
        assert events[0]["data"]["output_tokens"] == 50
        assert events[0]["data"]["stop_reason"] == "end_turn"

    async def test_message_delta_tool_use_stop(self, provider):
        chunk = {
            "type": "message_delta",
            "usage": {"input_tokens": 200, "output_tokens": 75},
            "delta": {"stop_reason": "tool_use"},
        }
        events = [e async for e in provider._map_chunk(chunk)]
        assert events[0]["data"]["stop_reason"] == "tool_use"

    async def test_message_delta_defaults(self, provider):
        chunk = {"type": "message_delta", "usage": {}, "delta": {}}
        events = [e async for e in provider._map_chunk(chunk)]
        assert events[0]["data"]["input_tokens"] == 0
        assert events[0]["data"]["output_tokens"] == 0
        assert events[0]["data"]["stop_reason"] == "end_turn"

    async def test_unknown_chunk_type(self, provider):
        chunk = {"type": "ping"}
        events = [e async for e in provider._map_chunk(chunk)]
        assert len(events) == 0


# ── stream_response ──


class TestStreamResponse:
    """Test the full streaming pipeline."""

    @pytest.fixture()
    def provider(self):
        return AnthropicProvider()

    async def test_non_200_yields_error(self, provider):
        """Non-200 response yields error event and returns."""
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.aread = AsyncMock(return_value=b'{"error": "invalid api key"}')

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.chat_provider.httpx.AsyncClient", return_value=mock_client_ctx):
            events = []
            async for evt in provider.stream_response(
                api_key="bad-key",
                model="claude-3",
                messages=[{"role": "user", "content": "hi"}],
            ):
                events.append(evt)

        assert len(events) == 1
        assert events[0]["event"] == "error"
        assert "401" in events[0]["data"]["error"]

    async def test_successful_stream(self, provider):
        """Successful stream parses SSE lines into events."""
        sse_lines = [
            "event: message_start",
            'data: {"type": "message_start", "message": {"id": "msg-1", "model": "claude-3"}}',
            "",
            "event: content_block_delta",
            'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi"}}',
            "",
            "event: message_delta",
            'data: {"type": "message_delta", "usage": {"input_tokens": 10, "output_tokens": 5}, "delta": {"stop_reason": "end_turn"}}',
            "",
            "data: [DONE]",
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_lines():
            for line in sse_lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.chat_provider.httpx.AsyncClient", return_value=mock_client_ctx):
            events = []
            async for evt in provider.stream_response(
                api_key="sk-test",
                model="claude-3",
                messages=[{"role": "user", "content": "hi"}],
            ):
                events.append(evt)

        event_types = [e["event"] for e in events]
        assert "message_start" in event_types
        assert "content_delta" in event_types
        assert "message_end" in event_types

    async def test_payload_includes_system_and_tools(self, provider):
        """system_prompt and tools are included in payload when provided."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_lines():
            yield "data: [DONE]"

        mock_response.aiter_lines = mock_aiter_lines

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        tools = [{"name": "test_tool", "description": "A test", "input_schema": {}}]

        with patch("src.services.chat_provider.httpx.AsyncClient", return_value=mock_client_ctx):
            async for _ in provider.stream_response(
                api_key="sk-test",
                model="claude-3",
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="You are helpful",
                tools=tools,
            ):
                pass

        # Verify the call was made with correct payload
        call_args = mock_client.stream.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["system"] == "You are helpful"
        assert payload["tools"] == tools
        assert payload["stream"] is True
        assert payload["model"] == "claude-3"

        # Verify headers
        headers = call_args.kwargs.get("headers") or call_args[1].get("headers")
        assert headers["x-api-key"] == "sk-test"
        assert headers["anthropic-version"] == ANTHROPIC_API_VERSION

    async def test_payload_omits_system_and_tools_when_none(self, provider):
        """system_prompt and tools omitted when not provided."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_lines():
            yield "data: [DONE]"

        mock_response.aiter_lines = mock_aiter_lines

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.chat_provider.httpx.AsyncClient", return_value=mock_client_ctx):
            async for _ in provider.stream_response(
                api_key="sk-test",
                model="claude-3",
                messages=[{"role": "user", "content": "hi"}],
            ):
                pass

        call_args = mock_client.stream.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert "system" not in payload
        assert "tools" not in payload

    async def test_malformed_json_skipped(self, provider):
        """Lines with invalid JSON are silently skipped."""
        sse_lines = [
            "data: {this is not json}",
            'data: {"type": "message_delta", "usage": {"input_tokens": 1, "output_tokens": 1}, "delta": {"stop_reason": "end_turn"}}',
            "data: [DONE]",
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_lines():
            for line in sse_lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.chat_provider.httpx.AsyncClient", return_value=mock_client_ctx):
            events = []
            async for evt in provider.stream_response(
                api_key="sk-test",
                model="claude-3",
                messages=[{"role": "user", "content": "hi"}],
            ):
                events.append(evt)

        assert len(events) == 1
        assert events[0]["event"] == "message_end"

    async def test_empty_lines_skipped(self, provider):
        """Empty SSE lines are skipped without error."""
        sse_lines = ["", "", "data: [DONE]"]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_lines():
            for line in sse_lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.chat_provider.httpx.AsyncClient", return_value=mock_client_ctx):
            events = []
            async for evt in provider.stream_response(
                api_key="sk-test",
                model="claude-3",
                messages=[{"role": "user", "content": "hi"}],
            ):
                events.append(evt)

        assert len(events) == 0
