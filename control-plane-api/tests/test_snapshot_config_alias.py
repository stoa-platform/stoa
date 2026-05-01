"""CAB-2199 / INFRA-1a S6 + Phase 3-B — regression guards for STOA_API_SNAPSHOT_* rename + alias.

The S6 sub-scope renames the error-snapshot env prefix from
``STOA_SNAPSHOTS_`` (plural, conflicts with the unrelated Rust gateway
``STOA_SNAPSHOT_*`` singular) to ``STOA_API_SNAPSHOT_`` (singular + ``_API_``
scope). Legacy prefix is honored as a per-field ``AliasChoices`` for one
release with deprecation warning + Prometheus metric. Conflicts (same
suffix, different value across old/new prefix in any source) fail boot.

**Phase 3-B hardening covered** (BH-INFRA1a-003 / 004 / 009 / 011 / 014 / 017):

- Scanner scoped to declared field suffixes — extraneous env vars matching
  the prefix but no real field do NOT trigger spurious boot failures.
- ``_env_file=`` runtime override is honored by the scanner (not just by
  Pydantic-Settings field resolution).
- Conflict error message is **value-blind**: lists source key names only,
  never the conflicting values. Eliminates the need for a secret-name
  heuristic at the error boundary.
- No mutate-on-raise side effect — ``_is_secret_env_key`` /
  ``_redact_value`` are kept as defence-in-depth helpers (still tested
  here so the contract for any future log path stays valid).

Tests:
- new prefix (``STOA_API_SNAPSHOT_*``) resolves.
- legacy alias (``STOA_SNAPSHOTS_*``) resolves with deprecation log.
- legacy alias increments Prometheus metric exactly once per (key, process).
- conflicting old/new values fail boot with value-blind error.
- matching old/new values do not raise.
- legacy alias surface covers dotenv (cwd path).
- conflict scanner reads BOTH process env AND cwd dotenv.
- runtime ``_env_file=`` non-cwd path honored for alias resolution AND
  for the conflict scanner (BH-INFRA1a-004).
- ``_env_file=None`` disables the dotenv scan.
- extraneous prefix-matching env vars (no declared field) do NOT trigger
  spurious conflicts (BH-INFRA1a-003).
- ``_is_secret_env_key`` heuristic direct unit test (defence-in-depth
  helper; not called by the validator path post Phase 3-B).
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
    cleared one-shot Counter guard so tests are order-independent.

    Phase 3-B: clear ALL declared field suffixes (not the partial 6 of
    Phase 2) by introspecting ``SnapshotSettings.model_fields``. Closes
    BH-INFRA1a-011 — the partial fixture would let an inherited
    ``STOA_SNAPSHOTS_CAPTURE_ON_4XX=true`` from a parent shell trip the
    scanner during unrelated tests.
    """
    monkeypatch.chdir(tmp_path)
    declared_suffixes = {name.upper() for name in SnapshotSettings.model_fields}
    for prefix in ("STOA_SNAPSHOTS_", "STOA_API_SNAPSHOT_"):
        for suffix in declared_suffixes:
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


def test_legacy_alias_from_cwd_dotenv_is_honored(tmp_path):
    """Default-cwd ``.env`` is read by the scanner. Critical: a developer
    who keeps ``STOA_SNAPSHOTS_*`` in their local ``.env`` after the rename
    ships must not silently lose their config."""
    # Fixture chdirs to tmp_path; write the cwd .env there.
    (tmp_path / ".env").write_text("STOA_SNAPSHOTS_ENABLED=false\n")
    s = SnapshotSettings()  # default _env_file=".env" → cwd
    assert s.enabled is False


def test_conflict_between_new_env_and_old_cwd_dotenv_fails(tmp_path, monkeypatch):
    """Conflict scanner must read BOTH process env AND the cwd dotenv."""
    (tmp_path / ".env").write_text("STOA_SNAPSHOTS_ENABLED=false\n")
    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "true")
    with pytest.raises(ValueError, match="Conflicting config"):
        SnapshotSettings()


def test_runtime_env_file_override_honored_for_alias_resolution(tmp_path):
    """Phase 3-B BH-INFRA1a-004 — the ``_env_file=`` runtime override
    points at a non-cwd dotenv; the scanner AND the alias resolution
    must both see it.

    Setup distinguishes cwd (no .env) from the override path so the
    test cannot pass coincidentally via cwd-fallback.
    """
    other_dir = tmp_path / "config"
    other_dir.mkdir()
    env_file = other_dir / "snapshots.env"
    env_file.write_text("STOA_SNAPSHOTS_ENABLED=false\n")
    # cwd is tmp_path (fixture chdir); cwd has no .env
    assert not (tmp_path / ".env").exists()

    s = SnapshotSettings(_env_file=str(env_file))
    assert s.enabled is False  # legacy alias from non-cwd dotenv resolved


def test_runtime_env_file_override_seen_by_conflict_scanner(tmp_path, monkeypatch):
    """Phase 3-B BH-INFRA1a-004 — the conflict scanner reads the runtime
    ``_env_file=`` override, not just cwd ``.env``.

    Pre-Phase-3-B the scanner only opened the static class-level
    ``.env`` from cwd, so a conflict between env (new prefix) and a
    non-cwd dotenv (legacy prefix) was silently missed.
    """
    other_dir = tmp_path / "config"
    other_dir.mkdir()
    env_file = other_dir / "snapshots.env"
    env_file.write_text("STOA_SNAPSHOTS_ENABLED=false\n")
    assert not (tmp_path / ".env").exists()

    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "true")
    with pytest.raises(ValueError, match="Conflicting config"):
        SnapshotSettings(_env_file=str(env_file))


def test_env_file_none_disables_dotenv_scan(tmp_path, monkeypatch):
    """Phase 3-B — passing ``_env_file=None`` to disable dotenv resolution
    (Pydantic-Settings convention) ALSO suppresses the scanner's dotenv
    pass so a stale cwd ``.env`` is not read against the caller's intent.
    """
    (tmp_path / ".env").write_text("STOA_SNAPSHOTS_ENABLED=false\n")
    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "true")
    # With _env_file=None, the dotenv (which would conflict) is ignored.
    s = SnapshotSettings(_env_file=None)
    assert s.enabled is True


def test_extraneous_prefix_no_spurious_conflict(monkeypatch):
    """Phase 3-B BH-INFRA1a-003 — env vars matching either prefix but no
    declared field MUST NOT trigger a boot fail.

    Pre-Phase-3-B, the scanner iterated all prefix-matching env vars and
    raised on any same-suffix divergence regardless of whether the
    suffix corresponded to a real field. Leftover legacy keys on shared
    K8s namespaces or CI runners would block boot for unrelated reasons.
    """
    monkeypatch.setenv("STOA_SNAPSHOTS_NOT_A_DECLARED_FIELD", "old-value")
    monkeypatch.setenv("STOA_API_SNAPSHOT_NOT_A_DECLARED_FIELD", "new-value")
    # Must not raise — neither suffix matches any SnapshotSettings field.
    s = SnapshotSettings()
    assert s.enabled is True  # default preserved


def test_conflict_error_format_value_blind(monkeypatch):
    """Phase 3-B BH-INFRA1a-014 — conflict errors list source key names
    only, NEVER the conflicting values.

    Replaces the Phase 2 secret-name heuristic that masked values for
    ``*SECRET*``/``*KEY*``/``*TOKEN*``/``*PASSWORD*`` keys but leaked
    raw values for everything else (including non-heuristic-matching
    secret-bearing keys like ``DB_DSN`` containing a Postgres URL with
    embedded password).
    """
    monkeypatch.setenv("STOA_SNAPSHOTS_STORAGE_BUCKET", "old-bucket-name")
    monkeypatch.setenv("STOA_API_SNAPSHOT_STORAGE_BUCKET", "new-bucket-name")
    with pytest.raises(ValueError) as exc_info:
        SnapshotSettings()
    msg = str(exc_info.value)

    # Key names ARE shown — operators need them to debug.
    assert "STOA_SNAPSHOTS_STORAGE_BUCKET" in msg
    assert "STOA_API_SNAPSHOT_STORAGE_BUCKET" in msg

    # Values are NEVER shown — neither secret-named nor non-secret.
    assert "old-bucket-name" not in msg
    assert "new-bucket-name" not in msg

    # Message points to the actionable remedy.
    assert "Remove the legacy" in msg or "remove the legacy" in msg.lower()


def test_conflict_error_value_blind_for_secret_named_keys_too(monkeypatch):
    """Counter-test of the value-blind contract: secret-bearing key names
    ALSO get value-omitted treatment (same code path)."""
    monkeypatch.setenv("STOA_SNAPSHOTS_STORAGE_SECRET_KEY", "oldval-aaaa")
    monkeypatch.setenv("STOA_API_SNAPSHOT_STORAGE_SECRET_KEY", "newval-bbbb")
    with pytest.raises(ValueError) as exc_info:
        SnapshotSettings()
    msg = str(exc_info.value)
    # Key names visible; values absent regardless of secret-name match.
    assert "STOA_SNAPSHOTS_STORAGE_SECRET_KEY" in msg
    assert "STOA_API_SNAPSHOT_STORAGE_SECRET_KEY" in msg
    assert "oldval-aaaa" not in msg
    assert "newval-bbbb" not in msg


def test_secret_helper_substring_match():
    """Direct test of `_is_secret_env_key` — defence-in-depth helper kept
    for any future log path that includes values. NOT called by the
    Phase 3-B conflict scanner (which is value-blind by design)."""
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
