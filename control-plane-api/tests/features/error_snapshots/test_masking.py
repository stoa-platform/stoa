# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for PII masking in error snapshots.

CAB-397: Ensures sensitive data is properly redacted.
"""

import pytest

from src.features.error_snapshots.masking import (
    MaskingConfig,
    PIIMasker,
    mask_request,
)


class TestPIIMasker:
    """Tests for PIIMasker class."""

    def test_mask_authorization_header(self):
        """Authorization header should be masked."""
        headers = {"Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."}
        masker = PIIMasker()

        masked, masked_keys = masker.mask_headers(headers)

        assert masked["Authorization"] == "[REDACTED]"
        assert "headers.Authorization" in masked_keys

    def test_mask_multiple_sensitive_headers(self):
        """Multiple sensitive headers should be masked."""
        headers = {
            "Authorization": "Bearer token123",
            "X-API-Key": "secret-key",
            "Cookie": "session=abc123",
            "Content-Type": "application/json",
        }
        masker = PIIMasker()

        masked, masked_keys = masker.mask_headers(headers)

        assert masked["Authorization"] == "[REDACTED]"
        assert masked["X-API-Key"] == "[REDACTED]"
        assert masked["Cookie"] == "[REDACTED]"
        assert masked["Content-Type"] == "application/json"
        assert len(masked_keys) == 3

    def test_mask_password_in_body(self):
        """Password field in body should be masked."""
        body = {"username": "john", "password": "super_secret"}
        masker = PIIMasker()

        masked, masked_keys = masker.mask_body(body)

        assert masked["username"] == "john"
        assert masked["password"] == "[REDACTED]"
        assert "body.password" in masked_keys

    def test_mask_nested_password(self):
        """Nested password fields should be masked."""
        body = {
            "user": {
                "name": "john",
                "credentials": {
                    "password": "secret123",
                    "api_key": "key456",
                },
            }
        }
        masker = PIIMasker()

        masked, masked_keys = masker.mask_body(body)

        assert masked["user"]["name"] == "john"
        assert masked["user"]["credentials"]["password"] == "[REDACTED]"
        assert masked["user"]["credentials"]["api_key"] == "[REDACTED]"
        assert len(masked_keys) == 2

    def test_mask_token_fields(self):
        """Token-related fields should be masked."""
        body = {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4...",
            "token": "simple_token",
        }
        masker = PIIMasker()

        masked, masked_keys = masker.mask_body(body)

        assert masked["access_token"] == "[REDACTED]"
        assert masked["refresh_token"] == "[REDACTED]"
        assert masked["token"] == "[REDACTED]"
        assert len(masked_keys) == 3

    def test_mask_credit_card_fields(self):
        """Credit card fields should be masked."""
        body = {
            "card_number": "4111-1111-1111-1111",
            "cvv": "123",
            "amount": 100.00,
        }
        masker = PIIMasker()

        masked, masked_keys = masker.mask_body(body)

        assert masked["card_number"] == "[REDACTED]"
        assert masked["cvv"] == "[REDACTED]"
        assert masked["amount"] == 100.00

    def test_mask_email_in_string_value(self):
        """Email patterns in string values should be masked."""
        body = {"message": "Contact user@example.com for support"}
        masker = PIIMasker()

        masked, masked_keys = masker.mask_body(body)

        assert masked["message"] == "[REDACTED]"

    def test_mask_credit_card_pattern(self):
        """Credit card number patterns should be masked."""
        body = {"note": "Card ending in 4111 1111 1111 1111 was used"}
        masker = PIIMasker()

        masked, masked_keys = masker.mask_body(body)

        assert masked["note"] == "[REDACTED]"

    def test_mask_ssn_pattern(self):
        """SSN patterns should be masked."""
        body = {"info": "SSN: 123-45-6789"}
        masker = PIIMasker()

        masked, masked_keys = masker.mask_body(body)

        assert masked["info"] == "[REDACTED]"

    def test_mask_list_items(self):
        """Items in lists should be masked."""
        body = {
            "users": [
                {"name": "Alice", "password": "alice123"},
                {"name": "Bob", "password": "bob456"},
            ]
        }
        masker = PIIMasker()

        masked, masked_keys = masker.mask_body(body)

        assert masked["users"][0]["name"] == "Alice"
        assert masked["users"][0]["password"] == "[REDACTED]"
        assert masked["users"][1]["password"] == "[REDACTED]"
        assert len(masked_keys) == 2

    def test_mask_query_params(self):
        """Sensitive query parameters should be masked."""
        params = {"token": "secret123", "page": "1", "api_key": "key456"}
        masker = PIIMasker()

        masked, masked_keys = masker.mask_query_params(params)

        assert masked["token"] == "[REDACTED]"
        assert masked["page"] == "1"
        assert masked["api_key"] == "[REDACTED]"
        assert len(masked_keys) == 2

    def test_mask_none_body(self):
        """None body should return None."""
        masker = PIIMasker()

        masked, masked_keys = masker.mask_body(None)

        assert masked is None
        assert len(masked_keys) == 0

    def test_mask_none_query_params(self):
        """None query params should return None."""
        masker = PIIMasker()

        masked, masked_keys = masker.mask_query_params(None)

        assert masked is None
        assert len(masked_keys) == 0

    def test_custom_masking_config(self):
        """Custom masking config should work."""
        config = MaskingConfig(
            headers=["x-custom-secret"],
            body_paths=["my_secret_field"],
            redacted_value="***",
        )
        masker = PIIMasker(config)

        headers = {"X-Custom-Secret": "value", "Authorization": "Bearer token"}
        body = {"my_secret_field": "secret", "password": "pass"}

        masked_h, masked_h_keys = masker.mask_headers(headers)
        masked_b, masked_b_keys = masker.mask_body(body)

        # Custom header masked
        assert masked_h["X-Custom-Secret"] == "***"
        # Default header NOT masked (only custom config)
        assert masked_h["Authorization"] == "Bearer token"
        # Custom field masked
        assert masked_b["my_secret_field"] == "***"
        # Default field NOT masked
        assert masked_b["password"] == "pass"

    def test_deep_nesting_protection(self):
        """Deep nesting should be handled without stack overflow."""
        # Build deeply nested structure
        body = {"level": 0}
        current = body
        for i in range(1, 30):
            current["nested"] = {"level": i}
            current = current["nested"]
        current["password"] = "secret"

        config = MaskingConfig(max_depth=25)
        masker = PIIMasker(config)

        # Should not raise
        masked, _ = masker.mask_body(body)

        # Check structure is preserved
        assert masked["level"] == 0
        assert "nested" in masked


class TestMaskRequestFunction:
    """Tests for the convenience mask_request function."""

    def test_mask_request_complete(self):
        """Full request masking should work."""
        headers = {"Authorization": "Bearer token", "Content-Type": "application/json"}
        body = {"username": "john", "password": "secret", "data": {"token": "abc"}}
        query = {"api_key": "key123", "page": "1"}

        masked_h, masked_b, masked_q, all_masked = mask_request(headers, body, query)

        assert masked_h["Authorization"] == "[REDACTED]"
        assert masked_h["Content-Type"] == "application/json"
        assert masked_b["username"] == "john"
        assert masked_b["password"] == "[REDACTED]"
        assert masked_b["data"]["token"] == "[REDACTED]"
        assert masked_q["api_key"] == "[REDACTED]"
        assert masked_q["page"] == "1"

        assert "headers.Authorization" in all_masked
        assert "body.password" in all_masked
        assert "body.data.token" in all_masked
        assert "query.api_key" in all_masked

    def test_mask_request_without_query(self):
        """Request without query params should work."""
        headers = {"Authorization": "Bearer token"}
        body = {"password": "secret"}

        masked_h, masked_b, masked_q, all_masked = mask_request(headers, body)

        assert masked_q is None
        assert len(all_masked) == 2

    def test_mask_request_with_custom_config(self):
        """Custom config should be respected."""
        config = MaskingConfig(
            headers=["x-custom"],
            body_paths=["custom_field"],
            redacted_value="HIDDEN",
        )

        headers = {"X-Custom": "value", "Authorization": "token"}
        body = {"custom_field": "secret", "password": "pass"}

        masked_h, masked_b, _, _ = mask_request(headers, body, config=config)

        assert masked_h["X-Custom"] == "HIDDEN"
        assert masked_h["Authorization"] == "token"  # Not in custom config
        assert masked_b["custom_field"] == "HIDDEN"
        assert masked_b["password"] == "pass"  # Not in custom config
