"""Application version defaults to pyproject.toml and honors env overrides."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from src.config import Settings, _default_app_version

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _pyproject_version() -> str:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def _settings_env(monkeypatch, **env: str) -> None:
    """Keep git provider validation satisfied when building a new Settings()."""
    monkeypatch.setenv("GIT_PROVIDER", "gitlab")
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "1")
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("APP_VERSION", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_default_app_version_matches_pyproject():
    expected = _pyproject_version()
    assert expected
    assert expected != "2.0.0"
    assert _default_app_version() == expected


def test_settings_default_version_matches_pyproject(monkeypatch):
    _settings_env(monkeypatch)
    assert _pyproject_version() == Settings().VERSION


def test_settings_version_env_override(monkeypatch):
    _settings_env(monkeypatch, VERSION="9.9.9")
    assert Settings().VERSION == "9.9.9"


def test_settings_app_version_alias_override(monkeypatch):
    _settings_env(monkeypatch, APP_VERSION="8.8.8")
    assert Settings().VERSION == "8.8.8"


@pytest.mark.asyncio
async def test_health_payload_uses_settings_version(monkeypatch):
    """The legacy /health handler reports Settings.VERSION."""
    from src import main as main_mod
    from src.main import health_legacy

    monkeypatch.setattr(main_mod.settings, "VERSION", "3.2.1")
    payload = await health_legacy()
    assert payload == {"status": "healthy", "version": "3.2.1"}
