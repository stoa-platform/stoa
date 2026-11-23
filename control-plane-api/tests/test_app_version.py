"""Application version defaults to pyproject.toml and honors env overrides."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from src import config as config_mod
from src.config import Settings, _default_app_version

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


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


@pytest.mark.parametrize(
    "env_vars",
    [
        {"VERSION": ""},
        {"VERSION": "   \t\n"},
        {"APP_VERSION": ""},
        {"APP_VERSION": "   "},
        {"VERSION": "", "APP_VERSION": "   "},
    ],
)
def test_settings_blank_version_falls_back_to_pyproject(monkeypatch, env_vars):
    _settings_env(monkeypatch, **env_vars)
    assert _pyproject_version() == Settings().VERSION


@pytest.mark.parametrize(
    "env_vars",
    [
        {},
        {"VERSION": ""},
        {"VERSION": "   "},
        {"APP_VERSION": ""},
        {"APP_VERSION": "   "},
        {"VERSION": "", "APP_VERSION": "   "},
    ],
)
def test_settings_blank_version_falls_back_to_dev_without_pyproject(
    monkeypatch, tmp_path, env_vars
):
    monkeypatch.setattr(config_mod, "_PYPROJECT_PATH", tmp_path / "missing-pyproject.toml")
    _settings_env(monkeypatch, **env_vars)
    assert Settings().VERSION == "0.0.0-dev"


@pytest.mark.parametrize(
    "pyproject_text",
    [
        "",
        '[project]\nname = "control-plane-api"\n',
        '[project]\nversion = ""\n',
        '[project]\nversion = "   "\n',
    ],
)
def test_default_app_version_falls_back_to_dev_for_blank_pyproject(
    monkeypatch, tmp_path, pyproject_text
):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(pyproject_text, encoding="utf-8")
    monkeypatch.setattr(config_mod, "_PYPROJECT_PATH", pyproject)
    assert _default_app_version() == "0.0.0-dev"


def test_settings_blank_version_falls_through_to_app_version(monkeypatch):
    _settings_env(monkeypatch, VERSION="   ", APP_VERSION=" 8.8.8 ")
    assert Settings().VERSION == "8.8.8"


def test_settings_trims_version_override(monkeypatch):
    _settings_env(monkeypatch, VERSION="  9.9.9  ")
    assert Settings().VERSION == "9.9.9"


def test_dockerfile_normalizes_empty_app_version_build_arg():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG APP_VERSION=0.0.0-dev" in text
    assert "ENV VERSION=${APP_VERSION:-0.0.0-dev}" in text


@pytest.mark.asyncio
async def test_health_payload_uses_settings_version(monkeypatch):
    """The legacy /health handler reports Settings.VERSION."""
    from src import main as main_mod
    from src.main import health_legacy

    monkeypatch.setattr(main_mod.settings, "VERSION", "3.2.1")
    payload = await health_legacy()
    assert payload == {"status": "healthy", "version": "3.2.1"}


@pytest.mark.asyncio
async def test_health_payload_never_serves_empty_version(monkeypatch, tmp_path):
    """Blank runtime VERSION without pyproject.toml resolves to 0.0.0-dev."""
    from src import main as main_mod
    from src.main import health_legacy

    monkeypatch.setattr(config_mod, "_PYPROJECT_PATH", tmp_path / "missing-pyproject.toml")
    _settings_env(monkeypatch, VERSION="   ")
    monkeypatch.setattr(main_mod, "settings", Settings())
    payload = await health_legacy()
    assert payload == {"status": "healthy", "version": "0.0.0-dev"}
