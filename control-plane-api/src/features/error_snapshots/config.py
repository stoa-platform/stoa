"""Error Snapshot feature configuration.

CAB-397: Configuration loaded from environment variables.
CAB-2199 / INFRA-1a S6: env prefix renamed from ``STOA_SNAPSHOTS_`` (plural)
to ``STOA_API_SNAPSHOT_`` (singular + ``_API_`` scope) to disambiguate from
the unrelated ``STOA_SNAPSHOT_*`` (singular, in-process ring buffer) on the
Rust gateway. Legacy prefix is honored as a per-field ``AliasChoices`` for
one release, with deprecation warning + Prometheus metric. Setting both
prefixes for the same field with different values fails boot — the conflict
scanner reads from BOTH process env and the dotenv file.

CAB-2199 Phase 3-B: conflict scanner hardened
(see ``docs/infra/INFRA-1a-BUG-HUNT.md`` Family C):

- Filtered to declared field suffixes (introspect ``model_fields``) so
  leftover env vars that match the prefix but no real field do not
  trigger spurious boot failures.
- Runtime ``_env_file=`` override is honored: ``SnapshotSettings.__init__``
  captures the kwarg and runs the scanner post-``super().__init__()`` so
  it scans the same dotenv Pydantic-Settings just used for field
  resolution.
- Conflict error message is **value-blind**: it lists source key names
  only, never the conflicting values. The scanner raises a plain
  ``ValueError`` (NOT a ``model_validator``-wrapped ``ValidationError``)
  so Pydantic does not dump ``input_value=`` into the rendered exception.
  The ``_is_secret_env_key`` / ``_redact_value`` helpers are kept as
  defence-in-depth for any future log path that includes values, but
  are no longer referenced by the scanner.
- No mutate-on-raise side effect on the input dict (closes BH-017
  without needing the Phase 2 redaction loop).

All settings have sensible defaults for development.
"""

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, ClassVar, Final, Literal

from prometheus_client import Counter
from pydantic import AliasChoices, Field, field_validator
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

# Council Stage 2 #1+#2 (Phase 2 design) — secret-name heuristic kept as
# defence-in-depth ONLY. The Phase 3-B conflict scanner is value-blind
# (no raw values in the error message), so neither helper is currently
# referenced from the validator path. They remain available for any
# future log path that needs to mask values by env-var name.
#
# Substring match on the env-var name; deliberately conservative (false
# positives = mask a non-secret = harmless; false negatives = leak a
# secret = unacceptable).
_SECRET_NAME_TOKENS: tuple[str, ...] = (
    "SECRET",
    "KEY",
    "TOKEN",
    "PASSWORD",
)


def _is_secret_env_key(env_key: str) -> bool:
    """True if the env-var name suggests it carries a secret value.

    Defence-in-depth helper. Not called by the Phase 3-B conflict
    scanner (which is value-blind) but kept available for any future
    log path that includes values.
    """
    upper = env_key.upper()
    return any(token in upper for token in _SECRET_NAME_TOKENS)


def _redact_value(env_key: str, value: str) -> str:
    """Return ``value`` if ``env_key`` is non-secret, else ``"<REDACTED>"``.

    Defence-in-depth helper. See ``_is_secret_env_key`` for the contract.
    """
    return "<REDACTED>" if _is_secret_env_key(env_key) else value


# Sentinel used by ``SnapshotSettings.__init__`` to distinguish "caller
# didn't pass ``_env_file=``" from "caller passed ``_env_file=None`` to
# explicitly disable the dotenv scan".
_UNSET: Final[object] = object()


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
    fails boot — the conflict scanner reads from BOTH process env and the
    dotenv file (resolved via the runtime ``_env_file=`` override when
    provided, otherwise the static class-level default).

    Phase 3-B contract: the conflict error message lists source key names
    only — values are never surfaced (avoids leaking secrets via env-var
    contents that don't match any heuristic). The scanner is also scoped
    to declared field suffixes so leftover env vars matching the prefix
    but no field do not trigger spurious failures.
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

    def __init__(self, **kwargs: Any) -> None:
        """Phase 3-B — run the conflict scan in ``__init__`` post-super().

        The Phase 2 scanner lived in a ``model_validator(mode="before")``
        and raised ``ValueError`` from there. Pydantic wraps that into a
        ``ValidationError`` and dumps the input dict as ``input_value=...``
        in the rendered exception — which leaks the conflicting values
        even when our own error message omits them. To honor the
        value-blind contract end-to-end, we move the scan here:

        1. Capture the runtime ``_env_file`` override (pydantic-settings
           consumes it internally for field resolution but does not pass
           it to validators).
        2. Run ``super().__init__(**kwargs)`` — pydantic-settings resolves
           fields via ``AliasChoices``; either prefix populates the
           model.
        3. Scan ``os.environ`` + the dotenv directly for cross-prefix
           conflicts on declared field suffixes. Raise a plain
           ``ValueError`` (NOT ``ValidationError``) on conflict — no
           Pydantic wrapper, no input-dict dump, no leak.
        4. Emit deprecation log + Prometheus counter for legacy-prefix
           usage (one-shot per (key, process) via ``_METRIC_EMITTED_KEYS``).
        """
        env_file_kwarg = kwargs.get("_env_file", _UNSET)
        super().__init__(**kwargs)
        # Resolve dotenv path: runtime override (post-super; safe because
        # super has already consumed the kwarg) wins over the static
        # class-level default. ``_env_file=None`` means "no dotenv".
        if env_file_kwarg is _UNSET:
            env_file_path: object = self.model_config.get("env_file") or ".env"
        else:
            env_file_path = env_file_kwarg
        self._scan_for_conflicts_and_log_deprecation(env_file_path)

    @classmethod
    def _scan_for_conflicts_and_log_deprecation(cls, env_file_path: object) -> None:
        """Scan declared field suffixes across process env AND dotenv.

        Phase 3-B contract (CAB-2199 BH-INFRA1a-003 / 004 / 014 / 017):

        - **Scoped to declared field suffixes.** Iterates ``cls.model_fields``
          to derive the canonical uppercase suffix for each field, then
          filters the env scan to those. Leftover env vars matching a
          legacy prefix but NO declared field do not trigger spurious
          boot failures (BH-003).
        - **Honors the runtime ``_env_file=`` override** received from
          ``__init__`` (BH-004). ``_env_file=None`` disables the dotenv
          scan.
        - **Value-blind error.** Conflict raises ``ValueError`` (plain,
          NOT ``ValidationError``) listing source key names only — never
          the conflicting values. Eliminates the ``_is_secret_env_key``
          heuristic at the error boundary (BH-014). Because we raise
          plain ``ValueError`` outside the validator path, Pydantic does
          NOT wrap and does NOT dump ``input_value=`` (no leak via the
          wrapped exception either — closes BH-017 without needing a
          mutate-on-raise).
        """
        declared_suffixes = {name.upper() for name in cls.model_fields}

        sources: list[tuple[str, dict[str, str]]] = [("env", dict(os.environ))]
        if env_file_path:
            sources.append(("dotenv", _read_dotenv(env_file_path)))

        # Collect (suffix → {source_key: value}) for declared suffixes only.
        seen: dict[str, dict[str, str]] = {}
        for source_label, source_map in sources:
            for env_key, env_value in source_map.items():
                for prefix in (_OLD_PREFIX, _NEW_PREFIX):
                    if env_key.startswith(prefix):
                        suffix = env_key[len(prefix):]
                        if suffix in declared_suffixes:
                            seen.setdefault(suffix, {})[
                                f"{source_label}:{env_key}"
                            ] = env_value
                        break

        deprecated_keys_emitted: list[str] = []
        for suffix, source_values in seen.items():
            distinct_values = set(source_values.values())
            if len(distinct_values) > 1:
                # Value-blind conflict report: list source keys only,
                # never the conflicting values. Key names are intentionally
                # not secret; only their values can be (and those are kept
                # out of every error / log path).
                source_keys_listed = sorted(source_values.keys())
                raise ValueError(
                    f"Conflicting config for suffix {suffix!r}: "
                    f"sources {source_keys_listed} have different values. "
                    f"Remove the legacy {_OLD_PREFIX}* key or align both "
                    f"prefixes to the same value. (Values are intentionally "
                    f"omitted from this message to avoid leaking secrets.)"
                )
            for source_key in source_values:
                if _OLD_PREFIX in source_key:
                    deprecated_keys_emitted.append(source_key.split(":", 1)[1])

        if deprecated_keys_emitted:
            with _METRIC_LOCK:
                for key in deprecated_keys_emitted:
                    if key not in _METRIC_EMITTED_KEYS:
                        DEPRECATED_CONFIG_USED.labels(name=key).inc()
                        _METRIC_EMITTED_KEYS.add(key)
            logger.warning(
                "Deprecated config prefix %s used (keys: %s). "
                "Rename to %s before next release. Tracked: CAB-2199 / INFRA-1a / CAB-2203 sunset.",
                _OLD_PREFIX,
                ",".join(sorted(set(deprecated_keys_emitted))),
                _NEW_PREFIX,
            )

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
