# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for Response Capping Engine (CAB-874).

Validates token-aware truncation for arrays, dicts with lists,
plain text, MCP envelope handling, and HTTP header injection.
"""

import json

import pytest
from pydantic import ValidationError

from src.middleware.token_counter import count_tokens
from src.transformer.capper import CapEngine, CapResult, _create_marker
from src.transformer.config import TransformConfig


# =============================================================================
# Fixtures — Reuse shapes from test_transformer.py
# =============================================================================

SMALL_PAYLOAD = {"id": "1", "title": "Hello"}

LINEAR_ISSUE = {
    "id": "issue-uuid-123",
    "identifier": "ENG-456",
    "title": "Fix token counting bug",
    "description": "A " * 2000 + "long description",
    "state": {"id": "state-1", "name": "In Progress", "type": "started"},
    "priority": 2,
    "assignee": {"id": "user-1", "name": "Alice"},
    "url": "https://linear.app/stoa/issue/ENG-456",
}

LARGE_LIST = [
    {"id": f"issue-{i}", "title": f"Issue number {i}", "description": "x" * 200}
    for i in range(100)
]

DICT_WITH_LIST = {
    "total": 100,
    "hasNextPage": True,
    "issues": LARGE_LIST,
}


# =============================================================================
# CapEngine — Unit Tests
# =============================================================================


class TestCapEngineUnderBudget:
    """Payloads under budget pass through unchanged."""

    def test_small_dict_unchanged(self):
        result = CapEngine.cap_response(SMALL_PAYLOAD, max_tokens=8000)
        assert not result.was_capped
        assert result.payload == SMALL_PAYLOAD
        assert result.original_tokens == result.final_tokens

    def test_empty_list_unchanged(self):
        result = CapEngine.cap_response([], max_tokens=8000)
        assert not result.was_capped
        assert result.payload == []

    def test_empty_dict_unchanged(self):
        result = CapEngine.cap_response({}, max_tokens=8000)
        assert not result.was_capped


class TestCapEngineArrayCapping:
    """Array capping via binary search."""

    def test_large_array_is_capped(self):
        result = CapEngine.cap_response(LARGE_LIST, max_tokens=2000)
        assert result.was_capped
        assert result.items_kept is not None
        assert result.items_kept < 100
        assert result.total_items == 100

    def test_capped_array_has_marker(self):
        result = CapEngine.cap_response(LARGE_LIST, max_tokens=2000)
        assert result.was_capped
        # Last element should be the marker string
        last = result.payload[-1]
        assert isinstance(last, str)
        assert "[STOA: Response truncated" in last
        assert "items" in last

    def test_capped_array_fits_budget(self):
        result = CapEngine.cap_response(LARGE_LIST, max_tokens=2000)
        # items_kept items should fit in budget (marker adds some overhead)
        kept_json = json.dumps(result.payload[:-1], separators=(",", ":"))
        assert count_tokens(kept_json) <= 2000

    def test_capped_payload_is_valid_json(self):
        result = CapEngine.cap_response(LARGE_LIST, max_tokens=1000)
        # Should be serializable
        serialized = json.dumps(result.payload)
        parsed = json.loads(serialized)
        assert isinstance(parsed, list)


class TestCapEngineDictWithList:
    """Dict containing a list value."""

    def test_dict_list_capped(self):
        result = CapEngine.cap_response(DICT_WITH_LIST, max_tokens=2000)
        assert result.was_capped
        assert result.items_kept < 100
        assert result.total_items == 100
        # Non-list keys preserved
        assert result.payload["total"] == 100
        assert result.payload["hasNextPage"] is True

    def test_dict_list_has_marker(self):
        result = CapEngine.cap_response(DICT_WITH_LIST, max_tokens=2000)
        issues = result.payload["issues"]
        last = issues[-1]
        assert isinstance(last, str)
        assert "[STOA: Response truncated" in last


class TestCapEngineTextCapping:
    """Plain text / non-structured payloads."""

    def test_long_text_capped(self):
        long_text = "word " * 10000  # ~50000 chars ≈ 12500 tokens
        result = CapEngine.cap_response(long_text, max_tokens=500)
        assert result.was_capped
        assert isinstance(result.payload, str)
        assert "[STOA: Response truncated" in result.payload


class TestInlineMarker:
    """Marker format validation."""

    def test_marker_with_items(self):
        marker = _create_marker(25000, 8000, items_kept=45, total_items=100)
        assert "25000" in marker
        assert "8000" in marker
        assert "45/100" in marker
        assert "[STOA:" in marker

    def test_marker_without_items(self):
        marker = _create_marker(12000, 8000)
        assert "12000" in marker
        assert "8000" in marker
        assert "items" not in marker


# =============================================================================
# MCP Envelope Capping
# =============================================================================


class TestMCPEnvelopeCapping:
    """Capping through the MCP response envelope."""

    def _make_envelope(self, payload):
        return {
            "content": [
                {"type": "text", "text": json.dumps(payload)},
            ],
            "isError": False,
        }

    def test_envelope_inner_json_capped(self):
        """Large inner payload should be capped inside the envelope."""
        from src.middleware.response_transformer import ResponseTransformerMiddleware

        mw = ResponseTransformerMiddleware(app=None)
        config = TransformConfig(max_response_tokens=2000)
        envelope = self._make_envelope(LARGE_LIST)

        result = mw._apply_capping(envelope, "linear-list-issues", config)
        assert result.was_capped

        # Parse inner content
        inner_text = result.payload["content"][0]["text"]
        inner = json.loads(inner_text)
        assert isinstance(inner, list)
        assert len(inner) < 101  # Capped + marker

    def test_envelope_under_budget_unchanged(self):
        from src.middleware.response_transformer import ResponseTransformerMiddleware

        mw = ResponseTransformerMiddleware(app=None)
        config = TransformConfig(max_response_tokens=8000)
        envelope = self._make_envelope(SMALL_PAYLOAD)

        result = mw._apply_capping(envelope, "test-tool", config)
        assert not result.was_capped


# =============================================================================
# Config Validation
# =============================================================================


class TestConfigMaxResponseTokens:
    """TransformConfig.max_response_tokens validation."""

    def test_valid_max_response_tokens(self):
        config = TransformConfig(max_response_tokens=5000)
        assert config.max_response_tokens == 5000

    def test_none_uses_global_default(self):
        config = TransformConfig()
        assert config.max_response_tokens is None

    def test_invalid_zero_rejected(self):
        with pytest.raises(ValidationError):
            TransformConfig(max_response_tokens=0)

    def test_invalid_negative_rejected(self):
        with pytest.raises(ValidationError):
            TransformConfig(max_response_tokens=-1)


# =============================================================================
# Per-tool Override
# =============================================================================


class TestPerToolOverride:
    """Per-tool max_response_tokens overrides global default."""

    def test_per_tool_override_caps_smaller(self):
        """Tool with 500 token limit should cap more aggressively."""
        result = CapEngine.cap_response(LARGE_LIST, max_tokens=500)
        assert result.was_capped
        assert result.items_kept < 10  # Very few items at 500 tokens


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Boundary conditions and edge cases."""

    def test_single_huge_item(self):
        """Single item exceeding budget produces valid output."""
        huge = [{"id": "1", "data": "x" * 50000}]
        result = CapEngine.cap_response(huge, max_tokens=100)
        assert result.was_capped
        # Should still produce something valid
        serialized = json.dumps(result.payload)
        assert len(serialized) > 0

    def test_exact_budget(self):
        """Payload exactly at budget should not be capped."""
        payload = {"a": "b"}
        tokens = count_tokens(json.dumps(payload, separators=(",", ":")))
        result = CapEngine.cap_response(payload, max_tokens=tokens)
        assert not result.was_capped

    def test_response_at_limit_plus_one(self):
        """Payload one token over should be capped."""
        # Build a payload that's just over a specific limit
        items = [{"id": str(i)} for i in range(50)]
        serialized = json.dumps(items, separators=(",", ":"))
        exact_tokens = count_tokens(serialized)
        result = CapEngine.cap_response(items, max_tokens=exact_tokens - 1)
        assert result.was_capped
