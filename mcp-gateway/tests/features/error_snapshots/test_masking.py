# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for MCP PII masking."""

import pytest

from src.features.error_snapshots.masking import (
    mask_tool_params,
    mask_headers,
    mask_string,
    mask_prompt,
    mask_url,
    mask_error_message,
    REDACTED,
)


class TestMaskToolParams:
    """Tests for tool parameter masking."""

    def test_mask_password(self):
        """Test password is masked."""
        params = {"username": "john", "password": "secret123"}
        masked, keys = mask_tool_params(params)
        assert masked["username"] == "john"
        assert masked["password"] == REDACTED
        assert "password" in keys

    def test_mask_api_key(self):
        """Test API key is masked."""
        params = {"api_key": "sk-abc123xyz789"}
        masked, keys = mask_tool_params(params)
        assert masked["api_key"] == REDACTED
        assert "api_key" in keys

    def test_mask_nested_sensitive(self):
        """Test nested sensitive fields are masked."""
        params = {
            "config": {
                "api_key": "secret",
                "endpoint": "https://api.example.com",
            }
        }
        masked, keys = mask_tool_params(params)
        assert masked["config"]["api_key"] == REDACTED
        assert masked["config"]["endpoint"] == "https://api.example.com"
        assert "config.api_key" in keys

    def test_mask_token_variations(self):
        """Test various token field names are masked."""
        params = {
            "access_token": "abc123",
            "refresh_token": "xyz789",
            "auth_token": "def456",
        }
        masked, keys = mask_tool_params(params)
        assert all(v == REDACTED for v in masked.values())
        assert len(keys) == 3

    def test_preserve_non_sensitive(self):
        """Test non-sensitive fields are preserved."""
        params = {
            "repo": "org/project",
            "title": "Bug report",
            "labels": ["bug", "urgent"],
        }
        masked, keys = mask_tool_params(params)
        assert masked == params
        assert len(keys) == 0


class TestMaskString:
    """Tests for string masking."""

    def test_mask_email(self):
        """Test email is partially masked."""
        result = mask_string("Contact john.doe@example.com for help")
        assert "***@example.com" in result
        assert "john.doe" not in result

    def test_mask_credit_card(self):
        """Test credit card is masked."""
        result = mask_string("Card: 4111-1111-1111-1111")
        assert "****-****-****-****" in result
        assert "4111" not in result

    def test_mask_ssn(self):
        """Test SSN is masked."""
        result = mask_string("SSN: 123-45-6789")
        assert "***-**-****" in result
        assert "123" not in result

    def test_mask_api_key_in_string(self):
        """Test API key in string is masked."""
        result = mask_string("API key: stoa_sk_abcdef1234567890")
        assert "stoa_sk_" in result
        assert REDACTED in result
        assert "abcdef1234567890" not in result

    def test_mask_jwt(self):
        """Test JWT is masked."""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = mask_string(f"Token: {jwt}")
        assert "JWT_REDACTED" in result
        assert "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U" not in result

    def test_preserve_normal_string(self):
        """Test normal strings are preserved."""
        text = "This is a normal string without sensitive data"
        result = mask_string(text)
        assert result == text


class TestMaskHeaders:
    """Tests for header masking."""

    def test_mask_authorization(self):
        """Test Authorization header is masked."""
        headers = {"Authorization": "Bearer eyJ..."}
        masked, keys = mask_headers(headers)
        assert masked["Authorization"] == REDACTED
        assert "headers.Authorization" in keys

    def test_mask_api_key_header(self):
        """Test X-API-Key header is masked."""
        headers = {"X-API-Key": "sk-secret123"}
        masked, keys = mask_headers(headers)
        assert masked["X-API-Key"] == REDACTED

    def test_mask_cookie(self):
        """Test Cookie header is masked."""
        headers = {"Cookie": "session=abc123"}
        masked, keys = mask_headers(headers)
        assert masked["Cookie"] == REDACTED

    def test_preserve_safe_headers(self):
        """Test safe headers are preserved."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "test-client/1.0",
        }
        masked, keys = mask_headers(headers)
        assert masked == headers
        assert len(keys) == 0


class TestMaskPrompt:
    """Tests for prompt masking."""

    def test_mask_prompt_basic(self):
        """Test basic prompt masking returns length and hash."""
        prompt = "Help me create a GitHub issue for the bug"
        result = mask_prompt(prompt)
        assert result["length"] == len(prompt)
        assert result["hash"].startswith("sha256:")
        assert "preview" not in result

    def test_mask_prompt_with_preview(self):
        """Test prompt masking with preview enabled."""
        prompt = "Help me create a GitHub issue for the bug"
        result = mask_prompt(prompt, include_preview=True)
        # Preview depends on settings.prompt_preview_length
        # By default it's 0, so no preview
        assert result["length"] == len(prompt)


class TestMaskUrl:
    """Tests for URL masking."""

    def test_mask_url_with_credentials(self):
        """Test URL with credentials is masked."""
        url = "https://user:password@api.example.com/v1"
        result = mask_url(url)
        assert "***:***@" in result
        assert "password" not in result

    def test_preserve_url_without_credentials(self):
        """Test URL without credentials is preserved."""
        url = "https://api.example.com/v1"
        result = mask_url(url)
        assert result == url


class TestMaskErrorMessage:
    """Tests for error message masking."""

    def test_mask_sensitive_in_error(self):
        """Test sensitive data in error message is masked."""
        error = "Authentication failed for user@example.com with token sk-abc123456789"
        result = mask_error_message(error)
        assert "***@example.com" in result
        assert "sk-abc123456789" not in result

    def test_preserve_normal_error(self):
        """Test normal error message is preserved."""
        error = "Connection timeout after 30 seconds"
        result = mask_error_message(error)
        assert result == error
