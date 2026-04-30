"""CAB-2199 / INFRA-1a S6 — regression guards for STOA_API_SNAPSHOT_* rename + alias.

The S6 sub-scope renames the error-snapshot env prefix from
``STOA_SNAPSHOTS_`` (plural, conflicts with the unrelated Rust gateway
``STOA_SNAPSHOT_*`` singular) to ``STOA_API_SNAPSHOT_`` (singular + ``_API_``
scope). Legacy prefix is honored as a per-field ``AliasChoices`` for one
release with deprecation warning + Prometheus metric. Conflicts (same
suffix, different value across old/new prefix in any source) fail boot.

Council Stage 2 #1+#2 secret masking covered: env keys matching
``*SECRET*``/``*KEY*``/``*TOKEN*``/``*PASSWORD*`` have their VALUES
redacted in the conflict ValueError. Key NAMES remain visible.

Tests:
- new prefix (``STOA_API_SNAPSHOT_*``) resolves.
- legacy alias (``STOA_SNAPSHOTS_*``) resolves with deprecation log.
- legacy alias increments Prometheus metric exactly once per (key, process).
- conflicting old/new values fail boot.
- matching old/new values do not raise.
- legacy alias surface covers dotenv (not just process env).
- conflict scanner reads BOTH process env and dotenv.
- secret-bearing values redacted in conflict error message.
- non-secret values remain visible (counter-test).
- ``_is_secret_env_key`` heuristic direct unit test.
"""

from __future__ import annotations

import pytest

from src.features.error_snapshots.config import (
    DEPRECATED_CONFIG_USED,
    _METRIC_EMITTED_KEYS,
    SnapshotSettings,
    _is_secret_env_key,
)


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Each test in tmp cwd with no .env + cleared snapshot env vars +
    cleared one-shot Counter guard so tests are order-independent."""
    monkeypatch.chdir(tmp_path)
    for prefix in ("STOA_SNAPSHOTS_", "STOA_API_SNAPSHOT_"):
        for suffix in (
            "ENABLED",
            "RETENTION_DAYS",
            "STORAGE_BUCKET",
            "STORAGE_SECRET_KEY",
            "STORAGE_ACCESS_KEY",
            "MASKING_EXTRA_HEADERS",
        ):
            monkeypatch.delenv(f"{prefix}{suffix}", raising=False)
    _METRIC_EMITTED_KEYS.clear()


def test_new_prefix_resolves(monkeypatch):
    """``STOA_API_SNAPSHOT_*`` is the canonical prefix and must resolve fields."""
    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "false")
    monkeypatch.setenv("STOA_API_SNAPSHOT_RETENTION_DAYS", "7")

    s = SnapshotSettings()
    assert s.enabled is False
    assert s.retention_days == 7


def test_legacy_alias_resolves_with_deprecation_log(monkeypatch, caplog):
    """Legacy ``STOA_SNAPSHOTS_*`` prefix is honored as AliasChoices for
    one release; emits a WARNING log line citing CAB-2199 / CAB-2203."""
    monkeypatch.setenv("STOA_SNAPSHOTS_ENABLED", "false")
    monkeypatch.setenv("STOA_SNAPSHOTS_RETENTION_DAYS", "14")

    with caplog.at_level("WARNING", logger="src.features.error_snapshots.config"):
        s = SnapshotSettings()

    assert s.enabled is False
    assert s.retention_days == 14
    assert any(
        "Deprecated config prefix STOA_SNAPSHOTS_" in r.message for r in caplog.records
    )
    # Sunset tracker reference present
    assert any("CAB-2203" in r.message for r in caplog.records)


def test_legacy_alias_increments_prometheus_metric(monkeypatch):
    """Each legacy-prefix env key increments the Counter once per process."""
    before = DEPRECATED_CONFIG_USED.labels(name="STOA_SNAPSHOTS_ENABLED")._value.get()
    monkeypatch.setenv("STOA_SNAPSHOTS_ENABLED", "false")
    SnapshotSettings()
    after = DEPRECATED_CONFIG_USED.labels(name="STOA_SNAPSHOTS_ENABLED")._value.get()
    assert after == before + 1


def test_metric_increments_once_per_key_per_process(monkeypatch):
    """One-shot guard — re-instantiating SnapshotSettings does not double-count."""
    monkeypatch.setenv("STOA_SNAPSHOTS_ENABLED", "false")
    before = DEPRECATED_CONFIG_USED.labels(name="STOA_SNAPSHOTS_ENABLED")._value.get()
    SnapshotSettings()
    SnapshotSettings()  # second instantiation must NOT increment
    SnapshotSettings()  # third too
    after = DEPRECATED_CONFIG_USED.labels(name="STOA_SNAPSHOTS_ENABLED")._value.get()
    assert after == before + 1, "exactly one increment despite 3 inits"


def test_conflicting_old_and_new_values_fails_boot(monkeypatch):
    """Same suffix, different values across old/new prefix → ValueError."""
    monkeypatch.setenv("STOA_SNAPSHOTS_ENABLED", "false")
    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "true")
    with pytest.raises(ValueError, match="Conflicting config"):
        SnapshotSettings()


def test_matching_old_and_new_values_no_error(monkeypatch):
    """Same suffix, same value across old/new prefix → no error, no surprise."""
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
    env_file = tmp_path / ".env"
    env_file.write_text("STOA_SNAPSHOTS_ENABLED=false\n")
    s = SnapshotSettings(_env_file=str(env_file))
    assert s.enabled is False


def test_conflict_between_new_env_and_old_dotenv_fails(tmp_path, monkeypatch):
    """Conflict scanner must read BOTH process env AND dotenv."""
    env_file = tmp_path / ".env"
    env_file.write_text("STOA_SNAPSHOTS_ENABLED=false\n")
    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "true")
    with pytest.raises(ValueError, match="Conflicting config"):
        SnapshotSettings(_env_file=str(env_file))


def test_conflict_redacts_secret_values_in_error_message(monkeypatch):
    """Council #1+#2 — error message must NOT leak secret values for
    SECRET/KEY/TOKEN/PASSWORD env keys. The key NAME is NOT secret —
    it remains visible for ops debugging."""
    monkeypatch.setenv("STOA_SNAPSHOTS_STORAGE_SECRET_KEY", "oldval-aaaa")
    monkeypatch.setenv("STOA_API_SNAPSHOT_STORAGE_SECRET_KEY", "newval-bbbb")
    with pytest.raises(ValueError) as exc_info:
        SnapshotSettings()
    msg = str(exc_info.value)
    # Both values masked because the env-key name matches the secret heuristic
    assert "oldval-aaaa" not in msg
    assert "newval-bbbb" not in msg
    assert "<REDACTED>" in msg
    # The key NAMES remain visible for ops
    assert "STOA_SNAPSHOTS_STORAGE_SECRET_KEY" in msg
    assert "STOA_API_SNAPSHOT_STORAGE_SECRET_KEY" in msg


def test_conflict_does_not_redact_non_secret_values(monkeypatch):
    """Counter-test — non-secret keys (ENABLED) keep their values visible
    so ops can see what is conflicting and decide which side wins."""
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
    # Positive matches
    assert _is_secret_env_key("STOA_SNAPSHOTS_STORAGE_SECRET_KEY")
    assert _is_secret_env_key("FOO_API_TOKEN")
    assert _is_secret_env_key("DB_PASSWORD")
    # `KEY` substring also matches `KEYRING` — acceptable per IMPL-S6 doc
    # (false positive: mask a non-secret = harmless; false negative would
    # be unacceptable).
    assert _is_secret_env_key("STOA_SNAPSHOTS_KEYRING")
    # Negative matches
    assert not _is_secret_env_key("STOA_SNAPSHOTS_ENABLED")
    assert not _is_secret_env_key("STOA_SNAPSHOTS_RETENTION_DAYS")
