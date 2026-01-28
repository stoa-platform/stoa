# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for MCP error snapshot models."""

import pytest
from datetime import datetime

from src.features.error_snapshots.models import (
    MCPErrorSnapshot,
    MCPErrorType,
    MCPServerContext,
    ToolInvocation,
    LLMContext,
    RetryContext,
    RequestContext,
    UserContext,
    estimate_llm_cost,
)


class TestMCPErrorType:
    """Tests for MCPErrorType enum."""

    def test_server_errors(self):
        """Test server error types exist."""
        assert MCPErrorType.SERVER_TIMEOUT.value == "server_timeout"
        assert MCPErrorType.SERVER_RATE_LIMITED.value == "server_rate_limited"
        assert MCPErrorType.SERVER_AUTH_FAILURE.value == "server_auth_failure"

    def test_tool_errors(self):
        """Test tool error types exist."""
        assert MCPErrorType.TOOL_NOT_FOUND.value == "tool_not_found"
        assert MCPErrorType.TOOL_EXECUTION_ERROR.value == "tool_execution_error"
        assert MCPErrorType.TOOL_TIMEOUT.value == "tool_timeout"

    def test_llm_errors(self):
        """Test LLM error types exist."""
        assert MCPErrorType.LLM_CONTEXT_EXCEEDED.value == "llm_context_exceeded"
        assert MCPErrorType.LLM_QUOTA_EXCEEDED.value == "llm_quota_exceeded"


class TestMCPServerContext:
    """Tests for MCPServerContext model."""

    def test_minimal_context(self):
        """Test creating minimal server context."""
        ctx = MCPServerContext(name="test-server")
        assert ctx.name == "test-server"
        assert ctx.url is None
        assert ctx.tools_available == []

    def test_full_context(self):
        """Test creating full server context."""
        ctx = MCPServerContext(
            name="github-mcp",
            url="https://mcp.example.com/github",
            version="1.2.0",
            tools_available=["search_repos", "create_issue"],
            health_at_error="degraded",
            latency_p99_ms=450,
            error_rate_percent=5.2,
        )
        assert ctx.name == "github-mcp"
        assert len(ctx.tools_available) == 2
        assert ctx.latency_p99_ms == 450


class TestToolInvocation:
    """Tests for ToolInvocation model."""

    def test_basic_invocation(self):
        """Test basic tool invocation."""
        inv = ToolInvocation(
            tool_name="create_issue",
            input_params={"repo": "org/project", "title": "Bug"},
            duration_ms=2340,
        )
        assert inv.tool_name == "create_issue"
        assert inv.duration_ms == 2340
        assert not inv.error_retryable

    def test_error_invocation(self):
        """Test tool invocation with error."""
        inv = ToolInvocation(
            tool_name="create_issue",
            error_type="RateLimitError",
            error_message="Rate limit exceeded",
            error_retryable=True,
            backend_status_code=429,
        )
        assert inv.error_retryable is True
        assert inv.backend_status_code == 429


class TestLLMContext:
    """Tests for LLMContext model."""

    def test_basic_context(self):
        """Test basic LLM context."""
        ctx = LLMContext(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            tokens_input=1250,
            tokens_output=500,
            latency_ms=890,
        )
        assert ctx.provider == "anthropic"
        assert ctx.tokens_input == 1250

    def test_cost_estimation(self):
        """Test LLM cost estimation."""
        cost = estimate_llm_cost("claude-sonnet-4-20250514", 1000, 500)
        # 1K input @ $0.003 + 0.5K output @ $0.015 = $0.003 + $0.0075 = $0.0105
        assert cost > 0
        assert cost < 0.02


class TestRetryContext:
    """Tests for RetryContext model."""

    def test_default_context(self):
        """Test default retry context."""
        ctx = RetryContext()
        assert ctx.attempts == 1
        assert ctx.max_attempts == 3
        assert ctx.strategy == "exponential_backoff"

    def test_with_fallback(self):
        """Test retry context with fallback."""
        ctx = RetryContext(
            attempts=3,
            delays_ms=[100, 400, 1600],
            fallback_attempted=True,
            fallback_server="github-mcp-backup",
        )
        assert ctx.fallback_attempted is True
        assert len(ctx.delays_ms) == 3


class TestMCPErrorSnapshot:
    """Tests for MCPErrorSnapshot model."""

    def test_minimal_snapshot(self):
        """Test creating minimal snapshot."""
        snapshot = MCPErrorSnapshot(
            error_type=MCPErrorType.TOOL_EXECUTION_ERROR,
            error_message="Tool failed",
            request=RequestContext(method="POST", path="/mcp/v1/tools/test/invoke"),
        )
        assert snapshot.id.startswith("MCP-")
        assert snapshot.error_type == MCPErrorType.TOOL_EXECUTION_ERROR
        assert snapshot.response_status == 500

    def test_full_snapshot(self):
        """Test creating full snapshot with all contexts."""
        snapshot = MCPErrorSnapshot(
            error_type=MCPErrorType.SERVER_TIMEOUT,
            error_message="Server timed out",
            request=RequestContext(
                method="POST",
                path="/mcp/v1/tools/github/invoke",
                headers={"content-type": "application/json"},
            ),
            response_status=504,
            user=UserContext(
                user_id="user-123",
                tenant_id="tenant-acme",
                roles=["developer"],
            ),
            mcp_server=MCPServerContext(
                name="github-mcp",
                tools_available=["search", "create_issue"],
            ),
            tool_invocation=ToolInvocation(
                tool_name="create_issue",
                input_params={"repo": "org/repo"},
                duration_ms=30000,
                error_retryable=True,
            ),
            retry_context=RetryContext(attempts=3),
            total_cost_usd=0.015,
            tokens_wasted=1500,
        )
        assert snapshot.mcp_server.name == "github-mcp"
        assert snapshot.tool_invocation.tool_name == "create_issue"
        assert snapshot.total_cost_usd == 0.015
        assert snapshot.tokens_wasted == 1500

    def test_to_kafka_message(self):
        """Test Kafka serialization."""
        snapshot = MCPErrorSnapshot(
            error_type=MCPErrorType.TOOL_NOT_FOUND,
            error_message="Tool not found",
            request=RequestContext(method="GET", path="/mcp/v1/tools/unknown"),
            response_status=404,
        )
        message = snapshot.to_kafka_message()
        assert isinstance(message, dict)
        assert message["error_type"] == "tool_not_found"
        assert "timestamp" in message

    def test_generate_prompt_hash(self):
        """Test prompt hash generation."""
        prompt = "Help me create a GitHub issue"
        hash1 = MCPErrorSnapshot.generate_prompt_hash(prompt)
        hash2 = MCPErrorSnapshot.generate_prompt_hash(prompt)
        assert hash1 == hash2
        assert hash1.startswith("sha256:")

        # Different prompt = different hash
        hash3 = MCPErrorSnapshot.generate_prompt_hash("Different prompt")
        assert hash3 != hash1


class TestEstimateLLMCost:
    """Tests for LLM cost estimation."""

    def test_claude_sonnet_cost(self):
        """Test Claude Sonnet cost estimation."""
        cost = estimate_llm_cost("claude-sonnet-4-20250514", 1000, 1000)
        # 1K input @ $0.003 + 1K output @ $0.015 = $0.018
        assert 0.017 < cost < 0.019

    def test_claude_opus_cost(self):
        """Test Claude Opus cost estimation."""
        cost = estimate_llm_cost("claude-opus-4-20250514", 1000, 1000)
        # 1K input @ $0.015 + 1K output @ $0.075 = $0.09
        assert 0.08 < cost < 0.1

    def test_unknown_model_cost(self):
        """Test unknown model uses default rates."""
        cost = estimate_llm_cost("unknown-model", 1000, 1000)
        # Should use default rates (same as sonnet)
        assert cost > 0

    def test_zero_tokens(self):
        """Test zero tokens returns zero cost."""
        cost = estimate_llm_cost("claude-sonnet-4-20250514", 0, 0)
        assert cost == 0.0
