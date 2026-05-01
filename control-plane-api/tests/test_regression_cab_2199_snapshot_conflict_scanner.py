"""Regression tests for CAB-2199 snapshot conflict scanner hardening."""

from __future__ import annotations

import pytest

from src.features.error_snapshots.config import _METRIC_EMITTED_KEYS, SnapshotSettings


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Run with no ambient snapshot env vars or cwd dotenv leakage."""
    monkeypatch.chdir(tmp_path)
    declared_suffixes = {name.upper() for name in SnapshotSettings.model_fields}
    for prefix in ("STOA_SNAPSHOTS_", "STOA_API_SNAPSHOT_"):
        for suffix in declared_suffixes:
            monkeypatch.delenv(f"{prefix}{suffix}", raising=False)
    _METRIC_EMITTED_KEYS.clear()


def test_regression_cab_2199_snapshot_scanner_ignores_unknown_suffixes(monkeypatch):
    """Prefix-matching keys for undeclared fields must not block boot."""
    monkeypatch.setenv("STOA_SNAPSHOTS_NOT_A_FIELD", "legacy")
    monkeypatch.setenv("STOA_API_SNAPSHOT_NOT_A_FIELD", "canonical")

    settings = SnapshotSettings()

    assert settings.enabled is True


def test_regression_cab_2199_snapshot_scanner_honors_runtime_env_file(tmp_path, monkeypatch):
    """The conflict scanner must inspect the same runtime _env_file as pydantic-settings."""
    env_file = tmp_path / "runtime.env"
    env_file.write_text("STOA_SNAPSHOTS_ENABLED=false\n", encoding="utf-8")
    monkeypatch.setenv("STOA_API_SNAPSHOT_ENABLED", "true")

    with pytest.raises(ValueError, match="Conflicting config"):
        SnapshotSettings(_env_file=str(env_file))


def test_regression_cab_2199_snapshot_conflict_error_omits_values(monkeypatch):
    """Conflict errors may show source keys, but never the conflicting values."""
    monkeypatch.setenv("STOA_SNAPSHOTS_STORAGE_BUCKET", "legacy-bucket-value")
    monkeypatch.setenv("STOA_API_SNAPSHOT_STORAGE_BUCKET", "canonical-bucket-value")

    with pytest.raises(ValueError) as exc_info:
        SnapshotSettings()

    msg = str(exc_info.value)
    assert "STOA_SNAPSHOTS_STORAGE_BUCKET" in msg
    assert "STOA_API_SNAPSHOT_STORAGE_BUCKET" in msg
    assert "legacy-bucket-value" not in msg
    assert "canonical-bucket-value" not in msg
