"""Tests for GitProvider ABC and factory (CAB-1890)."""

from unittest.mock import patch

import pytest

from src.services.git_provider import GitProvider, git_provider_factory


class TestGitProviderABC:
    """Verify the ABC contract cannot be instantiated directly."""

    def test_cannot_instantiate_abc(self):
        """GitProvider is abstract — direct instantiation must raise TypeError."""
        with pytest.raises(TypeError):
            GitProvider()

    def test_abc_defines_required_methods(self):
        """All 6 abstract methods must be declared on the ABC."""
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
        }
        assert abstract_methods == expected


class TestGitProviderFactory:
    """Verify factory routing based on GIT_PROVIDER setting."""

    @patch("src.services.git_provider.settings")
    def test_factory_returns_gitlab_service(self, mock_settings):
        """GIT_PROVIDER=gitlab must return a GitLabService instance."""
        mock_settings.GIT_PROVIDER = "gitlab"
        mock_settings.GITLAB_URL = "https://gitlab.com"
        mock_settings.GITLAB_TOKEN = "test-token"
        mock_settings.GITLAB_PROJECT_ID = "12345"

        provider = git_provider_factory()

        from src.services.git_service import GitLabService

        assert isinstance(provider, GitLabService)

    @patch("src.services.git_provider.settings")
    def test_factory_gitlab_case_insensitive(self, mock_settings):
        """Factory should handle case variations."""
        mock_settings.GIT_PROVIDER = "GitLab"
        mock_settings.GITLAB_URL = "https://gitlab.com"
        mock_settings.GITLAB_TOKEN = "test-token"
        mock_settings.GITLAB_PROJECT_ID = "12345"

        provider = git_provider_factory()

        from src.services.git_service import GitLabService

        assert isinstance(provider, GitLabService)

    @patch("src.services.git_provider.settings")
    def test_factory_returns_github_service(self, mock_settings):
        """GIT_PROVIDER=github must return a GitHubService instance."""
        mock_settings.GIT_PROVIDER = "github"

        provider = git_provider_factory()

        from src.services.github_service import GitHubService

        assert isinstance(provider, GitHubService)

    @patch("src.services.git_provider.settings")
    def test_factory_unknown_provider_raises(self, mock_settings):
        """Unknown provider must raise ValueError with supported values."""
        mock_settings.GIT_PROVIDER = "bitbucket"

        with pytest.raises(ValueError, match="Unsupported GIT_PROVIDER"):
            git_provider_factory()

    @patch("src.services.git_provider.settings")
    def test_factory_empty_provider_raises(self, mock_settings):
        """Empty string provider must raise ValueError."""
        mock_settings.GIT_PROVIDER = ""

        with pytest.raises(ValueError, match="Unsupported GIT_PROVIDER"):
            git_provider_factory()


class TestGitProviderConfig:
    """Verify GIT_PROVIDER config defaults in Settings."""

    def test_default_provider_is_gitlab(self):
        """Default GIT_PROVIDER must be 'github' (migrated from GitLab — CAB-1890)."""
        from src.config import Settings

        # Check class-level default (not the singleton which may have env overrides)
        field = Settings.model_fields["GIT_PROVIDER"]
        assert field.default == "github"

    def test_github_config_defaults(self):
        """GitHub config fields must have sensible defaults."""
        from src.config import Settings

        assert Settings.model_fields["GITHUB_TOKEN"].default == ""
        assert Settings.model_fields["GITHUB_ORG"].default == "stoa-platform"
        assert Settings.model_fields["GITHUB_CATALOG_REPO"].default == "stoa-catalog"
        assert Settings.model_fields["GITHUB_GITOPS_REPO"].default == "stoa-gitops"
        assert Settings.model_fields["GITHUB_WEBHOOK_SECRET"].default == ""
