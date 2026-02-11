"""Tests for Policy Management API Endpoints.

CAB-875: Tests for /mcp/v1/policies/* endpoints.

These tests verify the API contract and response structure.
The core policy engine logic is tested in test_argument_policy.py.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Depends

from src.handlers.policy_api import (
    router,
    PolicyCheckRequest,
    PolicyCheckResponse,
    ListPolicyRulesResponse,
    PolicyRuleInfo,
)
from src.policy.argument_models import Policy, PolicyResult, Rule, ConditionLeaf, Operator


class TestPolicyCheckResponse:
    """Tests for PolicyCheckResponse model."""

    def test_allowed_response(self):
        """Test allowed response structure."""
        response = PolicyCheckResponse(allowed=True)
        assert response.allowed is True
        assert response.policy_name is None
        assert response.message is None

    def test_denied_response(self):
        """Test denied response structure."""
        response = PolicyCheckResponse(
            allowed=False,
            policy_name="test-policy",
            rule_index=0,
            message="Denied",
            action="deny",
        )
        assert response.allowed is False
        assert response.policy_name == "test-policy"
        assert response.action == "deny"

    def test_warning_response(self):
        """Test warning response structure."""
        response = PolicyCheckResponse(
            allowed=True,
            policy_name="warn-policy",
            message="Warning message",
            action="warn",
        )
        assert response.allowed is True
        assert response.action == "warn"


class TestListPolicyRulesResponse:
    """Tests for ListPolicyRulesResponse model."""

    def test_empty_rules(self):
        """Test empty rules response."""
        response = ListPolicyRulesResponse(
            rules=[],
            total_count=0,
            engine_enabled=False,
        )
        assert len(response.rules) == 0
        assert response.engine_enabled is False

    def test_with_rules(self):
        """Test response with rules."""
        rules = [
            PolicyRuleInfo(
                name="test-policy",
                description="A test policy",
                tool="Test:*",
                enabled=True,
                priority=100,
                rules_count=1,
            )
        ]
        response = ListPolicyRulesResponse(
            rules=rules,
            total_count=1,
            engine_enabled=True,
        )
        assert len(response.rules) == 1
        assert response.rules[0].name == "test-policy"
        assert response.engine_enabled is True


class TestPolicyCheckRequest:
    """Tests for PolicyCheckRequest model."""

    def test_valid_request(self):
        """Test valid request structure."""
        request = PolicyCheckRequest(
            tool_name="Linear:create_issue",
            arguments={"title": "Test", "priority": 1},
        )
        assert request.tool_name == "Linear:create_issue"
        assert request.arguments["priority"] == 1

    def test_empty_arguments(self):
        """Test request with empty arguments."""
        request = PolicyCheckRequest(
            tool_name="Test:action",
            arguments={},
        )
        assert request.tool_name == "Test:action"
        assert request.arguments == {}


class TestPolicyRuleInfo:
    """Tests for PolicyRuleInfo model."""

    def test_rule_info_structure(self):
        """Test rule info structure."""
        info = PolicyRuleInfo(
            name="test-policy",
            description="A test policy for testing",
            tool="Linear:*",
            enabled=True,
            priority=100,
            rules_count=3,
        )
        assert info.name == "test-policy"
        assert info.tool == "Linear:*"
        assert info.priority == 100
        assert info.rules_count == 3

    def test_rule_info_disabled(self):
        """Test disabled rule info."""
        info = PolicyRuleInfo(
            name="disabled-policy",
            description="A disabled policy",
            tool="*:*",
            enabled=False,
            priority=0,
            rules_count=1,
        )
        assert info.enabled is False


# Note: Full API integration tests require authentication middleware mocking.
# The core policy engine logic is thoroughly tested in test_argument_policy.py.
# API response models are tested above to ensure correct contract.
