"""CAB-1889 CP-2: startup validation for the Git provider config.

Verifies the `_hydrate_and_validate_git` model validator on Settings:
- In production, missing creds for the selected provider crash the app.
- In dev/staging, the same mistakes only warn.
- Tokens for the *inactive* provider are tolerated but warn.
- Literal rejects unknown GIT_PROVIDER values at schema-load time.
- The default code (GIT_PROVIDER=github) without a GITHUB_TOKEN also
  crashes in prod — documents R-3 (conftest.py default is gitlab while
  Settings default is github).
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError


def _settings_env(monkeypatch, **overrides) -> None:
    """Reset the Git env vars then apply per-test overrides.

    Using monkeypatch so each test is isolated; conftest sets the
    GITLAB defaults at import time but they live in os.environ and
    need explicit unsetting per test.
    """
    keys = [
        "GIT_PROVIDER",
        "GITHUB_TOKEN",
        "GITLAB_TOKEN",
        "GITLAB_PROJECT_ID",
        "ENVIRONMENT",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)


class TestProductionValidationCrashes:
    """ENVIRONMENT=production + missing creds -> Settings() raises ValidationError."""

    def test_github_missing_token_crashes(self, monkeypatch):
        _settings_env(monkeypatch, ENVIRONMENT="production", GIT_PROVIDER="github")

        from src.config import Settings

        with pytest.raises(ValidationError, match="GITHUB_TOKEN is empty"):
            Settings()

    def test_gitlab_missing_token_crashes(self, monkeypatch):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="gitlab",
            GITLAB_PROJECT_ID="12345",
        )

        from src.config import Settings

        with pytest.raises(ValidationError, match="GITLAB_TOKEN is empty"):
            Settings()

    def test_gitlab_missing_project_id_crashes(self, monkeypatch):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="gitlab",
            GITLAB_TOKEN="glpat-xxx",
        )

        from src.config import Settings

        with pytest.raises(ValidationError, match="GITLAB_PROJECT_ID is empty"):
            Settings()

    def test_default_provider_github_without_token_crashes(self, monkeypatch):
        """R-3: Settings default is github; without GITHUB_TOKEN, prod crashes.

        Documents the gap between conftest.py (defaults to gitlab) and the
        code default in Settings (github). A fresh deployment that only
        sets ENVIRONMENT=production hits this.
        """
        _settings_env(monkeypatch, ENVIRONMENT="production")

        from src.config import Settings

        with pytest.raises(ValidationError, match="GITHUB_TOKEN is empty"):
            Settings()


class TestDevOnlyWarns:
    """ENVIRONMENT != production + missing creds -> warning, no crash."""

    def test_dev_missing_github_token_warns(self, monkeypatch, caplog):
        _settings_env(monkeypatch, ENVIRONMENT="dev", GIT_PROVIDER="github")

        from src.config import Settings

        caplog.set_level(logging.WARNING, logger="src.config")
        settings = Settings()

        assert settings.git.provider == "github"
        assert any("GITHUB_TOKEN is empty" in rec.message for rec in caplog.records)

    def test_staging_missing_gitlab_token_warns(self, monkeypatch, caplog):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="staging",
            GIT_PROVIDER="gitlab",
            GITLAB_PROJECT_ID="12345",
        )

        from src.config import Settings

        caplog.set_level(logging.WARNING, logger="src.config")
        settings = Settings()

        assert settings.git.provider == "gitlab"
        assert any("GITLAB_TOKEN is empty" in rec.message for rec in caplog.records)


class TestInactiveProviderTokenWarns:
    """Active provider valid + inactive provider token set -> warning."""

    def test_github_active_with_gitlab_token_warns(self, monkeypatch, caplog):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="github",
            GITHUB_TOKEN="ghp-aaa",
            GITLAB_TOKEN="glpat-bbb",
        )

        from src.config import Settings

        caplog.set_level(logging.WARNING, logger="src.config")
        settings = Settings()

        assert settings.git.provider == "github"
        assert any(
            "GITLAB_TOKEN is also set" in rec.message
            and "Inactive provider credentials" in rec.message
            for rec in caplog.records
        )

    def test_gitlab_active_with_github_token_warns(self, monkeypatch, caplog):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="gitlab",
            GITLAB_TOKEN="glpat-aaa",
            GITLAB_PROJECT_ID="12345",
            GITHUB_TOKEN="ghp-bbb",
        )

        from src.config import Settings

        caplog.set_level(logging.WARNING, logger="src.config")
        settings = Settings()

        assert settings.git.provider == "gitlab"
        assert any(
            "GITHUB_TOKEN is also set" in rec.message
            and "Inactive provider credentials" in rec.message
            for rec in caplog.records
        )


class TestLiteralRejectsUnknownProvider:
    """Literal["github", "gitlab"] rejects typos at schema-load time."""

    def test_bitbucket_rejected(self, monkeypatch):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="dev",
            GIT_PROVIDER="bitbucket",
        )

        from src.config import Settings

        with pytest.raises(ValidationError, match="Input should be 'github' or 'gitlab'"):
            Settings()

    def test_mixed_case_rejected(self, monkeypatch):
        """CAB-1889 CP-2: Literal is case-sensitive. 'GitHub' is rejected."""
        _settings_env(
            monkeypatch,
            ENVIRONMENT="dev",
            GIT_PROVIDER="GitHub",
        )

        from src.config import Settings

        with pytest.raises(ValidationError, match="Input should be 'github' or 'gitlab'"):
            Settings()


class TestValidConfigDoesNotWarn:
    """Sanity: a fully coherent config boots clean."""

    def test_github_valid_no_warnings(self, monkeypatch, caplog):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="github",
            GITHUB_TOKEN="ghp-aaa",
        )

        from src.config import Settings

        caplog.set_level(logging.WARNING, logger="src.config")
        settings = Settings()

        assert settings.git.provider == "github"
        # No Git-related warning should have fired
        assert not any(
            "GITHUB_" in rec.message or "GITLAB_" in rec.message for rec in caplog.records
        )

    def test_gitlab_valid_no_warnings(self, monkeypatch, caplog):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="gitlab",
            GITLAB_TOKEN="glpat-aaa",
            GITLAB_PROJECT_ID="12345",
        )

        from src.config import Settings

        caplog.set_level(logging.WARNING, logger="src.config")
        settings = Settings()

        assert settings.git.provider == "gitlab"
        assert not any(
            "GITHUB_" in rec.message or "GITLAB_" in rec.message for rec in caplog.records
        )
