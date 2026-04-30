"""Error Snapshot feature configuration.

CAB-397: Configuration loaded from environment variables.
CAB-2199 / INFRA-1a S6: env prefix renamed from ``STOA_SNAPSHOTS_`` (plural)
to ``STOA_API_SNAPSHOT_`` (singular + ``_API_`` scope) to disambiguate from
the unrelated ``STOA_SNAPSHOT_*`` (singular, in-process ring buffer) on the
Rust gateway. Legacy prefix is honored as a per-field ``AliasChoices`` for
one release, with deprecation warning + Prometheus metric. Setting both
prefixes for the same field with different values fails boot — the conflict
scanner reads from BOTH process env and the dotenv file.

All settings have sensible defaults for development.
"""

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import ClassVar, Literal

from prometheus_client import Counter
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .masking import MaskingConfig

logger = logging.getLogger(__name__)

# Counter name — Prometheus client_python AUTO-APPENDS `_total` to the exposed
# metric for Counters. Pass the bare name to the constructor; the exposition
# layer adds the suffix. Final exposed name: stoa_deprecated_config_used_total.
DEPRECATED_CONFIG_USED = Counter(
    "stoa_deprecated_config_used",
    "Deprecated config keys observed at startup (label: name = legacy env key).",
    ["name"],
)

# One-shot guard: increment Counter at most once per (key, process) so that
# get_snapshot_settings() being called multiple times — or SnapshotSettings()
# being instantiated in test fixtures — does not double-count.
_METRIC_EMITTED_KEYS: set[str] = set()
_METRIC_LOCK = Lock()

# Prefixes — old (legacy, plural) and new (canonical, singular + _API_ scope).
_OLD_PREFIX = "STOA_SNAPSHOTS_"
_NEW_PREFIX = "STOA_API_SNAPSHOT_"

# Council Stage 2 #1+#2 — values for env keys carrying secrets are redacted
# before they enter any error message or log line. Substring match on the
# env-var name; deliberately conservative (false positives = mask a
# non-secret = harmless; false negatives = leak a secret = unacceptable).
_SECRET_NAME_TOKENS: tuple[str, ...] = (
    "SECRET",
    "KEY",
    "TOKEN",
    "PASSWORD",
)


def _is_secret_env_key(env_key: str) -> bool:
    """True if the env-var name suggests it carries a secret value."""
    upper = env_key.upper()
    return any(token in upper for token in _SECRET_NAME_TOKENS)


def _redact_value(env_key: str, value: str) -> str:
    """Return ``value`` if ``env_key`` is non-secret, else ``"<REDACTED>"``."""
    return "<REDACTED>" if _is_secret_env_key(env_key) else value


def _read_dotenv(path: Path | str) -> dict[str, str]:
    """Minimal dotenv parser for the conflict-detection layer.

    pydantic-settings handles dotenv internally for field resolution; here we
    re-parse it ONLY to scan for legacy-prefix conflicts that would otherwise
    be invisible to ``os.environ``. Best-effort: lines like ``KEY=value``
    (whitespace ignored, comments stripped, no shell expansion).
    """
    p = Path(path)
    if not p.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Strip surrounding quotes — best-effort, not POSIX-quote-correct.
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def _alias(field: str) -> AliasChoices:
    """Build the (new, old) AliasChoices pair for a snapshot field."""
    return AliasChoices(f"{_NEW_PREFIX}{field}", f"{_OLD_PREFIX}{field}")


class SnapshotSettings(BaseSettings):
    """Configuration for error snapshot feature.

    Canonical env prefix: ``STOA_API_SNAPSHOT_*`` (revision v2 — was
    ``STOA_SNAPSHOTS_*``). Legacy prefix is honored as a per-field
    ``AliasChoices`` for one release, with deprecation warning + Prometheus
    metric. Setting both prefixes for the same field with different values
    fails boot — the conflict scanner reads from BOTH process env and dotenv.

    Secret values are never logged or surfaced in error messages. The conflict
    scanner redacts values for env keys whose name matches the secret heuristic
    (``*SECRET*``, ``*KEY*``, ``*TOKEN*``, ``*PASSWORD*``).
    """

    model_config = SettingsConfigDict(
        env_prefix=_NEW_PREFIX,
        env_file=".env",
        extra="ignore",
        populate_by_name=True,  # required for AliasChoices to fire
    )

    # Schema metadata for INFRA-1c cross-repo-config-coverage CI gate.
    DEPRECATED_PREFIX_ALIASES: ClassVar[dict[str, str]] = {
        _OLD_PREFIX: _NEW_PREFIX,
    }

    # Feature flag
    enabled: bool = Field(
        default=True,
        description="Enable/disable error snapshot capture",
        validation_alias=_alias("ENABLED"),
    )

    # Capture triggers
    capture_on_4xx: bool = Field(
        default=False,
        description="Capture snapshots on 4xx errors (can be noisy)",
        validation_alias=_alias("CAPTURE_ON_4XX"),
    )
    capture_on_5xx: bool = Field(
        default=True,
        description="Capture snapshots on 5xx errors",
        validation_alias=_alias("CAPTURE_ON_5XX"),
    )
    capture_on_timeout: bool = Field(
        default=True,
        description="Capture snapshots on timeout errors",
        validation_alias=_alias("CAPTURE_ON_TIMEOUT"),
    )

    # Timeout threshold (ms) - requests longer than this are considered timeouts
    timeout_threshold_ms: int = Field(
        default=30000,
        description="Threshold in ms for timeout detection",
        validation_alias=_alias("TIMEOUT_THRESHOLD_MS"),
    )

    # Storage configuration
    storage_type: Literal["minio", "s3"] = Field(
        default="minio",
        description="Storage backend type",
        validation_alias=_alias("STORAGE_TYPE"),
    )
    storage_endpoint: str = Field(
        default="minio.stoa-system:9000",
        description="MinIO/S3 endpoint URL",
        validation_alias=_alias("STORAGE_ENDPOINT"),
    )
    storage_bucket: str = Field(
        default="error-snapshots",
        description="Bucket name for snapshots",
        validation_alias=_alias("STORAGE_BUCKET"),
    )
    storage_access_key: str = Field(
        default="",
        description="S3/MinIO access key",
        validation_alias=_alias("STORAGE_ACCESS_KEY"),
    )
    storage_secret_key: str = Field(
        default="",
        description="S3/MinIO secret key",
        validation_alias=_alias("STORAGE_SECRET_KEY"),
    )
    storage_use_ssl: bool = Field(
        default=False,
        description="Use SSL for storage connection",
        validation_alias=_alias("STORAGE_USE_SSL"),
    )
    storage_region: str = Field(
        default="us-east-1",
        description="S3 region (ignored for MinIO)",
        validation_alias=_alias("STORAGE_REGION"),
    )

    # Retention
    retention_days: int = Field(
        default=30,
        description="Days to retain snapshots before cleanup",
        validation_alias=_alias("RETENTION_DAYS"),
    )

    # Performance settings
    max_body_size: int = Field(
        default=10_000,
        description="Max body size in bytes to capture (truncate if larger)",
        validation_alias=_alias("MAX_BODY_SIZE"),
    )
    max_logs_per_snapshot: int = Field(
        default=100,
        description="Max log entries to capture per snapshot",
        validation_alias=_alias("MAX_LOGS_PER_SNAPSHOT"),
    )
    async_capture: bool = Field(
        default=True,
        description="Capture snapshots in background task (recommended)",
        validation_alias=_alias("ASYNC_CAPTURE"),
    )
    log_window_seconds: int = Field(
        default=5,
        description="Seconds before/after error to capture logs",
        validation_alias=_alias("LOG_WINDOW_SECONDS"),
    )

    # Paths to exclude from capture
    exclude_paths: str = Field(
        default='["/health", "/metrics", "/ready", "/live", "/startup"]',
        description="JSON array of path prefixes to exclude from capture",
        validation_alias=_alias("EXCLUDE_PATHS"),
    )

    # Masking configuration (JSON string)
    masking_extra_headers: str = Field(
        default="[]",
        description="JSON array of additional headers to mask",
        validation_alias=_alias("MASKING_EXTRA_HEADERS"),
    )
    masking_extra_body_paths: str = Field(
        default="[]",
        description="JSON array of additional body paths to mask",
        validation_alias=_alias("MASKING_EXTRA_BODY_PATHS"),
    )

    @model_validator(mode="before")
    @classmethod
    def _detect_conflicts_and_emit_deprecation(cls, values: object) -> object:
        """Scan BOTH process env AND dotenv for legacy-prefix usage.

        - Process env: ``os.environ``.
        - Dotenv: parse the configured ``env_file`` (default ``.env``) — does
          NOT depend on whether pydantic-settings has already merged it.

        Conflict (same suffix, different value across old/new prefix in any
        source) raises ValueError with secret-aware redaction. Otherwise emits
        deprecation log (KEYS only, never values) + Counter increment
        (one-shot per key per process).
        """
        env_file_path = cls.model_config.get("env_file") or ".env"
        sources: list[tuple[str, dict[str, str]]] = [
            ("env", dict(os.environ)),
            ("dotenv", _read_dotenv(env_file_path)),
        ]

        # Collect all (suffix → {source_key: value}) where suffix is the
        # field-name tail after either prefix.
        seen: dict[str, dict[str, str]] = {}
        for source_label, source_map in sources:
            for env_key, env_value in source_map.items():
                if env_key.startswith(_OLD_PREFIX):
                    suffix = env_key[len(_OLD_PREFIX):]
                    seen.setdefault(suffix, {})[f"{source_label}:{env_key}"] = env_value
                elif env_key.startswith(_NEW_PREFIX):
                    suffix = env_key[len(_NEW_PREFIX):]
                    seen.setdefault(suffix, {})[f"{source_label}:{env_key}"] = env_value

        deprecated_keys_emitted: list[str] = []
        for suffix, source_values in seen.items():
            distinct_values = set(source_values.values())
            if len(distinct_values) > 1:
                # Conflict — multiple sources disagree.
                # Council Stage 2 #1+#2: redact values for secret-name keys
                # before assembling the error message. The env-var name itself
                # is not a secret — only its value is.
                redacted_sources = {
                    sk: _redact_value(sk.split(":", 1)[1], sv)
                    for sk, sv in source_values.items()
                }
                # Also scrub any secret-bearing key in the input ``values``
                # dict so Pydantic's ValidationError ``input_value=`` dump —
                # which it appends verbatim to ``str(e)`` — does not leak the
                # raw secret. Mutation is acceptable here because we are
                # about to raise; the model never sees the redacted dict
                # successfully.
                if isinstance(values, dict):
                    for k in list(values.keys()):
                        if _is_secret_env_key(k):
                            values[k] = "<REDACTED>"
                raise ValueError(
                    f"Conflicting config for suffix {suffix!r}: "
                    f"{redacted_sources!r}. Resolve before boot — the legacy "
                    f"{_OLD_PREFIX}* prefix is deprecated."
                )
            # Track legacy-prefix usage for metric/log (independent of conflict).
            for source_key in source_values:
                if _OLD_PREFIX in source_key:
                    deprecated_keys_emitted.append(source_key.split(":", 1)[1])

        if deprecated_keys_emitted:
            with _METRIC_LOCK:
                for key in deprecated_keys_emitted:
                    if key not in _METRIC_EMITTED_KEYS:
                        DEPRECATED_CONFIG_USED.labels(name=key).inc()
                        _METRIC_EMITTED_KEYS.add(key)
            # Council Stage 2 #1+#2 contract: this log line emits KEYS only
            # (never values). If the format ever changes to include values,
            # apply ``_redact_value`` per-key to honor the masking guarantee.
            logger.warning(
                "Deprecated config prefix %s used (keys: %s). "
                "Rename to %s before next release. Tracked: CAB-2199 / INFRA-1a / CAB-2203 sunset.",
                _OLD_PREFIX,
                ",".join(sorted(deprecated_keys_emitted)),
                _NEW_PREFIX,
            )
        return values

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
            result: list[str] = json.loads(self.exclude_paths)
            return result
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
