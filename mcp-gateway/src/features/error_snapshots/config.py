# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
MCP Error Snapshot Configuration
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSnapshotSettings(BaseSettings):
    """Configuration for MCP error snapshots"""

    model_config = SettingsConfigDict(
        env_prefix="MCP_SNAPSHOTS_",
        env_file=".env",
        extra="ignore",
    )

    # Feature flags
    enabled: bool = True
    capture_tool_errors: bool = True
    capture_server_errors: bool = True
    capture_llm_errors: bool = True
    capture_policy_errors: bool = True

    # Kafka configuration
    kafka_enabled: bool = True
    kafka_bootstrap_servers: str = "redpanda.stoa-system.svc.cluster.local:9092"
    kafka_topic: str = "stoa.errors.mcp-snapshots"

    # What to capture
    capture_on_4xx: bool = False  # Client errors (usually not useful)
    capture_on_5xx: bool = True   # Server errors
    capture_on_timeout: bool = True

    # PII masking
    mask_tool_params: bool = True
    mask_prompts: bool = True
    mask_headers: bool = True
    prompt_preview_length: int = 0  # 0 = no preview, >0 = first N chars

    # Sensitive parameter patterns to always mask
    sensitive_params: list[str] = [
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "private_key",
        "access_token",
        "refresh_token",
        "ssn",
        "credit_card",
        "card_number",
    ]

    # Sensitive headers to mask
    sensitive_headers: list[str] = [
        "authorization",
        "x-api-key",
        "cookie",
        "x-auth-token",
        "x-access-token",
    ]

    # Performance
    async_capture: bool = True
    max_response_preview_length: int = 500

    # Retention (informational, actual retention managed by Kafka)
    retention_days: int = 90  # Longer than gateway snapshots for cost analysis

    # Paths to exclude from capture
    exclude_paths: list[str] = [
        "/health",
        "/health/live",
        "/health/ready",
        "/health/startup",
        "/metrics",
    ]


@lru_cache
def get_mcp_snapshot_settings() -> MCPSnapshotSettings:
    """Get cached MCP snapshot settings"""
    return MCPSnapshotSettings()
