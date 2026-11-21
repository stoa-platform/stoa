# INFRA-1a — S6 implementation: `STOA_API_SNAPSHOT_*` rename + alias + masked deprecation

> **Companion to**: `docs/infra/INFRA-1a-PLAN.md` §2.6.
> **Scope**: implementation code + test corpus for sub-scope S6 only.
> **Created**: 2026-04-29 (revision v3 — Council Stage 2 adjustments #1+#2 secret masking, #3 plan-length trim).

This file holds the implementation code blocks extracted from the master plan. The master plan retains the §2.6.a (files to touch), §2.6.b (behavioral preservation), and §2.6.e (risks). Only the §2.6.c (code) and §2.6.d (tests) live here.

**Council adjustments folded in (v3)**:

- **#1+#2 — Secret value masking**: keys matching `*SECRET*`, `*KEY*`, `*TOKEN*`, `*PASSWORD*` (case-insensitive substring match on the env-var name) have their VALUES redacted to `<REDACTED>` in the raised `ValueError` conflict message. The deprecation `logger.warning` line emits keys only (no values), but the masking helper is reused there as a defence-in-depth contract for any future log additions.
- **#3 — Plan length**: this file replaces ~290 lines of the master plan with a slim summary section in §2.6 of the master.

---

## Naming choice (master plan §2.6.c)

- Current Python: `STOA_SNAPSHOTS_*` (plural)
- Current Rust: `STOA_SNAPSHOT_*` (singular)
- **Proposed Python new prefix**: `STOA_API_SNAPSHOT_*` (singular + `_API_` namespace to make it unambiguous in `kubectl describe pod` output: an operator scanning env vars sees `STOA_API_SNAPSHOT_RETENTION_DAYS` and immediately knows it's cp-api scope).
- Section 3 #3 alternative: `STOA_API_SNAPSHOTS_*` (plural, less divergent from current Python). Rejected because Rust uses singular and we want consistency in plurality across Python/Rust scope-neutral naming. Pinned for arbitrage.

---

## Code change (`config.py`)

Uses `AliasChoices` per field for the resolution surface (which Pydantic-Settings honors uniformly across process env, dotenv file, and secrets sources) PLUS a separate conflict scanner that reads ALL of those sources, not just `os.environ`. The conflict-error and deprecation-log paths apply secret-name redaction (Council Stage 2 adjustments #1+#2) so secret values cannot leak into tracebacks/logs.

```python
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any, ClassVar

from prometheus_client import Counter
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Counter name — Prometheus client_python AUTO-APPENDS `_total` to the exposed
# metric for Counters. Pass the bare name to the constructor; the exposition
# layer adds the suffix. Decided 2026-04-29 (revision v2).
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

_OLD_PREFIX = "STOA_SNAPSHOTS_"
_NEW_PREFIX = "STOA_API_SNAPSHOT_"

# Council Stage 2 adjustments #1+#2 — values for env keys carrying secrets are
# redacted before they enter any error message or log line. Substring match on
# the env-var name; deliberately conservative (false positives = mask a
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
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Strip surrounding quotes — best-effort, not POSIX-quote-correct.
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


class SnapshotSettings(BaseSettings):
    """Configuration for error snapshot feature.

    Canonical env prefix: ``STOA_API_SNAPSHOT_*`` (revision v2 — was
    ``STOA_SNAPSHOTS_*``). Legacy prefix is honored as a per-field
    ``AliasChoices`` for one release, with deprecation warning + Prometheus
    metric. Setting both prefixes for the same field with different values
    fails boot — the conflict scanner reads from BOTH process env and dotenv
    so a `.env`-only legacy setting also triggers the gate.

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

    enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            f"{_NEW_PREFIX}ENABLED",
            f"{_OLD_PREFIX}ENABLED",
        ),
    )
    capture_on_4xx: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            f"{_NEW_PREFIX}CAPTURE_ON_4XX",
            f"{_OLD_PREFIX}CAPTURE_ON_4XX",
        ),
    )
    # ... apply AliasChoices to ALL 17 fields. (Helper: build via metaclass or
    # pre-class loop over field_specs; PR-E commit lists the full mapping.)

    @model_validator(mode="before")
    @classmethod
    def _detect_conflicts_and_emit_deprecation(
        cls, values: object
    ) -> object:
        """Scan BOTH process env AND dotenv for legacy-prefix usage.

        - Process env: ``os.environ``.
        - Dotenv: parse the configured ``env_file`` (default ``.env``) — does
          NOT depend on whether pydantic-settings has already merged it.

        Conflict (same suffix, different value across old/new prefix in any
        source) raises ValueError with secret-aware redaction. Otherwise emits
        deprecation log (KEYS only, never values) + Counter increment
        (one-shot per key per process).
        """
        env_file_path = (cls.model_config.get("env_file") or ".env")
        sources: list[tuple[str, dict[str, str]]] = [
            ("env", dict(os.environ)),
            ("dotenv", _read_dotenv(env_file_path)),
        ]

        # Collect all (suffix, source, value) where suffix is the field-name
        # tail after either prefix.
        seen: dict[str, dict[str, str]] = {}  # suffix → {source_key: value}
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
                "Rename to %s before next release. Tracked: CAB-2199 / INFRA-1a.",
                _OLD_PREFIX,
                ",".join(sorted(deprecated_keys_emitted)),
                _NEW_PREFIX,
            )
        return values
```

**Metric exposition**: `prometheus_client` Counter is exposed with auto-appended `_total` suffix at `/metrics`. Constructor name `stoa_deprecated_config_used` ⇒ exposed as `stoa_deprecated_config_used_total{name="STOA_SNAPSHOTS_ENABLED"} 1`. The metric is incremented at `SnapshotSettings.__init__` (first call to `get_snapshot_settings()` during FastAPI startup), guarded by `_METRIC_EMITTED_KEYS` so re-instantiation in tests doesn't double-count.

**Why Counter not Gauge**: the metric semantics are "config legacy was observed at boot" — a one-time event, not a running-state indicator. Counter `_total` is the standard idiom for boot-time deprecation tracking. If long-term ops want "is the legacy config currently set", that's a separate Gauge to add in a later ticket (out of 1a scope).

**Schema metadata for INFRA-1c CI gate** (per ticket "Declare alias in config schema metadata") — already declared above as `DEPRECATED_PREFIX_ALIASES: ClassVar`. Documented for reference.

---

## Tests to add (master plan §2.6.d)

`control-plane-api/tests/test_snapshot_config_alias.py`:

```python
def test_new_prefix_works(monkeypatch):
    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "false")
    monkeypatch.setenv("STOA_API_SNAPSHOT_RETENTION_DAYS", "7")
    s = SnapshotSettings()
    assert s.enabled is False
    assert s.retention_days == 7

def test_legacy_alias_honored_with_deprecation_log(monkeypatch, caplog):
    monkeypatch.setenv("STOA_SNAPSHOTS_ENABLED", "false")
    monkeypatch.setenv("STOA_SNAPSHOTS_RETENTION_DAYS", "7")
    with caplog.at_level("WARNING"):
        s = SnapshotSettings()
    assert s.enabled is False
    assert s.retention_days == 7
    assert "Deprecated config prefix STOA_SNAPSHOTS_" in caplog.text

def test_legacy_alias_increments_prometheus_metric(monkeypatch):
    from src.features.error_snapshots.config import DEPRECATED_CONFIG_USED
    before = DEPRECATED_CONFIG_USED.labels(name="STOA_SNAPSHOTS_ENABLED")._value.get()
    monkeypatch.setenv("STOA_SNAPSHOTS_ENABLED", "false")
    SnapshotSettings()
    after = DEPRECATED_CONFIG_USED.labels(name="STOA_SNAPSHOTS_ENABLED")._value.get()
    assert after == before + 1

def test_conflicting_old_and_new_values_fails_boot(monkeypatch):
    monkeypatch.setenv("STOA_SNAPSHOTS_ENABLED", "false")
    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "true")
    with pytest.raises(ValueError, match="Conflicting config"):
        SnapshotSettings()

def test_matching_old_and_new_values_no_error(monkeypatch):
    monkeypatch.setenv("STOA_SNAPSHOTS_ENABLED", "false")
    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "false")
    s = SnapshotSettings()
    assert s.enabled is False

def test_legacy_alias_from_dotenv_file_is_honored(tmp_path, monkeypatch):
    """Regression — the alias surface must cover dotenv, not just process env.

    Critical: a developer who keeps `STOA_SNAPSHOTS_*` in their local `.env`
    after the rename ships must not silently lose their config. This is the
    most-likely real-world scenario for the legacy prefix surviving past PR-E.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("STOA_SNAPSHOTS_ENABLED=false\n")
    s = SnapshotSettings(_env_file=str(tmp_path / ".env"))
    assert s.enabled is False

def test_conflict_between_new_env_and_old_dotenv_fails(tmp_path, monkeypatch):
    """Conflict scanner must read BOTH process env AND dotenv."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("STOA_SNAPSHOTS_ENABLED=false\n")
    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "true")
    with pytest.raises(ValueError, match="Conflicting config"):
        SnapshotSettings(_env_file=str(tmp_path / ".env"))

def test_metric_increments_once_per_key_per_process(monkeypatch):
    """One-shot guard — re-instantiating SnapshotSettings does not double-count."""
    from src.features.error_snapshots.config import (
        DEPRECATED_CONFIG_USED, _METRIC_EMITTED_KEYS,
    )
    _METRIC_EMITTED_KEYS.clear()  # reset for this test
    monkeypatch.setenv("STOA_SNAPSHOTS_ENABLED", "false")
    before = DEPRECATED_CONFIG_USED.labels(name="STOA_SNAPSHOTS_ENABLED")._value.get()
    SnapshotSettings()
    SnapshotSettings()  # second instantiation must NOT increment
    SnapshotSettings()  # third too
    after = DEPRECATED_CONFIG_USED.labels(name="STOA_SNAPSHOTS_ENABLED")._value.get()
    assert after == before + 1  # exactly one increment despite 3 inits

# Council Stage 2 adjustments #1+#2 — secret value masking in conflict path.
def test_conflict_redacts_secret_values_in_error_message(monkeypatch):
    """Regression — error message must NOT leak secret values for SECRET/KEY/TOKEN/PASSWORD env keys."""
    monkeypatch.setenv("STOA_SNAPSHOTS_STORAGE_SECRET_KEY", "oldval-aaaa")
    monkeypatch.setenv("STOA_API_SNAPSHOT_STORAGE_SECRET_KEY", "newval-bbbb")
    with pytest.raises(ValueError) as exc_info:
        SnapshotSettings()
    msg = str(exc_info.value)
    # Both values must be masked because the env-key name matches the secret heuristic
    assert "oldval-aaaa" not in msg
    assert "newval-bbbb" not in msg
    assert "<REDACTED>" in msg
    # The KEY NAMES are NOT secret — they remain visible for ops
    assert "STOA_SNAPSHOTS_STORAGE_SECRET_KEY" in msg
    assert "STOA_API_SNAPSHOT_STORAGE_SECRET_KEY" in msg

def test_conflict_does_not_redact_non_secret_values(monkeypatch):
    """Counter-test — non-secret keys (e.g. ENABLED, RETENTION_DAYS) keep their values visible."""
    monkeypatch.setenv("STOA_SNAPSHOTS_ENABLED", "false")
    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "true")
    with pytest.raises(ValueError) as exc_info:
        SnapshotSettings()
    msg = str(exc_info.value)
    # Non-secret values remain — debugging needs them
    assert "false" in msg
    assert "true" in msg
    assert "<REDACTED>" not in msg

def test_secret_helper_substring_match():
    """Direct test of `_is_secret_env_key` — SECRET/KEY/TOKEN/PASSWORD substring."""
    from src.features.error_snapshots.config import _is_secret_env_key
    assert _is_secret_env_key("STOA_SNAPSHOTS_STORAGE_SECRET_KEY")
    assert _is_secret_env_key("STOA_SNAPSHOTS_API_TOKEN")
    assert _is_secret_env_key("STOA_SNAPSHOTS_DB_PASSWORD")
    assert _is_secret_env_key("STOA_SNAPSHOTS_KEYRING")  # token KEY substring matches
    assert not _is_secret_env_key("STOA_SNAPSHOTS_ENABLED")
    assert not _is_secret_env_key("STOA_SNAPSHOTS_RETENTION_DAYS")
```

Plus update existing `test_snapshot_config.py` and `test_snapshot_storage_ops.py` to use the new prefix (default test path) but keep one `test_legacy_*` regression test per file using the old prefix.

**Test count**: 11 tests minimum (was 8 in v2 + 3 added in v3 for redaction coverage).

**Note on `KEYRING` false positive**: `_is_secret_env_key("STOA_SNAPSHOTS_KEYRING") == True` because "KEY" is a substring of "KEYRING". Acceptable — masking a non-secret value is harmless; the alternative (regex-bounded matching) adds complexity for no security gain.
