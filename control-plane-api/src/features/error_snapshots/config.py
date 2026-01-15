"""Error Snapshot feature configuration.

CAB-397: Configuration loaded from environment variables.
All settings have sensible defaults for development.
"""

import json
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .masking import MaskingConfig


class SnapshotSettings(BaseSettings):
    """Configuration for error snapshot feature.

    All settings can be overridden via environment variables
    with the STOA_SNAPSHOTS_ prefix.
    """

    model_config = SettingsConfigDict(
        env_prefix="STOA_SNAPSHOTS_",
        env_file=".env",
        extra="ignore",
    )

    # Feature flag
    enabled: bool = Field(
        default=True,
        description="Enable/disable error snapshot capture",
    )

    # Capture triggers
    capture_on_4xx: bool = Field(
        default=False,
        description="Capture snapshots on 4xx errors (can be noisy)",
    )
    capture_on_5xx: bool = Field(
        default=True,
        description="Capture snapshots on 5xx errors",
    )
    capture_on_timeout: bool = Field(
        default=True,
        description="Capture snapshots on timeout errors",
    )

    # Timeout threshold (ms) - requests longer than this are considered timeouts
    timeout_threshold_ms: int = Field(
        default=30000,
        description="Threshold in ms for timeout detection",
    )

    # Storage configuration
    storage_type: Literal["minio", "s3"] = Field(
        default="minio",
        description="Storage backend type",
    )
    storage_endpoint: str = Field(
        default="minio.stoa-system:9000",
        description="MinIO/S3 endpoint URL",
    )
    storage_bucket: str = Field(
        default="error-snapshots",
        description="Bucket name for snapshots",
    )
    storage_access_key: str = Field(
        default="",
        description="S3/MinIO access key",
    )
    storage_secret_key: str = Field(
        default="",
        description="S3/MinIO secret key",
    )
    storage_use_ssl: bool = Field(
        default=False,
        description="Use SSL for storage connection",
    )
    storage_region: str = Field(
        default="us-east-1",
        description="S3 region (ignored for MinIO)",
    )

    # Retention
    retention_days: int = Field(
        default=30,
        description="Days to retain snapshots before cleanup",
    )

    # Performance settings
    max_body_size: int = Field(
        default=10_000,
        description="Max body size in bytes to capture (truncate if larger)",
    )
    max_logs_per_snapshot: int = Field(
        default=100,
        description="Max log entries to capture per snapshot",
    )
    async_capture: bool = Field(
        default=True,
        description="Capture snapshots in background task (recommended)",
    )
    log_window_seconds: int = Field(
        default=5,
        description="Seconds before/after error to capture logs",
    )

    # Paths to exclude from capture
    exclude_paths: str = Field(
        default='["/health", "/metrics", "/ready", "/live", "/startup"]',
        description="JSON array of path prefixes to exclude from capture",
    )

    # Masking configuration (JSON string)
    masking_extra_headers: str = Field(
        default="[]",
        description="JSON array of additional headers to mask",
    )
    masking_extra_body_paths: str = Field(
        default="[]",
        description="JSON array of additional body paths to mask",
    )

    @field_validator("exclude_paths", mode="before")
    @classmethod
    def parse_exclude_paths(cls, v: str | list) -> str:
        """Ensure exclude_paths is stored as JSON string."""
        if isinstance(v, list):
            return json.dumps(v)
        return v

    @property
    def exclude_paths_list(self) -> list[str]:
        """Get exclude paths as a list."""
        try:
            return json.loads(self.exclude_paths)
        except json.JSONDecodeError:
            return []

    @property
    def masking_config(self) -> MaskingConfig:
        """Build masking config with any extra patterns."""
        config = MaskingConfig()

        # Add extra headers
        try:
            extra_headers = json.loads(self.masking_extra_headers)
            if extra_headers:
                config.headers.extend(extra_headers)
        except json.JSONDecodeError:
            pass

        # Add extra body paths
        try:
            extra_paths = json.loads(self.masking_extra_body_paths)
            if extra_paths:
                config.body_paths.extend(extra_paths)
        except json.JSONDecodeError:
            pass

        return config

    @property
    def storage_url(self) -> str:
        """Get full storage URL."""
        protocol = "https" if self.storage_use_ssl else "http"
        return f"{protocol}://{self.storage_endpoint}"


@lru_cache
def get_snapshot_settings() -> SnapshotSettings:
    """Get cached snapshot settings instance."""
    return SnapshotSettings()
