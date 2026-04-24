"""Tests for GitProvider ABC and factory (CAB-1890)."""

from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from src.config import GitHubConfig, GitLabConfig, GitProviderConfig
from src.services.git_provider import GitProvider, git_provider_factory


class TestGitProviderABC:
    """Verify the ABC contract cannot be instantiated directly."""

    def test_cannot_instantiate_abc(self):
        """GitProvider is abstract — direct instantiation must raise TypeError."""
        with pytest.raises(TypeError):
            GitProvider()

    def test_abc_defines_required_methods(self):
        """All abstract methods must be declared on the ABC."""
        abstract_methods = GitProvider.__abstractmethods__
        expected = {
            "connect",
            "disconnect",
            "clone_repo",
            "get_file_content",
            "list_files",
            "create_webhook",
            "delete_webhook",
            "get_repo_info",
            "create_file",
            "update_file",
            "delete_file",
            "batch_commit",
        }
        assert abstract_methods == expected


def _git_cfg(provider: str) -> GitProviderConfig:
    """Build a fully populated GitProviderConfig for factory tests.

    CAB-1889 CP-2: factory reads settings.git.provider via Literal, so the
    provider argument here is typed as str only to support the negative
    tests that bypass schema validation.
    """
    return GitProviderConfig.model_construct(
        provider=provider,
        github=GitHubConfig(org="stoa-platform", catalog_repo="stoa-catalog"),
        gitlab=GitLabConfig(
            url="https://gitlab.com",
            token=SecretStr("test-token"),
            project_id="12345",
        ),
    )


class TestGitProviderFactory:
    """Verify factory routing based on settings.git.provider."""

    @patch("src.services.git_provider.settings")
    def test_factory_returns_gitlab_service(self, mock_settings):
        """provider=gitlab must return a GitLabService instance."""
        mock_settings.git = _git_cfg("gitlab")

        provider = git_provider_factory()

        from src.services.git_service import GitLabService

        assert isinstance(provider, GitLabService)

    @patch("src.services.git_provider.settings")
    def test_factory_returns_github_service(self, mock_settings):
        """provider=github must return a GitHubService instance."""
        mock_settings.git = _git_cfg("github")

        provider = git_provider_factory()

        from src.services.github_service import GitHubService

        assert isinstance(provider, GitHubService)

    @patch("src.services.git_provider.settings")
    def test_factory_unknown_provider_raises(self, mock_settings):
        """Unsupported provider (bypassing Literal via model_construct) must raise."""
        mock_settings.git = _git_cfg("bitbucket")

        with pytest.raises(ValueError, match="Unsupported GIT_PROVIDER"):
            git_provider_factory()

    @patch("src.services.git_provider.settings")
    def test_factory_empty_provider_raises(self, mock_settings):
        """Empty provider (bypassing Literal via model_construct) must raise."""
        mock_settings.git = _git_cfg("")

        with pytest.raises(ValueError, match="Unsupported GIT_PROVIDER"):
            git_provider_factory()


class TestGitProviderConfig:
    """Verify GIT_PROVIDER config defaults in Settings."""

    def test_default_provider_is_github(self):
        """Default GIT_PROVIDER must be 'github' (migrated from GitLab — CAB-1890)."""
        from src.config import Settings

        # Check class-level default (not the singleton which may have env overrides)
        field = Settings.model_fields["GIT_PROVIDER"]
        assert field.default == "github"

    def test_github_config_defaults(self):
        """GitHub config fields must have sensible defaults.

        CAB-1889 CP-2 B-1: GITHUB_TOKEN and GITHUB_WEBHOOK_SECRET are
        ``SecretStr`` on the flat ingress (not plain ``str``), so the
        default compares via ``.get_secret_value()``.
        """
        from src.config import Settings

        assert Settings.model_fields["GITHUB_TOKEN"].default.get_secret_value() == ""
        assert Settings.model_fields["GITHUB_ORG"].default == "stoa-platform"
        assert Settings.model_fields["GITHUB_CATALOG_REPO"].default == "stoa-catalog"
        assert Settings.model_fields["GITHUB_WEBHOOK_SECRET"].default.get_secret_value() == ""


class TestSubModelsRejectUnknownKwargs:
    """CAB-1889 CP-2 I-1: ``extra="forbid"`` on GitHubConfig / GitLabConfig /
    GitProviderConfig prevents the class of silent typo drops that let the
    CP-1 token-leak fixture pass a non-existent ``catalog_project_id=``
    kwarg unnoticed. Each test supplies a complete valid payload and adds
    one extra key so the failure is unambiguously about ``extra_forbidden``,
    not ``missing``.
    """

    def test_github_config_rejects_unknown_kwargs(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            GitHubConfig(
                token=SecretStr("x"),
                org="org",
                catalog_repo="catalog",
                webhook_secret=SecretStr("y"),
                tokne=SecretStr("z"),  # typo
            )

    def test_gitlab_config_rejects_unknown_kwargs(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            GitLabConfig(
                url="https://gitlab.com",
                token=SecretStr("x"),
                project_id="1",
                webhook_secret=SecretStr("y"),
                tokne=SecretStr("z"),  # typo
            )

    def test_git_provider_config_rejects_unknown_kwargs(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            GitProviderConfig(
                provider="github",
                github=GitHubConfig(),
                gitlab=GitLabConfig(),
                default_branch="main",
                bogus_field="nope",  # unknown
            )
