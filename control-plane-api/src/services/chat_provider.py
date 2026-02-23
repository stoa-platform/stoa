"""Chat provider abstraction and Anthropic implementation (CAB-286).

Defines a Protocol so new LLM providers can be added without changing the
service layer.  The Anthropic provider uses the Messages API with streaming.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)

# Default Anthropic API settings
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------


@runtime_checkable
class ChatProviderProtocol(Protocol):
    """Interface every LLM chat provider must implement."""

    async def stream_response(
        self,
        *,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield SSE-compatible dicts with event type and data."""
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Anthropic implementation
# ---------------------------------------------------------------------------


class AnthropicProvider:
    """Anthropic Messages API streaming provider."""

    async def stream_response(
        self,
        *,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream an Anthropic Messages response, yielding normalised events."""

        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": messages,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with (
            httpx.AsyncClient(timeout=120.0) as client,
            client.stream(
                "POST",
                ANTHROPIC_API_URL,
                headers=headers,
                json=payload,
            ) as response,
        ):
            if response.status_code != 200:
                body = await response.aread()
                logger.error(
                    "Anthropic API error",
                    extra={
                        "status": response.status_code,
                        "body": body.decode("utf-8", errors="replace")[:500],
                    },
                )
                yield {
                    "event": "error",
                    "data": {
                        "error": f"Anthropic API returned {response.status_code}",
                        "detail": body.decode("utf-8", errors="replace")[:500],
                    },
                }
                return

            async for line in response.aiter_lines():
                if not line:
                    continue

                if line.startswith("event: "):
                    continue

                if line.startswith("data: "):
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        break

                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    async for evt in self._map_chunk(chunk):
                        yield evt

    # ------------------------------------------------------------------
    # Internal: map Anthropic SSE chunks to normalised events
    # ------------------------------------------------------------------

    async def _map_chunk(self, chunk: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Map a single Anthropic SSE chunk to zero or more normalised events."""

        chunk_type = chunk.get("type", "")

        if chunk_type == "message_start":
            msg = chunk.get("message", {})
            yield {
                "event": "message_start",
                "data": {
                    "message_id": msg.get("id", ""),
                    "model": msg.get("model", ""),
                },
            }

        elif chunk_type == "content_block_start":
            block = chunk.get("content_block", {})
            if block.get("type") == "tool_use":
                yield {
                    "event": "tool_use_start",
                    "data": {
                        "tool_use_id": block.get("id", ""),
                        "tool_name": block.get("name", ""),
                    },
                }

        elif chunk_type == "content_block_delta":
            delta = chunk.get("delta", {})
            if delta.get("type") == "text_delta":
                yield {
                    "event": "content_delta",
                    "data": {"delta": delta.get("text", "")},
                }
            elif delta.get("type") == "input_json_delta":
                yield {
                    "event": "content_delta",
                    "data": {"delta": delta.get("partial_json", "")},
                }

        elif chunk_type == "message_delta":
            usage = chunk.get("usage", {})
            yield {
                "event": "message_end",
                "data": {
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "stop_reason": chunk.get("delta", {}).get("stop_reason", "end_turn"),
                },
            }
