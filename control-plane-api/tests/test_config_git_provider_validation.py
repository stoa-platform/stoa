"""CAB-1889 CP-2: startup validation for the Git provider config.

Verifies the `_hydrate_and_validate_git` model validator on Settings:
- In production, missing creds for the selected provider crash the app.
- In dev/staging, the same mistakes only warn.
- Tokens for the *inactive* provider are tolerated but warn.
- Literal rejects unknown GIT_PROVIDER values at schema-load time.
- The default code (GIT_PROVIDER=github) without a GITHUB_TOKEN also
  crashes in prod — documents R-3 (conftest.py default is gitlab while
  Settings default is github).
- CP-2 B-1: `repr(Settings())` does not leak credentials.
- CP-2 A-1: whitespace-only tokens are rejected; trailing newlines stripped.
- CP-2 C-1: GIT_PROVIDER accepts mixed case + whitespace (backward compat).
- CP-2 E-1: GITHUB_ORG / GITHUB_CATALOG_REPO non-empty; GITLAB_URL shape.
"""

# ruff: noqa: S106
# The whole point of this test file is to exercise the config validator
# with fake credential strings. Every `_settings_env(..., GITHUB_TOKEN=...)`
# would otherwise trip S106 "possible hardcoded password". Scope the waiver
# to this file (file-level directive above) rather than tagging ~20 lines.

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError


def _settings_env(monkeypatch, **overrides) -> None:
    """Reset the Git env vars then apply per-test overrides.

    Using monkeypatch so each test is isolated; conftest sets the
    GITLAB defaults at import time but they live in os.environ and
    need explicit unsetting per test.

    CAB-1889 CP-2 E-1: also resets GITHUB_ORG, GITHUB_CATALOG_REPO
    and GITLAB_URL so tests can assert the validator's new
    identity/URL-shape checks without inheriting shell env.
    """
    keys = [
        "GIT_PROVIDER",
        "GITHUB_TOKEN",
        "GITHUB_ORG",
        "GITHUB_CATALOG_REPO",
        "GITHUB_WEBHOOK_SECRET",
        "GITLAB_URL",
        "GITLAB_TOKEN",
        "GITLAB_PROJECT_ID",
        "GITLAB_WEBHOOK_SECRET",
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


class TestReprDoesNotLeakCredentials:
    """CAB-1889 CP-2 B-1: the four credential flat fields are ``SecretStr``
    so ``repr(Settings(...))`` never exposes raw tokens or webhook secrets.

    Previously the fields were ``str`` and a single ``logger.debug(settings)``
    or an unhandled exception carrying the instance in its locals dict would
    emit the plaintext secret into structured logs, where the defense-in-depth
    ``SecretRedactor`` filter only covers known PAT prefixes.
    """

    def test_repr_does_not_leak_any_credential(self, monkeypatch):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="github",
            GITHUB_TOKEN="ghp_should_never_leak_123456",
            GITHUB_WEBHOOK_SECRET="whsec_github_should_not_leak",
            GITLAB_TOKEN="glpat_should_never_leak_abc",
            GITLAB_WEBHOOK_SECRET="whsec_gitlab_should_not_leak",
            GITLAB_PROJECT_ID="1",
        )

        from src.config import Settings

        rendered = repr(Settings())
        for secret in (
            "ghp_should_never_leak_123456",
            "whsec_github_should_not_leak",
            "glpat_should_never_leak_abc",
            "whsec_gitlab_should_not_leak",
        ):
            assert secret not in rendered, f"repr(Settings()) leaked {secret!r}"


class TestTokenWhitespaceHandling:
    """CAB-1889 CP-2 A-1: tokens are stripped at the hydration boundary.

    Whitespace-only values are rejected; trailing newlines from K8s
    file-mounted secrets are normalised away so the downstream provider
    client sees the raw credential rather than ``"ghp_x\\n"``.
    """

    def test_whitespace_only_github_token_rejected_in_prod(self, monkeypatch):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="github",
            GITHUB_TOKEN="   ",
            GITHUB_ORG="stoa-platform",
            GITHUB_CATALOG_REPO="stoa-catalog",
        )

        from src.config import Settings

        with pytest.raises(ValidationError, match="GITHUB_TOKEN is empty"):
            Settings()

    def test_whitespace_only_gitlab_token_rejected_in_prod(self, monkeypatch):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="gitlab",
            GITLAB_TOKEN="  \n",
            GITLAB_PROJECT_ID="1",
        )

        from src.config import Settings

        with pytest.raises(ValidationError, match="GITLAB_TOKEN is empty"):
            Settings()

    def test_trailing_newline_token_is_stripped(self, monkeypatch):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="github",
            GITHUB_TOKEN="ghp_valid_token\n",
        )

        from src.config import Settings

        settings = Settings()
        assert settings.git.github.token.get_secret_value() == "ghp_valid_token"


class TestGitProviderCaseInsensitive:
    """CAB-1889 CP-2 C-1: backward compat for deployments that pre-date
    the ``Literal`` narrowing. The ``field_validator`` lowercases + strips
    the raw ``GIT_PROVIDER`` env value before Literal narrowing fires.
    """

    def test_mixed_case_provider_accepted(self, monkeypatch):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="GitHub",
            GITHUB_TOKEN="ghp_x",
        )

        from src.config import Settings

        settings = Settings()
        assert settings.git.provider == "github"

    def test_uppercase_provider_accepted(self, monkeypatch):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="GITLAB",
            GITLAB_TOKEN="glpat_x",
            GITLAB_PROJECT_ID="1",
        )

        from src.config import Settings

        settings = Settings()
        assert settings.git.provider == "gitlab"

    def test_provider_with_whitespace_and_mixed_case(self, monkeypatch):
        """Locks both C-1 (case) and A-1 (whitespace) on the most sensitive
        field: ``GIT_PROVIDER=" GitHub\\n"`` from a badly quoted ConfigMap
        must normalise to ``"github"`` and boot cleanly.
        """
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER=" GitHub\n",
            GITHUB_TOKEN="ghp_x",
        )

        from src.config import Settings

        settings = Settings()
        assert settings.git.provider == "github"


class TestIdentityAndUrlValidation:
    """CAB-1889 CP-2 E-1: identity fields (org, repo) must be non-empty
    for the selected provider, and GITLAB_URL must be syntactically valid
    http(s) with a non-empty netloc.
    """

    def test_empty_github_org_rejected_in_prod(self, monkeypatch):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="github",
            GITHUB_TOKEN="ghp_x",
            GITHUB_ORG="",
            GITHUB_CATALOG_REPO="stoa-catalog",
        )

        from src.config import Settings

        with pytest.raises(ValidationError, match="GITHUB_ORG is empty"):
            Settings()

    def test_empty_github_catalog_repo_rejected_in_prod(self, monkeypatch):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="github",
            GITHUB_TOKEN="ghp_x",
            GITHUB_ORG="stoa-platform",
            GITHUB_CATALOG_REPO="",
        )

        from src.config import Settings

        with pytest.raises(ValidationError, match="GITHUB_CATALOG_REPO is empty"):
            Settings()

    @pytest.mark.parametrize(
        "bad_url",
        [
            "not-a-url",
            "gitlab.corp",
            "ftp://gitlab.corp",
            "https://",
            "",
        ],
    )
    def test_invalid_gitlab_url_rejected_in_prod(self, monkeypatch, bad_url):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="gitlab",
            GITLAB_TOKEN="glpat_x",
            GITLAB_PROJECT_ID="1",
            GITLAB_URL=bad_url,
        )

        from src.config import Settings

        with pytest.raises(ValidationError, match="GITLAB_URL is not a valid http"):
            Settings()

    @pytest.mark.parametrize(
        "good_url",
        [
            "https://gitlab.com",
            "http://gitlab.corp",
            "https://gitlab.corp/path/subpath/",
            "https://gitlab.corp:8443/",
        ],
    )
    def test_valid_gitlab_url_accepted(self, monkeypatch, good_url):
        _settings_env(
            monkeypatch,
            ENVIRONMENT="production",
            GIT_PROVIDER="gitlab",
            GITLAB_TOKEN="glpat_x",
            GITLAB_PROJECT_ID="1",
            GITLAB_URL=good_url,
        )

        from src.config import Settings

        settings = Settings()
        assert settings.git.gitlab.url == good_url
