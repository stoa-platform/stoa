# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
PII Masking for MCP Error Snapshots

Masks sensitive data in tool parameters, headers, and LLM prompts.
"""

import re
from typing import Any

from .config import get_mcp_snapshot_settings

REDACTED = "[REDACTED]"


def mask_dict_value(value: Any, depth: int = 0, max_depth: int = 5) -> Any:
    """Recursively mask sensitive values in a dict"""
    if depth > max_depth:
        return REDACTED

    if isinstance(value, dict):
        return {k: mask_dict_value(v, depth + 1) for k, v in value.items()}
    elif isinstance(value, list):
        return [mask_dict_value(item, depth + 1) for item in value]
    elif isinstance(value, str):
        return mask_string(value)
    else:
        return value


def mask_string(value: str) -> str:
    """Mask potentially sensitive strings"""
    if not value:
        return value

    # Email pattern - keep domain
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    value = re.sub(email_pattern, lambda m: f"***@{m.group().split('@')[1]}", value)

    # Credit card pattern
    cc_pattern = r'\b(?:\d{4}[-\s]?){3}\d{4}\b'
    value = re.sub(cc_pattern, "****-****-****-****", value)

    # SSN pattern
    ssn_pattern = r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'
    value = re.sub(ssn_pattern, "***-**-****", value)

    # API key patterns (stoa_sk_*, sk-*, etc.)
    api_key_pattern = r'\b(stoa_sk_|sk-|api_|key_)[A-Za-z0-9_-]{10,}\b'
    value = re.sub(api_key_pattern, lambda m: f"{m.group()[:8]}...{REDACTED}", value)

    # JWT pattern (just mask the signature)
    jwt_pattern = r'\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'
    value = re.sub(jwt_pattern, "eyJ...[JWT_REDACTED]", value)

    return value


def mask_tool_params(params: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Mask sensitive parameters in tool invocation.

    Returns:
        Tuple of (masked_params, list_of_masked_keys)
    """
    settings = get_mcp_snapshot_settings()
    masked = {}
    masked_keys = []

    sensitive_lower = [p.lower() for p in settings.sensitive_params]

    for key, value in params.items():
        key_lower = key.lower()

        # Check if key matches sensitive patterns
        is_sensitive = any(
            pattern in key_lower
            for pattern in sensitive_lower
        )

        if is_sensitive:
            masked[key] = REDACTED
            masked_keys.append(key)
        elif isinstance(value, dict):
            # Recursively mask nested dicts
            nested_masked, nested_keys = mask_tool_params(value)
            masked[key] = nested_masked
            masked_keys.extend([f"{key}.{k}" for k in nested_keys])
        elif isinstance(value, str):
            masked[key] = mask_string(value)
            if masked[key] != value:
                masked_keys.append(key)
        else:
            masked[key] = value

    return masked, masked_keys


def mask_headers(headers: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """
    Mask sensitive HTTP headers.

    Returns:
        Tuple of (masked_headers, list_of_masked_keys)
    """
    settings = get_mcp_snapshot_settings()
    masked = {}
    masked_keys = []

    sensitive_lower = [h.lower() for h in settings.sensitive_headers]

    for key, value in headers.items():
        key_lower = key.lower()

        if key_lower in sensitive_lower:
            masked[key] = REDACTED
            masked_keys.append(f"headers.{key}")
        else:
            masked[key] = mask_string(value)

    return masked, masked_keys


def mask_prompt(prompt: str, include_preview: bool = False) -> dict[str, Any]:
    """
    Mask LLM prompt content.

    Returns dict with:
        - length: Character count
        - hash: SHA256 hash for correlation
        - preview: First N chars (if include_preview=True)
    """
    from .models import MCPErrorSnapshot

    settings = get_mcp_snapshot_settings()

    result = {
        "length": len(prompt),
        "hash": MCPErrorSnapshot.generate_prompt_hash(prompt),
    }

    if include_preview and settings.prompt_preview_length > 0:
        preview_len = min(settings.prompt_preview_length, len(prompt))
        result["preview"] = prompt[:preview_len] + ("..." if len(prompt) > preview_len else "")

    return result


def mask_url(url: str) -> str:
    """Mask credentials in URLs"""
    # Pattern: https://user:pass@host
    auth_pattern = r'(https?://)([^:]+):([^@]+)@'
    return re.sub(auth_pattern, r'\1***:***@', url)


def mask_error_message(message: str) -> str:
    """Mask potentially sensitive data in error messages"""
    return mask_string(message)
