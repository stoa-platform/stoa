# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for Token Counter middleware and worker (CAB-881)."""

import asyncio
import json
from unittest.mock import patch

import pytest

from src.middleware.token_counter import (
    TokenCounterMiddleware,
    TokenPayload,
    count_tokens,
    get_token_queue,
    _count_tokens_approx,
    _extract_tool_name,
    _hash_for_log,
    TOKENS_TOTAL,
    TOKENS_BY_TENANT,
    PAYLOAD_BYTES,
)
from src.middleware.token_counter_worker import TokenCounterWorker


# =============================================================================
# Token Counting
# =============================================================================


class TestCountTokens:
    """Tests for the token counting functions."""

    def test_approx_empty_string(self):
        assert _count_tokens_approx("") == 1  # min 1

    def test_approx_short_string(self):
        assert _count_tokens_approx("hello") == 1  # 5 // 4 = 1

    def test_approx_known_length(self):
        text = "a" * 400
        assert _count_tokens_approx(text) == 100

    def test_approx_json_payload(self):
        payload = json.dumps({"id": "123", "title": "Test issue", "state": "open"})
        tokens = _count_tokens_approx(payload)
        assert tokens > 0
        assert tokens == len(payload) // 4

    def test_count_tokens_default_is_approx(self):
        with patch.dict("os.environ", {}, clear=True):
            result = count_tokens("hello world test string")
            expected = _count_tokens_approx("hello world test string")
            assert result == expected

    def test_count_tokens_tiktoken_env(self):
        """When STOA_TOKEN_COUNTER=tiktoken but tiktoken not installed, falls back."""
        with patch.dict("os.environ", {"STOA_TOKEN_COUNTER": "tiktoken"}):
            # Should not raise even if tiktoken is not installed
            result = count_tokens("hello world")
            assert result > 0


# =============================================================================
# Tool Name Extraction
# =============================================================================


class TestExtractToolName:
    """Tests for extracting tool names from requests."""

    def test_rest_path(self):
        assert _extract_tool_name("/tools/linear-get-issue", None) == "linear-get-issue"

    def test_jsonrpc_body(self):
        body = {"method": "tools/call", "params": {"name": "notion-search"}}
        assert _extract_tool_name("/mcp/v1", body) == "notion-search"

    def test_unknown_path(self):
        assert _extract_tool_name("/health", None) is None

    def test_nested_tools_path(self):
        assert _extract_tool_name("/tools/my-tool", None) == "my-tool"


# =============================================================================
# PII Masking
# =============================================================================


class TestHashForLog:
    """Tests for PII hashing in logs."""

    def test_hash_deterministic(self):
        assert _hash_for_log("tenant-123") == _hash_for_log("tenant-123")

    def test_hash_different_inputs(self):
        assert _hash_for_log("tenant-a") != _hash_for_log("tenant-b")

    def test_hash_length(self):
        assert len(_hash_for_log("any-value")) == 12


# =============================================================================
# Queue
# =============================================================================


class TestTokenQueue:
    """Tests for the async token queue."""

    def test_get_queue_singleton(self):
        q1 = get_token_queue()
        q2 = get_token_queue()
        assert q1 is q2

    @pytest.mark.asyncio
    async def test_queue_put_get(self):
        queue = get_token_queue()
        # Drain any existing items
        while not queue.empty():
            queue.get_nowait()

        payload = TokenPayload(
            tool_name="test-tool",
            tenant_id="tenant-1",
            direction="request",
            body='{"test": true}',
        )
        await queue.put(payload)
        result = await queue.get()
        assert result.tool_name == "test-tool"
        assert result.tenant_id == "tenant-1"
        assert result.direction == "request"


# =============================================================================
# Worker
# =============================================================================


class TestTokenCounterWorker:
    """Tests for the background token counter worker."""

    @pytest.mark.asyncio
    async def test_worker_processes_payload(self):
        worker = TokenCounterWorker()
        queue = get_token_queue()

        # Drain queue
        while not queue.empty():
            queue.get_nowait()

        # Put a payload
        payload = TokenPayload(
            tool_name="linear-get-issue",
            tenant_id="tenant-test",
            direction="response",
            body='{"id": "123", "title": "Test"}',
        )
        await queue.put(payload)

        # Start worker, let it process, then stop
        await worker.start()
        await asyncio.sleep(0.1)  # Give worker time to process
        await worker.stop()

        # Queue should be drained
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_worker_start_stop_idempotent(self):
        worker = TokenCounterWorker()
        await worker.start()
        await worker.start()  # Should not raise
        await worker.stop()
        await worker.stop()  # Should not raise

    def test_process_records_metrics(self):
        worker = TokenCounterWorker()
        payload = TokenPayload(
            tool_name="test-metrics",
            tenant_id="tenant-metrics",
            direction="response",
            body="a" * 400,  # 100 tokens
        )

        # Get current counter values before
        before = TOKENS_TOTAL.labels(
            tool_name="test-metrics", direction="response"
        )._value.get()

        worker._process(payload)

        after = TOKENS_TOTAL.labels(
            tool_name="test-metrics", direction="response"
        )._value.get()

        assert after - before == 100
