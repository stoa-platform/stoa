# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""PII masking for error snapshots.

CAB-397: Ensures sensitive data is redacted before storage.
Tracks masked fields for audit purposes.
"""

import copy
import re
from typing import Any

from pydantic import BaseModel, Field


class MaskingConfig(BaseModel):
    """Configuration for PII masking."""

    # Headers to redact (case-insensitive)
    headers: list[str] = Field(
        default=[
            "authorization",
            "x-api-key",
            "x-auth-token",
            "cookie",
            "set-cookie",
            "x-csrf-token",
            "proxy-authorization",
            "x-amz-security-token",
            "x-forwarded-authorization",
        ]
    )

    # JSON body paths to redact (dot notation, case-insensitive)
    body_paths: list[str] = Field(
        default=[
            "password",
            "passwd",
            "secret",
            "token",
            "access_token",
            "refresh_token",
            "id_token",
            "api_key",
            "apikey",
            "api-key",
            "private_key",
            "privatekey",
            "credit_card",
            "creditcard",
            "card_number",
            "cardnumber",
            "cvv",
            "cvc",
            "ssn",
            "social_security",
            "pin",
            "otp",
            "auth_code",
            "verification_code",
        ]
    )

    # Regex patterns for values (applied to all string values)
    patterns: list[str] = Field(
        default=[
            # Email addresses
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            # Credit card numbers (with or without spaces/dashes)
            r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
            # SSN (US format)
            r"\b\d{3}-\d{2}-\d{4}\b",
            # JWT tokens (header.payload.signature)
            r"\beyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\b",
            # AWS access key IDs
            r"\bAKIA[0-9A-Z]{16}\b",
            # Generic API keys (long alphanumeric strings)
            r"\b[a-zA-Z0-9]{32,}\b",
        ]
    )

    # Replacement value
    redacted_value: str = "[REDACTED]"

    # Maximum depth for recursive masking (prevent stack overflow)
    max_depth: int = 20


class PIIMasker:
    """Masks sensitive data in snapshots.

    Supports:
    - Header redaction by name
    - Body field redaction by path
    - Regex-based value redaction
    - Recursive nested structure handling
    - Tracking of masked fields for audit
    """

    def __init__(self, config: MaskingConfig | None = None):
        self.config = config or MaskingConfig()
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.config.patterns
        ]
        self._headers_lower = {h.lower() for h in self.config.headers}
        self._body_paths_lower = {p.lower() for p in self.config.body_paths}

    def mask_headers(
        self, headers: dict[str, str]
    ) -> tuple[dict[str, str], list[str]]:
        """Mask sensitive headers.

        Args:
            headers: HTTP headers dictionary

        Returns:
            Tuple of (masked_headers, list of masked header paths)
        """
        masked = {}
        masked_keys = []

        for key, value in headers.items():
            if key.lower() in self._headers_lower:
                masked[key] = self.config.redacted_value
                masked_keys.append(f"headers.{key}")
            else:
                masked[key] = value

        return masked, masked_keys

    def mask_body(
        self, body: Any, path: str = "", depth: int = 0
    ) -> tuple[Any, list[str]]:
        """Recursively mask sensitive fields in body.

        Args:
            body: Request/response body (dict, list, or primitive)
            path: Current path in the structure (for tracking)
            depth: Current recursion depth

        Returns:
            Tuple of (masked_body, list of masked paths)
        """
        if body is None:
            return None, []

        # Prevent stack overflow on deeply nested structures
        if depth > self.config.max_depth:
            return body, []

        masked_paths: list[str] = []

        if isinstance(body, dict):
            masked = {}
            for key, value in body.items():
                current_path = f"{path}.{key}" if path else key

                # Check if key matches sensitive paths
                if key.lower() in self._body_paths_lower:
                    masked[key] = self.config.redacted_value
                    full_path = f"body.{current_path}" if path else f"body.{key}"
                    masked_paths.append(full_path)
                else:
                    # Recurse into nested structures
                    masked_value, nested_paths = self.mask_body(
                        value, current_path, depth + 1
                    )
                    masked[key] = masked_value
                    masked_paths.extend(nested_paths)

            return masked, masked_paths

        elif isinstance(body, list):
            masked = []
            for i, item in enumerate(body):
                current_path = f"{path}[{i}]"
                masked_item, nested_paths = self.mask_body(item, current_path, depth + 1)
                masked.append(masked_item)
                masked_paths.extend(nested_paths)

            return masked, masked_paths

        elif isinstance(body, str):
            # Check regex patterns for sensitive values
            masked_value = body
            for pattern in self._compiled_patterns:
                if pattern.search(masked_value):
                    masked_value = self.config.redacted_value
                    if path:
                        masked_paths.append(f"body.{path}")
                    break

            return masked_value, masked_paths

        else:
            # Numbers, bools, etc. - return as-is
            return body, []

    def mask_query_params(
        self, params: dict[str, str] | None
    ) -> tuple[dict[str, str] | None, list[str]]:
        """Mask sensitive query parameters.

        Args:
            params: Query parameters dictionary

        Returns:
            Tuple of (masked_params, list of masked param paths)
        """
        if not params:
            return None, []

        masked = {}
        masked_paths = []

        for key, value in params.items():
            if key.lower() in self._body_paths_lower:
                masked[key] = self.config.redacted_value
                masked_paths.append(f"query.{key}")
            else:
                # Also check value against patterns
                masked_value = value
                for pattern in self._compiled_patterns:
                    if pattern.search(str(value)):
                        masked_value = self.config.redacted_value
                        masked_paths.append(f"query.{key}")
                        break
                masked[key] = masked_value

        return masked, masked_paths

    def mask_snapshot_data(
        self,
        headers: dict[str, str],
        body: Any,
        query_params: dict[str, str] | None = None,
    ) -> tuple[dict[str, str], Any, dict[str, str] | None, list[str]]:
        """Mask all sensitive data in a request/response.

        Args:
            headers: HTTP headers
            body: Request/response body
            query_params: URL query parameters

        Returns:
            Tuple of (masked_headers, masked_body, masked_query_params, all_masked_fields)
        """
        all_masked: list[str] = []

        # Mask headers
        masked_headers, header_paths = self.mask_headers(headers)
        all_masked.extend(header_paths)

        # Mask body (deep copy to avoid mutating original)
        masked_body, body_paths = self.mask_body(copy.deepcopy(body))
        all_masked.extend(body_paths)

        # Mask query params
        masked_params, param_paths = self.mask_query_params(query_params)
        all_masked.extend(param_paths)

        return masked_headers, masked_body, masked_params, all_masked


# Singleton instance with default config
default_masker = PIIMasker()


def mask_request(
    headers: dict[str, str],
    body: Any,
    query_params: dict[str, str] | None = None,
    config: MaskingConfig | None = None,
) -> tuple[dict[str, str], Any, dict[str, str] | None, list[str]]:
    """Convenience function for masking request data.

    Args:
        headers: HTTP headers
        body: Request body
        query_params: URL query parameters
        config: Optional custom masking config

    Returns:
        Tuple of (masked_headers, masked_body, masked_query_params, masked_fields)
    """
    masker = PIIMasker(config) if config else default_masker
    return masker.mask_snapshot_data(headers, body, query_params)
